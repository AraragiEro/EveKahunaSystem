# -*- coding: utf-8 -*-
"""
内部 MCP 代理路由测试

测试 /api/internal/mcp/* 路由：
- QQ 相关 (vip, running-jobs, market-tags)
- 市场相关 (price, cost, fuzz, metrics)
- 工业相关 (missing-blueprints)
- 公司相关 (medica-vouchers)

所有 MCP 路由均要求服务间认证（请求头 X-Internal-API-Key，见 backend/auth.py 的
register_service_auth）；本文件通过 _mcp_service_auth fixture 统一为请求注入测试密钥。
需 mock enterprise astrbot service 模块提供模拟响应。
"""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

TEST_SERVICE_KEY = "test-service-key"


@pytest_asyncio.fixture(autouse=True)
async def _mcp_service_auth(mcp_test_client):
    """统一为 MCP 路由请求注入服务密钥（避免逐处修改既有请求调用）"""
    orig_get, orig_post = mcp_test_client.get, mcp_test_client.post

    def _inject(kwargs):
        headers = dict(kwargs.get("headers") or {})
        headers.setdefault("X-Internal-API-Key", TEST_SERVICE_KEY)
        kwargs["headers"] = headers
        return kwargs

    mcp_test_client.get = lambda *a, **kw: orig_get(*a, **_inject(kw))
    mcp_test_client.post = lambda *a, **kw: orig_post(*a, **_inject(kw))

    with patch("src_v2.backend.auth.get_service_api_key", return_value=TEST_SERVICE_KEY):
        yield


# ============================================================
# Mock Enterprise Service 工厂
# ============================================================

def create_mock_astrbot_service():
    """创建 mock enterprise astrbot service 模块"""

    mock = MagicMock()

    # QQ VIP
    mock._astrbot_qq_vip_state = AsyncMock(
        return_value=(
            {
                "status": 200,
                "is_bind": True,
                "data": {
                    "userName": "test_user",
                    "vipLevel": "Alpha",
                    "vipLevelCode": "vip_alpha",
                    "vipEndDate": "2025-12-31T23:59:59",
                },
            },
            200,
        )
    )

    # QQ Running Jobs
    mock._astrbot_running_jobs_overview = AsyncMock(
        return_value=(
            {
                "status": 200,
                "data": {
                    "userName": "test_user",
                    "runningValueOverview": {
                        "runningTotalValue": 5000000.0,
                        "runningManufacturingValue": 3000000.0,
                        "runningReactionValue": 2000000.0,
                    },
                    "jobsFinishOverview": {
                        "completedCount": 5,
                        "finishTodayCount": 2,
                        "finishTomorrowCount": 1,
                        "finishLaterCount": 2,
                    },
                    "roleLinesOverview": {
                        "participatingRoleCount": 3,
                        "rolesWithFreeLines": [],
                    },
                },
            },
            200,
        )
    )

    # QQ Market Tags
    mock._astrbot_market_tag_list = AsyncMock(
        return_value=(
            {
                "status": 200,
                "data": [
                    {"id": 1, "tag": "常用市场"},
                    {"id": 2, "tag": "弹药市场"},
                ],
            },
            200,
        )
    )

    # Market Price Detail
    mock._astrbot_market_price_detail = AsyncMock(
        return_value=(
            {
                "status": 200,
                "is_price": True,
                "data": {
                    "type_id": 44992,
                    "name": "PLEX",
                    "name_zh": "伊甸币",
                    "buy": 4500000.0,
                    "sell": 4600000.0,
                    "mid": 4550000.0,
                    "history_data": [],
                },
            },
            200,
        )
    )

    # Market Type Cost
    mock._astrbot_market_type_cost = AsyncMock(
        return_value=(
            {
                "status": 200,
                "is_cost": True,
                "data": {
                    "type_id": 23917,
                    "item_name": "Wyvern",
                    "item_name_cn": "飞龙级",
                    "total_cost": 1000000000.0,
                },
            },
            200,
        )
    )

    # Market Fuzz Type Name
    mock._astrbot_fuzz_type_name = AsyncMock(
        return_value=(
            {
                "status": 200,
                "data": [
                    {"name": "冥王级", "score": 95.0},
                    {"name": "冥府级", "score": 85.0},
                ],
            },
            200,
        )
    )

    # Market Type Metrics
    mock._astrbot_market_type_metrics = AsyncMock(
        return_value=(
            {
                "status": 200,
                "data": {
                    "market_id": 1,
                    "market_zone": "jita",
                    "rows": [
                        {
                            "type_id": 44992,
                            "name": "PLEX",
                            "sell_profit": 100000.0,
                            "asset_quantity": 50,
                            "plan_quantity": 10,
                            "sell_monthly_profit_space": 5000000.0,
                        }
                    ],
                },
            },
            200,
        )
    )

    # Missing Blueprints
    mock._astrbot_plan_missing_blueprint_workflow_summary = AsyncMock(
        return_value=(
            {
                "status": 200,
                "data": {
                    "user_name": "test_user",
                    "plan_name": "default",
                    "cache_hit": True,
                    "missing_blueprint_sheet_count": 2,
                    "missing_workflow_runs_count": 5,
                    "missing_blueprint_workflow": [
                        {
                            "type_id": 12345,
                            "type_name": "Test BP",
                            "workflow_count": 2,
                            "runs_total": 5,
                            "missing_blueprint_type": "舰船",
                        }
                    ],
                },
            },
            200,
        )
    )

    # Company Medica Vouchers
    mock._astrbot_get_company_medica_vouchers = AsyncMock(
        return_value=(
            {
                "status": 200,
                "data": [
                    ["CrazySheep7", "1,500,000,000", "123456789"],
                    ["Wynn Tim", "1,000,000,000", "987654321"],
                ],
                "count": 2,
            },
            200,
        )
    )

    return mock


# ============================================================
# Fixture：注入 mock enterprise 模块
# ============================================================


@pytest_asyncio.fixture
async def mcp_test_client(test_app, mock_config):
    """
    注入 mock enterprise astrbot service 到 sys.modules，
    让 internal_mcp 路由的懒加载导入获取到 mock 函数。
    """
    mock_service = create_mock_astrbot_service()

    # 确保父包存在（MagicMock 模块）
    enterprise_mods = {
        "src_v2.enterprise": MagicMock(),
        "src_v2.enterprise.api": MagicMock(),
        "src_v2.enterprise.api.api_astrbot_service": mock_service,
    }

    with patch.dict("sys.modules", enterprise_mods):
        from src_v2.backend.app import app

        app.secret_key = "test-secret-key-for-jwt"
        yield test_app.test_client()


# ============================================================
# QQ 相关路由
# ============================================================


@pytest.mark.api
class TestMcpQQVip:
    """GET /api/internal/mcp/qq/vip"""

    @pytest.mark.asyncio
    async def test_success_returns_200(self, mcp_test_client):
        resp = await mcp_test_client.get("/api/internal/mcp/qq/vip?qq=123456")
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["is_bind"] is True
        assert body["data"]["userName"] == "test_user"

    @pytest.mark.asyncio
    async def test_missing_qq_returns_400(self, mcp_test_client):
        resp = await mcp_test_client.get("/api/internal/mcp/qq/vip")
        assert resp.status_code == 400


@pytest.mark.api
class TestMcpQQRunningJobs:
    """GET /api/internal/mcp/qq/running-jobs"""

    @pytest.mark.asyncio
    async def test_success_returns_200(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/qq/running-jobs?qq=123456"
        )
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"]["userName"] == "test_user"

    @pytest.mark.asyncio
    async def test_missing_qq_returns_400(self, mcp_test_client):
        resp = await mcp_test_client.get("/api/internal/mcp/qq/running-jobs")
        assert resp.status_code == 400


@pytest.mark.api
class TestMcpQQMarketTags:
    """GET /api/internal/mcp/qq/market-tags"""

    @pytest.mark.asyncio
    async def test_success_returns_200(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/qq/market-tags?qq=123456"
        )
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert len(body["data"]) == 2

    @pytest.mark.asyncio
    async def test_missing_qq_returns_400(self, mcp_test_client):
        resp = await mcp_test_client.get("/api/internal/mcp/qq/market-tags")
        assert resp.status_code == 400


# ============================================================
# 市场相关路由
# ============================================================


@pytest.mark.api
class TestMcpMarketPrice:
    """GET /api/internal/mcp/market/price"""

    @pytest.mark.asyncio
    async def test_success_returns_200(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/market/price?type_name=PLEX"
        )
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["is_price"] is True
        assert body["data"]["name"] == "PLEX"

    @pytest.mark.asyncio
    async def test_missing_type_name_returns_400(self, mcp_test_client):
        resp = await mcp_test_client.get("/api/internal/mcp/market/price")
        assert resp.status_code == 400


@pytest.mark.api
class TestMcpMarketCost:
    """GET /api/internal/mcp/market/cost"""

    @pytest.mark.asyncio
    async def test_success_returns_200(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/market/cost?type_name=Wyvern"
        )
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["is_cost"] is True
        assert body["data"]["item_name"] == "Wyvern"

    @pytest.mark.asyncio
    async def test_missing_type_name_returns_400(self, mcp_test_client):
        resp = await mcp_test_client.get("/api/internal/mcp/market/cost")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_with_optional_params_returns_200(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/market/cost?type_name=Wyvern"
            "&user_name=test_user&plan_name=my_plan"
        )
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200


@pytest.mark.api
class TestMcpMarketFuzz:
    """GET /api/internal/mcp/market/fuzz"""

    @pytest.mark.asyncio
    async def test_success_returns_200(self, mcp_test_client):
        from urllib.parse import quote

        resp = await mcp_test_client.get(
            f"/api/internal/mcp/market/fuzz?type_name={quote('冥王')}"
        )
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert len(body["data"]) == 2

    @pytest.mark.asyncio
    async def test_missing_type_name_returns_400(self, mcp_test_client):
        resp = await mcp_test_client.get("/api/internal/mcp/market/fuzz")
        assert resp.status_code == 400


@pytest.mark.api
class TestMcpMarketMetrics:
    """GET /api/internal/mcp/market/metrics"""

    @pytest.mark.asyncio
    async def test_success_returns_200(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/market/metrics?qq=123456&market_id=1"
        )
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"]["market_id"] == 1

    @pytest.mark.asyncio
    async def test_missing_qq_returns_400(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/market/metrics?market_id=1"
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_market_id_returns_400(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/market/metrics?qq=123456"
        )
        assert resp.status_code == 400


# ============================================================
# 工业相关路由
# ============================================================


@pytest.mark.api
class TestMcpIndustryMissingBlueprints:
    """GET /api/internal/mcp/industry/missing-blueprints"""

    @pytest.mark.asyncio
    async def test_success_returns_200(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/industry/missing-blueprints"
            "?qq=123456&planname=default"
        )
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"]["cache_hit"] is True
        assert body["data"]["missing_blueprint_sheet_count"] == 2

    @pytest.mark.asyncio
    async def test_missing_qq_returns_400(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/industry/missing-blueprints?planname=default"
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_planname_returns_400(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/industry/missing-blueprints?qq=123456"
        )
        assert resp.status_code == 400


# ============================================================
# 公司相关路由
# ============================================================


@pytest.mark.api
class TestMcpCompanyMedicaVouchers:
    """GET /api/internal/mcp/company/medica-vouchers"""

    @pytest.mark.asyncio
    async def test_success_returns_200(self, mcp_test_client):
        resp = await mcp_test_client.get(
            "/api/internal/mcp/company/medica-vouchers?qq=123456789"
        )
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["count"] == 2
        assert len(body["data"]) == 2
        assert body["data"][0][0] == "CrazySheep7"
        assert body["data"][0][2] == "123456789"

        # qq 必须透传给后端 entry（同时带 qq 与 QQ，兼容既有参数约定）
        entry = sys.modules[
            "src_v2.enterprise.api.api_astrbot_service"
        ]._astrbot_get_company_medica_vouchers
        entry.assert_awaited_with({"qq": 123456789, "QQ": 123456789})

    @pytest.mark.asyncio
    async def test_missing_qq_returns_400(self, mcp_test_client):
        resp = await mcp_test_client.get("/api/internal/mcp/company/medica-vouchers")
        assert resp.status_code == 400
