"""Overview 历史数据 DAO 测试（SQLite in-memory）

覆盖新增的批量接口 ``get_latest_overview_data_by_user_names``：
仪表盘运营统计在 Redis 汇总值缺失时，用它回退到每个用户最新一条历史快照。
"""
from datetime import date, datetime

import pytest

from src_v2.core.database import model
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveOverviewHistoryDBUtils,
    UserDBUtils,
)

pytestmark = pytest.mark.dao


async def _add_history(user_name: str, day: date, data: dict) -> None:
    await EveOverviewHistoryDBUtils.save_obj(
        model.EveOverviewHistory(user_name=user_name, date=day, data=data)
    )


async def _add_user(user_name: str) -> None:
    await UserDBUtils.save_obj(
        model.User(
            user_name=user_name,
            create_date=datetime.utcnow(),
            password_hash="test_hash",
        )
    )


class TestGetLatestOverviewDataByUserNames:
    @pytest.mark.asyncio
    async def test_returns_latest_row_per_user(self, db_session):
        for name in ("user_a", "user_b"):
            await _add_user(name)

        await _add_history("user_a", date(2026, 10, 20), {"totalValue": 100})
        await _add_history("user_a", date(2026, 10, 22), {"totalValue": 300})
        await _add_history("user_b", date(2026, 10, 21), {"totalValue": 200})

        result = await EveOverviewHistoryDBUtils.get_latest_overview_data_by_user_names(
            ["user_a", "user_b"]
        )

        assert result["user_a"]["totalValue"] == 300
        assert result["user_b"]["totalValue"] == 200

    @pytest.mark.asyncio
    async def test_skips_users_without_history(self, db_session):
        await _add_user("user_a")
        await _add_user("user_c")
        await _add_history("user_a", date(2026, 10, 22), {"totalValue": 100})

        result = await EveOverviewHistoryDBUtils.get_latest_overview_data_by_user_names(
            ["user_a", "user_c"]
        )

        assert set(result.keys()) == {"user_a"}

    @pytest.mark.asyncio
    async def test_empty_user_list_returns_empty_dict(self, db_session):
        result = await EveOverviewHistoryDBUtils.get_latest_overview_data_by_user_names([])
        assert result == {}
