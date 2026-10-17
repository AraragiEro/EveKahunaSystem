# -*- coding: utf-8 -*-
"""
API 测试 - 系数监控相关路由

测试集:
- GET /api/EVE/home/searchSystems - 星系搜索
"""
import datetime
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest


@pytest.fixture(autouse=True)
def _setup_app_secret(mock_config):
    """确保 Quart app 使用测试 secret key"""
    from src_v2.backend.app import app

    app.secret_key = "test-secret-key-for-jwt"


@pytest.fixture
def user_auth_headers():
    """JWT 认证头部 (含 user_id，匹配路由中 g.current_user["user_id"])"""
    payload = {
        "user_name": "test_user",
        "user_id": "test_user",
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=24),
    }
    token = jwt.encode(payload, "test-secret-key-for-jwt", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# 星系搜索路由
# ============================================================


@pytest.mark.api
class TestSearchSystems:
    """GET /api/EVE/home/searchSystems - 星系搜索"""

    @pytest.mark.asyncio
    async def test_search_systems_valid(self, test_client, user_auth_headers):
        """有效搜索关键词 Jita → 返回星系列表"""
        # Mock SDE 数据库只读会话
        mock_sde_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (30000142, "Jita", "吉他"),
            (30005319, "Jita IV - Moon 1", "吉他 IV - 卫星 1"),
        ]
        mock_sde_session.execute = AsyncMock(return_value=mock_result)

        mock_sde_db = MagicMock()
        mock_sde_db.get_readonly_session.return_value.__aenter__ = AsyncMock(
            return_value=mock_sde_session
        )
        mock_sde_db.get_readonly_session.return_value.__aexit__ = AsyncMock(
            return_value=None
        )

        with patch(
            "src_v2.model.EVE.sde.utils.get_db_manager",
            new_callable=AsyncMock,
            return_value=mock_sde_db,
        ):
            resp = await test_client.get(
                "/api/EVE/home/searchSystems?q=Jita",
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert len(body["data"]) == 2
        assert body["count"] == 2
        assert body["data"][0]["system_id"] == 30000142
        assert body["data"][0]["system_name"] == "Jita"
        assert body["data"][0]["system_name_zh"] == "吉他"

    @pytest.mark.asyncio
    async def test_search_systems_empty(self, test_client, user_auth_headers):
        """搜索词过短 (< 2字符) → 空列表"""
        resp = await test_client.get(
            "/api/EVE/home/searchSystems?q=a",
            headers=user_auth_headers,
        )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"] == []
        assert body["count"] == 0

    @pytest.mark.asyncio
    async def test_search_systems_no_match(self, test_client, user_auth_headers):
        """无匹配结果 → 空列表"""
        mock_sde_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_sde_session.execute = AsyncMock(return_value=mock_result)

        mock_sde_db = MagicMock()
        mock_sde_db.get_readonly_session.return_value.__aenter__ = AsyncMock(
            return_value=mock_sde_session
        )
        mock_sde_db.get_readonly_session.return_value.__aexit__ = AsyncMock(
            return_value=None
        )

        with patch(
            "src_v2.model.EVE.sde.utils.get_db_manager",
            new_callable=AsyncMock,
            return_value=mock_sde_db,
        ):
            resp = await test_client.get(
                "/api/EVE/home/searchSystems?q=zzzzzzzz",
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"] == []
        assert body["count"] == 0

    @pytest.mark.asyncio
    async def test_search_systems_unauthorized(self, test_client):
        """无认证 → 401"""
        resp = await test_client.get("/api/EVE/home/searchSystems?q=Jita")
        assert resp.status_code == 401


# ============================================================
# 关注星系 CRUD 路由
# ============================================================


@pytest.mark.api
class TestWatchlistCRUD:
    """关注星系增删查 - GET/POST coefficient/watchlist, add, remove"""

    # ---- helpers ----

    @staticmethod
    def _patch_watchlist_db(system_ids=None):
        """patch UserWatchedSystemDBUtils 的查询/写入方法（关注星系列表 CRUD）"""
        return patch(
            "src_v2.backend.api.EVE.api_home.UserWatchedSystemDBUtils",
            select_system_ids_by_user_name=AsyncMock(return_value=system_ids or []),
            add_system_ignore_conflict=AsyncMock(),
            delete_by_user_and_system=AsyncMock(),
        )

    # ---- tests ----

    @pytest.mark.asyncio
    async def test_watchlist_unauthorized(self, test_client):
        """无认证访问 watchlist/add/remove → 全部 401"""
        # GET watchlist
        resp = await test_client.get("/api/EVE/home/coefficient/watchlist")
        assert resp.status_code == 401

        # POST add
        resp = await test_client.post(
            "/api/EVE/home/coefficient/add",
            json={"system_id": 30000142},
        )
        assert resp.status_code == 401

        # POST remove
        resp = await test_client.post(
            "/api/EVE/home/coefficient/remove",
            json={"system_id": 30000142},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_watchlist_empty(self, test_client, user_auth_headers):
        """空关注列表 → 返回空数组"""
        with self._patch_watchlist_db(system_ids=[]):
            resp = await test_client.get(
                "/api/EVE/home/coefficient/watchlist",
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"] == []
        assert body["count"] == 0

    @pytest.mark.asyncio
    async def test_get_watchlist_with_data(self, test_client, user_auth_headers):
        """有关注星系时返回系数+星系信息"""
        async def _mock_coeff(sid):
            data = {
                30000142: {"manufacturing": 0.023, "reaction": 0.05},
                30000144: {"manufacturing": None, "reaction": None},
            }
            return data.get(sid, {"manufacturing": None, "reaction": None})

        async def _mock_info(ids):
            return [
                {"system_id": sid, "system_name": f"System_{sid}", "region_name": "TestRegion"}
                for sid in ids
            ]

        with (
            self._patch_watchlist_db(system_ids=[30000142, 30000144]),
            patch(
                "src_v2.backend.api.EVE.api_home.get_system_coefficient",
                side_effect=_mock_coeff,
            ),
            patch(
                "src_v2.backend.api.EVE.api_home.get_system_info_batch",
                side_effect=_mock_info,
            ),
        ):
            resp = await test_client.get(
                "/api/EVE/home/coefficient/watchlist",
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["count"] == 2
        assert len(body["data"]) == 2

        jita = body["data"][0]
        assert jita["system_id"] == 30000142
        assert jita["system_name"] == "System_30000142"
        assert jita["region_name"] == "TestRegion"
        assert jita["manufacturing"] == 0.023
        assert jita["reaction"] == 0.05

    @pytest.mark.asyncio
    async def test_add_system(self, test_client, user_auth_headers):
        """添加星系 → 返回成功"""
        with self._patch_watchlist_db():
            resp = await test_client.post(
                "/api/EVE/home/coefficient/add",
                json={"system_id": 30000142},
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert "已添加" in body["message"] or "成功" in body["message"]

    @pytest.mark.asyncio
    async def test_add_duplicate(self, test_client, user_auth_headers):
        """重复添加同星系 → 幂等，不报错"""
        with self._patch_watchlist_db():
            # 添加两次
            resp1 = await test_client.post(
                "/api/EVE/home/coefficient/add",
                json={"system_id": 30000142},
                headers=user_auth_headers,
            )
            resp2 = await test_client.post(
                "/api/EVE/home/coefficient/add",
                json={"system_id": 30000142},
                headers=user_auth_headers,
            )

        assert resp1.status_code == 200
        assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_remove_system(self, test_client, user_auth_headers):
        """添加后移除星系 → 成功"""
        with self._patch_watchlist_db():
            resp = await test_client.post(
                "/api/EVE/home/coefficient/remove",
                json={"system_id": 30000142},
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, test_client, user_auth_headers):
        """移除未关注的星系 → 成功（无副作用）"""
        with self._patch_watchlist_db():
            resp = await test_client.post(
                "/api/EVE/home/coefficient/remove",
                json={"system_id": 99999999},
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200


# ============================================================
# 批量添加资产星系
# ============================================================


def _mock_asset_db(asset_system_ids, existing_watchlist_ids, added_count):
    """创建 mock 封装方法（返回已进入 with 的两个 patch 对象）。"""
    return (
        patch(
            "src_v2.backend.api.EVE.api_home.EveAssetViewDBUtils",
            select_distinct_system_ids_by_user_name=AsyncMock(
                return_value=list(asset_system_ids)
            ),
        ),
        patch(
            "src_v2.backend.api.EVE.api_home.UserWatchedSystemDBUtils",
            select_system_ids_by_user_name=AsyncMock(
                return_value=list(existing_watchlist_ids)
            ),
            batch_add_systems_ignore_conflict=AsyncMock(return_value=added_count),
        ),
    )


def _with_asset_db(asset_system_ids, existing_watchlist_ids, added_count, extra_patches=()):
    """组合 with 语句所需的全部 patch 对象（含可选 extra_patches）。"""
    return tuple(_mock_asset_db(asset_system_ids, existing_watchlist_ids, added_count)) + tuple(extra_patches)


@pytest.mark.api
class TestAddAllAssetSystems:
    """POST /api/EVE/home/coefficient/addAllAssetSystems — 批量添加资产星系"""

    @pytest.mark.asyncio
    async def test_add_all_assets_with_data(self, test_client, user_auth_headers):
        """用户有 3 个资产星系，watchlist 为空 → 添加 3 个并返回星系信息"""
        asset_ids = [30000142, 30002659, 30005319]
        existing_ids = []
        added_count = 3

        mock_systems_info = [
            {"system_id": 30000142, "system_name": "Jita", "region_name": "The Forge"},
            {"system_id": 30002659, "system_name": "Dodixie", "region_name": "Sinq Laison"},
            {"system_id": 30005319, "system_name": "Amarr", "region_name": "Domain"},
        ]

        patches = _with_asset_db(
            asset_ids, existing_ids, added_count,
            extra_patches=[
                patch(
                    "src_v2.model.EVE.industry.coefficient_utils.get_system_info_batch",
                    new_callable=AsyncMock,
                    return_value=mock_systems_info,
                ),
            ],
        )
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = await test_client.post(
                "/api/EVE/home/coefficient/addAllAssetSystems",
                json={},
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"]["added_count"] == 3
        assert len(body["data"]["systems"]) == 3
        assert body["data"]["systems"][0]["system_id"] == 30000142
        assert body["data"]["systems"][0]["system_name"] == "Jita"
        assert "已添加" in body["message"]

    @pytest.mark.asyncio
    async def test_add_all_assets_empty(self, test_client, user_auth_headers):
        """用户没有资产 → 返回 added_count=0，空列表"""
        patches = _with_asset_db([], [], 0)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = await test_client.post(
                "/api/EVE/home/coefficient/addAllAssetSystems",
                json={},
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"]["added_count"] == 0
        assert body["data"]["systems"] == []
        assert body["message"] == "未找到资产星系"

    @pytest.mark.asyncio
    async def test_add_all_merge_existing(self, test_client, user_auth_headers):
        """部分星系已在监控列表 → 只添加新的，不覆盖已有"""
        asset_ids = [30000142, 30002659, 30005319]
        existing_ids = [30000142]  # Jita already watched
        added_count = 2  # 只添加 30002659、30005319

        mock_systems_info = [
            {"system_id": 30002659, "system_name": "Dodixie", "region_name": "Sinq Laison"},
            {"system_id": 30005319, "system_name": "Amarr", "region_name": "Domain"},
        ]

        patches = _with_asset_db(
            asset_ids, existing_ids, added_count,
            extra_patches=[
                patch(
                    "src_v2.model.EVE.industry.coefficient_utils.get_system_info_batch",
                    new_callable=AsyncMock,
                    return_value=mock_systems_info,
                ),
            ],
        )
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = await test_client.post(
                "/api/EVE/home/coefficient/addAllAssetSystems",
                json={},
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"]["added_count"] == 2
        added_ids = {s["system_id"] for s in body["data"]["systems"]}
        assert 30000142 not in added_ids  # already watched, not added
        assert 30002659 in added_ids
        assert 30005319 in added_ids

    @pytest.mark.asyncio
    async def test_add_all_consecutive_calls(self, test_client, user_auth_headers):
        """连续调用两次 → 第二次 added_count=0（全部已存在）"""
        asset_ids = [30000142, 30002659]
        existing_ids = [30000142, 30002659]  # all already watched
        added_count = 0

        patches = _with_asset_db(asset_ids, existing_ids, added_count)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = await test_client.post(
                "/api/EVE/home/coefficient/addAllAssetSystems",
                json={},
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"]["added_count"] == 0
        assert body["data"]["systems"] == []
        assert "已添加" in body["message"] or "0" in body["message"]

    @pytest.mark.asyncio
    async def test_add_all_unauthorized(self, test_client):
        """无认证 → 401"""
        resp = await test_client.post(
            "/api/EVE/home/coefficient/addAllAssetSystems",
            json={},
        )
        assert resp.status_code == 401
