import asyncio
import json
from math import ceil
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveAssetPullMissionDBUtils,
    EveIndustryPlanConfigFlowDBUtils,
    EveIndustryPlanConfigFlowConfigDBUtils
)
from src_v2.core.database.neo4j_utils import Neo4jAssetUtils as NAU

from src_v2.core.utils import KahunaException

from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.user.user_manager import UserManager
from src_v2.core.database.kahuna_database_utils_v2 import EveIndustryPlanDBUtils
from src_v2.model.EVE.eveesi import eveesi
from src_v2.model.EVE.industry.industry_manager import BPM
from src_v2.model.EVE.sde import SdeUtils
from src_v2.model.EVE.industry.blueprint import BPManager

from src_v2.core.database.connect_manager import redis_manager as rds

running_job_update_lock = asyncio.Lock()
bp_asset_prepare_lock = asyncio.Lock()
asset_prepare_lock = asyncio.Lock()
running_asset_prepare_lock = asyncio.Lock()

from src_v2.core.log import logger

NULL_MANU_SEC_BONUS = 2.1
NULL_REAC_SEC_BONUS = 1.1

RIG_MATER_EFF = {
    1: 0.02,
    2: 0.024
}
RIG_TIME_EFF = {
    1: 0.2,
    2: 0.24,
}

MANU_STRUCTURE_MATER_EFF = 1 - 0.01

SMALL_STRUCTURE_MANU_TIME_EFF = 1 - 0.15
MID_STRUCTURE_MANU_TIME_EFF = 1 - 0.2
LARGE_STRUCTURE_MANU_TIME_EFF = 1 - 0.3

MID_STRUCTURE_REAC_TIME_EFF = 1 - 0.25
SMALL_STRUCTURE_REAC_TIME_EFF = 0

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

class ConfigFlowOperateCenter():
    def __init__(self, user_name: str, plan_name: str):
        # 同步初始化基本属性
        self.total_progress_key = ""
        self.current_progress_key = ""
        self.user_name = user_name
        self.plan_name = plan_name
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

    @classmethod
    async def create(cls, user_name: str, plan_name: str):
        """异步工厂方法，用于创建并初始化对象"""
        instance = cls(user_name, plan_name)
        await instance._async_init()
        return instance
    
    async def _async_init(self):
        """异步初始化逻辑"""
        config_flow = await EveIndustryPlanConfigFlowDBUtils.select_configflow_by_user_name_and_plan_name(
            self.user_name, self.plan_name
        )
        if not config_flow:
            self.config_flow = []
        else:
            self.config_flow = config_flow.config_list

        for config_id in self.config_flow:
            config = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_id(config_id)
            if not config:
                raise KahunaException(f"配置{config_id}不存在")

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
        container_list = []
        for config in self.load_asset_confs:
            container_list.append(config['asset_container_id'])
        assets = await NAU.get_asset_by_type_id_in_container_list(type_id, container_list)
        self.cache[f"get_type_assets_{type_id}"] = assets
        return assets

    # 获取指定typeid在配置许可中的资产总数量
    async def get_type_assets_quantity(self, type_id: int):
        assets = await self.get_type_assets(type_id)
        return sum([asset['quantity'] for asset in assets])

    # 获取正在运行的joblit
    async def get_running_job_list(self):
        from src_v2.core.log import logger
        async with running_job_update_lock:
            if self._running_jobs_update:
                return self._running_jobs
            # 获取能访问的权限
            # 获取个人角色  
            characters = await CharacterManager().get_user_all_characters(self.user_name)
            character_ids = [character.character_id for character in characters]

            # 检查主角色同公司是否有总监
            main_character_id = await UserManager().get_main_character_id(self.user_name)
            main_character = await CharacterManager().get_character_by_character_id(main_character_id)
            director = await CharacterManager().get_director_character_id_of_corporation(main_character.corporation_id)
            if director:
                director = await CharacterManager().get_character_by_character_id(director)
                character_ids.append(director.character_id)
            else:
                director = None

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
                corp_jobs =  await eveesi.corporations_corporation_id_industry_jobs(director.ac_token, director.corporation_id)
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

    async def _is_match_keyword(self, conf_list, type_id: int):
        group_list = [SdeUtils.get_groupname_by_id(type_id), SdeUtils.get_groupname_by_id(type_id, zh=True)]
        meta_list = [SdeUtils.get_metaname_by_typeid(type_id), SdeUtils.get_metaname_by_typeid(type_id, zh=True)]
        bp_name_list = [await BPManager.get_bp_name_by_typeid(type_id), await BPManager.get_bp_name_by_typeid(type_id, zh=True)]
        category_list = [SdeUtils.get_category_by_id(type_id), SdeUtils.get_category_by_id(type_id, zh=True)]
        market_group_list = SdeUtils.get_market_group_list(type_id)
        market_group_list.extend(SdeUtils.get_market_group_list(type_id, zh=True))

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

    async def get_max_job_run(self, type_id: int):
        res, conf = await self._is_match_keyword(self.max_job_split_count_confs, type_id)
        if not res:
            return 100000000
        if conf["judge_type"] == 'count':
            return conf['max_count']
        elif conf["judge_type"] == 'time':
            _, time_eff = await self.get_efficiency(type_id)
            _, fake_time_eff = await self.get_conf_eff(type_id)
            h, m ,s = conf["max_time_date"].split(":")
            day = conf["max_time_day"]
            max_time = day * 24 * 3600 + int(h) * 3600 + int(m) * 60 + int(s)
            active_time = await BPManager.get_production_time(type_id)

            # TODO 系数计算

            return max_time // (active_time * time_eff * fake_time_eff)

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
        async with bp_asset_prepare_lock:
            if self._bp_prepare:
                return
            # 可访问的容器list
            container_id_list = [conf['asset_container_id'] for conf in self.load_asset_confs]

            # 获取个人角色  
            characters = await CharacterManager().get_user_all_characters(self.user_name)
            character_ids = [character.character_id for character in characters]

            # 检查主角色同公司是否有总监
            main_character_id = await UserManager().get_main_character_id(self.user_name)
            main_character = await CharacterManager().get_character_by_character_id(main_character_id)
            director = await CharacterManager().get_director_character_id_of_corporation(main_character.corporation_id)
            if director:
                director = await CharacterManager().get_character_by_character_id(director)
                character_ids.append(director.character_id)
            else:
                director = None

            bp_assets = {}
            # 获取运行中的job
            for character_id in character_ids:
                assets_json = await rds.r.get(f"bp_assets_cha_{character_id}")
                if not assets_json:
                    character = await CharacterManager().get_character_by_character_id(character_id)
                    assets = await eveesi.characters_character_id_blueprints(character.ac_token, character_id)
                    await rds.r.set(f"bp_assets_cha_{character_id}", json.dumps(assets), ex=15)
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

            # 获取公司运行中的job
            if director:
                assets_json = await rds.r.get(f"bp_assets_cor_{director.corporation_id}")
                if not assets_json:
                    assets = await eveesi.corporations_corporation_id_blueprints(director.ac_token, director.corporation_id)
                    await rds.r.set(f"bp_assets_cor_{director.corporation_id}", json.dumps(assets), ex=15)
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
        if not self._bp_prepare:
            await self.prepare_bp_asset()
        bp_type_id = await BPManager.get_bp_id_by_prod_typeid(type_id)
        
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

    async def get_efficiency(self, type_id: int):
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
        if res:
            # 获取建筑
            structure_name = conf['structure_name']
            if structure_name not in self._structure_info:
                structure_infos = await NAU.get_structure_nodes()
                for info in structure_infos:
                    if info['structure_name'] == structure_name:
                        self._structure_info[structure_name] = info
                        break
            structure_info = self._structure_info[structure_name]
            
            if structure_info['structure_type'] == 'Sotiyo':
                structure_eff['mater_eff'] *= MANU_STRUCTURE_MATER_EFF
                structure_eff['time_eff'] *= LARGE_STRUCTURE_MANU_TIME_EFF
            elif structure_info['structure_type'] == 'Azbel':
                structure_eff['mater_eff'] *= MANU_STRUCTURE_MATER_EFF
                structure_eff['time_eff'] *= MID_STRUCTURE_MANU_TIME_EFF
            elif structure_info['structure_type'] == 'Raitaru':
                structure_eff['mater_eff'] *= MANU_STRUCTURE_MATER_EFF
                structure_eff['time_eff'] *= SMALL_STRUCTURE_MANU_TIME_EFF
            elif structure_info['structure_type'] == 'Tatara':
                structure_eff['mater_eff'] *= 1
                structure_eff['time_eff'] *= MID_STRUCTURE_REAC_TIME_EFF
            elif structure_info['structure_type'] == 'Athanor':
                structure_eff['mater_eff'] *= 1
                structure_eff['time_eff'] *= SMALL_STRUCTURE_REAC_TIME_EFF

            active_type = await BPManager.get_activity_id_by_product_typeid(type_id)
            # 建筑插
            for rig_conf in self.structure_rig_confs:
                if rig_conf['structure_id'] == structure_info['item_id']:
                    bunus = NULL_MANU_SEC_BONUS if active_type == 1 else NULL_REAC_SEC_BONUS
                    structure_rig_eff['mater_eff'] *= (1 - RIG_MATER_EFF[rig_conf['mater_eff_level']] * bunus)
                    structure_rig_eff['time_eff'] *= (1 - RIG_TIME_EFF[rig_conf['time_eff_level']] * bunus)
            
        # 蓝图这里不负责

        # 技能
        
        if active_type == 1:
            skill_eff['time_eff'] *= MANU_SKILL_TIME_EFF
        elif active_type == 11:
            skill_eff['time_eff'] *= REAC_SKILL_TIME_EFF
        else:
            raise KahunaException(f"活动类型{active_type}不存在")

        return (
            structure_eff['mater_eff'] * structure_rig_eff['mater_eff'],
            structure_eff['time_eff'] * structure_rig_eff['time_eff'] * skill_eff['time_eff']
        )

    async def get_conf_eff(self, type_id: int):
        if f"get_conf_eff_{type_id}" in self.cache:
            return self.cache[f"get_conf_eff_{type_id}"]
        res, conf = await self._is_match_keyword(self.default_blueprint_confs, type_id)
        if res:
            self.cache[f"get_conf_eff_{type_id}"] = (1 - 0.01 * conf['mater_eff'], 1 - 0.01 * conf['time_eff'])
        else: 
            self.cache[f"get_conf_eff_{type_id}"] = (1, 1)
        return self.cache[f"get_conf_eff_{type_id}"]

    async def prepare_asset(self):
        async with asset_prepare_lock:
            if self._asset_prepare:
                return

            container_id_list = [conf['asset_container_id'] for conf in self.load_asset_confs]
            
            assets = await NAU.get_asset_in_container_list(container_id_list)
            for asset in assets:
                self._asset[asset['type_id']] = self._asset.get(asset['type_id'], 0) + asset['quantity']
            self._asset_prepare = True

    async def deal_asset_quantity(self, quantity: int, type_id: int, index_id: int):
        if not self._asset_prepare:
            await self.prepare_asset()

        if (type_id, index_id) in self._asset_allocate:
            return self._asset_allocate[(type_id, index_id)]
        
        if type_id in self._asset:
            allocate_quantity = min(quantity, self._asset[type_id])
            self._asset[type_id] -= allocate_quantity
            self._asset_allocate[(type_id, index_id)] = quantity - allocate_quantity
        else:
            self._asset_allocate[(type_id, index_id)] = quantity

        return self._asset_allocate[(type_id, index_id)]

    async def calculate_work_material_avaliable(self, work_list: list):
        if not self._asset_prepare:
            await self.prepare_asset()
        disable = False
        for work in work_list:
            if disable:
                work['avaliable'] = False
                continue
            material_need = await BPManager.get_bp_materials(work['type_id'])
            runs = work['runs']
            mater_eff = work['mater_eff']
            
            for material_type_id, material_quantity in material_need.items():
                if material_type_id not in self._material_allocate:
                    self._material_allocate[material_type_id] = self._asset.get(material_type_id, 0)

                if ceil(material_quantity * runs * (mater_eff if material_quantity != 1 else 1)) > self._material_allocate[material_type_id]:
                    work['avaliable'] = False
                    disable = True
                    break
            if disable:
                continue

            if material_type_id not in self._material_allocate:
                logger.error(f"material_type_id {material_type_id} not in _material_allocate")
            for material_type_id, material_quantity in material_need.items():
                self._material_allocate[material_type_id] -= ceil(material_quantity * runs * (mater_eff if material_quantity != 1 else 1))
            work['avaliable'] = True
        

    async def prepare_running_asset(self):
        async with running_asset_prepare_lock:
            if self._running_asset_prepare:
                return
            container_id_list = [conf['asset_container_id'] for conf in self.load_asset_confs]
            
            running_job_list = await self.get_running_job_list()
            for job in running_job_list:
                if job['output_location_id'] not in container_id_list:
                    continue
                
                self._running_asset[job['product_type_id']] = self._running_asset.get(job['product_type_id'], 0) + await BPM.get_bp_product_quantity_typeid(job['product_type_id']) * job['runs']
            self._running_asset_prepare = True

    async def deal_running_job_quantity(self, quantity: int, type_id: int, index_id: int):
        if not self._running_asset_prepare:
            await self.prepare_running_asset()

        if (type_id, index_id) in self._running_asset_allocate:
            return self._running_asset_allocate[(type_id, index_id)]
        
        if type_id in self._running_asset:
            allocate_quantity = min(quantity, self._running_asset[type_id])
            self._running_asset[type_id] -= allocate_quantity
            self._running_asset_allocate[(type_id, index_id)] = quantity - allocate_quantity
        else:
            self._running_asset_allocate[(type_id, index_id)] = quantity

        return self._running_asset_allocate[(type_id, index_id)]