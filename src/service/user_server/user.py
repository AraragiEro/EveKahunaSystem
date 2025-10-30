from datetime import datetime, timedelta
import json
from warnings import deprecated

from ..database_server.sqlalchemy.kahuna_database_utils import (
    UserDataDBUtils,
    UserDBUtils
)
from ..character_server.character_manager import CharacterManager
from ...utils import KahunaException

class UserData():
    user_qq: int = 0
    user_data_colunms = ["plan", "alias", "sell_data"]
    """ 
    plan: dict = {
        plan_name: {
            bp_matcher: Matcher,
            st_matcher: Matcher,
            prod_block_matcher: Matcher,
            plan: [[type_id: quantity], ...]
        }, ...
    }
    alias: dict = {
        character_id: character_name, ...
    }
    """

    def __init__(self, user_qq: int):
        self.user_qq = user_qq
        self.plan: dict = {}
        self.alias: dict = {}

        """ sell setting """
        self.sell_data: dict = {
            "name": "",
            "sell_container_id": 0,
            "sell_location_flag": None,
            "market_group": [],
            "group": [],
            "meta": [],
            "category": []
        }

        # await self.load_self_data()

    async def get_from_db(self):
        return await UserDataDBUtils.select_user_data_by_user_qq(self.user_qq)

    async def insert_to_db(self) -> None:
        obj = await self.get_from_db()
        if not obj:
            obj = UserDataDBUtils.get_obj()

        obj.user_qq = self.user_qq
        obj.user_data = self.dums_self_data()

        await UserDataDBUtils.save_obj(obj)

    def dums_self_data(self) -> str:
        data = {
            key: getattr(self, key) for key in self.user_data_colunms
        }

        return json.dumps(data, indent=4)

    async def load_self_data(self) -> None:
        data = await self.get_from_db()
        if not data:
            data_dict = {}
        else:
            data_dict = json.loads(data.user_data)
        for key in self.user_data_colunms:
            setattr(self, key, data_dict.get(key, dict()))

        # alias的key需要转换为整数
        self.alias = {int(cid): data for cid, data in self.alias.items()}

        # 新增的属性需要添加默认值
        for plan, data in self.plan.items():
            if "container_block" not in data:
                data["container_block"] = []
            if "coop_user" not in data:
                data["coop_user"] = []
            if "manucycletime" not in data:
                data["manucycletime"] = 24
            if "reaccycletime" not in data:
                data["reaccycletime"] = 24

    def get_plan_detail(self, plan_name: str) -> str:
        if plan_name not in self.plan:
            raise KahunaException("plan not found.")
        plan_dict = self.plan[plan_name]


        res_str = (f"bp_matcher: {plan_dict['bp_matcher']}\n"
                   f"st_matcher: {plan_dict['st_matcher']}\n"
                   f"prod_block_matcher: {plan_dict['prod_block_matcher']}\n"
                   f"plan:\n")
        plan_str = "\n".join([f"{index + 1}.{plan[0]}: {plan[1]}" for index, plan in enumerate(plan_dict["plan"])])

        return res_str + "\n" + plan_str

    @property
    def feishu_token(self):
        if not self.feishu_sheet_token:
            raise KahunaException("create sheet first.")
        return self.feishu_sheet_token

    @feishu_token.setter
    def feishu_token(self, token: str):
        self.feishu_sheet_token = token

# TODO postgre 适配user对象的修改
class User():
    def __init__(self, qq: int, create_date: datetime, expire_date: datetime):
        self.user_qq = qq
        self.create_date = create_date
        self.expire_date = expire_date

        self.user_data = UserData(qq)
        self.main_character_id = None
        self.plan_max = 5
        self.user_data = UserData(qq)
        # self.user_data.load_self_data()

    # 不再user下进行数据库操作，交由manager执行
    @deprecated
    async def get_from_db(self):
        return await UserDBUtils.select_user_by_user_qq(self.user_qq)

    @deprecated
    def init_time(self):
        self.create_date = datetime.now()
        self.expire_date = datetime.now()

    @deprecated
    async def insert_to_db(self):
        user_obj = await self.get_from_db()
        if not user_obj:
            user_obj = UserDBUtils.get_obj()

        user_obj.user_qq = self.user_qq
        user_obj.create_date = self.create_date
        user_obj.expire_date = self.expire_date
        user_obj.main_character_id = self.main_character_id

        await UserDBUtils.save_obj(user_obj)
        await self.user_data.insert_to_db()

    @deprecated
    @property
    def info(self):
        res = (f"用户:{self.user_qq}\n"
                f"创建时间:{self.create_date}\n"
                f"到期时间:{self.expire_date}\n"
                f"剩余时间:{max(timedelta(), self.expire_date - datetime.now())}\n")
                # f"主角色：{CharacterManager.get_character_by_id(self.main_character_id).character_name}\n")
        if self.main_character_id != 0:
            res += f"主角色：{CharacterManager.get_character_by_id(self.main_character_id).character_name}\n"
        return res

    @deprecated
    @property
    def member_status(self):
        return self.expire_date > datetime.now()

    @deprecated
    async def add_member_time(self, day: int):
        add_time = timedelta(days=day)

        self.expire_date = max(self.expire_date, datetime.now()) + add_time
        await self.insert_to_db()
        return self.expire_date

    @deprecated
    async def clean_member_time(self):
        self.expire_date = datetime.now()
        await self.insert_to_db()

    @deprecated
    async def delete(self):
        user_obj = await UserDBUtils.select_user_by_user_qq(self.user_qq)
        if not user_obj:
            return

        await UserDBUtils.delete_user_by_user_qq(self.user_qq)

    @deprecated
    async def set_plan_product(self, plan_name: str, product: str, quantity: int):
        if plan_name not in self.user_data.plan:
            raise KahunaException(
                "计划不存在，请使用 .Inds plan create [plan_name] [bp_matcher] [st_matcher] [prod_block_matcher] 创建")
        self.user_data.plan[plan_name]["plan"].append([product, quantity])
        await self.user_data.insert_to_db()

    # TODO这是工业的功能，需要迁移
    @deprecated
    async def create_plan(self, plan_name: str,
                    bp_matcher, st_matcher, prod_block_matcher
                    ):
        if len(self.user_data.plan) - 3 >= self.plan_max:
            raise KahunaException(f"you can only create {self.plan_max} plans at most.")
        if plan_name not in self.user_data.plan:
            self.user_data.plan[plan_name] = {}

        self.user_data.plan[plan_name]["bp_matcher"] = bp_matcher.matcher_name
        self.user_data.plan[plan_name]["st_matcher"] = st_matcher.matcher_name
        self.user_data.plan[plan_name]["prod_block_matcher"] = prod_block_matcher.matcher_name
        self.user_data.plan[plan_name]["manucycletime"] = 24 # hour
        self.user_data.plan[plan_name]['reaccycletime'] = 24
        self.user_data.plan[plan_name]['container_block'] = []
        self.user_data.plan[plan_name]["plan"] = []
        self.user_data.plan[plan_name]["coop_user"] = []
        await self.user_data.insert_to_db()

    @deprecated
    async def delete_plan_prod(self, plan_name: str, index: int):
        if plan_name not in self.user_data.plan:
            raise KahunaException("plan not found.")
        if 0 <= index < len(self.user_data.plan[plan_name]["plan"]):
            self.user_data.plan[plan_name]["plan"].pop(index)
        await self.user_data.insert_to_db()

    @deprecated
    async def set_manu_cycle_time(self, plan_name: str, cycle_time: int):
        if plan_name not in self.user_data.plan:
            raise KahunaException("plan not found.")
        self.user_data.plan[plan_name]["manucycletime"] = cycle_time
        await self.user_data.insert_to_db()

    @deprecated
    async def set_reac_cycle_time(self, plan_name: str, cycle_time: int):
        if plan_name not in self.user_data.plan:
            raise KahunaException("plan not found.")
        self.user_data.plan[plan_name]["reaccycletime"] = cycle_time
        await self.user_data.insert_to_db()

    @deprecated
    async def delete_plan(self, plan_name: str):
        if plan_name not in self.user_data.plan:
            raise KahunaException("plan not found.")
        self.user_data.plan.pop(plan_name)
        await self.insert_to_db()

    @deprecated
    async def add_alias_character(self, character_id_list):
        for character_data in character_id_list:
            if character_data[0] not in self.user_data.alias:
                self.user_data.alias[character_data[0]] = character_data[1]
        await self.user_data.insert_to_db()

    @deprecated
    async def add_container_block(self, plan_name: str, container_id: int):
        if plan_name not in self.user_data.plan:
            raise KahunaException("plan not found.")
        if "container_block" not in self.user_data.plan[plan_name]:
            self.user_data.plan[plan_name]["container_block"] = []
        if container_id not in self.user_data.plan[plan_name]["container_block"]:
            self.user_data.plan[plan_name]["container_block"].append(container_id)
        await self.user_data.insert_to_db()

    @deprecated
    async def del_container_block(self, plan_name: str, container_id: int):
        if plan_name not in self.user_data.plan:
            raise KahunaException("plan not found.")
        if "container_block" not in self.user_data.plan[plan_name]:
            self.user_data.plan[plan_name]["container_block"] = []
        if container_id in self.user_data.plan[plan_name]["container_block"]:
            self.user_data.plan[plan_name]["container_block"].remove(container_id)
        await self.user_data.insert_to_db()

    @deprecated
    async def add_plan_coop_user(self, plan_name: str, user_qq: int):
        if plan_name not in self.user_data.plan:
            raise KahunaException("plan not found.")
        if user_qq not in set(self.user_data.plan[plan_name]["coop_user"]):
            self.user_data.plan[plan_name]["coop_user"].append(user_qq)
        await self.user_data.insert_to_db()

    @deprecated
    async def del_plan_coop_user(self, plan_name: str, user_qq: int):
        if plan_name not in self.user_data.plan:
            raise KahunaException("plan not found.")
        if user_qq in set(self.user_data.plan[plan_name]["coop_user"]):
            self.user_data.plan[plan_name]["coop_user"].remove(user_qq)
        await self.user_data.insert_to_db()
