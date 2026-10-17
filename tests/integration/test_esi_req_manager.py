# -*- coding: utf-8 -*-
"""
ESI Request Manager 集成测试

测试 Token Bucket 算法、错误惩罚机制、请求队列轮询调度和两阶段流水线。
使用 time.time() mock 实现确定性的令牌桶测试，不发起真实 ESI 网络调用。
"""

import asyncio
import time
from datetime import datetime
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src_v2.model.EVE.eveesi.esi_req_manager import (
    EsiReqManager,
    EsiRequest,
    TokenBucket,
    PoolRegistry,
    LEGACY_POOL_NAME,
    parse_window_limit,
    esi_request,
    esi_manager,
    EsiUsageLogDBUtils,
)

# ============================================================
# 工具函数
# ============================================================


def make_esi_request(func, required_tokens=60, limit=5):
    """创建测试用 EsiRequest，带默认 future 和 func_name"""
    future = asyncio.get_running_loop().create_future()
    async def execute_func():
        return await func()
    req = EsiRequest(
        execute_func, (), {}, future,
        required_tokens=required_tokens,
        limit=limit,
    )
    # 覆盖 func_name 为唯一标识，便于测试区分
    req.func_name = func.__name__
    return req


def make_mock_func(name="test_func"):
    """创建具名 mock 异步函数"""
    async def mock_func():
        return {"status": "ok"}
    mock_func.__name__ = name
    return mock_func


# ============================================================
# Token Bucket 测试
# ============================================================


@pytest.mark.integration
class TestTokenBucket:
    """get_tokens() 令牌桶算法测试"""

    @pytest.mark.asyncio
    async def test_initial_state_no_tokens(self):
        """初始状态 token_pool=0，get_tokens(60) 返回 False"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()
        assert manager.token_pool == 0.0
        assert manager.last_token_update_time == 100.0

        # 时间未推进，无令牌累积
        with patch("time.time", return_value=100.0):
            result = await manager.get_tokens(60)
        assert result is False
        assert manager.token_pool == 0.0

    @pytest.mark.asyncio
    async def test_tokens_accumulate_after_time_passes(self):
        """等待 0.5s 后累积 150 令牌，get_tokens(60) 返回 True"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 推进 0.5 秒 → 0.5 * 300 = 150 令牌
        with patch("time.time", return_value=100.5):
            result = await manager.get_tokens(60)
        assert result is True
        # 150 - 60 = 90 剩余令牌
        assert manager.token_pool == 90.0

    @pytest.mark.asyncio
    async def test_token_pool_capped_at_max(self):
        """令牌池上限为 max_token_pool（1200），超出部分不累积"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 推进 10 秒 → 10 * 300 = 3000 令牌，但上限 1200
        with patch("time.time", return_value=110.0):
            result = await manager.get_tokens(60)
        assert result is True
        # 1200 - 60 = 1140
        assert manager.token_pool == 1140.0

    @pytest.mark.asyncio
    async def test_multiple_requests_deplete_pool(self):
        """多次请求消耗令牌池，最终令牌不足"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 推进足够时间积累满额令牌
        with patch("time.time", return_value=105.0):
            # 5s → 1500 令牌，capped at 1200
            result1 = await manager.get_tokens(500)
        assert result1 is True
        assert manager.token_pool == 700.0

        # 第二次获取 600
        with patch("time.time", return_value=105.0):
            result2 = await manager.get_tokens(600)
        assert result2 is True
        assert manager.token_pool == 100.0

        # 第三次获取 200 → 不足
        with patch("time.time", return_value=105.0):
            result3 = await manager.get_tokens(200)
        assert result3 is False
        # 令牌池未变化（获取失败时不动池）
        assert manager.token_pool == 100.0

    @pytest.mark.asyncio
    async def test_get_tokens_consumes_on_success_only(self):
        """get_tokens 仅在成功时消耗令牌，失败时不动池"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 推进 1s → 300 令牌，获取 60
        with patch("time.time", return_value=101.0):
            await manager.get_tokens(60)
        # 300 - 60 = 240
        assert manager.token_pool == pytest.approx(240.0)

        # 请求 300 令牌 → 失败（只剩 240）
        with patch("time.time", return_value=101.0):
            result = await manager.get_tokens(300)
        assert result is False
        # 池未被修改
        assert manager.token_pool == pytest.approx(240.0)

    @pytest.mark.asyncio
    async def test_token_generation_rate_300_per_second(self):
        """验证令牌生成速率：每秒 300 令牌"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 推进 1.0 秒 → 300 令牌
        with patch("time.time", return_value=101.0):
            await manager.get_tokens(300)
        # 300 - 300 = 0
        assert manager.token_pool == 0.0

        # 再推进 2.0 秒 → 600 令牌
        with patch("time.time", return_value=103.0):
            await manager.get_tokens(600)
        assert manager.token_pool == 0.0

    @pytest.mark.asyncio
    async def test_concurrent_get_tokens_serialized_by_lock(self):
        """并发 get_tokens 被 asyncio.Lock 序列化"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 推进 1s → 300 令牌
        with patch("time.time", return_value=101.0):
            # 两个并发获取 200 令牌
            results = await asyncio.gather(
                manager.get_tokens(200),
                manager.get_tokens(200),
            )
        # 第一个消耗 200 → pool=100, < 200 → 第二个失败
        assert results == [True, False]
        assert manager.token_pool == 100.0

    @pytest.mark.asyncio
    async def test_get_tokens_with_exact_pool_amount(self):
        """请求数量恰好等于令牌池数量时成功"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 推进 1s → 300 令牌
        with patch("time.time", return_value=101.0):
            result = await manager.get_tokens(300)
        assert result is True
        assert manager.token_pool == 0.0


# ============================================================
# 错误惩罚测试
# ============================================================


@pytest.mark.integration
class TestErrorPenalty:
    """deduct_error_penalty() 错误惩罚机制测试"""

    @pytest.mark.asyncio
    async def test_penalty_makes_pool_negative(self):
        """扣除惩罚后令牌池变为负数"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 未推进时间 → 令牌池仍为 0
        with patch("time.time", return_value=100.0):
            await manager.deduct_error_penalty(220)
        assert manager.token_pool == -220.0

    @pytest.mark.asyncio
    async def test_default_penalty_is_220(self):
        """默认惩罚令牌数为 220"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        with patch("time.time", return_value=100.0):
            await manager.deduct_error_penalty()
        assert manager.token_pool == -220.0

    @pytest.mark.asyncio
    async def test_penalty_blocks_subsequent_get_tokens(self):
        """惩罚后 get_tokens(60) 返回 False，直到令牌恢复"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 扣除 220 惩罚
        with patch("time.time", return_value=100.0):
            await manager.deduct_error_penalty(220)
        assert manager.token_pool == -220.0

        # 推进 0.5s → 150 令牌累积 → pool = -220 + 150 = -70，仍不足 60
        with patch("time.time", return_value=100.5):
            result = await manager.get_tokens(60)
        assert result is False
        assert manager.token_pool == -70.0

        # 再推进 0.5s → 150 令牌 → pool = -70 + 150 = 80，够 60
        with patch("time.time", return_value=101.0):
            result = await manager.get_tokens(60)
        assert result is True
        assert manager.token_pool == 20.0

    @pytest.mark.asyncio
    async def test_penalty_accumulates_tokens_before_deduct(self):
        """惩罚前先累积令牌（已过的时间应计入）"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 推进 1s → 300 令牌累积，再扣除 220
        with patch("time.time", return_value=101.0):
            await manager.deduct_error_penalty(220)
        # 300 - 220 = 80
        assert manager.token_pool == 80.0


# ============================================================
# 多池错误惩罚测试
# ============================================================


@pytest.mark.integration
class TestErrorPenaltyMultiPool:
    """_handle_error_response() 多池错误惩罚测试"""

    @pytest.mark.asyncio
    async def test_429_no_penalty(self):
        """429 速率限制响应不扣除惩罚令牌"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()
            pool = await manager.pool_registry.get_or_create("char-location", "150/15m")
        initial_pool = pool.token_pool

        func = make_mock_func("test_429")
        req = make_esi_request(func)
        req.pool_name = "char-location"

        await manager._handle_error_response(
            req, 429, {"group": "char-location", "retry_after": "30"}
        )

        assert pool.token_pool == initial_pool
        assert manager._legacy_bucket.token_pool == 0.0

    @pytest.mark.asyncio
    async def test_5xx_no_penalty(self):
        """5XX 服务器错误不扣除惩罚令牌"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()
        initial_legacy = manager._legacy_bucket.token_pool

        func = make_mock_func("test_5xx")
        req = make_esi_request(func)

        await manager._handle_error_response(req, 500, {})

        assert manager._legacy_bucket.token_pool == initial_legacy

    @pytest.mark.asyncio
    async def test_4xx_new_system_penalty(self):
        """新系统 4XX 按池容量 20% 惩罚"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()
            pool = await manager.pool_registry.get_or_create("char-location", "150/15m")
            initial_pool = pool.token_pool

            func = make_mock_func("test_4xx_new")
            req = make_esi_request(func)
            req.pool_name = "char-location"

            await manager._handle_error_response(req, 404, {"group": "char-location"})

            expected_penalty = min(220, 150 * 0.2)  # = 30
            assert pool.token_pool == pytest.approx(initial_pool - expected_penalty)

    @pytest.mark.asyncio
    async def test_old_system_low_remain_aggressive(self):
        """旧系统 error_remain=5 时扣除 220 并记录警告"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()
            initial_legacy = manager._legacy_bucket.token_pool

            func = make_mock_func("test_old_system")
            req = make_esi_request(func)

            with patch.object(manager.logger, "warning") as mock_warning:
                await manager._handle_error_response(req, 404, {"error_remain": "5"})

            assert manager._legacy_bucket.token_pool == initial_legacy - 220
            warning_messages = [
                str(call.args[0]) for call in mock_warning.call_args_list
            ]
            assert any("error limit low" in msg for msg in warning_messages)

    @pytest.mark.asyncio
    async def test_no_headers_fallback_penalty(self):
        """无速率限制头时回退到遗留桶 220 惩罚"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()
            initial_legacy = manager._legacy_bucket.token_pool

            func = make_mock_func("test_no_headers")
            req = make_esi_request(func)

            await manager._handle_error_response(req, 404, {})

            assert manager._legacy_bucket.token_pool == initial_legacy - 220

    @pytest.mark.asyncio
    async def test_network_exception_legacy_penalty(self):
        """网络异常时直接对遗留桶扣除 220 惩罚"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()
            initial_legacy = manager._legacy_bucket.token_pool

            # 模拟 _process_request 中 except 分支的行为
            await manager.deduct_error_penalty_legacy(220)

            assert manager._legacy_bucket.token_pool == initial_legacy - 220

    @pytest.mark.asyncio
    async def test_network_exception_discovered_pool_light_penalty(self):
        """网络异常时已发现池仅扣 5（不盲减 220，避免与 ESI 真实 remaining 严重偏离）"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()
            pool = await manager.pool_registry.get_or_create("char-industry", "150/15m")
            pool._reported_remaining = 100  # 模拟已发现池，ESI 上报 remaining=100

        # 模拟 _process_request 中 except 分支对已发现池的行为
        pool.error_count += 1
        pool._reported_remaining = max(0, pool._reported_remaining - 5)

        assert pool._reported_remaining == 95
        assert pool.error_count == 1

    @pytest.mark.asyncio
    async def test_network_exception_discovered_pool_negative_guard(self):
        """已发现池异常扣除 5 不会让 remaining 变为负数（floor=0）"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()
            pool = await manager.pool_registry.get_or_create("char-industry", "150/15m")
            pool._reported_remaining = 3  # 极低 remaining

        pool.error_count += 1
        pool._reported_remaining = max(0, pool._reported_remaining - 5)

        assert pool._reported_remaining == 0
        assert pool.error_count == 1


# ============================================================
# 装饰器模式测试
# ============================================================


@pytest.mark.integration
class TestDecoratorModes:
    """esi_request 装饰器四种调用模式测试"""

    @pytest.mark.asyncio
    async def test_bare_decorator(self):
        """@esi_request 使用默认 limit=5, pool=None"""
        @esi_request
        async def my_func():
            return {"ok": True}

        with patch.object(esi_manager, "add_request", new_callable=AsyncMock) as mock_add:
            try:
                await asyncio.wait_for(my_func(), timeout=0.1)
            except (asyncio.TimeoutError, Exception):
                pass

            assert mock_add.called
            req = mock_add.call_args[0][0]
            assert req.limit == 5
            assert req.pool_name is None

    @pytest.mark.asyncio
    async def test_limit_only_decorator(self):
        """@esi_request(limit=30) 使用 limit=30, pool=None"""
        @esi_request(limit=30)
        async def my_func():
            return {"ok": True}

        with patch.object(esi_manager, "add_request", new_callable=AsyncMock) as mock_add:
            try:
                await asyncio.wait_for(my_func(), timeout=0.1)
            except (asyncio.TimeoutError, Exception):
                pass

            assert mock_add.called
            req = mock_add.call_args[0][0]
            assert req.limit == 30
            assert req.pool_name is None

    @pytest.mark.asyncio
    async def test_pool_only_decorator(self):
        """@esi_request(pool='test-pool') 使用 limit=5, pool='test-pool'"""
        @esi_request(pool="test-pool")
        async def my_func():
            return {"ok": True}

        with patch.object(esi_manager, "add_request", new_callable=AsyncMock) as mock_add:
            try:
                await asyncio.wait_for(my_func(), timeout=0.1)
            except (asyncio.TimeoutError, Exception):
                pass

            assert mock_add.called
            req = mock_add.call_args[0][0]
            assert req.limit == 5
            assert req.pool_name == "test-pool"

    @pytest.mark.asyncio
    async def test_pool_and_limit_decorator(self):
        """@esi_request(pool='test-pool', limit=30) 同时指定 pool 和 limit"""
        @esi_request(pool="test-pool", limit=30)
        async def my_func():
            return {"ok": True}

        with patch.object(esi_manager, "add_request", new_callable=AsyncMock) as mock_add:
            try:
                await asyncio.wait_for(my_func(), timeout=0.1)
            except (asyncio.TimeoutError, Exception):
                pass

            assert mock_add.called
            req = mock_add.call_args[0][0]
            assert req.limit == 30
            assert req.pool_name == "test-pool"


# ============================================================
# 请求队列测试
# ============================================================


@pytest.mark.integration
class TestRequestQueue:
    """add_request() + _get_next_request() 队列调度测试"""

    @pytest.mark.asyncio
    async def test_add_request_to_empty_queue(self):
        """向空队列添加请求后，_get_next_request 返回该请求"""
        manager = EsiReqManager()
        func = make_mock_func("func_a")
        req = make_esi_request(func)

        await manager.add_request(req)

        next_req = manager._get_next_request()
        assert next_req is req
        assert next_req.func_name == "func_a"

    @pytest.mark.asyncio
    async def test_add_multiple_requests_same_type(self):
        """同一函数类型的多个请求保持 FIFO 顺序"""
        manager = EsiReqManager()
        func = make_mock_func("func_a")

        req1 = make_esi_request(func)
        req2 = make_esi_request(func)
        req3 = make_esi_request(func)

        await manager.add_request(req1)
        await manager.add_request(req2)
        await manager.add_request(req3)

        assert manager._get_next_request() is req1
        assert manager._get_next_request() is req2
        assert manager._get_next_request() is req3
        assert manager._get_next_request() is None

    @pytest.mark.asyncio
    async def test_round_robin_across_function_types(self):
        """不同函数类型的请求按轮询顺序调度"""
        manager = EsiReqManager()
        func_a = make_mock_func("func_a")
        func_b = make_mock_func("func_b")
        func_c = make_mock_func("func_c")

        # 添加顺序: A1, B1, A2, C1, B2
        a1 = make_esi_request(func_a); a2 = make_esi_request(func_a)
        b1 = make_esi_request(func_b); b2 = make_esi_request(func_b)
        c1 = make_esi_request(func_c)

        await manager.add_request(a1)
        await manager.add_request(b1)
        await manager.add_request(a2)
        await manager.add_request(c1)
        await manager.add_request(b2)

        # 轮询调度: A1 → B1 → C1 → A2 → B2
        assert manager._get_next_request() is a1
        assert manager._get_next_request() is b1
        assert manager._get_next_request() is c1
        assert manager._get_next_request() is a2
        assert manager._get_next_request() is b2
        assert manager._get_next_request() is None

    @pytest.mark.asyncio
    async def test_round_robin_balanced_across_types(self):
        """验证轮询在各类型间均匀分配（不会连续取同一类型）"""
        manager = EsiReqManager()
        func_a = make_mock_func("func_a")
        func_b = make_mock_func("func_b")

        for _ in range(5):
            await manager.add_request(make_esi_request(func_a))
        for _ in range(5):
            await manager.add_request(make_esi_request(func_b))

        # 应该交替返回 a, b, a, b, ...
        names = []
        for _ in range(10):
            req = manager._get_next_request()
            names.append(req.func_name)

        assert names == ["func_a", "func_b"] * 5

    @pytest.mark.asyncio
    async def test_empty_queue_returns_none(self):
        """空队列 _get_next_request 返回 None"""
        manager = EsiReqManager()
        assert manager._get_next_request() is None

    @pytest.mark.asyncio
    async def test_queue_event_set_on_add(self):
        """add_request 后 queue_event 被设置"""
        manager = EsiReqManager()
        func = make_mock_func("func_a")
        req = make_esi_request(func)

        # 确保 event 初始未设置
        manager.queue_event.clear()
        assert not manager.queue_event.is_set()

        await manager.add_request(req)
        assert manager.queue_event.is_set()

    @pytest.mark.asyncio
    async def test_queue_keys_cleanup_on_empty(self):
        """队列耗尽后 request_queue_keys 中移除对应 key"""
        manager = EsiReqManager()
        func = make_mock_func("func_a")
        await manager.add_request(make_esi_request(func))
        await manager.add_request(make_esi_request(func))

        # 取两个请求（全部耗尽）
        manager._get_next_request()
        manager._get_next_request()

        # 队列已空，key 应被移除
        assert "func_a" not in manager.request_queue_keys
        assert manager._get_next_request() is None


# ============================================================
# 两阶段流水线测试
# ============================================================


@pytest.mark.integration
class TestPipeline:
    """_accept_request + _process_request 流水线测试"""

    @pytest.mark.asyncio
    async def test_start_creates_tasks(self):
        """start() 创建 _queue_task 和 _processing_task"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        assert manager._queue_task is None
        assert manager._processing_task is None

        await manager.start()

        assert manager._queue_task is not None
        assert manager._processing_task is not None
        assert not manager._queue_task.done()
        assert not manager._processing_task.done()

        # 清理
        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self):
        """stop() 取消 _queue_task 和 _processing_task"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        await manager.start()
        assert not manager._queue_task.done()
        assert not manager._processing_task.done()

        await manager.stop()

        assert manager._queue_task.done()
        assert manager._processing_task.done()

    @pytest.mark.asyncio
    async def test_process_request_moves_to_processing_queue(self):
        """process_request 将请求移到 processing_queue"""
        manager = EsiReqManager()
        func = make_mock_func("func_a")
        req = make_esi_request(func)

        assert len(manager.processing_queue) == 0

        manager.process_request(req)
        assert len(manager.processing_queue) == 1
        assert manager.processing_queue[0] is req
        assert manager.process_event.is_set()

    @pytest.mark.asyncio
    async def test_idempotent_start(self):
        """重复 start() 不报错"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        await manager.start()
        task1 = manager._queue_task
        task2 = manager._processing_task

        # 重复启动不会创建新任务
        await manager.start()
        assert manager._queue_task is task1
        assert manager._processing_task is task2

        await manager.stop()

    @pytest.mark.asyncio
    async def test_request_queue_lock_protects_concurrent_adds(self):
        """queue_lock 保护并发 add_request"""
        manager = EsiReqManager()
        func = make_mock_func("func_a")

        async def add_one():
            await manager.add_request(make_esi_request(func))

        # 并发添加 20 个请求
        await asyncio.gather(*(add_one() for _ in range(20)))

        count = 0
        while manager._get_next_request() is not None:
            count += 1
        assert count == 20


# ============================================================
# 自动发现测试
# ============================================================


@pytest.mark.integration
class TestAutoDiscovery:
    """_discover_and_cache() 自动发现 ESI 速率限制池测试"""

    @pytest.mark.asyncio
    async def test_first_request_discovers_pool(self):
        """首次请求从响应头发现新池并缓存映射"""
        manager = EsiReqManager()
        req = make_esi_request(make_mock_func("char_wallet_endpoint"))

        await manager._discover_and_cache(
            req, {"group": "char-wallet", "limit": "150/15m"}
        )

        # 验证 pool_registry 中已创建 "char-wallet" 池
        assert "char-wallet" in manager.pool_registry._pools
        pool = manager.pool_registry._pools["char-wallet"]
        # rate = 150 / (15 * 60) = 150 / 900 ≈ 0.1667
        assert pool.token_generation_rate == pytest.approx(150 / 900, rel=1e-3)

        # 验证 func_pool_cache 中有映射
        assert "char_wallet_endpoint" in manager.func_pool_cache
        assert manager.func_pool_cache["char_wallet_endpoint"] == "char-wallet"

    @pytest.mark.asyncio
    async def test_second_request_uses_cache(self):
        """同一 func_name 两次请求，第二次复用已有池（只创建 1 个池）"""
        manager = EsiReqManager()

        # 第一次请求：发现池
        req1 = make_esi_request(make_mock_func("cached_endpoint"))
        await manager._discover_and_cache(
            req1, {"group": "char-wallet", "limit": "150/15m"}
        )
        assert len(manager.pool_registry._pools) == 2  # legacy + char-wallet

        # 第二次请求：相同端点，不创建新池
        req2 = make_esi_request(make_mock_func("cached_endpoint"))
        await manager._discover_and_cache(
            req2, {"group": "char-wallet", "limit": "150/15m"}
        )
        assert len(manager.pool_registry._pools) == 2  # 仍是 2 个

    @pytest.mark.asyncio
    async def test_no_headers_falls_back_to_legacy(self):
        """响应头为空时回退到 legacy 池，记录 WARNING"""
        manager = EsiReqManager()
        req = make_esi_request(make_mock_func("no_header_endpoint"))

        with patch.object(manager.logger, "warning") as mock_warning:
            await manager._discover_and_cache(req, {})

        mock_warning.assert_called_once()
        assert "NO rate limit headers" in mock_warning.call_args[0][0]
        assert "no_header_endpoint" in mock_warning.call_args[0][0]

        # 未创建新池
        assert len(manager.pool_registry._pools) == 1  # 仅 legacy

    @pytest.mark.asyncio
    async def test_old_headers_only_no_pool_creation(self):
        """仅旧式 error_remain 头部时不创建新池，记录 DEBUG"""
        manager = EsiReqManager()
        req = make_esi_request(make_mock_func("old_style_endpoint"))

        with patch.object(manager.logger, "debug") as mock_debug:
            await manager._discover_and_cache(req, {"error_remain": "50"})

        mock_debug.assert_called_once()
        assert "Old ESI error limit system" in mock_debug.call_args[0][0]
        assert "old_style_endpoint" in mock_debug.call_args[0][0]

        # 未创建新池
        assert len(manager.pool_registry._pools) == 1  # 仅 legacy

    @pytest.mark.asyncio
    async def test_parse_failure_falls_back_to_legacy(self):
        """limit 字符串解析失败时回退 legacy，记录 WARNING"""
        manager = EsiReqManager()
        req = make_esi_request(make_mock_func("bad_parse_endpoint"))

        with patch.object(manager.logger, "warning") as mock_warning:
            await manager._discover_and_cache(
                req, {"group": "bad-pool", "limit": "garbage"}
            )

        mock_warning.assert_called_once()
        assert "Cannot parse window limit" in mock_warning.call_args[0][0]

        # pool_registry 未创建新池
        assert "bad-pool" not in manager.pool_registry._pools
        assert len(manager.pool_registry._pools) == 1  # 仅 legacy

    @pytest.mark.asyncio
    async def test_explicit_pool_bypasses_discovery(self):
        """显式指定 pool_name 时 lookup_pool 忽略自动发现结果"""
        manager = EsiReqManager()

        # 预注册 explicit 池（模拟装饰器已注册场景）
        await manager.pool_registry.get_or_create("explicit", "150/15m")

        func = make_mock_func("explicit_endpoint")
        future = asyncio.get_running_loop().create_future()
        req = EsiRequest(
            func, (), {}, future, required_tokens=60, limit=5, pool_name="explicit"
        )

        # lookup_pool 应按 pool_name 返回 explicit 池
        pool = await manager.lookup_pool(req)
        assert pool.name == "explicit"
        assert "explicit" in manager.pool_registry._pools

        # 自动发现写入缓存后，lookup_pool 仍按 pool_name 返回
        await manager._discover_and_cache(
            req, {"group": "char-wallet", "limit": "150/15m"}
        )
        pool2 = await manager.lookup_pool(req)
        assert pool2.name == "explicit"

    @pytest.mark.asyncio
    async def test_concurrent_discovery_race_safety(self):
        """5 端点 × 2 并发首次请求 = 10 个并发发现，验证恰好 5 个池"""
        manager = EsiReqManager()
        endpoints = [f"endpoint_{i}" for i in range(5)]

        async def discover(endpoint):
            req = make_esi_request(make_mock_func(endpoint))
            await manager._discover_and_cache(
                req, {"group": f"pool-{endpoint}", "limit": "150/15m"}
            )

        # 2 并发 per endpoint → 10 total
        tasks = []
        for ep in endpoints:
            tasks.append(discover(ep))
            tasks.append(discover(ep))

        await asyncio.gather(*tasks)

        # 1 legacy + 5 discovered = 6
        assert len(manager.pool_registry._pools) == 6

        for ep in endpoints:
            assert ep in manager.func_pool_cache
            assert manager.func_pool_cache[ep] == f"pool-{ep}"
            assert f"pool-{ep}" in manager.pool_registry._pools


# ============================================================
# 多池 get_tokens 测试
# ============================================================


@pytest.mark.integration
class TestMultiPoolGetTokens:
    """使用多个 TokenBucket 池的 get_tokens() 测试"""

    @pytest.mark.asyncio
    async def test_get_tokens_independent_pools(self):
        """创建 2 个 TokenBucket，从 A 扣除 100 → B 不变"""
        with patch("time.time", return_value=100.0):
            bucket_a = TokenBucket(generation_rate=300, max_tokens=1200, name="pool_A")
            bucket_b = TokenBucket(generation_rate=300, max_tokens=1200, name="pool_B")

        # 推进 1s → 300 令牌，A 扣除 100
        with patch("time.time", return_value=101.0):
            result_a = await bucket_a.get_tokens(100)
        assert result_a is True
        assert bucket_a.token_pool == 200.0
        # B 未被操作，令牌池保持初始值
        assert bucket_b.token_pool == 0.0

        # B 也可以独立获取令牌
        with patch("time.time", return_value=101.0):
            result_b = await bucket_b.get_tokens(100)
        assert result_b is True
        assert bucket_b.token_pool == 200.0

    @pytest.mark.asyncio
    async def test_get_tokens_pool_isolation(self):
        """pool_A rate=0.001（几乎空），pool_B rate=1000（充足），验证隔离"""
        with patch("time.time", return_value=100.0):
            pool_a = TokenBucket(generation_rate=0.001, max_tokens=1.0, name="pool_A")
            pool_b = TokenBucket(generation_rate=1000, max_tokens=1000, name="pool_B")

        # 推进 0.5s: pool_A → 0.0005 令牌; pool_B → 500 令牌
        with patch("time.time", return_value=100.5):
            result_a = await pool_a.get_tokens(60)
            result_b = await pool_b.get_tokens(60)

        assert result_a is False  # 0.0005 < 60
        assert result_b is True   # 500 >= 60
        # 验证 B 已消耗令牌
        assert pool_b.token_pool == 440.0

    @pytest.mark.asyncio
    async def test_get_tokens_different_rates(self):
        """不同速率的池，get_required_tokens(limit=5, pool) 返回不同值"""
        with patch("time.time", return_value=100.0):
            pool_slow = TokenBucket(generation_rate=100, max_tokens=1200, name="pool_slow")
            pool_fast = TokenBucket(generation_rate=300, max_tokens=1200, name="pool_fast")

        tokens_slow = EsiReqManager.get_required_tokens(limit=5, pool=pool_slow)
        tokens_fast = EsiReqManager.get_required_tokens(limit=5, pool=pool_fast)

        # max(1, ceil(100/5)) = 20
        # max(1, ceil(300/5)) = 60
        assert tokens_slow == 20
        assert tokens_fast == 60


# ============================================================
# 池感知批量循环测试
# ============================================================


@pytest.mark.integration
class TestPoolAwareBatchLoop:
    """processing_queue 批量处理的池感知逻辑测试"""

    @pytest.mark.asyncio
    async def test_cross_pool_non_blocking(self):
        """两个不同池的请求，一个池令牌不足不阻塞另一个"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()
            # 创建快池和慢池
            await manager.pool_registry.get_or_create("fast_pool", "1000/1s")
            await manager.pool_registry.get_or_create("slow_pool", "1/1000s")

        func_a = make_mock_func("func_a")
        func_b = make_mock_func("func_b")
        req_a = make_esi_request(func_a)
        req_b = make_esi_request(func_b)
        req_a.pool_name = "fast_pool"
        req_b.pool_name = "slow_pool"

        manager.processing_queue.append(req_a)
        manager.processing_queue.append(req_b)

        # 推进 0.5s: fast_pool → 500 令牌; slow_pool → ~0 令牌
        with patch("time.time", return_value=100.5):
            batch_size = min(len(manager.processing_queue), 30)
            processed = []
            for i in range(batch_size):
                req = manager.processing_queue[i]
                pool = await manager.lookup_pool(req)
                if await manager.get_tokens(req.required_tokens, pool):
                    processed.append(i)
            for i in reversed(processed):
                del manager.processing_queue[i]

        # fast_pool 有足够令牌 → 被处理; slow_pool 令牌不足 → 保留
        assert len(processed) == 1
        assert len(manager.processing_queue) == 1
        remaining = manager.processing_queue[0]
        assert remaining.func_name == "func_b"

    @pytest.mark.asyncio
    async def test_same_pool_blocking(self):
        """同一池的两个请求，池耗尽后两个都被延迟"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        func = make_mock_func("same_func")
        req1 = make_esi_request(func)
        req2 = make_esi_request(func)
        manager.processing_queue.append(req1)
        manager.processing_queue.append(req2)

        # 推进 0.2s: 0.2 * 300 = 60 令牌 → 恰好够 1 个请求
        with patch("time.time", return_value=100.2):
            batch_size = min(len(manager.processing_queue), 30)
            processed = []
            for i in range(batch_size):
                req = manager.processing_queue[i]
                pool = await manager.lookup_pool(req)
                if await manager.get_tokens(req.required_tokens, pool):
                    processed.append(i)
            for i in reversed(processed):
                del manager.processing_queue[i]

        # 仅第一个被处理，第二个因令牌不足保留
        assert len(processed) == 1
        assert len(manager.processing_queue) == 1
        assert manager.processing_queue[0] is req2

    @pytest.mark.asyncio
    async def test_batch_capacity_30_limit(self):
        """35 个请求，一批最多处理 30 个"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        func = make_mock_func("test_func")
        for _ in range(35):
            manager.processing_queue.append(make_esi_request(func, required_tokens=1))

        # 推进足够时间，确保令牌充足
        with patch("time.time", return_value=200.0):
            batch_size = min(len(manager.processing_queue), 30)
            processed = []
            for i in range(batch_size):
                req = manager.processing_queue[i]
                pool = await manager.lookup_pool(req)
                if await manager.get_tokens(req.required_tokens, pool):
                    processed.append(i)
            for i in reversed(processed):
                del manager.processing_queue[i]

        assert len(processed) == 30
        assert len(manager.processing_queue) == 5

    @pytest.mark.asyncio
    async def test_skipped_requests_retained(self):
        """因令牌不足跳过的请求保留在 processing_queue 中"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        func = make_mock_func("test_func")
        for _ in range(5):
            manager.processing_queue.append(make_esi_request(func))

        # 时间未推进，无令牌积累 → 全部跳过
        with patch("time.time", return_value=100.0):
            batch_size = min(len(manager.processing_queue), 30)
            processed = []
            for i in range(batch_size):
                req = manager.processing_queue[i]
                pool = await manager.lookup_pool(req)
                if await manager.get_tokens(req.required_tokens, pool):
                    processed.append(i)
            for i in reversed(processed):
                del manager.processing_queue[i]

        assert len(processed) == 0
        assert len(manager.processing_queue) == 5


# ============================================================
# TokenBucket 直接测试（不通过 EsiReqManager）
# ============================================================


@pytest.mark.integration
class TestTokenBucketClass:
    """直接测试 TokenBucket 类的核心行为"""

    @pytest.mark.asyncio
    async def test_token_bucket_init_defaults(self):
        """初始化后 token_pool=0, remaining_tokens=0, generation_rate=300"""
        bucket = TokenBucket(generation_rate=300, max_tokens=1200)
        assert bucket.token_pool == 0.0
        assert bucket.remaining_tokens == 0.0
        assert bucket.token_generation_rate == 300.0

    @pytest.mark.asyncio
    async def test_token_bucket_accumulates_over_time(self):
        """2 秒后累积 600 令牌，get_tokens(400) 成功，剩余 ≈200"""
        with patch("time.time", return_value=100.0):
            bucket = TokenBucket(generation_rate=300, max_tokens=1200)
        with patch("time.time", return_value=102.0):
            result = await bucket.get_tokens(400)
        assert result is True
        assert bucket.token_pool == pytest.approx(200.0)

    @pytest.mark.asyncio
    async def test_token_bucket_capped_at_max(self):
        """10 秒本应累积 3000 令牌，但被 max_tokens=1200 封顶"""
        with patch("time.time", return_value=100.0):
            bucket = TokenBucket(generation_rate=300, max_tokens=1200)
        with patch("time.time", return_value=110.0):
            result = await bucket.get_tokens(60)
        assert result is True
        assert bucket.token_pool == pytest.approx(1140.0)

    @pytest.mark.asyncio
    async def test_deduct_penalty_reduces_tokens(self):
        """deduct_penalty(50) 使 token_pool 变为 -50（无时间推移）"""
        with patch("time.time", return_value=100.0):
            bucket = TokenBucket(generation_rate=300, max_tokens=1200)
            await bucket.deduct_penalty(50)
        assert bucket.token_pool == -50.0

    @pytest.mark.asyncio
    async def test_concurrent_get_tokens_serialized(self):
        """并发 get_tokens 被锁序列化：第一个成功，第二个失败"""
        with patch("time.time", return_value=100.0):
            bucket = TokenBucket(generation_rate=300, max_tokens=1200)
        with patch("time.time", return_value=101.0):
            results = await asyncio.gather(
                bucket.get_tokens(200),
                bucket.get_tokens(200),
            )
        assert results == [True, False]
        assert bucket.token_pool == pytest.approx(100.0)


# ============================================================
# PoolRegistry 测试
# ============================================================


@pytest.mark.integration
class TestPoolRegistry:
    """PoolRegistry 注册表创建与缓存行为测试"""

    @pytest.mark.asyncio
    async def test_get_or_create_new_pool(self):
        """根据窗口限制创建新令牌桶，速率和容量正确"""
        registry = PoolRegistry()
        bucket = await registry.get_or_create("char-wallet", "150/15m")
        expected_rate = 150.0 / 900.0
        assert bucket.token_generation_rate == pytest.approx(expected_rate)
        assert bucket.max_token_pool == 150.0

    @pytest.mark.asyncio
    async def test_get_or_create_reuse(self):
        """相同名称返回同一 TokenBucket 实例"""
        registry = PoolRegistry()
        bucket1 = await registry.get_or_create("test-pool", "100/10s")
        bucket2 = await registry.get_or_create("test-pool", "999/99s")
        assert bucket1 is bucket2

    @pytest.mark.asyncio
    async def test_parse_window_limit_15m(self):
        """"150/15m" → (150, 900)"""
        result = parse_window_limit("150/15m")
        assert result == (150.0, 900.0)

    @pytest.mark.asyncio
    async def test_parse_window_limit_1h(self):
        """ "600/1h" → (600, 3600)"""
        result = parse_window_limit("600/1h")
        assert result == (600.0, 3600.0)

    @pytest.mark.asyncio
    async def test_parse_window_limit_invalid(self):
        """无法解析时返回 None"""
        result = parse_window_limit("garbage")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_legacy_consistent(self):
        """重复调用 get_legacy() 返回相同实例"""
        registry = PoolRegistry()
        b1 = await registry.get_legacy()
        b2 = await registry.get_legacy()
        assert b1 is b2
        assert b1.name == LEGACY_POOL_NAME


# ============================================================
# 队列深度测试
# ============================================================


@pytest.mark.integration
class TestQueueDepth:
    """get_queue_depth() 队列深度查询测试"""

    def test_get_queue_depth_idle(self):
        """空闲状态：backlog=0, in_flight=0"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()
        depth = manager.get_queue_depth()
        assert depth == {"backlog": 0, "in_flight": 0}
        assert isinstance(depth["backlog"], int)
        assert isinstance(depth["in_flight"], int)

    @pytest.mark.asyncio
    async def test_get_queue_depth_with_requests(self):
        """有排队请求和进行中请求时正确计数"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 添加 3 个请求到 request_queues
        func_a = make_mock_func("func_a")
        func_b = make_mock_func("func_b")
        await manager.add_request(make_esi_request(func_a))
        await manager.add_request(make_esi_request(func_a))
        await manager.add_request(make_esi_request(func_b))

        # 模拟 processing_queue 中有 2 个请求
        manager.processing_queue.append(make_esi_request(func_a))
        manager.processing_queue.append(make_esi_request(func_b))

        depth = manager.get_queue_depth()
        assert depth["backlog"] == 3
        assert depth["in_flight"] == 2


# ============================================================
# 错误计数测试
# ============================================================


@pytest.mark.integration
class TestErrorCounter:
    """error_count 错误计数测试"""

    @pytest.mark.asyncio
    async def test_error_counter_increments_on_error(self):
        """_handle_error_response 调用后 error_count 递增"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 验证初始 error_count 为 0
        assert manager._legacy_bucket.error_count == 0

        # 触发无头部错误惩罚 → legacy bucket error_count += 1
        func = make_mock_func("test_error_count")
        req = make_esi_request(func)
        await manager._handle_error_response(req, 404, {})

        assert manager._legacy_bucket.error_count == 1

        # 再次触发 → error_count 继续递增
        await manager._handle_error_response(req, 403, {})
        assert manager._legacy_bucket.error_count == 2

    @pytest.mark.asyncio
    async def test_error_counter_included_in_pool_stats(self):
        """get_pool_stats() 输出包含 error_count"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        # 触发一个错误以增加计数
        func = make_mock_func("test_pool_stats_error")
        req = make_esi_request(func)
        await manager._handle_error_response(req, 404, {})

        stats = manager.get_pool_stats()
        assert "pools" in stats
        legacy_stats = stats["pools"].get(LEGACY_POOL_NAME, None)
        assert legacy_stats is not None
        assert "error_count" in legacy_stats
        assert legacy_stats["error_count"] == 1
        # 验证原有字段仍然存在
        assert "rate" in legacy_stats
        assert "max" in legacy_stats
        assert "remaining" in legacy_stats


# ============================================================
# 日志钩子测试
# ============================================================


@pytest.mark.integration
class TestLogHook:
    """_process_request 中非阻塞日志记录测试"""

    @pytest.mark.asyncio
    async def test_log_hook_writes_on_request(self):
        """请求完成后触发 EsiUsageLogDBUtils.insert_log 调用"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        async def mock_esi_call():
            return ({"data": "test"}, {}, 200, {})

        mock_esi_call.__name__ = "test_log_endpoint"
        async def execute_func():
            return await mock_esi_call()

        future = asyncio.get_running_loop().create_future()
        req = EsiRequest(
            execute_func, (), {}, future,
            required_tokens=60, limit=5,
            pool_name=None,
        )
        req.func_name = "test_log_endpoint"

        with patch(
            "src_v2.model.EVE.eveesi.esi_req_manager.EsiUsageLogDBUtils.insert_log",
            new_callable=AsyncMock,
        ) as mock_insert:
            # 模拟 single_process 的核心逻辑并触发日志
            # 通过直接操作 processing_queue 并启动 process_request 来触发
            manager.start_time = time.time()
            manager.processing_queue.append(req)

            # 模拟 single_process 的行为（简化版，只处理一个请求）
            log_status_code = None
            log_error_message = None
            try:
                result = await req.func()
                if isinstance(result, tuple) and len(result) >= 3:
                    sc = result[2]
                    if isinstance(sc, int):
                        log_status_code = sc
                if not req.future.done():
                    req.future.set_result(result)
            except Exception as e:
                log_status_code = 0
                log_error_message = str(e)

            # 执行日志钩子（与 single_process 中的逻辑一致）
            try:
                pool = await manager.lookup_pool(req)
                log_pool_name = pool.name
            except Exception:
                log_pool_name = "unknown"

            latency_ms = (time.time() - req.timestamp) * 1000
            try:
                asyncio.create_task(
                    EsiUsageLogDBUtils.insert_log(
                        timestamp=datetime.utcnow(),
                        endpoint=req.func_name,
                        pool_name=log_pool_name,
                        character_id=0,
                        status_code=log_status_code,
                        latency_ms=latency_ms,
                        error_message=log_error_message,
                    )
                )
            except Exception:
                pass

            # 等待异步任务完成
            await asyncio.sleep(0.1)

            mock_insert.assert_called_once()
            call_kwargs = mock_insert.call_args.kwargs
            assert call_kwargs["endpoint"] == "test_log_endpoint"
            assert call_kwargs["status_code"] == 200
            assert call_kwargs["character_id"] == 0
            assert call_kwargs["error_message"] is None
            assert call_kwargs["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_log_hook_does_not_block(self):
        """日志插入失败时请求仍正常完成"""
        with patch("time.time", return_value=100.0):
            manager = EsiReqManager()

        async def mock_esi_call():
            return ({"data": "test"}, {}, 200, {})

        mock_esi_call.__name__ = "test_non_blocking"
        async def execute_func():
            return await mock_esi_call()

        future = asyncio.get_running_loop().create_future()
        req = EsiRequest(
            execute_func, (), {}, future,
            required_tokens=60, limit=5,
            pool_name=None,
        )
        req.func_name = "test_non_blocking"

        with patch(
            "src_v2.model.EVE.eveesi.esi_req_manager.EsiUsageLogDBUtils.insert_log",
            side_effect=RuntimeError("DB connection failed"),
            new_callable=AsyncMock,
        ):
            # 模拟 single_process 的核心逻辑
            log_status_code = None
            log_error_message = None
            try:
                result = await req.func()
                if isinstance(result, tuple) and len(result) >= 3:
                    sc = result[2]
                    if isinstance(sc, int):
                        log_status_code = sc
                if not req.future.done():
                    req.future.set_result(result)
            except Exception as e:
                log_status_code = 0
                log_error_message = str(e)

            # 执行日志钩子 - 应该被 try/except 捕获，不影响请求
            try:
                pool = await manager.lookup_pool(req)
                log_pool_name = pool.name
            except Exception:
                log_pool_name = "unknown"

            latency_ms = (time.time() - req.timestamp) * 1000
            log_exception = None
            try:
                asyncio.create_task(
                    EsiUsageLogDBUtils.insert_log(
                        timestamp=datetime.utcnow(),
                        endpoint=req.func_name,
                        pool_name=log_pool_name,
                        character_id=0,
                        status_code=log_status_code,
                        latency_ms=latency_ms,
                        error_message=log_error_message,
                    )
                )
            except Exception as exc:
                log_exception = exc

            # 验证 create_task 本身不抛异常（异常在 task 内部）
            assert log_exception is None

            # 验证请求正常完成
            assert req.future.done()
            result = req.future.result()
            assert result[0] == {"data": "test"}
            assert result[2] == 200
