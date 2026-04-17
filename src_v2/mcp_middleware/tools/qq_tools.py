"""QQ 相关 MCP Tools - 通过 HTTP 调用 Quart 后端"""

from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from src_v2.core.log import logger
from src_v2.mcp_middleware.client import QuartBackendClient


def register_qq_tools(mcp: FastMCP):
    """注册 QQ 相关 MCP tools"""

    @mcp.tool()
    async def qq_vip_state(qq: Annotated[int, Field(description="QQ 号码")]) -> dict:
        """
        通过 QQ 号获取用户 VIP 状态

        内部调用：GET /api/internal/mcp/qq/vip

        Returns:
            {
                "status": 200,
                "is_bind": True,
                "data": {
                    "userName": "用户名",
                    "vipLevel": "Alpha/Omega/Free",
                    "vipLevelCode": "vip_alpha/vip_omega",
                    "vipEndDate": "2024-12-31T23:59:59"
                }
            }
        """
        logger.info(f"MCP Tool: qq_vip_state(qq={qq})")

        try:
            async with QuartBackendClient() as client:
                result = await client.get_qq_vip_state(qq)

            logger.info(
                f"MCP Tool: qq_vip_state 完成，status={result.get('status', 'unknown')}"
            )
            return result
        except Exception as e:
            logger.error(f"MCP Tool: qq_vip_state 失败: {e}")
            return {"status": 500, "message": f"调用失败: {str(e)}"}

    @mcp.tool()
    async def running_jobs_overview(
        qq: Annotated[int, Field(description="QQ 号码")],
    ) -> dict:
        """
        获取用户运行中任务相关数据（制造、反应任务统计）

        Returns:
            {
                "status": 200,
                "data": {
                    "userName": "用户名",
                    "runningValueOverview": {...},
                    "jobsFinishOverview": {...},
                    "roleLinesOverview": {...}
                }
            }
        """
        logger.info(f"MCP Tool: running_jobs_overview(qq={qq})")

        try:
            async with QuartBackendClient() as client:
                result = await client.get_running_jobs_overview(qq)

            logger.info(
                f"MCP Tool: running_jobs_overview 完成，status={result.get('status', 'unknown')}"
            )
            return result
        except Exception as e:
            logger.error(f"MCP Tool: running_jobs_overview 失败: {e}")
            return {"status": 500, "message": f"调用失败: {str(e)}"}

    @mcp.tool()
    async def market_tag_list(qq: Annotated[int, Field(description="QQ 号码")]) -> dict:
        """
        获取用户的市场标签列表（Omega 及以上订阅可用）

        Returns:
            {
                "status": 200,
                "data": [{"id": 1, "tag": "标签名"}]
            }
        """
        logger.info(f"MCP Tool: market_tag_list(qq={qq})")

        try:
            async with QuartBackendClient() as client:
                result = await client.get_market_tag_list(qq)

            logger.info(
                f"MCP Tool: market_tag_list 完成，status={result.get('status', 'unknown')}"
            )
            return result
        except Exception as e:
            logger.error(f"MCP Tool: market_tag_list 失败: {e}")
            return {"status": 500, "message": f"调用失败: {str(e)}"}
