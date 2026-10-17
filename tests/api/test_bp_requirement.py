# -*- coding: utf-8 -*-
"""
蓝图需求视图 API 测试

覆盖 POST /api/EVE/industry/getBpRequirementViewData 端点与
analyze_blueprint_requirements 函数逻辑。

API 测试要点：
- Redis 缓存命中/未命中
- 认证/参数验证
- 响应结构正确性
- 身份只取自 JWT（g.current_user["user_id"]），请求体 user_name 仅管理员可代查

分析器测试要点：
- fake 条目筛选
- T2 发明源查询
- BPC runs 聚合
"""
import datetime
import json

import jwt
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import src_v2.backend.app as _backend_app

# 确保 app.secret_key 与下方 JWT 签名使用的密钥一致
TEST_SECRET = "test-secret-key-for-jwt"
_backend_app.app.secret_key = TEST_SECRET


# ============================================================
# 辅助函数：构造带 user_id 的 JWT 认证头
# ============================================================
# 注：端点身份取 g.current_user["user_id"]，而 tests/conftest.py 的
# auth_headers fixture 的 payload 只有 user_name，不适用于本端点，
# 因此这里自建 payload（与 test_auth_routes.py 的构造方式一致）。


def _auth_headers(user_id: str = "test_user") -> dict:
    """构造带 user_id 的有效 JWT 认证头（仅 Bearer，不触发 CSRF）"""
    _backend_app.app.secret_key = TEST_SECRET
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24),
    }
    token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# API 路由测试
# ============================================================


class TestBlueprintRequirementAPI:
    """测试 POST /api/EVE/industry/getBpRequirementViewData"""

    URL = "/api/EVE/industry/getBpRequirementViewData"

    MOCK_ANALYZE_RESULT = [
        {
            "type_id": 12345,
            "type_name": "TestItem",
            "type_name_zh": "测试物品",
            "missing_blueprint_type": "其他",
            "bpc_count": 1,
            "bpc_details": [{"runs": 5}],
            "runs_total": 5,
            "tech2_invention_source_bp_type_id": None,
            "tech2_invention_source_bp_type_name": None,
        }
    ]

    def _get_mock_analyze_patch(self):
        """返回 mock analyze_blueprint_requirements 的 patch 上下文管理器"""
        return patch(
            "src_v2.backend.api.EVE.api_industry.analyze_blueprint_requirements",
            AsyncMock(return_value=self.MOCK_ANALYZE_RESULT),
        )

    @staticmethod
    def _completed_cache_rdm(calls=None):
        """构造返回「计算已完成」缓存的 rdm mock

        Args:
            calls: 传入 list 时记录被读取的 Redis key，便于断言 key 前缀。
        """
        mock_rdm = MagicMock()
        mock_rdm.r.get = AsyncMock()

        async def redis_get(key):
            key_str = (
                key if isinstance(key, str) else key.decode("utf-8", errors="ignore")
            )
            if calls is not None:
                calls.append(key_str)
            if "status" in key_str:
                return b"completed"
            if "result" in key_str:
                # 返回 str 使端点中的 json.loads 可解析
                return json.dumps(
                    {
                        "work_flow": [
                            {
                                "type_id": 12345,
                                "type_name": "TestItem",
                                "type_name_zh": "测试物品",
                                "runs": 5,
                                "active_id": 1,
                                "bp_object": {"fake": True},
                            }
                        ]
                    }
                )
            return None

        mock_rdm.r.get.side_effect = redis_get
        return mock_rdm

    # ----------------------------------------------------------
    # 正向场景
    # ----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_bp_requirement_success(self, test_client):
        """Mock Redis 有完整数据 → 验证返回结构，身份取自 token 的 user_id

        注意：rdm（get_redis_manager）在 api_industry 导入时已绑定，
        不能依赖 conftest 的 connect_manager patch，需直接 patch
        api_industry.rdm。
        """
        calls = []
        mock_rdm = self._completed_cache_rdm(calls)

        with (
            patch(
                "src_v2.backend.api.EVE.api_industry.rdm",
                return_value=mock_rdm,
            ),
            self._get_mock_analyze_patch(),
        ):
            resp = await test_client.post(
                self.URL,
                json={"plan_name": "test_plan"},
                headers=_auth_headers("test_user"),
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200

        data = body["data"]
        assert data["cache_hit"] is True
        assert data["user_name"] == "test_user"
        assert data["plan_name"] == "test_plan"
        assert data["missing_blueprint_sheet_count"] == 1
        assert data["missing_workflow_runs_count"] == 5
        assert len(data["missing_blueprint_workflow"]) == 1

        item = data["missing_blueprint_workflow"][0]
        assert item["type_id"] == 12345
        assert item["type_name"] == "TestItem"
        assert item["type_name_zh"] == "测试物品"
        assert item["missing_blueprint_type"] == "其他"
        assert item["bpc_count"] == 1
        assert item["runs_total"] == 5
        assert item["bpc_details"][0]["runs"] == 5

        # 未带 user_name → Redis key 用当前用户身份
        assert calls
        assert calls[0] == "plan_calculate_status:test_user:test_plan"
        assert "plan_calculate_result:test_user:test_plan" in calls

    @pytest.mark.asyncio
    async def test_get_bp_requirement_empty_cache(self, test_client):
        """Mock Redis 无缓存 → 验证返回空 data（data 为 []，非 dict）"""
        mock_rdm = MagicMock()
        mock_rdm.r.get = AsyncMock(return_value=None)

        with patch("src_v2.backend.api.EVE.api_industry.rdm", return_value=mock_rdm):
            resp = await test_client.post(
                self.URL,
                json={"plan_name": "test_plan"},
                headers=_auth_headers("test_user"),
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"] == []  # 缓存未命中时 data 是空列表
        assert body["cache_hit"] is False

    # ----------------------------------------------------------
    # 身份与越权场景（安全审计 #18）
    # ----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_other_user_by_user_name_returns_403(self, test_client):
        """普通用户请求体带他人 user_name → 403，且不读 Redis"""
        mock_rdm = MagicMock()
        mock_rdm.r.get = AsyncMock(return_value=None)

        with (
            patch(
                "src_v2.backend.api.EVE.api_industry.is_admin_user",
                AsyncMock(return_value=False),
            ),
            patch("src_v2.backend.api.EVE.api_industry.rdm", return_value=mock_rdm),
        ):
            resp = await test_client.post(
                self.URL,
                json={"plan_name": "victim_plan", "user_name": "other_user"},
                headers=_auth_headers("attacker"),
            )

        assert resp.status_code == 403
        body = await resp.get_json()
        assert body["status"] == 403
        assert body["message"] == "无权查看他人的工业计划"
        mock_rdm.r.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_can_query_other_user(self, test_client):
        """管理员代查能力保留 → 200，且 Redis key 使用目标用户前缀"""
        calls = []
        mock_rdm = self._completed_cache_rdm(calls)

        with (
            patch(
                "src_v2.backend.api.EVE.api_industry.is_admin_user",
                AsyncMock(return_value=True),
            ),
            patch("src_v2.backend.api.EVE.api_industry.rdm", return_value=mock_rdm),
            self._get_mock_analyze_patch(),
        ):
            resp = await test_client.post(
                self.URL,
                json={"plan_name": "other_plan", "user_name": "other_user"},
                headers=_auth_headers("admin_user"),
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"]["user_name"] == "other_user"
        assert body["data"]["cache_hit"] is True

        # 断言代查确实落在目标用户的缓存 key 上
        assert calls
        assert calls[0] == "plan_calculate_status:other_user:other_plan"
        assert "plan_calculate_result:other_user:other_plan" in calls

    @pytest.mark.asyncio
    async def test_no_user_name_uses_token_identity(self, test_client):
        """不带 user_name 的普通用户 → 200，data.user_name 等于 token 里的 user_id

        回归 #18：修复前读 request.user_name 抛 AttributeError 被兜底吞掉，恒 500。
        """
        calls = []
        mock_rdm = self._completed_cache_rdm(calls)

        with (
            patch(
                "src_v2.backend.api.EVE.api_industry.is_admin_user",
                AsyncMock(return_value=False),
            ),
            patch("src_v2.backend.api.EVE.api_industry.rdm", return_value=mock_rdm),
            self._get_mock_analyze_patch(),
        ):
            resp = await test_client.post(
                self.URL,
                json={"plan_name": "my_plan"},
                headers=_auth_headers("attacker"),
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"]["user_name"] == "attacker"
        assert calls[0] == "plan_calculate_status:attacker:my_plan"

    # ----------------------------------------------------------
    # 异常场景
    # ----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_bp_requirement_unauthorized(self, test_client):
        """无 token → 验证 401"""
        resp = await test_client.post(
            self.URL,
            json={"plan_name": "test_plan"},
        )
        assert resp.status_code == 401
        body = await resp.get_json()
        assert "error" in body

    @pytest.mark.asyncio
    async def test_get_bp_requirement_no_plan_name(self, test_client):
        """缺少 plan_name → 验证 400

        注意：plan_name 为空时端点在读取身份之前就返回 400。
        """
        resp = await test_client.post(
            self.URL,
            json={},
            headers=_auth_headers("test_user"),
        )
        assert resp.status_code == 400
        body = await resp.get_json()
        assert "plan_name" in body.get("message", "")


# ============================================================
# 分析器单元测试
# ============================================================


class TestAnalyzeBlueprintRequirements:
    """测试 analyze_blueprint_requirements 函数

    直接导入并调用，Mock 其内部依赖的 SdeUtils / BPManager。
    """

    @pytest.mark.asyncio
    async def test_analyze_grouping(self):
        """输入含 fake 和非 fake 的 work_flow → 只返回 fake 条目"""
        from src_v2.model.EVE.industry.industry_utils.bp_requirement_analyzer import (
            analyze_blueprint_requirements,
        )

        work_flow = [
            # fake 条目 - type_id=100 两条，应聚合成一条
            {
                "type_id": 100,
                "type_name": "FakeItem",
                "type_name_zh": "假物品",
                "runs": 5,
                "active_id": 1,
                "bp_object": {"fake": True},
            },
            {
                "type_id": 100,
                "type_name": "FakeItem",
                "type_name_zh": "假物品",
                "runs": 10,
                "active_id": 1,
                "bp_object": {"fake": True},
            },
            # 非 fake → 应被过滤
            {
                "type_id": 200,
                "type_name": "RealItem",
                "type_name_zh": "真物品",
                "runs": 3,
                "active_id": 1,
                "bp_object": {"fake": False},
            },
            # 无 bp_object → 应被过滤
            {
                "type_id": 300,
                "type_name": "NoBpItem",
                "type_name_zh": "无bp物品",
                "runs": 7,
                "active_id": 1,
            },
            # 非 dict → 应被跳过
            "not_a_dict",
        ]

        with patch.multiple(
            "src_v2.model.EVE.sde.utils.SdeUtils",
            get_category_by_id=AsyncMock(return_value="其他"),
            get_market_group_list=AsyncMock(return_value=[]),
            get_metaname_by_typeid=AsyncMock(return_value="Tech I"),
            get_name_by_id=AsyncMock(return_value=""),
        ):
            result = await analyze_blueprint_requirements(work_flow)

        assert len(result) == 1, "只有 type_id=100 的 fake 条目应被返回"
        node = result[0]
        assert node["type_id"] == 100
        assert node["type_name"] == "FakeItem"
        assert node["type_name_zh"] == "假物品"
        assert node["runs_total"] == 15, "两条 runs (5+10) 应累加"
        assert node["bpc_count"] == 2, "两条条目应计数为 2"

    @pytest.mark.asyncio
    async def test_t2_invention_source(self):
        """输入 T2 物品 fake 条目 → tech2_invention_source 非空"""
        from src_v2.model.EVE.industry.industry_utils.bp_requirement_analyzer import (
            analyze_blueprint_requirements,
        )

        work_flow = [
            {
                "type_id": 44992,
                "type_name": "PLEX",
                "type_name_zh": "伊甸币",
                "runs": 3,
                "active_id": 8,
                "bp_object": {"fake": True},
            }
        ]

        with patch.multiple(
            "src_v2.model.EVE.sde.utils.SdeUtils",
            get_category_by_id=AsyncMock(return_value="其他"),
            get_market_group_list=AsyncMock(return_value=[]),
            get_metaname_by_typeid=AsyncMock(return_value="Tech II"),
            get_name_by_id=AsyncMock(return_value="Origin Blueprint"),
        ), patch.multiple(
            "src_v2.model.EVE.industry.blueprint.BPManager",
            get_bp_id_by_prod_typeid=AsyncMock(return_value=999),
            get_invention_source_bp_typeid_by_target_bp_typeid=AsyncMock(
                return_value=888
            ),
        ):
            result = await analyze_blueprint_requirements(work_flow)

        assert len(result) == 1
        node = result[0]
        assert node["tech2_invention_source_bp_type_id"] == 888
        assert node["tech2_invention_source_bp_type_name"] == "Origin Blueprint"

    @pytest.mark.asyncio
    async def test_bpc_details_grouping(self):
        """输入多个不同 runs 的 fake 条目 → bpc_details 正确"""
        from src_v2.model.EVE.industry.industry_utils.bp_requirement_analyzer import (
            analyze_blueprint_requirements,
        )

        runs_list = [3, 7, 0, 15]
        work_flow = [
            {
                "type_id": 500,
                "type_name": "RunsTestItem",
                "type_name_zh": "Runs测试物品",
                "runs": runs,
                "active_id": 1,
                "bp_object": {"fake": True},
            }
            for runs in runs_list
        ]

        with patch.multiple(
            "src_v2.model.EVE.sde.utils.SdeUtils",
            get_category_by_id=AsyncMock(return_value="其他"),
            get_market_group_list=AsyncMock(return_value=[]),
            get_metaname_by_typeid=AsyncMock(return_value="Tech I"),
            get_name_by_id=AsyncMock(return_value=""),
        ):
            result = await analyze_blueprint_requirements(work_flow)

        assert len(result) == 1
        node = result[0]
        assert node["runs_total"] == sum(runs_list), "所有 runs 应累加"
        assert node["bpc_count"] == len(runs_list), "条目数应等于 bpc_count"
        assert len(node["bpc_details"]) == len(runs_list)
        assert node["bpc_details"] == [{"runs": r} for r in runs_list]
