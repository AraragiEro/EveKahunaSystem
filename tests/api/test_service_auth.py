# -*- coding: utf-8 -*-
"""服务间认证（X-Internal-API-Key）回归测试

背景：`internal_mcp` 与 `api_astrbot` 两个蓝图的调用方是**无法交互式登录的服务容器**
（MCP 中间件 / QQ 机器人），因此不能走 JWT 认证，改用共享服务密钥。

本测试锁定修复后的四条行为，防止回退到"未配置即不校验"的历史漏洞：
1. 未配置密钥 → 503（fail-closed）
2. 缺少 / 密钥错误 → 401
3. 密钥正确 → 通过认证（不再被 401/503 拦截）
4. MODE=warn → 仅告警放行（灰度期行为）
"""
from unittest.mock import patch

import pytest

# 两个受保护的蓝图各取一个端点（method 必须与真实路由一致）
TARGETS = [
    ("GET", "/api/internal/mcp/qq/vip?qq=1"),
    ("POST", "/api/astrbot/kahunasystem/qq/vip"),
]

MCP_GET = "/api/internal/mcp/qq/vip?qq=1"


async def _request(client, method: str, endpoint: str, headers: dict = None):
    """按真实 HTTP 方法发起请求（方法不匹配会得到 405，绕过 before_request 钩子）"""
    if method == "GET":
        return await client.get(endpoint, headers=headers or {})
    return await client.post(endpoint, headers=headers or {}, json={"QQ": 1})


@pytest.mark.api
class TestServiceAuth:
    """服务间认证行为"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,endpoint", TARGETS)
    async def test_key_not_configured_rejects_all(self, test_client, method, endpoint):
        """未配置 [SERVICE] API_KEY → 503（绝不退回"无校验"）"""
        with patch("src_v2.backend.auth.get_service_api_key", return_value=""):
            resp = await _request(test_client, method, endpoint)

        assert resp.status_code == 503
        data = await resp.get_json()
        assert "not configured" in data["message"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,endpoint", TARGETS)
    async def test_missing_header_rejected(self, test_client, method, endpoint):
        """配置了密钥但请求未携带 header → 401"""
        with patch("src_v2.backend.auth.get_service_api_key", return_value="correct-key"):
            resp = await _request(test_client, method, endpoint)

        assert resp.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,endpoint", TARGETS)
    async def test_wrong_key_rejected(self, test_client, method, endpoint):
        """密钥错误 → 401"""
        with patch("src_v2.backend.auth.get_service_api_key", return_value="correct-key"):
            resp = await _request(
                test_client, method, endpoint, {"X-Internal-API-Key": "wrong-key"}
            )

        assert resp.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,endpoint", TARGETS)
    async def test_correct_key_passes_auth(self, test_client, method, endpoint):
        """密钥正确 → 通过认证层（业务层结果不计，只要不是 401/503/405）"""
        with patch("src_v2.backend.auth.get_service_api_key", return_value="correct-key"):
            resp = await _request(
                test_client, method, endpoint, {"X-Internal-API-Key": "correct-key"}
            )

        assert resp.status_code not in (401, 503, 405), (
            f"认证层不应拦截正确密钥，实际 {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_warn_mode_allows_with_wrong_key(self, test_client):
        """MODE=warn（灰度期）→ 密钥错误仅告警放行，不拦截"""
        with (
            patch("src_v2.backend.auth.get_service_api_key", return_value="correct-key"),
            patch("src_v2.backend.auth.config") as mock_config,
        ):
            mock_config.get.return_value = "warn"
            resp = await _request(
                test_client, "GET", MCP_GET, {"X-Internal-API-Key": "wrong-key"}
            )

        assert resp.status_code not in (401, 503)

    @pytest.mark.asyncio
    async def test_enforce_mode_blocks_with_wrong_key(self, test_client):
        """MODE=enforce（默认）→ 密钥错误必须拦截"""
        with (
            patch("src_v2.backend.auth.get_service_api_key", return_value="correct-key"),
            patch("src_v2.backend.auth.config") as mock_config,
        ):
            mock_config.get.return_value = "enforce"
            resp = await _request(
                test_client, "GET", MCP_GET, {"X-Internal-API-Key": "wrong-key"}
            )

        assert resp.status_code == 401


@pytest.mark.api
class TestInternalMcpNoIpWhitelist:
    """确认 IP 白名单已从认证逻辑中移除（反代后 remote_addr 不可信）"""

    def test_internal_mcp_has_no_allowed_ips(self):
        from src_v2.backend.api import internal_mcp

        assert not hasattr(internal_mcp, "_ALLOWED_IPS"), "不应再保留 IP 白名单常量"
        assert not hasattr(internal_mcp, "_mcp_auth"), "旧的 _mcp_auth 钩子应已移除"
