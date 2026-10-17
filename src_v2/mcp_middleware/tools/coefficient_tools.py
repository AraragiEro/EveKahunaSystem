"""系数查询 MCP Tools - 通过 HTTP 调用 Quart 后端"""

from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from src_v2.core.log import logger
from src_v2.mcp_middleware.client import QuartBackendClient


def register_coefficient_tools(mcp: FastMCP):
    """注册系数相关 MCP tools"""

    @mcp.tool()
    async def watched_system_coefficients(
        qq: Annotated[int, Field(description="QQ 号码")],
    ) -> dict:
        """
        查询用户在kahunasystem绑定的QQ对应的关注星系制造/反应系数

        内部调用：GET /api/internal/mcp/coefficient/watched-systems

        manufacturing 和 reaction 是小数形式的系数，展示时需要 ×100 后以百分比呈现。
        例如 0.023 → 2.30%，0.05 → 5.00%。
        null 表示暂无该星系系数数据（ESI 未拉取或已过期）。

        Returns:
            {
                "status": 200,
                "data": [
                    {
                        "system_id": 30000142,
                        "system_name": "Jita",
                        "region_name": "The Forge",
                        "manufacturing": 0.023,
                        "reaction": 0.05
                    }
                ],
                "count": 1
            }
        """
        logger.info(f"MCP Tool: watched_system_coefficients(qq={qq})")

        try:
            async with QuartBackendClient() as client:
                result = await client.get_watched_system_coefficients(qq)

            logger.info(
                f"MCP Tool: watched_system_coefficients 完成，"
                f"status={result.get('status', 'unknown')}"
            )
            return result
        except Exception as e:
            logger.error(f"MCP Tool: watched_system_coefficients 失败: {e}")
            return {"status": 500, "message": f"调用失败: {str(e)}"}
