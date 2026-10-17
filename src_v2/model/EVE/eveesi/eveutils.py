import json
from datetime import datetime
import asyncio
from typing import Optional, Any
import aiohttp
import traceback

from src_v2.core.log import logger
from src_v2.core.config.config import config

OUT_PAGE_ERROR = 404
FORBIDDEN_ERROR = 403

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSONEncoder subclass to handle datetime objects."""

    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()  # Convert datetime objects to ISO 8601 strings

        return super().default(o)  # Default serialization for other types


def _notify_esi_manager_rate_info(rate_limit_info):
    """通知 esi_manager 最新的速率限制信息，用于池自动发现。

    get_request_async 返回完整的 rate_limit_info，但上层 ESI API 函数
    通过 data, *_ = await get_request_async(...) 丢弃了这些头部信息。
    这里通过侧信道将信息传递给 esi_manager，确保池自动发现仍能正常工作。
    """
    try:
        from src_v2.model.EVE.eveesi.esi_req_manager import rate_limit_ctx
        rate_limit_ctx.set(rate_limit_info)
    except Exception:
        pass


async def get_request_async(
        url, headers=None, params=None, log=True, max_retries=2, timeout=60, no_retry_code = None
) -> Optional[Any]:
    """
    异步发送GET请求，带有重试机制

    Args:
        url: 请求URL
        headers: 请求头
        params: 查询参数
        log: 是否记录日志
        max_retries: 最大重试次数
        timeout: 超时时间（秒）
    Returns:
        (data, pages, status_code, rate_limit_info): 成功时返回数据和页数及状态码和速率限制信息
        (None, 0, status_code, rate_limit_info): 失败时返回None和状态码和速率限制信息
    """
    PROXY_ADD = config.get("APP", "PROXY", fallback=None)
    PROXY_PORT = config.get("APP", "PORT", fallback=None)
    proxy_url = f"http://{PROXY_ADD}:{PROXY_PORT}" if PROXY_ADD and PROXY_PORT else None
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=timeout),
                                       proxy=proxy_url) as response:
                    status_code = response.status
                    if status_code == 200:
                        try:
                            data = await asyncio.wait_for(response.json(), timeout=timeout)
                            pages = response.headers.get('X-Pages')
                            if pages:
                                pages = int(pages)

                            rate_limit_info = {
                                "group": response.headers.get("X-Ratelimit-Group"),
                                "limit": response.headers.get("X-Ratelimit-Limit"),
                                "remaining": response.headers.get("X-Ratelimit-Remaining"),
                                "used": response.headers.get("X-Ratelimit-Used"),
                                "reset": response.headers.get("X-Ratelimit-Reset"),
                                "error_remain": response.headers.get("X-ESI-Error-Limit-Remain"),
                                "error_reset": response.headers.get("X-ESI-Error-Limit-Reset"),
                                "retry_after": response.headers.get("Retry-After"),
                            }
                            _notify_esi_manager_rate_info(rate_limit_info)
                            return data, pages, status_code, rate_limit_info
                        except asyncio.TimeoutError:
                            if log:
                                logger.warning(f"JSON解析超时 (尝试 {attempt + 1}/{max_retries}): {url}")
                            if attempt == max_retries - 1:
                                raise
                            continue
                    elif no_retry_code and status_code in no_retry_code:
                        rate_limit_info = {
                            "group": response.headers.get("X-Ratelimit-Group"),
                            "limit": response.headers.get("X-Ratelimit-Limit"),
                            "remaining": response.headers.get("X-Ratelimit-Remaining"),
                            "used": response.headers.get("X-Ratelimit-Used"),
                            "reset": response.headers.get("X-Ratelimit-Reset"),
                            "error_remain": response.headers.get("X-ESI-Error-Limit-Remain"),
                            "error_reset": response.headers.get("X-ESI-Error-Limit-Reset"),
                            "retry_after": response.headers.get("Retry-After"),
                        }
                        _notify_esi_manager_rate_info(rate_limit_info)
                        return [], 0, status_code, rate_limit_info
                    else:
                        response_text = await response.text()
                        if log:
                            logger.warning(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {url}")
                            logger.warning(f'{status_code}:{response_text}')
                        if attempt == max_retries - 1:
                            rate_limit_info = {
                                "group": response.headers.get("X-Ratelimit-Group"),
                                "limit": response.headers.get("X-Ratelimit-Limit"),
                                "remaining": response.headers.get("X-Ratelimit-Remaining"),
                                "used": response.headers.get("X-Ratelimit-Used"),
                                "reset": response.headers.get("X-Ratelimit-Reset"),
                                "error_remain": response.headers.get("X-ESI-Error-Limit-Remain"),
                                "error_reset": response.headers.get("X-ESI-Error-Limit-Reset"),
                                "retry_after": response.headers.get("Retry-After"),
                            }
                            _notify_esi_manager_rate_info(rate_limit_info)
                            return None, 0, status_code, rate_limit_info
                        await asyncio.sleep(1 * (attempt + 1))  # 指数退避
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if log:
                logger.error(f"请求异常 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                if log:
                    logger.error(traceback.format_exc())
                _notify_esi_manager_rate_info({})
                return [], 0, 0, {}  # 网络错误，状态码为0
            await asyncio.sleep(1 * (attempt + 1))  # 指数退避
        except Exception:
            if log:
                logger.error(traceback.format_exc())
            _notify_esi_manager_rate_info({})
            return [], 0, 0, {}  # 其他异常，状态码为0

async def parse_token(token):
    if not isinstance(token, str):
        return await token
    else:
        return token