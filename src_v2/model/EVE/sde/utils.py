from functools import lru_cache
import networkx as nx
from thefuzz import fuzz, process
from peewee import DoesNotExist
from cachetools import TTLCache, cached
from unicodedata import category

from . import database as en_model, database_cn as zh_model
from .database import InvTypes, InvGroups, InvCategories, MapSolarSystems
from .database import MetaGroups, MarketGroups
from src_v2.core.log import logger

from .database_cn import InvTypes as InvTypes_zh

en_invtype_name_list = [res.typeName for res in InvTypes.select(InvTypes.typeName).where(InvTypes.marketGroupID != 0)]
zh_invtype_name_list = [res.typeName for res in InvTypes_zh.select(InvTypes_zh.typeName).where(InvTypes_zh.marketGroupID != 0)]


class SdeUtils:
    _market_tree = None
    item_map_dict = dict()

    @staticmethod
    @lru_cache(maxsize=2)
    def get_t2_ship() -> list:
        t2_search = (
            InvTypes.select(InvTypes.typeName)
            .join(InvGroups, on=(InvTypes.groupID == InvGroups.groupID))
            .join(InvCategories, on=(InvGroups.categoryID == InvCategories.categoryID))
            .where(InvCategories.categoryName == "Ship")
            .switch(InvTypes)
            .where(InvTypes.marketGroupID.is_null(False))
            .join(MetaGroups, on=(InvTypes.metaGroupID == MetaGroups.metaGroupID))
            .where(MetaGroups.nameID == "Tech II")
        )

        result = [type.typeName for type in t2_search]

        return result

    @staticmethod
    @lru_cache(maxsize=2)
    def get_battleship() -> list:
        ship_search = (
            InvTypes.select(InvTypes.typeName, InvTypes.typeID, InvTypes.marketGroupID)
            .join(InvGroups, on=(InvTypes.groupID == InvGroups.groupID))
            .join(InvCategories, on=(InvGroups.categoryID == InvCategories.categoryID))
            .where(InvCategories.categoryName == "Ship")
        )

        result = []
        for type in ship_search:
            market_list = SdeUtils.get_market_group_list(type.typeID)
            if 'Battleships' in market_list:
                result.append(type.typeName)

        return result


    @staticmethod
    @lru_cache(maxsize=2)
    def get_capital_ship() -> list:
        capital_ship_search = (
                InvTypes.select(InvTypes.typeName, InvTypes.typeID, InvTypes.marketGroupID)
                .join(InvGroups, on=(InvTypes.groupID == InvGroups.groupID))
                .join(InvCategories, on=(InvGroups.categoryID == InvCategories.categoryID))
                .where(InvCategories.categoryName == "Ship")
        )

        res = []
        for ship in capital_ship_search:
            market_list = SdeUtils.get_market_group_list(ship.typeID)
            if 'Capital Ships' in market_list:
                res.append(ship.typeName)

        res.remove('Venerable')
        res.remove('Vanguard')
        return res

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_groupname_by_id(invtpye_id: int, zh=False) -> str:
        if zh:
            model = zh_model
        else:
            model = en_model

        InvTypes = model.InvTypes
        InvGroups = model.InvGroups

        try:
            return (
                InvTypes.select(InvGroups.groupName)
                .join(InvGroups, on=(InvTypes.groupID == InvGroups.groupID))
                .switch(InvTypes)
                .where(InvTypes.typeID == invtpye_id).scalar()
            )
        except InvTypes.DoesNotExist:
            return None

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_groupid_by_groupname(group_name: str) -> str:
        if (data := InvGroups.get_or_none(InvGroups.groupName == group_name)) is None:
            return None
        return data.groupID

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_invtpye_node_by_id(invtpye_id: int) -> InvTypes:
        try:
            return InvTypes.get(InvTypes.typeID == invtpye_id)
        except InvTypes.DoesNotExist:
            return None

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_invtype_packagedvolume_by_id(invtpye_id: int) -> float:
        try:
            return InvTypes.get(InvTypes.typeID == invtpye_id).packagedVolume
        except InvTypes.DoesNotExist:
            return 0

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_metaname_by_metaid(meta_id: int) -> str:
        try:
            return MetaGroups.get(MetaGroups.metaGroupID == meta_id).nameID
        except MetaGroups.DoesNotExist:
            return None

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_metaname_by_typeid(typeid: int) -> int:
        try:
            return (InvTypes.select(MetaGroups.nameID)
                       .join(MetaGroups, on=(InvTypes.metaGroupID == MetaGroups.metaGroupID))
                       .switch(InvTypes)
                       .where(InvTypes.typeID == typeid)
                       .scalar()
            )
        except DoesNotExist:
            return None

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_metadid_by_metaname(meta_name: int) -> int:
        try:
            return MetaGroups.get(MetaGroups.nameID == meta_name).metaGroupID
        except MetaGroups.DoesNotExist:
            return None

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_id_by_name(name) -> int:
        try:
            if SdeUtils.maybe_chinese(name):
                return InvTypes_zh.get(InvTypes_zh.typeName == name).typeID
            return InvTypes.get(InvTypes.typeName == name).typeID
        except DoesNotExist:
            return None

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_name_by_id(type_id) -> str:
        try:
            return InvTypes.get(InvTypes.typeID == type_id).typeName
        except DoesNotExist:
            return None

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_id_by_cn_name(name) -> int:
        try:
            return InvTypes_zh.get(InvTypes_zh.typeName == name).typeID
        except InvTypes_zh.DoesNotExist:
            return None

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_cn_name_by_id(type_id) -> str:
        try:
            return InvTypes_zh.get(InvTypes_zh.typeID == type_id).typeName
        except InvTypes_zh.DoesNotExist:
            return None

    @classmethod
    def get_market_group_tree(cls):
        if not cls._market_tree:
            g = nx.DiGraph()

            market_group_data = MarketGroups.select()
            for market_group in market_group_data:
                g.add_node(market_group.marketGroupID)
                if market_group.parentGroupID:
                    g.add_node(market_group.parentGroupID)
                    g.add_edge(market_group.parentGroupID, market_group.marketGroupID)
            cls._market_tree = g
        return cls._market_tree

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_market_group_name_by_groupid(market_group_id, zh=False) -> str:
        if zh:
            model = zh_model
        else:
            model = en_model
        name = model.MarketGroups.get(model.MarketGroups.marketGroupID == market_group_id).nameID

        return name

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_market_groupid_by_name(market_group_name: str) -> int:
        name = MarketGroups.select(MarketGroups.marketGroupID).where(MarketGroups.nameID == market_group_name).scalar()

        return name

    @classmethod
    @lru_cache(maxsize=1000)
    def get_market_group_list(cls, type_id: int, zh=False) -> list[str]:
        try:
            market_tree = cls.get_market_group_tree()
            market_group_id = cls.get_invtpye_node_by_id(type_id)
            if not market_group_id:
                return []
            market_group_id = market_group_id.marketGroupID
            market_group_list = []
            if market_group_id:
                market_group_list = [cls.get_name_by_id(type_id), cls.get_market_group_name_by_groupid(market_group_id, zh)]
                parent_nodes = [parent_id for parent_id in market_tree.predecessors(market_group_id)]
                while parent_nodes:
                    parent_node = parent_nodes[0]
                    parent_name = cls.get_market_group_name_by_groupid(parent_node, zh)
                    market_group_list.append(parent_name)
                    parent_nodes = [parent_id for parent_id in market_tree.predecessors(parent_node)]
                market_group_list.reverse()
            return market_group_list
        except Exception as e:
            logger.error(f"get_market_group_list error: {e}")
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
    @lru_cache(maxsize=1000)
    def get_category_by_id(type_id: int, zh=False) -> str:
        if zh:
            model = zh_model
        else:
            model = en_model
        try:
            return (
                model.InvTypes.select(model.InvCategories.categoryName)
                .join(model.InvGroups, on=(model.InvTypes.groupID == model.InvGroups.groupID))
                .join(model.InvCategories, on=(model.InvGroups.categoryID == model.InvCategories.categoryID))
                .where(model.InvTypes.typeID == type_id)
                .scalar()
            )
        except model.InvTypes.DoesNotExist:
            return None

    @staticmethod
    @lru_cache(maxsize=100)
    def get_system_info_by_id(system_id: int, zh=False) -> dict:
        if zh:
            model = zh_model
        else:
            model = en_model
        return (
            model.MapSolarSystems.select(
                model.MapSolarSystems.solarSystemName.alias('system_name'),
                model.MapSolarSystems.solarSystemID.alias('system_id'),
                model.MapSolarSystems.regionID.alias('region_id'),
                model.MapRegions.regionName.alias('region_name')
            )
            .join(model.MapRegions, on=(model.MapSolarSystems.regionID == model.MapRegions.regionID))
            .where(model.MapSolarSystems.solarSystemID == system_id)
            .dicts()
            .first()
        )

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

    @lru_cache(maxsize=200)
    @staticmethod
    def fuzz_en_type(item_name, list_len) -> list[str]:
        choice = en_invtype_name_list
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @lru_cache(maxsize=200)
    @staticmethod
    def fuzz_zh_type(item_name, list_len) -> list[str]:
        choice = zh_invtype_name_list
        result = process.extract(item_name, choice, scorer=fuzz.token_sort_ratio, limit=list_len)
        return [res[0] for res in result]

    @staticmethod
    def fuzz_type(item_name, list_len = 5) -> list[str]:
        if SdeUtils.maybe_chinese(item_name):
            return SdeUtils.fuzz_zh_type(item_name, list_len)
        else:
            return SdeUtils.fuzz_en_type(item_name, list_len)

    @staticmethod
    def get_all_type_id_in_market():
        result = InvTypes.select(InvTypes.typeID).where(InvTypes.marketGroupID.is_null(False))

        return [res.typeID for res in result]

    @staticmethod
    def get_important_type_id_in_market():
        category_list = [
            'Charge',
            'Deployable',
            'Drone',
            'Fighter',
            'Implant',
            'Module',
            'Ship',
            'Subsystem'
        ]

        res = (
            InvTypes.select()
            .join(InvGroups, on=(InvTypes.groupID == InvGroups.groupID))
            .join(InvCategories, on=(InvGroups.categoryID == InvCategories.categoryID))
            .where((InvCategories.categoryName << category_list) & (InvTypes.marketGroupID.is_null(False)))
       )

        return[r.typeID for r in res]

    @lru_cache(maxsize=200)
    @staticmethod
    def get_volume_by_type_id(type_id: int) -> float:
        try:
            return InvTypes.get(InvTypes.typeID == type_id).volume
        except InvTypes.DoesNotExist:
            return 0

