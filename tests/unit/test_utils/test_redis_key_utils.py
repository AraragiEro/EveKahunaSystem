# -*- coding: utf-8 -*-
"""
Redis Key 构建工具单元测试

测试 src_v2.core.utils.redis_key_utils 中的 key builder 函数。
"""

import pytest
from src_v2.core.utils.redis_key_utils import (
    QQ_BIND_REDIS_PREFIX,
    API_INFO_TOKEN_REDIS_PREFIX,
    build_qq_bind_key,
    build_api_info_token_key,
)


@pytest.mark.unit
class TestBuildQqBindKey:
    """QQ 绑定 Redis Key 构建函数测试"""

    def test_normal_uuid(self):
        """普通 UUID → 正确拼接"""
        uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        expected = f"{QQ_BIND_REDIS_PREFIX}:{uuid}"
        assert build_qq_bind_key(uuid) == expected

    def test_empty_string(self):
        """空字符串 → 前缀后带冒号"""
        assert build_qq_bind_key("") == f"{QQ_BIND_REDIS_PREFIX}:"

    def test_special_chars(self):
        """含特殊字符的 UUID → 原样拼接，不做转义"""
        uuid = "abc_def!@#$%^&*()_+-=~"
        expected = f"{QQ_BIND_REDIS_PREFIX}:{uuid}"
        assert build_qq_bind_key(uuid) == expected

    def test_numeric_string(self):
        """纯数字字符串 → 正确拼接"""
        uuid = "1234567890"
        expected = f"{QQ_BIND_REDIS_PREFIX}:{uuid}"
        assert build_qq_bind_key(uuid) == expected

    def test_constant_not_mutated(self):
        """前缀常量是独立字符串，调用函数不改变常量值"""
        before = QQ_BIND_REDIS_PREFIX
        build_qq_bind_key("anything")
        assert QQ_BIND_REDIS_PREFIX == before


@pytest.mark.unit
class TestBuildApiInfoTokenKey:
    """API Token Redis Key 构建函数测试"""

    def test_normal_token(self):
        """普通 access_token → 正确拼接"""
        token = "eve_access_token_abc123"
        expected = f"{API_INFO_TOKEN_REDIS_PREFIX}:{token}"
        assert build_api_info_token_key(token) == expected

    def test_empty_string(self):
        """空字符串 → 前缀后带冒号"""
        assert build_api_info_token_key("") == f"{API_INFO_TOKEN_REDIS_PREFIX}:"

    def test_long_token(self):
        """长 token 字符串 → 正确拼接"""
        token = "x" * 1000
        expected = f"{API_INFO_TOKEN_REDIS_PREFIX}:{token}"
        result = build_api_info_token_key(token)
        assert result == expected
        assert len(result) == len(API_INFO_TOKEN_REDIS_PREFIX) + 1 + 1000

    def test_token_with_spaces(self):
        """含空格的 token → 按原字符串拼接"""
        token = "access token with spaces"
        expected = f"{API_INFO_TOKEN_REDIS_PREFIX}:{token}"
        assert build_api_info_token_key(token) == expected

    def test_constant_not_mutated(self):
        """前缀常量是独立字符串，调用函数不改变常量值"""
        before = API_INFO_TOKEN_REDIS_PREFIX
        build_api_info_token_key("anything")
        assert API_INFO_TOKEN_REDIS_PREFIX == before
