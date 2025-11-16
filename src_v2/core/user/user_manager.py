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
from sqlalchemy import delete
from src_v2.core.database.model import (
    User as M_User,
    UserData as M_UserData,
    InvitCode as M_InvitCode,
    UserRoles as M_UserRoles,
    UserPermissions as M_UserPermissions,
    EveAuthedCharacter as M_EveAuthedCharacter,
    EveAliasCharacter as M_EveAliasCharacter
)
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveAuthedCharacterDBUtils,
    EveAliasCharacterDBUtils
)
from src_v2.core.database.kahuna_database_utils_v2 import EveAliasCharacterDBUtils
from src_v2.core.database.model import EveAliasCharacter as M_EveAliasCharacter
from src_v2.core.log import logger
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.model.EVE.character.character import Character
# import Exception
from src_v2.core.utils import KahunaException, SingletonMeta, get_beijing_utctime
from src_v2.core.permission.permission_manager import permission_manager

ESI_CACHE = TTLCache(maxsize=100, ttl=300)
class UserManager(metaclass=SingletonMeta):
    def __init__(self):
        self.init_status = False
        self.lock = Lock()

    async def create_user(self, user_name: AnyStr, passwd_hash: AnyStr) -> User:
        # 检查是否已存在
        if await UserDBUtils.select_user_by_user_name(user_name):
            raise KahunaException("用户已存在")

        # 信息入库
        #  创建user
        async with postgres_manager.get_session() as session:
            user_database_obj = M_User(
                user_name=user_name,
                create_date=get_beijing_utctime(datetime.now()),
                password_hash=passwd_hash
            )
            await UserDBUtils.save_obj(user_database_obj, session=session)
            #  创建userdata
            userdata_database_obj = M_UserData(
                user_name=user_name
            )
            await UserDataDBUtils.save_obj(userdata_database_obj, session=session)

            return User.from_obj(user_database_obj)

    async def get_user(self, user_name: AnyStr) -> User | None:
        user_obj = await UserDBUtils.select_user_by_user_name(user_name)
        if not user_obj:
            return None
        return User.from_obj(user_obj)

    async def get_password_hash(self, user_name: AnyStr):
        return await UserDBUtils.select_passwd_hash_by_user_name(user_name)

    async def get_user_data(self, user_name: AnyStr):
        user_data = await UserDataDBUtils.select_user_data_by_user_name(user_name)
        if not user_data:
            raise KahunaException("userdata 不存在")
        return user_data

    async def get_main_character_id(self, user_name: AnyStr):
        main_character_id = await redis_manager.redis.get(f"user_{user_name}:main_character_id")
        if main_character_id:
            return int(main_character_id)
        user_data = await UserDataDBUtils.select_user_data_by_user_name(user_name)
        if not user_data:
            raise KahunaException("用户数据不存在")
        if not user_data.main_character_id:
            raise KahunaException("用户主角色未设置")
        await redis_manager.redis.set(f"user_{user_name}:main_character_id", user_data.main_character_id, ex=60 * 60)
        return user_data.main_character_id

    async def set_main_character(self, user_name: str, main_character_name: str):
        character_obj = await EveAuthedCharacterDBUtils.select_character_by_character_name(main_character_name)
        if not character_obj:
            raise KahunaException("角色不存在")
        main_character_id = character_obj.character_id
        user_data = await UserDataDBUtils.select_user_data_by_user_name(user_name)
        if not user_data:
            raise KahunaException("用户数据不存在")
        user_data.main_character_id = main_character_id
        await UserDataDBUtils.merge(user_data)

        character = Character.from_db_obj(character_obj)
        await character.refresh_character_token()
        if character.director:
            user_role = await permission_manager.get_user_roles(user_name)
            if "EveCorpDirector" not in user_role:
                await permission_manager.add_role_to_user(user_name, "EveCorpDirector")
        else:
            user_role = await permission_manager.get_user_roles(user_name)
            if "EveCorpDirector" in user_role:
                await permission_manager.remove_role_from_user(user_name, "EveCorpDirector")

        await redis_manager.redis.set(f"user_{user_name}:main_character_id", main_character_id, ex=60 * 60)

    async def update_same_title_alias_characters(self, character_list: list, main_character_id):
        for character in character_list:
            alias_character = await EveAliasCharacterDBUtils.select_alias_character_by_character_id(character.character_id)
            if not alias_character:
                await EveAliasCharacterDBUtils.save_obj(M_EveAliasCharacter(
                    alias_character_id=character.character_id,
                    main_character_id=main_character_id,
                    character_name=character.name,
                    enabled=False
                ))

    async def get_alias_character_list(self, main_character_id: int):
        alias_character_list = []
        async for alias_character in await EveAliasCharacterDBUtils.select_all_by_main_character_id(main_character_id):
            alias_character_list.append(alias_character)
        return alias_character_list

    def user_exists(self, user_name: AnyStr) -> bool:
        user_obj = UserDBUtils.select_user_by_user_name(user_name)
        if not user_obj:
            return False
        return True

    # VIP系统挂起
    # @classmethod
    # def add_member_time(cls, qq: int, days: int):
    #     if (user := cls.user_dict.get(qq, None)) is None:
    #         raise KahunaException("用户不存在。")
    #     return user.add_member_time(days)


    async def delete_user(self, user_name: AnyStr):
        async with postgres_manager.get_session() as session:
            # 删除userdata
            await UserDataDBUtils.delete_user_data_by_user_name(user_name, session=session)
            # 删除以下表格的用户数据
            # InvitCode
            async with postgres_manager.get_session() as session:
                stmt_invit_code = delete(M_InvitCode).where(M_InvitCode.user_name == user_name)
                await session.execute(stmt_invit_code)  # type: ignore
                # UserRoles
                stmt_user_roles = delete(M_UserRoles).where(M_UserRoles.user_name == user_name)
                await session.execute(stmt_user_roles)  # type: ignore
                # UserPermissions
                stmt_user_permissions = delete(M_UserPermissions).where(M_UserPermissions.user_name == user_name)
                await session.execute(stmt_user_permissions)  # type: ignore

                # EveAuthedCharacter
                stmt_eve_authed_character = delete(M_EveAuthedCharacter).where(M_EveAuthedCharacter.owner_user_name == user_name)
                await session.execute(stmt_eve_authed_character)  # type: ignore

            # 删除user
            await UserDBUtils.delete_user_by_user_username(user_name, session=session)
        
    #
    # async def clean_member_time(cls, qq: int) -> User:
    #     if (user := cls.user_dict.get(qq, None)) is None:
    #         raise KahunaException("用户不存在。")
    #     await user.clean_member_time()
    #
    #     return user

    async def get_users_list(self):
        users = []
        async for user in await UserDBUtils.select_all():
            users.append(user)
        return users