from datetime import datetime
from typing import AnyStr

from cachetools import TTLCache
from asyncio import Lock
from uuid import uuid4

from .user import User
from src_v2.core.database.kahuna_database_utils_v2 import (
    UserDBUtils,
    UserDataDBUtils
)
from src_v2.core.database.connect_manager import postgres_manager, redis_manager
from src_v2.core.database.model import User as M_User
from src_v2.core.database.model import UserData as M_UserData
# from src_v2.core.database.kahuna_database_utils import UserDBUtils
# from ..character_server.character_manager import CharacterManager
from src_v2.core.log import logger

# import Exception
from src_v2.core.utils import KahunaException, SingletonMeta, get_beijing_utctime

ESI_CACHE = TTLCache(maxsize=100, ttl=300)
class UserManager(metaclass=SingletonMeta):
    def __init__(self):
        self.init_status = False
        self.lock = Lock()
        self.user_dict = {} # {qq_id: User()}

    async def init(self):
        await self.init_user_dict()

    async def init_user_dict(self):
        # TODO postgre 不再全量读取到内存，只保存热点数据
        if not self.init_status:

            user_list = await UserDBUtils.select_all()
            for user in user_list:
                usr_obj = User(
                    user_name=user.user_name,
                    user_role=user.user_role,
                    user_permission=user.user_permission
                )
                self.user_dict[usr_obj.user_name] = usr_obj
                logger.info(f'初始化用户 {user.user_name} 成功。')
        self.init_status = True
        logger.info(f"init user list complete. {id(self)}")

    async def create_user(self, user_name: AnyStr, passwd_hash: AnyStr) -> User:
        # 检查是否已存在
        if await UserDBUtils.select_user_where_user_name(user_name):
            raise KahunaException("用户已存在")

        # 信息入库
        #  创建user
        async with postgres_manager.get_session() as session:
            user_database_obj = M_User(
                user_name=user_name,
                create_date=get_beijing_utctime(datetime.now()),
                password_hash=passwd_hash,
                user_role="user",
                user_permission=["member"]
            )
            await UserDBUtils.save_obj(user_database_obj, session=session)
            #  创建userdata
            userdata_database_obj = M_UserData(
                user_name=user_name,
                user_qq=None,
                main_character_id=None
            )
            await UserDataDBUtils.save_obj(userdata_database_obj, session=session)

            # 存入dict
            self.user_dict[user_name] = User(user_name=user_name, user_role="user", user_permission=["member"])

            return self.user_dict[user_name]

    async def get_user(self, user_name: AnyStr) -> User | None:
        if not self.init_status:
            await self.init_user_dict()
        return self.user_dict.get(user_name, None)

    async def get_password_hash(self, user_name: AnyStr):
        return await UserDBUtils.select_passwd_hash_where_user_name(user_name)


    # TODO 迁移到CharacerManager
    # async def get_main_character_id(self, user_name: AnyStr):
    #     if not self.user_dict.get(user_name, None):
    #         raise KahunaException("用户不存在")
    #
    #     # 从redis中提取
    #     redis = redis_manager.get_redis()
    #     userdata_cache = await redis.hgetall(f"user_data:{user_name}")
    #     if userdata_cache:
    #         return userdata_cache["main_character_id"]
    #
    #     user_data = await UserDataDBUtils.select_all_where_user_name(user_name)
    #     if not user_data:
    #         raise KahunaException("userdata 不存在")
    #     await redis.hset(f"user_data:{user_name}", mapping={
    #         "user_name": user_name,
    #         "user_qq": user_data.user_qq
    #     })
    #
    #     return user_data.main_character_id

    # TODO 迁移到CharacerManager
    # async def set_main_character(self, user_name: AnyStr, main_character: str):
    #     user = cls.get_user(qq)
    #     main_character = CharacterManager.get_character_by_name_qq(main_character, qq)
    #     user.main_character_id = main_character.character_id
    #
    #     await user.insert_to_db()

    def user_exists(self, user_name: AnyStr) -> bool:
        return user_name in self.user_dict.keys()

    # TODO VIP系统挂起
    # @classmethod
    # def add_member_time(cls, qq: int, days: int):
    #     if (user := cls.user_dict.get(qq, None)) is None:
    #         raise KahunaException("用户不存在。")
    #     return user.add_member_time(days)


    async def delete_user(self, user_name: AnyStr):
        if self.user_dict.get(user_name, None) is None:
            return

        async with postgres_manager.get_session() as session:
            # 删除user
            await UserDBUtils.delete_user_where_user_username(user_name, session=session)
            # 删除userdata
            await UserDataDBUtils.delete_userdata_where_username(user_name, session=session)
            # 从内存移除
            self.user_dict.pop(user_name)

    #
    # async def clean_member_time(cls, qq: int) -> User:
    #     if (user := cls.user_dict.get(qq, None)) is None:
    #         raise KahunaException("用户不存在。")
    #     await user.clean_member_time()
    #
    #     return user

    def get_users_list(self):
        return [user for user in self.user_dict.values()]