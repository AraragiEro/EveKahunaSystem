import time
import asyncio
from collections import deque
from functools import wraps
from typing import Callable, Any, Awaitable, Dict, Optional, List, Tuple

from ..log_server import logger

# 定义请求对象类型
class EsiRequest:
    def __init__(self, func: Callable, args: Tuple, kwargs: Dict, future: asyncio.Future):
        self.func = func  # ESI函数
        self.args = args  # 位置参数
        self.kwargs = kwargs  # 关键字参数
        self.future = future  # 用于返回结果的Future对象
        self.timestamp = time.time()  # 请求创建时间

class EsiReqManager:
    def __init__(self):
        # 请求队列
        self.request_queue = deque()
        self.processing_queue = deque()
        self.queue_event = asyncio.Event()  # 用于通知队列处理协程有新请求
        self.process_event = asyncio.Event()
        
        # 初始化滑动窗口

        # 初始化滑动窗口
        self.rate_limit = 50  # 每分钟请求限制
        self.window_size = 1  # 窗口大小（秒）
        self.request_timestamps = deque()  # 存储请求时间戳的队列
        self.lock = asyncio.Lock()
        
        # 日志
        self.logger = logger
        
        # 启动队列处理协程
        self._queue_task = None
        self._processing_task = None

    async def start(self):
        """启动请求处理协程"""
        if self._queue_task is None or self._queue_task.done():
            self._queue_task = asyncio.create_task(self._accept_request())
            self.logger.info("ESI请求队列处理协程已启动")
        if self._processing_task is None or self._processing_task.done():
            self._processing_task = asyncio.create_task(self._process_request())
            self.logger.info("ESI处理队列处理协程已启动")

    async def stop(self):
        """停止请求处理协程"""
        if self._queue_task and not self._queue_task.done():
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass
            self.logger.info("ESI请求队列处理协程已停止")
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
            self.logger.info("ESI处理队列处理协程已停止")

    # 每个eis请求需要获得一个token，token每分钟300个。
    async def get_token(self):
        """
        获取一个令牌，如果达到速率限制则等待
        返回: True表示获取成功
        """
        async with self.lock:
            current_time = time.time()

            # 清理过期的时间戳（超过60秒的）
            while self.request_timestamps and current_time - self.request_timestamps[0] > self.window_size:
                self.request_timestamps.popleft()

            # 检查是否达到速率限制
            if len(self.request_timestamps) >= self.rate_limit:
                # 计算需要等待的时间
                wait_time = self.request_timestamps[0] + self.window_size - current_time
                if wait_time > 0:
                    # self.logger.info(f"达到ESI速率限制，等待 {wait_time:.2f} 秒")
                    return False
                    await asyncio.sleep(wait_time)
                    # 重新获取当前时间，因为我们睡眠了一段时间
                    current_time = time.time()
                    # 再次清理过期的时间戳
                    while self.request_timestamps and current_time - self.request_timestamps[0] > self.window_size:
                        self.request_timestamps.popleft()

            # 添加新的请求时间戳
            self.request_timestamps.append(current_time)
            return True
    
    def add_request(self, req: EsiRequest):
        """添加请求到队列"""
        self.request_queue.append(req)
        self.queue_event.set()  # 通知队列处理协程
        if len(self.request_queue) % 50 == 0:
            self.logger.debug(f"当前请求队列长度: {len(self.request_queue)}")

    def process_request(self, req: EsiRequest):
        self.processing_queue.append(req)
        self.process_event.set()
        if len(self.processing_queue) % 50 == 0:
            self.logger.debug(f"当前处理队列长度: {len(self.processing_queue)}")

    async def _process_request(self):
        """处理请求队列的协程"""
        self.logger.info("开始处理ESI处理队列")

        active_set = set()
        async def single_process(req):
            result = await req.func()
            req.future.set_result(result)
        def done_call_back(task):
            active_set.discard(task)

        while True:
            # 如果队列为空，等待新请求
            if not self.processing_queue:
                self.logger.debug("处理队列为空，等待中。")
                self.process_event.clear()
                await self.process_event.wait()
                self.logger.debug("获得处理任务，进行处理。")
        
            try:
                # 获取当前队列中的所有请求，但最多处理100个，避免内存占用过高
                batch_size = min(len(self.processing_queue), 30)
                current_batch = []

                # 为每个请求获取token
                for _ in range(batch_size):
                    if not self.processing_queue:
                        break
                    # 获取token (这里每个请求仍然需要等待获取token)
                    if await self.get_token():
                        req = self.processing_queue.popleft()
                        task = asyncio.create_task(single_process(req))
                        active_set.add(task)
                        task.add_done_callback(done_call_back)

                await asyncio.sleep(1)

            except asyncio.CancelledError:
                self.logger.info("ESI请求队列处理协程被取消")
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
        """处理请求队列的协程"""
        self.logger.info("开始处理ESI请求队列")
        while True:
            # 如果队列为空，等待新请求
            if not self.request_queue:
                self.logger.debug("请求队列为空，等待中。")
                self.queue_event.clear()
                await self.queue_event.wait()
                self.logger.debug("获得请求任务，进行处理。")

            # 从队列获取请求
            if self.request_queue:
                req = self.request_queue[0]  # 先不弹出，获取token成功后再弹出

                try:
                    self.request_queue.popleft()

                    # 执行ESI函数
                    try:
                        # result = await req.func()
                        # req.future.set_result(result)
                        # self.logger.debug("完成任務。")
                        self.process_request(req)
                    except Exception as e:
                        req.future.set_exception(e)
                        self.logger.error(f"执行ESI请求时出错: {str(e)}", exc_info=True)

                except asyncio.CancelledError:
                    self.logger.info("ESI请求队列处理协程被取消")
                    # 将所有未处理的请求设置为取消状态
                    while self.request_queue:
                        req = self.request_queue.popleft()
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
def esi_request(func):
    """
    装饰器，将ESI函数调用转换为队列请求
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # 创建future对象，用于返回结果
        future = asyncio.get_running_loop().create_future()

        # 创建请求对象 - 这里使用一个内部函数来确保正确执行原始函数
        async def execute_func():
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"执行ESI函数时出错: {str(e)}", exc_info=True)
                raise e

        req = EsiRequest(execute_func, args, kwargs, future)

        # 将请求添加到队列
        esi_manager.add_request(req)
        
        # 等待请求完成并返回结果
        return await future
    
    return wrapper

# 确保应用启动时初始化ESI管理器
async def init_esi_manager():
    await esi_manager.start()

# 确保应用关闭时停止ESI管理器
async def shutdown_esi_manager():
    await esi_manager.stop()