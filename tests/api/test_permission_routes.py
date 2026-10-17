"""
API Route 测试: /api/permission Blueprint
测试 RBAC 鉴权链: @auth_required → @permission_required

覆盖所有 13 个端点，每个测试至少 2 个鉴权变体 (无token / 过期 / 非admin / admin)。
选取 8 个核心端点走完整 4 级鉴权矩阵，其余 5 个端点至少 2 级。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

import jwt

from src_v2.core.permission.permission_manager import permission_manager

pytestmark = pytest.mark.api

# ══════════════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════════════

TEST_SECRET = "test-secret-key-for-jwt"


def _make_token(user_id: str) -> str:
    """用 user_id 字段创建有效 JWT token。"""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24),
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def _auth(user_id: str) -> dict:
    """返回 Authorization headers dict（有效 token）。"""
    return {"Authorization": f"Bearer {_make_token(user_id)}"}


def _expired_token(user_id: str = "test_user") -> str:
    """创建已过期的 JWT token。"""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() - timedelta(hours=1),
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def _expired_auth(user_id: str = "test_user") -> dict:
    """返回已过期的 Authorization headers dict。"""
    return {"Authorization": f"Bearer {_expired_token(user_id)}"}


def _set_secret(test_app) -> None:
    """确保 Quart app 使用测试密钥 (与 TEST_SECRET 一致)。"""
    test_app.app.secret_key = TEST_SECRET


class _AsyncIter:
    """可被 async for 迭代的简单 mock 容器。

    用法: _AsyncIter([obj1, obj2]) 返回支持 async for 和 async with 的对象。
    """

    def __init__(self, items: list):
        self._items = items

    async def __aenter__(self):
        self._iter = iter(self._items)
        return self

    async def __aexit__(self, *args):
        pass

    def __aiter__(self):
        self._iter = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _mock_pm_forbidden():
    """Mock permission_manager 方法使权限检查失败 → 403。"""
    m = MagicMock()
    m.get_user_roles = AsyncMock(return_value=[])
    m.get_user_permissions = AsyncMock(return_value=[])
    return m


def _mock_pm_admin(perm: str = "admin:write"):
    """Mock permission_manager 方法使 admin 用户通过权限检查。"""
    m = MagicMock()

    async def get_roles(user_id: str):
        return ["admin"] if user_id == "admin" else []

    async def get_role_perms(role: str):
        return [perm] if role == "admin" else []

    async def get_user_perms(user_id: str):
        return []

    m.get_user_roles = AsyncMock(side_effect=get_roles)
    m.get_role_permissions = AsyncMock(side_effect=get_role_perms)
    m.get_user_permissions = AsyncMock(side_effect=get_user_perms)
    return m


# ══════════════════════════════════════════════════════════════════════
# GET /api/permission/roles (admin:write)
# ══════════════════════════════════════════════════════════════════════

class TestGetRoles:
    """GET /api/permission/roles — 完整 4 级鉴权矩阵"""

    URL = "/api/permission/roles"

    async def test_no_token(self, test_client, test_app):
        """无 token → 401"""
        _set_secret(test_app)
        resp = await test_client.get(self.URL)
        assert resp.status_code == 401

    async def test_expired_token(self, test_client, test_app):
        """过期 token → 401"""
        _set_secret(test_app)
        resp = await test_client.get(self.URL, headers=_expired_auth())
        assert resp.status_code == 401

    async def test_non_admin(self, test_client, test_app):
        """非 admin 用户 → 403"""
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
        ):
            m_roles.return_value = []
            m_perms.return_value = []
            resp = await test_client.get(self.URL, headers=_auth("test_user"))
            assert resp.status_code == 403

    async def test_admin(self, test_client, test_app):
        """admin 用户 → 200 (mock DB 返回角色列表)"""
        _set_secret(test_app)
        mock_role = MagicMock()
        mock_role.role_name = "admin"
        mock_role.role_description = "管理员"

        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch(
                "src_v2.backend.api.api_permission.RolesDBUtils.select_all",
                new_callable=AsyncMock,
            ) as m_select,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_select.return_value = _AsyncIter([mock_role])

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200
            assert len(data["data"]) == 1
            assert data["data"][0]["roleName"] == "admin"


# ══════════════════════════════════════════════════════════════════════
# POST /api/permission/roles (admin:write)
# ══════════════════════════════════════════════════════════════════════

class TestCreateRole:
    """POST /api/permission/roles — 完整 4 级鉴权矩阵"""

    URL = "/api/permission/roles"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.post(self.URL, json={"roleName": "editor"})
        assert resp.status_code == 401

    async def test_expired_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.post(
            self.URL, headers=_expired_auth(), json={"roleName": "editor"}
        )
        assert resp.status_code == 401

    async def test_non_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
        ):
            m_roles.return_value = []
            m_perms.return_value = []
            resp = await test_client.post(
                self.URL, headers=_auth("test_user"), json={"roleName": "editor"}
            )
            assert resp.status_code == 403

    async def test_admin(self, test_client, test_app):
        """admin 创建角色 → 200"""
        _set_secret(test_app)
        mock_role = MagicMock()
        mock_role.role_name = "editor"
        mock_role.role_description = "编辑者"

        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch.object(permission_manager, "create_role", new_callable=AsyncMock) as m_create,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_create.return_value = mock_role

            resp = await test_client.post(
                self.URL,
                headers=_auth("admin"),
                json={"roleName": "editor", "roleDescription": "编辑者"},
            )
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200
            assert "角色创建成功" in data["message"]


# ══════════════════════════════════════════════════════════════════════
# DELETE /api/permission/roles (admin:write)
# ══════════════════════════════════════════════════════════════════════

class TestDeleteRole:
    """DELETE /api/permission/roles — 完整 4 级鉴权矩阵"""

    URL = "/api/permission/roles"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.delete(self.URL, json={"roleName": "editor"})
        assert resp.status_code == 401

    async def test_expired_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.delete(
            self.URL, headers=_expired_auth(), json={"roleName": "editor"}
        )
        assert resp.status_code == 401

    async def test_non_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
        ):
            m_roles.return_value = []
            m_perms.return_value = []
            resp = await test_client.delete(
                self.URL, headers=_auth("test_user"), json={"roleName": "editor"}
            )
            assert resp.status_code == 403

    async def test_admin(self, test_client, test_app):
        """admin 删除角色 → 200"""
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch.object(permission_manager, "delete_role", new_callable=AsyncMock) as m_del,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_del.return_value = None

            resp = await test_client.delete(
                self.URL,
                headers=_auth("admin"),
                json={"roleName": "editor", "includeChildren": False},
            )
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200


# ══════════════════════════════════════════════════════════════════════
# GET /api/permission/permissions (admin:write)
# ══════════════════════════════════════════════════════════════════════

class TestGetPermissions:
    """GET /api/permission/permissions — 完整 4 级鉴权矩阵"""

    URL = "/api/permission/permissions"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.get(self.URL)
        assert resp.status_code == 401

    async def test_expired_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.get(self.URL, headers=_expired_auth())
        assert resp.status_code == 401

    async def test_non_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
        ):
            m_roles.return_value = []
            m_perms.return_value = []
            resp = await test_client.get(self.URL, headers=_auth("test_user"))
            assert resp.status_code == 403

    async def test_admin(self, test_client, test_app):
        _set_secret(test_app)
        mock_perm = MagicMock()
        mock_perm.permission_name = "admin:write"
        mock_perm.permission_description = "管理员写权限"

        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch(
                "src_v2.backend.api.api_permission.PermissionsDBUtils.select_all",
                new_callable=AsyncMock,
            ) as m_select,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_select.return_value = _AsyncIter([mock_perm])

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200
            assert data["data"][0]["permissionName"] == "admin:write"


# ══════════════════════════════════════════════════════════════════════
# POST /api/permission/permissions (admin:write)
# ══════════════════════════════════════════════════════════════════════

class TestCreatePermission:
    """POST /api/permission/permissions — 完整 4 级鉴权矩阵"""

    URL = "/api/permission/permissions"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.post(
            self.URL, json={"permissionName": "resource:write"}
        )
        assert resp.status_code == 401

    async def test_expired_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.post(
            self.URL,
            headers=_expired_auth(),
            json={"permissionName": "resource:write"},
        )
        assert resp.status_code == 401

    async def test_non_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
        ):
            m_roles.return_value = []
            m_perms.return_value = []
            resp = await test_client.post(
                self.URL,
                headers=_auth("test_user"),
                json={"permissionName": "resource:write"},
            )
            assert resp.status_code == 403

    async def test_admin(self, test_client, test_app):
        _set_secret(test_app)
        mock_perm = MagicMock()
        mock_perm.permission_name = "resource:write"
        mock_perm.permission_description = "资源写"

        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch.object(permission_manager, "create_permission", new_callable=AsyncMock) as m_cp,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_cp.return_value = mock_perm

            resp = await test_client.post(
                self.URL,
                headers=_auth("admin"),
                json={
                    "permissionName": "resource:write",
                    "permissionDescription": "资源写",
                },
            )
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200


# ══════════════════════════════════════════════════════════════════════
# GET /api/permission/users/{name}/roles (admin:read)
# ══════════════════════════════════════════════════════════════════════

class TestGetUserRoles:
    """GET /api/permission/users/{name}/roles — 完整 4 级鉴权矩阵
    (需要 admin:read 而非 admin:write)
    """

    URL = "/api/permission/users/testuser1/roles"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.get(self.URL)
        assert resp.status_code == 401

    async def test_expired_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.get(self.URL, headers=_expired_auth())
        assert resp.status_code == 401

    async def test_non_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
        ):
            m_roles.return_value = []
            m_perms.return_value = []
            resp = await test_client.get(self.URL, headers=_auth("test_user"))
            assert resp.status_code == 403

    async def test_admin(self, test_client, test_app):
        """admin 用户查询角色 (admin:read) → 200"""
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_pm_roles,
        ):
            # 权限检查: admin 有 admin:read
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:read"]
            m_up.return_value = []
            # handler 调用
            m_pm_roles.return_value = ["user"]

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200
            assert "user" in data["data"]


# ══════════════════════════════════════════════════════════════════════
# POST /api/permission/users/roles (admin:write)
# ══════════════════════════════════════════════════════════════════════

class TestAddRoleToUser:
    """POST /api/permission/users/roles — 完整 4 级鉴权矩阵"""

    URL = "/api/permission/users/roles"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.post(
            self.URL, json={"userName": "user1", "roleName": "editor"}
        )
        assert resp.status_code == 401

    async def test_expired_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.post(
            self.URL,
            headers=_expired_auth(),
            json={"userName": "user1", "roleName": "editor"},
        )
        assert resp.status_code == 401

    async def test_non_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
        ):
            m_roles.return_value = []
            m_perms.return_value = []
            resp = await test_client.post(
                self.URL,
                headers=_auth("test_user"),
                json={"userName": "user1", "roleName": "editor"},
            )
            assert resp.status_code == 403

    async def test_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch.object(permission_manager, "add_role_to_user", new_callable=AsyncMock) as m_add,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_add.return_value = None

            resp = await test_client.post(
                self.URL,
                headers=_auth("admin"),
                json={"userName": "user1", "roleName": "editor"},
            )
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200
            assert "用户角色添加成功" in data["message"]


# ══════════════════════════════════════════════════════════════════════
# GET /api/permission/users (admin:write)
# ══════════════════════════════════════════════════════════════════════

class TestGetUsers:
    """GET /api/permission/users — 完整 4 级鉴权矩阵"""

    URL = "/api/permission/users"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.get(self.URL)
        assert resp.status_code == 401

    async def test_expired_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.get(self.URL, headers=_expired_auth())
        assert resp.status_code == 401

    async def test_non_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
        ):
            m_roles.return_value = []
            m_perms.return_value = []
            resp = await test_client.get(self.URL, headers=_auth("test_user"))
            assert resp.status_code == 403

    async def test_admin(self, test_client, test_app):
        _set_secret(test_app)
        mock_user = MagicMock()
        mock_user.user_name = "admin"
        mock_user.create_date = datetime(2024, 1, 1)

        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch(
                "src_v2.backend.api.api_permission.UserDBUtils.select_all",
                new_callable=AsyncMock,
            ) as m_select,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_select.return_value = _AsyncIter([mock_user])

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200
            assert data["data"][0]["userName"] == "admin"


# ══════════════════════════════════════════════════════════════════════
# 其余端点 — 至少 2 级鉴权
# ══════════════════════════════════════════════════════════════════════


class TestDeletePermission:
    """DELETE /api/permission/permissions — 2 级鉴权 (no_token + admin)"""

    URL = "/api/permission/permissions"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.delete(
            self.URL, json={"permissionName": "resource:write"}
        )
        assert resp.status_code == 401

    async def test_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch.object(permission_manager, "delete_permission", new_callable=AsyncMock) as m_del,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_del.return_value = None

            resp = await test_client.delete(
                self.URL,
                headers=_auth("admin"),
                json={"permissionName": "resource:write", "force": False},
            )
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200


class TestGetRoleHierarchy:
    """GET /api/permission/roles/{name}/hierarchy — 2 级鉴权"""

    URL = "/api/permission/roles/admin/hierarchy"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.get(self.URL)
        assert resp.status_code == 401

    async def test_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch.object(permission_manager, "get_parent_roles", new_callable=AsyncMock) as m_pr,
            patch.object(permission_manager, "get_child_roles", new_callable=AsyncMock) as m_cr,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_pr.return_value = ["superadmin"]
            m_cr.return_value = ["editor"]

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200
            assert "parentRoles" in data["data"]
            assert "childRoles" in data["data"]


class TestAddRoleHierarchy:
    """POST /api/permission/roles/hierarchy — 2 级鉴权"""

    URL = "/api/permission/roles/hierarchy"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.post(
            self.URL,
            json={"parentRoleName": "admin", "childRoleName": "editor"},
        )
        assert resp.status_code == 401

    async def test_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch(
                "src_v2.backend.api.api_permission.RoleHierarchyDBUtils.save_obj",
                new_callable=AsyncMock,
            ) as m_save,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_save.return_value = None

            resp = await test_client.post(
                self.URL,
                headers=_auth("admin"),
                json={"parentRoleName": "admin", "childRoleName": "editor"},
            )
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200


class TestDeleteRoleHierarchy:
    """DELETE /api/permission/roles/hierarchy — 2 级鉴权"""

    URL = "/api/permission/roles/hierarchy"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.delete(
            self.URL,
            json={
                "hierarchyPairs": [
                    {"parentRoleName": "admin", "childRoleName": "editor"}
                ]
            },
        )
        assert resp.status_code == 401

    async def test_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch.object(
                permission_manager, "delete_role_hierarchys", new_callable=AsyncMock
            ) as m_del,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_del.return_value = None

            resp = await test_client.delete(
                self.URL,
                headers=_auth("admin"),
                json={
                    "hierarchyPairs": [
                        {"parentRoleName": "admin", "childRoleName": "editor"}
                    ]
                },
            )
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200


class TestRemoveRoleFromUser:
    """DELETE /api/permission/users/roles — 2 级鉴权"""

    URL = "/api/permission/users/roles"

    async def test_no_token(self, test_client, test_app):
        _set_secret(test_app)
        resp = await test_client.delete(
            self.URL, json={"userName": "user1", "roleName": "editor"}
        )
        assert resp.status_code == 401

    async def test_admin(self, test_client, test_app):
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock) as m_rp,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_up,
            patch.object(
                permission_manager, "remove_role_from_user", new_callable=AsyncMock
            ) as m_rem,
        ):
            m_roles.return_value = ["admin"]
            m_rp.return_value = ["admin:write"]
            m_up.return_value = []
            m_rem.return_value = None

            resp = await test_client.delete(
                self.URL,
                headers=_auth("admin"),
                json={"userName": "user1", "roleName": "editor"},
            )
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200
            assert "移除" in data["message"]
