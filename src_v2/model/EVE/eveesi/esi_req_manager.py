import time
import math
import asyncio
from collections import deque, defaultdict
from functools import wraps
from typing import Callable, Any, Awaitable, Dict, Optional, List, Tuple

from src_v2.core.log import logger

# 定义请求对象类型
class EsiRequest:
    def __init__(self, func: Callable, args: Tuple, kwargs: Dict, future: asyncio.Future, required_tokens: int = 60, limit: int = 5):
        self.func = func  # ESI函数
        self.func_name = func.__name__  # 函数名称
        self.args = args  # 位置参数
        self.kwargs = kwargs  # 关键字参数
        self.future = future  # 用于返回结果的Future对象
        self.timestamp = time.time()  # 请求创建时间
        self.required_tokens = required_tokens  # 该请求需要的令牌数量
        self.limit = limit  # 该接口的限速值（每秒请求上限）

class EsiReqManager:
    def __init__(self):
        # 使用字典存储不同函数类型的请求队列，实现轮询调度
        self.request_queues = defaultdict(deque)  # {func_name: deque([reqs])}
        self.request_queue_keys = deque()  # 改为 deque，用于轮询
        self.processing_queue = deque()
        self.queue_event = asyncio.Event()  # 用于通知队列处理协程有新请求
        self.process_event = asyncio.Event()
        self.queue_lock = asyncio.Lock()  # 保护队列操作的锁
        
        # 令牌池管理
        self.token_pool = 0.0  # 当前可用令牌数（初始为0）
        self.token_generation_rate = 300  # 每秒产生300个令牌
        self.max_token_pool = 600  # 令牌池最大容量
        self.last_token_update_time = time.time()  # 上次更新令牌的时间戳
        self.lock = asyncio.Lock()  # 保护令牌池操作的锁
        
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
        # 先停止处理任务，因为它可能依赖队列任务
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
            self.logger.info("ESI处理队列处理协程已停止")
        
        # 然后停止队列任务
        if self._queue_task and not self._queue_task.done():
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass
            self.logger.info("ESI请求队列处理协程已停止")

    async def get_tokens(self, required_tokens: int) -> bool:
        """
        获取指定数量的令牌，如果令牌不足则返回False
        令牌按时间连续累积，每秒产生token_generation_rate个令牌
        返回: True表示获取成功并已消耗令牌，False表示令牌不足
        """
        async with self.lock:
            current_time = time.time()
            
            # 计算自上次更新以来的时间差
            time_passed = current_time - self.last_token_update_time
            
            # 根据时间差累积令牌（不超过最大容量）
            tokens_to_add = time_passed * self.token_generation_rate
            token_pool_before = self.token_pool
            self.token_pool = min(self.max_token_pool, self.token_pool + tokens_to_add)
            self.last_token_update_time = current_time
            
            # Debug日志：记录令牌获取过程
            self.logger.debug(
                f"获取令牌请求: 需要 {required_tokens} 个, "
                f"时间差 {time_passed:.3f}s, "
                f"累积 {tokens_to_add:.2f} 个, "
                f"令牌池: {token_pool_before:.2f} -> {self.token_pool:.2f} (最大 {self.max_token_pool})"
            )
            
            # 检查是否有足够的令牌
            if self.token_pool >= required_tokens:
                # 立即消耗令牌
                self.token_pool -= required_tokens
                self.logger.debug(
                    f"令牌获取成功: 消耗 {required_tokens} 个, "
                    f"剩余令牌池: {self.token_pool:.2f}"
                )
                return True
            
            # 令牌不足
            tokens_needed = required_tokens - self.token_pool
            self.logger.debug(
                f"令牌获取失败: 需要 {required_tokens} 个, "
                f"当前可用 {self.token_pool:.2f} 个, "
                f"还差 {tokens_needed:.2f} 个, "
                f"预计等待时间: {tokens_needed / self.token_generation_rate:.2f}s"
            )
            return False
    
    async def deduct_error_penalty(self, penalty_tokens: int = 220):
        """
        扣除错误惩罚令牌，用于防止触发ESI错误速率限制
        当检测到非2xx/3xx响应时，扣除惩罚令牌以延后后续请求
        参数:
            penalty_tokens: 惩罚令牌数量，默认220（60 * 300 / 100，向上取整）
        """
        async with self.lock:
            # 更新令牌池（先累积令牌）
            current_time = time.time()
            time_passed = current_time - self.last_token_update_time
            tokens_to_add = time_passed * self.token_generation_rate
            token_pool_before = self.token_pool
            self.token_pool = min(self.max_token_pool, self.token_pool + tokens_to_add)
            token_pool_after_update = self.token_pool
            self.last_token_update_time = current_time
            
            # 扣除惩罚令牌（允许为负数，表示需要等待更长时间）
            self.token_pool -= penalty_tokens
            
            # Debug日志：记录错误惩罚过程
            self.logger.debug(
                f"错误惩罚: 扣除 {penalty_tokens} 个令牌, "
                f"时间差 {time_passed:.3f}s, "
                f"累积 {tokens_to_add:.2f} 个, "
                f"令牌池: {token_pool_before:.2f} -> {token_pool_after_update:.2f} -> {self.token_pool:.2f}"
            )
            
            # Warning日志：记录错误响应
            self.logger.warning(
                f"检测到ESI错误响应，扣除 {penalty_tokens} 个令牌，"
                f"当前令牌池: {self.token_pool:.2f}, "
                f"预计恢复时间: {max(0, -self.token_pool) / self.token_generation_rate:.2f}s"
            )
    
    async def add_request(self, req: EsiRequest):
        """添加请求到队列（按函数名分组）"""
        async with self.queue_lock:
            func_name = req.func_name
            # 如果这个函数类型还没有队列，添加到轮询列表
            if func_name not in self.request_queues or len(self.request_queues[func_name]) == 0:
                if func_name not in self.request_queue_keys:
                    self.request_queue_keys.append(func_name)
            self.request_queues[func_name].append(req)
            self.queue_event.set()  # 通知队列处理协程

    def _get_next_request(self) -> Optional[EsiRequest]:
        """
        轮询获取下一个请求，确保不同函数类型的请求都能得到公平处理
        返回: 下一个要处理的请求，如果没有则返回None
        """
        if not self.request_queue_keys:
            return None
        
        # 轮询所有有请求的函数类型
        attempts = 0
        max_attempts = len(self.request_queue_keys)
        
        while attempts < max_attempts:
            # 取出第一个函数名，尝试获取其队列中的请求
            func_name = self.request_queue_keys[0]
            self.request_queue_keys.rotate(-1)  # 将第一个移到末尾，实现轮询
            
            queue = self.request_queues[func_name]
            if queue:
                req = queue.popleft()
                # 如果这个函数类型的队列空了，从轮询列表中移除
                if not queue:
                    self.request_queue_keys.remove(func_name)
                    max_attempts -= 1
                return req
            else:
                # 队列为空，从轮询列表中移除
                self.request_queue_keys.remove(func_name)
                max_attempts -= 1
            
            attempts += 1
        
        return None

    def process_request(self, req: EsiRequest):
        self.processing_queue.append(req)
        self.process_event.set()

    async def _process_request(self):
        """处理请求队列的协程"""
        self.logger.info("开始处理ESI处理队列")

        active_set = set()
        async def single_process(req):
            try:
                result = await req.func()
                
                # 检测错误响应：如果返回值是元组且包含状态码，检查是否为非2xx/3xx响应
                # 注意：只有直接调用 get_request_async 并返回 (data, pages, status_code) 的函数才会被检测
                # 其他函数如果返回 None，也可能表示错误，但为了准确性，我们只检测明确包含状态码的情况
                if isinstance(result, tuple) and len(result) >= 3:
                    status_code = result[2]
                    # 检查状态码是否为非2xx/3xx响应
                    if isinstance(status_code, int) and not (200 <= status_code < 400):
                        # 检测到错误响应，扣除惩罚令牌
                        await self.deduct_error_penalty(220)
                        self.logger.warning(f"检测到ESI错误响应，状态码: {status_code}，已扣除惩罚令牌")
                
                if not req.future.done():
                    req.future.set_result(result)
            except Exception as e:
                # 异常也视为错误，扣除惩罚令牌
                await self.deduct_error_penalty(220)
                self.logger.warning(f"ESI请求异常: {str(e)}，已扣除惩罚令牌")
                
                if not req.future.done():
                    req.future.set_exception(e)
                else:
                    self.logger.error(f"Future already done when setting exception: {str(e)}", exc_info=True)
        def done_call_back(task):
            try:
                active_set.discard(task)
            except Exception:
                pass

        while True:
            # 如果队列为空，等待新请求
            if not self.processing_queue:
                # self.logger.debug("处理队列为空，等待中。")
                self.process_event.clear()
                await self.process_event.wait()
                # self.logger.debug("获得处理任务，进行处理。")
        
            try:
                # 获取当前队列中的所有请求，但最多处理30个，避免内存占用过高
                batch_size = min(len(self.processing_queue), 30)

                # 为每个请求获取token
                for _ in range(batch_size):
                    if not self.processing_queue:
                        break
                    # 检查队列中第一个请求是否有足够的令牌
                    req = self.processing_queue[0]  # 查看但不移除
                    # 获取指定数量的令牌
                    if await self.get_tokens(req.required_tokens):
                        # 令牌足够，移除请求并处理
                        req = self.processing_queue.popleft()
                        task = asyncio.create_task(single_process(req))
                        active_set.add(task)
                        task.add_done_callback(done_call_back)
                    else:
                        # 令牌不足，跳过这个请求，等待下次循环（令牌会继续累积）
                        break

                await asyncio.sleep(1)

            except asyncio.CancelledError:
                self.logger.info("ESI请求队列处理协程被取消")
                # 等待所有活动任务完成
                if active_set:
                    await asyncio.gather(*active_set, return_exceptions=True)
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
        """处理请求队列的协程（使用轮询调度）"""
        self.logger.info("开始处理ESI请求队列")
        while True:
            # 使用轮询方式获取下一个请求
            async with self.queue_lock:
                req = self._get_next_request()
            
            if req is None:
                # 没有请求，等待新请求
                self.logger.debug("请求队列为空，等待中。")
                self.queue_event.clear()
                await self.queue_event.wait()
                self.logger.debug("获得请求任务，进行处理。")
                continue

            try:
                # 执行ESI函数
                try:
                    self.process_request(req)
                except Exception as e:
                    req.future.set_exception(e)
                    self.logger.error(f"执行ESI请求时出错: {str(e)}", exc_info=True)

            except asyncio.CancelledError:
                self.logger.info("ESI请求队列处理协程被取消")
                # 将所有未处理的请求设置为取消状态
                async with self.queue_lock:
                    for queue in self.request_queues.values():
                        while queue:
                            req = queue.popleft()
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
def esi_request(limit: int = 5):
    """
    装饰器，将ESI函数调用转换为队列请求
    参数:
        limit: 该接口每秒请求上限，默认值为5
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 计算该接口需要的令牌数量
            # required_tokens = token_generation_rate / limit，向上取整，确保至少为1
            token_generation_rate = esi_manager.token_generation_rate
            required_tokens = max(1, math.ceil(token_generation_rate / limit))
            
            # 创建future对象，用于返回结果
            future = asyncio.get_running_loop().create_future()

            # 创建请求对象 - 这里使用一个内部函数来确保正确执行原始函数
            async def execute_func():
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"执行ESI函数时出错: {str(e)}", exc_info=True)
                    raise

            req = EsiRequest(execute_func, args, kwargs, future, required_tokens=required_tokens, limit=limit)

            # 将请求添加到队列
            await esi_manager.add_request(req)
            
            # 等待请求完成并返回结果
            try:
                return await future
            except Exception as e:
                # 确保异常被正确传播
                raise
        
        return wrapper
    
    # 支持不带括号的装饰器用法 @esi_request 和带参数的用法 @esi_request(limit=5)
    if callable(limit):
        # 如果直接传入函数，说明是 @esi_request 的用法，使用默认limit=5
        func = limit
        limit = 5
        return decorator(func)
    else:
        # 如果传入的是参数，说明是 @esi_request(limit=5) 的用法
        return decorator

# 确保应用启动时初始化ESI管理器
async def init_esi_manager():
    await esi_manager.start()

# 确保应用关闭时停止ESI管理器
async def shutdown_esi_manager():
    await esi_manager.stop()