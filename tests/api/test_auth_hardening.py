# -*- coding: utf-8 -*-
"""
认证安全加固测试（安全审计分册 03：#13 / #15 / #17）

覆盖点：
- #15-1 邀请码 /validate 匿名接口只返回 valid / available，不泄露元数据
- #15-3 注册：弱密码 400、重复用户名 400 且不回显「已存在」
- #15-4 登录：连续失败 5 次后 429；用户不存在返回 401 而非 500
- #13   refresh token：轮换后旧 token 失效、Redis 中不存明文、批量撤销
- 限流/refresh 存储组件 Redis 异常时 fail-open（登录仍成功）

复用 conftest 的 test_client / mock_config；mock 手法与 tests/api/test_auth_routes.py 保持一致。
"""
import datetime
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from werkzeug.security import generate_password_hash

import src_v2.backend.app as _backend_app

TEST_SECRET = "test-secret-key-for-jwt"


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _ensure_test_secret():
    """设置 app.secret_key 为测试密钥，使 JWT 验证与实际签名一致"""
    _backend_app.app.secret_key = TEST_SECRET


class _AwaitableList:
    """可多次 await 的列表包装器，用于模拟 async property（如 User.roles）"""

    def __init__(self, values):
        self._values = values

    def __await__(self):
        yield
        return list(self._values)


class _FakeRedis:
    """极简内存版 Redis，仅覆盖本次加固用到的命令"""

    def __init__(self):
        self.store = {}
        self.ttl = {}

    async def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttl[key] = ttl
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, *keys):
        count = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                count += 1
            self.ttl.pop(key, None)
        return count

    async def incr(self, key):
        value = int(self.store.get(key, 0)) + 1
        self.store[key] = value
        return value

    async def expire(self, key, ttl):
        self.ttl[key] = ttl
        return True

    async def sadd(self, key, *values):
        members = self.store.setdefault(key, set())
        added = 0
        for value in values:
            if value not in members:
                members.add(value)
                added += 1
        return added

    async def srem(self, key, *values):
        members = self.store.get(key) or set()
        removed = 0
        for value in values:
            if value in members:
                members.discard(value)
                removed += 1
        return removed

    async def smembers(self, key):
        return set(self.store.get(key) or set())


class _FakeRedisManager:
    """伪造的 Redis 连接管理器（只暴露 redis 属性）"""

    def __init__(self, redis):
        self.redis = redis


def _redis_down():
    """模拟 Redis 不可用：get_redis_manager 直接抛异常"""
    raise RuntimeError("Redis 未初始化")


# ============================================================================
# #15-1 邀请码 /validate 最小化返回
# ============================================================================
@pytest.mark.api
class TestInviteCodeValidateMinimalResponse:
    """/api/invite-code/validate 只返回 valid / available"""

    @pytest.mark.asyncio
    async def test_validate_only_returns_valid_and_available(self, test_client, mock_config):
        """即使后端返回完整字典，响应也只含 valid / available"""
        full_result = {
            "valid": True,
            "available": True,
            "invite_code": "SECRET-CODE",
            "creator_user_name": "creator",
            "used_count_current": 1,
            "used_count_max": 5,
            "create_date": datetime.datetime(2024, 1, 1, 0, 0, 0),
        }
        with patch("src_v2.backend.api.api_invite_code.permission_manager") as mock_pm:
            mock_pm.validate_invite_code = AsyncMock(return_value=dict(full_result))

            resp = await test_client.post(
                "/api/invite-code/validate",
                json={"inviteCode": "SECRET-CODE"},
            )
            data = await resp.get_json()

        assert resp.status_code == 200
        assert data == {"status": 200, "data": {"valid": True, "available": True}}
        # 不得泄露任何元数据
        raw = await resp.get_data(as_text=True)
        for leaked in ("SECRET-CODE", "creator", "used_count", "createDate", "create_date"):
            assert leaked not in raw

    @pytest.mark.asyncio
    async def test_validate_invalid_code_keeps_400(self, test_client, mock_config):
        """失败分支保持原 400 文案"""
        with patch("src_v2.backend.api.api_invite_code.permission_manager") as mock_pm:
            mock_pm.validate_invite_code = AsyncMock(
                return_value={"valid": False, "available": False}
            )

            resp = await test_client.post(
                "/api/invite-code/validate",
                json={"inviteCode": "BAD-CODE"},
            )
            data = await resp.get_json()

        assert resp.status_code == 400
        assert data["message"] == "邀请码不存在"


# ============================================================================
# #15-4 登录防暴力破解 / 防用户名枚举
# ============================================================================
@pytest.mark.api
class TestLoginRateLimitAndEnumeration:
    """登录限流与用户名枚举防护"""

    @pytest.mark.asyncio
    async def test_login_returns_429_after_five_failures(self, test_client, mock_config):
        """连续失败 5 次后，第 6 次（即使密码正确）返回 429"""
        _ensure_test_secret()
        fake_redis = _FakeRedis()
        valid_hash = generate_password_hash("correct_password")

        with (
            patch(
                "src_v2.core.utils.login_guard.get_redis_manager",
                return_value=_FakeRedisManager(fake_redis),
            ),
            patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls,
        ):
            mock_um = MagicMock()
            mock_um.get_password_hash = AsyncMock(return_value=valid_hash)
            mock_um_cls.return_value = mock_um

            for i in range(5):
                resp = await test_client.post(
                    "/api/auth/login",
                    json={"username": "rate_user", "password": "wrong_password"},
                )
                assert resp.status_code == 401, f"第 {i + 1} 次失败应返回 401"

            # 第 6 次：即便密码正确也应被限流拦住，且不再校验密码
            resp = await test_client.post(
                "/api/auth/login",
                json={"username": "rate_user", "password": "correct_password"},
            )
            data = await resp.get_json()

        assert resp.status_code == 429
        assert data["message"] == "登录尝试过于频繁，请稍后再试"

    @pytest.mark.asyncio
    async def test_login_nonexistent_user_returns_401_not_500(self, test_client, mock_config):
        """用户不存在 → 401（走 dummy 哈希校验，不抛异常、不泄露用户是否存在）"""
        from src_v2.backend.api import api_login as api_login_module

        with (
            patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls,
            patch(
                "src_v2.backend.api.api_login.check_password_hash",
                return_value=False,
            ) as mock_check,
        ):
            mock_um = MagicMock()
            # 真实实现里「用户不存在」时 get_password_hash 返回 None
            mock_um.get_password_hash = AsyncMock(return_value=None)
            mock_um_cls.return_value = mock_um

            resp = await test_client.post(
                "/api/auth/login",
                json={"username": "no_such_user", "password": "any_password1"},
            )
            data = await resp.get_json()

        assert resp.status_code == 401
        assert data["message"] == "用户名或密码错误"
        # 必须执行过一次哈希校验（用模块级 dummy 哈希），避免时间侧信道枚举
        assert mock_check.called
        assert mock_check.call_args[0][0] == api_login_module._DUMMY_PASSWORD_HASH

    @pytest.mark.asyncio
    async def test_login_fail_open_when_redis_down(self, test_client, mock_config):
        """限流与 refresh 存储组件 Redis 异常时登录仍成功（fail-open）"""
        _ensure_test_secret()
        valid_hash = generate_password_hash("correct_password")
        mock_user = MagicMock()
        mock_user.roles = _AwaitableList(["user"])

        with (
            patch("src_v2.core.utils.login_guard.get_redis_manager", side_effect=_redis_down),
            patch("src_v2.core.user.refresh_token_store.get_redis_manager", side_effect=_redis_down),
            patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls,
            patch("src_v2.backend.api.api_login.permission_manager") as mock_pm,
        ):
            mock_um = MagicMock()
            mock_um.get_password_hash = AsyncMock(return_value=valid_hash)
            mock_um.get_user = AsyncMock(return_value=mock_user)
            mock_um_cls.return_value = mock_um
            mock_pm.get_vip_state = AsyncMock(return_value=None)

            resp = await test_client.post(
                "/api/auth/login",
                json={"username": "redis_down_user", "password": "correct_password"},
            )
            data = await resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == 200
        # 降级行为：Redis 挂了就没有 refresh_token cookie，但 access token 照常下发
        set_cookies = resp.headers.getlist("Set-Cookie")
        assert any(c.startswith("auth_token=") for c in set_cookies)
        assert not any(c.startswith("refresh_token=") for c in set_cookies)


# ============================================================================
# #15-3 注册加固
# ============================================================================
@pytest.mark.api
class TestSignupHardening:
    """注册密码强度与错误文案"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "weak_password",
        ["abc123", "abcdefgh", "12345678", "Ab1", ""],
        ids=["too_short", "letters_only", "digits_only", "tiny", "empty"],
    )
    async def test_signup_weak_password_returns_400(
        self, test_client, mock_config, weak_password
    ):
        """弱密码 → 400 密码强度不足"""
        with patch("src_v2.backend.api.api_login.permission_manager") as mock_pm:
            mock_pm.validate_invite_code = AsyncMock(
                return_value={"valid": True, "available": True}
            )

            resp = await test_client.post(
                "/api/auth/signup",
                json={
                    "username": "weak_user",
                    "password": weak_password,
                    "inviteCode": "VALID-CODE",
                },
            )
            data = await resp.get_json()

        assert resp.status_code == 400
        assert data["message"] == "密码强度不足：至少 8 位且需包含字母和数字"

    @pytest.mark.asyncio
    async def test_signup_duplicate_username_hides_details(self, test_client, mock_config):
        """重复用户名 → 400 通用文案，响应体不含 exists / 已存在"""
        from src_v2.core.utils import KahunaException

        with (
            patch("src_v2.backend.api.api_login.permission_manager") as mock_pm,
            patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls,
        ):
            mock_pm.validate_invite_code = AsyncMock(
                return_value={"valid": True, "available": True}
            )
            mock_um = MagicMock()
            mock_um.create_user = AsyncMock(side_effect=KahunaException("用户已存在"))
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
            raw = (await resp.get_data(as_text=True)).lower()

        assert resp.status_code == 400
        assert data["status"] == 400
        assert "exists" not in raw
        assert "已存在" not in (await resp.get_data(as_text=True))

    @pytest.mark.asyncio
    async def test_signup_rate_limited_per_ip(self, test_client, mock_config):
        """同一 IP 每分钟第 6 次注册请求 → 429"""
        fake_redis = _FakeRedis()
        with (
            patch(
                "src_v2.core.utils.login_guard.get_redis_manager",
                return_value=_FakeRedisManager(fake_redis),
            ),
            patch("src_v2.backend.api.api_login.permission_manager") as mock_pm,
        ):
            mock_pm.validate_invite_code = AsyncMock(
                return_value={"valid": False}
            )
            codes = []
            for _ in range(6):
                resp = await test_client.post(
                    "/api/auth/signup",
                    json={
                        "username": "flood_user",
                        "password": "password123",
                        "inviteCode": "BAD-CODE",
                    },
                )
                codes.append(resp.status_code)

        # 前 5 次仍是正常业务校验（400），第 6 次被限流
        assert codes[:5] == [400] * 5
        assert codes[5] == 429


# ============================================================================
# #13 refresh token 轮换与存储安全
# ============================================================================
@pytest.mark.api
class TestRefreshTokenRotation:
    """/api/auth/refresh 轮换行为"""

    @pytest.mark.asyncio
    async def test_refresh_rotates_and_old_token_becomes_invalid(
        self, test_app, test_client, mock_config
    ):
        """首次轮换成功下发新 token；旧 token 再次使用 → 401 并清除 cookie"""
        _ensure_test_secret()
        mock_user = MagicMock()
        mock_user.roles = _AwaitableList(["user"])

        store = MagicMock()
        # 第一次：旧 token 有效 → 轮换出新 token；第二次：旧 token 已失效
        store.rotate_refresh_token = AsyncMock(
            side_effect=[("test_user", "new_raw_token"), None]
        )

        with (
            patch("src_v2.backend.api.api_login.refresh_token_store", store),
            patch("src_v2.backend.api.api_login.UserManager") as mock_um_cls,
        ):
            mock_um = MagicMock()
            mock_um.get_user = AsyncMock(return_value=mock_user)
            mock_um_cls.return_value = mock_um

            resp1 = await test_client.post(
                "/api/auth/refresh",
                headers={"Cookie": "refresh_token=old_raw_token"},
            )
            assert resp1.status_code == 200
            set_cookies_1 = resp1.headers.getlist("Set-Cookie")
            # 重新下发轮换后的 refresh token（7 天）与新的 access / csrf token
            assert any(
                "refresh_token=new_raw_token" in c and "Max-Age=604800" in c
                for c in set_cookies_1
            )
            assert any(c.startswith("auth_token=") for c in set_cookies_1)
            assert any(c.startswith("csrf_token=") for c in set_cookies_1)

            # 用干净的 client 模拟「另一处持有旧 token」的客户端再次刷新
            stale_client = test_app.test_client()
            resp2 = await stale_client.post(
                "/api/auth/refresh",
                headers={"Cookie": "refresh_token=old_raw_token"},
            )
            data2 = await resp2.get_json()
            set_cookies_2 = resp2.headers.getlist("Set-Cookie")

        assert store.rotate_refresh_token.await_count == 2
        assert store.rotate_refresh_token.await_args_list[0].args == ("old_raw_token",)
        assert store.rotate_refresh_token.await_args_list[1].args == ("old_raw_token",)
        assert resp2.status_code == 401
        assert data2["message"] == "无效或过期的 refresh token"
        # 轮换失败必须清除 refresh_token cookie
        assert any(
            c.startswith("refresh_token=;") and "Max-Age=0" in c for c in set_cookies_2
        )

    @pytest.mark.asyncio
    async def test_logout_revokes_current_refresh_token(self, test_client, mock_config):
        """登出撤销当前 refresh token"""
        _ensure_test_secret()
        import datetime as _dt

        import jwt

        token = jwt.encode(
            {
                "user_id": "test_user",
                "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=1),
            },
            TEST_SECRET,
            algorithm="HS256",
        )
        store = MagicMock()
        store.revoke_refresh_token = AsyncMock()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "csrf123",
            "Cookie": "csrf_token=csrf123; refresh_token=current_raw_token",
        }

        with patch("src_v2.backend.api.api_login.refresh_token_store", store):
            resp = await test_client.post("/api/auth/logout", headers=headers)
            data = await resp.get_json()

        assert resp.status_code == 200
        assert data["message"] == "登出成功"
        store.revoke_refresh_token.assert_awaited_once_with("current_raw_token")

    @pytest.mark.asyncio
    async def test_delete_account_revokes_all_tokens(self, test_client, mock_config):
        """注销账号撤销该用户全部 refresh token"""
        _ensure_test_secret()
        import datetime as _dt

        import jwt

        token = jwt.encode(
            {
                "user_id": "test_user",
                "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=1),
            },
            TEST_SECRET,
            algorithm="HS256",
        )
        store = MagicMock()
        store.revoke_all_for_user = AsyncMock(return_value=3)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": "csrf123",
            "Cookie": "csrf_token=csrf123; refresh_token=current_raw_token",
        }

        with (
            patch("src_v2.backend.api.api_login.refresh_token_store", store),
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

            resp = await test_client.post("/api/auth/deleteAccount", headers=headers)
            data = await resp.get_json()

        assert resp.status_code == 200
        assert data["message"] == "注销成功"
        store.revoke_all_for_user.assert_awaited_once_with("test_user")


# ============================================================================
# #13 refresh_token_store 存储层（不落明文 / 轮换 / 批量撤销）
# ============================================================================
@pytest.mark.api
class TestRefreshTokenStore:
    """refresh_token_store 单元级验证（用内存版 Redis）"""

    @pytest.mark.asyncio
    async def test_store_never_persists_plaintext_and_rotates(self):
        """Redis 中只有 sha256 哈希；轮换后旧 token 失效；可批量撤销"""
        from src_v2.core.user import refresh_token_store as store_module

        fake_redis = _FakeRedis()
        with patch(
            "src_v2.core.user.refresh_token_store.get_redis_manager",
            return_value=_FakeRedisManager(fake_redis),
        ):
            raw_token = await store_module.issue_refresh_token("user1")
            assert raw_token

            token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
            assert raw_token not in fake_redis.store
            assert fake_redis.store[f"refresh_token:{token_hash}"] == "user1"
            # 所有 value 都不能包含明文 token
            assert all(raw_token not in str(v) for v in fake_redis.store.values())
            # 7 天绝对过期
            assert fake_redis.ttl[f"refresh_token:{token_hash}"] == 7 * 24 * 3600
            assert await store_module.resolve_refresh_token(raw_token) == "user1"

            rotated = await store_module.rotate_refresh_token(raw_token)
            assert rotated is not None
            user_id, new_raw_token = rotated
            assert user_id == "user1"
            assert new_raw_token != raw_token
            # 旧 token 立即失效，新 token 可用
            assert await store_module.resolve_refresh_token(raw_token) is None
            assert await store_module.resolve_refresh_token(new_raw_token) == "user1"

            revoked = await store_module.revoke_all_for_user("user1")
            assert revoked == 1
            assert await store_module.resolve_refresh_token(new_raw_token) is None

    @pytest.mark.asyncio
    async def test_store_degrades_when_redis_down(self):
        """Redis 不可用时降级：issue 返回 ''，resolve/rotate 返回 None，revoke 静默"""
        from src_v2.core.user import refresh_token_store as store_module

        with patch(
            "src_v2.core.user.refresh_token_store.get_redis_manager",
            side_effect=_redis_down,
        ):
            assert await store_module.issue_refresh_token("user1") == ''
            assert await store_module.resolve_refresh_token("any_token") is None
            assert await store_module.rotate_refresh_token("any_token") is None
            # 不抛异常即为通过
            assert await store_module.revoke_refresh_token("any_token") is None
            assert await store_module.revoke_all_for_user("user1") == 0
