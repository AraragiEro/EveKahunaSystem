# -*- coding: utf-8 -*-
"""
auth Blueprint API 路由测试

覆盖 /api/auth 下所有端点：
- POST /api/auth/signup
- POST /api/auth/login
- GET  /api/auth/me
- POST /api/auth/logout
- POST /api/auth/deleteAccount

每个端点测试正向 + 异常（401/400/500）场景。
使用 mock_config / test_client 等 conftest fixture。
"""
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# 模块级初始化：确保 Quart app 使用测试密钥
# （app.secret_key 在模块导入时设定，mock_config 无法覆盖已赋值的属性）
# ---------------------------------------------------------------------------
import src_v2.backend.app as _backend_app

TEST_SECRET = "test-secret-key-for-jwt"


def _ensure_test_secret():
    """设置 app.secret_key 为测试密钥，使 JWT 验证与实际签名一致"""
    _backend_app.app.secret_key = TEST_SECRET


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
class _AwaitableList:
    """可多次 await 的列表包装器，用于模拟 async property（如 User.roles）。

    协程只能 await 一次，但 login 端点会 await user.roles 两次。
    本类通过 __await__ 返回新生成器实现可重复 await。"""

    def __init__(self, values):
        self._values = values

    def __await__(self):
        yield
        return list(self._values)


def _make_auth_header(
    user_id: str = "test_user", secret: str = TEST_SECRET
):
    """创建带 user_id 字段的有效 JWT 认证头部，用于 /me /logout /deleteAccount"""
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _make_csrf_token() -> str:
    """生成随机的 CSRF token"""
    import uuid
    return uuid.uuid4().hex


def _add_csrf(headers: dict, csrf_token: str) -> dict:
    """将 CSRF token 添加到请求头部和 cookie"""
    h = {**headers, "X-CSRF-Token": csrf_token, "Cookie": f"csrf_token={csrf_token}"}
    return h


# ============================================================================
# POST /api/auth/signup
# ============================================================================
@pytest.mark.api
class TestAuthSignup:
    """注册端点测试"""

    @pytest.mark.asyncio
    async def test_signup_success(self, test_client, mock_config):
        """有效注册数据 → 200"""
        with (
            patch("src_v2.backend.api.api_login.permission_manager") as mock_pm,
            patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls,
        ):
            mock_pm.validate_invite_code = AsyncMock(
                return_value={"valid": True, "available": True}
            )
            mock_pm.add_role_to_user = AsyncMock()
            mock_pm.use_invite_code = AsyncMock()
            mock_um = MagicMock()
            mock_um.create_user = AsyncMock(return_value=MagicMock())
            mock_um_cls.return_value = mock_um

            resp = await test_client.post(
                "/api/auth/signup",
                json={
                    "username": "newuser",
                    "password": "password123",
                    "inviteCode": "VALID-CODE",
                },
            )
            data = await resp.get_json()

            assert resp.status_code == 200
            assert data["status"] == 200
            assert data["message"] == "注册成功"

    @pytest.mark.asyncio
    async def test_signup_missing_invite_code(self, test_client, mock_config):
        """缺少邀请码 → 400"""
        resp = await test_client.post(
            "/api/auth/signup",
            json={"username": "newuser", "password": "password123"},
        )
        data = await resp.get_json()

        assert resp.status_code == 400
        assert data["message"] == "邀请码不能为空"

    @pytest.mark.asyncio
    async def test_signup_invalid_invite_code(self, test_client, mock_config):
        """无效邀请码 → 400"""
        with patch("src_v2.backend.api.api_login.permission_manager") as mock_pm:
            mock_pm.validate_invite_code = AsyncMock(
                return_value={"valid": False}
            )

            resp = await test_client.post(
                "/api/auth/signup",
                json={
                    "username": "newuser",
                    "password": "password123",
                    "inviteCode": "INVALID-CODE",
                },
            )
            data = await resp.get_json()

            assert resp.status_code == 400
            assert data["message"] == "邀请码不存在"

    @pytest.mark.asyncio
    async def test_signup_invite_code_exhausted(self, test_client, mock_config):
        """邀请码已用完 → 400"""
        with patch("src_v2.backend.api.api_login.permission_manager") as mock_pm:
            mock_pm.validate_invite_code = AsyncMock(
                return_value={"valid": True, "available": False}
            )

            resp = await test_client.post(
                "/api/auth/signup",
                json={
                    "username": "newuser",
                    "password": "password123",
                    "inviteCode": "EXHAUSTED-CODE",
                },
            )
            data = await resp.get_json()

            assert resp.status_code == 400
            assert data["message"] == "邀请码已使用完"

    @pytest.mark.asyncio
    async def test_signup_duplicate_username(self, test_client, mock_config):
        """重复用户名 → 400 通用文案（不回显"已存在"，防用户名枚举）"""
        from src_v2.core.utils import KahunaException

        with (
            patch("src_v2.backend.api.api_login.permission_manager") as mock_pm,
            patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls,
        ):
            mock_pm.validate_invite_code = AsyncMock(
                return_value={"valid": True, "available": True}
            )
            mock_um = MagicMock()
            mock_um.create_user = AsyncMock(
                side_effect=KahunaException("用户已存在")
            )
            mock_um_cls.return_value = mock_um

            resp = await test_client.post(
                "/api/auth/signup",
                json={
                    "username": "existing_user",
                    "password": "password123",
                    "inviteCode": "VALID-CODE",
                },
            )
            data = await resp.get_json()

            assert resp.status_code == 400
            assert data["status"] == 400
            # 不再回显「用户已存在」等内部信息
            assert "已存在" not in data["message"]
            assert "exists" not in data["message"].lower()

    @pytest.mark.asyncio
    async def test_signup_no_auth_token_needed(self, test_client, mock_config):
        """注册不需要认证 token — 验证无 token 也能访问（不返回 401）"""
        with (
            patch("src_v2.backend.api.api_login.permission_manager") as mock_pm,
            patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls,
        ):
            mock_pm.validate_invite_code = AsyncMock(
                return_value={"valid": True, "available": True}
            )
            mock_pm.add_role_to_user = AsyncMock()
            mock_pm.use_invite_code = AsyncMock()
            mock_um = MagicMock()
            mock_um.create_user = AsyncMock(return_value=MagicMock())
            mock_um_cls.return_value = mock_um

            # 不传 Authorization header
            resp = await test_client.post(
                "/api/auth/signup",
                json={
                    "username": "newuser2",
                    "password": "password123",
                    "inviteCode": "VALID-CODE",
                },
            )

            assert resp.status_code == 200


# ============================================================================
# POST /api/auth/login
# ============================================================================
@pytest.mark.api
class TestAuthLogin:
    """登录端点测试"""

    @pytest.mark.asyncio
    async def test_login_success(self, test_client, mock_config):
        """有效凭据 → 200，返回 token + user 信息"""
        _ensure_test_secret()
        valid_hash = generate_password_hash("correct_password")

        with (
            patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls,
            patch("src_v2.backend.api.api_login.permission_manager") as mock_pm,
        ):
            mock_user = MagicMock()
            # roles 是 async property，login 代码中 await user.roles 两次
            mock_user.roles = _AwaitableList(["user"])

            mock_um = MagicMock()
            mock_um.get_password_hash = AsyncMock(return_value=valid_hash)
            mock_um.get_user = AsyncMock(return_value=mock_user)
            mock_um_cls.return_value = mock_um

            mock_vip = MagicMock()
            mock_vip.vip_level = "vip_alpha"
            mock_vip.vip_end_date = datetime.datetime(2025, 12, 31, 23, 59, 59)
            mock_pm.get_vip_state = AsyncMock(return_value=mock_vip)

            resp = await test_client.post(
                "/api/auth/login",
                json={"username": "test_user", "password": "correct_password"},
            )
            data = await resp.get_json()

            assert resp.status_code == 200
            assert data["status"] == 200
            assert "token" in data
            assert data["user"]["username"] == "test_user"
            assert "vip_alpha" in data["user"]["roles"]

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, test_client, mock_config):
        """错误密码 → 401"""
        valid_hash = generate_password_hash("correct_password")

        with patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls:
            mock_um = MagicMock()
            mock_um.get_password_hash = AsyncMock(return_value=valid_hash)
            mock_um_cls.return_value = mock_um

            resp = await test_client.post(
                "/api/auth/login",
                json={"username": "test_user", "password": "wrong_password"},
            )
            data = await resp.get_json()

            assert resp.status_code == 401
            assert data["message"] == "用户名或密码错误"

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, test_client, mock_config):
        """不存在用户 → 401（get_password_hash 返回空字符串，check_password_hash 返回 False）"""
        with patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls:
            mock_um = MagicMock()
            # 返回空字符串模拟"无用户"，check_password_hash 会返回 False
            mock_um.get_password_hash = AsyncMock(return_value="")
            mock_um_cls.return_value = mock_um

            resp = await test_client.post(
                "/api/auth/login",
                json={"username": "no_such_user", "password": "any_password"},
            )
            data = await resp.get_json()

            assert resp.status_code == 401
            assert "用户名或密码错误" in data["message"]

    @pytest.mark.asyncio
    async def test_login_missing_password(self, test_client, mock_config):
        """缺少密码字段 → 400"""
        resp = await test_client.post(
            "/api/auth/login",
            json={"username": "test_user"},
        )
        data = await resp.get_json()

        assert resp.status_code == 400
        assert data["message"] == "用户名和密码不能为空"

    @pytest.mark.asyncio
    async def test_login_missing_username(self, test_client, mock_config):
        """缺少用户名字段 → 400"""
        resp = await test_client.post(
            "/api/auth/login",
            json={"password": "some_password"},
        )
        data = await resp.get_json()

        assert resp.status_code == 400
        assert data["message"] == "用户名和密码不能为空"


# ============================================================================
# GET /api/auth/me
# ============================================================================
@pytest.mark.api
class TestAuthMe:
    """当前用户信息端点测试"""

    @pytest.mark.asyncio
    async def test_me_with_valid_auth(self, test_client, mock_config):
        """有效 auth → 200，返回用户信息"""
        _ensure_test_secret()
        headers = _make_auth_header(user_id="test_user")

        with (
            patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls,
            patch("src_v2.backend.api.api_login.permission_manager") as mock_pm,
        ):
            mock_user = MagicMock()
            mock_user.user_name = "test_user"
            # roles 是 async property，me 代码中 await user.roles
            mock_user.roles = _AwaitableList(["user"])

            mock_um = MagicMock()
            mock_um.get_user = AsyncMock(return_value=mock_user)
            mock_um_cls.return_value = mock_um

            mock_vip = MagicMock()
            mock_vip.vip_level = "vip_alpha"
            mock_vip.vip_end_date = datetime.datetime(2025, 12, 31, 23, 59, 59)
            mock_pm.get_vip_state = AsyncMock(return_value=mock_vip)

            resp = await test_client.get("/api/auth/me", headers=headers)
            data = await resp.get_json()

            assert resp.status_code == 200
            assert data["status"] == 200
            assert data["username"] == "test_user"
            assert "vip_alpha" in data["roles"]

    @pytest.mark.asyncio
    async def test_me_with_expired_token(self, test_client, expired_auth_headers):
        """过期 token → 401"""
        resp = await test_client.get("/api/auth/me", headers=expired_auth_headers)
        data = await resp.get_json()

        assert resp.status_code == 401
        assert "无效" in data["error"]

    @pytest.mark.asyncio
    async def test_me_with_invalid_token(self, test_client, invalid_auth_headers):
        """无效格式 token → 401"""
        resp = await test_client.get("/api/auth/me", headers=invalid_auth_headers)
        data = await resp.get_json()

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_without_token(self, test_client):
        """无 token → 401"""
        resp = await test_client.get("/api/auth/me")
        data = await resp.get_json()

        assert resp.status_code == 401


# ============================================================================
# POST /api/auth/logout
# ============================================================================
@pytest.mark.api
class TestAuthLogout:
    """登出端点测试"""

    @pytest.mark.asyncio
    async def test_logout_with_valid_auth(self, test_client, mock_config):
        """有效 auth → 200"""
        _ensure_test_secret()
        headers = _make_auth_header(user_id="test_user")
        csrf_token = _make_csrf_token()
        headers = _add_csrf(headers, csrf_token)

        resp = await test_client.post("/api/auth/logout", headers=headers)
        data = await resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == 200
        assert data["message"] == "登出成功"

    @pytest.mark.asyncio
    async def test_logout_without_token(self, test_client):
        """无 token → 401"""
        resp = await test_client.post("/api/auth/logout")
        data = await resp.get_json()

        assert resp.status_code == 401


# ============================================================================
# POST /api/auth/deleteAccount
# ============================================================================
@pytest.mark.api
class TestAuthDeleteAccount:
    """注销账号端点测试"""

    @pytest.mark.asyncio
    async def test_delete_account_with_valid_auth(self, test_client, mock_config):
        """有效 auth → 200"""
        _ensure_test_secret()
        headers = _make_auth_header(user_id="test_user")
        csrf_token = _make_csrf_token()
        headers = _add_csrf(headers, csrf_token)

        with (
            patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls,
            patch("src_v2.backend.api.api_login.CharacterManager") as mock_cm_cls,
        ):
            mock_um = MagicMock()
            mock_um.get_main_character_id = AsyncMock(return_value=12345)
            mock_um.delete_user = AsyncMock()
            mock_um_cls.return_value = mock_um

            mock_cm = MagicMock()
            mock_cm.delete_all_alias_characters_of_main_character = AsyncMock()
            mock_cm.delete_all_character_of_user = AsyncMock()
            mock_cm_cls.return_value = mock_cm

            resp = await test_client.post(
                "/api/auth/deleteAccount", headers=headers
            )
            data = await resp.get_json()

            assert resp.status_code == 200
            assert data["status"] == 200
            assert data["message"] == "注销成功"

    @pytest.mark.asyncio
    async def test_delete_account_without_token(self, test_client):
        """无 token → 401"""
        resp = await test_client.post("/api/auth/deleteAccount")
        data = await resp.get_json()

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_account_with_expired_token(
        self, test_client, expired_auth_headers
    ):
        """过期 token → 401"""
        resp = await test_client.post(
            "/api/auth/deleteAccount", headers=expired_auth_headers
        )
        data = await resp.get_json()

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_account_with_invalid_token(
        self, test_client, invalid_auth_headers
    ):
        """无效 token → 401"""
        resp = await test_client.post(
            "/api/auth/deleteAccount", headers=invalid_auth_headers
        )
        data = await resp.get_json()

        assert resp.status_code == 401
