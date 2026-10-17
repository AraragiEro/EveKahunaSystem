"""
订单统计数据刷新定时器
通过轮询 Redis flag 判断是否需要刷新各 VIP 用户的订单统计
flag 存在 = 24h 内已刷新，跳过
flag 不存在 = 需要刷新，执行后设置 flag (TTL=24h)
管理员可通过删除 flag 实现手动刷新
"""
import asyncio
import random
import traceback
from datetime import datetime, timedelta, timezone

from src_v2.backend.api.EVE import utils_home
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.kahuna_database_utils_v2 import VipStateDBUtils
from src_v2.core.log import logger
from src_v2.core.utils import SingletonMeta


class OrdersStatsRefreshTimer(metaclass=SingletonMeta):
    FLAG_KEY_PREFIX = "orders_stats_refreshed"
    REFRESH_LOCK_PREFIX = "orders_stats_refresh_lock"
    CHECK_INTERVAL_SECONDS = 300
    FLAG_TTL = 86400

    def __init__(self):
        self._running = False
        self._task = None

    def _get_flag_key(self, user_name: str) -> str:
        return f"{self.FLAG_KEY_PREFIX}:{user_name}"

    def _get_lock_key(self, user_name: str) -> str:
        return f"{self.REFRESH_LOCK_PREFIX}:{user_name}"

    async def _get_vip_users(self):
        users = []
        try:
            async for vip_state in await VipStateDBUtils.select_all_vip_states():
                if vip_state.vip_level in ("vip_alpha", "vip_omega"):
                    users.append(vip_state.user_name)
        except Exception as e:
            logger.error(f"获取VIP用户列表失败: {e}")
        return users

    @staticmethod
    def delete_flag(user_name: str):
        """管理员手动删除 flag，触发下次轮询刷新"""

    async def _refresh_user_if_needed(self, user_name: str):
        flag_key = self._get_flag_key(user_name)
        if await rdm().r.exists(flag_key):
            return

        lock_key = self._get_lock_key(user_name)
        if not await rdm().r.set(lock_key, "1", ex=300, nx=True):
            return

        try:
            await utils_home.refresh_orders_stats(user_name)
            await rdm().r.set(flag_key, "1", ex=self.FLAG_TTL)
        except Exception:
            logger.error(
                f"刷新用户 {user_name} 订单统计失败: {traceback.format_exc()}"
            )
        finally:
            await rdm().r.delete(lock_key)

    async def _execute_refresh_task(self):
        vip_users = await self._get_vip_users()
        refreshed = 0
        skipped = 0
        for user_name in vip_users:
            try:
                flag_key = self._get_flag_key(user_name)
                if await rdm().r.exists(flag_key):
                    skipped += 1
                    continue
                await self._refresh_user_if_needed(user_name)
                refreshed += 1
            except Exception as e:
                logger.error(f"处理用户 {user_name} 订单统计刷新时出错: {e}")

        if refreshed > 0 or skipped > 0:
            logger.info(
                f"订单统计刷新完成: 刷新 {refreshed} 人, 跳过 {skipped} 人"
            )

    async def _run_scheduler(self):
        logger.info("订单统计刷新定时器已启动")

        jitter = random.uniform(0, self.CHECK_INTERVAL_SECONDS * 0.3)
        await asyncio.sleep(jitter)

        while self._running:
            try:
                await self._execute_refresh_task()
            except asyncio.CancelledError:
                logger.info("订单统计刷新定时器被取消")
                break
            except Exception as e:
                logger.error(f"订单统计刷新定时器出错: {e}", exc_info=True)
            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    def start(self):
        if self._running:
            logger.warning("订单统计刷新定时器已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("订单统计刷新定时器已启动")

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("订单统计刷新定时器已停止")

    async def wait(self):
        if self._task:
            await self._task
