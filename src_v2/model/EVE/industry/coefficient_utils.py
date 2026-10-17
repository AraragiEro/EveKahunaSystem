# -*- coding: utf-8 -*-
"""
星系系数查询工具模块

提供独立的星系系数查询函数，用于获取星系制造/反应系数。
数据源为 Redis 缓存（由 plan_configflow_operate.py 的 refresh_system_cost 填充）。

Functions:
    get_system_coefficient(solar_system_id) -> dict[str, float | None]
    get_system_info_batch(system_ids) -> list[dict]
"""

from typing import Dict, List, Optional

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.model.EVE.sde.utils import SdeUtils

# Redis Hash key 模板（由 refresh_system_cost 写入）
SYSTEM_COST_CACHE_KEY = "system_cost_cache:%d"


async def get_system_coefficient(solar_system_id: int) -> Dict[str, Optional[float]]:
    """从 Redis 获取星系制造/反应系数。

    Args:
        solar_system_id: EVE 星系 ID（例如 30000142 = 吉他）

    Returns:
        {"manufacturing": float | None, "reaction": float | None}
        当 Redis 中无缓存数据或查询异常时，两个字段均为 None。
    """
    try:
        redis_client = rdm().r
        data = await redis_client.hgetall(SYSTEM_COST_CACHE_KEY % solar_system_id)
    except Exception:
        return {"manufacturing": None, "reaction": None}

    if not data:
        return {"manufacturing": None, "reaction": None}

    # 兼容 str-key（decode_responses=True）和 bytes-key（原始响应）
    manufacturing = data.get("manufacturing") or data.get(b"manufacturing")
    reaction = data.get("reaction") or data.get(b"reaction")

    return {
        "manufacturing": float(manufacturing) if manufacturing is not None else None,
        "reaction": float(reaction) if reaction is not None else None,
    }


async def get_system_info_batch(system_ids: List[int]) -> List[dict]:
    """批量获取星系基本信息（星系名、区域名）。

    Args:
        system_ids: EVE 星系 ID 列表

    Returns:
        [{system_id, system_name, region_name}, ...]
        未知或不存在的星系 ID 会被静默跳过。
    """
    if not system_ids:
        return []

    results: List[dict] = []
    for system_id in system_ids:
        info = await SdeUtils.get_system_info_by_id(system_id)
        if info:
            results.append({
                "system_id": info.get("system_id"),
                "system_name": info.get("system_name"),
                "region_name": info.get("region_name"),
            })
    return results
