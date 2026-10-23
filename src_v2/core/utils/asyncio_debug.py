# -*- coding: utf-8 -*-
"""诊断工具：把 asyncio **协程栈** dump 到日志（SIGUSR1 触发）。

背景：2026-10-19 成本计算子进程静默卡死排查中，faulthandler 只能看到
线程栈（事件循环停在 selectors.select），看不到是哪个协程在等什么。
这个钩子把 `asyncio.all_tasks()` 里每个任务的协程栈打出来，
用 `kill -USR1 <pid>` 触发，输出走 logger（落到 app_logs）。

只在**子进程**里安装，主进程不受影响；未收到信号时零开销。
"""

import asyncio
import io
import os
import signal
import traceback

from src_v2.core.log import logger


def install_task_dumper(sig=signal.SIGUSR1):
    """安装 SIGUSR1 处理器：dump 当前事件循环所有任务栈。"""

    def _handler(signum, frame):
        try:
            try:
                loop = asyncio.get_event_loop_policy().get_event_loop()
            except Exception:
                loop = None

            try:
                tasks = asyncio.all_tasks(loop) if loop is not None else set()
            except Exception:
                tasks = set()

            buf = io.StringIO()
            buf.write(
                f"\n=== asyncio task dump (pid={os.getpid()}, "
                f"tasks={len(tasks)}) ===\n")
            for task in tasks:
                buf.write(f"--- task {task.get_name()}\n")
                try:
                    for frame in task.get_stack():
                        buf.write("".join(traceback.format_stack(frame)))
                except Exception as e:
                    buf.write(f"    (取栈失败: {e})\n")
            logger.error(buf.getvalue())
        except Exception as e:
            logger.error(f"asyncio 任务栈 dump 失败: {e}")

    try:
        signal.signal(sig, _handler)
        logger.info(f"已安装 asyncio 任务栈 dump 钩子（kill -USR1 {os.getpid()}）")
        return True
    except Exception as e:
        logger.warning(f"安装 asyncio 任务栈 dump 钩子失败: {e}")
        return False
