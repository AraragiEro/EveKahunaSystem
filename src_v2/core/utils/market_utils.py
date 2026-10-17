# -*- coding: utf-8 -*-
"""
市场相关工具函数

集中管理市场区域常量、区域转换等通用逻辑，
消除企业版 API 中重复定义的 get_region_id_from_market_zone 函数。
"""

from src_v2.core.utils import KahunaException
from src_v2.model.EVE.eve_constants import REGION_FORGE_ID, REGION_VALE_ID

# 市场区域名称 -> 区域ID 映射表
MARKET_ZONE_TO_REGION_ID = {
    'jita': REGION_FORGE_ID,
    'frt': REGION_VALE_ID,
}


def get_region_id_from_market_zone(market_zone: str) -> int:
    """
    将市场区域名称转换为区域ID

    :param market_zone: 市场区域名称，如 'jita', 'frt'
    :return: 区域ID
    :raises KahunaException: 如果市场区域不支持
    """
    if market_zone not in MARKET_ZONE_TO_REGION_ID:
        raise KahunaException(f"不支持的市场区域: {market_zone}")

    return MARKET_ZONE_TO_REGION_ID[market_zone]
