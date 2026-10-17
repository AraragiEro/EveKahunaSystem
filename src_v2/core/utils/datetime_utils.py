# -*- coding: utf-8 -*-
"""
日期时间解析工具

统一项目内 ISO 8601 日期字符串的解析逻辑，
消除 eveutils / contract_manager / api_industry 中重复且不一致的实现。

三种明确语义：
- parse_aware_utc_datetime：解析为带 UTC 时区的 datetime（ESI API 交互）
- parse_naive_utc_datetime：解析为 naive UTC datetime（数据库存储）
- safe_parse_datetime：安全解析，支持 None / 已存在 datetime / 空字符串
"""

from datetime import datetime, timezone
from typing import Any, Optional


def parse_aware_utc_datetime(dt_string: str) -> datetime:
    """
    解析 ISO 格式时间字符串为带 UTC 时区的 datetime

    如果字符串不含时区信息，假定为 UTC。
    用于与 ESI API 交互时保持时区感知。

    :param dt_string: ISO 8601 格式字符串
    :return: timezone-aware UTC datetime
    :raises ValueError: 无法解析时抛出
    """
    if not dt_string:
        raise ValueError("时间字符串不能为空")

    # 处理 Z 后缀
    if isinstance(dt_string, str) and dt_string.endswith("Z"):
        dt_string = dt_string[:-1] + "+00:00"

    dt_obj = datetime.fromisoformat(dt_string)
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
    return dt_obj


def parse_naive_utc_datetime(dt_string: str) -> Optional[datetime]:
    """
    解析 ISO 格式时间字符串为 naive UTC datetime（无时区）

    流程：先解析为 aware UTC，再转换为 UTC 时间，最后去除时区信息。
    适用于 PostgreSQL TIMESTAMP WITHOUT TIME ZONE 字段。

    注意：与直接 dt.replace(tzinfo=None) 不同，本函数会先调用 astimezone(timezone.utc)
    确保时区转换正确，避免 +08:00 等时区被直接剥离导致时间错误。

    :param dt_string: ISO 8601 格式字符串
    :return: naive UTC datetime；空输入返回 None
    """
    if not dt_string:
        return None

    # 处理 Z 后缀
    if isinstance(dt_string, str) and dt_string.endswith("Z"):
        dt_string = dt_string[:-1] + "+00:00"

    dt = datetime.fromisoformat(dt_string)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def safe_parse_datetime(dt_string: Any, default: Optional[datetime] = None) -> Optional[datetime]:
    """
    安全解析日期时间，支持多种输入类型

    - 已是 datetime 对象：直接返回
    - 空字符串 / None：返回 default
    - 字符串：按 parse_naive_utc_datetime 解析

    :param dt_string: 输入值（datetime、str、None 等）
    :param default: 空值或解析失败时的返回值，默认 None
    :return: naive UTC datetime 或 default
    """
    if dt_string is None or dt_string == "":
        return default

    if isinstance(dt_string, datetime):
        if dt_string.tzinfo is not None:
            return dt_string.astimezone(timezone.utc).replace(tzinfo=None)
        return dt_string

    if not isinstance(dt_string, str):
        return default

    try:
        return parse_naive_utc_datetime(dt_string)
    except ValueError:
        return default
