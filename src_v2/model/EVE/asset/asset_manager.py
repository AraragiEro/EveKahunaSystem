
import asyncio
from datetime import datetime, timezone, timedelta

from src_v2.core.database.connect_manager import redis_manager
from src_v2.core.utils import SingletonMeta
from src_v2.core.utils import KahunaException, get_beijing_utctime

from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.user.user_manager import UserManager

from src_v2.core.database.kahuna_database_utils_v2 import EveAssetPullMissionDBUtils
from src_v2.core.database.model import EveAssetPullMission as M_EveAssetPullMission

from src_v2.core.database.neo4j_models import Asset
from src_v2.core.database.neo4j_utils import Neo4jAssetUtils

from src_v2.model.EVE.sde.utils import SdeUtils

from src_v2.model.EVE.eveesi import eveesi

# kahuna logger
from src_v2.core.log import logger

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

        await self.clean_asset_pull_mission_assets(mission_obj)
        await self.processing_asset_pull_mission(mission_obj)

        mission_obj.last_pull_time = get_beijing_utctime(datetime.now())
        await EveAssetPullMissionDBUtils.save_obj(mission_obj)

    async def get_user_asset_pull_mission_list(self, user_name: str) -> list[dict]:
        missions = []
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

    async def processing_asset_pull_mission(self, mission_obj: M_EveAssetPullMission):
        if mission_obj.asset_owner_type == 'character':
            pull_function = eveesi.characters_character_assets

        elif mission_obj.asset_owner_type == 'corp':
            pull_function = eveesi.corporations_corporation_assets

        access_character = await CharacterManager().get_character_by_character_id(mission_obj.access_character_id)
        assets = await pull_function(access_character.ac_token, mission_obj.asset_owner_id)

        for assets_list_batch in assets:
            for asset in assets_list_batch[:]:
                if asset["location_type"] == 'station':
                    # 上级为空间站是NPC空间站，需要补充创建星系
                    # 获取缓存
                    station_info_cache = await redis_manager.redis.hgetall(f'eveesi:universe_stations_station:{asset["location_id"]}')
                    if not station_info_cache:
                        station_info = await eveesi.universe_stations_station(asset["location_id"])
                        station_info_cache = {
                            "name": station_info["name"],
                            "system_id": station_info["system_id"],
                        }
                        await redis_manager.redis.hset(f'eveesi:universe_stations_station:{asset["location_id"]}', mapping=station_info_cache)
                        await redis_manager.redis.expire(f'eveesi:universe_stations_station:{asset["location_id"]}', 60*60*24)
                    else:
                        station_info = station_info_cache

                    system_info = SdeUtils.get_system_info_by_id(station_info["system_id"])
                    station_node = {
                        'station_id': asset["location_id"],
                        'station_name': station_info["name"],
                        'system_id': station_info["system_id"],
                        'system_name': system_info['system_name'],
                    }
                    asset.update({
                        'owner_id': mission_obj.asset_owner_id,
                        'type_name': SdeUtils.get_name_by_id(asset['type_id'])
                    })
                    await Neo4jAssetUtils.merge_asset_to_station(asset, station_node)
                    # 连接station到system
                    system_node = {
                        'system_id': system_info['system_id'],
                        'system_name': system_info['system_name'],
                        'region_id': system_info['region_id'],
                        'region_name': system_info['region_name'],
                    }
                    await Neo4jAssetUtils.merge_station_to_system(station_node, system_node)
                    assets_list_batch.remove(asset)

                elif asset["location_flag"] in structure_sub_location_flags:
                    # 这些location_flag的上级可能是玩家建筑，尝试连接已存在的建筑节点
                    structure_node = {
                        'structure_id': asset['location_id']
                    }
                    asset.update({
                        'type_name': SdeUtils.get_name_by_id(asset['type_id']),
                        'owner_id': mission_obj.asset_owner_id
                    })
                    if await Neo4jAssetUtils.merge_asset_to_structure_if_exists(asset, structure_node):
                        assets_list_batch.remove(asset)
                else:
                    asset.update({
                        'type_name': SdeUtils.get_name_by_id(asset['type_id']),
                        'owner_id': mission_obj.asset_owner_id
                    })
            # 插入剩余所有未处理节点
            assets_list_batch_withou_station_structure = [asset for asset in assets_list_batch if asset["location_type"] not in ['station', 'solar_system']]
            await Neo4jAssetUtils.batch_create_assets(assets_list_batch_withou_station_structure)

        # 补全玩家建筑信息
        forbidden_structure_node_list = await Neo4jAssetUtils.get_forbidden_structure_node_list(mission_obj.asset_owner_id)

        for forbidden_structure_node in forbidden_structure_node_list:
            # 建筑信息
            structure_info_cache = await redis_manager.redis.hgetall(f'eveesi:universe_structures_structure:{forbidden_structure_node["item_id"]}')
            if not structure_info_cache:
                structure_info = await eveesi.universe_structures_structure(access_character.ac_token, forbidden_structure_node["item_id"])
                if structure_info:
                    structure_info_cache = {
                        "name": structure_info["name"],
                        "owner_id": structure_info["owner_id"],
                        "solar_system_id": structure_info["solar_system_id"],
                        "type_id": structure_info["type_id"]
                    }
                else:
                    logger.info(f"建筑{forbidden_structure_node["item_id"]}无权限，创建无权限建筑")
                    structure_info_cache = {
                        'name': f'Forbidden {SdeUtils.get_name_by_id(forbidden_structure_node['type_id'])}',
                        'owner_id': 'unknown',
                        'solar_system_id': 'unknown',
                        'type_id': 'unknown',
                    }
                await redis_manager.redis.hset(f'eveesi:universe_structures_structure:{forbidden_structure_node["item_id"]}', mapping=structure_info_cache)
                await redis_manager.redis.expire(f'eveesi:universe_structures_structure:{forbidden_structure_node["item_id"]}', 60*60*24)
            structure_info = structure_info_cache
            
            # 星系信息
            if structure_info['solar_system_id'] != 'unknown':
                system_info = SdeUtils.get_system_info_by_id(structure_info["solar_system_id"])
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
                'structure_type': SdeUtils.get_name_by_id(structure_info['type_id']) if structure_info['type_id'] != 'unknown' else 'unknown',
                'structure_type_id': structure_info['type_id'] if structure_info['type_id'] != 'unknown' else 'unknown',
                'system_id': system_info['system_id'],
                'system_name': system_info['system_name'],
                'region_id': system_info['region_id'],
                'region_name': system_info['region_name'],
            }
            forbidden_structure_node.update({
                "type_id": structure_node['structure_type_id'],
                "type_name": structure_node['structure_type'],
                "owner_id": mission_obj.asset_owner_id,
            })
            await Neo4jAssetUtils.merge_asset_to_structure_to_solar_system(forbidden_structure_node, structure_node, solar_system_node)

    async def clean_asset_pull_mission_assets(self, mission_obj: M_EveAssetPullMission):
        owner_id = mission_obj.asset_owner_id
        await Neo4jAssetUtils.delete_assets_by_owner_id(owner_id)