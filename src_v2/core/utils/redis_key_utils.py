# -*- coding: utf-8 -*-
"""
Redis Key 构造工具

集中管理各模块 Redis Key 的前缀与构造逻辑，
消除 API 层中重复定义的 key 构造函数。
"""

# QQ 绑定相关
QQ_BIND_REDIS_PREFIX = "kahunasystem:qq_bind"


def build_qq_bind_key(bind_uuid: str) -> str:
    """
    构造 QQ 绑定指令的 Redis Key

    :param bind_uuid: 绑定指令 UUID
    :return: Redis Key 字符串
    """
    return f"{QQ_BIND_REDIS_PREFIX}:{bind_uuid}"


# API Token 信息缓存相关
API_INFO_TOKEN_REDIS_PREFIX = "kahunasystem:api_info_token"


def build_api_info_token_key(access_token: str) -> str:
    """
    构造 API Token 信息缓存的 Redis Key

    :param access_token: EVE OAuth access_token
    :return: Redis Key 字符串
    """
    return f"{API_INFO_TOKEN_REDIS_PREFIX}:{access_token}"
