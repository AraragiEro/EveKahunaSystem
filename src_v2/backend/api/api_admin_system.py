import traceback
from dataclasses import dataclass
from typing import Optional, Any, Dict, List

from quart import Blueprint, jsonify, request

from src_v2.backend.auth import auth_required
from src_v2.backend.api.permission_required import role_required
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException
from src_v2.backend.api import response_helper
from src_v2.core.database.connect_manager import get_redis_manager as rdm

# 企业版市场成本刷新模块为可选依赖：社区版（无 src_v2/enterprise 目录）下置 None，
# 相关端点统一返回 403「仅企业版可用」，避免顶层 ImportError 拖垮整个服务。
try:
    from src_v2.enterprise.model.market_view_cost_refresh_timer import MarketViewCostRefreshTimer
    from src_v2.enterprise.utils.cost_refresher import CostRefresher
except ImportError:  # 社区版 / 开源版独立运行
    MarketViewCostRefreshTimer = None
    CostRefresher = None
    logger.warning("企业版市场成本刷新模块不可用（src_v2.enterprise 缺失），相关管理接口将返回 403")

api_admin_system_bp = Blueprint('api_admin_system', __name__, url_prefix='/api/admin/system')


# 响应数据模型
@dataclass
class AdminSystemResponse:
    """管理员系统管理响应"""
    status: int
    data: Optional[Dict[str, Any]] = None


@dataclass
class ErrorResponse:
    """错误响应"""
    status: int
    message: str


@api_admin_system_bp.route('/market-cost/status', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def get_market_cost_status():
    """
    获取市场成本缓存刷新状态

    返回当前系统缓存的数量、flag 状态、分布式锁状态、最近一次刷新详情以及实时计算进度。

    Tags:
        - 系统管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回状态信息
            - status: 状态码 (200)
            - data: 状态详情
                - overall_status: 整体状态 (idle / running / completed / failed)
                - flag_exists: flag 是否存在 (boolean)
                - lock_exists: 分布式锁是否存在 (boolean)
                - cached_type_id_count: 当前缓存的 type_id 数量 (integer)
                - detail: 最近一次刷新的详细状态 (object)
                - progress: 实时计算进度 (object)
                    - completed: 已完成数量 (integer)
                    - total: 总数量 (integer)
                    - current_step: 当前步骤描述 (string)
                    - status: 计算状态 (string)
        403: 权限不足
        500: 服务器错误

    Example Response:
        {
            "status": 200,
            "data": {
                "overall_status": "idle",
                "flag_exists": true,
                "lock_exists": false,
                "cached_type_id_count": 1247,
                "detail": {
                    "status": "completed",
                    "triggered_by": "auto",
                    "type_id_count": 1247,
                    "current_step": "计算完成",
                    "updated_at": "2025-04-22T02:00:00+08:00"
                },
                "progress": {
                    "completed": 1247,
                    "total": 1247,
                    "current_step": "计算完成",
                    "status": "completed"
                }
            }
        }
    """
    if MarketViewCostRefreshTimer is None:
        return response_helper.forbidden("此功能仅在企业版中可用")
    try:
        timer = MarketViewCostRefreshTimer()
        result = await timer.get_refresh_status()
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取市场成本刷新状态失败: {traceback.format_exc()}")
        return response_helper.server_error("获取市场成本刷新状态失败")


@api_admin_system_bp.route('/market-cost/trigger-full-refresh', methods=['POST'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def trigger_market_cost_full_refresh():
    """
    手动触发市场成本全量刷新

    删除现有 flag，通过分布式锁启动全量刷新任务。若已有任务在运行中，返回 409 冲突。

    Tags:
        - 系统管理

    Security:
        - Bearer: []

    Responses:
        200: 任务已启动
            - status: 状态码 (200)
            - message: 成功消息 (string)
            - data: 包含 triggered_by 信息 (object)
        409: 已有任务在运行中
            - status: 状态码 (409)
            - message: 错误信息 (string)
        403: 权限不足
        500: 服务器错误

    Example Response:
        {
            "status": 200,
            "message": "全量刷新任务已启动",
            "data": {
                "triggered_by": "admin"
            }
        }
    """
    if MarketViewCostRefreshTimer is None:
        return response_helper.forbidden("此功能仅在企业版中可用")
    try:
        timer = MarketViewCostRefreshTimer()
        result = await timer.trigger_full_refresh(triggered_by="admin")
        status_code = result.get("status", 200)
        if status_code == 409:
            return jsonify(result), 409
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"触发全量刷新失败: {traceback.format_exc()}")
        return response_helper.server_error("触发全量刷新失败")


@api_admin_system_bp.route('/market-cost/trigger-price-refresh', methods=['POST'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def trigger_market_cost_price_refresh():
    """
    手动触发系统缓存价格刷新

    基于已保存的材料骨架，查询最新市场价格，快速刷新成本结果。
    不重新计算材料，只更新价格字段。

    Tags:
        - 系统管理

    Security:
        - Bearer: []

    Request Body:
        - market_zone (string, optional): 市场区域，默认 'jita'
        - price_base (string, optional): 价格基准，默认 'buy'

    Responses:
        200: 刷新完成
            - status: 状态码 (200)
            - message: 成功消息 (string)
            - data: 刷新结果
                - refreshed: 成功刷新的数量 (integer)
                - failed: 失败的数量 (integer)
                - elapsed_ms: 耗时毫秒 (integer)
        403: 权限不足
        500: 服务器错误

    Example Response:
        {
            "status": 200,
            "message": "价格刷新完成",
            "data": {
                "refreshed": 1190,
                "failed": 0,
                "elapsed_ms": 822
            }
        }
    """
    if CostRefresher is None:
        return response_helper.forbidden("此功能仅在企业版中可用")
    try:
        data = await request.get_json() or {}
        market_zone = data.get('market_zone', 'jita')
        price_base = data.get('price_base', 'buy')

        result = await CostRefresher.refresh_market_costs(
            scope="system",
            market_id=-1,
            market_zone=market_zone,
            price_base=price_base
        )

        return jsonify({
            "status": 200,
            "message": f"价格刷新完成，成功 {result['refreshed']} 个，失败 {result['failed']} 个",
            "data": result
        })
    except Exception as e:
        traceback.print_exc()
        logger.error(f"触发价格刷新失败: {traceback.format_exc()}")
        return response_helper.server_error("触发价格刷新失败")


@api_admin_system_bp.route('/market-cost/refresh-logs', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def get_market_cost_refresh_logs():
    """
    获取市场成本刷新历史记录

    返回最近的市场成本全量刷新历史，包括自动触发和手动触发的记录。

    Tags:
        - 系统管理

    Security:
        - Bearer: []

    Parameters:
        - limit (query, integer, optional): 返回条数上限，默认10，最大50

    Responses:
        200: 成功返回历史记录
            - status: 状态码 (200)
            - data: 历史记录列表 (array)
                - time: 刷新时间 (string)
                - triggered_by: 触发方式 (string) auto / admin
                - type_id_count: 计算数量 (integer)
                - status: 结果状态 (string) completed / failed
                - error: 错误信息 (string, optional)
        403: 权限不足
        500: 服务器错误

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "time": "2025-04-22T02:00:00+08:00",
                    "triggered_by": "auto",
                    "type_id_count": 1247,
                    "status": "completed",
                    "error": null
                }
            ]
        }
    """
    if MarketViewCostRefreshTimer is None:
        return response_helper.forbidden("此功能仅在企业版中可用")
    try:
        limit = request.args.get('limit', 10, type=int)
        if limit <= 0 or limit > 50:
            limit = 10

        timer = MarketViewCostRefreshTimer()
        result = await timer.get_refresh_logs(limit=limit)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取刷新历史失败: {traceback.format_exc()}")
        return response_helper.server_error("获取刷新历史失败")


@api_admin_system_bp.route('/orders-stats/status', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def get_orders_stats_flag_status():
    try:
        user_name = request.args.get('user_name', '').strip()
        if not user_name:
            from src_v2.core.database.kahuna_database_utils_v2 import VipStateDBUtils
            users = []
            async for vs in await VipStateDBUtils.select_all_vip_states():
                if vs.vip_level in ('vip_alpha', 'vip_omega'):
                    users.append(vs.user_name)
        else:
            users = [user_name]

        results = []
        for u in users:
            flag_key = f"orders_stats_refreshed:{u}"
            exists = await rdm().r.exists(flag_key)
            ttl_val = await rdm().r.ttl(flag_key) if exists else -1
            results.append({
                "user_name": u,
                "flag_exists": exists,
                "ttl_seconds": ttl_val if ttl_val else -1,
            })

        return jsonify({"status": 200, "data": results})
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取订单统计刷新状态失败: {traceback.format_exc()}")
        return response_helper.server_error("获取订单统计刷新状态失败")


@api_admin_system_bp.route('/orders-stats/flag', methods=['DELETE'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def delete_orders_stats_flag():
    try:
        user_name = request.args.get('user_name', '').strip()
        if not user_name:
            return jsonify({"status": 400, "message": "缺少参数 user_name"})

        flag_key = f"orders_stats_refreshed:{user_name}"
        await rdm().r.delete(flag_key)
        logger.info(f"管理员删除了用户 {user_name} 的订单统计刷新标记，将在下次轮询时重新刷新")
        return jsonify({"status": 200, "message": f"已删除 {user_name} 的刷新标记"})
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除订单统计刷新标记失败: {traceback.format_exc()}")
        return response_helper.server_error("删除刷新标记失败")


# ─────────────────── LP 快照管理 ───────────────────

@api_admin_system_bp.route('/lp-snapshot/flag', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def get_lp_snapshot_flag_status():
    """查询 LP 快照 Redis 标志状态"""
    try:
        exists = await rdm().r.exists("lp_snapshot_executed_today")
        ttl_val = await rdm().r.ttl("lp_snapshot_executed_today") if exists else -1
        return jsonify({
            "status": 200,
            "data": {
                "flag_exists": bool(exists),
                "ttl_seconds": ttl_val if ttl_val else -1,
            }
        })
    except Exception as e:
        logger.error(f"获取 LP 快照标志状态失败: {e}")
        return response_helper.server_error("获取 LP 快照状态失败")


@api_admin_system_bp.route('/lp-snapshot/flag', methods=['DELETE'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def delete_lp_snapshot_flag():
    """清除 LP 快照 Redis 标志，触发重新计算"""
    try:
        await rdm().r.delete("lp_snapshot_executed_today")
        logger.info("管理员清除了 LP 快照执行标志，将在下次启动或定时触发时重新计算")
        return jsonify({"status": 200, "message": "LP 快照标志已清除，系统将重新计算 LP 价值"})
    except Exception as e:
        logger.error(f"清除 LP 快照标志失败: {e}")
        return response_helper.server_error("清除 LP 快照标志失败")
