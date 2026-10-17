import traceback
import time

from quart import Blueprint, request

from src_v2.backend.api.response_helper import ok, fail
from src_v2.backend.auth import auth_required
from src_v2.core.log import logger
from src_v2.model.EVE.industry.pi_calculator import PIProfitCalculator

api_pi_bp = Blueprint("api_pi", __name__, url_prefix="/api/EVE/pi")
pi_calc = PIProfitCalculator()

# ===== 缓存（30 分钟有效期）=====
_result_cache: dict = {}
CACHE_TTL = 1800
FORCE_COOLDOWN = 60  # 强制刷新冷却时间（秒）
_last_force_time: float = 0


def _product_to_dict(p) -> dict:
    d = {
        "type_id": p.type_id,
        "name_zh": p.name_zh,
        "name_en": p.name_en,
        "tier": p.tier,
        "output_per_cycle": p.output_per_cycle,
        "cycle_time": p.cycle_time,
        "path_count": p.path_count,
    }
    if p.best_profit_path:
        d["best_profit_path"] = _path_profit_to_dict(p.best_profit_path)
    else:
        d["best_profit_path"] = None
    if p.all_paths:
        d["all_paths"] = [_path_profit_to_dict(pp) for pp in p.all_paths]
    else:
        d["all_paths"] = []
    return d


def _path_profit_to_dict(pp) -> dict:
    return {
        "path_description": pp.path.path_description,
        "tiers": [
            {
                "tier": ft.tier,
                "type_id": ft.type_id,
                "name_zh": ft.name_zh,
                "factory_count": ft.factory_count,
            }
            for ft in pp.path.tiers
        ],
        "input_items": pp.input_items,
        "output_item": pp.output_item,
        "input_total_cost": pp.input_total_cost,
        "output_total_revenue": pp.output_total_revenue,
        "profit": pp.profit,
        "profit_margin_pct": pp.profit_margin_pct,
        "tier_details": getattr(pp, "tier_details", []),
    }


# ------------------------------------------------------------------
# 1. GET /products
# ------------------------------------------------------------------

@api_pi_bp.route("/products", methods=["GET"])
async def get_pi_products():
    try:
        await pi_calc.build_hierarchy()
        products = await pi_calc.get_products(min_tier=2)
        return ok(data={"products": [_product_to_dict(p) for p in products]})
    except Exception as e:
        logger.error(f"获取PI产品列表失败: {e}")
        return fail(str(e), 500)


# ------------------------------------------------------------------
# 2. GET /products/<type_id>/paths
# ------------------------------------------------------------------

@api_pi_bp.route("/products/<int:type_id>/paths", methods=["GET"])
async def get_product_paths(type_id: int):
    try:
        await pi_calc.build_hierarchy()
        product = await pi_calc.calculate_product(
            type_id,
            price_base=request.args.get("price_base", "sell"),
            material_price_base=request.args.get("material_base", "sell"),
        )
        if not product:
            return fail(f"产品 {type_id} 不存在", 404)
        return ok(data=_product_to_dict(product))
    except Exception as e:
        logger.error(f"获取PI产品生产路径失败 (type_id={type_id}): {e}")
        return fail(str(e), 500)


# ------------------------------------------------------------------
# 3. POST /calculate
# ------------------------------------------------------------------

@api_pi_bp.route("/calculate", methods=["POST"])
async def calculate_products():
    try:
        data = await request.get_json()
        type_ids = data.get("type_ids", [])
        price_base = data.get("price_base", "sell")
        material_price_base = data.get("material_base", "sell")
        if not type_ids:
            return fail("type_ids 不能为空", 400)

        await pi_calc.build_hierarchy()
        results = []
        for tid in type_ids:
            product = await pi_calc.calculate_product(
                tid, price_base=price_base, material_price_base=material_price_base
            )
            if product:
                results.append(_product_to_dict(product))
        return ok(data={"products": results})
    except Exception as e:
        logger.error(f"计算PI产品利润失败: {e}")
        return fail(str(e), 500)


# ------------------------------------------------------------------
# 4. POST /calculate-all
# ------------------------------------------------------------------

@api_pi_bp.route("/calculate-all", methods=["POST"])
async def calculate_all_products():
    global _last_force_time
    try:
        data = await request.get_json(silent=True) or {}
        price_base = data.get("price_base", "sell")
        material_price_base = data.get("material_base", "sell")
        min_tier = data.get("min_tier", 2)
        force = data.get("force", False)

        # 强制刷新防滥用：间隔不少于 FORCE_COOLDOWN 秒
        if force and time.time() - _last_force_time < FORCE_COOLDOWN:
            remain = int(FORCE_COOLDOWN - (time.time() - _last_force_time))
            return fail(f"刷新过于频繁，请 {remain} 秒后再试", 429)

        # 检查缓存
        cache_key = f"{price_base}_{material_price_base}"
        if not force and cache_key in _result_cache:
            entry = _result_cache[cache_key]
            if time.time() - entry["time"] < CACHE_TTL:
                return entry["data"]

        await pi_calc.build_hierarchy()
        products = await pi_calc.calculate_all(
            price_base=price_base, material_price_base=material_price_base
        )
        results = [
            _product_to_dict(p) for p in products if p.tier >= min_tier
        ]
        resp = ok(data={"products": results})

        # 写入缓存
        _result_cache[cache_key] = {"data": resp, "time": time.time()}
        if force:
            _last_force_time = time.time()
        return resp
    except Exception as e:
        logger.error(f"计算全部PI产品利润失败: {e}")
        return fail(str(e), 500)
