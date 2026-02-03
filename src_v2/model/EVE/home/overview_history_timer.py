"""
Overview历史数据自动保存定时任务
每天凌晨5点（+8时区）自动为开启自动保存的用户保存overview数据
"""
import asyncio
import json
import traceback
from datetime import datetime, timedelta, timezone
from typing import List

from src_v2.backend.api.EVE import utils_home
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.kahuna_database_utils_v2 import EveOverviewHistoryDBUtils, UserDataDBUtils, VipStateDBUtils
from src_v2.core.log import logger
from src_v2.core.utils import SingletonMeta, get_beijing_utctime


class OverviewHistoryTimer(metaclass=SingletonMeta):
    """Overview历史数据自动保存定时任务"""

    TIMEZONE_OFFSET = 8  # +8时区
    TARGET_HOUR = 5  # 目标执行时间：凌晨5点
    CHECK_INTERVAL_SECONDS = 300  # 检查间隔：5分钟

    def __init__(self):
        self._running = False
        self._task = None

    async def _get_vip_users(self) -> List[str]:
        """获取所有vip_alpha和vip_omega用户

        Returns:
            用户ID列表
        """
        users = []
        try:
            async for vip_state in await VipStateDBUtils.select_all_vip_states():
                if vip_state.vip_level in ('vip_alpha', 'vip_omega'):
                    users.append(vip_state.user_name)
        except Exception as e:
            logger.error(f"获取VIP用户列表失败: {traceback.format_exc()}")
        return users

    async def _should_auto_save(self, user_name: str) -> bool:
        """检查用户是否开启了自动保存

        Args:
            user_name: 用户名

        Returns:
            True如果开启，False如果未开启
        """
        try:
            auto_save = await UserDataDBUtils.get_user_setting(
                user_name, 'auto_save_overview_data', False
            )
            return bool(auto_save)
        except Exception as e:
            logger.error(f"检查用户 {user_name} 自动保存设置失败: {e}")
            return False

    async def _has_today_data(self, user_name: str) -> bool:
        """检查用户今日是否已有数据

        Args:
            user_name: 用户名

        Returns:
            True如果已有，False如果没有
        """
        try:
            today_date = utils_home.get_today_date_beijing()
            return await EveOverviewHistoryDBUtils.check_date_exists(user_name, today_date)
        except Exception as e:
            logger.error(f"检查用户 {user_name} 今日数据失败: {e}")
            return False

    async def _save_user_overview(self, user_name: str) -> bool:
        """为指定用户保存overview数据

        Args:
            user_name: 用户名

        Returns:
            True如果成功，False如果失败
        """
        try:
            # 从Redis获取overview数据
            overview_data_str = await rdm().r.get(f"overview_data:{user_name}")
            if not overview_data_str:
                # 如果没有缓存数据，需要计算一次
                logger.info(f"用户 {user_name} 没有缓存数据，开始强制刷新overview")
                try:
                    # 钱包价值
                    wallet_value = {}
                    try:
                        wallet_value = await utils_home.get_wallet_value(user_name)
                    except Exception:
                        logger.error(
                            f"获取用户 {user_name} 钱包价值失败: {traceback.format_exc()}")

                    # 订单价值
                    order_value = {}
                    try:
                        order_value = await utils_home.get_order_value(user_name)
                    except Exception:
                        logger.error(
                            f"获取用户 {user_name} 订单价值失败: {traceback.format_exc()}")

                    # 运行中流程价值
                    running_process_value = 0.0
                    try:
                        running_process_data = await utils_home.calculate_running_process_value(user_name)
                        running_process_value = running_process_data.get(
                            "total_value", 0.0)
                    except Exception:
                        logger.error(
                            f"获取用户 {user_name} 运行中流程价值失败: {traceback.format_exc()}")

                    # 标记资产价值
                    marked_asset_value = 0.0
                    try:
                        marked_asset_value = await utils_home.get_marked_asset_value(user_name)
                    except Exception:
                        logger.error(
                            f"获取用户 {user_name} 标记资产价值失败: {traceback.format_exc()}")

                    # 非标记资产价值
                    unmarked_asset_value = 0.0
                    try:
                        unmarked_asset_value = await utils_home.get_unmarked_asset_value(user_name)
                    except Exception:
                        logger.error(
                            f"获取用户 {user_name} 非标记资产价值失败: {traceback.format_exc()}")

                    # 组装overview数据
                    overview_data = {
                        "orderValue": order_value,
                        "walletValue": wallet_value,
                        "runningProcessValue": running_process_value,
                        "markedAssetValue": marked_asset_value,
                        "unmarkedAssetValue": unmarked_asset_value
                    }

                    # 保存到Redis
                    await rdm().r.set(f"overview_data:{user_name}", json.dumps(overview_data))
                    await rdm().r.expire(f"overview_data:{user_name}", 60 * 60)
                    logger.info(f"用户 {user_name} 的overview数据已强制刷新并缓存")

                    # 使用计算出的数据继续后续流程
                    overview_data_str = json.dumps(overview_data)
                except Exception as e:
                    logger.error(
                        f"为用户 {user_name} 强制刷新overview数据失败: {traceback.format_exc()}")
                    return False

            overview_data = json.loads(overview_data_str)

            # 处理数据（求和子结构）
            processed_data = utils_home.process_overview_data_for_history(
                overview_data)

            # 获取今日日期
            today_date = utils_home.get_today_date_beijing()

            # 保存数据
            await EveOverviewHistoryDBUtils.save_overview_data(
                user_name, today_date, processed_data
            )

            logger.info(f"用户 {user_name} 的overview数据已自动保存")
            return True

        except Exception as e:
            logger.error(
                f"为用户 {user_name} 保存overview数据失败: {traceback.format_exc()}")
            return False

    async def _execute_save_task(self):
        """执行自动保存任务"""
        try:
            logger.info("开始执行Overview历史数据自动保存任务")

            # 获取所有VIP用户
            vip_users = await self._get_vip_users()
            logger.info(f"找到 {len(vip_users)} 个VIP用户")

            saved_count = 0
            skipped_count = 0
            failed_count = 0

            for user_name in vip_users:
                try:
                    # 检查是否开启自动保存
                    if not await self._should_auto_save(user_name):
                        skipped_count += 1
                        continue

                    # 检查今日是否已有数据
                    if await self._has_today_data(user_name):
                        skipped_count += 1
                        logger.debug(f"用户 {user_name} 今日已有数据，跳过")
                        continue

                    # 保存数据
                    if await self._save_user_overview(user_name):
                        saved_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    logger.error(f"处理用户 {user_name} 时出错: {e}")
                    failed_count += 1

            logger.info(
                f"自动保存任务完成: 成功 {saved_count} 个, "
                f"跳过 {skipped_count} 个, 失败 {failed_count} 个"
            )

        except Exception as e:
            logger.error(f"执行自动保存任务失败: {traceback.format_exc()}")

    def _is_target_time(self) -> bool:
        """检查当前时间是否是目标执行时间（凌晨5点）

        Returns:
            True如果是目标时间，False如果不是
        """
        try:
            # 获取+8时区的当前时间
            beijing_time = get_beijing_utctime(datetime.now())
            current_hour = beijing_time.hour
            current_minute = beijing_time.minute

            # 检查是否是5点（允许5:00-5:59之间执行，避免错过）
            return current_hour == self.TARGET_HOUR
        except Exception as e:
            logger.error(f"检查目标时间失败: {e}")
            return False

    async def _run_scheduler(self):
        """定时任务主循环

        每天凌晨5点（+8时区）执行一次自动保存任务
        """
        logger.info("Overview历史数据自动保存定时器已启动")
        last_execution_date = None

        while self._running:
            try:
                # 获取当前日期（+8时区）
                beijing_time = get_beijing_utctime(datetime.now())
                current_date = beijing_time.date()

                # 检查是否是目标时间且今天还未执行
                if self._is_target_time() and last_execution_date != current_date:
                    logger.info(f"到达目标时间，开始执行自动保存任务（日期: {current_date}）")
                    await self._execute_save_task()
                    last_execution_date = current_date

                # 等待检查间隔
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info("Overview历史数据自动保存定时器被取消")
                break
            except Exception as e:
                logger.error(f"定时器循环出错: {e}", exc_info=True)
                # 出错后等待一段时间再继续
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    def start(self):
        """启动定时任务"""
        if self._running:
            logger.warning("Overview历史数据自动保存定时器已在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("Overview历史数据自动保存定时器已启动")

    def stop(self):
        """停止定时任务"""
        if not self._running:
            logger.warning("Overview历史数据自动保存定时器未运行")
            return

        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Overview历史数据自动保存定时器已停止")

    async def wait(self):
        """等待定时任务完成（用于测试）"""
        if self._task:
            await self._task
