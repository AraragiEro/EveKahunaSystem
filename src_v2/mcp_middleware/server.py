"""
MCP 中间层服务入口

提供 MCP 协议接口，所有工具通过 HTTP 调用 Quart 后端
"""

import asyncio
import argparse
import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from src_v2.core.log import logger
from src_v2.mcp_middleware.config import config
from src_v2.mcp_middleware.tools import register_all_tools


# 创建 MCP Server，禁用 DNS rebinding 保护以允许外部访问
mcp = FastMCP(
    name="kahuna-system-middleware",
    instructions="""
    Kahuna System MCP Middleware - 通过 HTTP 调用 Quart 后端
    
    提供以下功能：
    - 用户 VIP 状态查询
    - 市场数据查询和分析
    - 工业制造计算
    - 资产统计
    """,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


def init_mcp_tools():
    """初始化 MCP tools"""
    logger.info("MCP Middleware: 注册 tools...")
    register_all_tools(mcp)

    # 统计工具数量
    if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "_tools"):
        tool_count = len(mcp._tool_manager._tools)
        logger.info(f"MCP Middleware: 共 {tool_count} 个 tools")


async def start_mcp_server():
    """启动 MCP 中间层服务"""
    import uvicorn

    # 初始化 tools
    init_mcp_tools()

    # 获取 MCP SSE 应用
    mcp_app = mcp.sse_app()

    logger.info("=" * 60)
    logger.info("Starting MCP Middleware Service")
    logger.info("=" * 60)
    logger.info(f"MCP Endpoint: http://{config.mcp_host}:{config.mcp_port}/sse")
    logger.info(f"Quart Backend: {config.quart_base_url}")
    logger.info("=" * 60)

    # 使用 Uvicorn 启动
    uvicorn_config = uvicorn.Config(
        app=mcp_app,
        host=config.mcp_host,
        port=config.mcp_port,
        log_level="info",
        reload=False,
        workers=1,
    )
    server = uvicorn.Server(uvicorn_config)
    await server.serve()


def main():
    parser = argparse.ArgumentParser(description="KahunaBot MCP Middleware")
    parser.add_argument("--host", default="0.0.0.0", help="MCP server host")
    parser.add_argument("--port", type=int, default=9000, help="MCP server port")
    parser.add_argument(
        "--quart-url", default="http://localhost:9527", help="Quart backend URL"
    )

    args = parser.parse_args()

    # 更新配置
    config.mcp_host = args.host
    config.mcp_port = args.port
    config.quart_base_url = args.quart_url

    try:
        asyncio.run(start_mcp_server())
    except KeyboardInterrupt:
        logger.info("MCP Middleware stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
