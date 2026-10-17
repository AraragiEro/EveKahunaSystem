# -*- coding: utf-8 -*-
"""设置主角色 / 删除角色的归属校验回归测试

覆盖：
- UserManager.set_main_character：只能把自己绑定的角色设为主角色
- CharacterManager.delete_character_by_character_name：只能删除自己绑定的角色

安全背景：这两个方法原先仅按角色名全局查询，任意登录用户可提交他人角色名，
导致越权占用他人角色（含其 ESI token）并自动获得 EveCorpDirector 角色。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src_v2.core.utils import PermissionDeniedException

UM = "src_v2.core.user.user_manager"
CM = "src_v2.model.EVE.character.character_manager"


def _character(character_id=12345, name="My Director", owner="attacker"):
    obj = MagicMock()
    obj.character_id = character_id
    obj.character_name = name
    obj.owner_user_name = owner
    obj.director = True
    return obj


@pytest.mark.asyncio
async def test_set_main_character_rejects_other_users_character():
    """提交他人角色名 → 拒绝，且不写库、不授角色、不写缓存"""
    attacker_user_data = MagicMock()
    attacker_user_data.main_character_id = None

    with (
        patch(
            f"{UM}.EveAuthedCharacterDBUtils.select_character_by_character_name_and_owner",
            AsyncMock(return_value=None),
        ) as query,
        patch(
            f"{UM}.UserDataDBUtils.select_user_data_by_user_name",
            AsyncMock(return_value=attacker_user_data),
        ),
        patch(f"{UM}.UserDataDBUtils.merge", AsyncMock()) as merge,
        patch(f"{UM}.permission_manager.add_role_to_user", AsyncMock()) as add_role,
        patch(f"{UM}.rdm") as rdm,
    ):
        from src_v2.core.user.user_manager import UserManager

        with pytest.raises(PermissionDeniedException):
            await UserManager().set_main_character("attacker", "Victim Director")

    query.assert_awaited_once_with("Victim Director", "attacker")
    assert attacker_user_data.main_character_id is None
    merge.assert_not_awaited()
    add_role.assert_not_awaited()
    rdm.assert_not_called()


@pytest.mark.asyncio
async def test_set_main_character_accepts_own_director_character():
    """本人总监角色 → 正常写入并授予 EveCorpDirector"""
    own_character = _character()
    user_data = MagicMock()
    user_data.main_character_id = None

    fake_character = MagicMock()
    fake_character.director = True
    fake_character.refresh_character_token = AsyncMock()

    with (
        patch(
            f"{UM}.EveAuthedCharacterDBUtils.select_character_by_character_name_and_owner",
            AsyncMock(return_value=own_character),
        ) as query,
        patch(
            f"{UM}.UserDataDBUtils.select_user_data_by_user_name",
            AsyncMock(return_value=user_data),
        ),
        patch(f"{UM}.UserDataDBUtils.merge", AsyncMock()) as merge,
        patch(f"{UM}.Character.from_db_obj", return_value=fake_character),
        patch(f"{UM}.permission_manager.get_user_roles", AsyncMock(return_value=["user"])),
        patch(f"{UM}.permission_manager.add_role_to_user", AsyncMock()) as add_role,
        patch(f"{UM}.rdm") as rdm,
    ):
        rdm.return_value.r.set = AsyncMock()

        from src_v2.core.user.user_manager import UserManager

        await UserManager().set_main_character("attacker", "My Director")

    query.assert_awaited_once_with("My Director", "attacker")
    assert user_data.main_character_id == own_character.character_id
    merge.assert_awaited()
    add_role.assert_awaited_once_with("attacker", "EveCorpDirector")
    rdm.return_value.r.set.assert_awaited()


@pytest.mark.asyncio
async def test_set_main_character_removes_role_when_not_director():
    """本人非总监角色 → 撤销已持有的 EveCorpDirector"""
    own_character = _character(name="My Alt")
    user_data = MagicMock()
    user_data.main_character_id = None

    fake_character = MagicMock()
    fake_character.director = False
    fake_character.refresh_character_token = AsyncMock()

    with (
        patch(
            f"{UM}.EveAuthedCharacterDBUtils.select_character_by_character_name_and_owner",
            AsyncMock(return_value=own_character),
        ),
        patch(
            f"{UM}.UserDataDBUtils.select_user_data_by_user_name",
            AsyncMock(return_value=user_data),
        ),
        patch(f"{UM}.UserDataDBUtils.merge", AsyncMock()),
        patch(f"{UM}.Character.from_db_obj", return_value=fake_character),
        patch(
            f"{UM}.permission_manager.get_user_roles",
            AsyncMock(return_value=["user", "EveCorpDirector"]),
        ),
        patch(f"{UM}.permission_manager.remove_role_from_user", AsyncMock()) as remove_role,
        patch(f"{UM}.permission_manager.add_role_to_user", AsyncMock()) as add_role,
        patch(f"{UM}.rdm") as rdm,
    ):
        rdm.return_value.r.set = AsyncMock()

        from src_v2.core.user.user_manager import UserManager

        await UserManager().set_main_character("attacker", "My Alt")

    remove_role.assert_awaited_once_with("attacker", "EveCorpDirector")
    add_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_character_rejects_other_users_character():
    """提交他人角色名删除 → 拒绝，且不执行删除"""
    with (
        patch(
            f"{CM}.EveAuthedCharacterDBUtils.select_character_by_character_name_and_owner",
            AsyncMock(return_value=None),
        ) as query,
        patch(f"{CM}.EveAuthedCharacterDBUtils.delete_obj", AsyncMock()) as delete_obj,
    ):
        from src_v2.model.EVE.character.character_manager import CharacterManager

        with pytest.raises(PermissionDeniedException):
            await CharacterManager().delete_character_by_character_name(
                "Victim Director", "attacker"
            )

    query.assert_awaited_once_with("Victim Director", "attacker")
    delete_obj.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_character_accepts_own_character():
    """删除自己的角色 → 正常执行"""
    own_character = _character(name="My Alt")

    with (
        patch(
            f"{CM}.EveAuthedCharacterDBUtils.select_character_by_character_name_and_owner",
            AsyncMock(return_value=own_character),
        ) as query,
        patch(f"{CM}.EveAuthedCharacterDBUtils.delete_obj", AsyncMock()) as delete_obj,
    ):
        from src_v2.model.EVE.character.character_manager import CharacterManager

        await CharacterManager().delete_character_by_character_name("My Alt", "attacker")

    query.assert_awaited_once_with("My Alt", "attacker")
    delete_obj.assert_awaited_once_with(own_character)
