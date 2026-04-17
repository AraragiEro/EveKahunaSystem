"""市场相关 MCP Tools - 通过 HTTP 调用 Quart 后端"""

from typing import Annotated, Literal
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from src_v2.core.log import logger
from src_v2.mcp_middleware.client import QuartBackendClient


def register_market_tools(mcp: FastMCP):
    """注册市场相关 MCP tools"""

    @mcp.tool()
    async def market_price_detail(
        type_name: Annotated[
            str, Field(description="物品名称，支持中英文（如 'PLEX', '伊甸币'）")
        ],
    ) -> dict:
        """
        获取单个物品的市场价格详情（Jita 市场）

        Returns:
            {
                "status": 200,
                "is_price": True,
                "data": {
                    "type_id": 44992,
                    "name": "PLEX",
                    "name_zh": "伊甸币",
                    "buy": 4500000.0,
                    "sell": 4600000.0,
                    "mid": 4550000.0,
                    "history_data": [...]
                }
            }
        """
        logger.info(f"MCP Tool: market_price_detail(type_name={type_name})")

        try:
            async with QuartBackendClient() as client:
                result = await client.get_market_price(type_name)

            logger.info(
                f"MCP Tool: market_price_detail 完成，status={result.get('status', 'unknown')}"
            )
            return result
        except Exception as e:
            logger.error(f"MCP Tool: market_price_detail 失败: {e}")
            return {"status": 500, "message": f"调用失败: {str(e)}"}

    @mcp.tool()
    async def market_type_cost(
        type_name: Annotated[str, Field(description="物品名称")],
        user_name: Annotated[str, Field(description="用户名")] = "system",
        plan_name: Annotated[str, Field(description="计划名称")] = "default",
    ) -> dict:
        """
        获取单个物品的生产成本详情

        Returns:
            {
                "status": 200,
                "is_cost": True,
                "data": {
                    "type_id": 23917,
                    "material": {...},
                    "total_cost": total_cost,
                    "item_name": "Wyvern",
                    "item_name_cn": "飞龙级"
                }
            }
        """
        logger.info(
            f"MCP Tool: market_type_cost(type_name={type_name}, user={user_name}, plan={plan_name})"
        )

        try:
            async with QuartBackendClient() as client:
                result = await client.get_market_cost(type_name, user_name, plan_name)

            logger.info(
                f"MCP Tool: market_type_cost 完成，status={result.get('status', 'unknown')}"
            )
            return result
        except Exception as e:
            logger.error(f"MCP Tool: market_type_cost 失败: {e}")
            return {"status": 500, "message": f"调用失败: {str(e)}"}

    @mcp.tool()
    async def market_fuzz_type_name(
        type_name: Annotated[str, Field(description="搜索关键词")],
    ) -> dict:
        """
        物品名称模糊匹配

        Returns:
            {
                "status": 200,
                "data": [
                    {"name": "冥王级", "score": 95.0},
                    {"name": "冥府级", "score": 85.0}
                ]
            }
        """
        logger.info(f"MCP Tool: market_fuzz_type_name(type_name={type_name})")

        try:
            async with QuartBackendClient() as client:
                result = await client.fuzz_type_name(type_name)

            logger.info(
                f"MCP Tool: market_fuzz_type_name 完成，status={result.get('status', 'unknown')}"
            )
            return result
        except Exception as e:
            logger.error(f"MCP Tool: market_fuzz_type_name 失败: {e}")
            return {"status": 500, "message": f"调用失败: {str(e)}"}

    @mcp.tool()
    async def market_type_metrics(
        qq: Annotated[int, Field(description="QQ 号码")],
        market_id: Annotated[int, Field(description="市场 ID")],
        market_zone: Annotated[
            Literal["jita", "frt"], Field(description="市场区域")
        ] = "jita",
        cost_calculation_mode: Annotated[
            Literal["rough", "precise"], Field(description="成本计算模式")
        ] = "rough",
        price_base: Annotated[
            Literal["buy", "mid", "sell"], Field(description="价格基准")
        ] = "buy",
    ) -> dict:
        """
        获取市场物品关键指标

        Returns:
            {
                "status": 200,
                "data": {
                    "market_id": 1,
                    "market_zone": "jita",
                    "rows": [...]
                }
            }
        """
        logger.info(
            f"MCP Tool: market_type_metrics(qq={qq}, market_id={market_id}, zone={market_zone})"
        )

        try:
            async with QuartBackendClient() as client:
                result = await client.get_market_metrics(
                    qq, market_id, market_zone, cost_calculation_mode, price_base
                )

            logger.info(
                f"MCP Tool: market_type_metrics 完成，status={result.get('status', 'unknown')}"
            )
            return result
        except Exception as e:
            logger.error(f"MCP Tool: market_type_metrics 失败: {e}")
            return {"status": 500, "message": f"调用失败: {str(e)}"}
