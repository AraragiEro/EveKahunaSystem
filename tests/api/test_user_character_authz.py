# -*- coding: utf-8 -*-
"""用户角色管理接口越权防护测试

覆盖 /api/user/setMainCharacter 与 /api/user/deleteCharacter：
- 空 Bearer（原始复现脚本）→ 401，不会进入业务逻辑
- 操作他人角色 → 403
- 操作本人角色 → 200

使用 mock_config / test_client 等 conftest fixture。
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


@pytest.mark.api
class TestSetMainCharacterAuthz:
    """POST /api/user/setMainCharacter"""

    @pytest.mark.asyncio
    async def test_blank_bearer_rejected(self, test_client):
        """原始复现脚本原样请求：空 token + 空 characterName → 401"""
        resp = await test_client.post(
            "/api/user/setMainCharacter",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer ",
                "X-CSRF-Token": "",
            },
            json={"characterName": ""},
        )
        data = await resp.get_json()

        assert resp.status_code == 401
        assert "认证" in data["error"]

    @pytest.mark.asyncio
    async def test_other_users_character_returns_403(self, test_client):
        """提交他人角色名 → 403"""
        from src_v2.core.utils import PermissionDeniedException

        with patch("src_v2.backend.api.api_user.UserManager") as mock_um_cls:
            mock_um = MagicMock()
            mock_um.set_main_character = AsyncMock(
                side_effect=PermissionDeniedException("角色不存在或不属于当前用户")
            )
            mock_um_cls.return_value = mock_um

            resp = await test_client.post(
                "/api/user/setMainCharacter",
                headers=_auth_headers(),
                json={"characterName": "Victim Director"},
            )
        data = await resp.get_json()

        assert resp.status_code == 403
        assert data["message"] == "角色不存在或不属于当前用户"
        mock_um.set_main_character.assert_awaited_once_with("attacker", "Victim Director")

    @pytest.mark.asyncio
    async def test_own_character_returns_200(self, test_client):
        """提交本人角色名 → 200 + director 状态"""
        char_db = MagicMock()
        char_db.character_name = "My Character"
        char = MagicMock()
        char.director = True
        char.refresh_character_token = AsyncMock()

        with (
            patch("src_v2.backend.api.api_user.UserManager") as mock_um_cls,
            patch(
                "src_v2.backend.api.api_user.EveAuthedCharacterDBUtils.select_character_by_character_name_and_owner",
                AsyncMock(return_value=char_db),
            ),
            patch("src_v2.backend.api.api_user.Character.from_db_obj", return_value=char),
        ):
            mock_um = MagicMock()
            mock_um.set_main_character = AsyncMock()
            mock_um_cls.return_value = mock_um

            resp = await test_client.post(
                "/api/user/setMainCharacter",
                headers=_auth_headers(),
                json={"characterName": "My Character"},
            )
        data = await resp.get_json()

        assert resp.status_code == 200
        assert data["director"] is True
        assert data["message"] == "主角色设置成功"
        mock_um.set_main_character.assert_awaited_once_with("attacker", "My Character")


@pytest.mark.api
class TestDeleteCharacterAuthz:
    """POST /api/user/deleteCharacter"""

    @pytest.mark.asyncio
    async def test_other_users_character_returns_403(self, test_client):
        """提交他人角色名删除 → 403"""
        from src_v2.core.utils import PermissionDeniedException

        with patch("src_v2.backend.api.api_user.CharacterManager") as mock_cm_cls:
            mock_cm = MagicMock()
            mock_cm.delete_character_by_character_name = AsyncMock(
                side_effect=PermissionDeniedException("角色不存在或不属于当前用户")
            )
            mock_cm_cls.return_value = mock_cm

            resp = await test_client.post(
                "/api/user/deleteCharacter",
                headers=_auth_headers(),
                json={"characterName": "Victim Director"},
            )
        data = await resp.get_json()

        assert resp.status_code == 403
        assert data["message"] == "角色不存在或不属于当前用户"
        mock_cm.delete_character_by_character_name.assert_awaited_once_with(
            "Victim Director", "attacker"
        )

    @pytest.mark.asyncio
    async def test_own_character_returns_200(self, test_client):
        """删除本人角色 → 200"""
        with patch("src_v2.backend.api.api_user.CharacterManager") as mock_cm_cls:
            mock_cm = MagicMock()
            mock_cm.delete_character_by_character_name = AsyncMock()
            mock_cm_cls.return_value = mock_cm

            resp = await test_client.post(
                "/api/user/deleteCharacter",
                headers=_auth_headers(),
                json={"characterName": "My Alt"},
            )
        data = await resp.get_json()

        assert resp.status_code == 200
        assert data["message"] == "角色删除成功"
