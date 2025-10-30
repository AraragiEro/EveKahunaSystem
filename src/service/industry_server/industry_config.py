import asyncio
import json
from enum import Enum
import asyncio

from .blueprint import BPManager
from ..sde_service import SdeUtils
# from ..database_server.model import Matcher as M_Matcher
from ..database_server.sqlalchemy.kahuna_database_utils import MatcherDBUtils
from ..log_server import logger
from .structure import Structure
from ...utils import KahunaException
from .matcher import Matcher


NULL_MANU_SEC_BONUS = 2.1
NULL_REAC_SEC_BONUS = 1.1

T1_MANU_MATER_EFF = 1 - 0.02 * NULL_MANU_SEC_BONUS
T1_MANU_TIME_EFF = 1 - 0.2 * NULL_MANU_SEC_BONUS

T2_MANU_MATER_EFF = 1 - 0.024 * NULL_MANU_SEC_BONUS
T2_MANU_TIME_EFF = 1 - 0.24 * NULL_MANU_SEC_BONUS

T1_REAC_MATER_EFF = 1 - 0.02 * NULL_REAC_SEC_BONUS
T1_REAC_TIME_EFF = 1 - 0.2 * NULL_REAC_SEC_BONUS

T2_REAC_MATER_EFF = 1 - 0.024 * NULL_REAC_SEC_BONUS
T2_REAC_TIME_EFF = 1 - 0.24 * NULL_REAC_SEC_BONUS

MANU_STRUCTURE_MATER_EFF = 1 - 0.01

SMALL_STRUCTURE_MANU_TIME_EFF = 1 - 0.15
MID_STRUCTURE_MANU_TIME_EFF = 1 - 0.2
LARGE_STRUCTURE_MANU_TIME_EFF = 1 - 0.3

MID_STRUCTURE_REAC_TIME_EFF = 1 - 0.25
SMALL_STRUCTURE_REAC_TIME_EFF = 0

MANU_SKILL_TIME_EFF = 1 - 0.32
REAC_SKILL_TIME_EFF = 1 - 0.2

# 默认蓝图材料效率
DEFAULT_FACTION_MATERIAL_EFFICIENCY = 0
DEFAULT_T2_MATERIAL_EFFICIENCY = 0.02
DEFAULT_OTHER_MATERIAL_EFFICIENCY = 0.1

# 默认蓝图时间效率
DEFAULT_FACTION_TIME_EFFICIENCY = 0
DEFAULT_T2_TIME_EFFICIENCY = 0.04
DEFAULT_OTHER_TIME_EFFICIENCY = 0.2

LARGE_COST_EFF = 0.05
MID_COST_EFF = 0.04
SMALL_COST_EFF = 0.03

class EffStructUreType(Enum):
    T2_TATARA = 1
    T2_LETA_LU = 2
    T1_SOTIYO = 3

class IndustryConfigManager():
    init_matcher_status = False
    config_owner_qq = "default"
    matcher_type_set = {"bp", "structure", "prod_block", "sell"}
    # {name: Matcher}
    matcher_dict = dict()
    # 最终材料效率为：
    #   蓝图效率 * 建筑效率
    # 蓝图效率获取优先级：
    #   特别设置的蓝图效率 > 蓝图资产效率 > 默认蓝图效率
    # 建筑效率获取优先级
    #   特别设置的建筑效率 > 蓝图资产所在建筑效率 > 默认建筑效率
    @classmethod
    def get_eff(cls, source_id: int) -> tuple[int, int]:
        mater_eff = 1
        time_eff = 1

        action_id = BPManager.get_action_id(source_id)
        group_name = SdeUtils.get_groupname_by_id(source_id)
        # category = SdeUtils.get_category_by_id(source_id)

        if action_id == 11:
            mater_eff = 1

        return mater_eff, time_eff

    @classmethod
    def get_default_structure_type_by_source_id(cls, source_id: int) -> EffStructUreType:
        """ 在特殊项匹配失败，使用默认建筑分配 """
        # TODO 特殊项目匹配的设计，可以考虑多种模式：
        # 1. 单品种模式
        # 2. 市场组分类模式market
        # 3. 群组分类模式group
        # 4. 元组分类模式meta
        # 5. 类别组分类模式category
        action_id = BPManager.get_action_id(source_id)
        group_name = SdeUtils.get_groupname_by_id(source_id)

        if action_id == 11:
            return EffStructUreType.T2_TATARA
        elif group_name == 'Construction Components':
            return EffStructUreType.T2_LETA_LU
        else:
            return EffStructUreType.T1_SOTIYO

    @classmethod
    def getsource_struct_type_time_eff(cls, source_id: int) -> int:
        """ 获取制造默认时间效率参数 """
        # type 按照建筑分类,分别为T2tatara, T2莱塔卢， T1sotiyo
        source_type = cls.get_default_structure_type_by_source_id(source_id)

        if source_type == EffStructUreType.T2_TATARA:
            time_eff = 1 *NULL_REAC_SEC_BONUS * T2_REAC_TIME_EFF * MID_STRUCTURE_MANU_TIME_EFF
        elif source_type == EffStructUreType.T2_LETA_LU:
            time_eff = 1 * NULL_MANU_SEC_BONUS * T2_MANU_TIME_EFF * SMALL_STRUCTURE_MANU_TIME_EFF
        elif source_type == EffStructUreType.T1_SOTIYO:
            time_eff = 1 * NULL_MANU_SEC_BONUS * T1_MANU_TIME_EFF * LARGE_STRUCTURE_MANU_TIME_EFF

        return time_eff

    @classmethod
    def getsource_struct_type_mater_eff(cls, source_id: int) -> int:
        """ 获取制造建筑默认材料效率参数 """
        # type 按照建筑分类,分别为T2tatara, T2莱塔卢， T1sotiyo
        source_type = cls.get_default_structure_type_by_source_id(source_id)

        if source_type == EffStructUreType.T2_TATARA:
            mater_eff = 1 * NULL_REAC_SEC_BONUS * T2_REAC_MATER_EFF
        elif source_type == EffStructUreType.T2_LETA_LU:
            mater_eff = 1 * NULL_MANU_SEC_BONUS * T2_MANU_TIME_EFF * MANU_STRUCTURE_MATER_EFF
        elif source_type == EffStructUreType.T1_SOTIYO:
            mater_eff = 1 * NULL_MANU_SEC_BONUS * T1_MANU_TIME_EFF * MANU_STRUCTURE_MATER_EFF

        return mater_eff

    @classmethod
    async def init(cls):
        await cls.init_matcher_dict()

    @classmethod
    async def init_matcher_dict(cls):
        if not cls.init_matcher_status:
            matcher_list = await MatcherDBUtils.select_all()
            for matcher_data in matcher_list:
                cls.matcher_dict[matcher_data.matcher_name] = Matcher.init_from_db_data(matcher_data)
                logger.info(f'初始化匹配器 {matcher_data.matcher_name}.')
            cls.init_matcher_status = True
        logger.info(f'Matcher dict inited. {id(cls)}')


    @classmethod
    async def add_matcher(cls, matcher_name: str, user_qq: int, matcher_type: str) -> Matcher:
        if matcher_name in cls.matcher_dict:
            raise KeyError(f'Matcher {matcher_name} already exists')

        matcher = Matcher(matcher_name, user_qq, matcher_type)
        cls.matcher_dict[matcher_name] = matcher
        await matcher.insert_to_db()
        return matcher

    @classmethod
    async def delete_matcher(cls, matcher_name: str, user_qq: int) -> Matcher:
        if matcher_name not in cls.matcher_dict:
            raise KeyError(f'Matcher {matcher_name} does not exist')

        matcher = cls.matcher_dict[matcher_name]
        await matcher.delete_from_db()
        return cls.matcher_dict.pop(matcher_name)

    @classmethod
    def get_user_matcher(cls, user_qq: int) -> list[Matcher]:
        res = [matcher for matcher in cls.matcher_dict.values() if matcher.user_qq == user_qq]
        return res

    @classmethod
    def get_matcher_of_user_by_name(cls, matcher_name: str, user_qq: int) -> Matcher:
        for matcher in cls.get_user_matcher(user_qq):
            if matcher.matcher_name == matcher_name:
                return matcher
        raise KeyError(f'Matcher {matcher_name} does not exist')

    @classmethod
    def get_structure_EIV_cost_eff(cls, strcture_type_id: int) -> float:
        structure_type = SdeUtils.get_name_by_id(strcture_type_id)

        # manu
        if structure_type == "Sotiyo":
            return LARGE_COST_EFF
        elif structure_type == "Azbel":
            return MID_COST_EFF
        elif structure_type == "Raitaru":
            return SMALL_COST_EFF
        else:
            return 0

    @classmethod
    def get_structure_mater_time_eff(cls, strcture_type_id: int) -> [int, int]:
        structure_time_eff = 1
        structure_mater_eff = 1
        structure_type = SdeUtils.get_name_by_id(strcture_type_id)

        # manu
        if structure_type == "Sotiyo":
            structure_time_eff = LARGE_STRUCTURE_MANU_TIME_EFF
            structure_mater_eff = MANU_STRUCTURE_MATER_EFF
        elif structure_type == "Azbel":
            structure_time_eff = MID_STRUCTURE_MANU_TIME_EFF
            structure_mater_eff = MANU_STRUCTURE_MATER_EFF
        elif structure_type == "Raitaru":
            structure_time_eff = SMALL_STRUCTURE_MANU_TIME_EFF
            structure_mater_eff = MANU_STRUCTURE_MATER_EFF
        # reac
        elif structure_type == "Tatara":
            structure_time_eff = MID_STRUCTURE_REAC_TIME_EFF
        elif structure_type == "Athanor":
            structure_time_eff = SMALL_STRUCTURE_REAC_TIME_EFF

        return structure_mater_eff, structure_time_eff

    @classmethod
    def get_structure_rig_mater_time_eff(cls, structure: Structure) -> [int, int]:
        structure_time_eff = 1
        structure_mater_eff = 1
        structure_type = SdeUtils.get_name_by_id(structure.type_id)

        if structure_type in {"Sotiyo", "Azbel", "Raitaru"}:
            if structure.time_rig_level == 1:
                structure_time_eff = T1_MANU_TIME_EFF
                structure_mater_eff = T1_MANU_MATER_EFF
            elif structure.time_rig_level == 2:
                structure_time_eff = T2_MANU_TIME_EFF
                structure_mater_eff = T2_MANU_MATER_EFF
        elif structure_type in {"Tatara", "Athanor"}:
            if structure.time_rig_level == 1:
                structure_time_eff = T1_REAC_TIME_EFF
                structure_mater_eff = T1_REAC_MATER_EFF
            elif structure.time_rig_level == 2:
                structure_time_eff = T2_REAC_TIME_EFF
                structure_mater_eff = T2_REAC_MATER_EFF

        return structure_mater_eff, structure_time_eff

    @classmethod
    def allocate_structure(cls, source_id: int, st_matcher: Matcher) -> int | None:
        """
        input: source_id, matcher
        根据source_id的物品属性，按照"bp", "market_group", "group", "meta", "category"的顺序从matcher_data中匹配
    
        return: [structure_id , mater_eff , time_eff]
        """
        structure_id = None
        invType_data = SdeUtils.get_invtpye_node_by_id(source_id)
        if not invType_data:
            raise KahunaException(f"{source_id} 不存在于数据库，请联系管理员。")

        # bp
        bp_id = BPManager.get_bp_id_by_prod_typeid(source_id)
        bp_name = SdeUtils.get_name_by_id(bp_id)
        if bp_name in st_matcher.matcher_data["bp"]:
            return st_matcher.matcher_data["bp"][bp_name]

        # 找到符合条件的最小市场分类
        mklist = SdeUtils.get_market_group_list(source_id)
        mk_structure_id = None
        largest_index = 0
        for market_group, structure_id in st_matcher.matcher_data["market_group"].items():
            if market_group in mklist:
                if not mk_structure_id:
                    mk_structure_id = structure_id
                    largest_index = mklist.index(market_group)
                    continue
                index = mklist.index(market_group)
                if index > largest_index:
                    mk_structure_id = structure_id
                    largest_index = index
        if mk_structure_id:
            return mk_structure_id

        group = SdeUtils.get_groupname_by_id(source_id)
        if group in st_matcher.matcher_data["group"]:
            return st_matcher.matcher_data["group"][group]

        meta = SdeUtils.get_metaname_by_typeid(source_id)
        if meta in st_matcher.matcher_data["meta"]:
            return st_matcher.matcher_data["meta"][meta]

        category = SdeUtils.get_category_by_id(source_id)
        if category in st_matcher.matcher_data["category"]:
            return st_matcher.matcher_data["category"][category]

        raise KahunaException(f"typeid: {source_id} 无建筑分配，请配置匹配器。")


    @classmethod
    def get_default_bp_mater_time_eff(cls, type_id: int) -> [int, int]:
        """
        meta faction = 0-0
        meta T2 and category Ship = 2-4
        mkg = Titans 8 - 16
        mkg = Capital Ships 9 - 18
        meta T1 = 10-20
        """
        meta_name = SdeUtils.get_metaname_by_typeid(type_id)
        market_group_list = SdeUtils.get_market_group_list(type_id)
        category = SdeUtils.get_category_by_id(type_id)
        action_id = BPManager.get_action_id(type_id)
        if action_id == 11:
            return 1, 1
        if meta_name == "Faction":
            return 1, 1
        if meta_name == "Tech II" and category == "Ship":
            return 0.98, 0.96
        elif "Titans" in market_group_list:
            return 0.92, 0.84
        elif "Capital Ships" in market_group_list:
            return 0.91, 0.82
        else:
            return 0.9, 0.8
