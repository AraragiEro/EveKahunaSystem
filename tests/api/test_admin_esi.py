"""
API Route 测试: /api/admin/esi Blueprint
测试 TQ 状态查询端点和管理员权限校验
"""
import datetime as _dt
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from src_v2.core.permission.permission_manager import permission_manager

pytestmark = pytest.mark.api

TEST_SECRET = "test-secret-key-for-jwt"


def _make_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=24),
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_make_token(user_id)}"}


def _set_secret(test_app) -> None:
    test_app.app.secret_key = TEST_SECRET


class TestTqStatus:
    """GET /api/admin/esi/tq-status — 管理员 TQ 状态查询"""

    URL = "/api/admin/esi/tq-status"

    async def test_tq_status_returns_valid_value(self, test_client, test_app):
        """管理员请求应返回有效的 TQ 状态"""
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
            patch("src_v2.backend.api.api_admin_esi.check_tq_status", new_callable=AsyncMock) as m_tq,
        ):
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None
            m_tq.return_value = "online"

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            assert resp.status_code == 200
            data = await resp.get_json()
            assert data["status"] == 200
            assert data["data"]["status"] == "online"

    async def test_tq_status_rejects_non_admin(self, test_client, test_app):
        """非管理员用户应被拒绝访问"""
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_roles.return_value = ["user"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(self.URL, headers=_auth("test_user"))
            assert resp.status_code == 403


# ============================================================
# GET /api/admin/esi/characters
# ============================================================

class TestAdminEsiCharacters:
    """GET /api/admin/esi/characters — 角色列表"""

    URL = "/api/admin/esi/characters"
    FIXED_NOW = _dt.datetime(2024, 6, 15, 12, 0, 0)  # 固定北京时间，用于状态分类测试

    # ---- 辅助 ----

    @staticmethod
    def _make_char(character_id=1001, character_name="Test Char",
                   owner_user_name="user_a", expires_time=None,
                   birthday=None, corporation_id=None, director=False):
        """创建 Mock EveAuthedCharacter 对象"""
        char = MagicMock()
        char.character_id = character_id
        char.character_name = character_name
        char.owner_user_name = owner_user_name
        char.access_token = "test_access_token"
        char.refresh_token = "test_refresh_token"
        char.expires_time = expires_time
        char.birthday = birthday or _dt.datetime(2020, 1, 1)
        char.corporation_id = corporation_id
        char.director = director
        return char

    @staticmethod
    def _mock_db(characters):
        """创建 mock EveAuthedCharacterDBUtils.select_all_characters（返回指定角色列表）"""
        return patch(
            "src_v2.backend.api.api_admin_esi.EveAuthedCharacterDBUtils.select_all_characters",
            new_callable=AsyncMock,
            return_value=characters,
        )

    # ---- tests ----

    async def test_characters_list_returns_all(self, test_client, test_app):
        """有效管理员 → 返回所有角色列表"""
        _set_secret(test_app)
        ref = self.FIXED_NOW
        chars = [
            self._make_char(1001, "Alpha", "user_a",
                            expires_time=ref + _dt.timedelta(hours=2)),
            self._make_char(1002, "Beta", "user_b",
                            expires_time=ref + _dt.timedelta(hours=1)),
        ]
        with (
            self._mock_db(chars) as m_db,
            patch("src_v2.backend.api.api_admin_esi.get_beijing_utctime",
                  return_value=self.FIXED_NOW),
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            data = await resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == 200
        assert data["total"] == 2
        assert len(data["data"]) == 2

    async def test_characters_list_sanitized(self, test_client, test_app):
        """响应中不包含 access_token 和 refresh_token"""
        _set_secret(test_app)
        ref = self.FIXED_NOW
        char = self._make_char(1001, "Alpha", "user_a",
                               expires_time=ref + _dt.timedelta(hours=2))
        with (
            self._mock_db([char]) as m_db,
            patch("src_v2.backend.api.api_admin_esi.get_beijing_utctime",
                  return_value=self.FIXED_NOW),
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            data = await resp.get_json()

        assert resp.status_code == 200
        for item in data["data"]:
            assert "access_token" not in item
            assert "refresh_token" not in item

    async def test_characters_filter_by_user(self, test_client, test_app):
        """?user_name=user_b 只返回 user_b 的角色"""
        _set_secret(test_app)
        ref = self.FIXED_NOW
        chars = [
            self._make_char(1001, "Alpha", "user_a",
                            expires_time=ref + _dt.timedelta(hours=2)),
            self._make_char(1002, "Beta", "user_b",
                            expires_time=ref + _dt.timedelta(hours=1)),
            self._make_char(1003, "Gamma", "user_b",
                            expires_time=ref + _dt.timedelta(hours=3)),
        ]
        with (
            self._mock_db(chars) as m_db,
            patch("src_v2.backend.api.api_admin_esi.get_beijing_utctime",
                  return_value=self.FIXED_NOW),
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(
                self.URL + "?user_name=user_b", headers=_auth("admin")
            )
            data = await resp.get_json()

        assert resp.status_code == 200
        assert data["total"] == 2
        assert all(r["owner_user_name"] == "user_b" for r in data["data"])

    async def test_characters_filter_by_status(self, test_client, test_app):
        """?status=expired 只返回已过期的角色"""
        _set_secret(test_app)
        ref = self.FIXED_NOW
        chars = [
            self._make_char(1001, "Valid", "user_a",
                            expires_time=ref + _dt.timedelta(hours=2)),
            self._make_char(1002, "Expired", "user_b",
                            expires_time=ref - _dt.timedelta(hours=1)),
            self._make_char(1003, "AboutToExp", "user_c",
                            expires_time=ref + _dt.timedelta(seconds=60)),
        ]
        with (
            self._mock_db(chars) as m_db,
            patch("src_v2.backend.api.api_admin_esi.get_beijing_utctime",
                  return_value=self.FIXED_NOW),
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(
                self.URL + "?status=expired", headers=_auth("admin")
            )
            data = await resp.get_json()

        assert resp.status_code == 200
        assert data["total"] == 1
        assert data["data"][0]["character_name"] == "Expired"
        assert data["data"][0]["token_status"] == "expired"

    async def test_characters_status_classification(self, test_client, test_app):
        """验证 token_status 分类：valid / about_to_expire / expired / unknown"""
        _set_secret(test_app)
        ref = self.FIXED_NOW
        chars = [
            self._make_char(1001, "Valid", "user_a",
                            expires_time=ref + _dt.timedelta(hours=2)),
            self._make_char(1002, "AboutToExp", "user_b",
                            expires_time=ref + _dt.timedelta(seconds=120)),
            self._make_char(1003, "Expired", "user_c",
                            expires_time=ref - _dt.timedelta(minutes=10)),
            self._make_char(1004, "Unknown", "user_d",
                            expires_time=None),
        ]
        with (
            self._mock_db(chars) as m_db,
            patch("src_v2.backend.api.api_admin_esi.get_beijing_utctime",
                  return_value=self.FIXED_NOW),
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            data = await resp.get_json()

        assert resp.status_code == 200
        status_map = {r["character_name"]: r["token_status"] for r in data["data"]}
        assert status_map["Valid"] == "valid"
        assert status_map["AboutToExp"] == "about_to_expire"
        assert status_map["Expired"] == "expired"
        assert status_map["Unknown"] == "unknown"

    async def test_characters_rejects_non_admin(self, test_client, test_app):
        """普通用户 → 403"""
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_roles.return_value = ["user"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(self.URL, headers=_auth("test_user"))
            assert resp.status_code == 403

    async def test_characters_rejects_unauthenticated(self, test_client, test_app):
        """无 token → 401"""
        resp = await test_client.get(self.URL)
        assert resp.status_code == 401


# ============================================================
# POST /api/admin/esi/characters/{id}/test
# ============================================================

class TestAdminEsiTestToken:
    """POST /api/admin/esi/characters/{id}/test — Token 测试"""

    # ---- 辅助 ----

    @staticmethod
    def _make_char(character_id=1001, character_name="Test Char",
                   owner_user_name="user_a", expires_time=None,
                   has_token=True):
        """创建带 token 的 Mock 角色"""
        char = MagicMock()
        char.character_id = character_id
        char.character_name = character_name
        char.owner_user_name = owner_user_name
        char.access_token = "test_access_token" if has_token else None
        char.refresh_token = "test_refresh_token" if has_token else None
        char.expires_time = expires_time
        return char

    @staticmethod
    def _mock_redis(ttl_value=-2):
        """创建 redis mock，默认 key 不存在 (ttl=-2)"""
        redis = MagicMock()
        redis.ttl = AsyncMock(return_value=ttl_value)
        redis.setex = AsyncMock(return_value=True)
        return redis

    # ---- tests ----

    async def test_test_token_success(self, test_client, test_app):
        """有效 token → 200 + success=True"""
        _set_secret(test_app)
        char = self._make_char(1001, "Alpha")
        esi_data = {"name": "Alpha"}

        with (
            patch("src_v2.backend.api.api_admin_esi.EveAuthedCharacterDBUtils") as m_utils,
            patch("src_v2.backend.api.api_admin_esi.get_redis_manager") as m_rdm,
            patch("src_v2.backend.api.api_admin_esi.esi_manager") as m_esi_mgr,
            patch("src_v2.backend.api.api_admin_esi.get_request_async") as m_req,
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_utils.select_character_by_character_id = AsyncMock(return_value=char)
            m_rdm.return_value.redis = self._mock_redis(ttl_value=-2)
            m_esi_mgr.get_tokens = AsyncMock(return_value=True)
            m_req.return_value = (esi_data, 1, 200, {})
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.post(
                "/api/admin/esi/characters/1001/test", headers=_auth("admin")
            )
            body = await resp.get_json()

        assert resp.status_code == 200
        assert body["status"] == 200
        assert body["data"]["success"] is True
        assert body["data"]["status_code"] == 200
        assert body["data"]["character_name"] == "Alpha"
        assert "latency_ms" in body["data"]

    async def test_test_token_cooldown(self, test_client, test_app):
        """冷却中 → 429"""
        _set_secret(test_app)
        char = self._make_char(1001, "Alpha")

        with (
            patch("src_v2.backend.api.api_admin_esi.EveAuthedCharacterDBUtils") as m_utils,
            patch("src_v2.backend.api.api_admin_esi.get_redis_manager") as m_rdm,
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_utils.select_character_by_character_id = AsyncMock(return_value=char)
            m_rdm.return_value.redis = self._mock_redis(ttl_value=25)  # 剩余 25 秒
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.post(
                "/api/admin/esi/characters/1001/test", headers=_auth("admin")
            )
            body = await resp.get_json()

        assert resp.status_code == 429
        assert "冷却" in body["message"]
        assert body["cooldown_remaining"] == 25

    async def test_test_token_not_found(self, test_client, test_app):
        """不存在的 character_id → 404"""
        _set_secret(test_app)
        with (
            patch("src_v2.backend.api.api_admin_esi.EveAuthedCharacterDBUtils") as m_utils,
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_utils.select_character_by_character_id = AsyncMock(return_value=None)
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.post(
                "/api/admin/esi/characters/99999/test", headers=_auth("admin")
            )
            body = await resp.get_json()

        assert resp.status_code == 404
        assert "不存在" in body["message"]

    async def test_test_token_no_access_token(self, test_client, test_app):
        """角色没有 access_token → 400"""
        _set_secret(test_app)
        char = self._make_char(1001, "Alpha", has_token=False)

        with (
            patch("src_v2.backend.api.api_admin_esi.EveAuthedCharacterDBUtils") as m_utils,
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_utils.select_character_by_character_id = AsyncMock(return_value=char)
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.post(
                "/api/admin/esi/characters/1001/test", headers=_auth("admin")
            )
            body = await resp.get_json()

        assert resp.status_code == 400
        assert "access_token" in body["message"]


# ============================================================
# GET /api/admin/esi/buckets — ESI 速率限制桶统计
# ============================================================


class TestAdminEsiBuckets:
    """GET /api/admin/esi/buckets — ESI 速率限制桶统计"""

    URL = "/api/admin/esi/buckets"

    async def test_buckets_returns_pools(self, test_client, test_app):
        """有效管理员 → 返回所有桶统计"""
        _set_secret(test_app)
        mock_stats = {
            "pools": {
                "__legacy__": {
                    "rate": 300.0, "max": 1200.0,
                    "remaining": 500.0, "error_count": 2,
                },
                "esi-industry": {
                    "rate": 10.0, "max": 100.0,
                    "remaining": 80.0, "error_count": 0,
                },
            },
            "func_mappings": {
                "get_character_industry_jobs": "esi-industry",
                "get_corporation_industry_jobs": "esi-industry",
            },
            "missing_headers": ["get_old_endpoint"],
        }
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
            patch("src_v2.backend.api.api_admin_esi.esi_manager") as m_esi,
        ):
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None
            m_esi.get_pool_stats.return_value = mock_stats

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            data = await resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == 200
        pools = data["data"]["pools"]
        assert len(pools) == 2

        legacy = next(p for p in pools if p["pool_name"] == "__legacy__")
        assert legacy["rate"] == 300.0
        assert legacy["max"] == 1200.0
        assert legacy["remaining"] == 500.0
        assert legacy["error_count"] == 2
        assert legacy["endpoints"] == []

        ind = next(p for p in pools if p["pool_name"] == "esi-industry")
        assert ind["endpoints"] == [
            "get_character_industry_jobs",
            "get_corporation_industry_jobs",
        ]

        assert data["data"]["missing_headers"] == ["get_old_endpoint"]

    async def test_buckets_rejects_non_admin(self, test_client, test_app):
        """非管理员 → 403"""
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_roles.return_value = ["user"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(self.URL, headers=_auth("test_user"))
            assert resp.status_code == 403


# ============================================================
# GET /api/admin/esi/queue-depth — 请求队列深度
# ============================================================


class TestAdminEsiQueueDepth:
    """GET /api/admin/esi/queue-depth — 请求队列深度"""

    URL = "/api/admin/esi/queue-depth"

    async def test_queue_depth_returns_values(self, test_client, test_app):
        """有效管理员 → 返回队列深度"""
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
            patch("src_v2.backend.api.api_admin_esi.esi_manager") as m_esi,
        ):
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None
            m_esi.get_queue_depth.return_value = {"backlog": 5, "in_flight": 2}

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            data = await resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == 200
        assert data["data"]["backlog"] == 5
        assert data["data"]["in_flight"] == 2

    async def test_queue_depth_rejects_non_admin(self, test_client, test_app):
        """非管理员 → 403"""
        _set_secret(test_app)
        with (
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_roles.return_value = ["user"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(self.URL, headers=_auth("test_user"))
            assert resp.status_code == 403


# ============================================================
# GET /api/admin/esi/usage-log — ESI 使用日志（分页）
# ============================================================


class TestAdminEsiUsageLog:
    """GET /api/admin/esi/usage-log — ESI 使用日志"""

    URL = "/api/admin/esi/usage-log"

    @staticmethod
    def _make_log(
        id=1,
        endpoint="/characters/{id}/",
        pool_name="__legacy__",
        character_id=1001,
        status_code=200,
        latency_ms=150.0,
        error_message=None,
        timestamp=None,
    ):
        log = MagicMock()
        log.id = id
        log.timestamp = timestamp or _dt.datetime(2024, 6, 15, 12, 0, 0)
        log.endpoint = endpoint
        log.pool_name = pool_name
        log.character_id = character_id
        log.status_code = status_code
        log.latency_ms = latency_ms
        log.error_message = error_message
        return log

    async def test_usage_log_returns_items(self, test_client, test_app):
        """有效管理员 → 返回日志列表"""
        _set_secret(test_app)
        logs = [
            self._make_log(1, endpoint="/characters/1001/"),
            self._make_log(2, endpoint="/characters/1002/"),
        ]
        with (
            patch("src_v2.backend.api.api_admin_esi.EsiUsageLogDBUtils") as m_utils,
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_utils.query_logs = AsyncMock(return_value=logs)
            m_utils.get_total_count = AsyncMock(return_value=2)
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            data = await resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == 200
        assert len(data["data"]["items"]) == 2
        assert data["data"]["total"] == 2
        assert data["data"]["has_more"] is False

        # Verify item fields
        item = data["data"]["items"][0]
        assert "id" in item
        assert "timestamp" in item
        assert "endpoint" in item
        assert "pool_name" in item
        assert "character_id" in item
        assert "status_code" in item
        assert "latency_ms" in item

    async def test_usage_log_pagination(self, test_client, test_app):
        """分页参数生效，has_more 正确"""
        _set_secret(test_app)
        logs = [self._make_log(i) for i in range(1, 4)]
        with (
            patch("src_v2.backend.api.api_admin_esi.EsiUsageLogDBUtils") as m_utils,
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_utils.query_logs = AsyncMock(return_value=logs)
            m_utils.get_total_count = AsyncMock(return_value=10)
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(
                self.URL + "?limit=3&offset=0", headers=_auth("admin")
            )
            data = await resp.get_json()

        assert resp.status_code == 200
        assert len(data["data"]["items"]) == 3
        assert data["data"]["total"] == 10
        assert data["data"]["has_more"] is True  # 0 + 3 < 10

    async def test_usage_log_empty(self, test_client, test_app):
        """无日志时返回空列表"""
        _set_secret(test_app)
        with (
            patch("src_v2.backend.api.api_admin_esi.EsiUsageLogDBUtils") as m_utils,
            patch.object(permission_manager, "get_user_roles", new_callable=AsyncMock) as m_roles,
            patch.object(permission_manager, "get_user_permissions", new_callable=AsyncMock) as m_perms,
            patch.object(permission_manager, "get_all_descendant_roles", new_callable=AsyncMock) as m_desc,
            patch.object(permission_manager, "get_vip_state", new_callable=AsyncMock) as m_vip,
        ):
            m_utils.query_logs = AsyncMock(return_value=[])
            m_utils.get_total_count = AsyncMock(return_value=0)
            m_roles.return_value = ["admin"]
            m_perms.return_value = []
            m_desc.return_value = []
            m_vip.return_value = None

            resp = await test_client.get(self.URL, headers=_auth("admin"))
            data = await resp.get_json()

        assert resp.status_code == 200
        assert data["data"]["items"] == []
        assert data["data"]["total"] == 0
        assert data["data"]["has_more"] is False
