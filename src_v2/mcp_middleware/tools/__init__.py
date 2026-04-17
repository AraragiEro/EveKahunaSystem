"""
MCP Tools 注册
"""

from mcp.server.fastmcp import FastMCP
from src_v2.core.log import logger


def register_all_tools(mcp: FastMCP):
    """注册所有 MCP tools"""

    # QQ 相关工具
    try:
        from .qq_tools import register_qq_tools

        register_qq_tools(mcp)
        logger.info("MCP Tools: QQ 相关工具已注册")
    except Exception as e:
        logger.warning(f"MCP Tools: QQ 工具注册失败: {e}")

    # 市场相关工具
    try:
        from .market_tools import register_market_tools

        register_market_tools(mcp)
        logger.info("MCP Tools: 市场相关工具已注册")
    except Exception as e:
        logger.warning(f"MCP Tools: 市场工具注册失败: {e}")

    # 工业相关工具
    try:
        from .industry_tools import register_industry_tools

        register_industry_tools(mcp)
        logger.info("MCP Tools: 工业相关工具已注册")
    except Exception as e:
        logger.warning(f"MCP Tools: 工业工具注册失败: {e}")
