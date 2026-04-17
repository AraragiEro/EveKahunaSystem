"""
MCP 中间层配置

通过环境变量或 .env 文件配置
"""

import os
from typing import Optional


class MCPMiddlewareConfig:
    """MCP 中间层配置"""

    def __init__(self):
        # MCP 服务配置
        self.mcp_host: str = os.getenv("MCP_HOST", "0.0.0.0")
        self.mcp_port: int = int(os.getenv("MCP_PORT", "9000"))

        # Quart 后端配置
        self.quart_base_url: str = os.getenv("QUART_BASE_URL", "http://localhost:9527")

        # 认证配置（可选）
        self.quart_api_key: str = os.getenv("QUART_API_KEY", "")

        # 超时配置
        self.request_timeout: float = float(os.getenv("MCP_REQUEST_TIMEOUT", "30.0"))

    def __repr__(self) -> str:
        return (
            f"MCPMiddlewareConfig("
            f"mcp_host={self.mcp_host}, "
            f"mcp_port={self.mcp_port}, "
            f"quart_base_url={self.quart_base_url}"
            f")"
        )


# 全局配置实例
config = MCPMiddlewareConfig()
