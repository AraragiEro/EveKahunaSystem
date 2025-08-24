import functools
import json
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import re

from ..log_server import logger

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSONEncoder subclass to handle datetime objects."""

    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()  # Convert datetime objects to ISO 8601 strings

        return super().default(o)  # Default serialization for other types

def parse_iso_datetime(dt_string):
    try:
        # 移除所有时区相关信息
        dt_string = re.sub(r'[+-]\d{2}:?\d{2}$|Z$', '', dt_string)
        return datetime.fromisoformat(dt_string)
    except ValueError as e:
        raise ValueError(f"无法解析时间字符串 '{dt_string}': {str(e)}")