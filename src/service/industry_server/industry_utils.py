import math

from .blueprint import BPManager
from .market_price import MarketPrice
from .system_cost import SystemCost
from ..sde_service import SdeUtils
from cachetools import cached, TTLCache
from ..user_server.user_manager import UserManager
from ..character_server.character_manager import CharacterManager
from .structure import StructureManager

from ..database_server.sqlalchemy.kahuna_database_utils import (
    InvTypeMapDBUtils
)

from .blueprint import BPManager
from .industry_config import IndustryConfigManager

class IdsUtils:
    eiv_cache = TTLCache(maxsize=100, ttl=3600)
    @staticmethod
    async def get_eiv(type_id) -> int:
        if type_id in IdsUtils.eiv_cache:
            return IdsUtils.eiv_cache[type_id]
        bp_materials = BPManager.get_bp_materials(type_id)
        production_quantity = BPManager.get_bp_product_quantity_typeid(type_id)
        eiv = 0
        for child_id, quantity in bp_materials.items():
            child_market_price = await MarketPrice.get_adjusted_price_of_typeid(child_id)
            eiv += quantity * child_market_price

        res = eiv / production_quantity
        IdsUtils.eiv_cache[type_id] = res
        return res

    @classmethod
    def check_job_material_avaliable(cls, type_id, work, asset_dict):
        mater_needed = work.get_material_need()
        for child_id, child_need in mater_needed.items():
            if child_need > asset_dict.get(child_id, 0):
                return False

        for child_id, child_need in mater_needed.items():
            asset_dict[child_id] -= child_need
        return True

    @classmethod
    def input_work_checkpoint(cls, work_check_dict, work):
        type_id = work.type_id
        mater_needed = work.get_material_need()
        for child_id, child_need in mater_needed.items():
            if child_id not in work_check_dict:
                work_check_dict[child_id] = []
            work_check_dict[child_id].append({
                'min_index': min(work.support_index), 'quantity': child_need, 'work': work
            })

    @classmethod
    async def get_eiv_cost(cls, child_id, child_total_quantity: int, owner_qq: int, st_matcher):
        """ 获取系数成本 """
        character_id = UserManager.get_main_character_id(owner_qq)
        character = CharacterManager.get_character_by_id(character_id)
        structure_id = IndustryConfigManager.allocate_structure(child_id, st_matcher)
        structure = await StructureManager.get_structure(structure_id, character.ac_token)
        eiv_cost_eff = IndustryConfigManager.get_structure_EIV_cost_eff(structure.type_id)

        sys_manu_cost, sys_reac_cost = await SystemCost.get_system_cost(structure.solar_system_id)
        child_eiv = await cls.get_eiv(child_id) * child_total_quantity
        action_id = BPManager.get_action_id(child_id)

        if action_id == 1:
            child_eiv_cost = child_eiv * ((0.04 + 0.0001 + 0.0005) + (sys_manu_cost * (1 - eiv_cost_eff)))
        else:
            child_eiv_cost = child_eiv * ((0.04 + 0.0001 + 0.0005) + (sys_reac_cost * (1 - eiv_cost_eff)))

        return child_eiv_cost

    @classmethod
    async def get_logistic_need_data(cls, owner_qq: int, child_id: int, st_matcher: str, quantity: int):
        character_id = UserManager.get_main_character_id(owner_qq)
        character = CharacterManager.get_character_by_id(character_id)
        structure_id = IndustryConfigManager.allocate_structure(child_id, st_matcher)
        structure = await StructureManager.get_structure(structure_id, character.ac_token)

        return [child_id, structure, quantity]

    # TODO map功能
    # @classmethod
    # async def init_type_map(cls):
    #     map_list = await InvTypeMapDBUtils.select_all()
    #     cls.item_map_dict = {res.maped_type: res.target_type for res in map_list}

    # @classmethod
    # def add_type_map(cls, maped_item: str, target_item: str) -> tuple:
    #     if maped_item in cls.item_map_dict:
    #         return False, None
    #     if not SdeUtils.get_id_by_name(target_item):
    #         return False, SdeUtils.fuzz_type(target_item)
    #     new_map = InvTypeMap(maped_item, target_item)
    #     new_map.save()
    #     cls.item_map_dict[maped_item] = new_map