
import asyncio
from datetime import datetime, timezone, timedelta
import json
import pathlib
import uuid

from tqdm.std import tqdm

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.connect_manager import get_neo4j_manager as neo4j_manager
from src_v2.core.database.connect_manager import get_postgres_manager as dbm
from src_v2.core.utils import SingletonMeta, tqdm_manager
from src_v2.core.utils import KahunaException, get_beijing_utctime, get_random_token

from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.user.user_manager import UserManager

from src_v2.core.database.kahuna_database_utils_v2 import (
    EveAssetPullMissionDBUtils,
    EveAssetViewDBUtils,
    EveIndustryAssetContainerPermissionDBUtils
)
from src_v2.core.database.model import EveAssetPullMission as M_EveAssetPullMission
from src_v2.core.database.model import EveAssetView as M_EveAssetView

from src_v2.core.database.neo4j_models import Asset
from src_v2.core.database.neo4j_utils import Neo4jAssetUtils as NAU
from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU

from src_v2.model.EVE.sde.utils import SdeUtils

from src_v2.model.EVE.eveesi import eveesi

# kahuna logger
from src_v2.core.log import logger

CREATE_STATION_SEMAPHORE = asyncio.Semaphore(1)

structure_sub_location_flags = [
    "OfficeFolder",
    "StructureFuel",
    "Cargo",
    "HiSlot4",
    "MedSlot3",
    "HiSlot0",
    "ServiceSlot0",
    "LoSlot1",
    "MedSlot2",
    "MedSlot1",
    "MedSlot4",
    "LoSlot0",
    "LoSlot3",
    "HiSlot2",
    "HiSlot1",
    "QuantumCoreRoom",
    "HiSlot3",
    "MedSlot0",
    "LoSlot2",
    "HiSlot5",
    "MedSlot5",
    "FighterTube4",
    "FighterBay",
    "ServiceSlot1",
    "ServiceSlot2",
    "HiSlot7",
    "FighterTube0",
    "HiSlot6",
    "FighterTube2",
    "FighterTube1",
    "LoSlot4",
    "FighterTube3",
    "CorpDeliveries",
    "RigSlot1",
    "RigSlot2",
    "RigSlot0",
    "SecondaryStorage"
]

class AssetManager(metaclass=SingletonMeta):
    async def change_asset_pull_mission_status(self, asset_owner_type: str, asset_owner_id: int, active: bool):
        mission_obj = await EveAssetPullMissionDBUtils.select_mission_by_owner_id_and_owner_type(asset_owner_id, asset_owner_type)
        if not mission_obj:
            raise KahunaException('任务不存在')
        mission_obj.active = active
        await EveAssetPullMissionDBUtils.save_obj(mission_obj)
        
    async def pull_asset_now(self, asset_owner_type: str, asset_owner_id: int):
        mission_obj = await EveAssetPullMissionDBUtils.select_mission_by_owner_id_and_owner_type(asset_owner_id, asset_owner_type)
        if not mission_obj:
            raise KahunaException('任务不存在')

        await rdm().r.hset(f'asset_pull_mission_status:{asset_owner_type}:{asset_owner_id}', 'step_name', "清理旧数据")
        await self.clean_asset_pull_mission_assets(mission_obj)
        await self.processing_asset_pull_mission(mission_obj)

        mission_obj.last_pull_time = get_beijing_utctime(datetime.now())
        await EveAssetPullMissionDBUtils.merge(mission_obj)

    async def get_user_asset_pull_mission_list(self, user_name: str) -> list[dict]:
        missions = []
        # 拉取个人创建的任务
        async for mission in await EveAssetPullMissionDBUtils.select_all_by_user_name(user_name):
            if mission.asset_owner_type == 'character':
                character = await CharacterManager().get_character_by_character_id(mission.asset_owner_id)
                subject_name = character.character_name
            elif mission.asset_owner_type == 'corp':
                corporation = await CharacterManager().get_corporation_data_by_corporation_id(mission.asset_owner_id)
                subject_name = corporation.name
            missions.append({
                'subject_type': mission.asset_owner_type,
                'subject_name': subject_name,
                'subject_id': mission.asset_owner_id,
                'is_active': mission.active,
                'last_pull_time': mission.last_pull_time.replace(tzinfo=timezone(timedelta(hours=+8), 'Shanghai'))
            })
        logger.info(f"拉取个人创建的任务: {missions}")
        # 拉取同公司的任务
        main_character_id = await UserManager().get_main_character_id(user_name)
        main_character = await CharacterManager().get_character_by_character_id(main_character_id)
        logger.info(f"主角色: {main_character.character_name} {main_character.corporation_id}")
        if main_character.corporation_id:
            corp_id = main_character.corporation_id
            async for mission in await EveAssetPullMissionDBUtils.select_all_by_owner_id_and_owner_type(corp_id, 'corp'):
                if mission.asset_owner_id not in [m['subject_id'] for m in missions]:
                    logger.info(f"拉取同公司的任务: {mission.asset_owner_id}")
                    corporation_info = await rdm().redis.get(f'eveesi:corporations_corporation:{mission.asset_owner_id}') 
                    if not corporation_info:
                        corporation_info = await eveesi.corporations_corporation_id(mission.asset_owner_id)
                        logger.info(f"esi res:{corporation_info}")
                        if not corporation_info:
                            logger.error(f"公司{mission.asset_owner_id}获取公开信息失败，跳过")
                            continue
                        await rdm().redis.set(f'eveesi:corporations_corporation:{mission.asset_owner_id}', json.dumps(corporation_info))
                        await rdm().redis.expire(f'eveesi:corporations_corporation:{mission.asset_owner_id}', 60*60*24)
                    else:
                        corporation_info = json.loads(corporation_info)
                    logger.info(f"公司{mission.asset_owner_id}公开信息: {corporation_info}")
                    missions.append({
                        'subject_type': mission.asset_owner_type,
                        'subject_name': corporation_info['name'],
                        'subject_id': mission.asset_owner_id,
                        'is_active': mission.active,
                        'last_pull_time': mission.last_pull_time.replace(tzinfo=timezone(timedelta(hours=+8), 'Shanghai'))
                    })
                    logger.info(f"拉取同公司的任务: {missions}")
        logger.info(f"拉取同公司的任务: {missions}")

        return missions

    async def get_all_asset_pull_mission_list(self) -> list[dict]:
        """获取所有资产拉取任务（管理员使用）"""
        missions = []
        # 拉取所有任务
        async for mission in await EveAssetPullMissionDBUtils.select_all():
            if mission.asset_owner_type == 'character':
                character = await CharacterManager().get_character_by_character_id(mission.asset_owner_id)
                subject_name = character.character_name
            elif mission.asset_owner_type == 'corp':
                corporation_info = await rdm().redis.get(f'eveesi:corporations_corporation:{mission.asset_owner_id}') 
                if not corporation_info:
                    corporation_info = await eveesi.corporations_corporation_id(mission.asset_owner_id)
                    if not corporation_info:
                        logger.error(f"公司{mission.asset_owner_id}获取公开信息失败，跳过")
                        continue
                    await rdm().redis.set(f'eveesi:corporations_corporation:{mission.asset_owner_id}', json.dumps(corporation_info))
                    await rdm().redis.expire(f'eveesi:corporations_corporation:{mission.asset_owner_id}', 60*60*24)
                else:
                    corporation_info = json.loads(corporation_info)
                subject_name = corporation_info['name']
            else:
                subject_name = f"Unknown ({mission.asset_owner_id})"
            
            missions.append({
                'subject_type': mission.asset_owner_type,
                'subject_name': subject_name,
                'subject_id': mission.asset_owner_id,
                'is_active': mission.active,
                'last_pull_time': mission.last_pull_time.replace(tzinfo=timezone(timedelta(hours=+8), 'Shanghai')) if mission.last_pull_time else None,
                'user_name': mission.user_name  # 包含创建者用户名
            })
        
        return missions

    async def create_asset_pull_mission(self, user_name: str, asset_owner_type: str, asset_owner_id: int, active: bool):
        if asset_owner_type == 'character':
            access_character_id = asset_owner_id
        elif asset_owner_type == 'corp':
            main_character_id = await UserManager().get_main_character_id(user_name)
            access_character_id = main_character_id
        mission_obj = await EveAssetPullMissionDBUtils.select_mission_by_owner_id_and_owner_type(asset_owner_id, asset_owner_type)
        if mission_obj:
            raise KahunaException('任务已存在')
        mission_obj = M_EveAssetPullMission(
            user_name = user_name,
            access_character_id = access_character_id,
            asset_owner_type = asset_owner_type,
            asset_owner_id = asset_owner_id,
            active = active,
            last_pull_time = datetime(1980, 1, 1, 0, 0, 0)
        )
        await EveAssetPullMissionDBUtils.save_obj(mission_obj)

    async def get_station_info(self, station_id: int):
        # 上级为空间站是NPC空间站，需要补充创建星系
        # 获取缓存
        station_info_cache = await rdm().redis.hgetall(f'eveesi:universe_stations_station:{station_id}')
        if not station_info_cache:
            station_info = await eveesi.universe_stations_station(station_id)
            station_info_cache = {
                "name": station_info["name"],
                "system_id": station_info["system_id"],
            }
            await rdm().redis.hset(f'eveesi:universe_stations_station:{station_id}', mapping=station_info_cache)
            await rdm().redis.expire(f'eveesi:universe_stations_station:{station_id}', 60*60*24)
        else:
            station_info = station_info_cache
            return station_info, False

        return station_info, True

    async def create_station_node(self, station_id: int):
        async with CREATE_STATION_SEMAPHORE:
            station_info, is_new = await self.get_station_info(station_id)
            if not is_new:
                return
            system_info = await SdeUtils.get_system_info_by_id(station_info["system_id"])
            station_node = {
                'station_id': station_id,
                'station_name': station_info["name"],
                'system_id': station_info["system_id"],
                'system_name': system_info['system_name'],
            }
            await NIU.merge_node(
                "Station",
                {
                    "station_id": station_id,
                },
                station_node
            )

            system_node = {
                'system_id': system_info['system_id'],
                'system_name': system_info['system_name'],
                'region_id': system_info['region_id'],
                'region_name': system_info['region_name'],
            }
            await NIU.merge_node(
                "SolarSystem",
                {
                    "solar_system_id": system_info["system_id"],
                },
                system_node
            )

            await NIU.link_node(
                "Station",
                {"station_id": station_id},
                {},
                "LOCATED_IN",
                {},
                {},
                "SolarSystem",
                {"solar_system_id": system_info['system_id']},
                {}
            )

    async def _generate_all_nodes(self, assets_list: list[dict], mission_obj: M_EveAssetPullMission):
        stucture_list = await NAU.get_structure_nodes()
        structure_item_id_list = [structure.get("item_id", None) for structure in stucture_list]
        status_key = f'asset_pull_mission_status:{mission_obj.asset_owner_type}:{mission_obj.asset_owner_id}'

        # 设置无限进度条
        await rdm().r.hset(status_key, 'step_name', "生成资产树节点")
        await rdm().r.hset(status_key, 'step_progress', 0.5)
        await rdm().r.hset(status_key, 'is_indeterminate', 1)

        # 过滤掉结构节点，收集需要创建的资产节点
        assets_to_create = [asset for asset in assets_list if asset["item_id"] not in structure_item_id_list]
        
        if not assets_to_create:
            return

        # 并发获取所有 type_name
        async def get_type_name(asset: dict):
            return await SdeUtils.get_name_by_id(asset['type_id'])
        
        type_name_tasks = [asyncio.create_task(get_type_name(asset)) for asset in assets_to_create]
        type_names = await asyncio.gather(*type_name_tasks)

        # 收集所有节点数据
        nodes_data = []
        station_ids_to_create = set()
        
        for asset, type_name in zip(assets_to_create, type_names):
            asset.update({
                'type_name': type_name,
                'owner_id': mission_obj.asset_owner_id
            })
            nodes_data.append({
                "index": {
                    "item_id": asset["item_id"],
                    "owner_id": mission_obj.asset_owner_id,
                },
                "properties": asset
            })
            
            # 收集需要创建的 station_id
            if asset["location_type"] == 'station':
                station_ids_to_create.add(asset["location_id"])

        # 批量插入所有资产节点
        if nodes_data:
            async with neo4j_manager().semaphore:
                await NIU.batch_merge_nodes("Asset", nodes_data)

        # 批量创建 station 节点（需要单独处理，因为 create_station_node 有特殊逻辑）
        if station_ids_to_create:
            station_creation_tasks = [
                asyncio.create_task(self.create_station_node(station_id))
                for station_id in station_ids_to_create
            ]
            await asyncio.gather(*station_creation_tasks)

    async def _generate_all_locate_relation(self, assets_list: list[dict], mission_obj: M_EveAssetPullMission):
        status_key = f'asset_pull_mission_status:{mission_obj.asset_owner_type}:{mission_obj.asset_owner_id}'
        structure_nodes = await NAU.get_structure_nodes()
        structure_item_id_list = [structure.get("structure_id", None) for structure in structure_nodes]
        
        # 设置无限进度条
        await rdm().r.hset(status_key, 'step_name', "生成资产树关系")
        await rdm().r.hset(status_key, 'step_progress', 0.5)
        await rdm().r.hset(status_key, 'is_indeterminate', 1)

        # 按关系类型分组收集关系数据
        station_relations = []
        solar_system_relations = []
        solar_system_ids_to_fetch = set()  # 需要获取信息的 system_id 集合
        structure_relations = []
        asset_relations = []

        # 第一遍遍历：收集关系数据和需要获取的 system_id
        for asset in assets_list:
            source_index = {
                "item_id": asset["item_id"],
                "owner_id": mission_obj.asset_owner_id,
            }
            source_properties = {
                "item_id": asset["item_id"],
                "type_id": asset["type_id"],
                "owner_id": mission_obj.asset_owner_id,
            }

            if asset["location_type"] == 'station':
                station_relations.append({
                    "source_index": source_index,
                    "source_properties": source_properties,
                    "target_index": {"station_id": asset["location_id"]},
                    "target_properties": {},
                    "relation_index": {},
                    "relation_properties": {}
                })
            elif asset["location_type"] == 'solar_system':
                if asset["item_id"] in structure_item_id_list:
                    continue
                
                system_id = asset["location_id"]
                solar_system_ids_to_fetch.add(system_id)
                
                solar_system_relations.append({
                    "source_index": source_index,
                    "source_properties": source_properties,
                    "target_index": {"solar_system_id": system_id},
                    "target_properties": {"solar_system_id": system_id},
                    "relation_index": {},
                    "relation_properties": {}
                })
            else:
                if asset["location_id"] in structure_item_id_list:
                    structure_relations.append({
                        "source_index": source_index,
                        "source_properties": source_properties,
                        "target_index": {"structure_id": asset["location_id"]},
                        "target_properties": {"structure_id": asset["location_id"]},
                        "relation_index": {},
                        "relation_properties": {}
                    })
                else:
                    asset_relations.append({
                        "source_index": source_index,
                        "source_properties": source_properties,
                        "target_index": {
                            "item_id": asset["location_id"],
                            "owner_id": mission_obj.asset_owner_id,
                        },
                        "target_properties": {
                            "item_id": asset["location_id"],
                            "owner_id": mission_obj.asset_owner_id,
                        },
                        "relation_index": {},
                        "relation_properties": {}
                    })

        # 并发获取所有 SolarSystem 节点信息
        solar_system_nodes_data = []
        if solar_system_ids_to_fetch:
            async def get_system_node_data(system_id: int):
                system_info = await SdeUtils.get_system_info_by_id(system_id)
                return {
                    "index": {"solar_system_id": system_info["system_id"]},
                    "properties": {
                        'system_id': system_info['system_id'],
                        'system_name': system_info['system_name'],
                        'region_id': system_info['region_id'],
                        'region_name': system_info['region_name'],
                    }
                }
            
            system_node_tasks = [
                asyncio.create_task(get_system_node_data(system_id))
                for system_id in solar_system_ids_to_fetch
            ]
            solar_system_nodes_data = await asyncio.gather(*system_node_tasks)

        # 批量创建 SolarSystem 节点
        if solar_system_nodes_data:
            async with CREATE_STATION_SEMAPHORE:
                async with neo4j_manager().semaphore:
                    await NIU.batch_merge_nodes("SolarSystem", solar_system_nodes_data)

        # 批量插入各组关系
        async with neo4j_manager().semaphore:
            if station_relations:
                await NIU.batch_link_nodes("Asset", "Station", "LOCATED_IN", station_relations)
            
            if solar_system_relations:
                await NIU.batch_link_nodes("Asset", "SolarSystem", "LOCATED_IN", solar_system_relations)
            
            if structure_relations:
                await NIU.batch_link_nodes("Asset", "Structure", "LOCATED_IN", structure_relations)
            
            if asset_relations:
                await NIU.batch_link_nodes("Asset", "Asset", "LOCATED_IN", asset_relations)

    async def _generate_forbidden_structure_node(self, mission_obj: M_EveAssetPullMission):
        logger.info("开始生成无权限建筑节点")
        access_character = await CharacterManager().get_character_by_character_id(mission_obj.access_character_id)
        # 补全玩家建筑信息
        forbidden_structure_node_list = await NAU.get_forbidden_structure_node_list(mission_obj.asset_owner_id)
        logger.info(f"无权限建筑节点数量: {len(forbidden_structure_node_list)}")
        status_key = f'asset_pull_mission_status:{mission_obj.asset_owner_type}:{mission_obj.asset_owner_id}'
        await rdm().r.hset(status_key, 'step_name', "生成无权限建筑节点")
        await rdm().r.hset(status_key, 'step_progress', 0.5)
        await rdm().r.hset(status_key, 'is_indeterminate', 1)

        await tqdm_manager.add_mission("_generate_forbidden_structure_node", len(forbidden_structure_node_list))
        for forbidden_structure_node in forbidden_structure_node_list:
            # 建筑信息
            logger.info(f"开始生成无权限建筑节点: {forbidden_structure_node["item_id"]}")
            structure_info_cache = await rdm().redis.hgetall(f'eveesi:universe_structures_structure:{forbidden_structure_node["item_id"]}')
            if not structure_info_cache:
                structure_info = await eveesi.universe_structures_structure(access_character.ac_token, forbidden_structure_node["item_id"])
                if structure_info:
                    logger.info(f"建筑{forbidden_structure_node["item_id"]}获取到建筑信息")
                    structure_info_cache = {
                        "name": structure_info["name"],
                        "owner_id": structure_info["owner_id"],
                        "solar_system_id": structure_info["solar_system_id"],
                        "type_id": structure_info["type_id"]
                    }
                else:
                    logger.info(f"建筑{forbidden_structure_node["item_id"]}无权限，创建无权限建筑")
                    structure_info_cache = {
                        'name': f'Forbidden {await SdeUtils.get_name_by_id(int(forbidden_structure_node['type_id'])) if "type_id" in forbidden_structure_node else "unknown"}',
                        'owner_id': 'unknown',
                        'solar_system_id': 'unknown',
                        'type_id': 'unknown',
                    }
                await rdm().redis.hset(f'eveesi:universe_structures_structure:{forbidden_structure_node["item_id"]}', mapping=structure_info_cache)
                await rdm().redis.expire(f'eveesi:universe_structures_structure:{forbidden_structure_node["item_id"]}', 60*60*24)
            structure_info = structure_info_cache
            
            # 星系信息
            if structure_info['solar_system_id'] != 'unknown':
                system_info = await SdeUtils.get_system_info_by_id(int(structure_info["solar_system_id"]))
                if not system_info:
                    raise KahunaException(f"建筑{forbidden_structure_node["item_id"]}无星系信息")
                solar_system_node = {
                    'system_id': system_info['system_id'],
                    'system_name': system_info['system_name'],
                    'region_id': system_info['region_id'],
                    'region_name': system_info['region_name'],
                }
            else:
                solar_system_node = {
                    'system_id': 'unknown',
                    'system_name': 'unknown',
                    'region_id': 'unknown',
                    'region_name': 'unknown',
                }

            structure_node = {
                'structure_id': forbidden_structure_node["item_id"],
                'structure_name': structure_info["name"],
                'structure_type': await SdeUtils.get_name_by_id(int(structure_info['type_id'])) if structure_info['type_id'] != 'unknown' else 'unknown',
                'structure_type_id': structure_info['type_id'] if structure_info['type_id'] != 'unknown' else 'unknown',
                'system_id': solar_system_node['system_id'],
                'system_name': solar_system_node['system_name'],
                'region_id': solar_system_node['region_id'],
                'region_name': solar_system_node['region_name'],
            }
            forbidden_structure_node.update({
                "type_id": structure_node['structure_type_id'],
                "type_name": structure_node['structure_type'],
                "owner_id": mission_obj.asset_owner_id,
            })
            async with CREATE_STATION_SEMAPHORE:
                await NAU.merge_asset_to_structure_to_solar_system(forbidden_structure_node, structure_node, solar_system_node)
            await tqdm_manager.update_mission("_generate_forbidden_structure_node", 1)
        await tqdm_manager.complete_mission("_generate_forbidden_structure_node")

    async def _update_structure_node(self, mission_obj: M_EveAssetPullMission):
        access_character = await CharacterManager().get_character_by_character_id(mission_obj.access_character_id)
        structure_asset_nodes = await NAU.get_structure_asset_nodes(mission_obj.asset_owner_id)
        status_key = f'asset_pull_mission_status:{mission_obj.asset_owner_type}:{mission_obj.asset_owner_id}'
        await rdm().r.hset(status_key, 'step_name', "更新建筑节点信息")
        await rdm().r.hset(status_key, 'step_progress', 0.0)
        await rdm().r.hset(status_key, 'is_indeterminate', 0)

        await tqdm_manager.add_mission("_update_structure_node", len(structure_asset_nodes))
        for node in structure_asset_nodes:
            structure_info_cache = await rdm().redis.hgetall(f'eveesi:universe_structures_structure:{node["item_id"]}')
            if not structure_info_cache:
                structure_info = await eveesi.universe_structures_structure(access_character.ac_token, node["item_id"])
                if structure_info:
                    logger.info(f"建筑{node["item_id"]} 获取到建筑信息")
                    system_info = await SdeUtils.get_system_info_by_id(structure_info["solar_system_id"])
                    structure_info_cache = {
                        "name": structure_info["name"],
                        "owner_id": structure_info["owner_id"],
                        "solar_system_id": structure_info["solar_system_id"],
                        "type_id": structure_info["type_id"],
                        "system_id": system_info['system_id'],
                        "system_name": system_info['system_name'],
                        "region_id": system_info['region_id'],
                        "region_name": system_info['region_name'],
                    }
                else:
                    logger.info(f"建筑{node["item_id"]}无权限，创建无权限建筑")
                    structure_info_cache = {
                        'name': f'Forbidden {await SdeUtils.get_name_by_id(node['type_id'])}',
                        'owner_id': 'unknown',
                        'solar_system_id': 'unknown',
                        'type_id': 'unknown',
                        'system_id': 'unknown',
                        'system_name': 'unknown',
                        'region_id': 'unknown',
                        'region_name': 'unknown',
                    }
                await rdm().redis.hset(f'eveesi:universe_structures_structure:{node["item_id"]}', mapping=structure_info_cache)
                await rdm().redis.expire(f'eveesi:universe_structures_structure:{node["item_id"]}', 60*60*24)
            structure_info = structure_info_cache
            if "system_id" not in structure_info:
                logger.error(f"建筑{node["item_id"]}无星系信息，跳过更新")
                logger.error(structure_info)
                continue
            structure_node = {
                'structure_id': node["item_id"],
                'structure_name': structure_info["name"],
                'structure_type': await SdeUtils.get_name_by_id(structure_info['type_id']) if structure_info['type_id'] != 'unknown' else 'unknown',
                'structure_type_id': structure_info['type_id'] if structure_info['type_id'] != 'unknown' else 'unknown',
                'system_id': structure_info['system_id'],
                'system_name': structure_info['system_name'],
                'region_id': structure_info['region_id'],
                'region_name': structure_info['region_name'],
            }

            await NAU.change_asset_to_structure(node, structure_node)
            now_progress = await tqdm_manager.update_mission("_update_structure_node", 1)
            await rdm().r.hset(status_key, 'step_progress', now_progress / len(structure_asset_nodes))
        await tqdm_manager.complete_mission("_update_structure_node")

    async def _update_forbidden_structure_node(self, mission_obj: M_EveAssetPullMission):
        """处理该owner的asset连接到已经存在的forbidden_structure_node
        
        找到该owner的asset连接的所有forbidden_structure_node，尝试获取建筑信息。
        如果能够获取到，更新该node的信息，删除该node连接到unknown system的边，
        检查建筑所在星系节点是否存在，不存在则创建，创建连接到正确星系的边
        """
        logger.info("开始更新无权限建筑节点")
        access_character = await CharacterManager().get_character_by_character_id(mission_obj.access_character_id)
        forbidden_structure_nodes = await NAU.get_forbidden_structure_nodes_by_owner(mission_obj.asset_owner_id)
        logger.info(f"找到 {len(forbidden_structure_nodes)} 个无权限建筑节点需要更新")
        
        status_key = f'asset_pull_mission_status:{mission_obj.asset_owner_type}:{mission_obj.asset_owner_id}'
        await rdm().r.hset(status_key, 'step_name', "更新无权限建筑节点")
        await rdm().r.hset(status_key, 'step_progress', 0.0)
        await rdm().r.hset(status_key, 'is_indeterminate', 0)

        await tqdm_manager.add_mission("_update_forbidden_structure_node", len(forbidden_structure_nodes))
        for structure_node_data in forbidden_structure_nodes:
            structure_id = structure_node_data.get("structure_id")
            if not structure_id:
                logger.warning(f"跳过无structure_id的节点: {structure_node_data}")
                await tqdm_manager.update_mission("_update_forbidden_structure_node", 1)
                continue
            
            logger.info(f"开始更新无权限建筑节点: {structure_id}")
            # 尝试获取建筑信息
            structure_info_cache = await rdm().redis.hgetall(f'eveesi:universe_structures_structure:{structure_id}')
            if not structure_info_cache:
                structure_info = await eveesi.universe_structures_structure(access_character.ac_token, structure_id)
                if structure_info:
                    logger.info(f"建筑{structure_id}获取到建筑信息")
                    system_info = await SdeUtils.get_system_info_by_id(structure_info["solar_system_id"])
                    structure_info_cache = {
                        "name": structure_info["name"],
                        "owner_id": structure_info["owner_id"],
                        "solar_system_id": structure_info["solar_system_id"],
                        "type_id": structure_info["type_id"],
                        "system_id": system_info['system_id'],
                        "system_name": system_info['system_name'],
                        "region_id": system_info['region_id'],
                        "region_name": system_info['region_name'],
                    }
                else:
                    logger.info(f"建筑{structure_id}无权限，跳过更新")
                    await tqdm_manager.update_mission("_update_forbidden_structure_node", 1)
                    continue
                await rdm().redis.hset(f'eveesi:universe_structures_structure:{structure_id}', mapping=structure_info_cache)
                await rdm().redis.expire(f'eveesi:universe_structures_structure:{structure_id}', 60*60*24)
            else:
                # 检查缓存中的信息是否有效（不是unknown）
                if structure_info_cache.get('solar_system_id') == 'unknown' or structure_info_cache.get('solar_system_id') == b'unknown':
                    logger.info(f"建筑{structure_id}缓存信息为unknown，尝试重新获取")
                    structure_info = await eveesi.universe_structures_structure(access_character.ac_token, structure_id)
                    if structure_info:
                        logger.info(f"建筑{structure_id}重新获取到建筑信息")
                        system_info = await SdeUtils.get_system_info_by_id(structure_info["solar_system_id"])
                        structure_info_cache = {
                            "name": structure_info["name"],
                            "owner_id": structure_info["owner_id"],
                            "solar_system_id": structure_info["solar_system_id"],
                            "type_id": structure_info["type_id"],
                            "system_id": system_info['system_id'],
                            "system_name": system_info['system_name'],
                            "region_id": system_info['region_id'],
                            "region_name": system_info['region_name'],
                        }
                        await rdm().redis.hset(f'eveesi:universe_structures_structure:{structure_id}', mapping=structure_info_cache)
                        await rdm().redis.expire(f'eveesi:universe_structures_structure:{structure_id}', 60*60*24)
                    else:
                        logger.info(f"建筑{structure_id}重新获取仍无权限，跳过更新")
                        await tqdm_manager.update_mission("_update_forbidden_structure_node", 1)
                        continue
                else:
                    # 确保缓存中有system_id等信息
                    if 'system_id' not in structure_info_cache or structure_info_cache.get('system_id') == 'unknown':
                        solar_system_id = structure_info_cache.get('solar_system_id')
                        if solar_system_id and solar_system_id != 'unknown':
                            if isinstance(solar_system_id, bytes):
                                solar_system_id = int(solar_system_id.decode())
                            else:
                                solar_system_id = int(solar_system_id)
                            system_info = await SdeUtils.get_system_info_by_id(solar_system_id)
                            structure_info_cache['system_id'] = system_info['system_id']
                            structure_info_cache['system_name'] = system_info['system_name']
                            structure_info_cache['region_id'] = system_info['region_id']
                            structure_info_cache['region_name'] = system_info['region_name']
                            await rdm().redis.hset(f'eveesi:universe_structures_structure:{structure_id}', mapping=structure_info_cache)
            
            structure_info = structure_info_cache
            # 处理bytes类型的值，将redis返回的bytes转换为字符串或int
            def decode_value(value):
                if isinstance(value, bytes):
                    return value.decode('utf-8')
                return value
            
            # 转换所有可能为bytes的值
            for key in structure_info:
                structure_info[key] = decode_value(structure_info[key])
            
            # 获取system_id（优先使用system_id，如果没有则使用solar_system_id）
            system_id_value = structure_info.get('system_id') or structure_info.get('solar_system_id')
            
            # 检查是否能够获取到有效的建筑信息
            if system_id_value == 'unknown' or not system_id_value:
                logger.info(f"建筑{structure_id}仍为unknown，跳过更新")
                await tqdm_manager.update_mission("_update_forbidden_structure_node", 1)
                continue
            
            # 构建structure_node和solar_system_node
            structure_name = decode_value(structure_info.get("name", ""))
            type_id_value = structure_info.get('type_id')
            structure_type = 'unknown'
            if type_id_value and type_id_value != 'unknown':
                try:
                    structure_type = await SdeUtils.get_name_by_id(int(type_id_value))
                except (ValueError, TypeError):
                    logger.warning(f"建筑{structure_id}的type_id无效: {type_id_value}")
            
            structure_node = {
                'structure_id': structure_id,
                'structure_name': structure_name,
                'structure_type': structure_type,
            }
            
            # 获取system_id并查询星系信息
            try:
                system_id = int(system_id_value)
            except (ValueError, TypeError):
                logger.warning(f"建筑{structure_id}的system_id无效: {system_id_value}")
                await tqdm_manager.update_mission("_update_forbidden_structure_node", 1)
                continue
            
            system_info = await SdeUtils.get_system_info_by_id(system_id)
            if not system_info:
                logger.warning(f"建筑{structure_id}无法获取星系信息: {system_id}")
                await tqdm_manager.update_mission("_update_forbidden_structure_node", 1)
                continue
            solar_system_node = {
                'system_id': system_info['system_id'],
                'system_name': system_info['system_name'],
                'region_id': system_info['region_id'],
                'region_name': system_info['region_name'],
            }
            
            # 更新节点
            async with CREATE_STATION_SEMAPHORE:
                success = await NAU.update_forbidden_structure_node(structure_id, structure_node, solar_system_node)
                if success:
                    logger.info(f"成功更新建筑节点{structure_id}")
                else:
                    logger.warning(f"更新建筑节点{structure_id}失败")
            
            now_progress = await tqdm_manager.update_mission("_update_forbidden_structure_node", 1)
            await rdm().r.hset(status_key, 'step_progress', now_progress / len(forbidden_structure_nodes))
        await tqdm_manager.complete_mission("_update_forbidden_structure_node")

    async def processing_asset_pull_mission(self, mission_obj: M_EveAssetPullMission):
        status_key = f'asset_pull_mission_status:{mission_obj.asset_owner_type}:{mission_obj.asset_owner_id}'

        if mission_obj.asset_owner_type == 'character':
            pull_function = eveesi.characters_character_assets

        elif mission_obj.asset_owner_type == 'corp':
            pull_function = eveesi.corporations_corporation_assets

        access_character = await CharacterManager().get_character_by_character_id(mission_obj.access_character_id)

        await rdm().r.hset(status_key, 'step_name', "通过api拉取资产")
        assets = await pull_function(
            access_character.ac_token,
            mission_obj.asset_owner_id,
            status_key=status_key
        )
        assets_list = []
        for assets_list_batch in assets:
            assets_list.extend(assets_list_batch)

        # 生成所有节点
        await self._generate_all_nodes(assets_list, mission_obj)
        await self._generate_all_locate_relation(assets_list, mission_obj)
        await self._update_forbidden_structure_node(mission_obj)
        await self._update_solar_system_connected_asset_nodes(mission_obj)
        await self._generate_forbidden_structure_node(mission_obj)
        await self._update_structure_node(mission_obj)
        
    async def _update_solar_system_connected_asset_nodes(self, mission_obj: M_EveAssetPullMission):
        """找到直接连接到星系的Asset节点，使用item_id获取建筑信息，如果获取成功，则更新为Structure节点"""
        logger.info("开始更新直接连接星系的Asset节点为Structure节点")
        access_character = await CharacterManager().get_character_by_character_id(mission_obj.access_character_id)
        asset_nodes = await NAU.get_solar_system_connected_asset_nodes(mission_obj.asset_owner_id)
        logger.info(f"找到 {len(asset_nodes)} 个直接连接星系的Asset节点需要检查")
        
        status_key = f'asset_pull_mission_status:{mission_obj.asset_owner_type}:{mission_obj.asset_owner_id}'
        await rdm().r.hset(status_key, 'step_name', "更新直接连接星系的Asset节点")
        await rdm().r.hset(status_key, 'step_progress', 0.0)
        await rdm().r.hset(status_key, 'is_indeterminate', 0)

        await tqdm_manager.add_mission("_update_solar_system_connected_asset_nodes", len(asset_nodes))
        for node in asset_nodes:
            item_id = node.get("item_id")
            if not item_id:
                logger.warning(f"跳过无item_id的节点: {node}")
                await tqdm_manager.update_mission("_update_solar_system_connected_asset_nodes", 1)
                continue
            
            logger.info(f"开始检查Asset节点: {item_id}")
            # 尝试获取建筑信息
            structure_info_cache = await rdm().redis.hgetall(f'eveesi:universe_structures_structure:{item_id}')
            if not structure_info_cache:
                structure_info = await eveesi.universe_structures_structure(access_character.ac_token, item_id)
                if structure_info:
                    logger.info(f"建筑{item_id}获取到建筑信息")
                    system_info = await SdeUtils.get_system_info_by_id(structure_info["solar_system_id"])
                    structure_info_cache = {
                        "name": structure_info["name"],
                        "owner_id": structure_info["owner_id"],
                        "solar_system_id": structure_info["solar_system_id"],
                        "type_id": structure_info["type_id"],
                        "system_id": system_info['system_id'],
                        "system_name": system_info['system_name'],
                        "region_id": system_info['region_id'],
                        "region_name": system_info['region_name'],
                    }
                    await rdm().redis.hset(f'eveesi:universe_structures_structure:{item_id}', mapping=structure_info_cache)
                    await rdm().redis.expire(f'eveesi:universe_structures_structure:{item_id}', 60*60*24)
                else:
                    logger.info(f"Asset节点{item_id}无法获取建筑信息，跳过")
                    await tqdm_manager.update_mission("_update_solar_system_connected_asset_nodes", 1)
                    continue
            else:
                # 处理bytes类型的值，将redis返回的bytes转换为字符串或int
                def decode_value(value):
                    if isinstance(value, bytes):
                        return value.decode('utf-8')
                    return value
                
                # 转换所有可能为bytes的值
                structure_info = {}
                for key in structure_info_cache:
                    structure_info[key] = decode_value(structure_info_cache[key])
                
                # 检查缓存中的信息是否有效（不是unknown）
                if structure_info.get('solar_system_id') == 'unknown' or structure_info.get('system_id') == 'unknown':
                    logger.info(f"Asset节点{item_id}缓存信息为unknown，尝试重新获取")
                    structure_info_new = await eveesi.universe_structures_structure(access_character.ac_token, item_id)
                    if structure_info_new:
                        logger.info(f"Asset节点{item_id}重新获取到建筑信息")
                        system_info = await SdeUtils.get_system_info_by_id(structure_info_new["solar_system_id"])
                        structure_info_cache = {
                            "name": structure_info_new["name"],
                            "owner_id": structure_info_new["owner_id"],
                            "solar_system_id": structure_info_new["solar_system_id"],
                            "type_id": structure_info_new["type_id"],
                            "system_id": system_info['system_id'],
                            "system_name": system_info['system_name'],
                            "region_id": system_info['region_id'],
                            "region_name": system_info['region_name'],
                        }
                        await rdm().redis.hset(f'eveesi:universe_structures_structure:{item_id}', mapping=structure_info_cache)
                        await rdm().redis.expire(f'eveesi:universe_structures_structure:{item_id}', 60*60*24)
                        structure_info = structure_info_cache
                    else:
                        logger.info(f"Asset节点{item_id}重新获取仍无法获取建筑信息，跳过")
                        await tqdm_manager.update_mission("_update_solar_system_connected_asset_nodes", 1)
                        continue
                else:
                    # 确保缓存中有system_id等信息
                    if 'system_id' not in structure_info or structure_info.get('system_id') == 'unknown':
                        solar_system_id = structure_info.get('solar_system_id')
                        if solar_system_id and solar_system_id != 'unknown':
                            try:
                                if isinstance(solar_system_id, bytes):
                                    solar_system_id = int(solar_system_id.decode())
                                else:
                                    solar_system_id = int(solar_system_id)
                                system_info = await SdeUtils.get_system_info_by_id(solar_system_id)
                                structure_info['system_id'] = system_info['system_id']
                                structure_info['system_name'] = system_info['system_name']
                                structure_info['region_id'] = system_info['region_id']
                                structure_info['region_name'] = system_info['region_name']
                                await rdm().redis.hset(f'eveesi:universe_structures_structure:{item_id}', mapping=structure_info)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Asset节点{item_id}的solar_system_id无效: {solar_system_id}, 错误: {e}")
                                await tqdm_manager.update_mission("_update_solar_system_connected_asset_nodes", 1)
                                continue
            
            # 处理bytes类型的值（如果structure_info是从缓存获取的，可能还需要再次处理）
            def decode_value(value):
                if isinstance(value, bytes):
                    return value.decode('utf-8')
                return value
            
            # 转换所有可能为bytes的值
            for key in structure_info:
                structure_info[key] = decode_value(structure_info[key])
            
            # 获取system_id（优先使用system_id，如果没有则使用solar_system_id）
            system_id_value = structure_info.get('system_id') or structure_info.get('solar_system_id')
            
            # 检查是否能够获取到有效的建筑信息
            if system_id_value == 'unknown' or not system_id_value:
                logger.info(f"Asset节点{item_id}仍为unknown，跳过更新")
                await tqdm_manager.update_mission("_update_solar_system_connected_asset_nodes", 1)
                continue
            
            # 构建structure_node
            structure_name = decode_value(structure_info.get("name", ""))
            type_id_value = structure_info.get('type_id')
            structure_type = 'unknown'
            if type_id_value and type_id_value != 'unknown':
                try:
                    structure_type = await SdeUtils.get_name_by_id(int(type_id_value))
                except (ValueError, TypeError):
                    logger.warning(f"Asset节点{item_id}的type_id无效: {type_id_value}")
            
            # 获取system_id并查询星系信息
            try:
                system_id = int(system_id_value)
            except (ValueError, TypeError):
                logger.warning(f"Asset节点{item_id}的system_id无效: {system_id_value}")
                await tqdm_manager.update_mission("_update_solar_system_connected_asset_nodes", 1)
                continue
            
            system_info = await SdeUtils.get_system_info_by_id(system_id)
            if not system_info:
                logger.warning(f"Asset节点{item_id}无法获取星系信息: {system_id}")
                await tqdm_manager.update_mission("_update_solar_system_connected_asset_nodes", 1)
                continue
            
            structure_node = {
                'structure_id': item_id,
                'structure_name': structure_name,
                'structure_type': structure_type,
                'system_id': system_info['system_id'],
                'system_name': system_info['system_name'],
                'region_id': system_info['region_id'],
                'region_name': system_info['region_name'],
            }
            
            # 更新节点
            async with CREATE_STATION_SEMAPHORE:
                success = await NAU.change_asset_to_structure(node, structure_node)
                if success:
                    logger.info(f"成功将Asset节点{item_id}更新为Structure节点")
                else:
                    logger.warning(f"更新Asset节点{item_id}为Structure节点失败")
            
            now_progress = await tqdm_manager.update_mission("_update_solar_system_connected_asset_nodes", 1)
            await rdm().r.hset(status_key, 'step_progress', now_progress / len(asset_nodes))
        await tqdm_manager.complete_mission("_update_solar_system_connected_asset_nodes")
        
    async def clean_asset_pull_mission_assets(self, mission_obj: M_EveAssetPullMission):
        owner_id = mission_obj.asset_owner_id
        await NAU.delete_assets_by_owner_id(owner_id)

    async def search_container_by_item_name(self, user_name, item_name: str):
        type_id = await SdeUtils.get_id_by_name(item_name)
        # 获得用户能访问的所有资产所有者id
        owner_id_list = []
        async for mission in await EveAssetPullMissionDBUtils.select_all_by_user_name(user_name):
            owner_id_list.append(mission.asset_owner_id)

        # TODO 如果公司开放且不包含，则新增, 先无条件开放
        main_character_id = await UserManager().get_main_character_id(user_name)
        main_character = await CharacterManager().get_character_by_character_id(main_character_id)
        if main_character.corporation_id:
            corp_id = main_character.corporation_id
            owner_id_list.append(corp_id)

        # 图搜索符合的节点，返回路径
        paths = await NAU.search_container_by_item_name(owner_id_list, type_id)

        if not paths:
            raise KahunaException("找不到符合条件的容器")

        output_list = []
        for path in paths:
            output = {}
            for index, node in enumerate(path):
                if index == 0:
                    output['asset'] = node
                if index == 1:
                    output['container'] = node
                if "Structure" in node['labels'] or 'Station' in node['labels']:
                    output['structure'] = node
                if "SolarSystem" in node['labels']:
                    output['system'] = node
            output_list.append(output)
        return output_list


    async def get_asset_view_of_user(self, user_name: str):
        asset_view_list = []
        async for asset_view in await EveAssetViewDBUtils.select_by_user_name(user_name):
            # 优先使用asset_container_id_list，如果没有则使用asset_container_id（向后兼容）
            container_list = asset_view.asset_container_id_list if hasattr(asset_view, 'asset_container_id_list') and asset_view.asset_container_id_list else []
            if not container_list and asset_view.asset_container_id:
                # 向后兼容：将旧的单个container_id转换为新格式
                container_list = [{"container_id": asset_view.asset_container_id, "owner_id": asset_view.asset_owner_id}]
            
            asset_view_list.append({
                'sid': asset_view.sid,
                'asset_owner_id': asset_view.asset_owner_id,
                'asset_container_id': asset_view.asset_container_id,
                'asset_container_id_list': container_list,
                'structure_id': asset_view.structure_id,
                'system_id': asset_view.system_id,
                'tag': asset_view.tag,
                'public': asset_view.public if hasattr(asset_view, 'public') else False,
                'view_type': asset_view.view_type,
                'config': asset_view.config,
                'filter': asset_view.filter,
            })
        return asset_view_list

    async def get_public_asset_view_data(self, sid: str):
        """获取公开的资产视图数据
        
        :param sid: 资产视图SID
        :raises KahunaException: 如果资产视图不存在或未公开
        """
        asset_view = await EveAssetViewDBUtils.select_by_sid(sid)
        if not asset_view:
            raise KahunaException('资产视图不存在')
        
        if not asset_view.public:
            raise KahunaException('该资产视图未公开')
        
        return await self.get_asset_view_data(sid), asset_view.tag

    async def _check_filter(self, asset: dict, asset_view: M_EveAssetView):
        view_filter = asset_view.filter
        for f in view_filter:
            if f['type'] == 'location_flag' and asset.get('location_flag', None) != f['value']:
                return False
            if f['type'] == 'type_id' and asset.get('type_id', None) != f['value']:
                return False
            if f['type'] == 'group':
                group = await SdeUtils.get_groupname_by_id(asset.get('type_id', None))
                group_zh = await SdeUtils.get_groupname_by_id(asset.get('type_id', None), True)
                if group != f['value'] and group_zh != f['value']:
                    return False
            if f['type'] == 'meta':
                meta = await SdeUtils.get_metaname_by_typeid(asset.get('type_id', None))
                meta_zh = await SdeUtils.get_metaname_by_typeid(asset.get('type_id', None), True)
                if meta != f['value'] and meta_zh != f['value']:
                    return False
            if f['type'] == 'marketGroup':
                market_group_list = await SdeUtils.get_market_group_list(asset.get('type_id', None))
                market_group_list_zh = await SdeUtils.get_market_group_list(asset.get('type_id', None), True)
                if f['value'] not in market_group_list and f['value'] not in market_group_list_zh:
                    return False
            if f['type'] == 'category':
                category = await SdeUtils.get_category_by_id(asset.get('type_id', None))
                category_zh = await SdeUtils.get_category_by_id(asset.get('type_id', None), True)
                if category != f['value'] and category_zh != f['value']:
                    return False
        return True

    async def get_asset_view_data(self, sid: str):
        asset_view = await EveAssetViewDBUtils.select_by_sid(sid)
        if not asset_view:
            raise KahunaException('资产视图不存在')

        # 优先使用asset_container_id_list，如果没有则使用asset_container_id（向后兼容）
        container_list = asset_view.asset_container_id_list if hasattr(asset_view, 'asset_container_id_list') and asset_view.asset_container_id_list else []
        if not container_list and asset_view.asset_container_id:
            # 向后兼容：将旧的单个container_id转换为新格式
            container_list = [{"container_id": asset_view.asset_container_id, "owner_id": asset_view.asset_owner_id}]
        
        if not container_list:
            raise KahunaException('资产视图没有关联的容器')
        
        # 构建容器-所有者对列表
        container_owner_pairs = [
            [item["container_id"], item["owner_id"]] 
            for item in container_list
        ]
        
        asset_data = await NAU.get_asset_in_container_owner_list(container_owner_pairs)

        asset_dict = {}
        for asset in asset_data:
            type_id = asset['type_id']
            if not await self._check_filter(asset, asset_view):
                continue
            if type_id not in asset_dict:
                asset_dict[type_id] = {
                    'type_id': type_id,
                    'type_name': await SdeUtils.get_name_by_id(type_id),
                    'type_name_zh': await SdeUtils.get_name_by_id(type_id, 'zh'),
                    'quantity': 0
                }
            asset_dict[type_id]['quantity'] += asset['quantity']

        return asset_dict

    async def _get_class_type(self, type_id: int):
        category = await SdeUtils.get_category_by_id(type_id)
        group = await SdeUtils.get_groupname_by_id(type_id)
        if group == "Mineral":
            return "矿物"
        elif group == 'Ice Product':
            return "冰矿产物"
        elif group == "Fuel Block":
            return "燃料块"
        elif group == "Moon Materials":
            return "元素"
        elif group == "Harvestable Cloud":
            return "气云"
        elif category == "Planetary Commodities":
            return "行星工业"
        elif category == 'Blueprint':
            return "蓝图"
        
        market_group_list = await SdeUtils.get_market_group_list(type_id)
        # meta = await SdeUtils.get_metaname_by_typeid(type_id)
        if 'Reaction Materials' in market_group_list:
            return "反应材料"
        if 'Salvage Materials' in market_group_list:
            return "打捞件"
        elif 'Ships' in market_group_list:
            return "舰船"
        elif 'Advanced Components' in market_group_list:
            return "高级组件"
        elif 'Standard Capital Ship Components' in market_group_list or 'Advanced Capital Components' in market_group_list:
            return "旗舰组件"
        elif 'Components' in market_group_list:
            return '其他组件'
        else:
            return "杂货"

    async def get_asset_statistics_data(self, sid: str):
        asset_view = await EveAssetViewDBUtils.select_by_sid(sid)
        if not asset_view:
            raise KahunaException('资产视图不存在')

        # 优先使用asset_container_id_list，如果没有则使用asset_container_id（向后兼容）
        container_list = asset_view.asset_container_id_list if hasattr(asset_view, 'asset_container_id_list') and asset_view.asset_container_id_list else []
        
        if not container_list:
            raise KahunaException('资产视图没有关联的容器')
        
        # 构建容器-所有者对列表
        container_owner_pairs = []
        for item in container_list:
            container_id = item["container_id"]
            owner_id = item["owner_id"]
            pull_permission = await EveIndustryAssetContainerPermissionDBUtils.select_by_container_id_and_owner_id(container_id, owner_id)
            if not pull_permission:
                raise KahunaException(f"容器 {container_id} 没有权限")
            container_owner_pairs.append([container_id, owner_id, pull_permission.tag])
        
        asset_dict = {
            container_id: {
                'container_id': container_id,
                'name': name,
                'assets': {}
            } for container_id, _, name in container_owner_pairs
        }
        for container_id, owner_id, _ in container_owner_pairs:
            container_asset_d = asset_dict[container_id]['assets']
            asset_data = await NAU.get_asset_in_container_owner_list([[container_id, owner_id]])
            for asset in asset_data:
                type_id = asset['type_id']
                price_data = await rdm().r.hgetall(f"market_price:jita:{type_id}")
                if not price_data:
                    price = 0
                else:
                    price = float(price_data['max_buy'])
                if not await self._check_filter(asset, asset_view):
                    continue
                
                if type_id not in container_asset_d:
                    container_asset_d[type_id] = {
                        'type_id': type_id,
                        'type_name': await SdeUtils.get_name_by_id(type_id),
                        'type_name_zh': await SdeUtils.get_name_by_id(type_id, 'zh'),
                        'quantity': 0,
                        'price': price,
                        "class_type": await self._get_class_type(type_id)
                    }
                container_asset_d[type_id]['quantity'] += asset['quantity']

        return asset_dict

    async def get_asset_view_by_sid(self, sid: str):
        return await EveAssetViewDBUtils.select_by_sid(sid)

    async def fill_sell_price_data(self, output: dict, config: dict):
        """
        返回格式：
        {
            type_id: {
                type_id: int,
                type_name: str,
                type_name_zh: str,
                quantity: int,
                price: float
            }
        }
        """
        res = {}
        price_base = config.get('price_base', 'jita_sell')
        percent = config.get('percent', 1.0)
        for type_id, item in output.items():
            price_data = await rdm().r.hgetall(f"market_price:jita:{type_id}")
            if not price_data:
                continue
            max_buy = float(price_data['max_buy'])
            min_sell = float(price_data['min_sell'])
            res[type_id] = item
            if price_base == 'jita_sell':
                item['price'] = min_sell * percent
            elif price_base == 'jita_mid':
                item['price'] = max_buy + (min_sell - max_buy) * percent
            elif price_base == 'jita_buy':
                item['price'] = max_buy * percent
        return res

    async def save_asset_view_config(
        self,
        user_name: str,
        sid: str,
        tag: str = None,
        public: bool = None,
        filter_list: list = None,
        view_type: str = None,
        config: dict = None,
        container_list: list = None,
        is_admin: bool = False
    ):
        """保存资产视图配置（部分更新）
        
        :param user_name: 用户名
        :param sid: 资产视图SID
        :param tag: 标签（可选）
        :param public: 是否公开（可选）
        :param filter_list: 过滤条件列表，格式为 [{"type": str, "value": str}, ...]（可选）
        :param view_type: 视图类型（可选）
        :param config: 配置字典（可选，会与现有配置合并）
        :param container_list: 容器列表，格式为 [{container_id: int, owner_id: int}, ...]（可选）
        :param is_admin: 是否为管理员（可选，管理员可以修改其他用户的资产视图）
        """
        asset_view = await EveAssetViewDBUtils.select_by_sid(sid)
        if not asset_view:
            raise KahunaException('资产视图不存在')
        
        # 检查权限：只能修改自己的资产视图，或者管理员可以修改任何用户的资产视图
        if not is_admin and asset_view.user_name != user_name:
            raise KahunaException('无权修改此资产视图')
        
        # 只更新传递的参数
        if tag is not None:
            asset_view.tag = tag
        if public is not None:
            asset_view.public = public
        if filter_list is not None:
            asset_view.filter = filter_list
        if view_type is not None:
            asset_view.view_type = view_type
        if config is not None:
            # 合并配置，而不是完全替换
            current_config = asset_view.config or {}
            if isinstance(current_config, str):
                # 如果 config 是字符串，尝试解析为字典
                try:
                    current_config = json.loads(current_config)
                except:
                    current_config = {}
            merged_config = {**current_config, **config}
            asset_view.config = merged_config
        if container_list is not None:
            # 验证所有容器都属于该用户
            user_container_permissions = {}
            async for cp in await EveIndustryAssetContainerPermissionDBUtils.select_all_by_user_name(user_name):
                key = (cp.asset_container_id, cp.asset_owner_id)
                user_container_permissions[key] = cp
            
            # 检查所有容器是否都属于该用户
            invalid_containers = []
            for item in container_list:
                container_id = item.get('container_id')
                owner_id = item.get('owner_id')
                key = (container_id, owner_id)
                if key not in user_container_permissions:
                    invalid_containers.append(f"container_id={container_id}, owner_id={owner_id}")
            
            if invalid_containers:
                raise KahunaException(f'以下容器不属于该用户: {invalid_containers}')
            
            # 构建 asset_container_id_list，存储 {container_id, owner_id} 组合
            asset_container_id_list = [
                {"container_id": item["container_id"], "owner_id": item["owner_id"]}
                for item in container_list
            ]
            asset_view.asset_container_id_list = asset_container_id_list
            # 更新asset_container_id和asset_owner_id为第一个容器（向后兼容）
            if container_list and len(container_list) > 0:
                asset_view.asset_container_id = container_list[0]['container_id']
                asset_view.asset_owner_id = container_list[0]['owner_id']
        
        # 保存到数据库
        async with dbm().get_session() as session:
            await session.merge(asset_view)
            await session.commit()

    async def create_asset_view_from_container_permission(self, user_name: str, container_tag: str):
        """从容器许可创建资产视图（废弃，保留用于向后兼容）
        
        :param user_name: 用户名
        :param container_tag: 容器许可的 tag
        :raises KahunaException: 如果容器许可不存在或已存在相同的资产视图
        """
        # 查找对应的容器许可
        container_permission = None
        async for cp in await EveIndustryAssetContainerPermissionDBUtils.select_all_by_user_name(user_name):
            if cp.tag == container_tag:
                container_permission = cp
                break
        
        if not container_permission:
            raise KahunaException(f'未找到标签为 {container_tag} 的容器许可')
        
        # 生成唯一的 sid
        sid = get_random_token(20)
        
        # 构建 asset_container_id_list，存储 {container_id, owner_id} 组合
        asset_container_id_list = [{
            "container_id": container_permission.asset_container_id,
            "owner_id": container_permission.asset_owner_id
        }]
        
        # 创建资产视图对象
        asset_view = M_EveAssetView(
            sid=sid,
            user_name=user_name,
            asset_owner_id=container_permission.asset_owner_id,
            asset_container_id=container_permission.asset_container_id,
            asset_container_id_list=asset_container_id_list,
            structure_id=container_permission.structure_id,
            system_id=container_permission.system_id,
            tag=container_permission.tag,
            public=False,
            filter=[],
            view_type='default'
        )
        
        await EveAssetViewDBUtils.save_obj(asset_view)

    async def create_asset_view_from_container_list(self, user_name: str, container_list: list, tag: str):
        """从容器列表创建资产视图
        
        :param user_name: 用户名
        :param container_list: 容器列表，格式为 [{container_id: int, owner_id: int}, ...]
        :param tag: 资产视图标签
        :raises KahunaException: 如果容器许可不存在
        """
        if not container_list or len(container_list) == 0:
            raise KahunaException('容器列表不能为空')
        
        # 验证所有容器都属于该用户
        user_container_permissions = {}
        async for cp in await EveIndustryAssetContainerPermissionDBUtils.select_all_by_user_name(user_name):
            key = (cp.asset_container_id, cp.asset_owner_id)
            user_container_permissions[key] = cp
        
        # 检查所有容器是否都属于该用户
        invalid_containers = []
        container_permissions = {}
        for item in container_list:
            container_id = item.get('container_id')
            owner_id = item.get('owner_id')
            key = (container_id, owner_id)
            if key not in user_container_permissions:
                invalid_containers.append(f"container_id={container_id}, owner_id={owner_id}")
            else:
                container_permissions[key] = user_container_permissions[key]
        
        if invalid_containers:
            raise KahunaException(f'以下容器不属于该用户: {invalid_containers}')
        
        # 使用第一个容器的信息作为基础信息（structure_id, system_id）
        first_item = container_list[0]
        first_key = (first_item['container_id'], first_item['owner_id'])
        first_permission = container_permissions[first_key]
        
        # 生成唯一的 sid
        sid = get_random_token(20)
        
        # 构建 asset_container_id_list，存储 {container_id, owner_id} 组合
        asset_container_id_list = [
            {"container_id": item["container_id"], "owner_id": item["owner_id"]}
            for item in container_list
        ]
        
        # 创建资产视图对象
        asset_view = M_EveAssetView(
            sid=sid,
            user_name=user_name,
            asset_owner_id=first_item['owner_id'],  # 保留用于向后兼容
            asset_container_id=first_item['container_id'],  # 保留用于向后兼容
            asset_container_id_list=asset_container_id_list,
            structure_id=first_permission.structure_id,
            system_id=first_permission.system_id,
            tag=tag,
            public=False,
            filter=[],
            view_type='default'
        )
        
        await EveAssetViewDBUtils.save_obj(asset_view)

    async def delete_asset_view(self, user_name: str, sid: str, is_admin: bool = False):
        """删除资产视图
        
        :param user_name: 用户名
        :param sid: 资产视图SID
        :param is_admin: 是否为管理员（可选，管理员可以删除其他用户的资产视图）
        :raises KahunaException: 如果资产视图不存在或无权删除
        """
        asset_view = await EveAssetViewDBUtils.select_by_sid(sid)
        if not asset_view:
            raise KahunaException('资产视图不存在')
        
        # 检查权限：只能删除自己的资产视图，或者管理员可以删除任何用户的资产视图
        if not is_admin and asset_view.user_name != user_name:
            raise KahunaException('无权删除此资产视图')
        
        # 删除资产视图
        await EveAssetViewDBUtils.delete_obj(asset_view)