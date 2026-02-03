import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from quart import Blueprint, g, jsonify, request

from src_v2.backend.api.permission_required import permission_required
from src_v2.backend.auth import auth_required
from src_v2.core.database.kahuna_database_utils_v2 import (
    PermissionsDBUtils,
    RoleHierarchyDBUtils,
    RolePermissionsDBUtils,
    RolesDBUtils,
    UserDBUtils,
    UserRolesDBUtils,
)
from src_v2.core.log import logger
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.utils import KahunaException

api_permission_bp = Blueprint(
    'api_permission', __name__, url_prefix='/api/permission')


# 请求数据模型
@dataclass
class CreateRoleRequest:
    """创建角色请求"""
    roleName: str
    roleDescription: Optional[str] = None


@dataclass
class DeleteRoleRequest:
    """删除角色请求"""
    roleName: str
    includeChildren: bool = False


@dataclass
class CreatePermissionRequest:
    """创建权限请求"""
    permissionName: str
    permissionDescription: Optional[str] = None


@dataclass
class DeletePermissionRequest:
    """删除权限请求"""
    permissionName: str
    force: bool = False


@dataclass
class AddRoleHierarchyRequest:
    """添加角色层级关系请求"""
    parentRoleName: str
    childRoleName: str


@dataclass
class DeleteRoleHierarchyRequest:
    """删除角色层级关系请求"""
    hierarchyPairs: List[Dict[str, str]]


@dataclass
class AddRoleToUserRequest:
    """为用户添加角色请求"""
    userName: str
    roleName: str


@dataclass
class RemoveRoleFromUserRequest:
    """移除用户角色请求"""
    userName: str
    roleName: str


@dataclass
class AddPermissionToRoleRequest:
    """为角色添加权限请求"""
    roleName: str
    permissionName: str


@dataclass
class RemovePermissionFromRoleRequest:
    """移除角色权限请求"""
    roleName: str
    permissionName: str


# 响应数据模型
@dataclass
class RoleItem:
    """角色项"""
    roleName: str
    roleDescription: Optional[str] = None


@dataclass
class RolesResponse:
    """角色列表响应"""
    status: int
    data: List[RoleItem]


@dataclass
class PermissionItem:
    """权限项"""
    permissionName: str
    permissionDescription: Optional[str] = None


@dataclass
class PermissionsResponse:
    """权限列表响应"""
    status: int
    data: List[PermissionItem]


@dataclass
class MessageResponse:
    """消息响应"""
    status: int
    message: str


@dataclass
class RoleDataResponse:
    """角色数据响应"""
    status: int
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@dataclass
class PermissionUsageResponse:
    """权限使用情况响应"""
    status: int
    data: Dict[str, Any]


@dataclass
class RoleHierarchyResponse:
    """角色层级关系响应"""
    status: int
    data: Dict[str, List[str]]


@dataclass
class UserRolesResponse:
    """用户角色响应"""
    status: int
    data: List[str]


@dataclass
class UserItem:
    """用户项"""
    userName: str
    createDate: Optional[str] = None


@dataclass
class UsersResponse:
    """用户列表响应"""
    status: int
    data: List[UserItem]


@dataclass
class RolePermissionsResponse:
    """角色权限响应"""
    status: int
    data: List[str]


@dataclass
class ErrorResponse:
    """错误响应"""
    status: int
    message: str


# ==================== Role Management ====================

@api_permission_bp.route("/roles", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
# @validate_response(RolesResponse)
async def get_all_roles():
    """
    获取所有角色

    获取系统中所有角色的列表，包括角色名称和描述。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回角色列表
            - status: 状态码 (200)
            - data: 角色列表，每个元素包含角色名称和描述 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "roleName": "admin",
                    "roleDescription": "管理员角色"
                }
            ]
        }
    """
    try:
        roles = []
        async for role in await RolesDBUtils.select_all():
            roles.append({
                "roleName": role.role_name,
                "roleDescription": role.role_description
            })
        return {"status": 200, "data": roles}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取所有角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取所有角色失败"}), 500


@api_permission_bp.route("/roles", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
# @validate_request(CreateRoleRequest)
# @validate_response(RoleDataResponse)
async def create_role():
    """
    创建角色

    创建新的角色。角色名称不能为空。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Request Body:
        - roleName (string, required): 角色名称
        - roleDescription (string, optional): 角色描述

    Responses:
        200: 创建成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
            - data: 创建的角色信息 (object)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "roleName": "editor",
            "roleDescription": "编辑者角色"
        }

    Example Response:
        {
            "status": 200,
            "message": "角色创建成功",
            "data": {
                "roleName": "editor",
                "roleDescription": "编辑者角色"
            }
        }
    """
    try:
        data = await request.get_json()
        role_name = data.get("roleName")
        role_description = data.get("roleDescription")

        if not role_name:
            return jsonify({"status": 400, "message": "角色名称不能为空"}), 400

        role_obj = await permission_manager.create_role(
            role_name=role_name,
            role_description=role_description
        )

        return {
            "status": 200,
            "message": "角色创建成功",
            "data": {
                "roleName": role_obj.role_name,
                "roleDescription": role_obj.role_description
            }
        }
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"创建角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建角色失败"}), 500


@api_permission_bp.route("/roles", methods=["DELETE"])
@auth_required
@permission_required(["admin:write"])
# @validate_request(DeleteRoleRequest)
# @validate_response(MessageResponse)
async def delete_role():
    """
    删除角色

    删除指定的角色。可以选择是否同时删除子角色。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Request Body:
        - roleName (string, required): 角色名称
        - includeChildren (boolean, optional): 是否同时删除子角色，默认false

    Responses:
        200: 删除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "roleName": "editor",
            "includeChildren": false
        }

    Example Response:
        {
            "status": 200,
            "message": "角色删除成功"
        }
    """
    try:
        data = await request.get_json()
        role_name = data.get("roleName")
        include_children = data.get("includeChildren", False)

        if not role_name:
            return jsonify({"status": 400, "message": "角色名称不能为空"}), 400

        await permission_manager.delete_role(role_name, include_children=include_children)

        return {"status": 200, "message": "角色删除成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除角色失败"}), 500


# ==================== Permission Management ====================

@api_permission_bp.route("/permissions", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
# @validate_response(PermissionsResponse)
async def get_all_permissions():
    """
    获取所有权限

    获取系统中所有权限的列表，包括权限名称和描述。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回权限列表
            - status: 状态码 (200)
            - data: 权限列表，每个元素包含权限名称和描述 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "permissionName": "admin:read",
                    "permissionDescription": "管理员读取权限"
                }
            ]
        }
    """
    try:
        permissions = []
        async for permission in await PermissionsDBUtils.select_all():
            permissions.append({
                "permissionName": permission.permission_name,
                "permissionDescription": permission.permission_description
            })
        return {"status": 200, "data": permissions}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取所有权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取所有权限失败"}), 500


@api_permission_bp.route("/permissions", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
# @validate_request(CreatePermissionRequest)
# @validate_response(RoleDataResponse)
async def create_permission():
    """
    创建权限

    创建新的权限。权限名称不能为空。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Request Body:
        - permissionName (string, required): 权限名称
        - permissionDescription (string, optional): 权限描述

    Responses:
        200: 创建成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
            - data: 创建的权限信息 (object)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "permissionName": "resource:write",
            "permissionDescription": "资源写入权限"
        }

    Example Response:
        {
            "status": 200,
            "message": "权限创建成功",
            "data": {
                "permissionName": "resource:write",
                "permissionDescription": "资源写入权限"
            }
        }
    """
    try:
        data = await request.get_json()
        permission_name = data.get("permissionName")
        permission_description = data.get("permissionDescription")

        if not permission_name:
            return jsonify({"status": 400, "message": "权限名称不能为空"}), 400

        permission_obj = await permission_manager.create_permission(
            permission_name=permission_name,
            permission_description=permission_description
        )

        return jsonify({
            "status": 200,
            "message": "权限创建成功",
            "data": {
                "permissionName": permission_obj.permission_name,
                "permissionDescription": permission_obj.permission_description
            }
        })
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"创建权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建权限失败"}), 500


@api_permission_bp.route("/permissions/<permission_name>/usage", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
# @validate_response(PermissionUsageResponse)
async def get_permission_usage(permission_name: str):
    """
    获取权限的使用情况（被哪些用户和角色使用）

    获取指定权限的使用情况，包括被哪些用户和角色使用。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Parameters:
        - permission_name (path, string, required): 权限名称

    Responses:
        200: 成功返回使用情况
            - status: 状态码 (200)
            - data: 包含用户和角色使用情况的对象
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {
                "users": ["user1", "user2"],
                "roles": ["admin", "editor"]
            }
        }
    """
    try:
        usage_info = await permission_manager.get_permission_usage(permission_name)
        return {"status": 200, "data": usage_info}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取权限使用情况失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取权限使用情况失败"}), 500


@api_permission_bp.route("/permissions", methods=["DELETE"])
@auth_required
@permission_required(["admin:write"])
# @validate_request(DeletePermissionRequest)
# @validate_response(MessageResponse)
async def delete_permission():
    """
    删除权限

    删除指定的权限。如果权限正在被使用，需要设置force=true强制删除。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Request Body:
        - permissionName (string, required): 权限名称
        - force (boolean, optional): 是否强制删除，默认false

    Responses:
        200: 删除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "permissionName": "resource:write",
            "force": false
        }

    Example Response:
        {
            "status": 200,
            "message": "权限删除成功"
        }
    """
    try:
        data = await request.get_json()
        permission_name = data.get("permissionName")
        force = data.get("force", False)

        if not permission_name:
            return jsonify({"status": 400, "message": "权限名称不能为空"}), 400

        await permission_manager.delete_permission(permission_name, force=force)

        return {"status": 200, "message": "权限删除成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除权限失败"}), 500


# ==================== Role Hierarchy Management ====================

@api_permission_bp.route("/roles/<role_name>/hierarchy", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
# @validate_response(RoleHierarchyResponse)
async def get_role_hierarchy(role_name: str):
    """
    获取角色的层级关系（父角色和子角色）

    获取指定角色的层级关系，包括父角色和子角色列表。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Parameters:
        - role_name (path, string, required): 角色名称

    Responses:
        200: 成功返回层级关系
            - status: 状态码 (200)
            - data: 包含父角色和子角色列表的对象
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {
                "parentRoles": ["admin"],
                "childRoles": ["editor", "viewer"]
            }
        }
    """
    try:
        parent_roles = await permission_manager.get_parent_roles(role_name)
        child_roles = await permission_manager.get_child_roles(role_name)

        return jsonify({
            "status": 200,
            "data": {
                "parentRoles": parent_roles,
                "childRoles": child_roles
            }
        })
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取角色层级关系失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取角色层级关系失败"}), 500


@api_permission_bp.route("/roles/hierarchy", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
# @validate_request(AddRoleHierarchyRequest)
# @validate_response(MessageResponse)
async def add_role_hierarchy():
    """
    添加角色层级关系

    添加角色之间的层级关系，建立父子关系。父角色和子角色不能相同。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Request Body:
        - parentRoleName (string, required): 父角色名称
        - childRoleName (string, required): 子角色名称

    Responses:
        200: 添加成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "parentRoleName": "admin",
            "childRoleName": "editor"
        }

    Example Response:
        {
            "status": 200,
            "message": "角色层级关系添加成功"
        }
    """
    try:
        data = await request.get_json()
        parent_role_name = data.get("parentRoleName")
        child_role_name = data.get("childRoleName")

        if not parent_role_name or not child_role_name:
            return jsonify({"status": 400, "message": "父角色和子角色名称不能为空"}), 400

        if parent_role_name == child_role_name:
            return jsonify({"status": 400, "message": "父角色和子角色不能相同"}), 400

        from src_v2.core.database.model import RoleHierarchy as M_RoleHierarchy
        hierarchy_obj = M_RoleHierarchy(
            parent_role_name=parent_role_name,
            child_role_name=child_role_name
        )
        await RoleHierarchyDBUtils.save_obj(hierarchy_obj)

        return {"status": 200, "message": "角色层级关系添加成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"添加角色层级关系失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加角色层级关系失败"}), 500


@api_permission_bp.route("/roles/hierarchy", methods=["DELETE"])
@auth_required
@permission_required(["admin:write"])
# @validate_request(DeleteRoleHierarchyRequest)
# @validate_response(MessageResponse)
async def delete_role_hierarchy():
    """
    删除角色层级关系

    批量删除角色层级关系。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Request Body:
        - hierarchyPairs (array, required): 层级关系对列表，每个元素包含parentRoleName和childRoleName

    Responses:
        200: 删除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "hierarchyPairs": [
                {
                    "parentRoleName": "admin",
                    "childRoleName": "editor"
                }
            ]
        }

    Example Response:
        {
            "status": 200,
            "message": "角色层级关系删除成功"
        }
    """
    try:
        data = await request.get_json()
        hierarchy_pairs = data.get("hierarchyPairs", [])

        if not hierarchy_pairs:
            return jsonify({"status": 400, "message": "层级关系列表不能为空"}), 400

        await permission_manager.delete_role_hierarchys(hierarchy_pairs)

        return {"status": 200, "message": "角色层级关系删除成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除角色层级关系失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除角色层级关系失败"}), 500


# ==================== User Role Management ====================

@api_permission_bp.route("/users/<user_name>/roles", methods=["GET"])
@auth_required
@permission_required(["admin:read"])
# @validate_response(UserRolesResponse)
async def get_user_roles(user_name: str):
    """
    获取用户的所有角色

    获取指定用户的所有角色列表（包括直接分配和继承的角色）。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Parameters:
        - user_name (path, string, required): 用户名

    Responses:
        200: 成功返回角色列表
            - status: 状态码 (200)
            - data: 角色名称列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": ["admin", "editor"]
        }
    """
    try:
        roles = await permission_manager.get_user_roles(user_name)
        return {"status": 200, "data": roles}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取用户角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取用户角色失败"}), 500


@api_permission_bp.route("/users/roles", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
# @validate_request(AddRoleToUserRequest)
# @validate_response(MessageResponse)
async def add_role_to_user():
    """
    为用户添加角色

    为指定用户添加角色。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Request Body:
        - userName (string, required): 用户名
        - roleName (string, required): 角色名称

    Responses:
        200: 添加成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "userName": "user1",
            "roleName": "editor"
        }

    Example Response:
        {
            "status": 200,
            "message": "用户角色添加成功"
        }
    """
    try:
        data = await request.get_json()
        user_name = data.get("userName")
        role_name = data.get("roleName")

        if not user_name or not role_name:
            return jsonify({"status": 400, "message": "用户名和角色名称不能为空"}), 400

        await permission_manager.add_role_to_user(user_name, role_name)

        return {"status": 200, "message": "用户角色添加成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"添加用户角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加用户角色失败"}), 500


@api_permission_bp.route("/users/roles", methods=["DELETE"])
@auth_required
@permission_required(["admin:write"])
# @validate_request(RemoveRoleFromUserRequest)
# @validate_response(MessageResponse)
async def remove_role_from_user():
    """
    移除用户的角色

    移除指定用户的角色。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Request Body:
        - userName (string, required): 用户名
        - roleName (string, required): 角色名称

    Responses:
        200: 移除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "userName": "user1",
            "roleName": "editor"
        }

    Example Response:
        {
            "status": 200,
            "message": "用户角色移除成功"
        }
    """
    try:
        data = await request.get_json()
        user_name = data.get("userName")
        role_name = data.get("roleName")

        if not user_name or not role_name:
            return jsonify({"status": 400, "message": "用户名和角色名称不能为空"}), 400

        await permission_manager.remove_role_from_user(user_name, role_name)

        return {"status": 200, "message": "用户角色移除成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"移除用户角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "移除用户角色失败"}), 500


@api_permission_bp.route("/users", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
# @validate_response(UsersResponse)
async def get_all_users():
    """
    获取所有用户

    获取系统中所有用户的列表，包括用户名和创建日期。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回用户列表
            - status: 状态码 (200)
            - data: 用户列表，每个元素包含用户名和创建日期 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "userName": "user1",
                    "createDate": "2024-01-01T00:00:00"
                }
            ]
        }
    """
    try:
        users = []
        async for user in await UserDBUtils.select_all():
            users.append({
                "userName": user.user_name,
                "createDate": user.create_date.isoformat() if user.create_date else None
            })
        return {"status": 200, "data": users}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取所有用户失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取所有用户失败"}), 500


# ==================== Role Permission Management ====================

@api_permission_bp.route("/roles/<role_name>/permissions", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
# @validate_response(RolePermissionsResponse)
async def get_role_permissions(role_name: str):
    """
    获取角色的所有权限

    获取指定角色的所有权限列表（包括直接分配和继承的权限）。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Parameters:
        - role_name (path, string, required): 角色名称

    Responses:
        200: 成功返回权限列表
            - status: 状态码 (200)
            - data: 权限名称列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": ["admin:read", "admin:write"]
        }
    """
    try:
        permissions = await permission_manager.get_role_permissions(role_name)
        return {"status": 200, "data": permissions}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取角色权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取角色权限失败"}), 500


@api_permission_bp.route("/roles/permissions", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
# @validate_request(AddPermissionToRoleRequest)
# @validate_response(MessageResponse)
async def add_permission_to_role():
    """
    为角色添加权限

    为指定角色添加权限。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Request Body:
        - roleName (string, required): 角色名称
        - permissionName (string, required): 权限名称

    Responses:
        200: 添加成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "roleName": "editor",
            "permissionName": "resource:write"
        }

    Example Response:
        {
            "status": 200,
            "message": "角色权限添加成功"
        }
    """
    try:
        data = await request.get_json()
        role_name = data.get("roleName")
        permission_name = data.get("permissionName")

        if not role_name or not permission_name:
            return jsonify({"status": 400, "message": "角色名称和权限名称不能为空"}), 400

        await permission_manager.add_permissions_to_role(role_name, permission_name)

        return {"status": 200, "message": "角色权限添加成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"添加角色权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加角色权限失败"}), 500


@api_permission_bp.route("/roles/permissions", methods=["DELETE"])
@auth_required
@permission_required(["admin:write"])
# @validate_request(RemovePermissionFromRoleRequest)
# @validate_response(MessageResponse)
async def remove_permission_from_role():
    """
    移除角色的权限

    移除指定角色的权限。

    Tags:
        - 权限管理

    Security:
        - Bearer: []

    Request Body:
        - roleName (string, required): 角色名称
        - permissionName (string, required): 权限名称

    Responses:
        200: 移除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "roleName": "editor",
            "permissionName": "resource:write"
        }

    Example Response:
        {
            "status": 200,
            "message": "角色权限移除成功"
        }
    """
    try:
        data = await request.get_json()
        role_name = data.get("roleName")
        permission_name = data.get("permissionName")

        if not role_name or not permission_name:
            return jsonify({"status": 400, "message": "角色名称和权限名称不能为空"}), 400

        await permission_manager.remove_permissions_from_role(role_name, permission_name)

        return {"status": 200, "message": "角色权限移除成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"移除角色权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "移除角色权限失败"}), 500
