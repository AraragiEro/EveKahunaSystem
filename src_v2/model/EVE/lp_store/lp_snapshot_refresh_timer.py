"""
LP价值快照每日定时任务
每日 UTC 12:00 自动执行 LP 价值评估快照
"""
import asyncio
import random
import traceback
from datetime import datetime

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.log import logger
from src_v2.core.utils import SingletonMeta


class LpSnapshotRefreshTimer(metaclass=SingletonMeta):
    """LP价值快照每日定时任务 — 每日 UTC 12:00 执行"""

    TARGET_HOUR = 12  # UTC 12:00
    CHECK_INTERVAL_SECONDS = 300  # 检查间隔 5 分钟

    def __init__(self):
        self._running = False
        self._task = None

    async def _has_executed_today(self) -> bool:
        try:
            return await rdm().r.exists("lp_snapshot_executed_today") == 1
        except Exception:
            logger.error(f"检查LP快照今日执行状态失败: {traceback.format_exc()}")
            return False

    async def _execute_snapshot(self):
        try:
            from src_v2.model.EVE.lp_store.lp_snapshot_manager import LpSnapshotManager

            logger.info("开始LP价值每日快照...")
            manager = LpSnapshotManager()
            count = await manager.take_snapshot()
            logger.info(f"LP快照完成，写入{count}条军团记录")
        except Exception:
            logger.error(f"LP快照执行失败: {traceback.format_exc()}")

    def _is_target_hour(self) -> bool:
        return datetime.utcnow().hour == self.TARGET_HOUR

    async def _run_scheduler(self):
        logger.info("LP价值快照定时器已启动（每日 UTC 12:00）")

        jitter = random.uniform(0, self.CHECK_INTERVAL_SECONDS * 0.3)
        await asyncio.sleep(jitter)

        last_execution_date = None

        while self._running:
            try:
                utc_now = datetime.utcnow()
                current_date = utc_now.date()

                if self._is_target_hour() and last_execution_date != current_date:
                    logger.info(
                        f"到达目标时间 UTC 12:00，开始执行LP价值快照（日期: {current_date}）"
                    )
                    await self._execute_snapshot()
                    last_execution_date = current_date
                    await rdm().r.setex("lp_snapshot_executed_today", 86400, "1")

                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info("LP价值快照定时器被取消")
                break
            except Exception as e:
                logger.error(f"LP快照定时器循环出错: {e}", exc_info=True)
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    def start(self):
        if self._running:
            logger.warning("LP价值快照定时器已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("LP价值快照定时器已启动")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("LP价值快照定时器已停止")
