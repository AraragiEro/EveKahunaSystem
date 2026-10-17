"""TQ Server Status Manager — 本地内存缓存 + 后台定期刷新。

消除 ESI 状态检查的 Redis 依赖，99.9% 的 check_tq_status() 调用直接返回内存值。
"""
import asyncio
import time

import aiohttp

from src_v2.core.log import logger

TQ_STATUS_URL = "https://esi.evetech.net/status/"
_REFRESH_INTERVAL = 60  # seconds
_FETCH_TIMEOUT = aiohttp.ClientTimeout(total=5)


class TqStatusManager:
    """TQ 服务器状态管理器：内存缓存 + 后台定期刷新。

    每个 ESI 请求不再需要访问 Redis 获取 TQ 状态，
    改用本地内存缓存，后台定期刷新。彻底消除 ESI 状态
    检查对 Redis 的依赖和并发压力。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._status = "online"
            cls._instance._last_updated = 0.0
            cls._instance._refresh_task = None
            cls._instance._started = False
        return cls._instance

    @property
    def status(self) -> str:
        """返回当前缓存的 TQ 状态：online / offline / unknown"""
        return self._status

    def start(self):
        """启动后台刷新任务（幂等，多次调用安全）"""
        if self._started:
            return
        self._started = True
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info("TqStatusManager: 后台刷新已启动 (interval=60s)")

    async def _refresh_loop(self):
        """后台定期刷新循环"""
        # 启动时立即获取一次，设置初始状态
        await self._fetch_status()
        logger.info(f"TqStatusManager: 初始状态 = {self._status}")

        while True:
            await asyncio.sleep(_REFRESH_INTERVAL)
            try:
                await self._fetch_status()
            except Exception as e:
                logger.warning(f"TqStatusManager: 刷新异常: {e}")

    async def _fetch_status(self):
        """从 ESI /status/ 获取 TQ 状态"""
        try:
            async with aiohttp.ClientSession(timeout=_FETCH_TIMEOUT) as session:
                async with session.get(TQ_STATUS_URL) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        new_status = (
                            "online" if data.get("players", 0) > 0 else "offline"
                        )
                    else:
                        new_status = "unknown"
        except asyncio.TimeoutError:
            logger.warning("TQ 状态查询超时，保持上次状态")
            return
        except Exception as e:
            logger.warning(f"TQ 状态查询失败: {e}，保持上次状态")
            return

        if new_status != self._status:
            logger.info(
                f"TQ 状态变更: {self._status} -> {new_status}"
            )
        self._status = new_status
        self._last_updated = time.time()


# 全局单例
_tq_manager = TqStatusManager()


def get_tq_status() -> str:
    """获取当前 TQ 状态（缓存，即时返回，永不阻塞）"""
    return _tq_manager.status


def start_tq_status_refresh():
    """启动 TQ 状态后台刷新（应用启动时调用一次）"""
    _tq_manager.start()
