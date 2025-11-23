import logging
import os
import colorlog

# from astrbot.core import logger as astrbot_logger
from tqdm.asyncio import tqdm

plugin_name = "kahuna_bot"

log_color_config = {
    "DEBUG": "green",
    "INFO": "bold_cyan",
    "WARNING": "bold_yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
    "RESET": "reset",
    "asctime": "green",
}


def get_logger():
    # 创建一个名为 'kahuna_bot' 的 logger
    logger = logging.getLogger('kahuna_bot')

    # 避免重复初始化
    if logger.hasHandlers():
        return logger

    # 设置 logger 级别
    logger.setLevel(logging.INFO)

    # 创建一个输出到控制台的处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    # 创建一个格式化器并添加到处理器
    formatter = colorlog.ColoredFormatter(
        fmt=f"%(log_color)s [%(asctime)s] [{plugin_name}] [%(levelname)s] [%(filename)s:%(lineno)d]: %(message)s %(reset)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors=log_color_config,
    )
    console_handler.setFormatter(formatter)

    # 自定义文件名过滤器
    class FileNameFilter(logging.Filter):
        def filter(self, record):
            # 获取文件名（不含路径）
            record.filename = os.path.basename(record.pathname)
            return True

    # 添加过滤器
    console_handler.addFilter(FileNameFilter())
    # 自定义 emit 方法用于 tqdm 兼容
    def tqdm_emit(self, record):
        try:
            msg = self.format(record)
            # 使用 tqdm.write 来避免与进度条冲突
            tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)

    # 替换 console_handler 的 emit 方法
    console_handler.emit = tqdm_emit.__get__(console_handler, logging.StreamHandler)

    # 添加处理器到 logger
    logger.addHandler(console_handler)

    # 防止日志向上传播（避免重复输出）
    logger.propagate = False

    return logger


# 创建全局 logger 实例
logger = get_logger()
