"""
星系系数定时刷新器

每小时10分（+8时区）自动从 ESI 拉取最新的星系制造/反应系数，
写入 Redis 缓存（system_cost_cache:{system_id}）。

通过 Redis flag（system_cost_cache:flag）防止重复刷新：
- 标志存在 → 跳过（本小时已刷新过）
- 标志不存在 → 立即刷新
- 标志 TTL 到期后（下小时 :09）自动清除，触发下一轮刷新
"""

import asyncio
import random
import traceback
from datetime import datetime, timedelta, timezone

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.log import logger
from src_v2.core.utils import SingletonMeta


class SystemCostRefreshTimer(metaclass=SingletonMeta):
    """星系系数定时刷新器 — 每小时10分自动刷新"""

    REDIS_FLAG_KEY = "system_cost_cache:flag"
    TARGET_MINUTE = 10  # 每小时的10分
    CHECK_INTERVAL_SECONDS = 120  # 检查间隔 2 分钟
    TIMEZONE_OFFSET = 8  # +8 时区

    def __init__(self):
        self._running = False
        self._task = None

    async def _is_flag_set(self) -> bool:
        """检查本小时是否已刷新过（Redis flag 是否存在）"""
        try:
            return await rdm().r.exists(self.REDIS_FLAG_KEY) == 1
        except Exception:
            logger.error(f"检查 Redis flag 失败: {traceback.format_exc()}")
            return False

    def _is_target_time(self) -> bool:
        """检查当前时间是否已达到目标分钟（>= :10）"""
        tz = timezone(timedelta(hours=self.TIMEZONE_OFFSET))
        now = datetime.now(tz)
        return now.minute >= self.TARGET_MINUTE

    def _calculate_flag_ttl(self) -> int:
        """计算 flag TTL：到下一个小时的 :09 分。

        例如：当前 10:12 → TTL 到 11:09，约 57 分钟。
        这确保 flag 在下一次 :10 检查前已过期。
        """
        tz = timezone(timedelta(hours=self.TIMEZONE_OFFSET))
        now = datetime.now(tz)
        # 目标：当前小时+1 的 :09:00（使用 timedelta 避免 23→24 溢出）
        next_target = (
            now + timedelta(hours=1)
        ).replace(minute=self.TARGET_MINUTE - 1, second=0, microsecond=0)
        ttl = int((next_target - now).total_seconds())
        return max(ttl, 60)  # 最少 60 秒，防止极端情况

    async def _execute_refresh(self):
        """执行星系系数刷新任务。

        从 ESI /industry/systems/ 拉取数据，写入 Redis Hash。
        与 plan_configflow_operate.refresh_system_cost() 写入相同的 key，
        因此两个链路共享缓存数据。
        """
        try:
            # 双重检查：避免并发场景下重复执行
            if await self._is_flag_set():
                logger.info("星系系数刷新: flag 已存在，跳过（双重检查）")
                return

            from src_v2.model.EVE.eveesi.esi_api.industry import industry_systems

            logger.info("星系系数刷新: 开始从 ESI 拉取数据...")
            result = await industry_systems(log=True)

            if not result:
                logger.warning("星系系数刷新: ESI 返回空数据，跳过写入")
                return

            count = 0
            for item in result:
                data = {"solar_system_id": item["solar_system_id"]}
                for cost in item.get("cost_indices", []):
                    data[cost["activity"]] = cost["cost_index"]
                await rdm().r.hset(
                    f"system_cost_cache:{item['solar_system_id']}", mapping=data
                )
                count += 1

            # 设置 flag，TTL 到下个小时 :09 自动过期
            ttl = self._calculate_flag_ttl()
            await rdm().r.setex(self.REDIS_FLAG_KEY, ttl, "1")

            logger.info(f"星系系数刷新完成: {count} 个星系已更新，flag TTL={ttl}s")

        except Exception:
            logger.error(f"星系系数刷新失败: {traceback.format_exc()}")
            # 失败时设置短 TTL（600秒），避免频繁重试
            try:
                await rdm().r.setex(self.REDIS_FLAG_KEY, 600, "1")
            except Exception:
                pass

    async def _run_scheduler(self):
        """定时任务主循环。

        每 2 分钟检查一次：当前分钟 >= 10 且 flag 不存在 → 执行刷新。
        """
        logger.info("星系系数定时刷新器已启动（每小时 :10 分）")

        jitter = random.uniform(0, self.CHECK_INTERVAL_SECONDS * 0.3)
        await asyncio.sleep(jitter)

        while self._running:
            try:
                if self._is_target_time() and not await self._is_flag_set():
                    logger.info("星系系数刷新: 到达刷新时间窗口，flag 不存在，开始执行")
                    await self._execute_refresh()
                else:
                    logger.debug("星系系数刷新: 未达时间窗口或 flag 已存在，跳过")

                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info("星系系数定时刷新器被取消")
                break
            except Exception:
                logger.error(f"星系系数定时刷新器循环出错: {traceback.format_exc()}")
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    def start(self):
        """启动定时任务"""
        if self._running:
            logger.warning("星系系数定时刷新器已在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("星系系数定时刷新器已启动")

    def stop(self):
        """停止定时任务"""
        if not self._running:
            logger.warning("星系系数定时刷新器未运行")
            return

        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("星系系数定时刷新器已停止")

    async def wait(self):
        """等待定时任务完成（用于测试）"""
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
