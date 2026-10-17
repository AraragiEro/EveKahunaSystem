# -*- coding: utf-8 -*-
"""
API 公开路由测试

测试 /api/public/* 路由：
- 公开资产视图 (storage)
- 工作流分享/接取 (workflow)
"""
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
import pytest_asyncio


# ============================================================
# 本地 Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def _setup_app_secret(mock_config):
    """确保 Quart app 使用测试 secret key"""
    from src_v2.backend.app import app

    app.secret_key = "test-secret-key-for-jwt"


@pytest.fixture
def user_auth_headers():
    """JWT 认证头部 (含 user_id 字段，匹配路由中 g.current_user["user_id"])"""
    payload = {
        "user_name": "test_user",
        "user_id": "test_user",
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=24),
    }
    token = jwt.encode(payload, "test-secret-key-for-jwt", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth_headers():
    """管理员 JWT 认证头部"""
    payload = {
        "user_name": "admin",
        "user_id": "admin",
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=24),
    }
    token = jwt.encode(payload, "test-secret-key-for-jwt", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# Mock 工厂函数
# ============================================================

def mock_asset_view(sid="abc123", public=True, view_type="storage", config=None):
    """创建 mock 资产视图对象"""
    view = MagicMock()
    view.sid = sid
    view.public = public
    view.view_type = view_type
    view.config = config or {}
    view.tag = "测试标签"
    return view


def mock_industry_plan(
    user_name="test_user",
    plan_name="test_plan",
    public=True,
    share_token: str | None = "wf_testtoken123",
    filter_snapshot=None,
):
    """创建 mock 工业计划对象"""
    plan = MagicMock()
    plan.user_name = user_name
    plan.plan_name = plan_name
    plan.public = public
    plan.share_token = share_token
    plan.filter_snapshot = filter_snapshot or {}
    return plan


# ============================================================
# 公开资产视图路由
# ============================================================


@pytest.mark.api
class TestPublicStorage:
    """GET /api/public/storage/<sid> - 公开资产视图"""

    @pytest.mark.asyncio
    async def test_valid_public_storage_view_returns_200(self, test_client):
        """有效公开 sid → 200 + 正确结构"""
        view = mock_asset_view(sid="abc123", public=True, view_type="storage")
        view_data = {"items": [{"type_id": 123, "quantity": 100}]}

        with patch(
            "src_v2.backend.api.api_public.AssetManager"
        ) as mock_am_cls:
            mock_am = mock_am_cls.return_value
            mock_am.get_asset_view_by_sid = AsyncMock(return_value=view)
            mock_am.get_asset_view_data = AsyncMock(return_value=view_data)

            resp = await test_client.get("/api/public/storage/abc123")

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"] == view_data
        assert body["tag"] == "测试标签"
        assert body["view_type"] == "storage"

    @pytest.mark.asyncio
    async def test_not_public_storage_view_returns_403(self, test_client):
        """未公开资产视图 → 403"""
        view = mock_asset_view(sid="abc123", public=False)

        with patch("src_v2.backend.api.api_public.AssetManager") as mock_am_cls:
            mock_am = mock_am_cls.return_value
            mock_am.get_asset_view_by_sid = AsyncMock(return_value=view)

            resp = await test_client.get("/api/public/storage/abc123")

        assert resp.status_code == 403
        body = await resp.get_json()
        assert body["status"] == 403

    @pytest.mark.asyncio
    async def test_nonexistent_storage_view_returns_404(self, test_client):
        """不存在的 sid → 404"""
        with patch("src_v2.backend.api.api_public.AssetManager") as mock_am_cls:
            mock_am = mock_am_cls.return_value
            mock_am.get_asset_view_by_sid = AsyncMock(return_value=None)

            resp = await test_client.get("/api/public/storage/nonexistent")

        assert resp.status_code == 404
        body = await resp.get_json()
        assert body["status"] == 404

    @pytest.mark.asyncio
    async def test_sell_view_fills_price_data(self, test_client):
        """sell 类型视图 → 自动填充价格数据"""
        view = mock_asset_view(sid="sell123", public=True, view_type="sell", config={"region": "jita"})
        view_data = {"items": [{"type_id": 44992}]}
        enriched_data = {"items": [{"type_id": 44992, "price": 4500000}]}

        with (
            patch("src_v2.backend.api.api_public.AssetManager") as mock_am_cls,
            patch("src_v2.backend.api.api_public.MarketManager") as mock_mm_cls,
        ):
            mock_am = mock_am_cls.return_value
            mock_am.get_asset_view_by_sid = AsyncMock(return_value=view)
            mock_am.get_asset_view_data = AsyncMock(return_value=view_data)
            mock_am.fill_sell_price_data = AsyncMock(return_value=enriched_data)

            mock_mm = mock_mm_cls.return_value
            mock_mm.update_jita_price = AsyncMock()

            resp = await test_client.get("/api/public/storage/sell123")

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["data"] == enriched_data


# ============================================================
# 工作流分享路由
# ============================================================


@pytest.mark.api
class TestWorkflowShare:
    """POST /api/public/workflow/share - 创建工作流分享"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, test_client):
        """无认证 → 401"""
        resp = await test_client.post(
            "/api/public/workflow/share",
            json={"plan_name": "test_plan"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_with_auth_returns_200(self, test_client, user_auth_headers):
        """认证用户 → 200"""
        plan = mock_industry_plan(share_token=None)

        with patch(
            "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
        ) as mock_db:
            mock_db.select_by_user_name_and_plan_name = AsyncMock(
                return_value=plan
            )
            mock_db.update_share_info = AsyncMock(return_value=plan)

            resp = await test_client.post(
                "/api/public/workflow/share",
                    json={"plan_name": "test_plan", "filter_snapshot": {"showFake": "no_blueprint"}},
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["share_token"].startswith("wf_")
        assert "share_url" in body

    @pytest.mark.asyncio
    async def test_missing_plan_name_returns_400(self, test_client, user_auth_headers):
        """缺少 plan_name → 400"""
        resp = await test_client.post(
            "/api/public/workflow/share",
            json={"filter_snapshot": {}},
            headers=user_auth_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_plan_not_found_returns_404(self, test_client, user_auth_headers):
        """计划不存在 → 404"""
        with patch(
            "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
        ) as mock_db:
            mock_db.select_by_user_name_and_plan_name = AsyncMock(return_value=None)

            resp = await test_client.post(
                "/api/public/workflow/share",
                json={"plan_name": "nonexistent_plan"},
                headers=user_auth_headers,
            )

        assert resp.status_code == 404


@pytest.mark.api
class TestWorkflowShareToggle:
    """POST /api/public/workflow/share/toggle - 切换分享状态"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, test_client):
        """无认证 → 401"""
        resp = await test_client.post(
            "/api/public/workflow/share/toggle",
            json={"plan_name": "test_plan"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_with_auth_toggles_to_false(self, test_client, user_auth_headers):
        """认证用户切换 → 200"""
        plan = mock_industry_plan(public=True, share_token="wf_abc")

        with patch(
            "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
        ) as mock_db:
            mock_db.select_by_user_name_and_plan_name = AsyncMock(
                return_value=plan
            )
            mock_db.update_share_info = AsyncMock()

            resp = await test_client.post(
                "/api/public/workflow/share/toggle",
                json={"plan_name": "test_plan"},
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["public"] is False

    @pytest.mark.asyncio
    async def test_missing_plan_name_returns_400(self, test_client, user_auth_headers):
        """缺少 plan_name → 400"""
        resp = await test_client.post(
            "/api/public/workflow/share/toggle",
            json={},
            headers=user_auth_headers,
        )
        assert resp.status_code == 400


# ============================================================
# 公开工作流查看路由
# ============================================================


@pytest.mark.api
class TestPublicWorkflow:
    """GET /api/public/workflow/<token> - 获取公开工作流"""

    @pytest.mark.asyncio
    async def test_valid_token_returns_200(self, test_client):
        """有效 token → 200"""
        plan = mock_industry_plan(
            user_name="owner", plan_name="my_plan",
            public=True, share_token="wf_valtok",
            filter_snapshot={"showFake": "all"},
        )
        calc_result = {"work_flow": [
            {"type_id": 123, "type_name": "item", "runs": 5,
             "active_id": 1, "bp_object": {"fake": False},
             "avaliable": True}
        ] * 10}  # 10条线，确保数量校验通过
        
        with (
            patch(
                "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
            ) as mock_db,
            patch(
                "src_v2.model.EVE.industry.industry_manager.IndustryManager"
            ) as mock_im_cls,
        ):
            mock_db.select_by_share_token = AsyncMock(return_value=plan)
            mock_im_cls.get_calculation_result = AsyncMock(return_value=calc_result)

            resp = await test_client.get("/api/public/workflow/wf_valtok")

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"]["plan_name"] == "my_plan"
        assert body["data"]["workflow_data"] == calc_result["work_flow"]

    @pytest.mark.asyncio
    async def test_invalid_token_returns_404(self, test_client):
        """无效 token → 404"""
        with patch(
            "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
        ) as mock_db:
            mock_db.select_by_share_token = AsyncMock(return_value=None)

            resp = await test_client.get("/api/public/workflow/invalid_token")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_closed_share_returns_403(self, test_client):
        """已关闭的分享 → 403"""
        plan = mock_industry_plan(public=False, share_token="wf_closed")

        with patch(
            "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
        ) as mock_db:
            mock_db.select_by_share_token = AsyncMock(return_value=plan)

            resp = await test_client.get("/api/public/workflow/wf_closed")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_filtered_workflow_applies_filters(self, test_client):
        """应用过滤快照 → 只返回匹配项"""
        plan = mock_industry_plan(
            user_name="owner", plan_name="my_plan",
            public=True, share_token="wf_filt",
            filter_snapshot={"showFake": "no_blueprint"},
        )
        calc_result = {"work_flow": [
            {"type_id": 1, "type_name": "real", "runs": 3,
             "active_id": 1, "class_type": None,
             "bp_object": {"fake": False}, "avaliable": True},
            {"type_id": 2, "type_name": "fake_item", "runs": 2,
             "active_id": 1, "class_type": None,
             "bp_object": {"fake": True}, "avaliable": False},
        ]}

        with (
            patch("src_v2.backend.api.api_public.EveIndustryPlanDBUtils") as mock_db,
            patch("src_v2.model.EVE.industry.industry_manager.IndustryManager") as mock_im_cls,
        ):
            mock_db.select_by_share_token = AsyncMock(return_value=plan)
            mock_im_cls.get_calculation_result = AsyncMock(return_value=calc_result)

            resp = await test_client.get("/api/public/workflow/wf_filt")

        assert resp.status_code == 200
        body = await resp.get_json()
        # showFake=no_blueprint → 只返回 bp_object.fake=True 的
        filtered = body["data"]["workflow_data"]
        assert len(filtered) == 1
        assert filtered[0]["type_name"] == "fake_item"

    @pytest.mark.asyncio
    async def test_filtered_workflow_has_blueprint(self, test_client):
        """has_blueprint 筛选 → 只返回有蓝图的项目"""
        plan = mock_industry_plan(
            user_name="owner", plan_name="my_plan",
            public=True, share_token="wf_hasbp",
            filter_snapshot={"showFake": "has_blueprint"},
        )
        calc_result = {"work_flow": [
            {"type_id": 1, "type_name": "real_bp", "runs": 3,
             "active_id": 1, "class_type": None,
             "bp_object": {"fake": False}, "avaliable": True},
            {"type_id": 2, "type_name": "no_bp", "runs": 2,
             "active_id": 1, "class_type": None,
             "bp_object": {"fake": True}, "avaliable": False},
        ]}

        with (
            patch("src_v2.backend.api.api_public.EveIndustryPlanDBUtils") as mock_db,
            patch("src_v2.model.EVE.industry.industry_manager.IndustryManager") as mock_im_cls,
        ):
            mock_db.select_by_share_token = AsyncMock(return_value=plan)
            mock_im_cls.get_calculation_result = AsyncMock(return_value=calc_result)

            resp = await test_client.get("/api/public/workflow/wf_hasbp")

        assert resp.status_code == 200
        body = await resp.get_json()
        # showFake=has_blueprint → 只返回 bp_object.fake=False 的
        filtered = body["data"]["workflow_data"]
        assert len(filtered) == 1
        assert filtered[0]["type_name"] == "real_bp"


# ============================================================
# 任务接取路由
# ============================================================


@pytest.mark.api
class TestWorkflowClaim:
    """POST /api/public/workflow/<token>/claim - 接取任务"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, test_client):
        """无认证 → 401"""
        resp = await test_client.post(
            "/api/public/workflow/wf_tok/claim",
            json={"workflow_item_key": "123_5_false_true"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_with_auth_returns_200(self, test_client, user_auth_headers):
        """认证用户接取 → 200"""
        plan = mock_industry_plan(
            user_name="owner", plan_name="my_plan",
            public=True, share_token="wf_cltok",
        )
        calc_result = {"work_flow": [
            {"type_id": 123, "type_name": "item", "runs": 5,
             "active_id": 1, "bp_object": {"fake": False},
             "avaliable": True}
        ]}

        with (
            patch(
                "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
            ) as mock_plan_db,
            patch(
                "src_v2.backend.api.api_public.EveIndustryPlanTaskClaimDBUtils"
            ) as mock_claim_db,
            patch(
                "src_v2.model.EVE.industry.industry_manager.IndustryManager"
            ) as mock_im_cls,
        ):
            mock_plan_db.select_by_share_token = AsyncMock(return_value=plan)
            mock_im_cls.get_calculation_result = AsyncMock(return_value=calc_result)
            mock_claim_db.get_total_claimed_quantity = AsyncMock(return_value=0)
            # 封装模块内完成单会话接取（无已有记录 → 新建）
            mock_claim_db.claim_or_append = AsyncMock(return_value=("created", 1))

            resp = await test_client.post(
                "/api/public/workflow/wf_cltok/claim",
                json={"workflow_item_key": "123_5_false_true", "quantity": 1},
                headers=user_auth_headers,
            )

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200
        assert body["data"]["claimed_by"] == "test_user"

    @pytest.mark.asyncio
    async def test_missing_item_key_returns_400(self, test_client, user_auth_headers):
        """缺少 workflow_item_key → 400"""
        resp = await test_client.post(
            "/api/public/workflow/wf_tok/claim",
            json={"quantity": 1},
            headers=user_auth_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_multi_user_claim_different_users(
        self, test_client, user_auth_headers
    ):
        """两个不同用户可接取同一工作流项 → 200"""
        plan = mock_industry_plan(
            user_name="owner", plan_name="my_plan",
            public=True, share_token="wf_test",
        )
        calc_result = {"work_flow": [
            {"type_id": 123, "type_name": "item", "runs": 5,
             "active_id": 1, "bp_object": {"fake": False},
             "avaliable": True}
        ] * 10}  # 10 条线，足够两个用户接取

        # 第二个用户的 JWT
        user_b_headers = {
            "Authorization": f"Bearer {jwt.encode(
                {"user_name": "user_b", "user_id": "user_b",
                 "exp": datetime.datetime.now(datetime.timezone.utc)
                 + datetime.timedelta(hours=24)},
                "test-secret-key-for-jwt", algorithm="HS256"
            )}"
        }

        with (
            patch(
                "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
            ) as mock_plan_db,
            patch(
                "src_v2.backend.api.api_public.EveIndustryPlanTaskClaimDBUtils"
            ) as mock_claim_db,
            patch(
                "src_v2.model.EVE.industry.industry_manager.IndustryManager"
            ) as mock_im_cls,
        ):
            mock_plan_db.select_by_share_token = AsyncMock(return_value=plan)
            mock_im_cls.get_calculation_result = AsyncMock(return_value=calc_result)
            # total_claimed: 0 for 1st request (no claims yet), 2 for 2nd (user A claimed 2)
            mock_claim_db.get_total_claimed_quantity = AsyncMock(
                side_effect=[0, 2]
            )
            # 两个用户各自新建接取记录
            mock_claim_db.claim_or_append = AsyncMock(
                side_effect=[("created", 2), ("created", 3)]
            )

            # User A (test_user) 接取 2 线
            resp1 = await test_client.post(
                "/api/public/workflow/wf_test/claim",
                json={"workflow_item_key": "123_5_false_true", "quantity": 2},
                headers=user_auth_headers,
            )

            assert resp1.status_code == 200
            body1 = await resp1.get_json()
            assert body1["data"]["claimed_quantity"] == 2

            # User B (user_b) 接取 3 线
            resp2 = await test_client.post(
                "/api/public/workflow/wf_test/claim",
                json={"workflow_item_key": "123_5_false_true", "quantity": 3},
                headers=user_b_headers,
            )

            assert resp2.status_code == 200
            body2 = await resp2.get_json()
            assert body2["data"]["claimed_quantity"] == 3

    @pytest.mark.asyncio
    async def test_multi_user_claim_exceeds_total(
        self, test_client, user_auth_headers
    ):
        """多用户接取总量超出总线数 → 400"""
        plan = mock_industry_plan(
            user_name="owner", plan_name="my_plan",
            public=True, share_token="wf_test",
        )
        calc_result = {"work_flow": [
            {"type_id": 123, "type_name": "item", "runs": 5,
             "active_id": 1, "bp_object": {"fake": False},
             "avaliable": True}
        ] * 5}  # 5 条线，已接取 4 条，用户尝试再接取 2 条会超出

        user_b_headers = {
            "Authorization": f"Bearer {jwt.encode(
                {"user_name": "user_b", "user_id": "user_b",
                 "exp": datetime.datetime.now(datetime.timezone.utc)
                 + datetime.timedelta(hours=24)},
                "test-secret-key-for-jwt", algorithm="HS256"
            )}"
        }

        with (
            patch(
                "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
            ) as mock_plan_db,
            patch(
                "src_v2.backend.api.api_public.EveIndustryPlanTaskClaimDBUtils"
            ) as mock_claim_db,
            patch(
                "src_v2.model.EVE.industry.industry_manager.IndustryManager"
            ) as mock_im_cls,
        ):
            mock_plan_db.select_by_share_token = AsyncMock(return_value=plan)
            mock_im_cls.get_calculation_result = AsyncMock(return_value=calc_result)
            # 已接取 4 线（总线 5）
            mock_claim_db.get_total_claimed_quantity = AsyncMock(return_value=4)
            # 超额校验在 claim_or_append 之前完成，此 mock 不应被调用
            mock_claim_db.claim_or_append = AsyncMock(return_value=("created", 2))

            # User B 尝试接取 2 线，但只剩 1 线
            resp = await test_client.post(
                "/api/public/workflow/wf_test/claim",
                json={"workflow_item_key": "123_5_false_true", "quantity": 2},
                headers=user_b_headers,
            )

            assert resp.status_code == 400
            body = await resp.get_json()
            assert "超出可接取数量" in body["message"] or "剩余" in body["message"]

    @pytest.mark.asyncio
    async def test_claim_error_not_misleading(
        self, test_client, user_auth_headers
    ):
        """IntegrityError 时不返回误导的"您已接取该任务" → 409"""
        plan = mock_industry_plan(
            user_name="owner", plan_name="my_plan",
            public=True, share_token="wf_test",
        )
        calc_result = {"work_flow": [
            {"type_id": 123, "type_name": "item", "runs": 5,
             "active_id": 1, "bp_object": {"fake": False},
             "avaliable": True}
        ] * 10}  # 10 条线，确保不超过总量

        with (
            patch(
                "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
            ) as mock_plan_db,
            patch(
                "src_v2.backend.api.api_public.EveIndustryPlanTaskClaimDBUtils"
            ) as mock_claim_db,
            patch(
                "src_v2.model.EVE.industry.industry_manager.IndustryManager"
            ) as mock_im_cls,
        ):
            mock_plan_db.select_by_share_token = AsyncMock(return_value=plan)
            mock_im_cls.get_calculation_result = AsyncMock(return_value=calc_result)
            mock_claim_db.get_total_claimed_quantity = AsyncMock(return_value=0)
            # 唯一约束冲突且重试后仍未找到当前用户记录 → 返回 conflict，API 层映射为 409
            mock_claim_db.claim_or_append = AsyncMock(return_value=("conflict", 0))

            resp = await test_client.post(
                "/api/public/workflow/wf_test/claim",
                json={"workflow_item_key": "123_5_false_true", "quantity": 2},
                headers=user_auth_headers,
            )

            assert resp.status_code == 409
            body = await resp.get_json()
            # 当前用户未接取，不应返回"您已接取该任务"
            assert "您已接取该任务" not in body["message"]


# ============================================================
# 接取记录查看路由
# ============================================================


@pytest.mark.api
class TestWorkflowClaims:
    """GET /api/public/workflow/<token>/claims - 查看接取记录"""

    @pytest.mark.asyncio
    async def test_valid_token_returns_200(self, test_client):
        """有效 token → 200"""
        plan = mock_industry_plan(public=True, share_token="wf_cltok")
        calc_result = {"work_flow": [
            {"type_id": 123, "type_name": "item", "runs": 5,
             "active_id": 1, "bp_object": {"fake": False},
             "avaliable": True}
        ]}

        with (
            patch(
                "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
            ) as mock_plan_db,
            patch(
                "src_v2.backend.api.api_public.EveIndustryPlanTaskClaimDBUtils"
            ) as mock_claim_db,
            patch(
                "src_v2.model.EVE.industry.industry_manager.IndustryManager"
            ) as mock_im_cls,
        ):
            mock_plan_db.select_by_share_token = AsyncMock(return_value=plan)
            mock_im_cls.get_calculation_result = AsyncMock(return_value=calc_result)
            mock_claim_db.select_by_plan_token = AsyncMock(return_value=[])

            resp = await test_client.get("/api/public/workflow/wf_cltok/claims")

        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["status"] == 200

    @pytest.mark.asyncio
    async def test_invalid_token_returns_403(self, test_client):
        """无效 token → 403"""
        with patch(
            "src_v2.backend.api.api_public.EveIndustryPlanDBUtils"
        ) as mock_db:
            mock_db.select_by_share_token = AsyncMock(return_value=None)

            resp = await test_client.get("/api/public/workflow/bad_token/claims")

        assert resp.status_code == 403
