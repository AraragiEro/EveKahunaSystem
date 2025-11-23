# 标准库导入
import json

# 本地导入 - 核心工具
from src_v2.core.database.connect_manager import redis_manager as rdm
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveAssetPullMissionDBUtils,
    EveIndustryAssetContainerPermissionDBUtils
)
from src_v2.core.utils import KahunaException

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
        if container.asset_container_id == container_data['item_id']:
            raise KahunaException(f"容器 {container_data['item_id']} 已存在")

    permission_obj = EveIndustryAssetContainerPermissionDBUtils.get_obj()
    permission_obj.user_name = user_id
    permission_obj.asset_owner_id = asset_data['owner_id']
    permission_obj.asset_container_id = container_data['item_id']
    permission_obj.structure_id = structure_data['structure_id']
    permission_obj.system_id = system_data['system_id']
    permission_obj.tag = data['tag']
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


async def get_user_all_container_permission(user_id: str):
    """获取用户所有容器权限
    
    Args:
        user_id: 用户ID
    
    Returns:
        List[dict]: 容器权限列表
    """
    cache_str = await rdm.r.get(f'container_permission:{user_id}:all_container_permission')
    if cache_str:
        return json.loads(cache_str)

    all_container_permission = []
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
            owner = await eveesi.corporations_corporation_id(pull_mission.asset_owner_id)
            owner_name = owner['name']
        system_info = await SdeUtils.get_system_info_by_id(container.system_id)
        structure_info_cache = await rdm.redis.hgetall(f'eveesi:universe_structures_structure:{container.structure_id}')
        if not structure_info_cache:
            structure_info_cache = await eveesi.universe_structures_structure(access_character.ac_token, container.structure_id)
            structure_info_cache.pop("position")
            await rdm.redis.hset(f'eveesi:universe_structures_structure:{container.structure_id}', mapping=structure_info_cache)
        
        container = {
            "asset_owner_id": container.asset_owner_id,
            "asset_container_id": container.asset_container_id,
            "structure_id": container.structure_id,
            "structure_name": structure_info_cache['name'],
            "system_id": container.system_id,
            "system_name": system_info['system_name'],
            "owner_type": owner_type,
            "owner_name": owner_name,
            "tag": container.tag,
        }
        all_container_permission.append(container)

    await rdm.r.set(f'container_permission:{user_id}:all_container_permission', json.dumps(all_container_permission), ex=60*60)
    return all_container_permission

