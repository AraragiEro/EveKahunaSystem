from operator import itemgetter
from typing import Dict
from sqlalchemy import delete, select, text, func, distinct
from sqlalchemy.dialects.sqlite import insert as insert
import asyncio
from datetime import datetime, timedelta

from .connect_manager import database_manager as dbm
from ....utils import get_beijing_utctime

from .config_model import (
    AssetOwner,
    AssetContainer,
    Character,
    Structure,
    Matcher,
    # User,
    UserData,
    UserAssetStatistics,
    InvTypeMap,
    OrderHistory
)
from .cache_model import (
    Asset, AssetCache,
    BlueprintAsset, BlueprintAssetCache,
    IndustryJobs, IndustryJobsCache,
    SystemCost, SystemCostCache,
    MarketOrder, MarketOrderCache,
    MarketPrice, MarketPriceCache,
    MarketHistory,
    RefreshDate
)
from .model import (
    User,
    InvitCode,
    EveAuthedCharacter,
    EveAliasCharacter
)

from ...log_server import logger

"""
result.all()  # 返回所有行的列表，每行是一个元组 [(obj1,), (obj2,)]
result.first()  # 返回第一行元组 (obj1,) 或 None
result.one()  # 返回唯一一行元组 (obj1,)，如果不是恰好一行则抛出异常
result.one_or_none()  # 返回唯一一行元组 (obj1,) 或 None，如果多于一行则抛出异常
result.scalar()  # 返回第一行第一列的值 obj1 或 None
result.scalar_one()  # 返回唯一一行第一列的值 obj1，如果不是恰好一行则抛出异常
result.scalar_one_or_none()  # 返回唯一一行第一列的值 obj1 或 None，如果多于一行则抛出异常
result.partitions(size)  # 返回分批处理的迭代器，每批 size 个行元组
result.mappings().all()  # 返回所有行的字典列表 [{'col1': val1, 'col2': val2}, ...]
result.columns('col1', 'col2').all()  # 返回指定列的所有行元组 [(val1, val2), ...]

result.scalars().all()  # 返回所有行第一列的值列表 [obj1, obj2, ...]
result.scalars().first()  # 返回第一行第一列的值 obj1 或 None
result.scalars().one()  # 返回唯一一行第一列的值 obj1，如果不是恰好一行则抛出异常
result.scalars().one_or_none()  # 返回唯一一行第一列的值 obj1 或 None，如果多于一行则抛出异常
result.scalars(1).all()  # 返回所有行第二列的值列表 [val1, val2, ...]（索引从0开始）

result.fetchall()  # 等同于 all()，返回所有行的元组列表
result.fetchone()  # 等同于 first()，返回第一行元组或 None

result.keys()  # 返回结果列名列表
result.unique().all()  # 返回去重后的所有行元组列表
"""

class CommonUtils:
    cls_model = None
    @classmethod
    async def insert_many(cls, rows_list):
        """异步批量插入多条记录

        :param rows_list: 要插入的数据列表，每项是一个字典
        :return: 结果代理对象"""
        if not cls.cls_model:
            raise Exception("cls_model is None")
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = insert(cls.cls_model).values(rows_list)
                result = await session.execute(stmt)
                return result

    @classmethod
    async def insert_many_or_update_async(cls, rows_list, index_elements):
        """
        异步批量插入或更新记录

        :param rows_list: 要插入的数据列表，每项是一个字典
        :param index_elements: 唯一索引字段列表
        :return: 结果代理对象
        """
        if not cls.cls_model:
            raise Exception("cls_model is None")
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = insert(cls.cls_model).values(rows_list)

                update_dict = {c.name: c for c in stmt.excluded if c.name not in index_elements}

                stmt = stmt.on_conflict_do_update(
                    index_elements=index_elements,
                    set_=update_dict
                )

                result = await session.execute(stmt)
                return result

    @classmethod
    async def insert_many_ignore_conflict(cls, rows_list, index_elements):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = insert(cls.cls_model).values(rows_list)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=index_elements
                )
                await session.execute(stmt)

    @classmethod
    async def select_all(cls):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model)
                result = await session.execute(stmt)
                return result.scalars().all()

    @classmethod
    def get_obj(cls):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        return cls.cls_model()

    @classmethod
    async def save_obj(cls, asset_owner_obj):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                session.add(asset_owner_obj)

    @classmethod
    async def delete_all(cls):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = delete(cls.cls_model)
                await session.execute(stmt)

class CommonCacheUtils:
    cls_model = None
    cls_base_model = None

    @classmethod
    async def copy_base_to_cache(cls):
        if cls.cls_model == None or cls.cls_base_model == None:
            raise Exception("cls_model or cls_base_model is None")
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                try:
                    # 清空cache表
                    await session.execute(
                        delete(cls.cls_model)
                    )

                    # 将元数据表的数据复制到Cache表
                    table_name = cls.cls_base_model.__tablename__
                    cache_table_name = cls.cls_model.__tablename__
                    await session.execute(
                        text(f"INSERT INTO {cache_table_name} SELECT * FROM {table_name}")
                    )

                    logger.info(f"从 {table_name} 复制到 {cache_table_name} 完成。")
                except Exception as e:
                    logger.error(f"从 {table_name} 复制到 {cache_table_name} 失败。")
                    raise

class AssetDBUtils(CommonUtils):
    cls_model = Asset

    @classmethod
    async def delete_asset_by_ownerid_and_owner_type(cls, owner_id: int, owner_type: str):
        async_session = dbm.async_session(cls.cls_model)
    # M_Asset.delete().where((M_Asset.asset_type == self.owner_type) & (M_Asset.owner_id == self.owner_id)).execute()
        async with async_session() as session:
            async with session.begin():
                stmt = delete(cls.cls_model).where(
                    (cls.cls_model.asset_type == owner_type) &
                    (cls.cls_model.owner_id == owner_id)
                )
                await session.execute(stmt)

class AssetCacheDBUtils(AssetDBUtils, CommonCacheUtils):
    cls_model = AssetCache
    cls_base_model = AssetDBUtils.cls_model

    @classmethod
    async def owner_id_asset_item_count(cls, owner_id: int):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.owner_id == owner_id)
                await session.execute(stmt)

    @classmethod
    async def select_asset_by_type_id(cls, type_id: int):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.type_id == type_id)
                result = await session.execute(stmt)
                return result.scalars().all()

    @classmethod
    async def select_asset_in_container_list(cls, container_list: list):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.location_id.in_(container_list))
                result = await session.execute(stmt)
                return result.scalars().all()

    @classmethod
    async def select_one_asset_in_location_id(cls, location_id: int):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.location_id == location_id)
                result = await session.execute(stmt)
                return result.scalars().first()

    @classmethod
    async def select_one_asset_by_item_id_and_location_type(cls, item_id, param):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.item_id == item_id) &
                    (cls.cls_model.location_type == param)
                )
                result = await session.execute(stmt)
                return result.scalars().first()

    @classmethod
    async def select_father_location_by_location_id(cls, location_id):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.item_id == location_id)
                result = await session.execute(stmt)
                return result.scalars().first()


class AssetOwnerDBUtils(CommonUtils):
    cls_model = AssetOwner

    @classmethod
    async def get_all_asset_owner(cls):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model)
                result = await session.execute(stmt)
                return result.scalars().all()

    @classmethod
    async def get_asset_owner_by_owner_id_and_owner_type(cls, owner_id: int, owner_type: str):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.asset_owner_id == owner_id) &
                    (cls.cls_model.asset_type == owner_type)
                )
                result = await session.execute(stmt)
                return result.scalars().first()

class AssetContainerDBUtils(CommonUtils):
    cls_model = AssetContainer

    @classmethod
    async def select_container_by_location_id_and_owner_qq(cls, location_id: int, owner_qq: int):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.asset_location_id == location_id) &
                    (cls.cls_model.asset_owner_qq == owner_qq)
                )
                result = await session.execute(stmt)
                return result.scalars().first()

    @classmethod
    async def select_container_by_owner_qq_and_tag(cls, asset_owner_qq: int, tag: str) -> list[AssetContainer]:
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.asset_owner_qq == asset_owner_qq) &
                    (cls.cls_model.tag == tag)
                )
                result = await session.execute(stmt)
                return result.scalars().all()

class BluerprintAssetDBUtils(CommonUtils):
    cls_model = BlueprintAsset

    @classmethod
    async def delete_blueprint_asset_by_owner_id_and_owner_type(cls, owner_id: int, owner_type: str):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = delete(cls.cls_model).where(
                    (cls.cls_model.owner_type == owner_type) &
                    (cls.cls_model.owner_id == owner_id)
                )
                await session.execute(stmt)

class BluerprintAssetCacheDBUtils(BluerprintAssetDBUtils, CommonCacheUtils):
    cls_model = BlueprintAssetCache
    cls_base_model = BlueprintAsset

    @classmethod
    async def select_bpc_by_type_id_and_location_id(cls, type_id: int, location_id_list: list):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.type_id == type_id) &
                    (cls.cls_model.location_id.in_(location_id_list)) &
                    (cls.cls_model.runs > 0)
                )
                result = await session.execute(stmt)
                return result.scalars().all()

    @classmethod
    async def select_bpo_by_type_id_and_location_id(cls, type_id: int, location_id_list: list):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.type_id == type_id) &
                    (cls.cls_model.location_id.in_(location_id_list)) &
                    (cls.cls_model.runs < 0)
                )
                result = await session.execute(stmt)
                return result.scalars().all()

class CharacterDBUtils(CommonUtils):
    cls_model = Character

    @classmethod
    async def select_character_by_character_id(cls, character_id: int):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.character_id == character_id)
                result = await session.execute(stmt)
                return result.scalars().first()

class StructureDBUtils(CommonUtils):
    cls_model = Structure

    @classmethod
    async def select_structure_by_structure_id(cls, structure_id):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.structure_id == structure_id)
                result = await session.execute(stmt)
                return result.scalars().first()


class IndustryJobsDBUtils(CommonUtils):
    cls_model = IndustryJobs

    @classmethod
    async def delete_jobs_by_owner_id(cls, character_id):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = delete(cls.cls_model).where(cls.cls_model.owner_id == character_id)
                await session.execute(stmt)


class IndustryJobsCacheDBUtils(IndustryJobsDBUtils, CommonCacheUtils):
    cls_model = IndustryJobsCache
    cls_base_model = IndustryJobs

    @classmethod
    async def select_jobs_by_installer_id_list(cls, character_id_list) -> list[IndustryJobsCache]:
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.installer_id.in_(character_id_list))
                result = await session.execute(stmt)
                return result.scalars().all()

    @classmethod
    async def select_jobs_by_installer_id_and_type(cls, character_id: int, activity_id: int):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.installer_id == character_id) &
                    (cls.cls_model.activity_id == activity_id)
                )
                result = await session.execute(stmt)
                return result.scalars().all()


class InvTypeMapDBUtils(CommonUtils):
    cls_model = InvTypeMap

class SystemCostDBUtils(CommonUtils):
    cls_model = SystemCost

class SystemCostCacheDBUtils(SystemCostDBUtils, CommonCacheUtils):
    cls_model = SystemCostCache
    cls_base_model = SystemCost

    @classmethod
    async def select_system_cost_by_id(cls, solar_system_id) -> SystemCostCache:
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.solar_system_id == solar_system_id)
                result = await session.execute(stmt)
                return result.scalars().first()

class MarkerOrderDBUtils(CommonUtils):
    cls_model = MarketOrder

    @classmethod
    async def delete_order_by_location_id(cls, FRT_4H_STRUCTURE_ID):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = delete(cls.cls_model).where(cls.cls_model.location_id == FRT_4H_STRUCTURE_ID)
                await session.execute(stmt)

    @classmethod
    async def delete_order_by_type_id(cls, typeid):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = delete(cls.cls_model).where(cls.cls_model.type_id == typeid)
                await session.execute(stmt)

class MarketOrderCacheDBUtils(MarkerOrderDBUtils, CommonCacheUtils):
    cls_model = MarketOrderCache
    cls_base_model = MarketOrder

    @classmethod
    async def select_order_by_location_id(cls, location_id: int):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.location_id == location_id)
                result = await session.execute(stmt)
                return result.scalars().all()

    @classmethod
    async def select_order_count_by_location_id(cls, target_location):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(func.count(cls.cls_model.location_id)).where(cls.cls_model.location_id == target_location)
                result = await session.execute(stmt)
                return result.scalar()

    @classmethod
    async def select_buy_order_count_by_location_id(cls, target_location: int) -> int:
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(func.count(cls.cls_model.location_id)).where(
                    (cls.cls_model.location_id == target_location) &
                    (cls.cls_model.is_buy_order == True)
                )
                result = await session.execute(stmt)
                return result.scalar()

    @classmethod
    async def select_sell_order_count_by_location_id(cls, target_location):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(func.count(cls.cls_model.location_id)).where(
                    (cls.cls_model.location_id == target_location) &
                    (cls.cls_model.is_buy_order == False)
                )
                result = await session.execute(stmt)
                return result.scalar()

    @classmethod
    async def select_distinct_type_count_by_location_id(cls, target_location):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                # 使用func.count和distinct组合，一步完成计数
                stmt = select(func.count(func.distinct(cls.cls_model.type_id))).where(
                    cls.cls_model.location_id == target_location
                )
                result = await session.execute(stmt)
                return result.scalar()

    @classmethod
    async def select_max_buy_by_type_id_and_location_id(cls, target_id, target_location=None):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                if target_location:
                    stmt = select(func.max(cls.cls_model.price)).where(
                        (cls.cls_model.type_id == target_id) &
                        (cls.cls_model.location_id == target_location) &
                        (cls.cls_model.is_buy_order == True)
                    )
                else:
                    stmt = select(func.max(cls.cls_model.price)).where(
                        (cls.cls_model.type_id == target_id) &
                        (cls.cls_model.is_buy_order == True)
                    )
                result = await session.execute(stmt)
                return result.scalar()

    @classmethod
    async def select_min_sell_by_type_id_and_location_id(cls, target_id, target_location=None):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                if target_location:
                    stmt = select(func.min(cls.cls_model.price)).where(
                        (cls.cls_model.type_id == target_id) &
                        (cls.cls_model.location_id == target_location) &
                        (cls.cls_model.is_buy_order == False)
                    )
                else:
                    stmt = select(func.min(cls.cls_model.price)).where(
                        (cls.cls_model.type_id == target_id) &
                        (cls.cls_model.is_buy_order == False)
                    )
                result = await session.execute(stmt)
                return result.scalar()

    @classmethod
    async def select_5_buy_order_by_type_id_and_location_id(cls, type_id, target_location):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.type_id == type_id) &
                    (cls.cls_model.location_id == target_location) &
                    (cls.cls_model.is_buy_order == True)
                ).order_by(cls.cls_model.price.desc()).limit(5)
                result = await session.execute(stmt)
                return result.scalars().all()

    @classmethod
    async def select_5_sell_order_by_type_id_and_location_id(cls, type_id, target_location):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.type_id == type_id) &
                    (cls.cls_model.location_id == target_location) &
                    (cls.cls_model.is_buy_order == False)
                ).order_by(cls.cls_model.price.asc()).limit(5)
                result = await session.execute(stmt)
                return result.scalars().all()

    @classmethod
    async def select_5_buy_order_by_type_id(cls, type_id):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.type_id == type_id) &
                    (cls.cls_model.is_buy_order == True)
                ).order_by(cls.cls_model.price.desc()).limit(5)
                result = await session.execute(stmt)
                return result.scalars().all()

    @classmethod
    async def select_5_sell_order_by_type_id(cls, type_id):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.type_id == type_id) &
                    (cls.cls_model.is_buy_order == False)
                ).order_by(cls.cls_model.price.asc()).limit(5)
                result = await session.execute(stmt)
                return result.scalars().all()

class MarketPriceDBUtils(CommonUtils):
    cls_model = MarketPrice

class MarketPriceCacheDBUtils(MarketPriceDBUtils, CommonCacheUtils):
    cls_model = MarketPriceCache
    cls_base_model = MarketPrice

    @classmethod
    async def select_market_price_by_type_id(cls, type_id) -> MarketPriceCache:
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.type_id == type_id)
                result = await session.execute(stmt)
                return result.scalars().first()

class MarketHistoryDBUtils(CommonUtils):
    cls_model = MarketHistory

    @classmethod
    async def insert_many_ignore_conflict(cls, rows_list):
        await super().insert_many_ignore_conflict(rows_list, ['region_id', 'type_id', 'date'])

    @classmethod
    async def select_order_history_by_type_id_and_region_id(cls, type_id, region_id):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.type_id == type_id) &
                    (cls.cls_model.region_id == region_id)
                ).order_by(cls.cls_model.date.desc())
                result = await session.execute(stmt)
                return result.scalars().all()

    @classmethod
    async def select_order_history_before_date_by_type_id_and_region_id(cls, week_ago, type_id, REGION_VALE_ID):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.type_id == type_id) &
                    (cls.cls_model.region_id == REGION_VALE_ID) &
                    (cls.cls_model.date >= week_ago)
                ).order_by(cls.cls_model.date.desc())
                result = await session.execute(stmt)
                return result.scalars().all()


class MatcherDBUtils(CommonUtils):
    cls_model = Matcher

    @classmethod
    async def select_matcher_by_name(cls, matcher_name: str):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.matcher_name == matcher_name)
                result = await session.execute(stmt)
                return result.scalars().first()

    @classmethod
    async def delete_matcher_by_name(cls, matcher_name):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = delete(cls.cls_model).where(cls.cls_model.matcher_name == matcher_name)
                await session.execute(stmt)


class RefreshDataDBUtils(CommonUtils):
    cls_model = RefreshDate


    @classmethod
    async def create_refresh_date(cls, id: str):
        """
        创建或更新刷新日期记录

        Args:
            id: 记录的唯一标识符

        Returns:
            RefreshDate: 创建或更新的刷新日期记录
        """
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                try:
                    refresh_date = get_beijing_utctime(datetime.now())
                    # 尝试查找是否已存在该id的记录
                    # existing_record = cls.model.get_or_none(cls.model.id == id)
                    stmt = select(cls.cls_model).where(cls.cls_model.id == id)
                    result = await session.execute(stmt)
                    existing_record = result.scalars().first()

                    if existing_record:
                        # 如果记录存在，更新刷新日期
                        existing_record.date = refresh_date
                        session.add(existing_record)
                        return existing_record
                    else:
                        # 如果记录不存在，创建新记录
                        # new_record = cls.model.create(id=id, date=refresh_date)
                        new_record = cls.get_obj()
                        new_record.id = id
                        new_record.date = refresh_date
                        session.add(new_record)
                        return new_record
                except Exception as e:
                    # 处理可能发生的异常
                    logger.error(f"创建或更新刷新日期记录时发生错误: {e}")
                    raise

    @classmethod
    async def out_of_min_interval(cls, id: str, time_interval_min: int):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                try:
                    time_interval = timedelta(minutes=time_interval_min)

                    stmt = select(cls.cls_model).where(cls.cls_model.id == id)
                    result = await session.execute(stmt)
                    refresh_date = result.scalars().first()
                    if not refresh_date:
                        return True
                    # logger.info(f"now - refresh_date: {get_beijing_utctime(datetime.now()) - refresh_date.date}")
                    return get_beijing_utctime(datetime.now()) - refresh_date.date > time_interval
                except Exception as e:
                    logger.error(e)
                    raise

    @classmethod
    async def out_of_day_interval(cls, id: str, time_interval_day: int):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                try:
                    stmt = select(cls.cls_model).where(cls.cls_model.id == id)
                    result = await session.execute(stmt)
                    refresh_date = result.scalars().first()
                    if not refresh_date:
                        return True
                    # 获取当前北京时间
                    current_date = get_beijing_utctime(datetime.now()).date()
                    # 获取上次刷新的日期部分
                    last_refresh_date = refresh_date.date.date()

                    # 计算日期差
                    days_diff = (current_date - last_refresh_date).days

                    # 判断是否超过指定的天数间隔
                    return days_diff >= time_interval_day
                except Exception as e:
                    logger.error(e)
                    raise

    @classmethod
    async def out_of_hour_interval(cls, id: str, time_interval_hour: int):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                try:
                    stmt = select(cls.cls_model).where(cls.cls_model.id == id)
                    result = await session.execute(stmt)
                    refresh_date = result.scalars().first()
                    if not refresh_date:
                        return True

                    # 获取当前北京时间
                    current_time = get_beijing_utctime(datetime.now())
                    # 获取上次刷新的时间
                    last_refresh_time = refresh_date.date

                    # 如果是不同的日期，直接计算完整的小时差
                    if current_time.date() != last_refresh_time.date():
                        # 计算天数差
                        days_diff = (current_time.date() - last_refresh_time.date()).days
                        # 计算小时差
                        hour_diff = current_time.hour + (24 - last_refresh_time.hour) + (days_diff - 1) * 24
                    else:
                        # 同一天，直接比较小时部分
                        hour_diff = current_time.hour - last_refresh_time.hour

                    # 判断是否超过指定的小时间隔
                    return hour_diff >= time_interval_hour
                except Exception as e:
                    logger.error(e)
                    raise

    @classmethod
    async def update_refresh_date(cls, id: str, log: bool = True):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                # refresh_date = get_beijing_utctime(datetime.now())
                # cls.model.update(date=refresh_date).where(cls.model.id == id).execute()
                stmt = select(cls.cls_model).where(cls.cls_model.id == id)
                result = await session.execute(stmt)
                refresh_date = result.scalars().first()
                if not refresh_date:
                    await cls.create_refresh_date(id)
                    return

                if not refresh_date:
                    refresh_date = cls.get_obj()
                    refresh_date.id = id
                refresh_date.date = get_beijing_utctime(datetime.now())
                session.add(refresh_date)
                if log:
                    logger.info(f'缓存标志 {id} 刷新时间到 {refresh_date.date}')

class UserDBUtils(CommonUtils):
    cls_model = User

    @classmethod
    async def select_user_by_user_qq(cls, user_qq):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.user_qq == user_qq)
                result = await session.execute(stmt)
                return result.scalars().first()

    @classmethod
    async def delete_user_by_user_qq(cls, user_qq):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = delete(cls.cls_model).where(cls.cls_model.user_qq == user_qq)
                await session.execute(stmt)

class UserDataDBUtils(CommonUtils):
    cls_model = UserData

    @classmethod
    async def select_user_data_by_user_qq(cls, user_qq: int):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.user_qq == user_qq)
                result = await session.execute(stmt)
                return result.scalars().first()


class UserAssetStatisticsDBUtils(CommonUtils):
    cls_model = UserAssetStatistics

    @classmethod
    async def update(cls, user_qq, date, asset_data: dict):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(
                    (cls.cls_model.user_qq == user_qq) &
                    (cls.cls_model.date == date)
                )
                result = await session.execute(stmt)
                existing_record = result.scalars().first()
                if not existing_record:
                    existing_record = cls.get_obj()
                existing_record.user_qq = user_qq
                existing_record.date = date
                existing_record.asset_statistics = asset_data
                session.add(existing_record)

    @classmethod
    async def get_user_asset_statistics(cls, user_qq):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.user_qq == user_qq)
                result = await session.execute(stmt)
                return result.scalars().all()

class OrderHistoryDBUtils(CommonUtils):
    cls_model = OrderHistory

    @classmethod
    async def insert_many_ignore_conflict(cls, rows_list):
        await super().insert_many_ignore_conflict(rows_list, ['order_id', 'owner_id'])

    @classmethod
    async def select_order_history_by_owner_id_list(cls, param):
        async_session = dbm.async_session(cls.cls_model)
        async with async_session() as session:
            async with session.begin():
                stmt = select(cls.cls_model).where(cls.cls_model.owner_id.in_(param))
                result = await session.execute(stmt)
                return result.scalars().all()
