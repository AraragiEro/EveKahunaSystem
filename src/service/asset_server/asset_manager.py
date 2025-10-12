
import asyncio

from .asset_container import AssetContainer, ContainerTag
from ..database_server.sqlalchemy.kahuna_database_utils import (
    AssetCacheDBUtils,
    BluerprintAssetCacheDBUtils,
    RefreshDataDBUtils
)
from .asset_owner import AssetOwner
from ..character_server.character_manager import CharacterManager
from ..industry_server.structure import StructureManager
from ..sde_service.utils import SdeUtils
from ..evesso_server.eveesi import universe_structures_structure
# from ..database_server.utils import RefreshDateUtils
# kahuna KahunaException
from ...utils import KahunaException

# kahuna logger
from ..log_server import logger

class AssetManager():
    init_asset_status = False
    init_container_status = False
    asset_dict: dict[(str, int): AssetOwner] = dict() # {(owner_type, owner_id): Asset}
    container_dict: dict[(int, str): AssetContainer] = dict() # {(owner_qq, location_id): AssetContainer}
    monitor_process = None
    last_refresh = None
    refresh_flag = asyncio.Lock()

    @classmethod
    async def init(cls):
        await cls.init_asset_dict()
        await cls.init_container_dict()

    @classmethod
    async def init_asset_dict(cls):
        if not cls.init_asset_status:
            owner_list = await AssetOwner.get_all_asset_owner()
            for owner in owner_list:
                access_character = CharacterManager.get_character_by_id(owner.asset_access_character_id)
                asset_owner = AssetOwner(
                    owner.asset_owner_qq,
                    owner.asset_type,
                    owner.asset_owner_id,
                    access_character)
                cls.asset_dict[(asset_owner.owner_type, asset_owner.owner_id)] = asset_owner
                logger.info(f"初始化库存凭据: {asset_owner.owner_type}, QQ:{owner.asset_owner_qq}")
        cls.init_status = True
        logger.info(f"init asset complete. {id(cls)}")

    @classmethod
    async def init_container_dict(cls):
        if not cls.init_container_status:
            container_list = await AssetContainer.get_all_asset_container()
            for container in container_list:
                asset_container = AssetContainer(
                    container.asset_location_id,
                    container.asset_location_type,
                    container.asset_name,
                    container.asset_owner_qq,
                )
                asset_container.structure_id = container.structure_id
                asset_container.solar_system_id = container.solar_system_id
                asset_container.asset_owner_id = container.asset_owner_id
                asset_container.asset_owner_type = container.asset_owner_type
                asset_container.tag = container.tag

                cls.container_dict[(asset_container.asset_owner_qq, asset_container.asset_location_id)] = asset_container
        cls.init_container_status = True
        logger.info(f"init container complete. {id(cls)}")

    @classmethod
    async def create_asset(cls, qq_id: int, type: str, owner_id, character_obj):
        asset = AssetOwner(qq_id, type, owner_id, character_obj)
        if not await asset.token_accessable:
            return

        await asset.insert_to_db()
        cls.asset_dict[(type, owner_id)] = asset
        return asset

    @classmethod
    async def copy_to_cache(cls):
        await AssetCacheDBUtils.copy_base_to_cache()
        await BluerprintAssetCacheDBUtils.copy_base_to_cache()

    @classmethod
    async def refresh_asset(cls, type, owner_id):
        asset: AssetOwner = cls.asset_dict.get((type, owner_id), None)
        if asset is None:
            raise KahunaException("没有找到对应的库存。")
        await asset.get_asset()
        await cls.copy_to_cache()
        return asset

    @classmethod
    async def refresh_all_asset(cls, force=False):
        if not force and not await RefreshDataDBUtils.out_of_min_interval('asset', 15):
            return
        if cls.refresh_flag.locked():
            logger.info('可能有计算任务执行中，延迟资产刷新。')
            return
        async with cls.refresh_flag:
            logger.info('开始刷新所有资产')
            for asset in cls.asset_dict.values():
                await asset.get_asset()
            await cls.copy_to_cache()

            await RefreshDataDBUtils.update_refresh_date('asset')
            logger.info('刷新资产完成。')

    @classmethod
    async def get_asset_in_container_list(cls, container_list: list):
        return await AssetCacheDBUtils.select_asset_in_container_list(container_list)

    @classmethod
    async def add_container(cls, owner_qq: int, location_id: int, location_type: str, asset_name: str, operate_qq: int, ac_token):
        if location_type == 'Hangar':
            raise KahunaException("个人机库根目录暂不支持加入容器")
        # 权限校验
        asset_data = await AssetCacheDBUtils.select_one_asset_in_location_id(location_id)
        if not asset_data:
            raise KahunaException('没有相关资产数据，请确认location id是否正确。')
        if not AssetContainer.operater_has_container_permission(operate_qq, asset_data.owner_id):
            raise KahunaException("container permission denied.")

        """
        solar_system_id = 0
        asset_owner_id = 0
        """

        asset_container = AssetContainer(
            location_id,
            location_type,
            asset_name,
            owner_qq
        )

        # access_character = CharacterManager.get_character_by_id(UserManager.get_main_character_id(operate_qq))
        structure_id, structure_flag = await StructureManager.get_structure_id_from_location_id(asset_data.location_id, asset_data.location_flag)
        structure_info = await universe_structures_structure(ac_token, structure_id)

        asset_container.asset_owner_id = asset_data.owner_id
        asset_container.asset_owner_type = asset_data.asset_type
        asset_container.structure_id = structure_id
        asset_container.solar_system_id = structure_info["solar_system_id"]

        await asset_container.insert_to_db()
        cls.container_dict[(owner_qq, location_id)] = asset_container

        return asset_container

    @classmethod
    async def set_container_tag(cls, require_list: list[int, int], tag: str):
        if tag not in ContainerTag.__members__:
            raise KahunaException(f"tag must be {ContainerTag.__members__}")
        success_list = []
        for owner_qq, container_id in require_list:
            if (owner_qq, container_id) not in cls.container_dict:
                continue

            container = cls.container_dict[owner_qq, container_id]
            container.tag = tag
            await container.insert_to_db()
            success_list.append(container)
        return success_list

    @classmethod
    def get_user_container(cls, owner_qq: int):
        return [container for k, container in cls.container_dict.items() if k[0] == owner_qq]
