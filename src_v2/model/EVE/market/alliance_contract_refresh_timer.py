import asyncio
from datetime import datetime, timedelta, timezone

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.log import logger
from src_v2.core.utils import SingletonMeta
from src_v2.model.EVE.market.contract_manager import contract_manager


class AllianceContractRefreshTimer(metaclass=SingletonMeta):
    """
    联盟合同刷新定时器

    每日在 0:00-0:59, 6:00-6:59, 12:00-12:59, 18:00-18:59（+8时区）时间段内自动刷新联盟合同。
    通过 Redis flag 防止重复执行，标志过期时间设置为下一个目标时间点。
    如果没有标志，立即执行（无论是否在时间窗口内）。
    """

    REDIS_FLAG_KEY = "alliance_contract_refresh:flag"
    TARGET_HOURS = [0, 6, 12, 18]  # 目标时间点（北京时间）
    TIMEZONE_OFFSET = 8  # +8时区
    CHECK_INTERVAL_SECONDS = 300  # 5分钟检查一次

    def __init__(self):
        self._running = False
        self._task = None

    def _is_in_target_time_range(self) -> bool:
        """
        检查当前时间是否在任意一个目标时间窗口内

        Returns:
            bool: 如果当前时间在 0:00-0:59, 6:00-6:59, 12:00-12:59, 18:00-18:59 之间，返回True
        """
        tz = timezone(timedelta(hours=self.TIMEZONE_OFFSET))
        now = datetime.now(tz)
        return now.hour in self.TARGET_HOURS

    def _get_next_target_time(self) -> datetime:
        """
        计算下一个目标时间点（+8时区）

        Returns:
            datetime: 下一个目标时间点的时间（带时区信息）
        """
        # 获取当前+8时区时间
        tz = timezone(timedelta(hours=self.TIMEZONE_OFFSET))
        now = datetime.now(tz)

        # 找到下一个目标时间点
        next_target = None
        for target_hour in sorted(self.TARGET_HOURS):
            # 计算今天的目标时间点
            today_target = now.replace(
                hour=target_hour, minute=0, second=0, microsecond=0)

            # 如果目标时间点在未来（大于当前时间），则这个就是下一个目标
            if today_target > now:
                next_target = today_target
                break

        # 如果今天的所有时间点都过了，则取明天的第一个时间点
        if next_target is None:
            tomorrow = now + timedelta(days=1)
            first_hour = min(self.TARGET_HOURS)
            next_target = tomorrow.replace(
                hour=first_hour, minute=0, second=0, microsecond=0)

        return next_target

    def _calculate_expire_seconds(self) -> int:
        """
        计算从当前时间到下一个目标时间点的秒数（用于设置 Redis key 过期时间）

        Returns:
            int: 到下一个目标时间点的秒数（至少为1秒，确保Redis接受）
        """
        next_target = self._get_next_target_time()
        tz = timezone(timedelta(hours=self.TIMEZONE_OFFSET))
        now = datetime.now(tz)
        delta = next_target - now
        expire_seconds = int(delta.total_seconds())
        # 确保过期时间至少为1秒，避免Redis报错
        return max(1, expire_seconds)

    async def _execute_refresh_task(self):
        """
        执行联盟合同刷新任务
        """
        try:
            logger.info("开始执行联盟合同刷新任务")

            # 调用 contract_manager 的刷新方法
            await contract_manager.refresh_alliance_contracts()

            logger.info("联盟合同刷新任务完成")

            # 任务完成后设置 Redis flag，过期时间设置为下一个目标时间点
            expire_seconds = self._calculate_expire_seconds()
            await rdm().r.set(self.REDIS_FLAG_KEY, "1", ex=expire_seconds)
            logger.info(
                f"已设置 Redis flag，过期时间: {expire_seconds} 秒后（下一个目标时间点）")

        except Exception as e:
            logger.error(f"执行联盟合同刷新任务失败: {e}", exc_info=True)
            # 即使失败也设置一个较短的过期时间，避免一直重试
            try:
                await rdm().r.set(self.REDIS_FLAG_KEY, "1", ex=3600)  # 1小时后过期
            except Exception as redis_error:
                logger.error(f"设置 Redis flag 失败: {redis_error}", exc_info=True)

    async def _run_scheduler(self):
        """
        定时任务主循环

        每5分钟检查一次 Redis 标志，如果检测不到标志则执行刷新任务（无论是否在时间窗口内）。
        如果标志存在，跳过执行。
        """
        logger.info("联盟合同刷新定时器已启动，每5分钟检查一次 Redis 标志")

        while self._running:
            try:
                # 检查 Redis flag
                flag_exists = await rdm().r.exists(self.REDIS_FLAG_KEY)

                if not flag_exists:
                    # 标志不存在，立即执行（无论是否在时间窗口内）
                    in_time_range = self._is_in_target_time_range()
                    if in_time_range:
                        logger.info(
                            "检测到 alliance_contract_refresh:flag 不存在，且当前时间在目标时间窗口内，开始执行刷新任务")
                    else:
                        logger.info(
                            "检测到 alliance_contract_refresh:flag 不存在，立即执行刷新任务（不在时间窗口内）")
                    await self._execute_refresh_task()
                else:
                    logger.debug("alliance_contract_refresh:flag 存在，跳过本次执行")

                # 等待5分钟后再次检查
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info("联盟合同刷新定时器被取消")
                break
            except Exception as e:
                logger.error(f"定时器循环出错: {e}", exc_info=True)
                # 出错后等待5分钟再继续
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    def start(self):
        """
        启动定时任务
        """
        if self._running:
            logger.warning("联盟合同刷新定时器已在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("联盟合同刷新定时器已启动")

    def stop(self):
        """
        停止定时任务
        """
        if not self._running:
            logger.warning("联盟合同刷新定时器未运行")
            return

        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("联盟合同刷新定时器已停止")

    async def wait(self):
        """
        等待定时任务完成（用于测试或清理）
        """
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
