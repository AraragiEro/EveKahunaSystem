import asyncio
from copy import deepcopy
import json
import time
from math import ceil
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveIndustryPlanConfigFlowDBUtils,
    EveIndustryPlanConfigFlowConfigDBUtils
)
from src_v2.core.database.neo4j_utils import Neo4jAssetUtils as NAU
from src_v2.model.EVE.industry.blueprint import BPManager as BPM
from src_v2.model.EVE.sde import SdeUtils
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.connect_manager import get_neo4j_manager as ndm
from src_v2.core.database.connect_manager import get_postgres_manager as pdm
from src_v2.model.EVE.sde.sde_builder.database_manager import get_sde_database_manager as sdm

from src_v2.core.utils import KahunaException

from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.user.user_manager import UserManager
from src_v2.core.database.kahuna_database_utils_v2 import EveIndustryPlanDBUtils
from src_v2.model.EVE.eveesi import eveesi
from src_v2.model.EVE.market.market_manager import MarketManager

from src_v2.core.log import logger

NULL_MANU_SEC_BONUS = 2.1
NULL_REAC_SEC_BONUS = 1.1

RIG_MATER_EFF = {
    0: 0,
    1: 0.02,
    2: 0.024
}
RIG_TIME_EFF = {
    0: 0,
    1: 0.2,
    2: 0.24,
}

MANU_STRUCTURE_MATER_EFF = 1 - 0.01

SMALL_STRUCTURE_MANU_TIME_EFF = 1 - 0.15
MID_STRUCTURE_MANU_TIME_EFF = 1 - 0.2
LARGE_STRUCTURE_MANU_TIME_EFF = 1 - 0.3

MID_STRUCTURE_REAC_TIME_EFF = 1 - 0.25
SMALL_STRUCTURE_REAC_TIME_EFF = 1

MANU_SKILL_TIME_EFF = 1 - 0.354
REAC_SKILL_TIME_EFF = 1 - 0.2

# 默认蓝图材料效率
DEFAULT_FACTION_MATERIAL_EFFICIENCY = 0
DEFAULT_T2_MATERIAL_EFFICIENCY = 0.02
DEFAULT_OTHER_MATERIAL_EFFICIENCY = 0.1

# 默认蓝图时间效率
DEFAULT_FACTION_TIME_EFFICIENCY = 0
DEFAULT_T2_TIME_EFFICIENCY = 0.04
DEFAULT_OTHER_TIME_EFFICIENCY = 0.2

LARGE_COST_EFF = 0.05
MID_COST_EFF = 0.04
SMALL_COST_EFF = 0.03


class OpLockManager:
    def __init__(self):
        self.running_job_update_lock = asyncio.Lock()
        self.bp_asset_prepare_lock = asyncio.Lock()
        self.asset_prepare_lock = asyncio.Lock()
        self.running_asset_prepare_lock = asyncio.Lock()
        self.refresh_system_cost_lock = asyncio.Lock()
        self.refresh_market_price_lock = asyncio.Lock()
        self.structure_info_refresh_lock = asyncio.Lock()

    def reset_lock(self):
        self.running_job_update_lock = asyncio.Lock()
        self.bp_asset_prepare_lock = asyncio.Lock()
        self.asset_prepare_lock = asyncio.Lock()
        self.running_asset_prepare_lock = asyncio.Lock()
        self.refresh_system_cost_lock = asyncio.Lock()
        self.refresh_market_price_lock = asyncio.Lock()
        self.structure_info_refresh_lock = asyncio.Lock()


op_lock_manager = OpLockManager()


class ConfigFlowOperateCenter():
    def __init__(self, user_name: str, plan_name: str, plan_settings: dict, sub_process=False, dm=None):
        # 同步初始化基本属性
        self.total_progress_key = ""
        self.current_progress_key = ""
        self.user_name = user_name
        self.plan_name = plan_name
        self.plan_settings = plan_settings
        self.structure_rig_confs = []
        self.structure_assign_confs = []
        self.material_tag_confs = []
        self.default_blueprint_confs = []
        self.load_asset_confs = []
        self.config_flow = []
        self.max_job_split_count_confs = []
        self.cache = {}
        self._running_jobs_update = False
        self._running_jobs = []

        if not sub_process:
            self.npm = ndm()
            self.pdm = pdm()
            self.rdm = rdm()
            self.sdm = sdm()
        else:
            self.npm = dm[0] if dm else None
            self.pdm = dm[1] if dm else None
            self.rdm = dm[2] if dm else None
            self.sdm = dm[3] if dm else None

        self._bp_prepare = False
        self._bp_asset = {}
        self._bp_used = {}

        self._structure_info = {}
        self._node_type_dict = {}

        self._asset_prepare = False
        self._asset = {}
        self._asset_allocate = {}
        self._material_allocate = {}

        self._running_asset_prepare = False
        self._running_asset = {}
        self._running_asset_allocate = {}

        self.calculate_cache = {}

        self.work_list_cache = {}

        self.node_need_quantity = {}

        self.set_uped_jobs = {}

        self._system_cost_status = False
        self._system_cost = {}

        self.type_eff_cache = {}

        self.type_assign_structure_info_cache_status = False
        self.structure_info_cache = {}
        self.type_assign_structure_info_cache = {}

        self._market_price_status = False
        self._type_adjust_price = {}

        self.index_product_dict = {}
        self.product_num_dict = {}

        self.all_node_in_relation_dict = {}
        self.all_relation_between_nodes_dict = {}
        self.all_ralation_dict = {}

    @classmethod
    async def create(cls, user_name: str, plan_name: str, plan_settings: dict, sub_process=False, dm=None):
        """异步工厂方法，用于创建并初始化对象"""
        instance = cls(user_name, plan_name, plan_settings,
                       sub_process=sub_process, dm=dm)
        await instance._async_init(user_name, plan_name)
        return instance

    async def _async_init(self, user_name: str, plan_name: str):
        """异步初始化逻辑"""
        config_flow = await EveIndustryPlanConfigFlowDBUtils.select_configflow_by_user_name_and_plan_name(
            user_name, plan_name, pdm=self.pdm
        )
        if not config_flow:
            self.config_flow = []
        else:
            self.config_flow = config_flow.config_list

        for config_id in self.config_flow:
            config = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_id(config_id, pdm=self.pdm)
            if not config:
                logger.warning(f"配置{config_id}不存在")
                continue

            if config.config_type == 'StructureRigConfig':
                self.structure_rig_confs.append(config.config_value)
            elif config.config_type == 'StructureAssignConf':
                self.structure_assign_confs.append(config.config_value)
            elif config.config_type == 'MaterialTagConf':
                self.material_tag_confs.append(config.config_value)
            elif config.config_type == 'DefaultBlueprintConf':
                self.default_blueprint_confs.append(config.config_value)
            elif config.config_type == 'LoadAssetConf':
                self.load_asset_confs.append(config.config_value)
            elif config.config_type == 'MaxJobSplitCountConf':
                self.max_job_split_count_confs.append(config.config_value)
            else:
                raise KahunaException(f"配置类型{config.config_type}不存在")

    # 获取指定typeid在配置许可中的资产列表
    async def get_type_assets(self, type_id: int):
        if f"get_type_assets_{type_id}" in self.cache:
            return self.cache[f"get_type_assets_{type_id}"]
        container_owner_list = []
        for config in self.load_asset_confs:
            container_owner_list.append(
                [config['asset_container_id'],
                config['asset_owner_id'],
                config.get('location_flag', None)])
        assets = await NAU.get_asset_by_type_id_in_container_owner_list(type_id, container_owner_list, self.npm)
        self.cache[f"get_type_assets_{type_id}"] = assets
        return assets

    # 获取指定typeid在配置许可中的资产总数量
    async def get_type_assets_quantity(self, type_id: int):
        assets = await self.get_type_assets(type_id)
        return sum([asset['quantity'] for asset in assets])

    # 获取正在运行的joblit
    async def get_running_job_list(self):
        async with op_lock_manager.running_job_update_lock:
            if self._running_jobs_update:
                return self._running_jobs
            # 获取能访问的权限
            # 获取个人角色
            characters = await CharacterManager().get_user_all_characters(self.user_name)
            character_ids = [
                character.character_id for character in characters]

            # 检查主角色同公司是否有总监
            main_character_id = await UserManager().get_main_character_id(self.user_name)
            main_character = await CharacterManager().get_character_by_character_id(main_character_id)
            director_character_ids = await CharacterManager().get_director_character_id_of_corporation(main_character.corporation_id)
            director = None
            for director_character_id in director_character_ids:
                director = await CharacterManager().get_character_by_character_id(director_character_id)
                try:
                    await director.ac_token
                    character_ids.append(director.character_id)
                    break
                except Exception as e:
                    logger.warning(f"获取总监角色 {director_character_id} 的token失败: {str(e)}")
                    continue

            running_job_list = []
            # 获取运行中的job
            for character_id in character_ids:
                character = await CharacterManager().get_character_by_character_id(character_id)
                jobs = await eveesi.characters_character_id_industry_jobs(character.ac_token, character_id)
                if not jobs:
                    continue
                running_job_list.extend(jobs)

            # 获取公司运行中的job
            if director:
                corp_jobs = await eveesi.corporations_corporation_id_industry_jobs(director.ac_token, director.corporation_id)
                for job in corp_jobs:
                    running_job_list.extend(job)

            self._running_jobs = running_job_list
            self._running_jobs_update = True
            return running_job_list

    # 获取某typeid正在运行的作业数量
    # 或通过container权限进行过滤，输出目标符才会计数
    async def get_running_job_count(self, type_id: int):
        running_job_list = await self.get_running_job_list()
        access_container_list = []
        for config in self.load_asset_confs:
            access_container_list.append(config['asset_container_id'])
        count = 0
        for job in running_job_list:
            if job['product_type_id'] == type_id:
                if job['output_location_id'] in access_container_list:
                    count += job['runs']
        return count

    async def get_running_job_tableview_data(self, consider_running_job: bool):
        if not consider_running_job:
            return []

        running_job_list = await self.get_running_job_list()
        access_container_list = []
        for config in self.load_asset_confs:
            access_container_list.append(config['asset_container_id'])

        installer_data = []
        for job in running_job_list:
            if job['output_location_id'] not in access_container_list:
                continue
            character_public_info = await CharacterManager().get_public_character_info_by_character_id(job['installer_id'])
            active_type = await BPM.get_activity_id_by_product_typeid(job['product_type_id'], pdm=self.sdm)
            if active_type == 1:
                activity_name = "制造"
            elif active_type == 11:
                activity_name = "反应"
            else:
                activity_name = "未知"

            installer_data.append({
                "character_name": character_public_info.name,
                "character_title": character_public_info.title,
                "activity_name": activity_name,
                "product_type_name": await SdeUtils.get_name_by_id(job['product_type_id'], zh=True, pdm=self.sdm),
                **job
            })

        return installer_data

    async def _is_match_keyword(self, conf_list, type_id: int):
        group_list = [await SdeUtils.get_groupname_by_id(type_id, pdm=self.sdm), await SdeUtils.get_groupname_by_id(type_id, zh=True, pdm=self.sdm)]
        meta_list = [await SdeUtils.get_metaname_by_typeid(type_id, pdm=self.sdm), await SdeUtils.get_metaname_by_typeid(type_id, zh=True, pdm=self.sdm)]
        bp_name_list = [await BPM.get_bp_name_by_typeid(type_id, pdm=self.sdm), await BPM.get_bp_name_by_typeid(type_id, zh=True, pdm=self.sdm)]
        category_list = [await SdeUtils.get_category_by_id(type_id, pdm=self.sdm), await SdeUtils.get_category_by_id(type_id, zh=True, pdm=self.sdm)]
        market_group_list = await SdeUtils.get_market_group_list(type_id, pdm=self.sdm)
        market_group_list.extend(await SdeUtils.get_market_group_list(type_id, zh=True, pdm=self.sdm))

        for config in conf_list:
            match = True
            res = None
            for kw in config['keyword_groups']:
                if kw['keyword_type'] == 'marketGroup' and kw['keyword'] in market_group_list:
                    continue
                elif kw['keyword_type'] == 'group' and kw['keyword'] in group_list:
                    continue
                elif kw['keyword_type'] == 'meta' and kw['keyword'] in meta_list:
                    continue
                elif kw['keyword_type'] == 'blueprint' and kw['keyword'] in bp_name_list:
                    continue
                elif kw['keyword_type'] == 'category' and kw['keyword'] in category_list:
                    continue
                else:
                    match = False
                    break

            if match:
                return True, config
        return False, None

    async def is_material_type(self, type_id: int):
        res, _ = await self._is_match_keyword(self.material_tag_confs, type_id)
        return res

    async def get_max_job_run(self, type_id: int) -> int:
        max_acctive_time = (3 * 24 + 6) * 3600
        active_time = await BPM.get_production_time(type_id, pdm=self.sdm)
        max_job_run = max(1, max_acctive_time // active_time)

        if not active_time:
            return 100000000
        res, conf = await self._is_match_keyword(self.max_job_split_count_confs, type_id)
        if not res:
            return max_job_run

        try:
            if conf["judge_type"] == 'count':
                return max(1, conf.get('max_count', max_job_run))
            elif conf["judge_type"] == 'time':
                _, time_eff = await self.get_efficiency(type_id)
                _, fake_time_eff = await self.get_conf_eff(type_id)
            else:
                return max_job_run

            try:
                d = conf.get("max_time_date", None)
                if not d:
                    d = "00:00:00"
                h, m, s = d.split(":")
                day = conf.get("max_time_day", 0)
                max_time = day * 24 * 3600 + \
                    int(h) * 3600 + int(m) * 60 + int(s)

                return max(1, max_time // (active_time * time_eff * fake_time_eff))
            except Exception as e:
                logger.error(f"获取最大作业运行数量失败: {e}")
                logger.error(f"配置: {conf}")
            return max_job_run
        except Exception as e:
            logger.error(f"获取最大作业运行数量失败: {e}")
            logger.error(f"配置: {conf}")
            return max_job_run

    async def get_relation_need_calculate(self, product_type_id: int):
        product_type = self._node_type_dict.get(product_type_id, None)
        if not product_type:
            res = await self.is_material_type(product_type_id)
            if res:
                self._node_type_dict[product_type_id] = "material"
            else:
                self._node_type_dict[product_type_id] = "product"
            product_type = self._node_type_dict[product_type_id]

        return product_type == "product"

    def get_node_type(self, type_id: int):
        return self._node_type_dict.get(type_id, None)

    async def prepare_bp_asset(self):
        async with op_lock_manager.bp_asset_prepare_lock:
            if self._bp_prepare:
                return
            # 可访问的容器list
            container_id_list = [conf['asset_container_id']
                                 for conf in self.load_asset_confs]

            # 获取个人角色
            characters = await CharacterManager().get_user_all_characters(self.user_name)
            character_ids = [
                character.character_id for character in characters]

            # 检查主角色同公司是否有总监
            main_character_id = await UserManager().get_main_character_id(self.user_name)
            main_character = await CharacterManager().get_character_by_character_id(main_character_id)
            director_character_ids = await CharacterManager().get_director_character_id_of_corporation(main_character.corporation_id)
            director = None
            for director_character_id in director_character_ids:
                director = await CharacterManager().get_character_by_character_id(director_character_id)
                try:
                    await director.ac_token
                    character_ids.append(director.character_id)
                    break
                except Exception as e:
                    logger.warning(f"获取总监角色 {director_character_id} 的token失败: {str(e)}")
                    continue

            bp_assets = {}
            # 获取运行中的job
            for character_id in character_ids:
                assets_json = await self.rdm.r.get(f"bp_assets_cha_{character_id}")
                if not assets_json:
                    character = await CharacterManager().get_character_by_character_id(character_id)
                    assets = await eveesi.characters_character_id_blueprints(character.ac_token, character_id)
                    if assets:
                        await self.rdm.r.set(f"bp_assets_cha_{character_id}", json.dumps(assets), ex=15 * 60)
                else:
                    assets = json.loads(assets_json)
                for page in assets:
                    if not page:
                        continue
                    for bp in page:
                        if bp['location_id'] not in container_id_list:
                            continue
                        if bp["runs"] == -1:
                            bp_type = "bpo"
                        else:
                            bp_type = "bpc"
                        if bp['type_id'] not in bp_assets:
                            bp_assets[bp['type_id']] = {
                                "bpc": [],
                                "bpo": []
                            }
                        bp_assets[bp['type_id']][bp_type].append(bp)

            # 获取公司的蓝图资产
            if director:
                assets_json = await self.rdm.r.get(f"bp_assets_cor_{director.corporation_id}")
                if not assets_json:
                    assets = await eveesi.corporations_corporation_id_blueprints(director.ac_token, director.corporation_id)
                    if assets:
                        await self.rdm.r.set(f"bp_assets_cor_{director.corporation_id}", json.dumps(assets), ex=15 * 60)
                else:
                    assets = json.loads(assets_json)
                for page in assets:
                    for bp in page:
                        if bp['location_id'] not in container_id_list:
                            continue
                        if bp["runs"] == -1:
                            bp_type = "bpo"
                        else:
                            bp_type = "bpc"
                        if bp['type_id'] not in bp_assets:
                            bp_assets[bp['type_id']] = {
                                "bpc": [],
                                "bpo": []
                            }
                        bp_assets[bp['type_id']][bp_type].append(bp)

            self._bp_asset = bp_assets
            self._bp_prepare = True

    async def get_bp_object(self, type_id: int, less_job_run: bool, considerate_bp_relation: bool):
        bp_type_id = await BPM.get_bp_id_by_prod_typeid(type_id, pdm=self.sdm)

        fake_bp = {
            "type_id": bp_type_id,
            "item_id": None,
            "location_flag": None,
            "location_id": None,
            "material_efficiency": None,
            "time_efficiency": None,
            "quantity": None,
            "runs": -1,
            "fake": True
        }

        if not considerate_bp_relation:
            return fake_bp

        # 更新bp资产缓存
        if not self._bp_prepare:
            await self.prepare_bp_asset()
        # 先用bpc
        bpc_list = self._bp_asset.get(bp_type_id, {}).get("bpc", [])
        bpc_list.sort(key=lambda x: (x["runs"]), reverse=True)
        for bpc in bpc_list:
            if less_job_run < bpc["runs"]:
                continue
            if self._bp_used.get(bpc["item_id"], 1) > 0:
                res = {
                    "type_id": bp_type_id,
                    "item_id": bpc["item_id"],
                    "location_flag": bpc["location_flag"],
                    "location_id": bpc["location_id"],
                    "material_efficiency": bpc["material_efficiency"],
                    "time_efficiency": bpc["time_efficiency"],
                    "quantity": bpc["quantity"],
                    "runs": bpc["runs"],
                    "fake": False
                }
                self._bp_used[bpc["item_id"]] = 0
                return res
        for bpc in reversed(bpc_list):
            if self._bp_used.get(bpc["item_id"], 1) > 0:
                res = {
                    "type_id": bp_type_id,
                    "item_id": bpc["item_id"],
                    "location_flag": bpc["location_flag"],
                    "location_id": bpc["location_id"],
                    "material_efficiency": bpc["material_efficiency"],
                    "time_efficiency": bpc["time_efficiency"],
                    "quantity": bpc["quantity"],
                    "runs": bpc["runs"],
                    "fake": False
                }
                self._bp_used[bpc["item_id"]] = 0
                return res

        # 再用bpo
        bpo_list = self._bp_asset.get(bp_type_id, {}).get("bpo", [])
        bpo_list.sort(key=lambda x: (x["quantity"]), reverse=True)
        for index, bpo in enumerate(bpo_list):
            if self._bp_used.get(bpo["item_id"], 1) > 0:
                res = {
                    "type_id": bp_type_id,
                    "item_id": bpo["item_id"],
                    "location_flag": bpo["location_flag"],
                    "location_id": bpo["location_id"],
                    "material_efficiency": bpo["material_efficiency"],
                    "time_efficiency": bpo["time_efficiency"],
                    "quantity": bpo["quantity"],
                    "runs": bpo["runs"],
                    "fake": False
                }
                if bpo["item_id"] not in self._bp_used:
                    if bpo["quantity"] > 0:
                        self._bp_used[bpo["item_id"]] = bpo["quantity"] - 1
                    else:
                        self._bp_used[bpo["item_id"]] = 0
                else:
                    self._bp_used[bpo["item_id"]] -= 1
                return res

        return fake_bp

    async def get_bp_status(self, type_id: int, consider_bp_relation: bool):
        if not consider_bp_relation:
            return 0, {
                "bpc": 0,
                "bpo": 0
            }

        if not self._bp_prepare:
            await self.prepare_bp_asset()

        bp_type_id = await BPM.get_bp_id_by_prod_typeid(type_id, pdm=self.sdm)
        bpc_list = self._bp_asset.get(bp_type_id, {}).get("bpc", [])
        bpo_list = self._bp_asset.get(bp_type_id, {}).get("bpo", [])

        bp_quantity = len(bpc_list) + len(bpo_list)
        bp_jobs = {
            "bpc": sum([bpc["runs"] for bpc in bpc_list]),
            "bpo": len(bpo_list)
        }

        return bp_quantity, bp_jobs

    async def refresh_structure_info(self):
        async with op_lock_manager.structure_info_refresh_lock:
            if self.type_assign_structure_info_cache_status:
                return
            structure_infos = await NAU.get_structure_nodes(self.npm)
            self._structure_info = {
                info['structure_name']: info for info in structure_infos}
            self.type_assign_structure_info_cache_status = True

    async def get_type_assign_structure_info(self, type_id: int) -> dict | None:
        """
        Args:
            type_id: int
        Returns:
            None or 
        structure_info: {
            "item_id": int,
            "owner_id": int,
            "region_id": int,
            "region_name": str,
            "structure_id": int,
            "structure_name": str,
            "structure_type": str,
            "system_id": int,
            "system_name": str,
        }
        """
        if not self.type_assign_structure_info_cache_status:
            await self.refresh_structure_info()
        if type_id in self.type_assign_structure_info_cache:
            return self.type_assign_structure_info_cache[type_id]

        res, conf = await self._is_match_keyword(self.structure_assign_confs, type_id)
        if res:
            # 获取建筑
            structure_name = conf['structure_name']
            structure_info = self._structure_info.get(structure_name, None)
            self.type_assign_structure_info_cache[type_id] = structure_info
            return structure_info
        return None

    async def get_efficiency(self, type_id: int):
        if type_id in self.type_eff_cache:
            return self.type_eff_cache[type_id]
        # 建筑
        structure_eff = {
            "mater_eff": 1,
            "time_eff": 1
        }
        # 建筑插
        structure_rig_eff = {
            "mater_eff": 1,
            "time_eff": 1
        }
        # 蓝图 这里不负责
        # bp_eff = [1, 1]

        # 时间还包括技能
        skill_eff = {
            "time_eff": 1
        }

        # 找到物品分配的建筑
        res, conf = await self._is_match_keyword(self.structure_assign_confs, type_id)
        active_type = await BPM.get_activity_id_by_product_typeid(type_id, pdm=self.sdm)
        if res:
            # 获取建筑
            structure_name = conf['structure_name']
            from src_v2.model.EVE.industry.industry_utils.config_utils import VIRTUAL_STRUCTURE_DICT
            if structure_name in VIRTUAL_STRUCTURE_DICT:
                virtual_structure_type = structure_name.split('-')[1]
                structure_info = {
                    "structure_id": VIRTUAL_STRUCTURE_DICT[structure_name],
                    "structure_name": structure_name,
                    "structure_type": virtual_structure_type,
                    "system_id": 0,
                    "system_name": "虚拟",
                    "item_id": VIRTUAL_STRUCTURE_DICT[structure_name],
                }
                self._structure_info[structure_name] = structure_info
            elif structure_name not in self._structure_info:
                # 如果 _structure_info 为空，先确保 refresh_structure_info() 已被调用
                if not self.type_assign_structure_info_cache_status:
                    await self.refresh_structure_info()

                # 刷新后再次检查
                if structure_name not in self._structure_info:
                    logger.error(
                        f"结构 '{structure_name}' 未找到。self._structure_info: {self._structure_info}")
                    raise KahunaException(
                        f"结构 '{structure_name}' 未找到。请检查结构分配配置中的结构名称是否正确，或确保该结构已添加到系统中。")
            structure_info = self._structure_info[structure_name]

            # 制造 =======================================================
            if structure_info['structure_type'] == 'Sotiyo':
                structure_eff['mater_eff'] *= MANU_STRUCTURE_MATER_EFF
                structure_eff['time_eff'] *= LARGE_STRUCTURE_MANU_TIME_EFF
            elif structure_info['structure_type'] == 'Azbel':
                structure_eff['mater_eff'] *= MANU_STRUCTURE_MATER_EFF
                structure_eff['time_eff'] *= MID_STRUCTURE_MANU_TIME_EFF
            elif structure_info['structure_type'] == 'Raitaru':
                structure_eff['mater_eff'] *= MANU_STRUCTURE_MATER_EFF
                structure_eff['time_eff'] *= SMALL_STRUCTURE_MANU_TIME_EFF
            # 反应 =======================================================
            elif structure_info['structure_type'] == 'Tatara':
                structure_eff['mater_eff'] *= 1
                structure_eff['time_eff'] *= MID_STRUCTURE_REAC_TIME_EFF
            elif structure_info['structure_type'] == 'Athanor':
                structure_eff['mater_eff'] *= 1
                structure_eff['time_eff'] *= SMALL_STRUCTURE_REAC_TIME_EFF

            # 建筑插 ======================================================
            for rig_conf in self.structure_rig_confs:
                if rig_conf['structure_id'] == structure_info['item_id']:
                    bunus = NULL_MANU_SEC_BONUS if active_type == 1 else NULL_REAC_SEC_BONUS
                    structure_rig_eff['mater_eff'] *= (
                        1 - RIG_MATER_EFF[rig_conf['mater_eff_level']] * bunus)
                    structure_rig_eff['time_eff'] *= (
                        1 - RIG_TIME_EFF[rig_conf['time_eff_level']] * bunus)

        # 蓝图这里不负责

        # 技能
        if active_type == 1:
            skill_eff['time_eff'] *= MANU_SKILL_TIME_EFF
        elif active_type == 11:
            skill_eff['time_eff'] *= REAC_SKILL_TIME_EFF
        else:
            raise KahunaException(f"活动类型{active_type}不存在")

        self.type_eff_cache[type_id] = (
            structure_eff['mater_eff'] * structure_rig_eff['mater_eff'],
            structure_eff['time_eff'] *
            structure_rig_eff['time_eff'] * skill_eff['time_eff']
        )
        return self.type_eff_cache[type_id]

    async def get_conf_eff(self, type_id: int):
        if f"get_conf_eff_{type_id}" in self.cache:
            return self.cache[f"get_conf_eff_{type_id}"]
        res, conf = await self._is_match_keyword(self.default_blueprint_confs, type_id)
        if res:
            self.cache[f"get_conf_eff_{type_id}"] = (
                1 - 0.01 * conf['mater_eff'], 1 - 0.01 * conf['time_eff'])
        else:
            self.cache[f"get_conf_eff_{type_id}"] = (1, 1)
        return self.cache[f"get_conf_eff_{type_id}"]

    async def prepare_asset(self):
        async with op_lock_manager.asset_prepare_lock:
            if self._asset_prepare:
                return

            container_id_list = [[conf['asset_container_id'],
                                  conf['asset_owner_id'],
                                  conf.get('location_flag', None)] for conf in self.load_asset_confs]

            assets = await NAU.get_asset_in_container_owner_list(container_id_list, self.npm)
            for asset in assets:
                self._asset[asset['type_id']] = self._asset.get(
                    asset['type_id'], 0) + asset['quantity']
            self._asset_prepare = True

    async def deal_asset_quantity(self, quantity: int, type_id: int, index_id: int):
        if not self._asset_prepare:
            await self.prepare_asset()

        if (type_id, index_id) in self._asset_allocate:
            return self._asset_allocate[(type_id, index_id)]

        if type_id in self._asset:
            allocate_quantity = min(quantity, self._asset[type_id])
            self._asset[type_id] -= allocate_quantity
            self._asset_allocate[(type_id, index_id)
                                 ] = quantity - allocate_quantity
        else:
            self._asset_allocate[(type_id, index_id)] = quantity

        return self._asset_allocate[(type_id, index_id)]

    async def get_structure_material_provide_dict(self):
        """
        Returns:
            Dict: 建筑物资供给字典
            {
                "structure_id": {
                    "structure_name": str,
                    "structure_type": str,
                    "system_id": int,
                    "system_name": str,
                    "region_id": int,
                    "region_name": str,
                    "material_provide": Dict[int, int]
                }
            }
        """
        structure_material_provide_dict = {}
        contaier_conf_dict = {conf['asset_container_id']: conf for conf in self.load_asset_confs}

        assets = await NAU.get_asset_in_container_owner_list([[conf['asset_container_id'], conf['asset_owner_id'], conf.get('location_flag', None)] for conf in self.load_asset_confs], self.npm)
        for asset in assets:
            asset_container_conf = contaier_conf_dict.get(
                asset['location_id'], None)
            if not asset_container_conf:
                continue
            if asset_container_conf["structure_id"] not in structure_material_provide_dict:
                structure_info = await NAU.get_structure_node_by_structure_id(asset_container_conf["structure_id"], self.npm)
                if structure_info:
                    structure_material_provide_dict[structure_info["structure_id"]
                                                    ] = structure_info
                else:
                    logger.error(
                        f"structure_info {asset_container_conf['structure_id']} not found")
                    continue
                structure_material_provide_dict[structure_info["structure_id"]]["material_provide"] = {
                }
            else:
                structure_info = structure_material_provide_dict[asset_container_conf["structure_id"]]
            structure_node = structure_material_provide_dict[structure_info["structure_id"]]
            structure_node["material_provide"][asset['type_id']] = structure_node["material_provide"].get(
                asset['type_id'], 0) + asset['quantity']

        return structure_material_provide_dict

    async def get_work_material_need(self, work: dict):
        material_need = await BPM.get_bp_materials(work['type_id'], pdm=self.sdm)
        runs = work['runs']
        mater_eff = work['mater_eff']
        material_need_dict = {}
        for material_type_id, material_quantity in material_need.items():
            material_need_dict[material_type_id] = ceil(
                material_quantity * runs * (mater_eff if material_quantity != 1 else 1))
        return material_need_dict

    async def calculate_work_material_avaliable(self, work_list: list):
        if not self._asset_prepare:
            await self.prepare_asset()
        disable = False
        for work in work_list:
            if disable:
                work['avaliable'] = False
                continue
            material_need = await BPM.get_bp_materials(work['type_id'], pdm=self.sdm)
            runs = work['runs']
            mater_eff = work['mater_eff']

            for material_type_id, material_quantity in material_need.items():
                if material_type_id not in self._material_allocate:
                    self._material_allocate[material_type_id] = self._asset.get(
                        material_type_id, 0)

                if ceil(material_quantity * runs * (mater_eff if material_quantity != 1 else 1)) > self._material_allocate[material_type_id]:
                    work['avaliable'] = False
                    disable = True
                    break
            if disable:
                continue

            if material_type_id not in self._material_allocate:
                logger.error(
                    f"material_type_id {material_type_id} not in _material_allocate")
            for material_type_id, material_quantity in material_need.items():
                self._material_allocate[material_type_id] -= ceil(
                    material_quantity * runs * (mater_eff if material_quantity != 1 else 1))
            work['avaliable'] = True

    async def prepare_running_asset(self):
        async with op_lock_manager.running_asset_prepare_lock:
            if self._running_asset_prepare:
                return
            container_id_list = [conf['asset_container_id']
                                 for conf in self.load_asset_confs]

            running_job_list = await self.get_running_job_list()
            for job in running_job_list:
                if job['output_location_id'] not in container_id_list:
                    continue

                self._running_asset[job['product_type_id']] = self._running_asset.get(job['product_type_id'], 0) + await BPM.get_bp_product_quantity_typeid(job['product_type_id'], pdm=self.sdm) * job['runs']
            self._running_asset_prepare = True

    async def deal_running_job_quantity(self, quantity: int, type_id: int, index_id: int):
        if not self._running_asset_prepare:
            await self.prepare_running_asset()

        if (type_id, index_id) in self._running_asset_allocate:
            return self._running_asset_allocate[(type_id, index_id)]

        if type_id in self._running_asset:
            allocate_quantity = min(quantity, self._running_asset[type_id])
            self._running_asset[type_id] -= allocate_quantity
            self._running_asset_allocate[(
                type_id, index_id)] = quantity - allocate_quantity
        else:
            self._running_asset_allocate[(type_id, index_id)] = quantity

        return self._running_asset_allocate[(type_id, index_id)]

    async def refresh_system_cost(self):
        async with op_lock_manager.refresh_system_cost_lock:
            if self.plan_name.startswith("calculate_cost") or await self.rdm.r.get(f"system_cost_cache:status") == "ok":
                return

            result = await eveesi.industry_systems(log=True)

            for item in result:
                data = {"solar_system_id": item["solar_system_id"]}
                for cost in item["cost_indices"]:
                    data[cost["activity"]] = cost["cost_index"]
                await self.rdm.r.hset(f"system_cost_cache:{item['solar_system_id']}", mapping=data)

            # 过期时间到下一个整小时
            now = time.time()
            next_hour = (int(now) // 3600 + 1) * 3600
            ex_seconds = int(next_hour - now)
            # 确保过期时间至少为1秒
            if ex_seconds <= 0:
                ex_seconds = 3600  # 如果计算错误，默认1小时
            await self.rdm.r.set(f"system_cost_cache:status", "ok", ex=ex_seconds)

    async def get_system_cost(self, solar_system_id: int):
        if not self._system_cost_status and await self.rdm.r.get(f"system_cost_cache:status") != "ok":
            await self.refresh_system_cost()

            system_cost = await self.rdm.r.hgetall(f"system_cost_cache:{solar_system_id}")

            self._system_cost[solar_system_id] = system_cost

            if not system_cost or "manufacturing" not in system_cost or "reaction" not in system_cost:
                return {
                    "manufacturing": 0.02 + 0.04,
                    "reaction": 0.02 + 0.04
                }
            return system_cost

        if solar_system_id in self._system_cost:
            if not self._system_cost[solar_system_id] or "manufacturing" not in self._system_cost[solar_system_id] or "reaction" not in self._system_cost[solar_system_id]:
                return {
                    "manufacturing": 0.02 + 0.04,
                    "reaction": 0.02 + 0.04
                }
            return self._system_cost[solar_system_id]

        system_cost = await self.rdm.r.hgetall(f"system_cost_cache:{solar_system_id}")
        if not system_cost or "manufacturing" not in system_cost or "reaction" not in system_cost:
            return {
                "manufacturing": 0.02 + 0.04,
                "reaction": 0.02 + 0.04
            }
        self._system_cost[solar_system_id] = system_cost
        return system_cost

    async def refresh_market_price(self):
        async with op_lock_manager.refresh_market_price_lock:
            if await self.rdm.r.get(f"market_price_cache:status") == "ok":
                return

        results = await eveesi.markets_prices(log=True)
        # results = [{'adjusted_price': 36.93619227019693, 'average_price': 33.77, 'type_id': 18}, ...]
        for data in results:
            if 'adjusted_price' not in data:
                data['adjusted_price'] = 0.0
            if 'average_price' not in data:
                data['average_price'] = 0.0

            await self.rdm.r.hset(f"market_price_cache:{data['type_id']}", mapping=data)

        # 获取到明天0点的时间间隔，单位分钟
        now = time.time()
        # 获取当前时间的struct_time
        now_struct = time.localtime(now)
        # 构造明天0点的struct_time
        tomorrow_zero_struct = time.struct_time((
            now_struct.tm_year,
            now_struct.tm_mon,
            now_struct.tm_mday + 1,
            0, 0, 0,
            now_struct.tm_wday,
            now_struct.tm_yday,
            now_struct.tm_isdst,
        ))
        # 转换为时间戳
        tomorrow_zero_ts = time.mktime(tomorrow_zero_struct)
        ex_seconds = int(tomorrow_zero_ts - now)
        # 确保过期时间至少为1秒
        if ex_seconds <= 0:
            ex_seconds = 86400  # 如果计算错误，默认24小时（1天）
        await self.rdm.r.set(f"market_price_cache:status", "ok", ex=ex_seconds)

    async def get_type_adjust_price(self, type_id: int):
        if not self._market_price_status and await self.rdm.r.get(f"market_price_cache:status") != "ok":
            await self.refresh_market_price()

        if type_id in self._type_adjust_price:
            return self._type_adjust_price[type_id]

        type_adjust_price = float(await self.rdm.r.hget(f"market_price_cache:{type_id}", "adjusted_price"))
        self._type_adjust_price[type_id] = type_adjust_price
        return type_adjust_price

    async def init_at_begin(self):
        await self.refresh_market_price()
        await self.refresh_structure_info()
        # await MarketManager().update_jita_price(rdm=self.rdm)
        if self.plan_settings.get('considerate_bp_relation', False):
            await self.prepare_bp_asset()
        if self.plan_settings.get('considerate_running_job', False):
            await self.prepare_running_asset()
        if self.plan_settings.get('considerate_asset', False):
            await self.prepare_asset()
