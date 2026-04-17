"""
Quart 后端 HTTP 客户端

负责通过 HTTP API 调用 KahunaBot 后端服务
"""

import httpx
from typing import Any, Optional, Dict
from src_v2.mcp_middleware.config import config
from src_v2.core.log import logger


class QuartBackendClient:
    """
    KahunaBot Quart 后端 HTTP 客户端

    负责通过 HTTP API 调用后端服务
    """

    def __init__(self):
        self.base_url = config.quart_base_url
        self.api_key = config.quart_api_key
        self.timeout = config.request_timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["X-Internal-API-Key"] = self.api_key

        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, headers=headers
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def call_api(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        调用 Quart 后端 API

        Args:
            method: HTTP 方法 (GET, POST, etc.)
            path: API 路径 (如 "/api/internal/mcp/qq/vip")
            json_data: JSON 请求体
            params: URL 参数

        Returns:
            API 响应数据
        """
        try:
            logger.debug(f"Calling Quart API: {method} {path}")
            response = await self._client.request(
                method=method, url=path, json=json_data, params=params
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Quart API error: {e.response.status_code} - {e.response.text}"
            )
            return {
                "status": e.response.status_code,
                "message": f"Backend error: {e.response.text}",
            }
        except Exception as e:
            logger.error(f"Quart API call failed: {e}")
            return {"status": 500, "message": f"Internal error: {str(e)}"}

    # ===== QQ 相关 API =====

    async def get_qq_vip_state(self, qq: int) -> Dict[str, Any]:
        """获取 QQ 用户 VIP 状态"""
        return await self.call_api(
            method="GET", path="/api/internal/mcp/qq/vip", params={"qq": qq}
        )

    async def get_running_jobs_overview(self, qq: int) -> Dict[str, Any]:
        """获取运行中任务概览"""
        return await self.call_api(
            method="GET", path="/api/internal/mcp/qq/running-jobs", params={"qq": qq}
        )

    async def get_market_tag_list(self, qq: int) -> Dict[str, Any]:
        """获取市场标签列表"""
        return await self.call_api(
            method="GET", path="/api/internal/mcp/qq/market-tags", params={"qq": qq}
        )

    # ===== 市场相关 API =====

    async def get_market_price(self, type_name: str) -> Dict[str, Any]:
        """获取市场价格"""
        return await self.call_api(
            method="GET",
            path="/api/internal/mcp/market/price",
            params={"type_name": type_name},
        )

    async def get_market_cost(
        self, type_name: str, user_name: str = "system", plan_name: str = "default"
    ) -> Dict[str, Any]:
        """获取生产成本"""
        return await self.call_api(
            method="GET",
            path="/api/internal/mcp/market/cost",
            params={
                "type_name": type_name,
                "user_name": user_name,
                "plan_name": plan_name,
            },
        )

    async def fuzz_type_name(self, type_name: str) -> Dict[str, Any]:
        """模糊匹配物品名称"""
        return await self.call_api(
            method="GET",
            path="/api/internal/mcp/market/fuzz",
            params={"type_name": type_name},
        )

    async def get_market_metrics(
        self,
        qq: int,
        market_id: int,
        market_zone: str = "jita",
        cost_calculation_mode: str = "rough",
        price_base: str = "buy",
    ) -> Dict[str, Any]:
        """获取市场指标"""
        return await self.call_api(
            method="GET",
            path="/api/internal/mcp/market/metrics",
            params={
                "qq": qq,
                "market_id": market_id,
                "market_zone": market_zone,
                "cost_calculation_mode": cost_calculation_mode,
                "price_base": price_base,
            },
        )

    # ===== 工业相关 API =====

    async def get_missing_blueprint_summary(
        self, qq: int, planname: str
    ) -> Dict[str, Any]:
        """获取缺失蓝图工作流汇总"""
        return await self.call_api(
            method="GET",
            path="/api/internal/mcp/industry/missing-blueprints",
            params={"qq": qq, "planname": planname},
        )

    async def get_company_medica_vouchers(self) -> Dict[str, Any]:
        """获取公司医疗抵扣额度"""
        return await self.call_api(
            method="GET", path="/api/internal/mcp/company/medica-vouchers"
        )
