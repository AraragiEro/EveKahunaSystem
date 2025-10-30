from typing import AnyStr, List
from datetime import datetime, timedelta
import json
from warnings import deprecated

from src_v2.core.database.kahuna_database_utils_v2 import (
    UserDataDBUtils,
    UserDBUtils
)
# from ..character_manager import CharacterManager
from src_v2.core.utils import KahunaException

# TODO postgre 适配user对象的修改
class User():
    def __init__(self, user_name: AnyStr, user_role: AnyStr, user_permission: List):
        self.user_name = user_name
        self.user_role = user_role
        self.user_permission = user_permission
        # self.user_data.load_self_data()

    # @deprecated
    # @property
    # def info(self):
    #     res = (f"用户:{self.user_qq}\n"
    #             f"创建时间:{self.create_date}\n"
    #             f"到期时间:{self.expire_date}\n"
    #             f"剩余时间:{max(timedelta(), self.expire_date - datetime.now())}\n")
    #             # f"主角色：{CharacterManager.get_character_by_id(self.main_character_id).character_name}\n")
    #     if self.main_character_id != 0:
    #         res += f"主角色：{CharacterManager.get_character_by_id(self.main_character_id).character_name}\n"
    #     return res

    # @deprecated
    # async def set_plan_product(self, plan_name: str, product: str, quantity: int):
    #     if plan_name not in self.user_data.plan:
    #         raise KahunaException(
    #             "计划不存在，请使用 .Inds plan create [plan_name] [bp_matcher] [st_matcher] [prod_block_matcher] 创建")
    #     self.user_data.plan[plan_name]["plan"].append([product, quantity])
    #     await self.user_data.insert_to_db()

    # TODO这是工业的功能，需要迁移
    # @deprecated
    # async def create_plan(self, plan_name: str,
    #                 bp_matcher, st_matcher, prod_block_matcher
    #                 ):
    #     if len(self.user_data.plan) - 3 >= self.plan_max:
    #         raise KahunaException(f"you can only create {self.plan_max} plans at most.")
    #     if plan_name not in self.user_data.plan:
    #         self.user_data.plan[plan_name] = {}
    #
    #     self.user_data.plan[plan_name]["bp_matcher"] = bp_matcher.matcher_name
    #     self.user_data.plan[plan_name]["st_matcher"] = st_matcher.matcher_name
    #     self.user_data.plan[plan_name]["prod_block_matcher"] = prod_block_matcher.matcher_name
    #     self.user_data.plan[plan_name]["manucycletime"] = 24 # hour
    #     self.user_data.plan[plan_name]['reaccycletime'] = 24
    #     self.user_data.plan[plan_name]['container_block'] = []
    #     self.user_data.plan[plan_name]["plan"] = []
    #     self.user_data.plan[plan_name]["coop_user"] = []
    #     await self.user_data.insert_to_db()

    # @deprecated
    # async def delete_plan_prod(self, plan_name: str, index: int):
    #     if plan_name not in self.user_data.plan:
    #         raise KahunaException("plan not found.")
    #     if 0 <= index < len(self.user_data.plan[plan_name]["plan"]):
    #         self.user_data.plan[plan_name]["plan"].pop(index)
    #     await self.user_data.insert_to_db()
    #
    # @deprecated
    # async def set_manu_cycle_time(self, plan_name: str, cycle_time: int):
    #     if plan_name not in self.user_data.plan:
    #         raise KahunaException("plan not found.")
    #     self.user_data.plan[plan_name]["manucycletime"] = cycle_time
    #     await self.user_data.insert_to_db()
    #
    # @deprecated
    # async def set_reac_cycle_time(self, plan_name: str, cycle_time: int):
    #     if plan_name not in self.user_data.plan:
    #         raise KahunaException("plan not found.")
    #     self.user_data.plan[plan_name]["reaccycletime"] = cycle_time
    #     await self.user_data.insert_to_db()
    #
    # @deprecated
    # async def delete_plan(self, plan_name: str):
    #     if plan_name not in self.user_data.plan:
    #         raise KahunaException("plan not found.")
    #     self.user_data.plan.pop(plan_name)
    #     await self.insert_to_db()
    #
    # @deprecated
    # async def add_alias_character(self, character_id_list):
    #     for character_data in character_id_list:
    #         if character_data[0] not in self.user_data.alias:
    #             self.user_data.alias[character_data[0]] = character_data[1]
    #     await self.user_data.insert_to_db()
    #
    # @deprecated
    # async def add_container_block(self, plan_name: str, container_id: int):
    #     if plan_name not in self.user_data.plan:
    #         raise KahunaException("plan not found.")
    #     if "container_block" not in self.user_data.plan[plan_name]:
    #         self.user_data.plan[plan_name]["container_block"] = []
    #     if container_id not in self.user_data.plan[plan_name]["container_block"]:
    #         self.user_data.plan[plan_name]["container_block"].append(container_id)
    #     await self.user_data.insert_to_db()
    #
    # @deprecated
    # async def del_container_block(self, plan_name: str, container_id: int):
    #     if plan_name not in self.user_data.plan:
    #         raise KahunaException("plan not found.")
    #     if "container_block" not in self.user_data.plan[plan_name]:
    #         self.user_data.plan[plan_name]["container_block"] = []
    #     if container_id in self.user_data.plan[plan_name]["container_block"]:
    #         self.user_data.plan[plan_name]["container_block"].remove(container_id)
    #     await self.user_data.insert_to_db()
    #
    # @deprecated
    # async def add_plan_coop_user(self, plan_name: str, user_qq: int):
    #     if plan_name not in self.user_data.plan:
    #         raise KahunaException("plan not found.")
    #     if user_qq not in set(self.user_data.plan[plan_name]["coop_user"]):
    #         self.user_data.plan[plan_name]["coop_user"].append(user_qq)
    #     await self.user_data.insert_to_db()
    #
    # @deprecated
    # async def del_plan_coop_user(self, plan_name: str, user_qq: int):
    #     if plan_name not in self.user_data.plan:
    #         raise KahunaException("plan not found.")
    #     if user_qq in set(self.user_data.plan[plan_name]["coop_user"]):
    #         self.user_data.plan[plan_name]["coop_user"].remove(user_qq)
    #     await self.user_data.insert_to_db()
