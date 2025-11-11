from typing import AnyStr, List
from datetime import datetime, timedelta
import json
from warnings import deprecated

from src_v2.core.database.kahuna_database_utils_v2 import (
    UserDataDBUtils,
    UserDBUtils,
    UserRolesDBUtils,
    UserPermissionsDBUtils
)
from src_v2.core.database.connect_manager import redis_manager as rdm
from src_v2.core.utils import KahunaException

# TODO postgre 适配user对象的修改
class User():
    def __init__(self, user_name: str):
        self.user_name = user_name
        # self.user_data.load_self_data()

    @classmethod
    def from_obj(cls, user_obj):
        return cls(user_name=user_obj.user_name)

    @property
    async def roles(self) -> list[str]:
        # 获取 roles
        roles = await rdm.redis.lrange(f"l:user:roles:{self.user_name}", 0, -1)
        if not roles:
            role_names = []
            async for role_obj in await UserRolesDBUtils.select_user_roles_by_user_name(self.user_name):
                role_names.append(role_obj.role_name)
            if role_names:
                await rdm.redis.rpush(f"l:user:roles:{self.user_name}", *role_names)
                await rdm.redis.expire(f"l:user:roles:{self.user_name}", 60 * 60)
            roles = role_names
        return roles

    @property
    async def permissions(self) -> list[str]:
        # 获取 permissions
        permissions = await rdm.redis.lrange(f"l:user:permissions:{self.user_name}", 0, -1)
        if not permissions: 
            permission_names = []
            async for permission_obj in await UserPermissionsDBUtils.select_user_permissions_by_user_name(self.user_name):
                permission_names.append(permission_obj.permission_name)
            if permission_names:
                await rdm.redis.rpush(f"l:user:permissions:{self.user_name}", *permission_names)
                await rdm.redis.expire(f"l:user:permissions:{self.user_name}", 60 * 60)
            permissions = permission_names
        return permissions
