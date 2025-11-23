# -*- coding: utf-8 -*-
"""
版本检测模块
用于检测当前应用版本（社区版或企业版）
"""
import os
from ..config.config import config
from ..log import logger

# 版本类型
EDITION_COMMUNITY = "community"
EDITION_ENTERPRISE = "enterprise"

# 有效版本列表
VALID_EDITIONS = [EDITION_COMMUNITY, EDITION_ENTERPRISE]

def get_edition() -> str:
    """
    获取当前应用版本
    
    Returns:
        str: 版本类型，'community' 或 'enterprise'，默认为 'community'
    """
    try:
        # 尝试从配置文件读取版本信息
        edition = config.get('EDITION', 'Edition', fallback=EDITION_COMMUNITY)
        
        # 验证版本值是否有效
        if edition not in VALID_EDITIONS:
            logger.warning(f"无效的版本配置: {edition}，使用默认值: {EDITION_COMMUNITY}")
            edition = EDITION_COMMUNITY
        
        return edition
    except Exception as e:
        logger.warning(f"读取版本配置失败: {e}，使用默认值: {EDITION_COMMUNITY}")
        return EDITION_COMMUNITY

def is_enterprise() -> bool:
    """
    判断是否为企业版
    
    Returns:
        bool: 如果是企业版返回 True，否则返回 False
    """
    return get_edition() == EDITION_ENTERPRISE

def is_community() -> bool:
    """
    判断是否为社区版
    
    Returns:
        bool: 如果是社区版返回 True，否则返回 False
    """
    return get_edition() == EDITION_COMMUNITY

# 初始化时记录版本信息
_current_edition = get_edition()
logger.info(f"应用版本: {_current_edition}")

