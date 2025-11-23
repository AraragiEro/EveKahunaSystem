from quart import request, jsonify, g, Blueprint
from src_v2.backend.auth import auth_required
from src_v2.backend.api.permission_required import permission_required
from src_v2.core.log import logger
import traceback
from src_v2.core.utils import KahunaException
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.database.kahuna_database_utils_v2 import (
    RolesDBUtils,
    PermissionsDBUtils,
    UserRolesDBUtils,
    RolePermissionsDBUtils,
    RoleHierarchyDBUtils,
    UserDBUtils
)

api_permission_bp = Blueprint('api_permission', __name__, url_prefix='/api/permission')


# ==================== Role Management ====================

@api_permission_bp.route("/roles", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
async def get_all_roles():
    """获取所有角色"""
    try:
        roles = []
        async for role in await RolesDBUtils.select_all():
            roles.append({
                "roleName": role.role_name,
                "roleDescription": role.role_description
            })
        return jsonify({"status": 200, "data": roles})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取所有角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取所有角色失败"}), 500


@api_permission_bp.route("/roles", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
async def create_role():
    """创建角色"""
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
        
        return jsonify({
            "status": 200,
            "message": "角色创建成功",
            "data": {
                "roleName": role_obj.role_name,
                "roleDescription": role_obj.role_description
            }
        })
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"创建角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建角色失败"}), 500


@api_permission_bp.route("/roles", methods=["DELETE"])
@auth_required
@permission_required(["admin:write"])
async def delete_role():
    """删除角色"""
    try:
        data = await request.get_json()
        role_name = data.get("roleName")
        include_children = data.get("includeChildren", False)
        
        if not role_name:
            return jsonify({"status": 400, "message": "角色名称不能为空"}), 400
        
        await permission_manager.delete_role(role_name, include_children=include_children)
        
        return jsonify({"status": 200, "message": "角色删除成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"删除角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除角色失败"}), 500


# ==================== Permission Management ====================

@api_permission_bp.route("/permissions", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
async def get_all_permissions():
    """获取所有权限"""
    try:
        permissions = []
        async for permission in await PermissionsDBUtils.select_all():
            permissions.append({
                "permissionName": permission.permission_name,
                "permissionDescription": permission.permission_description
            })
        return jsonify({"status": 200, "data": permissions})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取所有权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取所有权限失败"}), 500


@api_permission_bp.route("/permissions", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
async def create_permission():
    """创建权限"""
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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"创建权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建权限失败"}), 500


@api_permission_bp.route("/permissions/<permission_name>/usage", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
async def get_permission_usage(permission_name: str):
    """获取权限的使用情况（被哪些用户和角色使用）"""
    try:
        usage_info = await permission_manager.get_permission_usage(permission_name)
        return jsonify({"status": 200, "data": usage_info})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取权限使用情况失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取权限使用情况失败"}), 500


@api_permission_bp.route("/permissions", methods=["DELETE"])    
@auth_required
@permission_required(["admin:write"])
async def delete_permission():
    """删除权限"""
    try:
        data = await request.get_json()
        permission_name = data.get("permissionName")
        force = data.get("force", False)
        
        if not permission_name:
            return jsonify({"status": 400, "message": "权限名称不能为空"}), 400
        
        await permission_manager.delete_permission(permission_name, force=force)
        
        return jsonify({"status": 200, "message": "权限删除成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"删除权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除权限失败"}), 500


# ==================== Role Hierarchy Management ====================

@api_permission_bp.route("/roles/<role_name>/hierarchy", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
async def get_role_hierarchy(role_name: str):
    """获取角色的层级关系（父角色和子角色）"""
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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取角色层级关系失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取角色层级关系失败"}), 500


@api_permission_bp.route("/roles/hierarchy", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
async def add_role_hierarchy():
    """添加角色层级关系"""
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
        
        return jsonify({"status": 200, "message": "角色层级关系添加成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"添加角色层级关系失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加角色层级关系失败"}), 500


@api_permission_bp.route("/roles/hierarchy", methods=["DELETE"])
@auth_required
@permission_required(["admin:write"])
async def delete_role_hierarchy():
    """删除角色层级关系"""
    try:
        data = await request.get_json()
        hierarchy_pairs = data.get("hierarchyPairs", [])
        
        if not hierarchy_pairs:
            return jsonify({"status": 400, "message": "层级关系列表不能为空"}), 400
        
        await permission_manager.delete_role_hierarchys(hierarchy_pairs)
        
        return jsonify({"status": 200, "message": "角色层级关系删除成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"删除角色层级关系失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除角色层级关系失败"}), 500


# ==================== User Role Management ====================

@api_permission_bp.route("/users/<user_name>/roles", methods=["GET"])
@auth_required
@permission_required(["admin:read"])
async def get_user_roles(user_name: str):
    """获取用户的所有角色"""
    try:
        roles = await permission_manager.get_user_roles(user_name)
        return jsonify({"status": 200, "data": roles})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取用户角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取用户角色失败"}), 500


@api_permission_bp.route("/users/roles", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
async def add_role_to_user():
    """为用户添加角色"""
    try:
        data = await request.get_json()
        user_name = data.get("userName")
        role_name = data.get("roleName")
        
        if not user_name or not role_name:
            return jsonify({"status": 400, "message": "用户名和角色名称不能为空"}), 400
        
        await permission_manager.add_role_to_user(user_name, role_name)
        
        return jsonify({"status": 200, "message": "用户角色添加成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"添加用户角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加用户角色失败"}), 500


@api_permission_bp.route("/users/roles", methods=["DELETE"])
@auth_required
@permission_required(["admin:write"])
async def remove_role_from_user():
    """移除用户的角色"""
    try:
        data = await request.get_json()
        user_name = data.get("userName")
        role_name = data.get("roleName")
        
        if not user_name or not role_name:
            return jsonify({"status": 400, "message": "用户名和角色名称不能为空"}), 400
        
        await permission_manager.remove_role_from_user(user_name, role_name)
        
        return jsonify({"status": 200, "message": "用户角色移除成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"移除用户角色失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "移除用户角色失败"}), 500


@api_permission_bp.route("/users", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
async def get_all_users():
    """获取所有用户"""
    try:
        users = []
        async for user in await UserDBUtils.select_all():
            users.append({
                "userName": user.user_name,
                "createDate": user.create_date.isoformat() if user.create_date else None
            })
        return jsonify({"status": 200, "data": users})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取所有用户失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取所有用户失败"}), 500


# ==================== Role Permission Management ====================

@api_permission_bp.route("/roles/<role_name>/permissions", methods=["GET"])
@auth_required
@permission_required(["admin:write"])
async def get_role_permissions(role_name: str):
    """获取角色的所有权限"""
    try:
        permissions = await permission_manager.get_role_permissions(role_name)
        return jsonify({"status": 200, "data": permissions})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取角色权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取角色权限失败"}), 500


@api_permission_bp.route("/roles/permissions", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
async def add_permission_to_role():
    """为角色添加权限"""
    try:
        data = await request.get_json()
        role_name = data.get("roleName")
        permission_name = data.get("permissionName")
        
        if not role_name or not permission_name:
            return jsonify({"status": 400, "message": "角色名称和权限名称不能为空"}), 400
        
        await permission_manager.add_permissions_to_role(role_name, permission_name)
        
        return jsonify({"status": 200, "message": "角色权限添加成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"添加角色权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加角色权限失败"}), 500


@api_permission_bp.route("/roles/permissions", methods=["DELETE"])
@auth_required
@permission_required(["admin:write"])
async def remove_permission_from_role():
    """移除角色的权限"""
    try:
        data = await request.get_json()
        role_name = data.get("roleName")
        permission_name = data.get("permissionName")
        
        if not role_name or not permission_name:
            return jsonify({"status": 400, "message": "角色名称和权限名称不能为空"}), 400
        
        await permission_manager.remove_permissions_from_role(role_name, permission_name)
        
        return jsonify({"status": 200, "message": "角色权限移除成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"移除角色权限失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "移除角色权限失败"}), 500

