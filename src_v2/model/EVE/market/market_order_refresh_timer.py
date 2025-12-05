import asyncio

from src_v2.core.database.connect_manager import redis_manager as rdm
from src_v2.model.EVE.market.market_manager import MarketManager
from src_v2.core.log import logger
from src_v2.core.utils import SingletonMeta


class MarketOrderRefreshTimer(metaclass=SingletonMeta):
    """
    Jita 订单刷新定时器
    
    每30分钟检查一次 Redis 标志，如果检测不到标志则执行 Jita 订单更新任务。
    通过 Redis flag 防止重复执行，标志由 MarketManager.update_jita_price() 设置。
    """
    
    REDIS_FLAG_KEY = "market_update_flag:jita"
    CHECK_INTERVAL_SECONDS = 1800  # 30分钟检查一次
    
    def __init__(self):
        self._running = False
        self._task = None
    
    async def _execute_refresh_task(self):
        """
        执行 Jita 订单刷新任务
        """
        try:
            logger.info("开始执行 Jita 订单刷新任务")
            
            # 获取 MarketManager 实例并更新 Jita 订单
            market_manager = MarketManager()
            await market_manager.update_jita_price()
            
            logger.info("Jita 订单刷新任务完成")
            
        except Exception as e:
            logger.error(f"执行 Jita 订单刷新任务失败: {e}", exc_info=True)
    
    async def _run_scheduler(self):
        """
        定时任务主循环
        
        每30分钟检查一次 Redis 标志，如果检测不到标志则执行任务。
        """
        logger.info("Jita 订单刷新定时器已启动，每30分钟检查一次 Redis 标志")
        
        while self._running:
            try:
                # 检查 Redis flag
                flag_exists = await rdm.r.exists(self.REDIS_FLAG_KEY)
                
                if not flag_exists:
                    logger.info("检测到 market_update_flag:jita 不存在，开始执行任务")
                    # 执行任务
                    await self._execute_refresh_task()
                else:
                    logger.debug("market_update_flag:jita 存在，跳过本次执行")
                
                # 等待30分钟后再次检查
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
                
            except asyncio.CancelledError:
                logger.info("Jita 订单刷新定时器被取消")
                break
            except Exception as e:
                logger.error(f"定时器循环出错: {e}", exc_info=True)
                # 出错后等待30分钟再继续
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
    
    def start(self):
        """
        启动定时任务
        """
        if self._running:
            logger.warning("Jita 订单刷新定时器已在运行中")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("Jita 订单刷新定时器已启动")
    
    def stop(self):
        """
        停止定时任务
        """
        if not self._running:
            logger.warning("Jita 订单刷新定时器未运行")
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Jita 订单刷新定时器已停止")
    
    async def wait(self):
        """
        等待定时任务完成（用于测试或清理）
        """
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

