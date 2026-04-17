"""工业相关 MCP Tools - 通过 HTTP 调用 Quart 后端"""

from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from src_v2.core.log import logger
from src_v2.mcp_middleware.client import QuartBackendClient


def register_industry_tools(mcp: FastMCP):
    """注册工业相关 MCP tools"""

    @mcp.tool()
    async def plan_missing_blueprint_workflow_summary(
        qq: Annotated[int, Field(description="QQ 号码")],
        planname: Annotated[str, Field(description="计划名称")],
    ) -> dict:
        """
        通过计划名获取缺失蓝图工作流汇总

        Returns:
            {
                "status": 200,
                "data": {
                    "user_name": "用户名",
                    "plan_name": "计划名",
                    "missing_blueprint_workflow": [...]
                }
            }
        """
        logger.info(
            f"MCP Tool: plan_missing_blueprint_workflow_summary(qq={qq}, planname={planname})"
        )

        try:
            async with QuartBackendClient() as client:
                result = await client.get_missing_blueprint_summary(qq, planname)

            logger.info(
                f"MCP Tool: plan_missing_blueprint_workflow_summary 完成，status={result.get('status', 'unknown')}"
            )
            return result
        except Exception as e:
            logger.error(f"MCP Tool: plan_missing_blueprint_workflow_summary 失败: {e}")
            return {"status": 500, "message": f"调用失败: {str(e)}"}

    @mcp.tool()
    async def get_company_medica_vouchers() -> dict:
        """
        获取公司医疗抵扣额度

        Returns:
            {
                "status": 200,
                "data": [
                    ["用户名", "额度"],
                    ["CrazySheep7", "1,500,000,000"]
                ]
            }
        """
        logger.info("MCP Tool: get_company_medica_vouchers()")

        try:
            async with QuartBackendClient() as client:
                result = await client.get_company_medica_vouchers()

            logger.info(
                f"MCP Tool: get_company_medica_vouchers 完成，status={result.get('status', 'unknown')}"
            )
            return result
        except Exception as e:
            logger.error(f"MCP Tool: get_company_medica_vouchers 失败: {e}")
            return {"status": 500, "message": f"调用失败: {str(e)}"}
