# -*- coding: utf-8 -*-
"""安全审计 02-high：认证通过但归属未校验的越权回归测试

覆盖 docs/security/02-high.md 中的：
- #3  /api/EVE/industry/getPlanCalculateResultTableView：请求体 user_name 不得直接替换身份，
      只有管理员可代查；普通用户 → 403
- #6  /api/EVE/asset/{close,start,delete}AssetPullMission：只能操作自己的资产拉取任务
- #10 /api/EVE/asset/getAssetViewData：他人未公开的视图 → 403，公开/本人/管理员可读

使用 tests/conftest.py 的 test_client fixture。
"""
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

import src_v2.backend.app as _backend_app

TEST_SECRET = "test-secret-key-for-jwt"


def _auth_headers(user_id: str = "attacker"):
    """构造带 user_id 的有效 JWT 认证头（仅 Bearer，不触发 CSRF）"""
    _backend_app.app.secret_key = TEST_SECRET
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24),
    }
    token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _vip_alpha_permission_manager():
    """构造能通过 @role_required(["vip_alpha"]) 的 permission_manager mock"""
    mock_pm = MagicMock()
    mock_pm.get_user_roles = AsyncMock(return_value=["user"])
    mock_pm.get_all_descendant_roles = AsyncMock(return_value=set())
    vip_state = MagicMock()
    vip_state.vip_level = "vip_alpha"
    mock_pm.get_vip_state = AsyncMock(return_value=vip_state)
    return mock_pm


# ──────────────────────────────────────────────
# #3 工业计划计算结果：user_name 不得替换身份
# ──────────────────────────────────────────────
@pytest.mark.api
class TestIndustryPlanAuthz:
    """POST /api/EVE/industry/getPlanCalculateResultTableView"""

    URL = "/api/EVE/industry/getPlanCalculateResultTableView"

    @pytest.mark.asyncio
    async def test_other_user_by_user_name_returns_403(self, test_client):
        """普通用户提交他人 user_name → 403，且不进入业务逻辑"""
        with (
            patch(
                "src_v2.backend.api.EVE.api_industry.is_admin_user",
                AsyncMock(return_value=False),
            ),
            patch("src_v2.backend.api.EVE.api_industry.IndustryManager") as mock_im,
        ):
            resp = await test_client.post(
                self.URL,
                headers=_auth_headers("attacker"),
                json={
                    "plan_name": "victim_plan",
                    "user_name": "victim",
                    "operate_type": "status",
                },
            )
        data = await resp.get_json()

        assert resp.status_code == 403
        assert data["message"] == "无权查看他人的工业计划"
        mock_im.get_calculation_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_can_query_other_user(self, test_client):
        """管理员代查能力保留 → 200，且以目标用户身份查询"""
        with (
            patch(
                "src_v2.backend.api.EVE.api_industry.is_admin_user",
                AsyncMock(return_value=True),
            ),
            patch("src_v2.backend.api.EVE.api_industry.IndustryManager") as mock_im,
        ):
            mock_im.get_calculation_status = AsyncMock(return_value={"status": "done"})
            resp = await test_client.post(
                self.URL,
                headers=_auth_headers("admin_user"),
                json={
                    "plan_name": "victim_plan",
                    "user_name": "victim",
                    "operate_type": "status",
                },
            )

        assert resp.status_code == 200
        mock_im.get_calculation_status.assert_awaited_once_with(
            "victim", "victim_plan"
        )

    @pytest.mark.asyncio
    async def test_own_plan_returns_200(self, test_client):
        """不传 user_name 时使用当前用户身份 → 200"""
        with patch(
            "src_v2.backend.api.EVE.api_industry.IndustryManager"
        ) as mock_im:
            mock_im.get_calculation_status = AsyncMock(return_value={"status": "done"})
            resp = await test_client.post(
                self.URL,
                headers=_auth_headers("attacker"),
                json={"plan_name": "my_plan", "operate_type": "status"},
            )

        assert resp.status_code == 200
        mock_im.get_calculation_status.assert_awaited_once_with(
            "attacker", "my_plan"
        )


# ──────────────────────────────────────────────
# #6 资产拉取任务 启停/删除：归属校验
# ──────────────────────────────────────────────
@pytest.mark.api
class TestAssetPullMissionAuthz:
    """close/start/deleteAssetPullMission"""

    CLOSE_URL = "/api/EVE/asset/closeAssetPullMission"
    START_URL = "/api/EVE/asset/startAssetPullMission"
    DELETE_URL = "/api/EVE/asset/deleteAssetPullMission"
    BODY = {
        "asset_owner_type": "character",
        "asset_owner_id": 123456,
        "active": False,
    }

    @staticmethod
    def _mission(owner: str):
        mission = MagicMock()
        mission.user_name = owner
        return mission

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", [CLOSE_URL, START_URL])
    async def test_change_other_users_mission_returns_403(self, test_client, url):
        """关闭/启动他人任务 → 403，且不写库"""
        with (
            patch(
                "src_v2.backend.api.permission_required.permission_manager",
                _vip_alpha_permission_manager(),
            ),
            patch(
                "src_v2.backend.api.EVE.api_asset.is_admin_user",
                AsyncMock(return_value=False),
            ),
            patch(
                "src_v2.backend.api.EVE.api_asset."
                "EveAssetPullMissionDBUtils.select_mission_by_owner_id_and_owner_type",
                AsyncMock(return_value=self._mission("victim")),
            ),
            patch("src_v2.backend.api.EVE.api_asset.AssetManager") as mock_am_cls,
        ):
            resp = await test_client.post(
                url, headers=_auth_headers("attacker"), json=self.BODY
            )

        assert resp.status_code == 403
        mock_am_cls.return_value.change_asset_pull_mission_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_own_mission_returns_200(self, test_client):
        """关闭本人任务 → 200，正常写库"""
        with (
            patch(
                "src_v2.backend.api.permission_required.permission_manager",
                _vip_alpha_permission_manager(),
            ),
            patch(
                "src_v2.backend.api.EVE.api_asset.is_admin_user",
                AsyncMock(return_value=False),
            ),
            patch(
                "src_v2.backend.api.EVE.api_asset."
                "EveAssetPullMissionDBUtils.select_mission_by_owner_id_and_owner_type",
                AsyncMock(return_value=self._mission("attacker")),
            ),
            patch("src_v2.backend.api.EVE.api_asset.AssetManager") as mock_am_cls,
        ):
            mock_am = MagicMock()
            mock_am.change_asset_pull_mission_status = AsyncMock()
            mock_am_cls.return_value = mock_am

            resp = await test_client.post(
                self.CLOSE_URL, headers=_auth_headers("attacker"), json=self.BODY
            )

        assert resp.status_code == 200
        mock_am.change_asset_pull_mission_status.assert_awaited_once_with(
            "character", 123456, False
        )

    @pytest.mark.asyncio
    async def test_delete_other_users_mission_returns_403(self, test_client):
        """删除他人任务 → 403，且不删库"""
        with (
            patch(
                "src_v2.backend.api.permission_required.permission_manager",
                _vip_alpha_permission_manager(),
            ),
            patch(
                "src_v2.backend.api.EVE.api_asset.is_admin_user",
                AsyncMock(return_value=False),
            ),
            patch(
                "src_v2.backend.api.EVE.api_asset."
                "EveAssetPullMissionDBUtils.select_mission_by_owner_id_and_owner_type",
                AsyncMock(return_value=self._mission("victim")),
            ),
            patch(
                "src_v2.backend.api.EVE.api_asset.EveAssetPullMissionDBUtils.delete_obj",
                AsyncMock(),
            ) as mock_delete,
        ):
            resp = await test_client.delete(
                self.DELETE_URL,
                headers=_auth_headers("attacker"),
                json={"asset_owner_type": "character", "asset_owner_id": 123456},
            )

        assert resp.status_code == 403
        mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_mission_returns_400(self, test_client):
        """任务不存在 → 400"""
        with (
            patch(
                "src_v2.backend.api.permission_required.permission_manager",
                _vip_alpha_permission_manager(),
            ),
            patch(
                "src_v2.backend.api.EVE.api_asset."
                "EveAssetPullMissionDBUtils.select_mission_by_owner_id_and_owner_type",
                AsyncMock(return_value=None),
            ),
        ):
            resp = await test_client.post(
                self.CLOSE_URL, headers=_auth_headers("attacker"), json=self.BODY
            )

        assert resp.status_code == 400


# ──────────────────────────────────────────────
# #10 资产视图数据：sid 不是凭据
# ──────────────────────────────────────────────
@pytest.mark.api
class TestAssetViewDataAuthz:
    """GET /api/EVE/asset/getAssetViewData"""

    URL = "/api/EVE/asset/getAssetViewData"

    @staticmethod
    def _view(owner: str, public: bool = False, view_type: str = "default"):
        view = MagicMock()
        view.user_name = owner
        view.public = public
        view.view_type = view_type
        view.config = {}
        return view

    @pytest.mark.asyncio
    async def test_other_users_private_view_returns_403(self, test_client):
        """他人未公开视图 → 403，且不查询资产数据"""
        with (
            patch("src_v2.backend.api.EVE.api_asset.AssetManager") as mock_am_cls,
            patch(
                "src_v2.backend.api.EVE.api_asset.is_admin_user",
                AsyncMock(return_value=False),
            ),
        ):
            mock_am = MagicMock()
            mock_am.get_asset_view_by_sid = AsyncMock(
                return_value=self._view("victim", public=False)
            )
            mock_am.get_asset_view_data = AsyncMock(return_value={})
            mock_am_cls.return_value = mock_am

            resp = await test_client.get(
                f"{self.URL}?asset_view_sid=victim_sid",
                headers=_auth_headers("attacker"),
            )

        assert resp.status_code == 403
        mock_am.get_asset_view_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_public_view_returns_200(self, test_client):
        """已公开（分享）的视图 → 200"""
        with (
            patch("src_v2.backend.api.EVE.api_asset.AssetManager") as mock_am_cls,
            patch(
                "src_v2.backend.api.EVE.api_asset.is_admin_user",
                AsyncMock(return_value=False),
            ),
        ):
            mock_am = MagicMock()
            mock_am.get_asset_view_by_sid = AsyncMock(
                return_value=self._view("victim", public=True)
            )
            mock_am.get_asset_view_data = AsyncMock(return_value={123: {"quantity": 1}})
            mock_am_cls.return_value = mock_am

            resp = await test_client.get(
                f"{self.URL}?asset_view_sid=public_sid",
                headers=_auth_headers("attacker"),
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_own_view_returns_200(self, test_client):
        """本人视图（未公开）→ 200"""
        with (
            patch("src_v2.backend.api.EVE.api_asset.AssetManager") as mock_am_cls,
            patch(
                "src_v2.backend.api.EVE.api_asset.is_admin_user",
                AsyncMock(return_value=False),
            ),
        ):
            mock_am = MagicMock()
            mock_am.get_asset_view_by_sid = AsyncMock(
                return_value=self._view("attacker", public=False)
            )
            mock_am.get_asset_view_data = AsyncMock(return_value={})
            mock_am_cls.return_value = mock_am

            resp = await test_client.get(
                f"{self.URL}?asset_view_sid=my_sid",
                headers=_auth_headers("attacker"),
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_missing_view_returns_404(self, test_client):
        """视图不存在 → 404（而不是 AttributeError 500）"""
        with patch("src_v2.backend.api.EVE.api_asset.AssetManager") as mock_am_cls:
            mock_am = MagicMock()
            mock_am.get_asset_view_by_sid = AsyncMock(return_value=None)
            mock_am_cls.return_value = mock_am

            resp = await test_client.get(
                f"{self.URL}?asset_view_sid=not_exist",
                headers=_auth_headers("attacker"),
            )

        assert resp.status_code == 404
