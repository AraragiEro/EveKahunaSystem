from datetime import datetime
from cachetools import TTLCache
from asyncio import Lock

from .user import User
# from ..database_server.model import User as M_User
from ..database_server.sqlalchemy.kahuna_database_utils import UserDBUtils
from ..character_server.character_manager import CharacterManager
from ..log_server import logger

# import Exception
from ...utils import KahunaException

ESI_CACHE = TTLCache(maxsize=100, ttl=300)
class UserManager():
    init_status = False
    lock = Lock()
    user_dict = dict() # {qq_id: User()}

    @classmethod
    async def init(cls):
        await cls.init_user_dict()

    @classmethod
    async def init_user_dict(cls):
        # TODO postgre 不再全量读取到内存，只保存热点数据
        if not cls.init_status:

            user_list = await UserDBUtils.select_all()
            for user in user_list:
                usr_obj = User(
                    qq=user.user_qq
                )
                await usr_obj.user_data.load_self_data()
                if user.main_character_id:
                    usr_obj.main_character_id = user.main_character_id
                cls.user_dict[usr_obj.user_qq] = usr_obj
                logger.info(f'初始化用户 {user.user_qq} 成功。')
        cls.init_status = True
        logger.info(f"init user list complete. {id(cls)}")

    @classmethod
    def get_main_character_id(cls, qq: int):
        user = cls.user_dict.get(qq, None)
        if not user:
            raise KahunaException("用户主角色不存在，请先注册和设置主角色。")
        return user.main_character_id

    @classmethod
    async def set_main_character(cls, qq: int, main_character: str):
        user = cls.get_user(qq)
        main_character = CharacterManager.get_character_by_name_qq(main_character, qq)
        user.main_character_id = main_character.character_id

        await user.insert_to_db()

    @classmethod
    async def create_user(cls, qq: int) -> User:
        if (user := cls.user_dict.get(qq, None)) is None:
            user = User(qq=qq, create_date=datetime.now(), expire_date=datetime.now())
            await user.user_data.load_self_data()
        user.init_time()
        await user.insert_to_db()
        cls.user_dict[user.user_qq] = user

        return user

    @classmethod
    def user_exists(cls, qq: int) -> bool:
        return qq in cls.user_dict.keys()

    @classmethod
    def get_user(cls, qq: int) -> User:
        if (user := cls.user_dict.get(qq, None)) is None:
            raise KahunaException("用户不存在。")
        return user

    @classmethod
    def add_member_time(cls, qq: int, days: int):
        if (user := cls.user_dict.get(qq, None)) is None:
            raise KahunaException("用户不存在。")
        return user.add_member_time(days)

    @classmethod
    async def delete_user(cls, qq: int):
        if (user := cls.user_dict.get(qq, None)) is None:
            return
        await user.delete()
        cls.user_dict.pop(qq)

    @classmethod
    async def clean_member_time(cls, qq: int) -> User:
        if (user := cls.user_dict.get(qq, None)) is None:
            raise KahunaException("用户不存在。")
        await user.clean_member_time()

        return user

    @classmethod
    def get_users_list(cls):
        return [user for user in cls.user_dict.values()]