import time
import math
import re
import asyncio
import contextvars
from collections import deque, defaultdict
from datetime import datetime
from functools import wraps
from typing import Callable, Dict, Optional, Tuple, TypedDict

from src_v2.core.log import logger
from src_v2.core.database.kahuna_database_utils_v2 import EsiUsageLogDBUtils

# 定义请求对象类型
class EsiRequest:
    def __init__(self, func: Callable, args: Tuple, kwargs: Dict, future: asyncio.Future, required_tokens: int = 60, limit: int = 5, pool_name: str = None):
        self.func = func  # ESI函数
        self.func_name = func.__name__  # 函数名称
        self.args = args  # 位置参数
        self.kwargs = kwargs  # 关键字参数
        self.future = future  # 用于返回结果的Future对象
        self.timestamp = time.time()  # 请求创建时间
        self.required_tokens = required_tokens  # 该请求需要的令牌数量
        self.limit = limit  # 该接口的限速值（每秒请求上限）
        self.pool_name = pool_name  # 该请求所属的令牌池名称


class TokenBucket:
    """令牌桶，用于 ESI 请求速率限制"""

    def __init__(self, generation_rate: float, max_tokens: float, name: str = ""):
        self.token_pool = 0.0  # 当前可用令牌数
        self.token_generation_rate = generation_rate  # 每秒产生的令牌数
        self.max_token_pool = max_tokens  # 令牌池最大容量
        self.last_token_update_time = time.time()  # 上次更新令牌的时间戳
        self.lock = asyncio.Lock()  # 保护令牌池操作的锁
        self.name = name  # 令牌桶名称
        self.error_count = 0  # 错误计数（非2xx/3xx响应次数）
        self._reported_remaining: Optional[int] = None  # ESI 响应头 X-Ratelimit-Remaining 的真实值
        self._reported_remaining_reset: Optional[float] = None  # ESI 响应头 X-Ratelimit-Reset 的窗口重置时间戳

    @property
    def remaining_tokens(self) -> float:
        """返回当前剩余令牌数"""
        return self.token_pool

    async def get_tokens(self, required_tokens: int) -> bool:
        """
        获取指定数量的令牌，如果令牌不足则返回False
        令牌按时间连续累积，每秒产生generation_rate个令牌
        返回: True表示获取成功并已消耗令牌，False表示令牌不足
        """
        # For pools with real ESI remaining data, use header-based check
        # with local deduction to prevent bursts of requests between ESI updates
        if self._reported_remaining is not None:
            # 窗口过期检查：防止 _reported_remaining 长时间不更新导致令牌桶死锁
            if self._reported_remaining_reset is not None and time.time() >= self._reported_remaining_reset:
                logger.info(
                    f"令牌池 '{self.name}' ESI 窗口已过期 "
                    f"(reset={self._reported_remaining_reset:.0f}), "
                    f"重置 _reported_remaining，回退到时间累积模式"
                )
                self._reported_remaining = None
                self._reported_remaining_reset = None
                # 不回 return，继续往下走时间累积路径
            else:
                if self._reported_remaining >= required_tokens:
                    self._reported_remaining -= required_tokens
                    return True
                return False
        # No ESI data yet (legacy pool, test pool, or first request to new pool):
        # fall through to existing TokenBucket simulation
        async with self.lock:
            current_time = time.time()

            # 计算自上次更新以来的时间差
            time_passed = current_time - self.last_token_update_time

            # 根据时间差累积令牌（不超过最大容量）
            tokens_to_add = time_passed * self.token_generation_rate
            token_pool_before = self.token_pool
            self.token_pool = min(self.max_token_pool, self.token_pool + tokens_to_add)
            self.last_token_update_time = current_time

            # Debug日志：记录令牌获取过程
            logger.debug(
                f"获取令牌请求: 需要 {required_tokens} 个, "
                f"时间差 {time_passed:.3f}s, "
                f"累积 {tokens_to_add:.2f} 个, "
                f"令牌池: {token_pool_before:.2f} -> {self.token_pool:.2f} (最大 {self.max_token_pool})"
            )

            # 检查是否有足够的令牌
            if self.token_pool >= required_tokens:
                # 立即消耗令牌
                self.token_pool -= required_tokens
                logger.debug(
                    f"令牌获取成功: 消耗 {required_tokens} 个, "
                    f"剩余令牌池: {self.token_pool:.2f}"
                )
                return True

            # 令牌不足
            tokens_needed = required_tokens - self.token_pool
            logger.debug(
                f"令牌获取失败: 需要 {required_tokens} 个, "
                f"当前可用 {self.token_pool:.2f} 个, "
                f"还差 {tokens_needed:.2f} 个, "
                f"预计等待时间: {tokens_needed / self.token_generation_rate:.2f}s"
            )
            return False

    async def deduct_penalty(self, penalty_tokens: int = 220):
        """
        扣除惩罚令牌，用于防止触发ESI错误速率限制
        参数:
            penalty_tokens: 惩罚令牌数量，默认220
        """
        async with self.lock:
            # 更新令牌池（先累积令牌）
            current_time = time.time()
            time_passed = current_time - self.last_token_update_time
            tokens_to_add = time_passed * self.token_generation_rate
            token_pool_before = self.token_pool
            self.token_pool = min(self.max_token_pool, self.token_pool + tokens_to_add)
            token_pool_after_update = self.token_pool
            self.last_token_update_time = current_time

            # 扣除惩罚令牌（允许为负数，表示需要等待更长时间）
            self.token_pool -= penalty_tokens

            # Debug日志：记录错误惩罚过程
            logger.debug(
                f"错误惩罚: 扣除 {penalty_tokens} 个令牌, "
                f"时间差 {time_passed:.3f}s, "
                f"累积 {tokens_to_add:.2f} 个, "
                f"令牌池: {token_pool_before:.2f} -> {token_pool_after_update:.2f} -> {self.token_pool:.2f}"
            )

    def sync_from_esi_headers(self, rate_limit_info: dict):
        """从 ESI 响应头同步 remaining 和窗口重置时间戳

        调用时机：每次收到 ESI 响应（成功、429、5XX、4XX）时调用，
        确保 _reported_remaining_reset 始终反映 ESI 服务端的真实窗口边界，
        防止本地缓存过期导致令牌桶死锁。
        """
        if rate_limit_info.get("remaining") is not None:
            try:
                self._reported_remaining = int(rate_limit_info["remaining"])
            except (ValueError, TypeError):
                pass

        if rate_limit_info.get("reset") is not None:
            try:
                self._reported_remaining_reset = float(rate_limit_info["reset"])
            except (ValueError, TypeError):
                pass
        elif self._reported_remaining_reset is None and self._reported_remaining is not None:
            # 首次同步但 ESI 未返回 reset 头（极少数老端点），用池参数估算窗口时长
            if self.token_generation_rate > 0:
                window_seconds = self.max_token_pool / self.token_generation_rate
                self._reported_remaining_reset = time.time() + window_seconds


class RateLimitInfo(TypedDict, total=False):
    """ESI 速率限制响应头信息"""
    group: str
    limit: str
    remaining: int
    used: int
    reset: int
    error_remain: int
    error_reset: int
    retry_after: int


LEGACY_POOL_NAME = "__legacy__"

# Per-task rate limit info (avoids race between concurrent ESI responses)
rate_limit_ctx = contextvars.ContextVar('esi_rate_limit_info', default=None)


def parse_window_limit(limit_str: str) -> Optional[Tuple[float, float]]:
    """解析窗口限制字符串

    例如: "150/15m" → (150, 900), "600/1h" → (600, 3600)
    后缀: s=秒, m=分(×60), h=小时(×3600), d=天(×86400)

    Returns:
        (tokens, window_seconds) 元组，解析失败返回 None
    """
    if not limit_str or not isinstance(limit_str, str):
        return None

    match = re.fullmatch(r'(\d+)/(\d+)([smhd])?', limit_str.strip())
    if not match:
        return None

    tokens = float(match.group(1))
    value = float(match.group(2))
    unit = match.group(3) or 's'

    multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    multiplier = multipliers.get(unit)
    if multiplier is None:
        return None

    return (tokens, value * multiplier)


class PoolRegistry:
    """管理多个 TokenBucket 池的注册表"""

    def __init__(self):
        self._pools: dict[str, TokenBucket] = {}
        self._pool_lock: asyncio.Lock = asyncio.Lock()

    async def get_or_create(self, group_name: str, window_limit: Optional[str] = None) -> TokenBucket:
        """获取或创建指定组的令牌桶"""
        if group_name in self._pools:
            return self._pools[group_name]

        async with self._pool_lock:
            if group_name in self._pools:
                return self._pools[group_name]

            if group_name == LEGACY_POOL_NAME and window_limit is None:
                bucket = TokenBucket(generation_rate=300, max_tokens=1200, name=LEGACY_POOL_NAME)
                self._pools[group_name] = bucket
                return bucket

            if window_limit is None:
                # Explicit pool without window limit — use default params
                bucket = TokenBucket(generation_rate=300, max_tokens=1200, name=group_name)
                self._pools[group_name] = bucket
                logger.info(f"Discovered new pool '{group_name}' (default params)")
                return bucket

            if window_limit:
                parsed = parse_window_limit(window_limit)
                if parsed:
                    tokens, window_seconds = parsed
                    rate = tokens / window_seconds if window_seconds > 0 else tokens
                    bucket = TokenBucket(generation_rate=rate, max_tokens=tokens, name=group_name)
                    self._pools[group_name] = bucket
                    logger.info(f"Discovered new pool '{group_name}' ({tokens}/{window_limit})")
                    return bucket

            logger.warning(
                f"Cannot parse window limit '{window_limit}' for pool "
                f"'{group_name}', falling back to legacy"
            )

        return await self.get_legacy()

    async def get_legacy(self) -> TokenBucket:
        """获取传统令牌桶（自动创建）"""
        if LEGACY_POOL_NAME not in self._pools:
            async with self._pool_lock:
                if LEGACY_POOL_NAME not in self._pools:
                    bucket = TokenBucket(generation_rate=300, max_tokens=1200, name=LEGACY_POOL_NAME)
                    self._pools[LEGACY_POOL_NAME] = bucket
        return self._pools[LEGACY_POOL_NAME]

    def get_stats(self) -> dict:
        """返回所有池的统计信息"""
        return {
            "pools": {
                name: {
                    "rate": bucket.token_generation_rate,
                    "max": bucket.max_token_pool,
                    "remaining": bucket._reported_remaining if bucket._reported_remaining is not None else bucket.remaining_tokens,
                    "reset": bucket._reported_remaining_reset,
                    "error_count": bucket.error_count,
                }
                for name, bucket in self._pools.items()
            }
        }


class EsiReqManager:
    def __init__(self):
        # 使用字典存储不同函数类型的请求队列，实现轮询调度
        self.request_queues = defaultdict(deque)  # {func_name: deque([reqs])}
        self.request_queue_keys = deque()  # 改为 deque，用于轮询
        self.processing_queue = deque()
        self.queue_event = asyncio.Event()  # 用于通知队列处理协程有新请求
        self.process_event = asyncio.Event()
        self.queue_lock = asyncio.Lock()  # 保护队列操作的锁
        
        # 令牌池注册表与缓存
        self.pool_registry = PoolRegistry()
        self._legacy_bucket = TokenBucket(generation_rate=300, max_tokens=1200, name=LEGACY_POOL_NAME)
        self.pool_registry._pools[LEGACY_POOL_NAME] = self._legacy_bucket
        self.func_pool_cache: dict[str, str] = {}  # func_name → pool_group_name
        self.func_pool_lock = asyncio.Lock()  # 保护缓存写入
        self._missing_headers_endpoints: set[str] = set()
        # 日志
        self.logger = logger
        
        # 启动队列处理协程
        self._queue_task = None
        self._processing_task = None

    # 向后兼容属性（委托到遗留令牌桶）
    @property
    def token_pool(self) -> float:
        return self._legacy_bucket.remaining_tokens

    @property
    def token_generation_rate(self) -> float:
        return self._legacy_bucket.token_generation_rate

    @property
    def max_token_pool(self) -> float:
        return self._legacy_bucket.max_token_pool

    @property
    def last_token_update_time(self) -> float:
        return self._legacy_bucket.last_token_update_time

    async def start(self):
        """启动请求处理协程"""
        if self._queue_task is None or self._queue_task.done():
            self._queue_task = asyncio.create_task(self._accept_request())
            self.logger.info("ESI请求队列处理协程已启动")
        if self._processing_task is None or self._processing_task.done():
            self._processing_task = asyncio.create_task(self._process_request())
            self.logger.info("ESI处理队列处理协程已启动")
        self.logger.info(
            f"ESI Multi-Pool Manager started. "
            f"Legacy pool: {self.token_generation_rate}/s, max {self.max_token_pool}. "
            f"Auto-discovery enabled."
        )

    async def stop(self):
        """停止请求处理协程"""
        # 先停止处理任务，因为它可能依赖队列任务
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
            self.logger.info("ESI处理队列处理协程已停止")
        
        # 然后停止队列任务
        if self._queue_task and not self._queue_task.done():
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass
            self.logger.info("ESI请求队列处理协程已停止")

    async def get_tokens(self, required_tokens: int, pool: TokenBucket = None) -> bool:
        """
        获取指定数量的令牌，如果令牌不足则返回False
        令牌按时间连续累积，每秒产生token_generation_rate个令牌
        参数:
            required_tokens: 需要的令牌数量
            pool: 目标令牌池，为None时使用遗留令牌桶（向后兼容旧调用方）
        返回: True表示获取成功并已消耗令牌，False表示令牌不足
        """
        if pool is None:
            pool = self._legacy_bucket
        return await pool.get_tokens(required_tokens)
    
    async def deduct_error_penalty(self, penalty_tokens: int = 220):
        """DEPRECATED: use deduct_error_penalty_legacy instead."""
        return await self.deduct_error_penalty_legacy(penalty_tokens)

    async def deduct_error_penalty_legacy(self, penalty_tokens: int = 220):
        """
        扣除错误惩罚令牌，用于防止触发ESI错误速率限制
        当检测到非2xx/3xx响应时，扣除惩罚令牌以延后后续请求
        参数:
            penalty_tokens: 惩罚令牌数量，默认220（60 * 300 / 100，向上取整）
        """
        await self._legacy_bucket.deduct_penalty(penalty_tokens)
        # Warning日志：记录错误响应
        self.logger.warning(
            f"检测到ESI错误响应，扣除 {penalty_tokens} 个令牌，"
            f"当前令牌池: {self.token_pool:.2f}, "
            f"预计恢复时间: {max(0, -self.token_pool) / self.token_generation_rate:.2f}s"
        )

    async def lookup_pool(self, req: EsiRequest) -> TokenBucket:
        """根据请求查找或创建对应的令牌池"""
        if req.pool_name is not None:
            # 显式指定池名称
            return await self.pool_registry.get_or_create(req.pool_name)

        if req.func_name in self.func_pool_cache:
            # 缓存命中
            return await self.pool_registry.get_or_create(self.func_pool_cache[req.func_name])

        # 回退到遗留令牌桶
        return self._legacy_bucket

    async def _discover_and_cache(self, req: EsiRequest, rate_limit_info: dict):
        """从响应头自动发现并缓存 ESI 速率限制池

        仅在成功响应（状态码 200-399）时由调用方触发，避免缓存错误响应的瞬态头。
        """
        async with self.func_pool_lock:
            if rate_limit_info.get("group") is not None:
                group = rate_limit_info["group"]
                pool = await self.pool_registry.get_or_create(group, rate_limit_info.get("limit"))
                if req.func_name not in self.func_pool_cache:
                    self.func_pool_cache[req.func_name] = group
                    self.logger.info(
                        f"🆕 New ESI rate limit pool: '{group}' — "
                        f"{rate_limit_info.get('limit')} — discovered via {req.func_name}"
                    )
                # Always update real remaining from ESI response header
                pool.sync_from_esi_headers(rate_limit_info)
            elif rate_limit_info.get("error_remain") is not None:
                self.logger.debug(
                    f"Old ESI error limit system detected for '{req.func_name}': "
                    f"{rate_limit_info.get('error_remain')} remaining"
                )
            else:
                self._missing_headers_endpoints.add(req.func_name)
                self.logger.warning(
                    f"⚠️ ESI endpoint '{req.func_name}' returned NO rate limit headers. "
                    f"Using LEGACY pool."
                )

    async def _handle_error_response(self, req: EsiRequest, status_code: int, rate_limit_info: dict):
        """处理错误响应，根据ESI限速系统类型应用不同的惩罚策略。

        策略:
          - 429: 速率限制响应，不扣除惩罚（ESI已限制该端点）
          - 5XX: 服务器错误，不扣除惩罚（ESI docs: 0 tokens）
          - 新系统 (X-Ratelimit-Group): 按池容量比例扣除
          - 旧系统 (X-ESI-Error-Limit-Remain): 扣除遗留桶220惩罚
          - 无头部: 扣除遗留桶220惩罚
        """
        # 429 速率限制 — 不惩罚（但计入错误计数）
        if isinstance(status_code, int) and status_code == 429:
            group = rate_limit_info.get("group", "unknown")
            retry = rate_limit_info.get("retry_after", "unknown")
            self.logger.info(f"429 rate limited on pool '{group}', Retry-After: {retry}")
            pool = await self.lookup_pool(req)
            pool.error_count += 1
            # Sync reported_remaining from ESI header (429 usually means remaining=0)
            if pool._reported_remaining is not None:
                pool.sync_from_esi_headers(rate_limit_info)
                if pool._reported_remaining is None:  # remaining 解析失败，手动设 0
                    pool._reported_remaining = 0
            return

        # 5XX 服务器错误 — 不惩罚（但计入错误计数）
        if isinstance(status_code, int) and 500 <= status_code < 600:
            pool = await self.lookup_pool(req)
            pool.error_count += 1
            # Sync reported_remaining from ESI header if available
            if pool._reported_remaining is not None:
                pool.sync_from_esi_headers(rate_limit_info)
            return

        # 新系统头部存在 — 按池惩罚（仅遗留池扣惩罚，已发现池让 ESI 自行限速）
        if rate_limit_info.get("group") is not None:
            pool = await self.lookup_pool(req)
            pool.error_count += 1
            if pool._reported_remaining is None:
                penalty = min(220, pool.max_token_pool * 0.2)
                await pool.deduct_penalty(penalty)
                self.logger.warning(
                    f"检测到ESI错误响应，状态码: {status_code}，"
                    f"已扣除 {penalty:.0f} 惩罚令牌 (池: {pool.name})"
                )
            else:
                # Discovered pool: sync from ESI header (the source of truth)
                if rate_limit_info.get("remaining") is not None:
                    pool.sync_from_esi_headers(rate_limit_info)
                else:
                    pool._reported_remaining = max(0, pool._reported_remaining - 5)
                self.logger.warning(
                    f"ESI error response on discovered pool '{pool.name}', "
                    f"status: {status_code}"
                )
            return

        # 旧系统头部存在 — 遗留桶惩罚
        if rate_limit_info.get("error_remain") is not None:
            remain = int(rate_limit_info["error_remain"])
            if remain < 20:
                self.logger.warning(f"ESI error limit low: {remain} remaining")
            self._legacy_bucket.error_count += 1
            await self._legacy_bucket.deduct_penalty(220)
            self.logger.warning(
                f"检测到ESI错误响应，状态码: {status_code}，已扣除惩罚令牌"
            )
            return

        # 无任何头部 — 遗留桶惩罚
        self._legacy_bucket.error_count += 1
        await self._legacy_bucket.deduct_penalty(220)
        self.logger.warning(f"检测到ESI错误响应，状态码: {status_code}，已扣除惩罚令牌")

    @staticmethod
    def get_required_tokens(limit: int, pool: TokenBucket) -> int:
        """计算给定限速和令牌池所需的令牌数"""
        return max(1, math.ceil(pool.token_generation_rate / limit))

    def get_missing_header_endpoints(self) -> list[str]:
        """返回缺少 ESI 速率限制头的端点列表"""
        return sorted(self._missing_headers_endpoints)

    def get_pool_stats(self) -> dict:
        """返回所有池的完整诊断信息"""
        return {
            "pools": self.pool_registry.get_stats()["pools"],
            "func_mappings": dict(self.func_pool_cache),
            "missing_headers": self.get_missing_header_endpoints(),
        }

    def get_queue_depth(self) -> dict:
        """返回请求队列深度信息"""
        backlog = sum(len(q) for q in self.request_queues.values())
        in_flight = len(self.processing_queue)
        return {"backlog": backlog, "in_flight": in_flight}

    async def add_request(self, req: EsiRequest):
        """添加请求到队列（按函数名分组）"""
        import time as _t
        req._enqueue_time = _t.monotonic()
        async with self.queue_lock:
            func_name = req.func_name
            # 如果这个函数类型还没有队列，添加到轮询列表
            if func_name not in self.request_queues or len(self.request_queues[func_name]) == 0:
                if func_name not in self.request_queue_keys:
                    self.request_queue_keys.append(func_name)
            self.request_queues[func_name].append(req)
            self.queue_event.set()  # 通知队列处理协程

    def _get_next_request(self) -> Optional[EsiRequest]:
        """
        轮询获取下一个请求，确保不同函数类型的请求都能得到公平处理
        返回: 下一个要处理的请求，如果没有则返回None
        """
        if not self.request_queue_keys:
            return None
        
        # 轮询所有有请求的函数类型
        attempts = 0
        max_attempts = len(self.request_queue_keys)
        
        while attempts < max_attempts:
            # 取出第一个函数名，尝试获取其队列中的请求
            func_name = self.request_queue_keys[0]
            self.request_queue_keys.rotate(-1)  # 将第一个移到末尾，实现轮询
            
            queue = self.request_queues[func_name]
            if queue:
                req = queue.popleft()
                # 如果这个函数类型的队列空了，从轮询列表中移除
                if not queue:
                    self.request_queue_keys.remove(func_name)
                    max_attempts -= 1
                return req
            else:
                # 队列为空，从轮询列表中移除
                self.request_queue_keys.remove(func_name)
                max_attempts -= 1
            
            attempts += 1
        
        return None

    def process_request(self, req: EsiRequest):
        self.processing_queue.append(req)
        self.process_event.set()

    async def _process_request(self):
        """处理请求队列的协程"""
        self.logger.info("开始处理ESI处理队列")

        active_set = set()
        async def single_process(req):
            log_status_code = None
            log_error_message = None
            import time as _t3
            _proc_start = _t3.monotonic()
            try:
                result = await req.func()
                _proc_elapsed = _t3.monotonic() - _proc_start
                if _proc_elapsed > 30:
                    self.logger.warning(f"[esi_proc] {req.func_name} 执行耗时 {_proc_elapsed:.1f}s")
                else:
                    self.logger.debug(f"[esi_proc] {req.func_name} 完成 (耗时 {_proc_elapsed:.2f}s)")
                
                # 自动发现速率限制池（仅成功响应）
                # 优先从返回值元组提取 rate_limit_info；若 API 函数已丢弃头部信息
                # （返回非元组），则读取 get_request_async 通过侧信道存储的值
                if isinstance(result, tuple) and len(result) >= 4:
                    rate_limit_info = result[3] or {}
                    status_code = result[2] if isinstance(result[2], int) else 0
                    log_status_code = status_code
                    if 200 <= status_code < 400:
                        await self._discover_and_cache(req, rate_limit_info)
                else:
                    rate_limit_info = rate_limit_ctx.get(None) or {}
                    log_status_code = 200  # 非元组返回值视为成功
                    if rate_limit_info:
                        await self._discover_and_cache(req, rate_limit_info)
                
                # 检测错误响应：如果返回值是元组且包含状态码，检查是否为非2xx/3xx响应
                if isinstance(result, tuple) and len(result) >= 3:
                    status_code = result[2]
                    log_status_code = status_code
                    if isinstance(status_code, int) and not (200 <= status_code < 400):
                        await self._handle_error_response(req, status_code, rate_limit_info)
                
                if not req.future.done():
                    req.future.set_result(result)
            except Exception as e:
                # 异常也视为错误，扣除惩罚令牌
                # 注意：网络异常时无法拿到 ESI 响应头，_reported_remaining 是上次成功
                # 同步的陈旧值。不做大量扣除（避免与实际 ESI 状态严重偏离），
                # 仅轻微扣减 + 依赖下一次成功响应的 sync_from_esi_headers 纠正。
                log_status_code = 0
                log_error_message = str(e)
                pool = await self.lookup_pool(req)
                pool.error_count += 1
                if pool._reported_remaining is not None:
                    pool._reported_remaining = max(0, pool._reported_remaining - 5)
                    self.logger.warning(f"ESI请求异常: {str(e)}，已扣除5惩罚令牌 (池: {pool.name})")
                else:
                    await pool.deduct_penalty(220)
                    self.logger.warning(f"ESI请求异常: {str(e)}，已扣除惩罚令牌")
                
                if not req.future.done():
                    req.future.set_exception(e)
                else:
                    self.logger.error(f"Future already done when setting exception: {str(e)}", exc_info=True)
            
            # 非阻塞日志记录（fire-and-forget，不影响请求响应）
            try:
                pool = await self.lookup_pool(req)
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
        def done_call_back(task):
            try:
                active_set.discard(task)
            except Exception:
                pass

        while True:
            # 如果队列为空，等待新请求
            if not self.processing_queue:
                # self.logger.debug("处理队列为空，等待中。")
                self.process_event.clear()
                await self.process_event.wait()
                # self.logger.debug("获得处理任务，进行处理。")
        
            try:
                # 获取当前队列中的所有请求，但最多处理30个，避免内存占用过高
                batch_size = min(len(self.processing_queue), 30)

                # 遍历队列中的所有待处理请求，跳过池中令牌不足的（pool-aware）
                # 这样某个池令牌不足不会阻塞其他池的请求
                processed_indices = []
                for i in range(batch_size):
                    req = self.processing_queue[i]
                    pool = await self.lookup_pool(req)
                    if await self.get_tokens(req.required_tokens, pool):
                        processed_indices.append(i)
                        task = asyncio.create_task(single_process(req))
                        active_set.add(task)
                        task.add_done_callback(done_call_back)

                # 移除已处理的请求（逆序删除以保持索引正确）
                for i in reversed(processed_indices):
                    del self.processing_queue[i]

                skipped_count = batch_size - len(processed_indices)
                if skipped_count > 0:
                    self.logger.debug(
                        f"Batch processed: {len(processed_indices)} requests, "
                        f"{skipped_count} skipped (pool tokens insufficient)"
                    )

                await asyncio.sleep(1)

            except asyncio.CancelledError:
                self.logger.info("ESI请求队列处理协程被取消")
                # 等待所有活动任务完成
                if active_set:
                    await asyncio.gather(*active_set, return_exceptions=True)
                # 将所有未处理的请求设置为取消状态
                while self.processing_queue:
                    req = self.processing_queue.popleft()
                    if not req.future.done():
                        req.future.cancel()
                raise
            except Exception as e:
                self.logger.error(f"处理ESI请求队列时出错: {str(e)}", exc_info=True)
                # 如果出错，短暂暂停后继续
                await asyncio.sleep(1)

    async def _accept_request(self):
        """处理请求队列的协程（使用轮询调度）"""
        self.logger.info("开始处理ESI请求队列")
        while True:
            # 使用轮询方式获取下一个请求
            async with self.queue_lock:
                req = self._get_next_request()
            
            if req is None:
                # 没有请求，等待新请求
                self.logger.debug("请求队列为空，等待中。")
                self.queue_event.clear()
                await self.queue_event.wait()
                self.logger.debug("获得请求任务，进行处理。")
                continue

            try:
                # 执行ESI函数
                try:
                    self.process_request(req)
                except Exception as e:
                    req.future.set_exception(e)
                    self.logger.error(f"执行ESI请求时出错: {str(e)}", exc_info=True)

            except asyncio.CancelledError:
                self.logger.info("ESI请求队列处理协程被取消")
                # 将所有未处理的请求设置为取消状态
                async with self.queue_lock:
                    for queue in self.request_queues.values():
                        while queue:
                            req = queue.popleft()
                            if not req.future.done():
                                req.future.cancel()
                raise
            except Exception as e:
                self.logger.error(f"处理ESI请求队列时出错: {str(e)}", exc_info=True)
                # 如果出错，短暂暂停后继续
                await asyncio.sleep(1)

# 创建全局单例
esi_manager = EsiReqManager()

# ESI函数装饰器
def esi_request(limit_or_func=None, *, limit: int = 5, pool: Optional[str] = None):
    """
    装饰器，将ESI函数调用转换为队列请求

    支持4种调用方式:
        @esi_request              → limit=5, pool=None (自动发现)
        @esi_request(limit=30)    → 自定义limit, 自动发现pool
        @esi_request(pool='my')   → 指定pool, 默认limit=5
        @esi_request(pool='my', limit=30) → 同时指定pool和limit

    参数:
        limit: 该接口每秒请求上限，默认值为5 (仅关键字参数)
        pool: 指定令牌池名称，默认None由系统自动发现 (仅关键字参数)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 检查 TQ 服务器状态（本地内存缓存，不依赖 Redis）
            try:
                from src_v2.model.EVE.eveesi.tq_status import get_tq_status
                from src_v2.core.utils import EsiUnavailableError
                tq_status = get_tq_status()
                if tq_status == "offline":
                    raise EsiUnavailableError()
            except EsiUnavailableError:
                raise
            # 其他异常不阻塞请求（local cache 不会抛异常，保留安全兜底）

            # required_tokens: for auto-discovered pools use ESI standard cost (2);
            # for explicit pools keep the legacy rate-based calculation
            if pool is None:
                required_tokens = 2  # ESI standard token cost for 2XX responses
            else:
                required_tokens = max(1, math.ceil(esi_manager.token_generation_rate / limit))

            # 创建future对象，用于返回结果
            future = asyncio.get_running_loop().create_future()

            # 创建请求对象 - 这里使用一个内部函数来确保正确执行原始函数
            async def execute_func():
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"执行ESI函数时出错: {str(e)}", exc_info=True)
                    raise

            execute_func.__name__ = func.__name__  # 确保 EsiRequest 记录真实的函数名

            req = EsiRequest(execute_func, args, kwargs, future,
                             required_tokens=required_tokens, limit=limit,
                             pool_name=pool)

            # 将请求添加到队列
            await esi_manager.add_request(req)

            # 等待请求完成并返回结果
            import time as _t2
            _wait_start = _t2.monotonic()
            try:
                result = await future
                _wait_elapsed = _t2.monotonic() - _wait_start
                if _wait_elapsed > 10:
                    logger.warning(f"[esi_req] {func.__name__} future等待耗时 {_wait_elapsed:.1f}s (可能队列阻塞)")
                else:
                    logger.debug(f"[esi_req] {func.__name__} future完成 (耗时 {_wait_elapsed:.2f}s)")
                return result
            except Exception:
                # 确保异常被正确传播
                raise

        return wrapper

    # 支持不带括号的装饰器用法 @esi_request 和带参数的用法 @esi_request(limit=30)
    if callable(limit_or_func):
        # 直接传入函数 → @esi_request 用法，使用默认 limit=5, pool=None
        func = limit_or_func
        return decorator(func)
    else:
        # 传入的是参数 → @esi_request(limit=30) 或 @esi_request(pool='x')
        if limit_or_func is not None:
            limit = limit_or_func  # 位置参数 → limit
        return decorator

# 确保应用启动时初始化ESI管理器
async def init_esi_manager():
    await esi_manager.start()

# 确保应用关闭时停止ESI管理器
async def shutdown_esi_manager():
    await esi_manager.stop()