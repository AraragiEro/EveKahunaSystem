# -*- coding: utf-8 -*-
"""
verify_jwt_token 单元测试

测试 JWT token 验证函数在各种场景下的行为：
- 有效/过期/无效密钥/格式错误/空 token
- 自定义 payload 字段保持
"""

import datetime

import jwt
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.unit
class TestVerifyJwtToken:
    """verify_jwt_token 函数单元测试"""

    SECRET = "test-secret"

    def _call_verify(self, token):
        """
        在 mock app 上下文内调用 verify_jwt_token。

        由于 ``from quart import current_app as app`` 是一个 werkzeug
        LocalProxy，直接 patch 会被 _is_async_obj 触发 "Not within an app
        context" 错误。这里用 new=MagicMock 跳过对原始对象的访问。
        """
        fake_app = MagicMock(config={"SECRET_KEY": self.SECRET})
        with patch("src_v2.backend.auth.app", new=fake_app):
            from src_v2.backend.auth import verify_jwt_token

            return verify_jwt_token(token)

    # ------------------------------------------------------------------
    # 正常场景
    # ------------------------------------------------------------------
    def test_valid_token_returns_payload(self):
        """有效 token → 返回 payload 字典"""
        payload = {"user_name": "test_user", "role": "admin"}
        token = jwt.encode(payload, self.SECRET, algorithm="HS256")

        result = self._call_verify(token)

        assert result is not None
        assert result["user_name"] == "test_user"
        assert result["role"] == "admin"

    def test_valid_token_with_custom_fields(self):
        """带自定义字段的有效 token → 所有字段保持"""
        payload = {
            "user_name": "test_user",
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=1),
            "custom_field": "hello",
            "nested": {"key": "value"},
        }
        token = jwt.encode(payload, self.SECRET, algorithm="HS256")

        result = self._call_verify(token)

        assert result is not None
        assert result["user_name"] == "test_user"
        assert result["custom_field"] == "hello"
        assert result["nested"] == {"key": "value"}

    def test_valid_token_without_expiry(self):
        """无过期时间的有效 token → 返回 payload"""
        payload = {"user_name": "test_user"}
        token = jwt.encode(payload, self.SECRET, algorithm="HS256")

        result = self._call_verify(token)

        assert result is not None
        assert result["user_name"] == "test_user"

    # ------------------------------------------------------------------
    # 异常场景 —— 全部应返回 None
    # ------------------------------------------------------------------
    def test_expired_token_returns_none(self):
        """已过期 token → 返回 None"""
        payload = {
            "user_name": "test_user",
            "exp": datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=1),
        }
        token = jwt.encode(payload, self.SECRET, algorithm="HS256")

        result = self._call_verify(token)

        assert result is None

    def test_wrong_secret_returns_none(self):
        """使用错误密钥签名的 token → 返回 None"""
        payload = {"user_name": "test_user"}
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        result = self._call_verify(token)

        assert result is None

    def test_malformed_token_returns_none(self):
        """格式错误的 token（乱码字符串）→ 返回 None"""
        result = self._call_verify("this.is.not.a.valid.jwt")
        assert result is None

    def test_empty_string_returns_none(self):
        """空字符串 token → 返回 None"""
        result = self._call_verify("")
        assert result is None

    def test_none_token_returns_none(self):
        """None 值 token → 返回 None（jwt.decode 抛出异常）"""
        fake_app = MagicMock(config={"SECRET_KEY": self.SECRET})
        with patch("src_v2.backend.auth.app", new=fake_app):
            from src_v2.backend.auth import verify_jwt_token

            result = verify_jwt_token(None)
        assert result is None

    def test_token_with_invalid_algorithm_header(self):
        """token 使用不支持的算法 → 返回 None"""
        import base64

        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
        payload = (
            base64.urlsafe_b64encode(b'{"user_name":"test_user"}')
            .rstrip(b"=")
            .decode()
        )
        sig = base64.urlsafe_b64encode(b"fake-signature").rstrip(b"=").decode()
        fake_token = f"{header}.{payload}.{sig}"

        result = self._call_verify(fake_token)
        assert result is None
