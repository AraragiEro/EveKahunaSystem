"""
内部 MCP API 路由

为 MCP 中间层服务提供专用的 HTTP API
这些路由应该限制为仅限本地或内部网络访问
"""

from quart import Blueprint, request, jsonify
from src_v2.core.log import logger

# 创建 Blueprint
internal_mcp_bp = Blueprint("internal_mcp", __name__, url_prefix="/api/internal/mcp")


# ===== QQ 相关接口 =====


@internal_mcp_bp.route("/qq/vip", methods=["GET"])
async def mcp_qq_vip():
    """MCP 内部接口：获取 QQ VIP 状态"""
    qq = request.args.get("qq", type=int)
    if not qq:
        return jsonify({"status": 400, "message": "Missing qq parameter"}), 400

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
        return jsonify({"status": 500, "message": str(e)}), 500


@internal_mcp_bp.route("/qq/running-jobs", methods=["GET"])
async def mcp_qq_running_jobs():
    """MCP 内部接口：获取运行中任务概览"""
    qq = request.args.get("qq", type=int)
    if not qq:
        return jsonify({"status": 400, "message": "Missing qq parameter"}), 400

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
        return jsonify({"status": 500, "message": str(e)}), 500


@internal_mcp_bp.route("/qq/market-tags", methods=["GET"])
async def mcp_qq_market_tags():
    """MCP 内部接口：获取市场标签列表"""
    qq = request.args.get("qq", type=int)
    if not qq:
        return jsonify({"status": 400, "message": "Missing qq parameter"}), 400

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
        return jsonify({"status": 500, "message": str(e)}), 500


# ===== 市场相关接口 =====


@internal_mcp_bp.route("/market/price", methods=["GET"])
async def mcp_market_price():
    """MCP 内部接口：获取市场价格"""
    type_name = request.args.get("type_name")
    if not type_name:
        return jsonify({"status": 400, "message": "Missing type_name parameter"}), 400

    logger.info(f"[Internal MCP] market/price: type_name={type_name}")

    try:
        from src_v2.enterprise.api.api_astrbot_service import (
            _astrbot_market_price_detail,
        )

        args = {"type_name": type_name, "name": type_name}
        result, status = await _astrbot_market_price_detail(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] market/price error: {e}")
        return jsonify({"status": 500, "message": str(e)}), 500


@internal_mcp_bp.route("/market/cost", methods=["GET"])
async def mcp_market_cost():
    """MCP 内部接口：获取生产成本"""
    type_name = request.args.get("type_name")
    user_name = request.args.get("user_name", "system")
    plan_name = request.args.get("plan_name", "default")

    if not type_name:
        return jsonify({"status": 400, "message": "Missing type_name parameter"}), 400

    logger.info(f"[Internal MCP] market/cost: type_name={type_name}, user={user_name}")

    try:
        from src_v2.enterprise.api.api_astrbot_service import _astrbot_market_type_cost

        args = {
            "type_name": type_name,
            "name": type_name,
            "user_name": user_name,
            "plan_name": plan_name,
        }
        result, status = await _astrbot_market_type_cost(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] market/cost error: {e}")
        return jsonify({"status": 500, "message": str(e)}), 500


@internal_mcp_bp.route("/market/fuzz", methods=["GET"])
async def mcp_market_fuzz():
    """MCP 内部接口：模糊匹配物品名称"""
    type_name = request.args.get("type_name")
    if not type_name:
        return jsonify({"status": 400, "message": "Missing type_name parameter"}), 400

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
        return jsonify({"status": 500, "message": str(e)}), 500


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
        return jsonify({"status": 500, "message": str(e)}), 500


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
        return jsonify({"status": 500, "message": str(e)}), 500


@internal_mcp_bp.route("/company/medica-vouchers", methods=["GET"])
async def mcp_company_medica_vouchers():
    """MCP 内部接口：获取公司医疗抵扣额度"""
    logger.info("[Internal MCP] company/medica-vouchers")

    try:
        from src_v2.enterprise.api.api_astrbot_service import (
            _astrbot_get_company_medica_vouchers,
        )

        args = {}
        result, status = await _astrbot_get_company_medica_vouchers(args)
        return jsonify(result), status
    except ImportError:
        return jsonify(
            {"status": 503, "message": "Enterprise module not available"}
        ), 503
    except Exception as e:
        logger.error(f"[Internal MCP] company/medica-vouchers error: {e}")
        return jsonify({"status": 500, "message": str(e)}), 500
