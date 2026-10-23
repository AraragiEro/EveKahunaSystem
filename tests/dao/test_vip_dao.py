# -*- coding: utf-8 -*-
"""VipState DAO 测试（SQLite in-memory）

回归背景：``vip_state`` 在会员过期后不会清空 ``vip_level``，历史开通记录会一直保留。
``count_vip_users`` 原先只按 level 计数（不看到期时间），导致首页「VIP 会员」
把已过期用户也算进去（生产库 52 vs 实际有效 14）。
"""
from datetime import datetime, timedelta

import pytest

from src_v2.core.database import model
from src_v2.core.database.kahuna_database_utils_v2 import (
    UserDBUtils,
    VipStateDBUtils,
)
from src_v2.core.utils import get_beijing_utctime

pytestmark = pytest.mark.dao


def _beijing_now() -> datetime:
    return get_beijing_utctime(datetime.now())


async def _add_vip(user_name: str, vip_level, vip_end_date) -> None:
    await UserDBUtils.save_obj(
        model.User(
            user_name=user_name,
            create_date=datetime.utcnow(),
            password_hash="test_hash",
        )
    )
    await VipStateDBUtils.save_obj(
        model.VipState(
            user_name=user_name,
            vip_level=vip_level,
            vip_end_date=vip_end_date,
        )
    )


class TestCountVipUsers:
    @pytest.mark.asyncio
    async def test_counts_only_active_vip(self, db_session):
        """只统计未过期（或未设置到期）的 VIP，过期记录与 Free 用户不计入"""
        now = _beijing_now()
        await _add_vip("active_alpha", "vip_alpha", now + timedelta(days=10))
        await _add_vip("active_omega", "vip_omega", now + timedelta(days=10))
        await _add_vip("expired_alpha", "vip_alpha", now - timedelta(days=1))
        await _add_vip("expired_omega", "vip_omega", now - timedelta(days=1))
        await _add_vip("free_user", None, None)
        # 未设置到期时间视为长期有效
        await _add_vip("no_end_date", "vip_omega", None)

        assert await VipStateDBUtils.count_vip_users() == 3

    @pytest.mark.asyncio
    async def test_all_expired_returns_zero(self, db_session):
        """全部过期 → 0（修复前会返回 2）"""
        now = _beijing_now()
        await _add_vip("expired_alpha", "vip_alpha", now - timedelta(days=1))
        await _add_vip("expired_omega", "vip_omega", now - timedelta(days=1))

        assert await VipStateDBUtils.count_vip_users() == 0

    @pytest.mark.asyncio
    async def test_empty_table_returns_zero(self, db_session):
        assert await VipStateDBUtils.count_vip_users() == 0


class TestSelectActiveVipUserNames:
    @pytest.mark.asyncio
    async def test_returns_only_active_vip(self, db_session):
        """只返回未过期的 VIP 用户名，过期与 Free 用户被排除"""
        now = _beijing_now()
        await _add_vip("active_alpha", "vip_alpha", now + timedelta(days=10))
        await _add_vip("active_omega", "vip_omega", now + timedelta(days=10))
        await _add_vip("expired_alpha", "vip_alpha", now - timedelta(days=1))
        await _add_vip("free_user", None, None)

        names = await VipStateDBUtils.select_active_vip_user_names()

        assert sorted(names) == ["active_alpha", "active_omega"]

    @pytest.mark.asyncio
    async def test_empty_table_returns_empty_list(self, db_session):
        assert await VipStateDBUtils.select_active_vip_user_names() == []
