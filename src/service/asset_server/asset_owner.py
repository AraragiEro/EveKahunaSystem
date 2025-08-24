import asyncio

from tqdm import tqdm

# kahuna model
from ..evesso_server.eveesi import (characters_character_assets,
                                    corporations_corporation_assets,
                                    characters_character_id_blueprints,
                                    corporations_corporation_id_blueprints)
from ..character_server.character import Character

from ..database_server.sqlalchemy.kahuna_database_utils import (
    AssetDBUtils, AssetCacheDBUtils,
    AssetOwnerDBUtils,
    BluerprintAssetDBUtils
)
from ..database_server.sqlalchemy.connect_manager import database_manager

# kahuna logger
from ..log_server import logger

# kahuna KahunaException

# 查价缓存

REGION_FORGE_ID = 10000002
JITA_TRADE_HUB_STRUCTURE_ID = 60003760
FRT_4H_STRUCTURE_ID = 1035466617946


class AssetOwner():
    owner_qq = 0
    owner_type: str = "character"
    owner_id: int = 0
    access_character: Character = None

    def __init__(self, owner_qq: int, owner_type: str, owner_id: int, access_character: Character):
        if owner_type != "character" and owner_type != "corp":
            raise ValueError("Invalid owner_type. [character or corp]")
        self.owner_qq = owner_qq
        self.owner_type = owner_type
        self.owner_id = owner_id
        self.access_character = access_character

    @staticmethod
    async def get_all_asset_owner():
        return await AssetOwnerDBUtils.get_all_asset_owner()

    async def get_from_db(self):
        return await AssetOwnerDBUtils.get_asset_owner_by_owner_id_and_owner_type(self.owner_id, self.owner_type)

    @property
    async def token_accessable(self):
        res = None
        if self.owner_type == "character":
            res = await characters_character_assets(self.access_character.ac_token, self.owner_id, test=True)
        elif self.owner_type == "corp":
            res = await corporations_corporation_assets(self.access_character.ac_token, self.owner_id, test=True)
        if not res:
            return False
        return True

    async def insert_to_db(self):
        obj = await self.get_from_db()

        if not obj:
            obj = AssetOwnerDBUtils.get_obj()

        obj.asset_owner_id = self.owner_id
        obj.asset_type = self.owner_type
        obj.asset_owner_qq = self.owner_qq
        obj.asset_access_character_id = self.access_character.character_id

        await AssetOwnerDBUtils.save_obj(obj)

    async def get_asset(self):
        logger.info(f"开始刷新 {self.owner_type} {self.access_character.character_name} 资产")
        if self.owner_type == "character":
            await self.get_owner_asset(characters_character_assets, self.owner_id)
            logger.info(f"请求bp资产。")
            await self.get_owner_bp_asset(characters_character_id_blueprints, self.owner_id)
        elif self.owner_type == "corp":
            await self.get_owner_asset(corporations_corporation_assets, self.owner_id)
            logger.info(f"请求bp资产。")
            await self.get_owner_bp_asset(corporations_corporation_id_blueprints, self.owner_id)

    async def get_owner_asset(self, asset_esi, owner_id):
        results = await asset_esi(self.access_character.ac_token, owner_id)

        await AssetDBUtils.delete_asset_by_ownerid_and_owner_type(self.owner_id, self.owner_type)
        # 批量写入
        with tqdm(total=len(results), desc=f"写入{AssetDBUtils.cls_model.__tablename__}数据库", unit="page", ascii='=-') as pbar:
            for result in results:
                # result = [order for order in result if order["location_id"] == JITA_TRADE_HUB_STRUCTURE_ID]
                for asset in result:
                    asset.update({"asset_type": self.owner_type, "owner_id": self.owner_id})
                    if "is_blueprint_copy" not in asset:
                        asset["is_blueprint_copy"] = False
                await AssetDBUtils.insert_many(result)
                pbar.update()
        logger.info("请求完成。")

    async def get_owner_bp_asset(self, asset_esi, owner_id):
        if not self.access_character:
            return
        results = await asset_esi(self.access_character.ac_token, owner_id)

        # 删除owner的bp资产
        await BluerprintAssetDBUtils.delete_blueprint_asset_by_owner_id_and_owner_type(self.owner_id, self.owner_type)
        with tqdm(total=len(results), desc=f"写入{BluerprintAssetDBUtils.cls_model.__tablename__}数据库", unit="page", ascii='=-') as pbar:
            for result in results:
                for asset in result:
                    asset.update({"owner_type": self.owner_type, "owner_id": self.owner_id})
                await BluerprintAssetDBUtils.insert_many(result)
                pbar.update()

    async def asset_item_count(self):
        return await AssetCacheDBUtils.owner_id_asset_item_count(self.owner_id)

    def asset_valuation(self):
        pass

