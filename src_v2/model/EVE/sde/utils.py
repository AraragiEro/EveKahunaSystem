import asyncio
import traceback
import networkx as nx
from thefuzz import fuzz, process
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from aiocache import cached
from aiocache.serializers import PickleSerializer
import traceback

from src_v2.model.EVE.sde.sde_builder.database_manager import get_sde_database_manager as sde_database_manager
from .sde_builder import (
    InvTypes,
    InvGroups,
    InvCategories,
    MapSolarSystems,
    MapRegions,
    IndustryBlueprints,
    MetaGroups,
    MarketGroups,
    TypeMaterials,
)
from src_v2.core.log import logger
from src_v2.core.database.connect_manager import get_neo4j_manager as neo4j_manager

# 数据库管理器单例
class LockManager():
    def __init__(self):
        self.init_lock = asyncio.Lock()
        self.invtype_name_list_lock = asyncio.Lock()
        self.invgroup_name_list_lock = asyncio.Lock()
        self.meta_name_list_lock = asyncio.Lock()
        self.blueprint_name_list_lock = asyncio.Lock()
        self.market_group_name_list_lock = asyncio.Lock()
        self.category_name_list_lock = asyncio.Lock()

    def reset_lock(self):
        self.init_lock = asyncio.Lock()
        self.invtype_name_list_lock = asyncio.Lock()
        self.invgroup_name_list_lock = asyncio.Lock()
        self.meta_name_list_lock = asyncio.Lock()
        self.blueprint_name_list_lock = asyncio.Lock()
        self.market_group_name_list_lock = asyncio.Lock()
        self.category_name_list_lock = asyncio.Lock()
lock_manager = LockManager()

# 数据列表缓存（将在后续步骤中改为异步加载）
_en_invtype_name_list: Optional[List[str]] = None
_zh_invtype_name_list: Optional[List[str]] = None
_en_invgroup_name_list: Optional[List[str]] = None
_zh_invgroup_name_list: Optional[List[str]] = None
_en_meta_name_list: Optional[List[str]] = None
_zh_meta_name_list: Optional[List[str]] = None
_en_blueprint_name_list: Optional[List[str]] = None
_zh_blueprint_name_list: Optional[List[str]] = None
_en_market_group_name_list: Optional[List[str]] = None
_zh_market_group_name_list: Optional[List[str]] = None
_en_category_name_list: Optional[List[str]] = None
_zh_category_name_list: Optional[List[str]] = None


async def get_db_manager():
    """获取数据库管理器单例
    
    Args:
        subprocess: 是否为子进程模式，子进程模式下使用更小的连接池
    """
    return sde_database_manager()


class SdeUtils:
    _market_tree = None
    item_map_dict = dict()

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def _get_invtype_name_list(zh: bool = False) -> List[str]:
        """获取物品类型名称列表（用于模糊搜索）"""
        global _en_invtype_name_list, _zh_invtype_name_list
        result_list = _zh_invtype_name_list if zh else _en_invtype_name_list
        if result_list is not None:
            return result_list
        
        async with lock_manager.invtype_name_list_lock:
            # 双重检查
            result_list = _zh_invtype_name_list if zh else _en_invtype_name_list
            if result_list is not None:
                return result_list
            
            async with (await get_db_manager()).get_readonly_session() as session:
                if zh:
                    stmt = select(InvTypes.typeName_zh).where(InvTypes.marketGroupID.isnot(None))
                    result = await session.execute(stmt)
                    _zh_invtype_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _zh_invtype_name_list
                else:
                    stmt = select(InvTypes.typeName_en).where(InvTypes.marketGroupID.isnot(None))
                    result = await session.execute(stmt)
                    _en_invtype_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _en_invtype_name_list

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def _get_invgroup_name_list(zh: bool = False) -> List[str]:
        """获取组名称列表（用于模糊搜索）"""
        global _en_invgroup_name_list, _zh_invgroup_name_list
        result_list = _zh_invgroup_name_list if zh else _en_invgroup_name_list
        if result_list is not None:
            return result_list
        
        async with lock_manager.invgroup_name_list_lock:
            # 双重检查
            result_list = _zh_invgroup_name_list if zh else _en_invgroup_name_list
            if result_list is not None:
                return result_list
            
            async with (await get_db_manager()).get_readonly_session() as session:
                if zh:
                    stmt = select(InvGroups.groupName_zh)
                    result = await session.execute(stmt)
                    _zh_invgroup_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _zh_invgroup_name_list
                else:
                    stmt = select(InvGroups.groupName_en)
                    result = await session.execute(stmt)
                    _en_invgroup_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _en_invgroup_name_list

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def _get_meta_name_list(zh: bool = False) -> List[str]:
        """获取 meta 名称列表（用于模糊搜索）"""
        global _en_meta_name_list, _zh_meta_name_list
        result_list = _zh_meta_name_list if zh else _en_meta_name_list
        if result_list is not None:
            return result_list
        
        async with lock_manager.meta_name_list_lock:
            # 双重检查
            result_list = _zh_meta_name_list if zh else _en_meta_name_list
            if result_list is not None:
                return result_list
            
            async with (await get_db_manager()).get_readonly_session() as session:
                if zh:
                    stmt = select(MetaGroups.nameID_zh)
                    result = await session.execute(stmt)
                    _zh_meta_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _zh_meta_name_list
                else:
                    stmt = select(MetaGroups.nameID_en)
                    result = await session.execute(stmt)
                    _en_meta_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _en_meta_name_list

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def _get_blueprint_name_list(zh: bool = False) -> List[str]:
        """获取蓝图名称列表（用于模糊搜索）"""
        global _en_blueprint_name_list, _zh_blueprint_name_list
        result_list = _zh_blueprint_name_list if zh else _en_blueprint_name_list
        if result_list is not None:
            return result_list
        
        async with lock_manager.blueprint_name_list_lock:
            # 双重检查
            result_list = _zh_blueprint_name_list if zh else _en_blueprint_name_list
            if result_list is not None:
                return result_list
            
            async with (await get_db_manager()).get_readonly_session() as session:
                if zh:
                    name_field = InvTypes.typeName_zh
                    stmt = (
                        select(name_field)
                        .select_from(IndustryBlueprints)
                        .join(InvTypes, IndustryBlueprints.blueprintTypeID == InvTypes.typeID)
                        .where(InvTypes.marketGroupID.isnot(None))
                    )
                    result = await session.execute(stmt)
                    _zh_blueprint_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _zh_blueprint_name_list
                else:
                    name_field = InvTypes.typeName_en
                    stmt = (
                        select(name_field)
                        .select_from(IndustryBlueprints)
                        .join(InvTypes, IndustryBlueprints.blueprintTypeID == InvTypes.typeID)
                        .where(InvTypes.marketGroupID.isnot(None))
                    )
                    result = await session.execute(stmt)
                    _en_blueprint_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _en_blueprint_name_list

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def _get_market_group_name_list(zh: bool = False) -> List[str]:
        """获取市场组名称列表（用于模糊搜索）"""
        global _en_market_group_name_list, _zh_market_group_name_list
        result_list = _zh_market_group_name_list if zh else _en_market_group_name_list
        if result_list is not None:
            return result_list
        
        async with lock_manager.market_group_name_list_lock:
            # 双重检查
            result_list = _zh_market_group_name_list if zh else _en_market_group_name_list
            if result_list is not None:
                return result_list
            
            async with (await get_db_manager()).get_readonly_session() as session:
                if zh:
                    stmt = select(MarketGroups.nameID_zh)
                    result = await session.execute(stmt)
                    _zh_market_group_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _zh_market_group_name_list
                else:
                    stmt = select(MarketGroups.nameID_en)
                    result = await session.execute(stmt)
                    _en_market_group_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _en_market_group_name_list

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def _get_category_name_list(zh: bool = False) -> List[str]:
        """获取类别名称列表（用于模糊搜索）"""
        global _en_category_name_list, _zh_category_name_list
        result_list = _zh_category_name_list if zh else _en_category_name_list
        if result_list is not None:
            return result_list
        
        async with lock_manager.category_name_list_lock:
            # 双重检查
            result_list = _zh_category_name_list if zh else _en_category_name_list
            if result_list is not None:
                return result_list
            
            async with (await get_db_manager()).get_readonly_session() as session:
                if zh:
                    stmt = select(InvCategories.categoryName_zh)
                    result = await session.execute(stmt)
                    _zh_category_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _zh_category_name_list
                else:
                    stmt = select(InvCategories.categoryName_en)
                    result = await session.execute(stmt)
                    _en_category_name_list = [row[0] for row in result if row[0] is not None] or []
                    return _en_category_name_list

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_t2_ship(zh: bool = False) -> List[str]:
        """获取所有 T2 舰船名称列表"""
        async with (await get_db_manager()).get_readonly_session() as session:
            # name_field = InvTypes.typeName_zh if zh else InvTypes.typeName_en
            category_name_field = InvCategories.categoryName_zh if zh else InvCategories.categoryName_en
            meta_name_field = MetaGroups.nameID_zh if zh else MetaGroups.nameID_en
            
            stmt = (
                select(InvTypes.typeID)
                .select_from(InvTypes)
                .join(InvGroups, InvTypes.groupID == InvGroups.groupID)
                .join(InvCategories, InvGroups.categoryID == InvCategories.categoryID)
                .join(MetaGroups, InvTypes.metaGroupID == MetaGroups.metaGroupID)
                .where(category_name_field == ("舰船" if zh else "Ship"))
                .where(InvTypes.marketGroupID.isnot(None))
                .where(meta_name_field == ("二级科技" if zh else "Tech II"))
            )
            result = await session.execute(stmt)
            return [row[0] for row in result if row[0] is not None]

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_battleship(zh: bool = False) -> List[str]:
        """获取所有战列舰名称列表"""
        # 先获取所有数据，避免在会话内嵌套调用其他数据库方法
        ship_data = []
        async with (await get_db_manager()).get_readonly_session() as session:
            name_field = InvTypes.typeName_zh if zh else InvTypes.typeName_en
            category_name_field = InvCategories.categoryName_zh if zh else InvCategories.categoryName_en
            
            stmt = (
                select(InvTypes.typeID, name_field)
                .select_from(InvTypes)
                .join(InvGroups, InvTypes.groupID == InvGroups.groupID)
                .join(InvCategories, InvGroups.categoryID == InvCategories.categoryID)
                .where(category_name_field == ("舰船" if zh else "Ship"))
            )
            result = await session.execute(stmt)
            
            for row in result:
                ship_data.append((row.typeID, row[1]))  # (type_id, type_name)
        
        # 在会话外调用 get_market_group_list，避免嵌套会话
        battleship_list = []
        target_name = "战列舰" if zh else "Battleships"
        for type_id, type_name in ship_data:
            market_list = await SdeUtils.get_market_group_list(type_id, zh=zh)
            if target_name in market_list:
                battleship_list.append(type_name)
        
        return battleship_list

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_capital_ship(zh: bool = False) -> List[str]:
        """获取所有旗舰名称列表"""
        # 先获取所有数据，避免在会话内嵌套调用其他数据库方法
        ship_data = []
        async with (await get_db_manager()).get_readonly_session() as session:
            name_field = InvTypes.typeName_zh if zh else InvTypes.typeName_en
            category_name_field = InvCategories.categoryName_zh if zh else InvCategories.categoryName_en
            
            stmt = (
                select(InvTypes.typeID, name_field)
                .select_from(InvTypes)
                .join(InvGroups, InvTypes.groupID == InvGroups.groupID)
                .join(InvCategories, InvGroups.categoryID == InvCategories.categoryID)
                .where(category_name_field == ("舰船" if zh else "Ship"))
            )
            result = await session.execute(stmt)
            
            for row in result:
                ship_data.append((row.typeID, row[1]))  # (type_id, type_name)
        
        # 在会话外调用 get_market_group_list，避免嵌套会话
        capital_ship_list = []
        target_name = "旗舰" if zh else "Capital Ships"
        for type_id, type_name in ship_data:
            market_list = await SdeUtils.get_market_group_list(type_id, zh=zh)
            if target_name in market_list:
                capital_ship_list.append(type_name)
        
        # 移除特定物品
        exclude_items = ["Venerable", "Vanguard"] if not zh else ["可敬级", "先锋级"]
        for item in exclude_items:
            if item in capital_ship_list:
                capital_ship_list.remove(item)
        
        return capital_ship_list

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_groupname_by_id(invtpye_id: int, zh: bool = False, pdm = None) -> Optional[str]:
        """根据 typeID 获取组名称"""
        try:
            if pdm:
                m = pdm
            else:
                m = await get_db_manager()
            async with m.get_readonly_session() as session:
                group_name_field = InvGroups.groupName_zh if zh else InvGroups.groupName_en
                stmt = (
                    select(group_name_field)
                    .select_from(InvTypes)
                    .join(InvGroups, InvTypes.groupID == InvGroups.groupID)
                    .where(InvTypes.typeID == invtpye_id)
                )
                result = await session.execute(stmt)
                return result.scalar()
        except Exception as e:
            task = asyncio.current_task()
            traceback.print_stack(task)
            logger.warning(f"获取 type_id={invtpye_id} 的组名称时出错: {e}")
            return None

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_groupid_by_groupname(group_name: str) -> Optional[int]:
        """根据组名称获取 groupID"""
        try:
            async with (await get_db_manager()).get_readonly_session() as session:
                is_zh = SdeUtils.maybe_chinese(group_name)
                group_name_field = InvGroups.groupName_zh if is_zh else InvGroups.groupName_en
                stmt = select(InvGroups.groupID).where(group_name_field == group_name)
                result = await session.execute(stmt)
                return result.scalar()
        except Exception as e:
            logger.warning(f"获取 group_name={group_name} 的 groupID 时出错: {e}")
            return None

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_invtpye_node_by_id(invtpye_id: int):
        """根据 typeID 获取 InvTypes 对象"""
        try:
            async with (await get_db_manager()).get_readonly_session() as session:
                stmt = select(InvTypes).where(InvTypes.typeID == invtpye_id)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            logger.warning(f"获取 type_id={invtpye_id} 的 InvTypes 对象时出错: {e}")
            return None

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_invtype_packagedvolume_by_id(invtpye_id: int) -> float:
        """根据 typeID 获取 packagedVolume"""
        try:
            async with (await get_db_manager()).get_readonly_session() as session:
                stmt = select(InvTypes.packagedVolume).where(InvTypes.typeID == invtpye_id)
                result = await session.execute(stmt)
                volume = result.scalar()
                return volume if volume is not None else 0.0
        except Exception as e:
            logger.warning(f"获取 type_id={invtpye_id} 的 packagedVolume 时出错: {e}")
            return 0.0

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_metaname_by_metaid(meta_id: int, zh: bool = False) -> Optional[str]:
        """根据 metaGroupID 获取 meta 名称"""
        try:
            async with (await get_db_manager()).get_readonly_session() as session:
                name_field = MetaGroups.nameID_zh if zh else MetaGroups.nameID_en
                stmt = select(name_field).where(MetaGroups.metaGroupID == meta_id)
                result = await session.execute(stmt)
                return result.scalar()
        except Exception as e:
            logger.warning(f"获取 meta_id={meta_id} 的 meta 名称时出错: {e}")
            return None

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_metaname_by_typeid(typeid: int, zh: bool = False, pdm = None) -> Optional[str]:
        """根据 typeID 获取 meta 名称"""
        try:
            if pdm:
                m = pdm
            else:
                m = await get_db_manager()
            async with m.get_readonly_session() as session:
                name_field = MetaGroups.nameID_zh if zh else MetaGroups.nameID_en
                stmt = (
                    select(name_field)
                    .select_from(InvTypes)
                    .join(MetaGroups, InvTypes.metaGroupID == MetaGroups.metaGroupID)
                    .where(InvTypes.typeID == typeid)
                )
                result = await session.execute(stmt)
                return result.scalar()
        except Exception as e:
            logger.warning(f"获取 type_id={typeid} 的 meta 名称时出错: {e}")
            return None

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_metadid_by_metaname(meta_name: str) -> Optional[int]:
        """根据 meta 名称获取 metaGroupID"""
        try:
            async with (await get_db_manager()).get_readonly_session() as session:
                is_zh = SdeUtils.maybe_chinese(meta_name)
                name_field = MetaGroups.nameID_zh if is_zh else MetaGroups.nameID_en
                stmt = select(MetaGroups.metaGroupID).where(name_field == meta_name)
                result = await session.execute(stmt)
                return result.scalar()
        except Exception as e:
            logger.warning(f"获取 meta_name={meta_name} 的 metaGroupID 时出错: {e}")
            return None

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_id_by_name(name: str) -> Optional[int]:
        """根据物品名称获取 typeID"""
        try:
            async with (await get_db_manager()).get_readonly_session() as session:
                is_zh = SdeUtils.maybe_chinese(name)
                name_field = InvTypes.typeName_zh if is_zh else InvTypes.typeName_en
                stmt = select(InvTypes.typeID).where(name_field == name)
                result = await session.execute(stmt)
                return result.scalar()
        except Exception as e:
            logger.warning(f"获取 name={name} 的 typeID 时出错: {e}")
            return None

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_name_by_id(type_id: int, zh: bool = False, pdm = None) -> Optional[str]:
        """根据 typeID 获取物品名称"""
        try:
            if pdm:
                m = pdm
            else:
                m = await get_db_manager()
            async with m.get_readonly_session() as session:
                name_field = InvTypes.typeName_zh if zh else InvTypes.typeName_en
                stmt = select(name_field).where(InvTypes.typeID == type_id)
                result = await session.execute(stmt)
                return result.scalar()
        except Exception as e:
            # 捕获其他可能的异常，避免程序崩溃
            logger.warning(f"获取 type_id={type_id} 的名称时出错: {e}")
            return None

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_id_by_cn_name(name: str) -> Optional[int]:
        """根据中文名称获取 typeID（向后兼容方法）"""
        return await SdeUtils.get_id_by_name(name)

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_cn_name_by_id(type_id: int, pdm = None) -> Optional[str]:
        """根据 typeID 获取中文名称（向后兼容方法）"""
        return await SdeUtils.get_name_by_id(type_id, zh=True, pdm=pdm)

    @classmethod
    async def get_market_group_tree(cls, sdm=None):
        """获取市场组树（NetworkX 图）"""
        if not cls._market_tree:
            g = nx.DiGraph()
            if sdm:
                m = sdm
            else:
                m = await get_db_manager()
            async with m.get_readonly_session() as session:
                stmt = select(MarketGroups.marketGroupID, MarketGroups.parentGroupID)
                result = await session.execute(stmt)
                for row in result:
                    g.add_node(row.marketGroupID)
                    if row.parentGroupID:
                        g.add_node(row.parentGroupID)
                        g.add_edge(row.parentGroupID, row.marketGroupID)
            cls._market_tree = g
        return cls._market_tree

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_market_group_name_by_groupid(market_group_id: int, zh: bool = False) -> Optional[str]:
        """根据 marketGroupID 获取市场组名称"""
        try:
            async with (await get_db_manager()).get_readonly_session() as session:
                name_field = MarketGroups.nameID_zh if zh else MarketGroups.nameID_en
                stmt = select(name_field).where(MarketGroups.marketGroupID == market_group_id)
                result = await session.execute(stmt)
                return result.scalar()
        except Exception as e:
            logger.warning(f"获取 market_group_id={market_group_id} 的市场组名称时出错: {e}")
            return None

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_market_groupid_by_name(market_group_name: str) -> Optional[int]:
        """根据市场组名称获取 marketGroupID"""
        try:
            async with (await get_db_manager()).get_readonly_session() as session:
                is_zh = SdeUtils.maybe_chinese(market_group_name)
                name_field = MarketGroups.nameID_zh if is_zh else MarketGroups.nameID_en
                stmt = select(MarketGroups.marketGroupID).where(name_field == market_group_name)
                result = await session.execute(stmt)
                return result.scalar()
        except Exception as e:
            logger.warning(f"获取 market_group_name={market_group_name} 的 marketGroupID 时出错: {e}")
            return None

    @classmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_market_group_list(cls, type_id: int, zh: bool = False, pdm = None) -> List[str]:
        """根据 typeID 获取市场组列表（从根到叶子）"""
        try:
            # 在打开数据库会话之前先获取市场组树，避免嵌套会话
            # 如果缓存已存在，不会创建新的数据库会话
            market_tree = await cls.get_market_group_tree(sdm=pdm)
            
            if pdm:
                m = pdm
            else:
                m = await get_db_manager()
            async with m.get_readonly_session() as session:
                # 获取物品信息和市场组ID
                type_name_field = InvTypes.typeName_zh if zh else InvTypes.typeName_en
                stmt = select(InvTypes.marketGroupID, type_name_field).where(InvTypes.typeID == type_id)
                result = await session.execute(stmt)
                row = result.first()
                
                if not row or row.marketGroupID is None:
                    return []
                
                market_group_id = row.marketGroupID
                type_name = row[1]  # type_name_field
                
                # 获取当前市场组名称
                market_group_name_field = MarketGroups.nameID_zh if zh else MarketGroups.nameID_en
                stmt = select(market_group_name_field).where(MarketGroups.marketGroupID == market_group_id)
                result = await session.execute(stmt)
                current_group_name = result.scalar()
                
                if not current_group_name:
                    return []
                
                market_group_list = [type_name, current_group_name]
                
                # 遍历父节点
                parent_nodes = list(market_tree.predecessors(market_group_id))
                while parent_nodes:
                    parent_node = parent_nodes[0]
                    stmt = select(market_group_name_field).where(MarketGroups.marketGroupID == parent_node)
                    result = await session.execute(stmt)
                    parent_name = result.scalar()
                    if parent_name:
                        market_group_list.append(parent_name)
                    parent_nodes = list(market_tree.predecessors(parent_node))
                
                market_group_list.reverse()
                return market_group_list
        except Exception as e:
            task = asyncio.current_task()
            traceback.print_stack(task)
            logger.warning(f"获取 type_id={type_id} 的市场组列表时出错: {e}")
            return []

        # market_group_id = cls.get_invtpye_node_by_id(type_id).marketGroupID
        # market_group_list = [cls.get_name_by_id(type_id), cls.get_market_group_name(market_group_id)]
        # while True:
        #     parent_id = MarketGroups.get_or_none(MarketGroups.marketGroupID == market_group_id)
        #     parent_id = parent_id.parentGroupID
        #     if not parent_id:
        #         market_group_list.reverse()
        #         return market_group_list
        #     parent_name = cls.get_market_group_name(parent_id)
        #     market_group_list.append(parent_name)
        #     market_group_id = parent_id


    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_category_by_id(type_id: int, zh: bool = False, pdm = None) -> Optional[str]:
        """根据 typeID 获取类别名称"""
        try:
            if pdm:
                m = pdm
            else:
                m = await get_db_manager()
            async with m.get_readonly_session() as session:
                category_name_field = InvCategories.categoryName_zh if zh else InvCategories.categoryName_en
                stmt = (
                    select(category_name_field)
                    .select_from(InvTypes)
                    .join(InvGroups, InvTypes.groupID == InvGroups.groupID)
                    .join(InvCategories, InvGroups.categoryID == InvCategories.categoryID)
                    .where(InvTypes.typeID == type_id)
                )
                result = await session.execute(stmt)
                return result.scalar()
        except Exception as e:
            logger.warning(f"获取 type_id={type_id} 的类别名称时出错: {e}")
            return None

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_system_info_by_id(system_id: int, zh: bool = False, pdm = None) -> Optional[dict]:
        """根据 systemID 获取星系信息"""
        try:
            if pdm:
                m = pdm
            else:
                m = await get_db_manager()
            async with m.get_readonly_session() as session:
                system_name_field = MapSolarSystems.solarSystemName_zh if zh else MapSolarSystems.solarSystemName_en
                region_name_field = MapRegions.regionName_zh if zh else MapRegions.regionName_en
                
                stmt = (
                    select(
                        system_name_field.label('system_name'),
                        MapSolarSystems.solarSystemID.label('system_id'),
                        MapSolarSystems.regionID.label('region_id'),
                        region_name_field.label('region_name'),
                        MapSolarSystems.x.label('x'),
                        MapSolarSystems.y.label('y'),
                        MapSolarSystems.z.label('z')
                    )
                    .select_from(MapSolarSystems)
                    .join(MapRegions, MapSolarSystems.regionID == MapRegions.regionID)
                    .where(MapSolarSystems.solarSystemID == system_id)
                )
                result = await session.execute(stmt)
                row = result.first()
                if row:
                    return {
                        'system_name': row.system_name,
                        'system_id': row.system_id,
                        'region_id': row.region_id,
                        'region_name': row.region_name,
                        'x': row.x,
                        'y': row.y,
                        'z': row.z
                    }
                return None
        except Exception as e:
            logger.warning(f"获取 system_id={system_id} 的星系信息时出错: {e}")
            return None

    @staticmethod
    def maybe_chinese(strs):
        en_count = 0
        cn_count = 0
        for _char in strs:
            if '\u4e00' <= _char <= '\u9fa5':
                cn_count += 1
            elif 'a' <= _char <= 'z':
                en_count += 1
        return cn_count > en_count

    @staticmethod
    async def fuzz_en_type(item_name: str, list_len: int = 5) -> List[str]:
        """英文物品类型模糊搜索"""
        choice = await SdeUtils._get_invtype_name_list(zh=False)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    async def fuzz_zh_type(item_name: str, list_len: int = 5) -> List[str]:
        """中文物品类型模糊搜索"""
        choice = await SdeUtils._get_invtype_name_list(zh=True)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    async def fuzz_type(item_name: str, list_len: int = 5) -> List[str]:
        """物品类型模糊搜索（自动判断语言）"""
        if SdeUtils.maybe_chinese(item_name):
            return await SdeUtils.fuzz_zh_type(item_name, list_len)
        else:
            return await SdeUtils.fuzz_en_type(item_name, list_len)

    @staticmethod
    async def fuzz_zh_group(item_name: str, list_len: int = 5) -> List[str]:
        """中文组名称模糊搜索"""
        choice = await SdeUtils._get_invgroup_name_list(zh=True)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    async def fuzz_en_group(item_name: str, list_len: int = 5) -> List[str]:
        """英文组名称模糊搜索"""
        choice = await SdeUtils._get_invgroup_name_list(zh=False)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    async def fuzz_group(item_name: str, list_len: int = 5) -> List[str]:
        """组名称模糊搜索（自动判断语言）"""
        if SdeUtils.maybe_chinese(item_name):
            return await SdeUtils.fuzz_zh_group(item_name, list_len)
        else:
            return await SdeUtils.fuzz_en_group(item_name, list_len)

    @staticmethod
    async def fuzz_zh_meta(item_name: str, list_len: int = 5) -> List[str]:
        """中文 meta 名称模糊搜索"""
        choice = await SdeUtils._get_meta_name_list(zh=True)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    async def fuzz_en_meta(item_name: str, list_len: int = 5) -> List[str]:
        """英文 meta 名称模糊搜索"""
        choice = await SdeUtils._get_meta_name_list(zh=False)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    async def fuzz_meta(item_name: str, list_len: int = 5) -> List[str]:
        """meta 名称模糊搜索（自动判断语言）"""
        if SdeUtils.maybe_chinese(item_name):
            return await SdeUtils.fuzz_zh_meta(item_name, list_len)
        else:
            return await SdeUtils.fuzz_en_meta(item_name, list_len)

    @staticmethod
    async def fuzz_blueprint(item_name: str, list_len: int = 5) -> List[str]:
        """蓝图名称模糊搜索（自动判断语言）"""
        if SdeUtils.maybe_chinese(item_name):
            return await SdeUtils.fuzz_zh_blueprint(item_name, list_len)
        else:
            return await SdeUtils.fuzz_en_blueprint(item_name, list_len)

    @staticmethod
    async def fuzz_zh_blueprint(item_name: str, list_len: int = 5) -> List[str]:
        """中文蓝图名称模糊搜索"""
        choice = await SdeUtils._get_blueprint_name_list(zh=True)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    async def fuzz_en_blueprint(item_name: str, list_len: int = 5) -> List[str]:
        """英文蓝图名称模糊搜索"""
        choice = await SdeUtils._get_blueprint_name_list(zh=False)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        logger.info(f"input: {item_name}, fuzz_en_blueprint result: {result}")
        return [res[0] for res in result]

    @staticmethod
    async def fuzz_market_group(item_name: str, list_len: int = 5) -> List[str]:
        """市场组名称模糊搜索（自动判断语言）"""
        if SdeUtils.maybe_chinese(item_name):
            return await SdeUtils.fuzz_zh_market_group(item_name, list_len)
        else:
            return await SdeUtils.fuzz_en_market_group(item_name, list_len)

    @staticmethod
    async def fuzz_zh_market_group(item_name: str, list_len: int = 5) -> List[str]:
        """中文市场组名称模糊搜索"""
        choice = await SdeUtils._get_market_group_name_list(zh=True)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    async def fuzz_en_market_group(item_name: str, list_len: int = 5) -> List[str]:
        """英文市场组名称模糊搜索"""
        choice = await SdeUtils._get_market_group_name_list(zh=False)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    async def fuzz_category(item_name: str, list_len: int = 5) -> List[str]:
        """类别名称模糊搜索（自动判断语言）"""
        if SdeUtils.maybe_chinese(item_name):
            return await SdeUtils.fuzz_zh_category(item_name, list_len)
        else:
            return await SdeUtils.fuzz_en_category(item_name, list_len)

    @staticmethod
    async def fuzz_zh_category(item_name: str, list_len: int = 5) -> List[str]:
        """中文类别名称模糊搜索"""
        choice = await SdeUtils._get_category_name_list(zh=True)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    async def fuzz_en_category(item_name: str, list_len: int = 5) -> List[str]:
        """英文类别名称模糊搜索"""
        choice = await SdeUtils._get_category_name_list(zh=False)
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_all_type_id_in_market() -> List[int]:
        """获取所有在市场中的 typeID 列表"""
        async with (await get_db_manager()).get_readonly_session() as session:
            stmt = select(InvTypes.typeID).where(InvTypes.marketGroupID.isnot(None))
            result = await session.execute(stmt)
            return [row[0] for row in result]

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_important_type_id_in_market(zh: bool = False) -> List[int]:
        """获取重要类别在市场中的 typeID 列表"""
        category_list_en = [
            'Charge', 'Deployable', 'Drone', 'Fighter',
            'Implant', 'Module', 'Ship', 'Subsystem'
        ]
        category_list_zh = [
            '弹药', '可部署', '无人机', '战斗机',
            '植入体', '装备', '舰船', '子系统'
        ]
        category_list = category_list_zh if zh else category_list_en
        
        async with (await get_db_manager()).get_readonly_session() as session:
            category_name_field = InvCategories.categoryName_zh if zh else InvCategories.categoryName_en
            stmt = (
                select(InvTypes.typeID)
                .select_from(InvTypes)
                .join(InvGroups, InvTypes.groupID == InvGroups.groupID)
                .join(InvCategories, InvGroups.categoryID == InvCategories.categoryID)
                .where(category_name_field.in_(category_list))
                .where(InvTypes.marketGroupID.isnot(None))
            )
            result = await session.execute(stmt)
            return [row[0] for row in result]

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_volume_by_type_id(type_id: int, sdm=None) -> float:
        """根据 typeID 获取体积"""
        try:
            if sdm:
                m = sdm
            else:
                m = await get_db_manager()
            async with m.get_readonly_session() as session:
                stmt = select(InvTypes.volume).where(InvTypes.typeID == type_id)
                result = await session.execute(stmt)
                volume = result.scalar()
                return volume if volume is not None else 0.0
        except Exception as e:
            logger.warning(f"获取 type_id={type_id} 的体积时出错: {e}")
            return 0.0
    
    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_packaged_volume_by_type_id(type_id: int, sdm=None) -> float:
        """根据 typeID 获取包装体积"""
        try:
            if sdm:
                m = sdm
            else:
                m = await get_db_manager()
            async with m.get_readonly_session() as session:
                stmt = select(InvTypes.packagedVolume).where(InvTypes.typeID == type_id)
                result = await session.execute(stmt)
                volume = result.scalar()
                return volume if volume is not None else 0.0
        except Exception as e:
            logger.warning(f"获取 type_id={type_id} 的包装体积时出错: {e}")
            return 0.0


    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def search_type_ids_by_criteria(search_type: str, keyword: str, max_results: int = 200) -> List[dict]:
        """
        根据搜索类型和关键字搜索type_id列表
        
        Args:
            search_type: 搜索类型 (group, meta, category, marketGroup)
            keyword: 搜索关键字
            max_results: 最大返回结果数
        
        Returns:
            List[dict]: 包含 {type_id, type_name_zh} 的列表
        """
        results = []
        try:
            async with (await get_db_manager()).get_readonly_session() as session:
                is_zh = SdeUtils.maybe_chinese(keyword)
                
                if search_type == 'group':
                    # 通过group名称查询
                    group_name_field = InvGroups.groupName_zh if is_zh else InvGroups.groupName_en
                    stmt = (
                        select(InvTypes.typeID, InvTypes.typeName_zh)
                        .select_from(InvTypes)
                        .join(InvGroups, InvTypes.groupID == InvGroups.groupID)
                        .where(group_name_field == keyword)
                        .where(InvTypes.marketGroupID.isnot(None))
                        .where(InvTypes.typeName_zh.isnot(None))
                        .limit(max_results)
                    )
                    result = await session.execute(stmt)
                    for row in result:
                        results.append({
                            'type_id': row.typeID,
                            'type_name_zh': row.typeName_zh
                        })
                
                elif search_type == 'meta':
                    # 通过meta名称查询
                    meta_name_field = MetaGroups.nameID_zh if is_zh else MetaGroups.nameID_en
                    stmt = (
                        select(InvTypes.typeID, InvTypes.typeName_zh)
                        .select_from(InvTypes)
                        .join(MetaGroups, InvTypes.metaGroupID == MetaGroups.metaGroupID)
                        .where(meta_name_field == keyword)
                        .where(InvTypes.marketGroupID.isnot(None))
                        .where(InvTypes.typeName_zh.isnot(None))
                        .limit(max_results)
                    )
                    result = await session.execute(stmt)
                    for row in result:
                        results.append({
                            'type_id': row.typeID,
                            'type_name_zh': row.typeName_zh
                        })
                
                elif search_type == 'category':
                    # 通过category名称查询
                    category_name_field = InvCategories.categoryName_zh if is_zh else InvCategories.categoryName_en
                    stmt = (
                        select(InvTypes.typeID, InvTypes.typeName_zh)
                        .select_from(InvTypes)
                        .join(InvGroups, InvTypes.groupID == InvGroups.groupID)
                        .join(InvCategories, InvGroups.categoryID == InvCategories.categoryID)
                        .where(category_name_field == keyword)
                        .where(InvTypes.marketGroupID.isnot(None))
                        .where(InvTypes.typeName_zh.isnot(None))
                        .limit(max_results)
                    )
                    result = await session.execute(stmt)
                    for row in result:
                        results.append({
                            'type_id': row.typeID,
                            'type_name_zh': row.typeName_zh
                        })
                
                elif search_type == 'marketGroup':
                    # 通过marketGroup名称查询，使用neo4j
                    # 注意：marketGroup可能有父子关系，neo4j可以更好地处理层级关系
                    async with neo4j_manager().get_session() as neo4j_session:
                        # 查询匹配的MarketGroup节点，然后找到所有连接的Type节点
                        # 关系方向：Type -[:EVE_MARKET_GROUP]-> MarketGroup
                        if is_zh:
                            query = """
                            MATCH (mg:MarketGroup {name_id_zh: $keyword})
                            MATCH (t:Type)-[:EVE_MARKET_GROUP*0..20]->(mg)
                            WHERE t.type_name_zh IS NOT NULL
                            RETURN t.type_id AS type_id, t.type_name_zh AS type_name_zh
                            LIMIT $limit
                            """
                        else:
                            query = """
                            MATCH (mg:MarketGroup {name_id: $keyword})
                            MATCH (t:Type)-[:EVE_MARKET_GROUP*0..20]->(mg)
                            WHERE t.type_name_zh IS NOT NULL
                            RETURN t.type_id AS type_id, t.type_name_zh AS type_name_zh
                            LIMIT $limit
                            """
                        neo4j_result = await neo4j_session.run(query, {
                            "keyword": keyword,
                            "limit": max_results + 1  # 多查询一个用于判断是否超过限制
                        })
                        async for record in neo4j_result:
                            if len(results) >= max_results:
                                break
                            type_id = record.get("type_id")
                            type_name_zh = record.get("type_name_zh")
                            if type_id and type_name_zh:
                                results.append({
                                    'type_id': type_id,
                                    'type_name_zh': type_name_zh
                                })
        
        except Exception as e:
            logger.warning(f"搜索type_id失败: search_type={search_type}, keyword={keyword}, error={e}")
        
        return results

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_compressed_asteroid_type_ids() -> tuple[List[int], List[int]]:
        """获取压缩矿类型ID列表，返回两个分类列表
        
        Returns:
            tuple[List[int], List[int]]: (standard_and_moon_ore_ids, ice_ore_ids)
                - standard_and_moon_ore_ids: 标准矿石和卫星矿石的type_id列表
                - ice_ore_ids: 冰矿的type_id列表
        """
        try:
            async with neo4j_manager().get_session() as neo4j_session:
                # 查询标准矿石和卫星矿石
                standard_and_moon_market_groups = ["标准矿石", "卫星矿石"]
                query_standard_moon = """
                MATCH (mg:MarketGroup)
                WHERE mg.name_id_zh IN $market_group_names
                MATCH (t:Type)-[:EVE_MARKET_GROUP*0..20]->(mg)
                WHERE t.type_name IS NOT NULL 
                  AND t.type_name STARTS WITH 'Compressed'
                RETURN DISTINCT t.type_id AS type_id
                """
                
                neo4j_result = await neo4j_session.run(query_standard_moon, {
                    "market_group_names": standard_and_moon_market_groups
                })
                
                standard_and_moon_ore_ids = []
                async for record in neo4j_result:
                    type_id = record.get("type_id")
                    if type_id is not None:
                        standard_and_moon_ore_ids.append(type_id)
                
                # 查询冰矿
                ice_market_groups = ["冰矿"]
                query_ice = """
                MATCH (mg:MarketGroup)
                WHERE mg.name_id_zh IN $market_group_names
                MATCH (t:Type)-[:EVE_MARKET_GROUP*0..20]->(mg)
                WHERE t.type_name IS NOT NULL 
                  AND t.type_name STARTS WITH 'Compressed'
                RETURN DISTINCT t.type_id AS type_id
                """
                
                neo4j_result = await neo4j_session.run(query_ice, {
                    "market_group_names": ice_market_groups
                })
                
                ice_ore_ids = []
                async for record in neo4j_result:
                    type_id = record.get("type_id")
                    if type_id is not None:
                        ice_ore_ids.append(type_id)
                
                return (standard_and_moon_ore_ids, ice_ore_ids)
        except Exception as e:
            logger.warning(f"获取压缩矿类型ID列表失败: {e}")
            traceback.print_exc()
            return ([], [])

    @staticmethod
    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_type_material_data_by_ids(type_ids: List[int]) -> List[dict]:
        """根据类型ID列表获取类型材料数据"""
        try:
            async with (await get_db_manager()).get_readonly_session() as session:
                stmt = select(TypeMaterials).where(TypeMaterials.typeID.in_(type_ids))
                result = await session.execute(stmt)
                return [
                    {
                        "typeID": obj.typeID,
                        "materialTypeID": obj.materialTypeID,
                        "quantity": obj.quantity
                    }
                    for obj in result.scalars()
                ]
        except Exception as e:
            logger.warning(f"获取类型材料数据失败: {e}")
            traceback.print_exc()
            return []