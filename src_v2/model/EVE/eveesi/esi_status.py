import asyncio
import time

import aiohttp

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.log import logger
from src_v2.core.utils import EsiUnavailableError

_STATUS_KEY = "esi_server_status"
_STATUS_LOCK = asyncio.Lock()
TQ_STATUS_URL = "https://esi.evetech.net/status/"
_TIMEOUT = aiohttp.ClientTimeout(total=5)

# 本地内存缓存，Redis 不可达时的降级方案
_LOCAL_CACHE = {
    "status": "online",       # 初始默认 optimistic
    "timestamp": 0,
    "redis_failures": 0,
}
_LOCAL_CACHE_TTL = 600        # 10 分钟
_REDIS_RETRY_DELAY = 3.0      # 重试间隔 3 秒
_MAX_REDIS_RETRIES = 3


async def _fetch_tq_status() -> str:
    """Direct HTTP call to ESI /status/, bypassing rate-limit queue"""
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(TQ_STATUS_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return "online" if data.get("players", 0) > 0 else "offline"
                return "offline"
    except asyncio.TimeoutError:
        logger.warning("ESI /status/ 超时")
        return "unknown"
    except Exception:
        logger.warning("ESI /status/ 请求失败")
        return "unknown"


def _get_local_cached_status() -> str | None:
    """返回本地内存缓存的状态，过期则返回 None"""
    if time.time() - _LOCAL_CACHE["timestamp"] < _LOCAL_CACHE_TTL:
        return _LOCAL_CACHE["status"]
    return None


def _set_local_cached_status(status: str):
    """写入本地内存缓存并重置失败计数"""
    _LOCAL_CACHE["status"] = status
    _LOCAL_CACHE["timestamp"] = time.time()
    _LOCAL_CACHE["redis_failures"] = 0


async def check_tq_status() -> str:
    """Check TQ server status with Redis cache + local fallback + thundering herd protection"""
    # ---- 阶段 1: Redis 读取 + 重试 ----
    for attempt in range(_MAX_REDIS_RETRIES):
        try:
            cached = await rdm().get_esi_status_redis().get(_STATUS_KEY)
            if cached:
                status = cached.decode() if isinstance(cached, bytes) else cached
                _set_local_cached_status(status)
                return status
            # key 不存在（有效期为 0），跳出重试直接走锁+回源
            break
        except Exception as e:
            _LOCAL_CACHE["redis_failures"] += 1
            if attempt < _MAX_REDIS_RETRIES - 1:
                logger.warning(
                    f"Redis 不可达 (attempt {attempt + 1}/{_MAX_REDIS_RETRIES})："
                    f"{type(e).__name__}: {str(e)[:200]}，"
                    f"等待 {_REDIS_RETRY_DELAY}s 后重试"
                )
                await asyncio.sleep(_REDIS_RETRY_DELAY)
            else:
                logger.error(
                    f"Redis 连续 {_LOCAL_CACHE['redis_failures']} 次不可达（最后错误: {type(e).__name__}: {str(e)[:200]}），"
                    f"尝试本地缓存降级"
                )
                local = _get_local_cached_status()
                if local:
                    logger.warning(f"降级使用本地缓存: {local}")
                    return local
                logger.error("本地缓存已过期，返回 offline 阻止 ESI 请求")
                return "offline"

    # ---- 阶段 2: 加锁回源（防 thundering herd） ----
    async with _STATUS_LOCK:
        try:
            cached = await rdm().get_esi_status_redis().get(_STATUS_KEY)
            if cached:
                status = cached.decode() if isinstance(cached, bytes) else cached
                _set_local_cached_status(status)
                return status
        except Exception:
            pass

        status = await _fetch_tq_status()
        ttl = 45 if status == "offline" else 60
        try:
            await rdm().get_esi_status_redis().setex(_STATUS_KEY, ttl, status)
            _set_local_cached_status(status)
        except Exception:
            logger.error("Redis 写入 ESI status 失败")
        return status
