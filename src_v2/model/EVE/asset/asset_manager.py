
import asyncio
from datetime import datetime, timezone, timedelta
import pathlib

from tqdm.std import tqdm

from src_v2.core.database.connect_manager import redis_manager as rdm, neo4j_manager
from src_v2.core.utils import SingletonMeta, tqdm_manager
from src_v2.core.utils import KahunaException, get_beijing_utctime

from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.user.user_manager import UserManager

from src_v2.core.database.kahuna_database_utils_v2 import EveAssetPullMissionDBUtils
from src_v2.core.database.model import EveAssetPullMission as M_EveAssetPullMission

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

        await rdm.r.hset(f'asset_pull_mission_status:{asset_owner_type}:{asset_owner_id}', 'step_name', "清理旧数据")
        await self.clean_asset_pull_mission_assets(mission_obj)
        await self.processing_asset_pull_mission(mission_obj)

        mission_obj.last_pull_time = get_beijing_utctime(datetime.now())
        await EveAssetPullMissionDBUtils.merge(mission_obj)

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

    async def get_station_info(self, station_id: int):
        # 上级为空间站是NPC空间站，需要补充创建星系
        # 获取缓存
        station_info_cache = await rdm.redis.hgetall(f'eveesi:universe_stations_station:{station_id}')
        if not station_info_cache:
            station_info = await eveesi.universe_stations_station(station_id)
            station_info_cache = {
                "name": station_info["name"],
                "system_id": station_info["system_id"],
            }
            await rdm.redis.hset(f'eveesi:universe_stations_station:{station_id}', mapping=station_info_cache)
            await rdm.redis.expire(f'eveesi:universe_stations_station:{station_id}', 60*60*24)
        else:
            station_info = station_info_cache
            return station_info, False

        return station_info, True

    async def create_station_node(self, station_id: int):
        async with CREATE_STATION_SEMAPHORE:
            station_info, is_new = await self.get_station_info(station_id)
            if not is_new:
                return
            system_info = SdeUtils.get_system_info_by_id(station_info["system_id"])
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

        last_progress = 0
        async def generate_with_semaphore(asset: dict):
            nonlocal last_progress
            async with neo4j_manager.semaphore:
                if asset["item_id"] in structure_item_id_list:
                    return
                asset.update({
                    'type_name': SdeUtils.get_name_by_id(asset['type_id']),
                    'owner_id': mission_obj.asset_owner_id
                })
                await NIU.merge_node(
                    "Asset",
                    {
                        "item_id": asset["item_id"],
                        "owner_id": asset["owner_id"],
                    },
                    asset
                )

                if asset["location_type"] == 'station':
                    await self.create_station_node(asset["location_id"])

                now_progress = await tqdm_manager.update_mission("_generate_all_nodes", 1)
                if now_progress / len(assets_list) * 100 > last_progress + 0.1:
                    await rdm.r.hset(status_key, 'step_progress', now_progress / len(assets_list))
                    last_progress = now_progress / len(assets_list)

        await tqdm_manager.add_mission("_generate_all_nodes", len(assets_list))
        await rdm.r.hset(status_key, 'step_name', "生成资产树节点")
        await rdm.r.hset(status_key, 'step_progress', 0)
        tasks = [asyncio.create_task(generate_with_semaphore(asset)) for asset in assets_list]
        await asyncio.gather(*tasks)
        await tqdm_manager.complete_mission("_generate_all_nodes")

    async def _generate_all_locate_relation(self, assets_list: list[dict], mission_obj: M_EveAssetPullMission):
        status_key = f'asset_pull_mission_status:{mission_obj.asset_owner_type}:{mission_obj.asset_owner_id}'
        structure_nodes = await NAU.get_structure_nodes()
        structure_item_id_list = [structure.get("structure_id", None) for structure in structure_nodes]
        
        last_progress = 0
        async def generate_with_semaphore(asset: dict):
            nonlocal last_progress
            async with neo4j_manager.semaphore:
                if asset["location_type"] == 'station':
                    await NIU.link_node(
                        "Asset",
                        {
                            "item_id": asset["item_id"],
                            "type_id": asset["type_id"],
                            "owner_id": mission_obj.asset_owner_id,
                        },
                        {},
                        "LOCATED_IN",
                        {},{},
                        "Station",
                        {
                            "station_id": asset["location_id"],
                        },
                        {}
                    )
                elif asset["location_type"] == 'solar_system':
                    system_info = SdeUtils.get_system_info_by_id(asset["location_id"])
                    system_node = {
                        'system_id': system_info['system_id'],
                        'system_name': system_info['system_name'],
                        'region_id': system_info['region_id'],
                        'region_name': system_info['region_name'],
                    }
                    async with CREATE_STATION_SEMAPHORE:
                        await NIU.merge_node(
                            "SolarSystem",
                            {
                                "solar_system_id": system_info["system_id"],
                            },
                            system_node
                        )
                    await NIU.link_node(
                        "Asset",
                        {
                            "item_id": asset["item_id"],
                            "type_id": asset["type_id"],
                            "owner_id": mission_obj.asset_owner_id,
                        },
                        {
                            "item_id": asset["item_id"],
                            "type_id": asset["type_id"],
                            "owner_id": mission_obj.asset_owner_id,
                        },
                        "LOCATED_IN",
                        {},{},
                        "SolarSystem",
                        {"solar_system_id": system_info["system_id"]},
                        {"solar_system_id": system_info["system_id"]}
                    )
                else:
                    if asset["location_id"] in structure_item_id_list:
                        
                        await NIU.link_node(
                            "Asset",
                            {
                                "item_id": asset["item_id"],
                                "type_id": asset["type_id"],
                                "owner_id": mission_obj.asset_owner_id,
                            },
                            {
                                "item_id": asset["item_id"],
                                "type_id": asset["type_id"],
                                "owner_id": mission_obj.asset_owner_id,
                            },
                            "LOCATED_IN",
                            {},{},
                            "Structure",
                            {"structure_id": asset["location_id"]},
                            {"structure_id": asset["location_id"]}
                        )
                    else:
                        await NIU.link_node(
                            "Asset",
                            {
                                "item_id": asset["item_id"],
                                "type_id": asset["type_id"],
                                "owner_id": mission_obj.asset_owner_id,
                            },
                            {
                                "item_id": asset["item_id"],
                                "type_id": asset["type_id"],
                                "owner_id": asset["owner_id"],
                            },
                            "LOCATED_IN",
                            {},{},
                            "Asset",
                            {
                                "item_id": asset["location_id"],
                                "owner_id": asset["owner_id"],
                            },
                            {
                                "item_id": asset["location_id"],
                                "owner_id": mission_obj.asset_owner_id,
                            }
                        )
                now_progress = await tqdm_manager.update_mission("_generate_all_locate_relation", 1)
                if now_progress / len(assets_list) > last_progress + 0.1:
                    await rdm.r.hset(status_key, 'step_progress', now_progress / len(assets_list))
                    last_progress = now_progress / len(assets_list)

        await tqdm_manager.add_mission("_generate_all_locate_relation", len(assets_list))
        await rdm.r.hset(status_key, 'step_name', "生成资产树关系")
        await rdm.r.hset(status_key, 'step_progress', 0)
        tasks = [asyncio.create_task(generate_with_semaphore(asset)) for asset in assets_list]
        # await asyncio.gather(*tasks)
        while True:
            uncompleted_tasks = [task for task in tasks if not task.done()]
            if not uncompleted_tasks:
                break
            await asyncio.sleep(0.1)  # 避免 CPU 占用过高
        await tqdm_manager.complete_mission("_generate_all_locate_relation")

    async def _generate_forbidden_structure_node(self, mission_obj: M_EveAssetPullMission):
        access_character = await CharacterManager().get_character_by_character_id(mission_obj.access_character_id)
        # 补全玩家建筑信息
        forbidden_structure_node_list = await NAU.get_forbidden_structure_node_list(mission_obj.asset_owner_id)
        status_key = f'asset_pull_mission_status:{mission_obj.asset_owner_type}:{mission_obj.asset_owner_id}'
        await rdm.r.hset(status_key, 'step_name', "生成无权限建筑节点")
        await rdm.r.hset(status_key, 'step_progress', 0.5)
        await rdm.r.hset(status_key, 'is_indeterminate', 1)

        await tqdm_manager.add_mission("_generate_forbidden_structure_node", len(forbidden_structure_node_list))
        for forbidden_structure_node in forbidden_structure_node_list:
            # 建筑信息
            structure_info_cache = await rdm.redis.hgetall(f'eveesi:universe_structures_structure:{forbidden_structure_node["item_id"]}')
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
                    logger.debug(f"建筑{forbidden_structure_node["item_id"]}无权限，创建无权限建筑")
                    structure_info_cache = {
                        'name': f'Forbidden {SdeUtils.get_name_by_id(forbidden_structure_node['type_id'])}',
                        'owner_id': 'unknown',
                        'solar_system_id': 'unknown',
                        'type_id': 'unknown',
                    }
                await rdm.redis.hset(f'eveesi:universe_structures_structure:{forbidden_structure_node["item_id"]}', mapping=structure_info_cache)
                await rdm.redis.expire(f'eveesi:universe_structures_structure:{forbidden_structure_node["item_id"]}', 60*60*24)
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
            async with CREATE_STATION_SEMAPHORE:
                await NAU.merge_asset_to_structure_to_solar_system(forbidden_structure_node, structure_node, solar_system_node)
            await tqdm_manager.update_mission("_generate_forbidden_structure_node", 1)
        await tqdm_manager.complete_mission("_generate_forbidden_structure_node")

    async def _update_structure_node(self, mission_obj: M_EveAssetPullMission):
        access_character = await CharacterManager().get_character_by_character_id(mission_obj.access_character_id)
        structure_asset_nodes = await NAU.get_structure_asset_nodes(mission_obj.asset_owner_id)
        status_key = f'asset_pull_mission_status:{mission_obj.asset_owner_type}:{mission_obj.asset_owner_id}'
        await rdm.r.hset(status_key, 'step_name', "更新建筑节点信息")
        await rdm.r.hset(status_key, 'step_progress', 0.0)
        await rdm.r.hset(status_key, 'is_indeterminate', 0)

        await tqdm_manager.add_mission("_update_structure_node", len(structure_asset_nodes))
        for node in structure_asset_nodes:
            structure_info_cache = await rdm.redis.hgetall(f'eveesi:universe_structures_structure:{node["item_id"]}')
            if not structure_info_cache:
                structure_info = await eveesi.universe_structures_structure(access_character.ac_token, node["item_id"])
                if structure_info:
                    system_info = SdeUtils.get_system_info_by_id(structure_info["solar_system_id"])
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
                        'name': f'Forbidden {SdeUtils.get_name_by_id(node['type_id'])}',
                        'owner_id': 'unknown',
                        'solar_system_id': 'unknown',
                        'type_id': 'unknown',
                        'system_id': 'unknown',
                        'system_name': 'unknown',
                        'region_id': 'unknown',
                        'region_name': 'unknown',
                    }
                await rdm.redis.hset(f'eveesi:universe_structures_structure:{node["item_id"]}', mapping=structure_info_cache)
                await rdm.redis.expire(f'eveesi:universe_structures_structure:{node["item_id"]}', 60*60*24)
            structure_info = structure_info_cache
            structure_node = {
                'structure_id': node["item_id"],
                'structure_name': structure_info["name"],
                'structure_type': SdeUtils.get_name_by_id(structure_info['type_id']) if structure_info['type_id'] != 'unknown' else 'unknown',
                'structure_type_id': structure_info['type_id'] if structure_info['type_id'] != 'unknown' else 'unknown',
                'system_id': structure_info['system_id'],
                'system_name': structure_info['system_name'],
                'region_id': structure_info['region_id'],
                'region_name': structure_info['region_name'],
            }

            await NAU.change_asset_to_structure(node, structure_node)
            now_progress = await tqdm_manager.update_mission("_update_structure_node", 1)
            await rdm.r.hset(status_key, 'step_progress', now_progress / len(structure_asset_nodes))
        await tqdm_manager.complete_mission("_update_structure_node")

    async def processing_asset_pull_mission(self, mission_obj: M_EveAssetPullMission):
        status_key = f'asset_pull_mission_status:{mission_obj.asset_owner_type}:{mission_obj.asset_owner_id}'

        if mission_obj.asset_owner_type == 'character':
            pull_function = eveesi.characters_character_assets

        elif mission_obj.asset_owner_type == 'corp':
            pull_function = eveesi.corporations_corporation_assets

        access_character = await CharacterManager().get_character_by_character_id(mission_obj.access_character_id)

        await rdm.r.hset(status_key, 'step_name', "通过api拉取资产")
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
        await self._generate_forbidden_structure_node(mission_obj)
        await self._update_structure_node(mission_obj)
        
    async def clean_asset_pull_mission_assets(self, mission_obj: M_EveAssetPullMission):
        owner_id = mission_obj.asset_owner_id
        await NAU.delete_assets_by_owner_id(owner_id)

    async def search_container_by_item_name(self, user_name, item_name: str):
        type_id = SdeUtils.get_id_by_name(item_name)
        # 获得用户能访问的所有资产所有者id
        owner_id_list = []
        async for mission in await EveAssetPullMissionDBUtils.select_all_by_user_name(user_name):
            owner_id_list.append(mission.asset_owner_id)

        # TODO 如果公司开放且不包含，则新增 

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
