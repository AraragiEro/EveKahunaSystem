"""权限变更纵深防御测试（安全审计分册 03 #14：admin:write 粒度过粗）

覆盖三件事：
1. `grant_guard` 纯单元行为（GrantDenied / assert_admin_operator / audit_grant /
   is_self_admin_grant）；
2. 4 个权限写端点（users/roles 增删、roles/permissions 增删）与 VIP PUT：
   操作者不是管理员时一律 403，且 permission_manager 的写方法 /
   VipStateDBUtils.update_vip_state 一次都不会被调用（杜绝"先拒绝后落库"）；
3. 管理员操作时正常 200，并撤销目标用户的 refresh token；
   自我授予 admin 角色额外 403。
"""
import sys
import types
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from src_v2.core.permission import grant_guard
from src_v2.core.permission.grant_guard import (
    GrantDenied,
    assert_admin_operator,
    audit_grant,
    is_self_admin_grant,
)
from src_v2.core.permission.permission_manager import permission_manager

pytestmark = pytest.mark.api

TEST_SECRET = "test-secret-key-for-jwt"

# ══════════════════════════════════════════════════════════════════════
# 辅助工具
# ══════════════════════════════════════════════════════════════════════


def _make_token(user_id: str) -> str:
    """用 user_id 字段创建有效 JWT token（本项目的 user_id 即 user_name）。"""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24),
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def _auth(user_id: str) -> dict:
    """返回 Authorization headers dict（有效 token）。"""
    return {"Authorization": f"Bearer {_make_token(user_id)}"}


def _set_secret(test_app) -> None:
    """确保 Quart app 使用测试密钥（与 TEST_SECRET 一致）。"""
    test_app.app.secret_key = TEST_SECRET


# refresh_token_store 由并行子任务提供，可能尚未就绪
try:
    from src_v2.core.user import refresh_token_store as _refresh_token_store  # noqa: F401

    _HAS_REFRESH_STORE = True
except Exception:  # pragma: no cover - 取决于并行子任务是否已合入
    _HAS_REFRESH_STORE = False


@contextmanager
def _patch_revoke():
    """patch 撤销 refresh token 的接口，返回可断言的 AsyncMock。

    模块尚未就绪时注入临时桩模块：既验证端点确实执行了撤销调用，
    也验证"模块缺失不会让端点 500"。
    """
    if _HAS_REFRESH_STORE:
        with patch(
            "src_v2.core.user.refresh_token_store.revoke_all_for_user",
            new_callable=AsyncMock,
        ) as m_revoke:
            yield m_revoke
    else:
        stub = types.ModuleType("src_v2.core.user.refresh_token_store")
        stub.revoke_all_for_user = AsyncMock(return_value=None)
        with patch.dict(sys.modules, {"src_v2.core.user.refresh_token_store": stub}):
            yield stub.revoke_all_for_user


@contextmanager
def _patch_authz(admin_ok: bool):
    """patch 整条鉴权链，并返回 grant_guard.is_admin_user 的 mock。

    - permission_required 依赖 get_user_roles / get_role_permissions /
      get_user_permissions（这里让 admin:write 检查通过，模拟"攻击者恰好持有
      admin:write 但没有 admin 角色"的真实场景）
    - role_required 依赖 get_all_descendant_roles / get_vip_state
    - grant_guard.is_admin_user 是装饰器之后的二次管理员判定
    """
    with ExitStack() as stack:
        m_roles = stack.enter_context(
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock)
        )
        m_role_perms = stack.enter_context(
            patch.object(permission_manager, "get_role_permissions", new_callable=AsyncMock)
        )
        m_user_perms = stack.enter_context(
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock)
        )
        m_desc = stack.enter_context(
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock)
        )
        m_vip = stack.enter_context(
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock)
        )
        m_admin = stack.enter_context(
            patch("src_v2.core.permission.grant_guard.is_admin_user", new_callable=AsyncMock)
        )

        m_roles.return_value = ["admin"]
        m_role_perms.return_value = ["admin:write"]
        m_user_perms.return_value = []
        m_desc.return_value = []
        m_vip.return_value = None
        m_admin.return_value = admin_ok
        yield m_admin


# ══════════════════════════════════════════════════════════════════════
# 一、grant_guard 纯单元测试
# ══════════════════════════════════════════════════════════════════════


class TestGrantGuardUnit:
    """grant_guard 模块自身的单元行为"""

    def test_grant_denied_is_exception(self):
        """GrantDenied 是普通异常，消息为中文"""
        err = GrantDenied("需要管理员（admin）角色才能执行该操作")
        assert isinstance(err, Exception)
        assert "管理员" in str(err)

    async def test_assert_admin_operator_passes(self):
        """is_admin_user 为真 → 不抛异常"""
        with patch(
            "src_v2.core.permission.grant_guard.is_admin_user",
            new_callable=AsyncMock,
        ) as m_admin:
            m_admin.return_value = True
            await assert_admin_operator("admin")
            m_admin.assert_awaited_once_with("admin")

    async def test_assert_admin_operator_denied(self):
        """is_admin_user 为假 → GrantDenied，消息统一"""
        with patch(
            "src_v2.core.permission.grant_guard.is_admin_user",
            new_callable=AsyncMock,
        ) as m_admin:
            m_admin.return_value = False
            with pytest.raises(GrantDenied) as exc_info:
                await assert_admin_operator("user1")
            assert str(exc_info.value) == "需要管理员（admin）角色才能执行该操作"

    async def test_assert_admin_operator_empty_operator(self):
        """空操作者 → 直接拒绝（不查库）"""
        with pytest.raises(GrantDenied):
            await assert_admin_operator("")

    async def test_assert_admin_operator_fail_closed_on_error(self):
        """is_admin_user 抛异常 → fail-closed 拒绝"""
        with patch(
            "src_v2.core.permission.grant_guard.is_admin_user",
            new_callable=AsyncMock,
        ) as m_admin:
            m_admin.side_effect = RuntimeError("数据库不可用")
            with pytest.raises(GrantDenied):
                await assert_admin_operator("admin")

    def test_audit_grant_logs_without_secrets(self):
        """audit_grant 只记录 operator/action/target/item"""
        with patch.object(grant_guard, "logger") as m_logger:
            audit_grant("admin", "update-vip", "user1", "level=vip_alpha")
            m_logger.info.assert_called_once_with(
                "[grant-audit] operator=admin action=update-vip target=user1"
                " item=level=vip_alpha"
            )

    @pytest.mark.parametrize(
        "operator,target_user,role_name,expected",
        [
            ("admin", "admin", "admin", True),          # 同名 + admin → 自我升级
            ("admin", "admin", "editor", False),        # 同名但非 admin
            ("admin", "user1", "admin", False),         # 不同名
            ("admin", "user1", "editor", False),        # 都不同
            ("admin", "", "admin", False),              # 目标为空
            ("", "admin", "admin", False),              # 操作者为空
            ("admin", "admin", "", False),              # 角色为空
            (" admin ", "admin", " admin ", True),      # 首尾空格不影响判定
        ],
    )
    def test_is_self_admin_grant_boundaries(self, operator, target_user, role_name, expected):
        """is_self_admin_grant 边界：同名 admin / 同名非 admin / 不同名 / 空值"""
        assert is_self_admin_grant(operator, target_user, role_name) is expected


# ══════════════════════════════════════════════════════════════════════
# 二、4 个权限写端点：非管理员一律 403 且不落库
# ══════════════════════════════════════════════════════════════════════


class TestPermissionWriteEndpointsDenied:
    """持有 admin:write 但不是 admin 的账号 → 403，permission_manager 写方法不被调用"""

    async def test_add_role_to_user_denied(self, test_client, test_app):
        """POST /api/permission/users/roles → 403"""
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=False),
            patch.object(
                permission_manager, "add_role_to_user", new_callable=AsyncMock
            ) as m_add,
            _patch_revoke() as m_revoke,
        ):
            resp = await test_client.post(
                "/api/permission/users/roles",
                headers=_auth("user1"),
                json={"userName": "user1", "roleName": "admin"},
            )
            assert resp.status_code == 403
            data = await resp.get_json()
            assert data["status"] == 403
            assert "管理员" in data["message"]
            m_add.assert_not_called()
            m_revoke.assert_not_called()

    async def test_remove_role_from_user_denied(self, test_client, test_app):
        """DELETE /api/permission/users/roles → 403"""
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=False),
            patch.object(
                permission_manager, "remove_role_from_user", new_callable=AsyncMock
            ) as m_remove,
            _patch_revoke() as m_revoke,
        ):
            resp = await test_client.delete(
                "/api/permission/users/roles",
                headers=_auth("user1"),
                json={"userName": "user2", "roleName": "editor"},
            )
            assert resp.status_code == 403
            m_remove.assert_not_called()
            m_revoke.assert_not_called()

    async def test_add_permission_to_role_denied(self, test_client, test_app):
        """POST /api/permission/roles/permissions → 403"""
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=False),
            patch.object(
                permission_manager, "add_permissions_to_role", new_callable=AsyncMock
            ) as m_add_perm,
            _patch_revoke() as m_revoke,
        ):
            resp = await test_client.post(
                "/api/permission/roles/permissions",
                headers=_auth("user1"),
                json={"roleName": "editor", "permissionName": "admin:write"},
            )
            assert resp.status_code == 403
            data = await resp.get_json()
            assert data["status"] == 403
            m_add_perm.assert_not_called()
            m_revoke.assert_not_called()

    async def test_remove_permission_from_role_denied(self, test_client, test_app):
        """DELETE /api/permission/roles/permissions → 403"""
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=False),
            patch.object(
                permission_manager, "remove_permissions_from_role", new_callable=AsyncMock
            ) as m_rm_perm,
            _patch_revoke() as m_revoke,
        ):
            resp = await test_client.delete(
                "/api/permission/roles/permissions",
                headers=_auth("user1"),
                json={"roleName": "editor", "permissionName": "admin:write"},
            )
            assert resp.status_code == 403
            m_rm_perm.assert_not_called()
            m_revoke.assert_not_called()

    async def test_update_vip_denied(self, test_client, test_app):
        """PUT /api/vip/<user> → 403，VipStateDBUtils.update_vip_state 不被调用"""
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=False),
            patch(
                "src_v2.backend.api.api_vip.UserDBUtils.select_user_by_user_name",
                new_callable=AsyncMock,
            ) as m_select_user,
            patch(
                "src_v2.backend.api.api_vip.VipStateDBUtils.update_vip_state",
                new_callable=AsyncMock,
            ) as m_update,
            _patch_revoke() as m_revoke,
        ):
            m_select_user.return_value = MagicMock()
            resp = await test_client.put(
                "/api/vip/user1",
                headers=_auth("user1"),
                json={"vipLevel": "vip_omega", "vipEndDate": "2099-12-31T23:59:59"},
            )
            assert resp.status_code == 403
            data = await resp.get_json()
            assert data["status"] == 403
            m_update.assert_not_called()
            m_revoke.assert_not_called()


# ══════════════════════════════════════════════════════════════════════
# 三、管理员操作：正常 200 + 撤销 refresh token
# ══════════════════════════════════════════════════════════════════════


class TestPermissionWriteEndpointsAllowed:
    """管理员操作 → 200，并撤销目标用户 refresh token（角色级变更只提示重登）"""

    async def test_add_role_to_user_ok(self, test_client, test_app):
        """POST /api/permission/users/roles → 200 + 撤销目标用户 token"""
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=True),
            patch.object(
                permission_manager, "add_role_to_user", new_callable=AsyncMock
            ) as m_add,
            _patch_revoke() as m_revoke,
        ):
            resp = await test_client.post(
                "/api/permission/users/roles",
                headers=_auth("admin"),
                json={"userName": "user1", "roleName": "editor"},
            )
            assert resp.status_code == 200
            data = await resp.get_json()
            assert "用户角色添加成功" in data["message"]
            m_add.assert_awaited_once_with("user1", "editor")
            m_revoke.assert_awaited_once_with("user1")

    async def test_remove_role_from_user_ok(self, test_client, test_app):
        """DELETE /api/permission/users/roles → 200 + 撤销目标用户 token"""
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=True),
            patch.object(
                permission_manager, "remove_role_from_user", new_callable=AsyncMock
            ) as m_remove,
            _patch_revoke() as m_revoke,
        ):
            resp = await test_client.delete(
                "/api/permission/users/roles",
                headers=_auth("admin"),
                json={"userName": "user1", "roleName": "editor"},
            )
            assert resp.status_code == 200
            m_remove.assert_awaited_once_with("user1", "editor")
            m_revoke.assert_awaited_once_with("user1")

    async def test_add_permission_to_role_ok(self, test_client, test_app):
        """POST /api/permission/roles/permissions → 200，角色级变更不逐个撤销 token"""
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=True),
            patch.object(
                permission_manager, "add_permissions_to_role", new_callable=AsyncMock
            ) as m_add_perm,
            _patch_revoke() as m_revoke,
        ):
            resp = await test_client.post(
                "/api/permission/roles/permissions",
                headers=_auth("admin"),
                json={"roleName": "editor", "permissionName": "resource:write"},
            )
            assert resp.status_code == 200
            data = await resp.get_json()
            assert "角色权限添加成功" in data["message"]
            m_add_perm.assert_awaited_once_with("editor", "resource:write")
            m_revoke.assert_not_called()

    async def test_remove_permission_from_role_ok(self, test_client, test_app):
        """DELETE /api/permission/roles/permissions → 200，角色级变更不逐个撤销 token"""
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=True),
            patch.object(
                permission_manager, "remove_permissions_from_role", new_callable=AsyncMock
            ) as m_rm_perm,
            _patch_revoke() as m_revoke,
        ):
            resp = await test_client.delete(
                "/api/permission/roles/permissions",
                headers=_auth("admin"),
                json={"roleName": "editor", "permissionName": "resource:write"},
            )
            assert resp.status_code == 200
            m_rm_perm.assert_awaited_once_with("editor", "resource:write")
            m_revoke.assert_not_called()

    async def test_update_vip_ok(self, test_client, test_app):
        """PUT /api/vip/<user> → 200 + 撤销目标用户 token"""
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=True),
            patch(
                "src_v2.backend.api.api_vip.UserDBUtils.select_user_by_user_name",
                new_callable=AsyncMock,
            ) as m_select_user,
            patch(
                "src_v2.backend.api.api_vip.VipStateDBUtils.update_vip_state",
                new_callable=AsyncMock,
            ) as m_update,
            _patch_revoke() as m_revoke,
        ):
            m_select_user.return_value = MagicMock()
            resp = await test_client.put(
                "/api/vip/user1",
                headers=_auth("admin"),
                json={"vipLevel": "vip_alpha", "vipEndDate": "2026-12-31T23:59:59"},
            )
            assert resp.status_code == 200
            data = await resp.get_json()
            assert "更新成功" in data["message"]
            m_update.assert_awaited_once()
            # 只允许写 vip_alpha / vip_omega
            assert m_update.await_args.kwargs["vip_level"] == "vip_alpha"
            m_revoke.assert_awaited_once_with("user1")


# ══════════════════════════════════════════════════════════════════════
# 四、自我授予 admin 角色（纵深防御）
# ══════════════════════════════════════════════════════════════════════


class TestSelfAdminGrant:
    """即使已是管理员，也拒绝给自己授予 admin 角色"""

    async def test_self_admin_grant_rejected(self, test_client, test_app):
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=True),
            patch.object(
                permission_manager, "add_role_to_user", new_callable=AsyncMock
            ) as m_add,
            _patch_revoke() as m_revoke,
        ):
            resp = await test_client.post(
                "/api/permission/users/roles",
                headers=_auth("admin"),
                json={"userName": "admin", "roleName": "admin"},
            )
            assert resp.status_code == 403
            data = await resp.get_json()
            assert data["status"] == 403
            assert data["message"] == "不能给自己授予管理员角色"
            m_add.assert_not_called()
            m_revoke.assert_not_called()

    async def test_self_non_admin_role_allowed(self, test_client, test_app):
        """给自己加非 admin 角色不属于自我升级，正常放行"""
        _set_secret(test_app)
        with (
            _patch_authz(admin_ok=True),
            patch.object(
                permission_manager, "add_role_to_user", new_callable=AsyncMock
            ) as m_add,
            _patch_revoke() as m_revoke,
        ):
            resp = await test_client.post(
                "/api/permission/users/roles",
                headers=_auth("admin"),
                json={"userName": "admin", "roleName": "editor"},
            )
            assert resp.status_code == 200
            m_add.assert_awaited_once_with("admin", "editor")
            m_revoke.assert_awaited_once_with("admin")


# ══════════════════════════════════════════════════════════════════════
# 五、VIP PUT 走 role_required（不再是 admin:write）
# ══════════════════════════════════════════════════════════════════════


class TestVipRequiresAdminRole:
    """VIP PUT 的装饰器路径：必须持有 admin 角色"""

    async def test_non_admin_role_denied_by_decorator(self, test_client, test_app):
        """无 admin 角色（也没有任何角色）→ role_required 直接 403"""
        _set_secret(test_app)
        with (
            patch.object(
                permission_manager, "get_user_roles", new_callable=AsyncMock
            ) as m_roles,
            patch.object(
                permission_manager, "get_vip_state", new_callable=AsyncMock
            ) as m_vip,
            patch(
                "src_v2.backend.api.api_vip.VipStateDBUtils.update_vip_state",
                new_callable=AsyncMock,
            ) as m_update,
        ):
            m_roles.return_value = []
            m_vip.return_value = None
            resp = await test_client.put(
                "/api/vip/user1",
                headers=_auth("user1"),
                json={"vipLevel": "vip_omega"},
            )
            assert resp.status_code == 403
            m_update.assert_not_called()

    async def test_vip_level_cannot_replace_admin_role(self, test_client, test_app):
        """VIP 等级被 role_required 当角色用，但 vip_omega 不等于 admin"""
        _set_secret(test_app)
        vip_state = MagicMock()
        vip_state.vip_level = "vip_omega"
        with (
            patch.object(
                permission_manager, "get_user_roles", new_callable=AsyncMock
            ) as m_roles,
            patch.object(
                permission_manager, "get_all_descendant_roles", new_callable=AsyncMock
            ) as m_desc,
            patch.object(
                permission_manager, "get_vip_state", new_callable=AsyncMock
            ) as m_vip,
            patch(
                "src_v2.backend.api.api_vip.VipStateDBUtils.update_vip_state",
                new_callable=AsyncMock,
            ) as m_update,
        ):
            m_roles.return_value = ["vip_alpha"]  # 冒充 VIP 角色
            m_desc.return_value = []
            m_vip.return_value = vip_state
            resp = await test_client.put(
                "/api/vip/user1",
                headers=_auth("user1"),
                json={"vipLevel": "vip_omega"},
            )
            assert resp.status_code == 403
            m_update.assert_not_called()
