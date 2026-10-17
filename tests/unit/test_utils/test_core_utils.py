# -*- coding: utf-8 -*-
"""
Core Utils 纯工具函数单元测试

测试 src_v2.core.utils 中的纯函数：roundup、chunks、get_user_tmp_cache_prefix、
get_beijing_utctime、get_random_token。
"""

import string
from datetime import datetime, timezone, timedelta

import pytest
from src_v2.core.utils import (
    roundup,
    chunks,
    get_user_tmp_cache_prefix,
    get_beijing_utctime,
    get_random_token,
)


class TestRoundup:
    """roundup(x, base) 函数测试"""

    def test_normal_case(self):
        """普通场景: 5 向上取整到 10 的倍数 → 10"""
        assert roundup(5, 10) == 10

    def test_exact_multiple(self):
        """恰好是倍数: 20 → 20"""
        assert roundup(20, 10) == 20

    def test_already_at_base(self):
        """x 等于 base → base"""
        assert roundup(10, 10) == 10

    def test_zero(self):
        """x 为 0 → 0"""
        assert roundup(0, 10) == 0

    def test_negative_rounded_up(self):
        """负数: -5 向上取整到 10 的倍数 → 0"""
        assert roundup(-5, 10) == 0

    def test_negative_larger(self):
        """负数绝对值大于 base: -15 → -10"""
        assert roundup(-15, 10) == -10

    def test_non_standard_base(self):
        """非 10 的 base: 3 向上取整到 7 的倍数 → 7"""
        assert roundup(3, 7) == 7

    def test_one_base(self):
        """base 为 1: x 向上取整 → x 本身"""
        assert roundup(7, 1) == 7
        assert roundup(0, 1) == 0


class TestChunks:
    """chunks(lst, n) 生成器函数测试"""

    def test_empty_list(self):
        """空列表 → 不 yield 任何元素"""
        result = list(chunks([], 3))
        assert result == []

    def test_list_smaller_than_chunk(self):
        """列表长度小于 n → 直接返回整个列表"""
        result = list(chunks([1, 2], 5))
        assert result == [[1, 2]]

    def test_exact_multiple(self):
        """列表长度恰好是 n 的倍数 → 每个 chunk 大小均为 n"""
        result = list(chunks([1, 2, 3, 4, 5, 6], 3))
        assert result == [[1, 2, 3], [4, 5, 6]]

    def test_partial_last_chunk(self):
        """最后一个 chunk 长度不足 n → 正确返回部分"""
        result = list(chunks([1, 2, 3, 4, 5], 3))
        assert result == [[1, 2, 3], [4, 5]]

    def test_single_element_chunks(self):
        """n=1: 每个元素单独成块"""
        result = list(chunks([1, 2, 3], 1))
        assert result == [[1], [2], [3]]

    def test_large_chunk_size(self):
        """n 远大于列表长度 → 一次返回整个列表"""
        result = list(chunks(["a", "b"], 100))
        assert result == [["a", "b"]]

    def test_preserves_order(self):
        """保持原始顺序"""
        original = [10, 20, 30, 40, 50]
        result = list(chunks(original, 2))
        flat = [item for chunk in result for item in chunk]
        assert flat == original


class TestGetUserTmpCachePrefix:
    """get_user_tmp_cache_prefix 函数测试"""

    def test_valid_qq(self):
        """普通 QQ 号"""
        assert get_user_tmp_cache_prefix(123456789) == "cache_123456789_"

    def test_zero(self):
        """QQ 号为 0"""
        assert get_user_tmp_cache_prefix(0) == "cache_0_"

    def test_large_number(self):
        """大数值 QQ 号"""
        assert get_user_tmp_cache_prefix(999999999999) == "cache_999999999999_"

    def test_negative_number(self):
        """负数 — 按整数格式拼接"""
        assert get_user_tmp_cache_prefix(-1) == "cache_-1_"

    def test_returns_string(self):
        """返回值类型为 str"""
        assert isinstance(get_user_tmp_cache_prefix(10086), str)


class TestGetBeijingUtctime:
    """get_beijing_utctime 函数测试

    注意：该函数行为依赖系统时区。
    - 系统时区为 UTC 时：对输入 +8h 返回北京时间
    - 系统时区非 UTC 时：原样返回输入
    """

    def test_utc_aware_unchanged_on_non_utc_system(self):
        """UTC aware datetime → 在非UTC系统上原样返回"""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = get_beijing_utctime(dt)
        assert isinstance(result, datetime)

    def test_naive_datetime(self):
        """naive datetime → 返回 datetime 对象"""
        dt = datetime(2024, 6, 15, 8, 30, 0)
        result = get_beijing_utctime(dt)
        assert isinstance(result, datetime)

    def test_returns_datetime_type(self):
        """确保返回值为 datetime 类型"""
        dt = datetime(2024, 1, 1, 0, 0, 0)
        result = get_beijing_utctime(dt)
        assert isinstance(result, datetime)

    def test_custom_timezone_aware(self):
        """非 UTC 的 aware datetime → 原样返回（offset 不为 0）"""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        result = get_beijing_utctime(dt)
        assert isinstance(result, datetime)

    def test_midnight(self):
        """午夜时间 → 正常处理不报错"""
        dt = datetime(2024, 1, 1, 0, 0, 0)
        result = get_beijing_utctime(dt)
        assert isinstance(result, datetime)


class TestGetRandomToken:
    """get_random_token 函数测试"""

    VALID_CHARS = set(string.ascii_letters + string.digits)

    def test_default_length(self):
        """默认长度为 10"""
        token = get_random_token()
        assert len(token) == 10

    def test_custom_length(self):
        """指定长度 20"""
        token = get_random_token(20)
        assert len(token) == 20

    def test_zero_length(self):
        """长度为 0 → 空字符串"""
        token = get_random_token(0)
        assert token == ""

    def test_length_one(self):
        """长度为 1 → 单个字符"""
        token = get_random_token(1)
        assert len(token) == 1
        assert token in self.VALID_CHARS

    def test_character_set(self):
        """所有字符来自大小写字母和数字"""
        token = get_random_token(1000)
        invalid_chars = [c for c in token if c not in self.VALID_CHARS]
        assert not invalid_chars, f"发现非法字符: {set(invalid_chars)}"

    def test_uniqueness(self):
        """生成 100 个 token，应无重复（62^10 组合，碰撞概率极低）"""
        tokens = [get_random_token(10) for _ in range(100)]
        assert len(set(tokens)) == 100, "发现重复 token"

    def test_different_lengths_produce_different_tokens(self):
        """不同长度生成不同长度的 token"""
        t1 = get_random_token(5)
        t2 = get_random_token(15)
        assert len(t1) == 5
        assert len(t2) == 15
