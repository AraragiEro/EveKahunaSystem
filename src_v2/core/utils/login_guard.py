# -*- coding: utf-8 -*-
"""登录 / 注册限流守卫（Redis 固定窗口计数）

设计：
- 固定窗口：第一次 ``hit`` 时 ``INCR`` 并 ``EXPIRE``，窗口内累计计数；
- **fail-open**：Redis 未初始化或任何异常时一律放行（返回 True），只记 warning，
  绝不因为限流组件故障让登录/注册返回 500；
- key 由调用方传入（如 ``login_fail:user:{username}``、``login_fail:ip:{ip}``），
  本模块不再额外加前缀，便于运维直接按 key 排查与手动清零。
"""

from quart import request

from src_v2.core.database.connect_manager import get_redis_manager
from src_v2.core.log import logger


async def client_ip() -> str:
    """获取客户端 IP（Quart 请求上下文外或取不到时返回 'unknown'）"""
    try:
        addr = request.remote_addr
        return addr or 'unknown'
    except Exception:
        return 'unknown'


async def hit(key: str, limit: int, window_seconds: int) -> bool:
    """固定窗口计数：放行并 +1 → True；已超限 → False

    :param key: 计数 key（调用方负责命名）
    :param limit: 窗口内允许的次数上限
    :param window_seconds: 窗口长度（秒）
    """
    if not key or limit <= 0 or window_seconds <= 0:
        return True

    try:
        redis = get_redis_manager().redis
        current = await redis.incr(key)
        if int(current) == 1:
            # 首次计数才设置过期，保证固定窗口而不是滑动续期
            await redis.expire(key, window_seconds)
        return int(current) <= limit
    except Exception as e:
        logger.warning(f"限流计数失败（fail-open 放行）key={key}: {e}")
        return True


async def reset(key: str) -> None:
    """清空计数（登录成功、人工解锁）"""
    if not key:
        return

    try:
        redis = get_redis_manager().redis
        await redis.delete(key)
    except Exception as e:
        logger.warning(f"限流计数重置失败（忽略）key={key}: {e}")
