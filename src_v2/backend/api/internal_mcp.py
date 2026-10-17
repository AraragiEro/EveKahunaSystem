"""
内部 MCP API 路由

为 MCP 中间层服务提供专用的 HTTP API
安全层：共享服务密钥（X-Internal-API-Key），在 api/__init__.py 中通过
        register_service_auth(internal_mcp_bp) 注册，实现见 src_v2/backend/auth.py
"""

from quart import Blueprint, request, jsonify
from src_v2.core.log import logger
from src_v2.backend.api import response_helper

# 创建 Blueprint
internal_mcp_bp = Blueprint("internal_mcp", __name__, url_prefix="/api/internal/mcp")


# ===== QQ 相关接口 =====


@internal_mcp_bp.route("/qq/vip", methods=["GET"])
async def mcp_qq_vip():
    """MCP 内部接口：获取 QQ VIP 状态"""
    qq = request.args.get("qq", type=int)
    if not qq:
        return response_helper.bad_request("Missing qq parameter")

    logger.info(f"[Internal MCP] qq/vip: qq={qq}")

    # 调用现有业务逻辑
    try:
        from src_v2.enterprise.api.api_astrbot_service import _astrbot_qq_vip_state

        args = {"QQ": qq, "qq": qq}
        result, status = await _astrbot_qq_vip_state(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] qq/vip error: {e}")
        return response_helper.fail(str(e), 500)


@internal_mcp_bp.route("/qq/running-jobs", methods=["GET"])
async def mcp_qq_running_jobs():
    """MCP 内部接口：获取运行中任务概览"""
    qq = request.args.get("qq", type=int)
    if not qq:
        return response_helper.bad_request("Missing qq parameter")

    logger.info(f"[Internal MCP] qq/running-jobs: qq={qq}")

    try:
        from src_v2.enterprise.api.api_astrbot_service import (
            _astrbot_running_jobs_overview,
        )

        args = {"QQ": qq, "qq": qq}
        result, status = await _astrbot_running_jobs_overview(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] qq/running-jobs error: {e}")
        return response_helper.fail(str(e), 500)


@internal_mcp_bp.route("/qq/market-tags", methods=["GET"])
async def mcp_qq_market_tags():
    """MCP 内部接口：获取市场标签列表"""
    qq = request.args.get("qq", type=int)
    if not qq:
        return response_helper.bad_request("Missing qq parameter")

    logger.info(f"[Internal MCP] qq/market-tags: qq={qq}")

    try:
        from src_v2.enterprise.api.api_astrbot_service import _astrbot_market_tag_list

        args = {"QQ": qq, "qq": qq}
        result, status = await _astrbot_market_tag_list(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] qq/market-tags error: {e}")
        return response_helper.fail(str(e), 500)


# ===== 市场相关接口 =====


@internal_mcp_bp.route("/market/price", methods=["GET"])
async def mcp_market_price():
    """MCP 内部接口：获取市场价格"""
    type_name = request.args.get("type_name")
    if not type_name:
        return response_helper.bad_request("Missing type_name parameter")

    market_zone = request.args.get("market_zone", "jita")
    logger.info(f"[Internal MCP] market/price: type_name={type_name}, market_zone={market_zone}")

    try:
        from src_v2.enterprise.api.api_astrbot_service import (
            _astrbot_market_price_detail,
        )

        args = {"type_name": type_name, "name": type_name, "market_zone": market_zone}
        result, status = await _astrbot_market_price_detail(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] market/price error: {e}")
        return response_helper.fail(str(e), 500)


@internal_mcp_bp.route("/market/cost", methods=["GET"])
async def mcp_market_cost():
    """MCP 内部接口：获取生产成本

    成本缓存作用域由服务端按 QQ 绑定解析，query 里的 user_name 不再生效
    （安全审计 #8：不能让调用方指定 user_name 读写他人成本缓存）。
    """
    type_name = request.args.get("type_name")
    qq = request.args.get("qq", type=int)
    plan_name = request.args.get("plan_name", "default")
    force_recalculate = request.args.get("force_recalculate", "false").lower() == "true"

    if not type_name:
        return response_helper.bad_request("Missing type_name parameter")

    logger.info(f"[Internal MCP] market/cost: type_name={type_name}, qq={qq}, force={force_recalculate}")

    try:
        from src_v2.enterprise.api.api_astrbot_service import _astrbot_market_type_cost

        args = {
            "type_name": type_name,
            "name": type_name,
            "qq": qq,
            "plan_name": plan_name,
            "force_recalculate": force_recalculate,
        }
        result, status = await _astrbot_market_type_cost(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] market/cost error: {e}")
        return response_helper.fail(str(e), 500)


@internal_mcp_bp.route("/market/fuzz", methods=["GET"])
async def mcp_market_fuzz():
    """MCP 内部接口：模糊匹配物品名称"""
    type_name = request.args.get("type_name")
    if not type_name:
        return response_helper.bad_request("Missing type_name parameter")

    logger.info(f"[Internal MCP] market/fuzz: type_name={type_name}")

    try:
        from src_v2.enterprise.api.api_astrbot_service import _astrbot_fuzz_type_name

        args = {"type_name": type_name, "name": type_name}
        result, status = await _astrbot_fuzz_type_name(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] market/fuzz error: {e}")
        return response_helper.fail(str(e), 500)


@internal_mcp_bp.route("/market/metrics", methods=["GET"])
async def mcp_market_metrics():
    """MCP 内部接口：获取市场指标"""
    qq = request.args.get("qq", type=int)
    market_id = request.args.get("market_id", type=int)
    market_zone = request.args.get("market_zone", "jita")
    cost_calculation_mode = request.args.get("cost_calculation_mode", "rough")
    price_base = request.args.get("price_base", "buy")

    if not qq or not market_id:
        return jsonify(
            {"status": 400, "message": "Missing qq or market_id parameter"}
        ), 400

    logger.info(f"[Internal MCP] market/metrics: qq={qq}, market_id={market_id}")

    try:
        from src_v2.enterprise.api.api_astrbot_service import (
            _astrbot_market_type_metrics,
        )

        args = {
            "QQ": qq,
            "qq": qq,
            "market_id": market_id,
            "marketId": market_id,
            "market_zone": market_zone,
            "marketZone": market_zone,
            "cost_calculation_mode": cost_calculation_mode,
            "costCalculationMode": cost_calculation_mode,
            "price_base": price_base,
            "priceBase": price_base,
        }
        result, status = await _astrbot_market_type_metrics(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] market/metrics error: {e}")
        return response_helper.fail(str(e), 500)


# ===== 工业相关接口 =====


@internal_mcp_bp.route("/industry/missing-blueprints", methods=["GET"])
async def mcp_industry_missing_blueprints():
    """MCP 内部接口：获取缺失蓝图工作流汇总"""
    qq = request.args.get("qq", type=int)
    planname = request.args.get("planname")

    if not qq or not planname:
        return jsonify(
            {"status": 400, "message": "Missing qq or planname parameter"}
        ), 400

    logger.info(
        f"[Internal MCP] industry/missing-blueprints: qq={qq}, planname={planname}"
    )

    try:
        from src_v2.enterprise.api.api_astrbot_service import (
            _astrbot_plan_missing_blueprint_workflow_summary,
        )

        args = {
            "QQ": qq,
            "qq": qq,
            "planname": planname,
            "plan_name": planname,
            "planName": planname,
        }
        result, status = await _astrbot_plan_missing_blueprint_workflow_summary(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] industry/missing-blueprints error: {e}")
        return response_helper.fail(str(e), 500)


@internal_mcp_bp.route("/company/medica-vouchers", methods=["GET"])
async def mcp_company_medica_vouchers():
    """MCP 内部接口：获取公司医疗抵扣额度（只返回指定 QQ 的记录）

    Query params:
        qq: QQ 号码（必填）

    Returns:
        {
            "status": 200,
            "data": [["角色名", "额度", "QQ号"]],
            "count": 1
        }
    """
    qq = request.args.get("qq", type=int)
    if not qq:
        return response_helper.bad_request("Missing qq parameter")

    logger.info(f"[Internal MCP] company/medica-vouchers: qq={qq}")

    try:
        from src_v2.enterprise.api.api_astrbot_service import (
            _astrbot_get_company_medica_vouchers,
        )

        args = {"qq": qq, "QQ": qq}
        result, status = await _astrbot_get_company_medica_vouchers(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] company/medica-vouchers error: {e}")
        return response_helper.fail(str(e), 500)


# ===== 系数相关接口 =====


@internal_mcp_bp.route("/coefficient/watched-systems", methods=["GET"])
async def mcp_coefficient_watched_systems():
    """MCP 内部接口：根据 QQ 获取用户关注星系的系数

    Query params:
        qq: QQ 号码

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
    qq = request.args.get("qq", type=int)
    if not qq:
        return response_helper.bad_request("Missing qq parameter")

    logger.info(f"[Internal MCP] coefficient/watched-systems: qq={qq}")

    try:
        from src_v2.core.database.kahuna_database_utils_v2 import (
            UserQQBindingDBUtils,
            UserWatchedSystemDBUtils,
        )
        from src_v2.model.EVE.industry.coefficient_utils import (
            get_system_coefficient,
            get_system_info_batch,
        )
        import asyncio

        # 1. QQ → user_name
        binding = await UserQQBindingDBUtils.select_by_user_qq(qq)
        if not binding:
            return jsonify({
                "status": 200,
                "is_bind": False,
                "message": "QQ 未绑定",
                "data": [],
                "count": 0,
                "note": "manufacturing 和 reaction 为小数系数，展示时请 ×100 转换为百分比。null 表示暂无数据。",
            })

        user_name = binding.user_name

        # 2. 查询关注星系列表（封装模块内实现）
        system_ids = await UserWatchedSystemDBUtils.select_system_ids_by_user_name(user_name)

        if not system_ids:
            return jsonify({
                "status": 200,
                "data": [],
                "count": 0,
                "note": "manufacturing 和 reaction 为小数系数，展示时请 ×100 转换为百分比。null 表示暂无数据。",
            })

        # 3. 并行获取所有星系的系数
        coeff_tasks = [get_system_coefficient(sid) for sid in system_ids]
        coeff_results = await asyncio.gather(*coeff_tasks)

        # 4. 批量获取星系基本信息（名称、区域）
        system_infos = await get_system_info_batch(system_ids)
        info_map = {si["system_id"]: si for si in system_infos}

        # 5. 组装响应
        data = []
        for sid, coeff in zip(system_ids, coeff_results):
            info = info_map.get(sid, {})
            data.append({
                "system_id": sid,
                "system_name": info.get("system_name", ""),
                "region_name": info.get("region_name", ""),
                "manufacturing": coeff.get("manufacturing"),
                "reaction": coeff.get("reaction"),
            })

        return jsonify({
            "status": 200,
            "data": data,
            "count": len(data),
            "note": "manufacturing 和 reaction 为小数系数，展示时请 ×100 转换为百分比（如 0.023 → 2.30%）。null 表示暂无数据。",
        })

    except ImportError:
        return jsonify(
            {"status": 503, "message": "Required module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] coefficient/watched-systems error: {e}")
        return response_helper.fail(str(e), 500)
