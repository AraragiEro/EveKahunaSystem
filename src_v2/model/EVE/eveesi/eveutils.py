import json
from datetime import datetime, timezone
import asyncio
from typing import Optional, Any
import aiohttp
import traceback

from src_v2.core.log import logger

OUT_PAGE_ERROR = 404
FORBIDDEN_ERROR = 403

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSONEncoder subclass to handle datetime objects."""

    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()  # Convert datetime objects to ISO 8601 strings

        return super().default(o)  # Default serialization for other types

def parse_iso_datetime(dt_string):
    """
    解析 ISO 格式的时间字符串。
    如果字符串包含时区信息，返回时区感知的 datetime 对象。
    如果字符串不包含时区信息，则假定为 UTC 并返回时区感知的 UTC datetime 对象。
    """
    try:
        dt_obj = datetime.fromisoformat(dt_string)
        if dt_obj.tzinfo is None:
            # 如果解析后是 offset-naive，则假定它代表 UTC
            return dt_obj.replace(tzinfo=timezone.utc)
        return dt_obj
    except ValueError as e:
        raise ValueError(f"无法解析时间字符串 '{dt_string}': {str(e)}")


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
    """
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    if response.status == 200:
                        try:
                            data = await asyncio.wait_for(response.json(), timeout=timeout)
                            pages = response.headers.get('X-Pages')
                            if pages:
                                pages = int(pages)

                            return data, pages
                        except asyncio.TimeoutError:
                            if log:
                                logger.warning(f"JSON解析超时 (尝试 {attempt + 1}/{max_retries}): {url}")
                            if attempt == max_retries - 1:
                                raise
                            continue
                    elif no_retry_code and response.status in no_retry_code:
                        return [], 0
                    else:
                        response_text = await response.text()
                        if log:
                            logger.warning(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {url}")
                            logger.warning(f'{response.status}:{response_text}')
                        if attempt == max_retries - 1:
                            return None, 0
                        await asyncio.sleep(1 * (attempt + 1))  # 指数退避
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if log:
                logger.error(f"请求异常 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                if log:
                    logger.error(traceback.format_exc())
                return [], 0
            await asyncio.sleep(1 * (attempt + 1))  # 指数退避
        except Exception as e:
            if log:
                logger.error(traceback.format_exc())
            return [], 0

async def parse_token(token):
    if not isinstance(token, str):
        return await token
    else:
        return token