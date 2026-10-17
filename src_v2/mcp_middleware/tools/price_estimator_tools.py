"""估价器 MCP Tools - 通过 HTTP 调用 Quart 后端"""

import asyncio
from typing import Annotated

from pydantic import Field
from mcp.server.fastmcp import FastMCP
from src_v2.core.log import logger
from src_v2.mcp_middleware.client import QuartBackendClient
from src_v2.mcp_middleware.config import config as mcp_config
from src_v2.core.config.config import config as app_config


def _share_url(result_uuid: str) -> str:
    """生成分享链接"""
    host = app_config.get("EVE", "CALLBACK_LOCAL_HOST", fallback=None)
    if host:
        return f"https://{host}/utils/estimator?uuid={result_uuid}"
    base = mcp_config.quart_base_url.rstrip("/")
    return f"{base}/utils/estimator?uuid={result_uuid}"


def _format_price(value: float) -> str:
    """格式化价格为千分位字符串"""
    return f"{value:,.2f}"


def _summarize_result(result: dict) -> str:
    """将估价结果格式化为可读文本"""
    items = result.get("items", [])
    if not items:
        return "未解析到物品"

    summary = result.get("summary", {})
    lines = []
    for item in items[:20]:  # 最多展示20行
        name = item.get("name", "?")
        qty = item.get("quantity", 0)
        jita_sell = item.get("total_jita_sell", 0)
        cost = item.get("total_cost", 0)
        tags = ""
        if item.get("type_id") is None:
            tags = " [未识别]"
        elif not item.get("cost_cached") and item.get("has_blueprint"):
            tags = " [缺成本]"
        lines.append(
            f"  {name} ×{qty}  Jita卖={_format_price(jita_sell)}  成本={_format_price(cost)}{tags}"
        )

    coef = summary.get("coefficient", 1.0)
    result_text = "\n".join(lines)
    result_text += "\n\n--- 汇总 ---"
    result_text += f"\nJita卖总价: {_format_price(summary.get('total_jita_sell', 0))} ISK"
    result_text += f"\nJita买总价: {_format_price(summary.get('total_jita_buy', 0))} ISK"
    result_text += f"\n4H卖总价:  {_format_price(summary.get('total_frt_sell', 0))} ISK"
    result_text += f"\n成本总价:  {_format_price(summary.get('total_cost', 0))} ISK"
    if coef != 1.0:
        result_text += f"\n调整后 (×{coef}): Jita卖 {_format_price(summary.get('total_jita_sell', 0) * coef)} ISK"

    unrecognized = result.get("unrecognized_names", [])
    if unrecognized:
        result_text += f"\n\n未识别物品: {', '.join(unrecognized[:10])}"

    missing = result.get("missing_cost_type_ids", [])
    if missing:
        result_text += f"\n缺少成本数据: {len(missing)} 个物品"

    return result_text


async def _poll_cost_calculation(client: QuartBackendClient, task_id: str, timeout: int = 120) -> dict:
    """轮询成本计算直到完成"""
    start = asyncio.get_event_loop().time()
    while True:
        status = await client.price_estimate_cost_status(task_id)
        data = status.get("data", {})
        s = data.get("status", "pending")

        if s == "completed":
            logger.info(f"成本计算完成 task_id={task_id}")
            return data
        if s == "failed":
            logger.error(f"成本计算失败 task_id={task_id}: {data.get('error')}")
            return data

        if asyncio.get_event_loop().time() - start > timeout:
            logger.warning(f"成本计算超时 task_id={task_id}")
            return {"status": "timeout", "message": "成本计算超时"}

        await asyncio.sleep(2)


def register_price_estimator_tools(mcp: FastMCP):
    """注册估价器 MCP tools"""

    @mcp.tool()
    async def price_estimate(
        text: Annotated[
            str,
            Field(
                description="粘贴的EVE游戏文本，支持合同复制/仓库/配装等多种格式。\n"
                "格式示例：\n"
                "  'Arbalest' Rocket Launcher I\t1\tModule\t高能量槽\n"
                "  Sleipnir\t20\n"
                "  [Huginn, 配置名]\n  Gyrostabilizer II\n  Barrage M x4000"
            ),
        ],
        coefficient: Annotated[
            float,
            Field(description="价格系数，默认为1.0。如填0.9则所有总价×0.9", ge=0.01, le=10),
        ] = 1.0,
        auto_calculate_cost: Annotated[
            bool,
            Field(
                description="是否自动计算缺失的成本数据。设为true则会等待成本计算完成后返回（可能需要几分钟）"
            ),
        ] = False,
    ) -> dict:
        """
        物品估价器 - 粘贴EVE游戏文本，自动解析物品并估算市场价值。

        支持5种EVE文本格式：
        1. 游戏合同复制（Tab分隔多列）
        2. 仓库图标复制（2列Tab分隔）
        3. 仓库详情复制（多列Tab分隔）
        4. 仓库列表复制（同3）
        5. 配装文本（[船型名, 配置名] + 物品 x数量）

        一定要给用户提供share_url链接，方便用户查看完整结果和分享给其他人。
        Returns:
            {
                "status": 200,
                "share_url": "http://xxx/utils/estimator?uuid=abc123",
                "summary": "Jita卖总价: 4,589,100,000.00 ISK\n...",
                "data": { ... 完整估价数据 ... }
            }
        """
        logger.info(
            f"MCP Tool: price_estimate(text_len={len(text)}, auto_calc={auto_calculate_cost})"
        )

        try:
            async with QuartBackendClient() as client:
                # Step 1: 估价计算
                result = await client.price_estimate(text, coefficient)

                if result.get("status") != 200:
                    return result

                data = result.get("data", {})
                result_uuid = data.get("result_uuid")
                missing = data.get("missing_cost_type_ids", [])

                # Step 2: 如果开启自动计算且有缺失成本
                if auto_calculate_cost and missing and result_uuid:
                    logger.info(
                        f"自动计算缺失成本: uuid={result_uuid}, items={len(missing)}"
                    )

                    cost_start = await client.price_estimate_cost_start(
                        missing, result_uuid
                    )
                    cost_data = cost_start.get("data", {})
                    task_id = cost_data.get("task_id")

                    if task_id:
                        # 轮询直到完成
                        cost_result = await _poll_cost_calculation(client, task_id)

                        if cost_result.get("status") == "completed":
                            # 重新获取完整结果（含更新后的成本）
                            reload_result = await client.call_api(
                                method="GET",
                                path=f"/api/EVE/price-estimator/result",
                                params={"uuid": result_uuid},
                            )
                            if reload_result.get("status") == 200:
                                data = reload_result.get("data", {})

                share_url = _share_url(result_uuid) if result_uuid else ""

                return {
                    "status": 200,
                    "share_url": share_url,
                    "summary": _summarize_result(data),
                    "data": data,
                }

        except Exception as e:
            logger.error(f"MCP Tool: price_estimate 失败: {e}", exc_info=True)
            return {"status": 500, "message": f"估价失败: {str(e)}"}
