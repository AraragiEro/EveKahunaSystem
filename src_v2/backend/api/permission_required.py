import datetime
import jwt
from functools import wraps
from quart import request, jsonify, g
from quart import current_app as app
from src_v2.core.permission.permission_manager import permission_manager

from src_v2.core.log import logger

def permission_required(req_permissions: list[str]):
    """权限装饰器（带参数）"""
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            # 在请求执行时检查权限
            user_id = g.current_user['user_id']
            for permission in req_permissions:
                per_name = permission.split(":")[0]
                per_action = permission.split(":")[1]

            roles = await permission_manager.get_user_roles(user_id)
            permissions = []
            for role in roles:
                role_permissions = await permission_manager.get_role_permissions(role)
                permissions.extend(role_permissions)
            user_permissions = await permission_manager.get_user_permissions(user_id)
            permissions.extend(user_permissions)

            # 检查permission，只有write的权限添加read
            permissions_set = set(permissions)
            for perm in list(permissions_set):
                if perm.endswith(':write'):
                    per_name = perm.rsplit(':', 1)[0]
                    read_perm = f"{per_name}:read"
                    if read_perm not in permissions_set:
                        permissions_set.add(read_perm)
            permissions = list(permissions_set)

            permission_access = all(perm in permissions for perm in req_permissions)

            # 检查权限
            if not permission_access:
                logger.error(f"{f.__name__}: 用户 {user_id} 权限不足，缺少权限 {req_permissions}")
                return jsonify({'error': '权限不足'}), 403
            
            return await f(*args, **kwargs)
        return decorated_function
    return decorator

def role_required(req_roles: list[str], res_code = 403, message: str = '权限不足'):
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            user_id = g.current_user['user_id']
            # 获取用户直接拥有的角色
            direct_roles = await permission_manager.get_user_roles(user_id)
            
            # 获取所有角色（直接角色 + 所有子角色）
            all_roles = set(direct_roles)
            for role in direct_roles:
                # 递归获取该角色的所有子角色
                descendant_roles = await permission_manager.get_all_descendant_roles(role)
                all_roles.update(descendant_roles)
            
            # 获取vip等级
            vip_state = await permission_manager.get_vip_state(user_id)
            if vip_state:
                logger.info(f"vip_state: {vip_state.vip_level}")
                all_roles.add(vip_state.vip_level)
            else:
                logger.info(f"vip_state: None")

            # 检查所需的角色是否在扩展后的角色集合中
            role_access = all(role in all_roles for role in req_roles)
            logger.info(f"all_roles: {all_roles}")
            logger.info(f"req_roles: {req_roles}")
            if not role_access:
                if "vip_alpha" in req_roles or "vip_omega" in req_roles:
                    return jsonify({'message': message}), res_code
                else:
                    logger.error(f"{f.__name__}: 用户 {user_id} 权限不足，缺少角色 {req_roles}")
                    return jsonify({'message': message}), res_code
            return await f(*args, **kwargs)
        return decorated_function
    return decorator