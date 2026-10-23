# -*- coding: utf-8 -*-
"""仪表盘运营统计聚合测试

回归背景：``aggregate_ops_stats`` 原先只读 ``overview_data:{user}``（1 小时 TTL、
且会被不含资产的 dashboardOverview 接口覆盖），缓存 miss 的用户被静默跳过，
导致首页「总资产价值」长期只统计到个别在线用户。
现在改为：有效 VIP + Redis 汇总 hash 优先 + 历史快照回退，五项求和。
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

UH = "src_v2.backend.api.EVE.utils_home"
DBU = "src_v2.core.database.kahuna_database_utils_v2"


def _processed(total_value: float, running: float = 0.0) -> dict:
    return {
        "walletValue": total_value - running,
        "orderValue": 0.0,
        "runningProcessValue": running,
        "markedAssetValue": 0.0,
        "unmarkedAssetValue": 0.0,
        "totalValue": total_value,
    }


def _redis_mock(hash_values: dict, get_values: dict | None = None):
    redis = MagicMock()
    redis.hgetall = AsyncMock(return_value=hash_values)
    redis.get = AsyncMock(return_value=(get_values or {}).get("value"))
    redis.hset = AsyncMock()
    rdm = MagicMock()
    rdm.return_value.r = redis
    return rdm, redis


@pytest.mark.asyncio
async def test_aggregate_uses_hash_then_history_without_cache():
    """hash 有值的用户直接取，缺失的回退历史快照，三者之和进入总资产"""
    hash_values = {
        b"vip_a": json.dumps(_processed(100.0, 10.0)).encode(),
    }
    rdm, redis = _redis_mock(hash_values)
    history = {"vip_b": _processed(200.0, 20.0)}

    with (
        patch(f"{UH}.rdm", rdm),
        patch(f"{DBU}.UserDBUtils.count_all", AsyncMock(return_value=199)),
        patch(f"{DBU}.VipStateDBUtils.count_vip_users", AsyncMock(return_value=14)),
        patch(f"{DBU}.EveIndustryPlanDBUtils.count_all", AsyncMock(return_value=316)),
        patch(
            f"{DBU}.VipStateDBUtils.select_active_vip_user_names",
            AsyncMock(return_value=["vip_a", "vip_b", "vip_c"]),
        ),
        patch(
            f"{DBU}.EveOverviewHistoryDBUtils.get_latest_overview_data_by_user_names",
            AsyncMock(return_value=history),
        ) as history_query,
    ):
        from src_v2.backend.api.EVE.utils_home import aggregate_ops_stats

        stats = await aggregate_ops_stats()

    assert stats["total_users"] == 199
    assert stats["total_vips"] == 14
    assert stats["total_plans"] == 316
    # vip_a(100, hash) + vip_b(200, 历史) + vip_c(无数据) = 300
    assert stats["total_asset_value"] == 300.0
    assert stats["total_running_value"] == 30.0
    # 只对 hash 里缺的用户查历史
    history_query.assert_awaited_once_with(["vip_b", "vip_c"])
    # 不再读取 1 小时 TTL 的 overview_data 缓存
    redis.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_aggregate_ignores_invalid_hash_value():
    """hash 里坏掉的 JSON 不影响其他用户，且仍会走历史回退"""
    rdm, _ = _redis_mock({b"vip_a": b"not-json"})
    history = {"vip_a": _processed(50.0)}

    with (
        patch(f"{UH}.rdm", rdm),
        patch(f"{DBU}.UserDBUtils.count_all", AsyncMock(return_value=1)),
        patch(f"{DBU}.VipStateDBUtils.count_vip_users", AsyncMock(return_value=1)),
        patch(f"{DBU}.EveIndustryPlanDBUtils.count_all", AsyncMock(return_value=0)),
        patch(
            f"{DBU}.VipStateDBUtils.select_active_vip_user_names",
            AsyncMock(return_value=["vip_a"]),
        ),
        patch(
            f"{DBU}.EveOverviewHistoryDBUtils.get_latest_overview_data_by_user_names",
            AsyncMock(return_value=history),
        ),
    ):
        from src_v2.backend.api.EVE.utils_home import aggregate_ops_stats

        stats = await aggregate_ops_stats()

    assert stats["total_asset_value"] == 50.0


@pytest.mark.asyncio
async def test_record_ops_latest_overview_processes_and_writes_hash():
    """完整 overview 计算后写入长期 hash，存的是五项求和后的结果"""
    rdm, redis = _redis_mock({})
    raw_overview = {
        "orderValue": {"char1": 30.0},
        "walletValue": {"char1": 70.0},
        "runningProcessValue": 5.0,
        "markedAssetValue": 400.0,
        "unmarkedAssetValue": 100.0,
    }

    with patch(f"{UH}.rdm", rdm):
        from src_v2.backend.api.EVE.utils_home import record_ops_latest_overview

        await record_ops_latest_overview("vip_a", raw_overview)

    redis.hset.assert_awaited_once()
    args = redis.hset.await_args.args
    assert args[0] == "ops_overview_latest"
    assert args[1] == "vip_a"
    stored = json.loads(args[2])
    assert stored["walletValue"] == 70.0
    assert stored["orderValue"] == 30.0
    assert stored["totalValue"] == 605.0
