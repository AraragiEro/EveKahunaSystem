# 标准库导入
import json

# 本地导入 - 核心工具
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.connect_manager import get_neo4j_manager as neo4j_manager
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveAssetPullMissionDBUtils,
    EveIndustryAssetContainerPermissionDBUtils
)
from src_v2.core.utils import KahunaException
from src_v2.core.database.neo4j_utils import Neo4jAssetUtils as NAU

# 本地导入 - EVE 模块
from src_v2.model.EVE.character import CharacterManager
from src_v2.model.EVE.eveesi import eveesi
from src_v2.model.EVE.sde import SdeUtils


async def add_industrypermision(user_id: str, data):
    """添加工业权限
    
    Args:
        user_id: 用户ID
        data: 包含 container, asset, structure, system 和 tag 的数据
    """
    container_data = data['container']
    asset_data = data['asset']
    structure_data = data['structure']
    system_data = data['system']

    async for container in await EveIndustryAssetContainerPermissionDBUtils.select_all_by_user_name(user_id):
        if container.asset_container_id == container_data['item_id'] and container.location_flag == asset_data['location_flag']:
            raise KahunaException(f"容器 {container_data['item_id']} 位置标志 {asset_data['location_flag']} 已存在")

    # # 检查是否为建筑节点，禁止使用建筑节点作为许可访问点
    # async with neo4j_manager().get_session() as session:
    #     query = """
    #     MATCH (n:Structure {item_id: $item_id})
    #     RETURN n
    #     LIMIT 1
    #     """
    #     result = await session.run(query, {"item_id": container_data['item_id']})
    #     record = await result.single()
    #     if record and record["n"]:
    #         raise KahunaException(f"禁止使用建筑节点作为许可访问点，请使用空间站货柜对您的资产进行分类。")

    permission_obj = EveIndustryAssetContainerPermissionDBUtils.get_obj()
    permission_obj.user_name = user_id
    permission_obj.asset_owner_id = asset_data['owner_id']
    permission_obj.asset_container_id = container_data['item_id']
    permission_obj.structure_id = structure_data['structure_id']
    permission_obj.system_id = system_data['system_id']
    permission_obj.tag = data['tag']
    permission_obj.location_flag = asset_data['location_flag']
    await EveIndustryAssetContainerPermissionDBUtils.save_obj(permission_obj)


async def delete_industrypermision(user_id: str, data):
    """删除工业权限
    
    Args:
        user_id: 用户ID
        data: 包含 asset_owner_id 和 asset_container_id 的数据
    """
    asset_owner_id = data['asset_owner_id']
    asset_container_id = data['asset_container_id']

    async for permission in await EveIndustryAssetContainerPermissionDBUtils.select_all_by_user_name(user_id):
        if permission.asset_owner_id == asset_owner_id and permission.asset_container_id == asset_container_id:
            await EveIndustryAssetContainerPermissionDBUtils.delete_obj(permission)
            return
    raise KahunaException(f"许可不存在")


def _serialize_for_redis(data: dict) -> dict:
    """将字典中的复杂类型（list, dict）序列化为JSON字符串，以便存储到Redis
    
    Args:
        data: 要序列化的字典
    
    Returns:
        序列化后的字典，所有list和dict值都被转换为JSON字符串
    """
    result = {}
    for key, value in data.items():
        if isinstance(value, (list, dict)):
            result[key] = json.dumps(value, ensure_ascii=False)
        else:
            result[key] = value
    return result


async def get_user_all_container_permission(user_id: str):
    """获取用户所有容器权限
    
    Args:
        user_id: 用户ID
    
    Returns:
        List[dict]: 容器权限列表
    """
    cache_str = await rdm().r.get(f'container_permission:{user_id}:all_container_permission')
    if cache_str:
        return json.loads(cache_str)

    all_container_permission = []
    onwer_corp_d = {}
    async for container in await EveIndustryAssetContainerPermissionDBUtils.select_all_by_user_name(user_id):
        pull_mission = await EveAssetPullMissionDBUtils.select_mission_by_owner_id(container.asset_owner_id)
        if not pull_mission:
            continue
        access_character = await CharacterManager().get_character_by_character_id(pull_mission.access_character_id)
        owner_type = pull_mission.asset_owner_type
        if owner_type == 'character':
            owner = await eveesi.characters_character(pull_mission.asset_owner_id)
            owner_name = owner['name']
        elif owner_type == 'corp':
            if pull_mission.asset_owner_id not in onwer_corp_d:
                owner = await eveesi.corporations_corporation_id(pull_mission.asset_owner_id)
                onwer_corp_d[pull_mission.asset_owner_id] = owner['name']
            owner_name = onwer_corp_d[pull_mission.asset_owner_id]
        else:
            raise KahunaException(f"资产所有者类型错误: {owner_type}")
        system_info = await SdeUtils.get_system_info_by_id(container.system_id)
        if container.structure_id > 100000000:
            structure_info_cache = await rdm().r.hgetall(f'eveesi:universe_structures_structure:{container.structure_id}')
            if not structure_info_cache:
                # 玩家建筑
                structure_info_cache = await eveesi.universe_structures_structure(access_character.ac_token, container.structure_id)
                structure_info_cache.pop("position", None)
                # 序列化复杂类型以便存储到Redis
                serialized_cache = _serialize_for_redis(structure_info_cache)
                await rdm().redis.hset(f'eveesi:universe_structures_structure:{container.structure_id}', mapping=serialized_cache)
        # 空间站
        else:
            station_info_cache = await rdm().r.hgetall(f'eveesi:universe_stations_station:{container.structure_id}')
            if not station_info_cache:
                station_info_cache = await eveesi.universe_stations_station(container.structure_id)
                station_info_cache.pop("position", None)
                # 序列化复杂类型以便存储到Redis
                serialized_cache = _serialize_for_redis(station_info_cache)
                await rdm().redis.hset(f'eveesi:universe_stations_station:{container.structure_id}', mapping=serialized_cache)
        
        container = {
            "asset_owner_id": container.asset_owner_id,
            "asset_container_id": container.asset_container_id,
            "structure_id": container.structure_id,
            "structure_name": structure_info_cache['name'] if structure_info_cache else station_info_cache['name'],
            "system_id": container.system_id,
            "system_name": system_info['system_name'],
            "owner_type": owner_type,
            "owner_name": owner_name,
            "tag": container.tag,
            "location_flag": container.location_flag,
        }
        all_container_permission.append(container)

    await rdm().r.set(f'container_permission:{user_id}:all_container_permission', json.dumps(all_container_permission), ex=60*60)
    return all_container_permission


async def get_location_flag_list(asset_owner_id: int, asset_container_id: int):
    """获取位置标志列表
    
    Args:
        asset_owner_id: 资产所有者ID
        asset_container_id: 资产容器ID
    """
    asset_in_user_container_list = await NAU.get_asset_in_container_owner_list([[asset_container_id, asset_owner_id, None]])

    for asset in asset_in_user_container_list:
        if 'CorpSAG' in asset['location_flag']:
            return [
                'CorpSAG1',
                'CorpSAG2',
                'CorpSAG3',
                'CorpSAG4',
                'CorpSAG5',
                'CorpSAG6',
                'CorpSAG7',
            ]
    
    return []

async def update_container_permission_tag(user_id: str, data):
    """更新容器许可标签
    
    Args:
        user_id: 用户ID
        data: 包含 asset_owner_id, asset_container_id 和 tag 的数据
    
    Raises:
        KahunaException: 如果许可不存在或无权修改
    """
    asset_owner_id = data['asset_owner_id']
    asset_container_id = data['asset_container_id']
    new_tag = data['tag']
    
    # 查找许可记录（包含 user_name 条件）
    permission = await EveIndustryAssetContainerPermissionDBUtils.select_by_container_id_owner_id_and_user_name(
        asset_container_id, asset_owner_id, user_id
    )
    
    if not permission:
        raise KahunaException(f"许可不存在")
    
    # 更新标签
    permission.tag = new_tag
    await EveIndustryAssetContainerPermissionDBUtils.merge(permission)
    
    # 清除缓存
    await rdm().r.delete(f'container_permission:{user_id}:all_container_permission')


async def update_container_permission_location_flag(user_id: str, data):
    """更新容器许可位置标志
    
    Args:
        user_id: 用户ID
        data: 包含 asset_owner_id, asset_container_id 和 location_flag 的数据
    
    Raises:
        KahunaException: 如果许可不存在或无权修改
    """
    asset_owner_id = data['asset_owner_id']
    asset_container_id = data['asset_container_id']
    new_location_flag = data['location_flag']
    
    # 查找许可记录（包含 user_name 条件）
    permission = await EveIndustryAssetContainerPermissionDBUtils.select_by_container_id_owner_id_and_user_name(
        asset_container_id, asset_owner_id, user_id
    )
    
    if not permission:
        raise KahunaException(f"许可不存在")
    
    # 更新位置标志
    permission.location_flag = new_location_flag
    await EveIndustryAssetContainerPermissionDBUtils.merge(permission)
    
    # 清除缓存
    await rdm().r.delete(f'container_permission:{user_id}:all_container_permission')

