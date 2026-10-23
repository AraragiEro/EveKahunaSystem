# -*- coding: utf-8 -*-
"""重新授权/换绑时必须重置 token 永久失效状态

回归背景：
- ``character.py`` 里刷新 token 遇到 ``InvalidGrantError`` 会累加
  ``refresh_failure_count``，达到 ``MAX_REFRESH_FAILURES``(3) 后
  ``ac_token`` 直接抛 ``EveTokenPermanentlyInvalidError``，不再尝试刷新。
- ``insert_new_character`` 原实现用「新建对象 + merge」只更新 token 列，
  未显式赋值的 ``refresh_failure_count`` / ``last_refresh_error`` 会被
  SQLAlchemy ``merge`` 静默跳过，于是用户重新授权后仍然被判为永久失效。
"""

import datetime
import inspect

import pytest
from unittest.mock import AsyncMock, patch

from src_v2.core.database.model import EveAuthedCharacter

CM = "src_v2.model.EVE.character.character_manager"


def _existing_character(failure_count: int = 3) -> EveAuthedCharacter:
    """构造一条「已被判定永久失效」的既有角色行"""
    return EveAuthedCharacter(
        character_id=2116728305,
        owner_user_name="clearwind",
        character_name="Old Name",
        birthday=datetime.datetime(2010, 1, 1),
        access_token="old-access",
        refresh_token="old-refresh",
        expires_time=datetime.datetime(2026, 10, 22, 18, 29, 59),
        corporation_id=98570132,
        director=False,
        refresh_failure_count=failure_count,
        last_refresh_error="InvalidGrantError: (invalid_grant) Invalid refresh token.",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rebind_resets_token_failure_state():
    """重新绑定已永久失效的角色 → 失败计数与错误信息被清零"""
    existing = _existing_character()

    verify = {
        "CharacterID": 2116728305,
        "CharacterName": "Clearwind Sherlock",
        "ExpiresOn": "2030-01-01T00:00:00Z",
    }
    character_info = {
        "corporation_id": 98570132,
        "birthday": "2010-01-01T00:00:00Z",
    }

    async def fake_roles(ac_token, character_id):
        """生产代码传的是 await 后的 token；这里自行消费协程，避免协程泄漏"""
        if inspect.isawaitable(ac_token):
            await ac_token
        return {"roles": []}

    with (
        patch(f"{CM}.eveesi.verify_eve_oauth_token", AsyncMock(return_value=verify)),
        patch(f"{CM}.eveesi.characters_character", AsyncMock(return_value=character_info)),
        patch(f"{CM}.eveesi.characters_character_roles", new=fake_roles),
        patch(
            f"{CM}.EveAuthedCharacterDBUtils.select_character_by_character_id",
            AsyncMock(return_value=existing),
        ),
        patch(f"{CM}.EveAuthedCharacterDBUtils.merge", AsyncMock()) as merge,
    ):
        from src_v2.model.EVE.character.character_manager import CharacterManager

        character = await CharacterManager().insert_new_character(
            {
                "ac_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_at": 1893456000,  # 2030-01-01T00:00:00Z
            },
            "clearwind",
        )

    # 持久化对象上的失效状态被显式重置
    assert existing.refresh_failure_count == 0
    assert existing.last_refresh_error is None
    # token / 角色信息照常更新
    assert existing.access_token == "new-access"
    assert existing.refresh_token == "new-refresh"
    assert existing.character_name == "Clearwind Sherlock"
    assert existing.corporation_id == 98570132

    # 返回的角色对象不再被视为永久失效
    assert character.refresh_failure_count == 0
    assert character.token_permanently_failed is False
    # 两次 merge：一次写 token + 重置状态，一次补写 director
    assert merge.await_count == 2
