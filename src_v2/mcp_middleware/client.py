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

    async def get_market_price(self, type_name: str, market_zone: str = "jita") -> Dict[str, Any]:
        """获取市场价格"""
        return await self.call_api(
            method="GET",
            path="/api/internal/mcp/market/price",
            params={"type_name": type_name, "market_zone": market_zone},
        )

    async def get_market_cost(
        self, type_name: str, qq: int = None, plan_name: str = "default",
        force_recalculate: bool = False,
    ) -> Dict[str, Any]:
        """获取生产成本

        成本缓存作用域由后端按 qq 绑定解析（user_name 已不再受理）。
        """
        params = {
            "type_name": type_name,
            "plan_name": plan_name,
        }
        if qq is not None:
            params["qq"] = qq
        if force_recalculate:
            params["force_recalculate"] = "true"
        return await self.call_api(
            method="GET",
            path="/api/internal/mcp/market/cost",
            params=params,
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

    async def get_company_medica_vouchers(self, qq: int) -> Dict[str, Any]:
        """获取公司医疗抵扣额度（只返回该 QQ 的记录）"""
        return await self.call_api(
            method="GET",
            path="/api/internal/mcp/company/medica-vouchers",
            params={"qq": qq},
        )

    # ===== 估价器 API =====

    async def price_estimate(self, text: str, coefficient: float = 1.0) -> Dict[str, Any]:
        """估价计算"""
        return await self.call_api(
            method="POST",
            path="/api/EVE/price-estimator/calculate",
            json_data={"text": text, "coefficient": coefficient},
        )

    async def price_estimate_cost_start(
        self, type_ids: list[int], result_uuid: str
    ) -> Dict[str, Any]:
        """启动成本计算"""
        return await self.call_api(
            method="POST",
            path="/api/EVE/price-estimator/calculate-cost",
            json_data={"type_ids": type_ids, "result_uuid": result_uuid},
        )

    async def price_estimate_cost_status(self, task_id: str) -> Dict[str, Any]:
        """查询成本计算进度"""
        return await self.call_api(
            method="GET",
            path="/api/EVE/price-estimator/calculate-cost/status",
            params={"task_id": task_id},
        )

    # ===== 系数相关 API =====

    async def get_watched_system_coefficients(self, qq: int) -> Dict[str, Any]:
        """获取用户关注星系的制造/反应系数"""
        return await self.call_api(
            method="GET",
            path="/api/internal/mcp/coefficient/watched-systems",
            params={"qq": qq},
        )
