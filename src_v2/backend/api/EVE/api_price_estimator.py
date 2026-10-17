# -*- coding: utf-8 -*-
"""
估价器 (Price Estimator) API 端点

提供文本解析、价格查询、成本计算功能。
支持5种EVE游戏文本格式的解析与估价。
"""

import asyncio
import hashlib
import json
import os
import re
import time
import traceback
import uuid as _uuid
from typing import Any, Optional

from quart import Blueprint, g, jsonify, request

from src_v2.backend.api import response_helper
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException
from src_v2.model.EVE.industry.blueprint import BPManager as BPM
from src_v2.model.EVE.industry.industry_manager import IndustryManager
from src_v2.model.EVE.industry.plan_configflow_operate import ConfigFlowOperateCenter
from src_v2.model.EVE.market.market_manager import MarketManager
from src_v2.model.EVE.sde.utils import SdeUtils

api_price_estimator_bp = Blueprint(
    "api_price_estimator", __name__, url_prefix="/api/EVE/price-estimator"
)

# 系统成本缓存 Redis key（与市场分析共用）
SYSTEM_COST_CACHE_KEY = "market_cost_calculation_result:system:-1"

# 临时计划名（用于成本计算上下文）
TEMP_PLAN_NAME = "price_estimator_temp"

# 进度相关 Redis key 前缀
TASK_CTX_PREFIX = "pe_cost_task"
TASK_TTL = 7200  # 任务上下文过期时间（秒）

# 估价结果缓存
RESULT_CACHE_PREFIX = "pe_result"
RESULT_CACHE_TTL = 86400 * 7  # 7 天

# 成本计算队列
QUEUE_KEY = "pe_cost_queue"
QUEUE_LOCK_KEY = "pe_cost_queue_lock"
MAX_BATCH_SIZE = 50  # 单次最多计算 50 个 type_id


def _get_user_name() -> str:
    """安全获取当前用户名，公开端点可能无登录态"""
    try:
        return g.current_user.get("user_id", "anonymous")
    except Exception:
        return "anonymous"


# ------------------------------------------------------------------
# 文本解析
# ------------------------------------------------------------------

def parse_estimate_text(text: str) -> list[dict]:
    """
    解析输入文本，返回 [(name, quantity), ...] 列表

    支持6种格式：
    1. 合同Tab分隔（多列，第1列名称可能含引号，第2列数量）
    2. 仓库图标（2列Tab分隔）
    3. 仓库详情（多列Tab分隔，取前2列）
    4. 仓库列表（同3）
    5. 配装文本（[ShipName, ...] 头 + x后缀行）
    6. 空格分隔的简单格式（如 "Ishtar 1"、"PLEX 100"）
    """
    lines = text.strip().split("\n")
    items: list[dict] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 过滤空槽位等无意义行
        if line.lower() in ("[empty slot]", "[empty high slot]",
                            "[empty med slot]", "[empty low slot]",
                            "[empty rig slot]", "[empty subsystem slot]"):
            continue

        # 模式5：配装文本 - [ShipName, ...]
        if line.startswith("[") and "]" in line and not line.startswith("[Empty"):
            inner = line[1:line.index("]")]
            ship_name = inner.split(",")[0].strip()
            items.append({"name": ship_name, "quantity": 1})
            continue

        # 模式5：配装文本 - 物品 x数量（如 "Barrage M x4000"）
        x_match = re.match(r"^(.+?)\s+x(\d[\d,]*)$", line)
        if x_match:
            name = x_match.group(1).strip()
            qty = int(x_match.group(2).replace(",", ""))
            items.append({"name": name, "quantity": qty})
            continue

        # 模式1-4：Tab分隔
        if "\t" in line:
            parts = line.split("\t")
            # 第1列：物品名（去除可能的单引号包裹）
            name = parts[0].strip().strip("'\"")
            if not name:
                continue
            # 第2列：数量
            try:
                qty = int(parts[1].strip().replace(",", ""))
            except (ValueError, IndexError):
                continue
            items.append({"name": name, "quantity": qty})
            continue

        # 模式6：空格分隔的 "物品名 数量" 格式（如 "Ishtar 1"）
        # 数字前至少需有一个空格，且数字部分不能超长（避免 "Cap Booster 3200" 误判）
        num_match = re.match(r"^(.+)\s+(\d{1,4})$", line)
        if num_match:
            name = num_match.group(1).strip()
            qty = int(num_match.group(2))
            items.append({"name": name, "quantity": qty})
            continue

        # 模式5 fallback：单行无Tab无x = 单个装备
        # 过滤明显的非物品行（如中括号配置行）
        if not line.startswith("[") and not line.startswith("<"):
            items.append({"name": line, "quantity": 1})

    return items


# ------------------------------------------------------------------
# 名称 → type_id 解析
# ------------------------------------------------------------------

async def resolve_type_id(name: str) -> Optional[int]:
    """将物品名称解析为 type_id，失败返回 None"""
    try:
        name = name.strip("*")  # 去除EVE名词高亮添加的*号
        # 精确匹配
        type_id = await SdeUtils.get_id_by_name(name)
        if type_id:
            return type_id

        # 模糊匹配 fallback（参考 api_astrbot_service.py 的严谨匹配逻辑）
        fuzz_list = await SdeUtils.fuzz_type(name, list_len=10)
        if fuzz_list:
            found_tid = None
            if SdeUtils.maybe_chinese(name):
                # 中文：精确匹配，或长度≥2的子串匹配
                for item in fuzz_list:
                    if name == item:
                        found_tid = await SdeUtils.get_id_by_name(item)
                        if found_tid:
                            logger.debug(f"模糊匹配: '{name}' → '{item}' (type_id={found_tid})")
                            return found_tid
                    elif len(name) >= 2 and name in item:
                        found_tid = await SdeUtils.get_id_by_name(item)
                        if found_tid:
                            logger.debug(f"模糊匹配: '{name}' → '{item}' (type_id={found_tid})")
                            return found_tid
            else:
                # 英文：仅接受大小写不敏感完全匹配
                name_lower = name.lower()
                for item in fuzz_list:
                    if name_lower == item.lower():
                        found_tid = await SdeUtils.get_id_by_name(item)
                        if found_tid:
                            logger.debug(f"模糊匹配: '{name}' → '{item}' (type_id={found_tid})")
                            return found_tid
    except Exception as e:
        logger.error(f"解析物品名 '{name}' 失败: {e}")

    return None


# ------------------------------------------------------------------
# 价格与成本查询
# ------------------------------------------------------------------

async def _get_market_prices(type_id: int) -> dict:
    """获取 Jita 和 FRT 市场价格"""
    prices = {
        "jita_buy": 0.0,
        "jita_sell": 0.0,
        "jita_mid": 0.0,
        "frt_buy": 0.0,
        "frt_sell": 0.0,
    }

    try:
        # Jita 价格
        jita_data = await rdm().r.hgetall(f"market_price:jita:{type_id}")
        if jita_data:
            prices["jita_buy"] = _safe_float(jita_data.get("max_buy"))
            prices["jita_sell"] = _safe_float(jita_data.get("min_sell"))
            if prices["jita_buy"] or prices["jita_sell"]:
                prices["jita_mid"] = round(
                    (prices["jita_buy"] + prices["jita_sell"]) / 2, 2
                )

        # FRT 价格
        frt_data = await rdm().r.hgetall(f"market_price:frt:{type_id}")
        if frt_data:
            prices["frt_buy"] = _safe_float(frt_data.get("max_buy"))
            prices["frt_sell"] = _safe_float(frt_data.get("min_sell"))
    except Exception as e:
        logger.error(f"获取 type_id={type_id} 市场价格失败: {e}")

    return prices


async def _extract_unit_cost(cost_item: Optional[dict], price_base: str = "sell") -> float:
    """从成本缓存项中提取单位生产成本（含材料+EIV）

    兼容两种 eiv_cost_dict 结构：
    格式1（扁平，生产环境）：
      {"eiv_cost": ..., "product_num": ..., "children": [...]}
    格式2（嵌套，特定计算路径）：
      {"12005": {"eiv_cost": ..., "product_num": ..., "children": [...]}}

    总成本 = Σ(child.quantity × child.price) / product_num
           + eiv_cost / product_num
    """
    if not cost_item or not isinstance(cost_item, dict):
        return 0.0

    eiv_dict = cost_item.get("eiv_cost_dict")
    if not isinstance(eiv_dict, dict) or not eiv_dict:
        return 0.0

    # 判断是扁平还是嵌套结构
    if "eiv_cost" in eiv_dict or "children" in eiv_dict:
        inner = eiv_dict  # 扁平：直接用
    else:
        inner = next(iter(eiv_dict.values()), None)  # 嵌套：取第一层值
        if not isinstance(inner, dict):
            return 0.0

    product_num = _safe_float(inner.get("product_num"), 1.0)
    if product_num <= 0:
        return 0.0

    # 缓存中的 product_num 可能未乘 products_per_run（如弹药批量生产），
    # 导致单位成本被高估。优先从缓存读取，缓存缺失则通过 BPM 查询
    products_per_run = _safe_float(inner.get("products_per_run"), 0.0)
    if products_per_run <= 0:
        try:
            products_per_run = float(
                await BPM.get_bp_product_quantity_typeid(
                    int(inner.get("type_id", 0) or cost_item.get("type_id", 0))
                )
            )
        except Exception:
            products_per_run = 1.0
    if products_per_run > 1:
        product_num = product_num * products_per_run

    # 1) 材料成本
    children = inner.get("children") or []
    children_cost = 0.0
    price_field = "jita_sell_price" if price_base == "sell" else "jita_buy_price"

    for child in children:
        if not isinstance(child, dict):
            continue
        qty = _safe_float(child.get("quantity"))
        price = _safe_float(child.get(price_field))
        children_cost += qty * price

    children_unit_cost = children_cost / product_num

    # 2) EIV 成本
    eiv_cost = _safe_float(inner.get("eiv_cost"))
    eiv_unit_cost = eiv_cost / product_num

    return round(children_unit_cost + eiv_unit_cost, 2)


def _safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为 float"""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

# ------------------------------------------------------------------
# 成本计算队列（最多50个/次，顺序执行，执行前刷新待计算列表）
# ------------------------------------------------------------------

_queue_worker_started = False

async def _refresh_result_cache(result_uuid: str, calculated: dict) -> None:
    """用新的成本数据更新已缓存的估价结果"""
    key = f"{RESULT_CACHE_PREFIX}:{result_uuid}"
    try:
        cached_str = await rdm().r.get(key)
        if not cached_str:
            return
        cached = json.loads(cached_str)
        items = cached.get("items", [])
        updated = False
        for item in items:
            tid = item.get("type_id")
            if tid is None:
                continue
            cost_info = calculated.get(str(tid))
            if cost_info:
                item["cost"] = cost_info["cost"]
                item["cost_cached"] = True
                item["total_cost"] = round(cost_info["cost"] * item.get("quantity", 1), 2)
                updated = True
        if updated:
            remaining = [tid for tid in cached.get("missing_cost_type_ids", [])
                         if str(tid) not in calculated]
            cached["missing_cost_type_ids"] = remaining
            total_cost = sum(i.get("total_cost", 0) for i in items)
            cached["summary"]["total_cost"] = round(total_cost, 2)
            await rdm().r.set(key, json.dumps(cached), ex=RESULT_CACHE_TTL)
    except Exception as e:
        logger.error(f"更新估价结果缓存失败 uuid={result_uuid}: {e}", exc_info=True)


async def _do_cost_calculation(task_id, user_name, market_id,
                                type_ids, result_uuid=None):
    """执行实际的成本计算（被队列调用）"""
    ctx_key = f"{TASK_CTX_PREFIX}:{task_id}"
    try:
        plan_settings = {
            "name": TEMP_PLAN_NAME,
            "work_type": "whole", "split_to_jobs": True,
            "considerate_asset": False,
            "considerate_bp_relation": False,
            "considerate_running_job": False,
            "full_split": False,
        }
        op = await ConfigFlowOperateCenter.create(user_name, TEMP_PLAN_NAME, plan_settings)
        await op.init_at_begin()

        new_cost_dict = await IndustryManager.calculate_cost(op, type_ids, market_id=market_id)

        result_key = f"market_cost_calculation_result:{user_name}:{market_id}"
        if not new_cost_dict:
            result_str = await rdm().r.get(result_key)
            new_cost_dict = json.loads(result_str) if result_str else {}

        # 合并到系统缓存
        cached_str = await rdm().r.get(SYSTEM_COST_CACHE_KEY)
        cached_dict = json.loads(cached_str) if cached_str else {}
        merged = {**cached_dict, **new_cost_dict}
        await rdm().r.set(SYSTEM_COST_CACHE_KEY, json.dumps(merged))

        # 保存材料骨架
        try:
            from src_v2.core.edition import is_enterprise
            if is_enterprise():
                from src_v2.enterprise.utils.cost_refresher import CostRefresher
                await CostRefresher.save_skeletons_from_full_result("system", -1, new_cost_dict)
        except Exception:
            pass

        # 提取单位成本
        calculated = {}
        for tid in type_ids:
            cost_item = new_cost_dict.get(str(tid)) or new_cost_dict.get(tid)
            unit_cost = await _extract_unit_cost(cost_item)
            calculated[str(tid)] = {
                "cost": unit_cost,
                "product_num": _safe_float(
                    (cost_item or {}).get("eiv_cost_dict", {}).get("product_num"), 1.0
                ),
            }

        if result_uuid:
            await _refresh_result_cache(result_uuid, calculated)

        await rdm().r.hset(ctx_key, mapping={
            "status": "completed", "completed": str(len(type_ids)),
            "total": str(len(type_ids)), "current_step": "计算完成",
            "calculated": json.dumps(calculated),
            "merged_count": str(len(merged)),
        })
        await rdm().r.expire(ctx_key, TASK_TTL)
        await rdm().r.delete(result_key)

        logger.info(f"[计算完成] task_id={task_id}, calculated={len(calculated)}, merged={len(merged)}")

    except Exception as e:
        logger.error(f"[计算失败] task_id={task_id}: {e}", exc_info=True)
        await rdm().r.hset(ctx_key, mapping={
            "status": "failed", "error": str(e)[:500]
        })
        await rdm().r.expire(ctx_key, TASK_TTL)


async def _process_cost_queue() -> None:
    """顺序处理成本计算队列（每次处理前刷新待计算列表，限制50个）"""
    global _queue_worker_started
    try:
        while True:
            try:
                item_str = await rdm().r.lpop(QUEUE_KEY)
                if not item_str:
                    break

                item = json.loads(item_str)
                task_id = item["task_id"]
                orig_type_ids = item["type_ids"]
                result_uuid = item.get("result_uuid")

                ctx_key = f"{TASK_CTX_PREFIX}:{task_id}"
                await rdm().r.hset(ctx_key, mapping={
                    "status": "running", "queue_position": "0"
                })

                # 重新读取系统缓存，分离已计算和待计算的 type_id
                cached_str = await rdm().r.get(SYSTEM_COST_CACHE_KEY)
                cached = json.loads(cached_str) if cached_str else {}
                pending_ids: list[int] = []
                already_cached_ids: list[int] = []
                for tid in orig_type_ids:
                    if str(tid) in cached or tid in cached:
                        already_cached_ids.append(tid)
                    else:
                        pending_ids.append(tid)

                # 前序任务已计算的 → 直接从系统缓存提取成本，更新结果缓存
                if already_cached_ids and result_uuid:
                    pre_calculated = {}
                    for tid in already_cached_ids:
                        cost_item = cached.get(str(tid)) or cached.get(tid)
                        unit_cost = await _extract_unit_cost(cost_item)
                        pre_calculated[str(tid)] = {"cost": unit_cost, "product_num": 0}
                    await _refresh_result_cache(result_uuid, pre_calculated)

                if not pending_ids:
                    logger.info(f"[队列] task_id={task_id} 所有 type_id 已被前序任务计算，跳过")
                    await rdm().r.hset(ctx_key, mapping={
                        "status": "completed",
                        "current_step": f"所有 {len(orig_type_ids)} 个物品已由前序任务计算完成",
                        "completed": str(len(orig_type_ids)),
                        "total": str(len(orig_type_ids)),
                        "calculated": json.dumps(pre_calculated if already_cached_ids else {}),
                    })
                    await rdm().r.expire(ctx_key, TASK_TTL)
                    continue

                logger.info(
                    f"[队列] task_id={task_id} 原始={len(orig_type_ids)} "
                    f"前序已算={len(already_cached_ids)} 仍需={len(pending_ids)}"
                )

                batch_ids = pending_ids[:MAX_BATCH_SIZE]
                skipped = len(pending_ids) - len(batch_ids)

                await rdm().r.hset(ctx_key, mapping={
                    "total": str(len(batch_ids)), "completed": "0",
                    "current_step": f"开始计算 {len(batch_ids)} 个 type_id"
                    + (f" (跳过 {skipped} 个超出上限)" if skipped else ""),
                })

                await _do_cost_calculation(task_id, item["user_name"],
                                           item["market_id"], batch_ids, result_uuid)

                if skipped > 0:
                    await rdm().r.hset(ctx_key, mapping={
                        "current_step": f"已完成 {len(batch_ids)} 个 (跳过 {skipped} 个超出上限, 可再次提交)"
                    })

            except Exception as e:
                logger.error(f"[队列] 处理失败: {e}", exc_info=True)

    finally:
        # 队列清空后重置标志，允许下次重新启动
        _queue_worker_started = False
        await rdm().r.delete(QUEUE_LOCK_KEY)


def _ensure_queue_worker():
    """确保队列 worker 已启动（全局唯一，完成后自动重置）"""
    global _queue_worker_started
    if not _queue_worker_started:
        _queue_worker_started = True
        asyncio.create_task(_process_cost_queue())



# ------------------------------------------------------------------
# API 端点
# ------------------------------------------------------------------


@api_price_estimator_bp.route("/calculate", methods=["POST"])
async def calculate():
    """
    估价计算

    接收原始文本，解析物品名和数量，查询市场价格和成本。

    Request Body:
        - text (string, required): 粘贴的EVE文本
        - coefficient (float, optional): 价格系数，默认1.0

    Responses:
        200: 估价结果
            - items: 物品列表（含价格、成本）
            - missing_cost_type_ids: 缺少成本缓存的type_id列表
            - unrecognized_names: 未识别的物品名列表
            - summary: 汇总数据
    """
    try:
        data = await request.get_json()
        if not data:
            return response_helper.bad_request("请求体不能为空")

        text = (data.get("text") or "").strip()
        if not text:
            return response_helper.bad_request("文本内容不能为空")

        coefficient = _safe_float(data.get("coefficient"), 1.0)
        if coefficient <= 0:
            return response_helper.bad_request("价格系数必须大于0")

        # Step 1: 解析文本 → (name, quantity) 列表
        raw_items = parse_estimate_text(text)
        if not raw_items:
            return response_helper.bad_request("未能从文本中解析出任何物品")

        # 合并同名物品数量
        merged: dict[str, int] = {}
        for item in raw_items:
            name = item["name"]
            merged[name] = merged.get(name, 0) + item["quantity"]

        # Step 2: 名称 → type_id 解析
        type_id_map: dict[str, Optional[int]] = {}
        unrecognized_names: list[str] = []
        for name in merged:
            tid = await resolve_type_id(name)
            type_id_map[name] = tid
            if tid is None:
                unrecognized_names.append(name)

        # Step 3: 读取系统成本缓存
        cost_cache: dict = {}
        try:
            cached_str = await rdm().r.get(SYSTEM_COST_CACHE_KEY)
            if cached_str:
                cost_cache = json.loads(cached_str)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"解析成本缓存失败: {e}")

        # Step 4: 逐物品处理
        items_result: list[dict] = []
        missing_cost_type_ids: list[int] = []
        totals = {
            "total_jita_buy": 0.0,
            "total_jita_sell": 0.0,
            "total_frt_sell": 0.0,
            "total_cost": 0.0,
        }

        for name, qty in merged.items():
            tid = type_id_map.get(name)
            if tid is None:
                items_result.append({
                    "name": name, "name_en": "", "type_id": None,
                    "quantity": qty, "has_blueprint": False, "cost_cached": False,
                    "jita_buy": 0.0, "jita_sell": 0.0, "jita_mid": 0.0,
                    "frt_buy": 0.0, "frt_sell": 0.0, "cost": 0.0,
                    "total_jita_buy": 0.0, "total_jita_sell": 0.0,
                    "total_frt_sell": 0.0, "total_cost": 0.0,
                })
                continue

            try:
                name_en = await SdeUtils.get_name_by_id(tid, zh=False) or name
                name_zh = await SdeUtils.get_name_by_id(tid, zh=True) or name
            except Exception:
                name_en = name
                name_zh = name

            prices = await _get_market_prices(tid)

            has_blueprint = False
            try:
                bp_id = await BPM.get_bp_id_by_prod_typeid(tid)
                has_blueprint = bp_id is not None
            except Exception as e:
                logger.warning(f"蓝图检查 type_id={tid} 失败: {e}")

            cost = 0.0
            cost_cached = False
            if has_blueprint:
                tid_str = str(tid)
                if tid_str in cost_cache:
                    cost_item = cost_cache[tid_str]
                    try:
                        from src_v2.core.edition import is_enterprise
                        if is_enterprise():
                            from src_v2.enterprise.utils.cost_refresher import CostRefresher
                            refreshed = await CostRefresher.refresh_single_cost(
                                scope="system", market_id=-1, type_id=tid,
                                market_zone="jita", price_base="sell"
                            )
                            if refreshed is not None and refreshed.get("children"):
                                cost_item = {
                                    "type_id": tid,
                                    "eiv_cost_dict": refreshed
                                }
                    except Exception:
                        pass
                    cost = await _extract_unit_cost(cost_item)
                    cost_cached = True
                elif tid in cost_cache:
                    cost_item = cost_cache[tid]
                    try:
                        from src_v2.core.edition import is_enterprise
                        if is_enterprise():
                            from src_v2.enterprise.utils.cost_refresher import CostRefresher
                            refreshed = await CostRefresher.refresh_single_cost(
                                scope="system", market_id=-1, type_id=tid,
                                market_zone="jita", price_base="sell"
                            )
                            if refreshed is not None and refreshed.get("children"):
                                cost_item = {
                                    "type_id": tid,
                                    "eiv_cost_dict": refreshed
                                }
                    except Exception:
                        pass
                    cost = await _extract_unit_cost(cost_item)
                    cost_cached = True
                else:
                    missing_cost_type_ids.append(tid)
            else:
                # 不可制造物品，使用 Jita 买入价作为参考成本
                cost = prices["jita_buy"]
                cost_cached = True

            total_jita_buy = round(prices["jita_buy"] * qty, 2)
            total_jita_sell = round(prices["jita_sell"] * qty, 2)
            total_frt_sell = round(prices["frt_sell"] * qty, 2)
            total_cost = round(cost * qty, 2)

            items_result.append({
                "name": name_zh, "name_en": name_en, "type_id": tid,
                "quantity": qty, "has_blueprint": has_blueprint,
                "cost_cached": cost_cached,
                "jita_buy": prices["jita_buy"], "jita_sell": prices["jita_sell"],
                "jita_mid": prices["jita_mid"],
                "frt_buy": prices["frt_buy"], "frt_sell": prices["frt_sell"],
                "cost": cost,
                "total_jita_buy": total_jita_buy,
                "total_jita_sell": total_jita_sell,
                "total_frt_sell": total_frt_sell,
                "total_cost": total_cost,
            })

            totals["total_jita_buy"] += total_jita_buy
            totals["total_jita_sell"] += total_jita_sell
            totals["total_frt_sell"] += total_frt_sell
            totals["total_cost"] += total_cost

        totals = {k: round(v, 2) for k, v in totals.items()}
        summary = {
            **totals,
            "coefficient": coefficient,
        }

        try:
            from src_v2.core.edition import is_enterprise
            if is_enterprise():
                from src_v2.enterprise.utils.cost_refresher import CostRefresher
                if await CostRefresher.is_expired("system", -1):
                    asyncio.create_task(
                        CostRefresher.refresh_market_costs("system", -1, "jita", "sell")
                    )
        except Exception:
            pass

        # 生成 UUID 并缓存结果（用于分享链接）
        result_uuid = _uuid.uuid4().hex
        result_data = {
            "text": text,
            "coefficient": coefficient,
            "items": items_result,
            "missing_cost_type_ids": missing_cost_type_ids,
            "unrecognized_names": unrecognized_names,
            "summary": summary,
        }
        await rdm().r.set(
            f"{RESULT_CACHE_PREFIX}:{result_uuid}",
            json.dumps(result_data),
            ex=RESULT_CACHE_TTL,
        )

        return jsonify({
            "status": 200,
            "data": {
                **result_data,
                "result_uuid": result_uuid,
            },
        })

    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"估价计算失败: {traceback.format_exc()}")
        return response_helper.server_error("估价计算失败")


@api_price_estimator_bp.route("/calculate-cost", methods=["POST"])
async def calculate_cost_start():
    """
    启动批量成本计算（异步，返回任务ID供轮询）

    后台执行增量合并策略：
    1. 读取现有系统缓存
    2. 仅计算缺失的 type_ids
    3. 合并到系统缓存
    4. 回写 Redis

    Request Body:
        - type_ids (array[int], required): 需要计算成本的type_id列表

    Responses:
        200: 任务已启动
            - task_id: 轮询用的任务ID
            - total: 待计算总数
    """
    try:
        user_name = _get_user_name()
        data = await request.get_json()
        if not data:
            return response_helper.bad_request("请求体不能为空")

        type_ids = data.get("type_ids", [])
        if not isinstance(type_ids, list) or not type_ids:
            return response_helper.bad_request("type_ids必须是非空数组")

        valid_ids = [tid for tid in type_ids if isinstance(tid, int) and tid > 0]
        if not valid_ids:
            return response_helper.bad_request("没有有效的type_id")

        # 过滤有蓝图的
        bp_filtered_ids = []
        for tid in valid_ids:
            try:
                bp_id = await BPM.get_bp_id_by_prod_typeid(tid)
                if bp_id is not None:
                    bp_filtered_ids.append(tid)
            except Exception as e:
                logger.warning(f"蓝图检查 type_id={tid} 失败: {e}")

        if not bp_filtered_ids:
            return jsonify({
                "status": 200,
                "data": {
                    "task_id": None,
                    "total": 0,
                    "message": "所有物品均无蓝图，无法计算成本",
                },
            })

        # 生成唯一 task_id 和 market_id
        task_id = hashlib.md5(
            f"{user_name}{time.time()}{os.urandom(4)}".encode()
        ).hexdigest()[:12]
        market_id = -(abs(hash(task_id)) % 900000) - 100000

        # 初始化进度（hash 结构，供状态端点读取）
        ctx_key = f"{TASK_CTX_PREFIX}:{task_id}"
        total = min(len(bp_filtered_ids), MAX_BATCH_SIZE)
        overflow = max(0, len(bp_filtered_ids) - MAX_BATCH_SIZE)
        await rdm().r.hset(ctx_key, mapping={
            "status": "pending", "total": str(total),
            "completed": "0", "current_step": "排队中...",
            "user_name": user_name, "market_id": str(market_id),
        })
        await rdm().r.expire(ctx_key, TASK_TTL)

        # 入队（队列处理器会重新读取缓存过滤已计算的 type_id）
        queue_item = json.dumps({
            "task_id": task_id,
            "user_name": user_name,
            "market_id": market_id,
            "type_ids": bp_filtered_ids,
            "result_uuid": data.get("result_uuid"),
        })
        await rdm().r.rpush(QUEUE_KEY, queue_item)

        # 确保队列 worker 运行
        _ensure_queue_worker()

        # 计算队列位置
        queue_len = await rdm().r.llen(QUEUE_KEY)

        logger.info(
            f"[估价器] 成本计算已入队: task_id={task_id}, "
            f"items={len(bp_filtered_ids)}, queue_pos={queue_len}"
        )

        return jsonify({
            "status": 200,
            "data": {
                "task_id": task_id,
                "total": total,
                "queue_position": queue_len,
                "overflow_count": overflow if overflow > 0 else 0,
            },
        })

    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"启动成本计算任务失败: {traceback.format_exc()}")
        return response_helper.server_error("启动成本计算失败")


@api_price_estimator_bp.route("/calculate-cost/status", methods=["GET"])
async def calculate_cost_status():
    """
    查询成本计算进度

    读取 IndustryManager.calculate_cost 自动写入的进度 key
    （market_cost_calculation_progress:{user}:{market_id}），
    以及后台任务完成后写入的结果。

    Query Parameters:
        - task_id (string, required): 任务ID

    Responses:
        200: 进度信息
            - status: pending/running/completed/failed
            - total: 总数
            - completed: 已完成数
            - queue_position: 队列位置（pending时）
            - current_step: 当前步骤描述
            - calculated: 结果（仅 completed 时）
    """
    try:
        task_id = request.args.get("task_id")
        if not task_id:
            return response_helper.bad_request("缺少 task_id 参数")

        ctx_key = f"{TASK_CTX_PREFIX}:{task_id}"
        ctx = await rdm().r.hgetall(ctx_key)
        if not ctx:
            return response_helper.not_found("任务不存在或已过期")

        status = ctx.get("status", "pending")
        total = int(ctx.get("total", "0"))
        completed = int(ctx.get("completed", "0"))
        current_step = ctx.get("current_step", "")

        # 已完成
        if status == "completed":
            calculated_str = ctx.get("calculated", "{}")
            try:
                calculated = json.loads(calculated_str)
            except (json.JSONDecodeError, TypeError):
                calculated = {}
            return jsonify({
                "status": 200,
                "data": {
                    "status": "completed", "total": total,
                    "completed": total, "current_step": "计算完成",
                    "calculated": calculated,
                    "merged_count": int(ctx.get("merged_count", "0")),
                },
            })

        # 失败
        if status == "failed":
            return jsonify({
                "status": 200,
                "data": {
                    "status": "failed", "total": total,
                    "completed": 0, "current_step": "计算失败",
                    "error": ctx.get("error", "未知错误"),
                },
            })

        # pending → 查队列位置
        if status == "pending":
            queue_items = await rdm().r.lrange(QUEUE_KEY, 0, -1)
            pos = 0
            for i, item_str in enumerate(queue_items):
                try:
                    item = json.loads(item_str)
                    if item.get("task_id") == task_id:
                        pos = i + 1
                        break
                except (json.JSONDecodeError, TypeError):
                    pass
            return jsonify({
                "status": 200,
                "data": {
                    "status": "pending", "total": total,
                    "completed": 0, "queue_position": pos,
                    "current_step": f"队列第 {pos} 位" if pos > 0 else "排队中",
                },
            })

        # running → 读取 IndustryManager 进度
        user_name = ctx.get("user_name", "anonymous")
        market_id = int(ctx.get("market_id", "-1"))
        progress_key = f"market_cost_calculation_progress:{user_name}:{market_id}"
        total_key = f"market_cost_calculation_total:{user_name}:{market_id}"

        progress = await rdm().r.hgetall(progress_key)
        total_str = await rdm().r.get(total_key)

        calc_status = progress.get("status", "running") if progress else "running"
        calc_completed = int(progress.get("completed", "0")) if progress else completed
        calc_step = progress.get("current_step", current_step) if progress else current_step
        calc_total = int(total_str) if total_str else total

        # 检查计算是否实际完成
        lock_key = f"calculate_cost_lock:{user_name}:{market_id}"
        lock_exists = await rdm().r.get(lock_key)
        if calc_status == "running" and calc_completed >= calc_total and not lock_exists:
            calc_status = "completed"

        return jsonify({
            "status": 200,
            "data": {
                "status": calc_status,
                "total": calc_total,
                "completed": calc_completed,
                "current_step": calc_step,
            },
        })

    except Exception as e:
        traceback.print_exc()
        logger.error(f"查询成本计算状态失败: {traceback.format_exc()}")
        return response_helper.server_error("查询状态失败")


@api_price_estimator_bp.route("/result", methods=["GET"])
async def get_cached_result():
    """
    通过 UUID 获取缓存的估价结果（公开端点，用于分享链接）

    Query Parameters:
        - uuid (string, required): 估价结果 UUID

    Responses:
        200: 缓存的估价结果
        404: 结果不存在或已过期
    """
    try:
        result_uuid = request.args.get("uuid")
        if not result_uuid:
            return response_helper.bad_request("缺少 uuid 参数")

        key = f"{RESULT_CACHE_PREFIX}:{result_uuid}"
        cached = await rdm().r.get(key)
        if not cached:
            return response_helper.not_found("估价结果不存在或已过期（保存7天）")

        result_data = json.loads(cached)
        return jsonify({
            "status": 200,
            "data": result_data,
        })

    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取缓存估价结果失败: {traceback.format_exc()}")
        return response_helper.server_error("获取结果失败")
