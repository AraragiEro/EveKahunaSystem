"""
Dashboard运营数据快照定时任务
每天凌晨0点（+8时区）自动执行 aggregate_ops_stats() 并将结果缓存到Redis
"""
import asyncio
import json
import random
import traceback
from datetime import datetime

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.log import logger
from src_v2.core.utils import SingletonMeta, get_beijing_utctime


class DashboardOpsSnapshotTimer(metaclass=SingletonMeta):
    """Dashboard运营数据快照定时任务"""

    TIMEZONE_OFFSET = 8  # +8时区
    TARGET_HOUR = 0  # 目标执行时间：凌晨0点
    CHECK_INTERVAL_SECONDS = 300  # 检查间隔：5分钟

    def __init__(self):
        self._running = False
        self._task = None

    async def _has_executed_today(self) -> bool:
        """检查今日是否已执行过快照任务

        Returns:
            True如果已执行，False如果未执行
        """
        try:
            return await rdm().r.exists("dashboard_ops_executed_today") == 1
        except Exception:
            logger.error(f"检查今日执行状态失败: {traceback.format_exc()}")
            return False

    async def _execute_save_task(self):
        """执行运营数据快照任务"""
        try:
            from src_v2.backend.api.EVE.utils_home import aggregate_ops_stats

            stats = await aggregate_ops_stats()
            await rdm().r.setex("dashboard_ops_stats", 86400, json.dumps(stats))
            await rdm().r.setex("dashboard_ops_executed_today", 86400, "1")
            logger.info(f"Dashboard ops stats saved: {stats}")
        except Exception:
            logger.error(f"Dashboard ops snapshot failed: {traceback.format_exc()}")

    def _is_target_time(self) -> bool:
        """检查当前时间是否是目标执行时间（凌晨0点）

        Returns:
            True如果是目标时间，False如果不是
        """
        try:
            beijing_time = get_beijing_utctime(datetime.now())
            return beijing_time.hour == self.TARGET_HOUR
        except Exception as e:
            logger.error(f"检查目标时间失败: {e}")
            return False

    async def _run_scheduler(self):
        """定时任务主循环

        每天凌晨0点（+8时区）执行一次运营数据快照任务
        """
        logger.info("Dashboard运营数据快照定时器已启动")

        jitter = random.uniform(0, self.CHECK_INTERVAL_SECONDS * 0.3)
        await asyncio.sleep(jitter)

        last_execution_date = None

        while self._running:
            try:
                beijing_time = get_beijing_utctime(datetime.now())
                current_date = beijing_time.date()

                if self._is_target_time() and last_execution_date != current_date:
                    logger.info(f"到达目标时间，开始执行运营数据快照任务（日期: {current_date}）")
                    await self._execute_save_task()
                    last_execution_date = current_date

                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info("Dashboard运营数据快照定时器被取消")
                break
            except Exception as e:
                logger.error(f"定时器循环出错: {e}", exc_info=True)
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    def start(self):
        """启动定时任务"""
        if self._running:
            logger.warning("Dashboard运营数据快照定时器已在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        # 启动时立即异步执行一次快照（不阻塞启动流程）
        asyncio.ensure_future(self._execute_initial_snapshot())
        logger.info("Dashboard运营数据快照定时器已启动")

    async def _execute_initial_snapshot(self):
        """启动时延迟5秒后执行首次快照（等数据库连接就绪）"""
        await asyncio.sleep(5)
        logger.info("执行 Dashboard 运营数据首次快照...")
        await self._execute_save_task()

    def stop(self):
        """停止定时任务"""
        if not self._running:
            logger.warning("Dashboard运营数据快照定时器未运行")
            return

        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Dashboard运营数据快照定时器已停止")

    async def wait(self):
        """等待定时任务完成（用于测试）"""
        if self._task:
            await self._task
