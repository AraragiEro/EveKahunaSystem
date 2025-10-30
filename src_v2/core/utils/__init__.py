import math
import asyncio
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from math import trunc

from ..log import logger

# import transformers

DEBUG_QQ = None

class KahunaException(Exception):
    def __init__(self, message):
        super(KahunaException, self).__init__(message)
        self.message = message

def roundup(x, base):
    return base * math.ceil(x / base)

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

class PluginMeta(type):  # 定义元类
    def __init__(cls, name, bases, dct):
        super().__init__(name, bases, dct)
        # 每次类被创建时，自动运行 init
        cls.init()

class SingletonMeta(type):
    """
    用于单例类继承
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

async def run_func_delay_min(start_delay, func, *args, **kwargs):
    await asyncio.sleep(start_delay * 60)
    await func(*args, **kwargs)

async def async_refresh_per_min(start_delay: int, interval: int, func):
    logger.info(f'注册异步定时轮询任务: {func.__name__}, 延迟{start_delay}分钟, 循环间隔{interval}分钟')
    await asyncio.sleep(start_delay * 60)
    while True:
        try:
            logger.debug(f'轮询任务{func.__name__} 激活')
            await func()
            await asyncio.sleep(5)
            logger.debug(f'轮询任务{func.__name__} 完成，睡眠{interval}分钟')
            await asyncio.sleep(interval * 60)
        except Exception as e:
            # 打印完整的异常堆栈信息
            error_msg = f"轮询任务 {func.__name__} 执行出错: {str(e)}\n"
            error_msg += traceback.format_exc()
            logger.error(error_msg)

            # 添加短暂休眠，防止在发生错误时过于频繁地重试
            await asyncio.sleep(60)  # 错误后等待1分钟再继续


def get_user_tmp_cache_prefix(user_qq: int):
    return f"cache_{user_qq}_"

def get_beijing_utctime(current: datetime) -> datetime:
    # 检查是否为UTC时间（通过检查系统时区）
    if current.astimezone().utcoffset().total_seconds() == 0:  # 如果是UTC时区
        # 转换为北京时间 (UTC+8)
        current = current + timedelta(hours=8)
    return current

class classproperty(property):
    def __get__(self, instance, cls):
        return self.fget(cls)


class ClassPropertyMetaclass(type):
    def __setattr__(self, key, value):
        if key in self.__dict__:
            obj = self.__dict__.get(key)
            if type(obj) is classproperty:
                return obj.__set__(self, value)
        return super().__setattr__(key, value)

def set_debug_qq(qq: int):
    global DEBUG_QQ
    DEBUG_QQ = qq

def get_debug_qq():
    return DEBUG_QQ

def unset_debug_qq():
    global DEBUG_QQ
    DEBUG_QQ = None

# from .deepseek_tokenizer import tokenizer
# def get_chat_token_count(input: str):
#     result = tokenizer.encode(input)
#     return result
#
# def check_context_token_count(input: str, context_token_limit: int):
#     result = get_chat_token_count(input)
#     return result <= context_token_limit