"""市场调价缓存（market_price_cache）刷新与定时器。

背景（2026-10-19 复盘）：
- 计算链路（`.成本`）以前在 `plan_configflow_operate.get_type_adjust_price` 里
  **按需**刷新本缓存：持有进程内锁去 ESI 拉全量价格表，且整段没有超时。
  ESI 抖动时锁被占几分钟，5 个并发关系计算任务全部在 acquire 上等待，
  整个成本计算静默卡死。
- 现在计算链路**只读缓存、绝不刷新**，本模块的定时器成为唯一刷新者。

缓存结构（与既有读取方保持一致）：
- `market_price_cache:{type_id}` -> hash: adjusted_price / average_price
- `market_price_cache:status`    -> "ok"，TTL 到次日 0 点
- `market_price_cache:etag`      -> ESI 的 Etag，用于 If-None-Match 条件请求
"""

import asyncio
import time
import traceback

import aiohttp

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.log import logger
from src_v2.core.utils import SingletonMeta

ESI_PRICES_URL = "https://esi.evetech.net/markets/prices/?datasource=tranquility"


def _status_ttl_seconds() -> int:
    """status 键的 TTL：到次日 0 点（与旧实现一致）。"""
    now = time.localtime()
    tomorrow = time.struct_time((
        now.tm_year, now.tm_mon, now.tm_mday + 1, 0, 0, 0,
        now.tm_wday, now.tm_yday, now.tm_isdst,
    ))
    ttl = int(time.mktime(tomorrow) - time.time())
    return ttl if ttl > 0 else 86400


async def refresh_market_price_cache(redis=None) -> int:
    """从 ESI 拉全量调价并写入 Redis，返回写入的 type_id 数量。

    - ETag 条件请求：数据未变更时 ESI 返回 304，省掉约 1.1MB 下行；
    - pipeline 分块（500/批）写入：避免约 2 万次串行往返（旧实现正是这样
      在持锁状态下把刷新拖到分钟级）；
    - 失败向上抛异常，由调用方决定降级。
    """
    r = redis if redis is not None else rdm().r

    etag = await r.get("market_price_cache:etag")
    if isinstance(etag, bytes):
        etag = etag.decode("utf-8", "ignore")
    headers = {
        "User-Agent": "EveKahunaSystem/price-cache",
        "Accept": "application/json",
    }
    if etag:
        headers["If-None-Match"] = etag

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as session:
        async with session.get(ESI_PRICES_URL, headers=headers) as resp:
            if resp.status == 304:
                ttl = _status_ttl_seconds()
                await r.set("market_price_cache:status", "ok", ex=ttl)
                logger.info(f"调价缓存刷新: ESI 返回 304（无变更），仅续期 status TTL={ttl}s")
                return 0
            if resp.status != 200:
                raise RuntimeError(f"ESI markets/prices 返回 HTTP {resp.status}")
            results = await resp.json()
            new_etag = resp.headers.get("Etag")

    if not results:
        raise RuntimeError("ESI markets/prices 返回空数据")

    written = 0
    pipe = r.pipeline(transaction=False)
    pending = 0
    for item in results:
        item.setdefault("adjusted_price", 0.0)
        item.setdefault("average_price", 0.0)
        pipe.hset(f"market_price_cache:{item['type_id']}", mapping=item)
        pending += 1
        if pending >= 500:
            await pipe.execute()
            written += pending
            pipe = r.pipeline(transaction=False)
            pending = 0
    if pending:
        await pipe.execute()
        written += pending

    if new_etag:
        await r.set("market_price_cache:etag", new_etag)
    await r.set("market_price_cache:status", "ok", ex=_status_ttl_seconds())
    logger.info(f"调价缓存刷新完成: {written} 个 type_id（pipeline 分块写入）")
    return written


class MarketPriceCacheRefreshTimer(metaclass=SingletonMeta):
    """调价缓存定时刷新器：status 非 ok 时自动刷新。

    每 10 分钟检查一次 `market_price_cache:status`：
    - `ok` → 跳过（TTL 到次日 0 点，因此正常情况下每天只刷新一次）
    - 非 `ok` → 抢 Redis 锁（600s）后刷新；失败记日志，下个周期再试
    计算链路只读这份缓存，因此本定时器是价格的唯一来源。
    """

    CHECK_INTERVAL_SECONDS = 600
    LOCK_KEY = "market_price_cache:refresh_lock"

    def __init__(self):
        self._running = False
        self._task = None

    async def _run_scheduler(self):
        logger.info("调价缓存定时刷新器已启动（每 10 分钟检查一次）")
        # 启动后稍等，避开服务初始化与其它定时器的高峰
        await asyncio.sleep(30)
        while self._running:
            try:
                status = await rdm().r.get("market_price_cache:status")
                if isinstance(status, bytes):
                    status = status.decode("utf-8", "ignore")
                if status == "ok":
                    await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
                    continue

                acquired = await rdm().r.set(self.LOCK_KEY, "1", nx=True, ex=600)
                if not acquired:
                    logger.debug("调价缓存刷新: 已有实例在刷新，跳过本轮")
                    await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
                    continue

                try:
                    await refresh_market_price_cache()
                finally:
                    try:
                        await rdm().r.delete(self.LOCK_KEY)
                    except Exception:
                        pass

                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                logger.info("调价缓存定时刷新器被取消")
                break
            except Exception:
                logger.error(f"调价缓存定时刷新器循环出错: {traceback.format_exc()}")
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    def start(self):
        if self._running:
            logger.warning("调价缓存定时刷新器已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        return self._task

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("调价缓存定时刷新器已停止")
