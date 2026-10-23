import asyncio
import json
import traceback
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from quart import Blueprint, g, jsonify, request

from src_v2.backend.api.permission_required import role_required
from src_v2.backend.auth import auth_required
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveAssetViewDBUtils,
    EveCharacterOrdersStatsDetailDBUtils,
    EveOverviewHistoryDBUtils,
    UserDataDBUtils,
    UserWatchedSystemDBUtils,
)
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException
from src_v2.model.EVE.industry.coefficient_utils import get_system_coefficient, get_system_info_batch
from src_v2.model.EVE.sde.utils import SdeUtils

from . import utils_home

api_home_bp = Blueprint('api_home', __name__, url_prefix='/api/EVE/home')


@api_home_bp.route('/overview', methods=['POST'])
@auth_required
@role_required(['vip_alpha'])
async def get_overview():
    # 获取 JSON 请求体参数
    character_ids: Optional[List[int]] = None
    asset_mission_filters: Optional[List[Tuple[str, int]]] = None

    import time as _t
    _req_start = _t.monotonic()
    user_id = g.current_user['user_id']

    try:
        # 如果不需要强制刷新，则从缓存中获取数据
        request_data = await request.get_json()
        if not request_data.get("force_refresh", False):
            overview_data = await rdm().r.get(f"overview_data:{user_id}")
            if overview_data:
                _elapsed = _t.monotonic() - _req_start
                logger.info(f"[overview] user={user_id} 命中缓存 (耗时 {_elapsed:.2f}s)")
                # 查询多个时间点的历史记录
                today_date = utils_home.get_today_date_beijing()
                last_note_1d = None
                last_note_7d = None
                last_note_30d = None
                earliest_note = None
                
                try:
                    # 查询最早的数据（作为fallback）
                    earliest_record = await EveOverviewHistoryDBUtils.get_earliest_overview_data(
                        g.current_user['user_id']
                    )
                    if earliest_record:
                        earliest_note = earliest_record.data
                    
                    # 查询1天前的数据
                    date_1d = today_date - timedelta(days=1)
                    record_1d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
                        g.current_user['user_id'], date_1d
                    )
                    if record_1d:
                        last_note_1d = record_1d.data
                    elif earliest_note:
                        last_note_1d = earliest_note
                    
                    # 查询7天前的数据
                    date_7d = today_date - timedelta(days=7)
                    record_7d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
                        g.current_user['user_id'], date_7d
                    )
                    if record_7d:
                        last_note_7d = record_7d.data
                    elif earliest_note:
                        last_note_7d = earliest_note
                    
                    # 查询30天前的数据
                    date_30d = today_date - timedelta(days=30)
                    record_30d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
                        g.current_user['user_id'], date_30d
                    )
                    if record_30d:
                        last_note_30d = record_30d.data
                    elif earliest_note:
                        last_note_30d = earliest_note
                except Exception:
                    logger.warning("查询历史记录失败: %s", traceback.format_exc())

                return {
                    "status": 200,
                    "data": {
                        "today": json.loads(overview_data),
                        "last_note": last_note_1d,  # 保持向后兼容
                        "last_note_1d": last_note_1d,
                        "last_note_7d": last_note_7d,
                        "last_note_30d": last_note_30d,
                        "earliest_note": earliest_note
                    }
                }

        # 解析 character_ids
        if request_data and 'character_ids' in request_data:
            character_ids_list = request_data.get('character_ids')
            if character_ids_list is None:
                character_ids = None
            elif isinstance(character_ids_list, list):
                # 确保所有元素都是整数
                character_ids = []
                for cid in character_ids_list:
                    try:
                        character_ids.append(int(cid))
                    except (ValueError, TypeError):
                        continue
                # 如果列表为空，设置为 None
                if not character_ids:
                    character_ids = None
            else:
                # 单个值的情况
                try:
                    character_ids = [int(character_ids_list)]
                except (ValueError, TypeError):
                    character_ids = None

        # 解析 asset_mission_keys
        if request_data and 'asset_mission_keys' in request_data:
            asset_mission_keys = request_data.get('asset_mission_keys')
            if asset_mission_keys is None:
                asset_mission_filters = None
            elif isinstance(asset_mission_keys, list):
                asset_mission_filters = []
                for key in asset_mission_keys:
                    if not isinstance(key, str):
                        continue
                    # 解析格式: "character_123456" 或 "corp_789012"
                    try:
                        parts = key.split('_', 1)
                        if len(parts) == 2:
                            subject_type = parts[0]
                            subject_id = int(parts[1])
                            if subject_type in ('character', 'corp'):
                                asset_mission_filters.append(
                                    (subject_type, subject_id))
                    except (ValueError, TypeError):
                        continue
                # 如果列表为空，设置为 None
                if not asset_mission_filters:
                    asset_mission_filters = None
            else:
                # 单个值的情况
                if isinstance(asset_mission_keys, str):
                    try:
                        parts = asset_mission_keys.split('_', 1)
                        if len(parts) == 2:
                            subject_type = parts[0]
                            subject_id = int(parts[1])
                            if subject_type in ('character', 'corp'):
                                asset_mission_filters = [
                                    (subject_type, subject_id)]
                    except (ValueError, TypeError):
                        asset_mission_filters = None
    except Exception as e:
        logger.warning("解析请求参数失败: %s", str(e))
        character_ids = None
        asset_mission_filters = None

    # 并行获取5个数据类别的价值（避免串行累积耗时）
    logger.info(f"[overview] user={user_id} 缓存未命中，开始全量计算")
    user_id = g.current_user["user_id"]

    async def _fetch_with_timeout(name: str, coro, default, timeout: float = 30.0):
        """安全执行协程，超时或异常时返回默认值，记录详细日志"""
        import time as _t
        _start = _t.monotonic()
        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            _elapsed = _t.monotonic() - _start
            logger.info(f"[overview] {name} 完成 (耗时 {_elapsed:.2f}s)")
            return (name, result, None)
        except asyncio.TimeoutError:
            _elapsed = _t.monotonic() - _start
            logger.error(f"[overview] {name} 超时 (>{timeout}s, 实际等待 {_elapsed:.2f}s)，返回默认值")
            return (name, default, "timeout")
        except Exception:
            _elapsed = _t.monotonic() - _start
            logger.error(f"[overview] {name} 失败 (耗时 {_elapsed:.2f}s): {traceback.format_exc()}")
            return (name, default, "error")

    results = await asyncio.gather(
        _fetch_with_timeout('wallet_value',
            utils_home.get_wallet_value(user_id, character_ids=character_ids), {}, timeout=30.0),
        _fetch_with_timeout('order_value',
            utils_home.get_order_value(user_id, character_ids=character_ids), {}, timeout=30.0),
        _fetch_with_timeout('running_process_value',
            utils_home.calculate_running_process_value(user_id), {"total_value": 0.0}, timeout=30.0),
        _fetch_with_timeout('marked_asset_value',
            utils_home.get_marked_asset_value(user_id, asset_mission_filters=asset_mission_filters), 0.0, timeout=30.0),
        _fetch_with_timeout('unmarked_asset_value',
            utils_home.get_unmarked_asset_value(user_id, asset_mission_filters=asset_mission_filters), 0.0, timeout=30.0),
    )
    # 解析并行结果
    wallet_value = {}
    order_value = {}
    running_process_value = 0.0
    marked_asset_value = 0.0
    unmarked_asset_value = 0.0

    for name, value, _error in results:
        if name == 'wallet_value':
            wallet_value = value
        elif name == 'order_value':
            order_value = value
        elif name == 'running_process_value':
            running_process_value = value.get("total_value", 0.0)
        elif name == 'marked_asset_value':
            marked_asset_value = value
        elif name == 'unmarked_asset_value':
            unmarked_asset_value = value

    res = {
        "orderValue": order_value,
        "walletValue": wallet_value,
        "runningProcessValue": running_process_value,
        "markedAssetValue": marked_asset_value,
        "unmarkedAssetValue": unmarked_asset_value
    }
    await rdm().r.set(f"overview_data:{g.current_user['user_id']}", json.dumps(res))
    await rdm().r.expire(f"overview_data:{g.current_user['user_id']}", 60 * 60)
    # 同步一份五项汇总值，供仪表盘运营统计（不依赖 1h TTL 缓存）
    await utils_home.record_ops_latest_overview(g.current_user['user_id'], res)
    _recalc_elapsed = _t.monotonic() - _req_start
    logger.info(f"[overview] user={g.current_user['user_id']} 全量计算完成 (总耗时 {_recalc_elapsed:.2f}s)")
    _hist_start = _t.monotonic()

    # 查询多个时间点的历史记录
    today_date = utils_home.get_today_date_beijing()
    last_note_1d = None
    last_note_7d = None
    last_note_30d = None
    earliest_note = None
    
    try:
        # 查询最早的数据（作为fallback）
        earliest_record = await EveOverviewHistoryDBUtils.get_earliest_overview_data(
            g.current_user['user_id']
        )
        if earliest_record:
            earliest_note = earliest_record.data
        
        # 查询1天前的数据
        date_1d = today_date - timedelta(days=1)
        record_1d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
            g.current_user['user_id'], date_1d
        )
        if record_1d:
            last_note_1d = record_1d.data
        elif earliest_note:
            last_note_1d = earliest_note
        
        # 查询7天前的数据
        date_7d = today_date - timedelta(days=7)
        record_7d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
            g.current_user['user_id'], date_7d
        )
        if record_7d:
            last_note_7d = record_7d.data
        elif earliest_note:
            last_note_7d = earliest_note
        
        # 查询30天前的数据
        date_30d = today_date - timedelta(days=30)
        record_30d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
            g.current_user['user_id'], date_30d
        )
        if record_30d:
            last_note_30d = record_30d.data
        elif earliest_note:
            last_note_30d = earliest_note
    except Exception:
        logger.warning("查询历史记录失败: %s", traceback.format_exc())

    _hist_elapsed = _t.monotonic() - _hist_start
    _total = _t.monotonic() - _req_start
    logger.info(f"[overview] user={g.current_user['user_id']} 返回 (计算{_recalc_elapsed:.1f}s + 历史{_hist_elapsed:.1f}s = 总{_total:.1f}s)")
    return {
        "status": 200,
        "data": {
            "today": res,
            "last_note": last_note_1d,
            "last_note_1d": last_note_1d,
            "last_note_7d": last_note_7d,
            "last_note_30d": last_note_30d,
            "earliest_note": earliest_note
        }
    }


@api_home_bp.route('/dashboardOverview', methods=['POST'])
@auth_required
async def get_dashboard_overview():
    """获取仪表盘概览数据（无 VIP 限制）"""
    # 获取 JSON 请求体参数
    character_ids: Optional[List[int]] = None

    try:
        # 如果不需要强制刷新，则从缓存中获取数据
        request_data = await request.get_json()
        if not request_data.get("force_refresh", False):
            overview_data = await rdm().r.get(f"overview_data:{g.current_user['user_id']}")
            if overview_data:
                # 查询多个时间点的历史记录
                today_date = utils_home.get_today_date_beijing()
                last_note_1d = None
                last_note_7d = None
                last_note_30d = None
                earliest_note = None
                
                try:
                    # 查询最早的数据（作为fallback）
                    earliest_record = await EveOverviewHistoryDBUtils.get_earliest_overview_data(
                        g.current_user['user_id']
                    )
                    if earliest_record:
                        earliest_note = earliest_record.data
                    
                    # 查询1天前的数据
                    date_1d = today_date - timedelta(days=1)
                    record_1d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
                        g.current_user['user_id'], date_1d
                    )
                    if record_1d:
                        last_note_1d = record_1d.data
                    elif earliest_note:
                        last_note_1d = earliest_note
                    
                    # 查询7天前的数据
                    date_7d = today_date - timedelta(days=7)
                    record_7d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
                        g.current_user['user_id'], date_7d
                    )
                    if record_7d:
                        last_note_7d = record_7d.data
                    elif earliest_note:
                        last_note_7d = earliest_note
                    
                    # 查询30天前的数据
                    date_30d = today_date - timedelta(days=30)
                    record_30d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
                        g.current_user['user_id'], date_30d
                    )
                    if record_30d:
                        last_note_30d = record_30d.data
                    elif earliest_note:
                        last_note_30d = earliest_note
                except Exception:
                    logger.warning("查询历史记录失败: %s", traceback.format_exc())

                return {
                    "status": 200,
                    "data": {
                        "today": json.loads(overview_data),
                        "last_note": last_note_1d,  # 保持向后兼容
                        "last_note_1d": last_note_1d,
                        "last_note_7d": last_note_7d,
                        "last_note_30d": last_note_30d,
                        "earliest_note": earliest_note
                    }
                }

        # 解析 character_ids
        if request_data and 'character_ids' in request_data:
            character_ids_list = request_data.get('character_ids')
            if character_ids_list is None:
                character_ids = None
            elif isinstance(character_ids_list, list):
                # 确保所有元素都是整数
                character_ids = []
                for cid in character_ids_list:
                    try:
                        character_ids.append(int(cid))
                    except (ValueError, TypeError):
                        continue
                # 如果列表为空，设置为 None
                if not character_ids:
                    character_ids = None
            else:
                # 单个值的情况
                try:
                    character_ids = [int(character_ids_list)]
                except (ValueError, TypeError):
                    character_ids = None
    except Exception as e:
        logger.warning("解析请求参数失败: %s", str(e))
        character_ids = None

    # 并行获取3个数据类别的价值（避免串行累积耗时）
    user_id = g.current_user["user_id"]

    async def _fetch_with_default(name: str, coro, default):
        """安全执行协程，异常时返回默认值并记录日志"""
        try:
            result = await coro
            return (name, result, None)
        except Exception:
            logger.error("获取%s失败: %s", name, traceback.format_exc())
            return (name, default, None)

    results = await asyncio.gather(
        _fetch_with_default('wallet_value',
            utils_home.get_wallet_value(user_id, character_ids=character_ids), {}),
        _fetch_with_default('order_value',
            utils_home.get_order_value(user_id, character_ids=character_ids), {}),
        _fetch_with_default('running_process_value',
            utils_home.calculate_running_process_value(user_id), {"total_value": 0.0}),
    )

    # 解析并行结果
    wallet_value = {}
    order_value = {}
    running_process_value = 0.0

    for name, value, _error in results:
        if name == 'wallet_value':
            wallet_value = value
        elif name == 'order_value':
            order_value = value
        elif name == 'running_process_value':
            running_process_value = value.get("total_value", 0.0)

    res = {
        "orderValue": order_value,
        "walletValue": wallet_value,
        "runningProcessValue": running_process_value,
        "markedAssetValue": 0.0,
        "unmarkedAssetValue": 0.0
    }
    # 本接口只刷新钱包/订单/运行中，不应把 VIP overview 已算好的资产价值清零。
    # 两个接口共用 overview_data:{user} 这一个缓存 key，这里保留已有资产字段。
    try:
        cached_overview_str = await rdm().r.get(f"overview_data:{g.current_user['user_id']}")
        if cached_overview_str:
            cached_overview = json.loads(cached_overview_str)
            res["markedAssetValue"] = cached_overview.get("markedAssetValue", 0.0)
            res["unmarkedAssetValue"] = cached_overview.get("unmarkedAssetValue", 0.0)
    except Exception:
        logger.warning("合并已有 overview 资产价值失败: %s", traceback.format_exc())
    await rdm().r.set(f"overview_data:{g.current_user['user_id']}", json.dumps(res))
    await rdm().r.expire(f"overview_data:{g.current_user['user_id']}", 60 * 60)

    # 查询多个时间点的历史记录
    today_date = utils_home.get_today_date_beijing()
    last_note_1d = None
    last_note_7d = None
    last_note_30d = None
    earliest_note = None
    
    try:
        # 查询最早的数据（作为fallback）
        earliest_record = await EveOverviewHistoryDBUtils.get_earliest_overview_data(
            g.current_user['user_id']
        )
        if earliest_record:
            earliest_note = earliest_record.data
        
        # 查询1天前的数据
        date_1d = today_date - timedelta(days=1)
        record_1d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
            g.current_user['user_id'], date_1d
        )
        if record_1d:
            last_note_1d = record_1d.data
        elif earliest_note:
            last_note_1d = earliest_note
        
        # 查询7天前的数据
        date_7d = today_date - timedelta(days=7)
        record_7d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
            g.current_user['user_id'], date_7d
        )
        if record_7d:
            last_note_7d = record_7d.data
        elif earliest_note:
            last_note_7d = earliest_note
        
        # 查询30天前的数据
        date_30d = today_date - timedelta(days=30)
        record_30d = await EveOverviewHistoryDBUtils.get_overview_data_near_date(
            g.current_user['user_id'], date_30d
        )
        if record_30d:
            last_note_30d = record_30d.data
        elif earliest_note:
            last_note_30d = earliest_note
    except Exception:
        logger.warning("查询历史记录失败: %s", traceback.format_exc())

    return {
        "status": 200,
        "data": {
            "today": res,
            "last_note": last_note_1d,  # 保持向后兼容
            "last_note_1d": last_note_1d,
            "last_note_7d": last_note_7d,
            "last_note_30d": last_note_30d,
            "earliest_note": earliest_note
        }
    }


@api_home_bp.route('/dashboardStats', methods=['GET'])
@auth_required
async def get_dashboard_stats():
    """获取仪表盘运营统计数据（午夜缓存）"""
    try:
        cached = await rdm().r.get("dashboard_ops_stats")
        if cached:
            data = json.loads(cached)
            return jsonify({"status": 200, "data": data}), 200
        else:
            # 缓存未命中，立即计算并缓存
            try:
                from src_v2.backend.api.EVE.utils_home import aggregate_ops_stats
                stats = await aggregate_ops_stats()
                await rdm().r.setex("dashboard_ops_stats", 86400, json.dumps(stats))
                return jsonify({"status": 200, "data": stats}), 200
            except Exception:
                logger.error(f"即时计算运营统计失败: {traceback.format_exc()}")
                return jsonify({
                    "status": 200,
                    "data": {
                        "total_users": 0, "total_vips": 0, "total_plans": 0,
                        "total_asset_value": 0, "total_running_value": 0
                    }
                }), 200
    except Exception as e:
        logger.error(f"获取仪表盘统计数据失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取统计数据失败"}), 500


@api_home_bp.route('/serverStatus', methods=['GET'])
@auth_required
async def get_server_status():
    """获取 EVE Online TQ 服务器状态"""
    try:
        status = await rdm().r.get("esi_server_status")
        if status:
            status_str = status.decode() if isinstance(status, bytes) else status
        else:
            # 缓存未命中，主动检查
            from src_v2.model.EVE.eveesi.esi_status import check_tq_status
            status_str = await check_tq_status()
        return jsonify({"status": 200, "data": {"status": status_str}}), 200
    except Exception:
        return jsonify({"status": 200, "data": {"status": "unknown"}}), 200


@api_home_bp.route('/orderDetails', methods=['POST'])
@auth_required
@role_required(['vip_alpha'])
async def get_order_details():
    """获取订单详情列表"""
    try:
        # 获取 JSON 请求体参数
        character_ids: Optional[List[int]] = None

        try:
            request_data = await request.get_json()
            # 解析 character_ids
            if request_data and 'character_ids' in request_data:
                character_ids_list = request_data.get('character_ids')
                if character_ids_list is None:
                    character_ids = None
                elif isinstance(character_ids_list, list):
                    # 确保所有元素都是整数
                    character_ids = []
                    for cid in character_ids_list:
                        try:
                            character_ids.append(int(cid))
                        except (ValueError, TypeError):
                            continue
                    # 如果列表为空，设置为 None
                    if not character_ids:
                        character_ids = None
                else:
                    # 单个值的情况
                    try:
                        character_ids = [int(character_ids_list)]
                    except (ValueError, TypeError):
                        character_ids = None
        except Exception as e:
            logger.warning("解析请求参数失败: %s", str(e))
            character_ids = None

        # 获取订单详情
        order_details = await utils_home.get_order_details(
            g.current_user["user_id"],
            character_ids=character_ids
        )

        return jsonify({
            "status": 200,
            "data": order_details
        }), 200

    except KahunaException as e:
        traceback.print_exc()
        return jsonify({
            "status": 500,
            "message": str(e)
        }), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取订单详情失败: {traceback.format_exc()}")
        return jsonify({
            "status": 500,
            "message": "获取订单详情失败"
        }), 500


@api_home_bp.route('/saveSnapshot', methods=['POST'])
@auth_required
@role_required(['vip_alpha'])
async def save_snapshot():
    """保存当日快照"""
    try:
        user_id = g.current_user['user_id']

        # 从Redis获取当前overview数据
        overview_data_str = await rdm().r.get(f"overview_data:{user_id}")
        if not overview_data_str:
            return jsonify({
                "status": 400,
                "message": "当前没有overview数据，请先刷新数据"
            }), 400

        overview_data = json.loads(overview_data_str)

        # 处理数据（求和子结构）
        processed_data = utils_home.process_overview_data_for_history(
            overview_data)

        # 获取今日日期（+8时区）
        today_date = utils_home.get_today_date_beijing()

        # 检查今日是否已有数据
        exists = await EveOverviewHistoryDBUtils.check_date_exists(user_id, today_date)

        if exists:
            # 返回提示，需要前端确认后覆盖
            return jsonify({
                "status": 200,
                "data": {
                    "exists": True,
                    "message": "今日数据已存在，是否覆盖？"
                }
            }), 200

        # 保存数据
        await EveOverviewHistoryDBUtils.save_overview_data(
            user_id, today_date, processed_data
        )

        return jsonify({
            "status": 200,
            "data": {
                "exists": False,
                "message": "快照保存成功",
                "date": today_date.isoformat()
            }
        }), 200

    except KahunaException as e:
        traceback.print_exc()
        return jsonify({
            "status": 500,
            "message": str(e)
        }), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存快照失败: {traceback.format_exc()}")
        return jsonify({
            "status": 500,
            "message": "保存快照失败"
        }), 500


@api_home_bp.route('/saveSnapshot', methods=['PUT'])
@auth_required
@role_required(['vip_alpha'])
async def overwrite_snapshot():
    """覆盖保存当日快照（确认覆盖时调用）"""
    try:
        user_id = g.current_user['user_id']

        # 从Redis获取当前overview数据
        overview_data_str = await rdm().r.get(f"overview_data:{user_id}")
        if not overview_data_str:
            return jsonify({
                "status": 400,
                "message": "当前没有overview数据，请先刷新数据"
            }), 400

        overview_data = json.loads(overview_data_str)

        # 处理数据（求和子结构）
        processed_data = utils_home.process_overview_data_for_history(
            overview_data)

        # 获取今日日期（+8时区）
        today_date = utils_home.get_today_date_beijing()

        # 保存或覆盖数据
        await EveOverviewHistoryDBUtils.save_overview_data(
            user_id, today_date, processed_data
        )

        return jsonify({
            "status": 200,
            "data": {
                "message": "快照覆盖成功",
                "date": today_date.isoformat()
            }
        }), 200

    except KahunaException as e:
        traceback.print_exc()
        return jsonify({
            "status": 500,
            "message": str(e)
        }), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"覆盖快照失败: {traceback.format_exc()}")
        return jsonify({
            "status": 500,
            "message": "覆盖快照失败"
        }), 500


@api_home_bp.route('/history', methods=['GET'])
@auth_required
@role_required(['vip_alpha'])
async def get_history():
    """获取历史数据"""
    try:
        user_id = g.current_user['user_id']

        # 获取查询参数
        days = request.args.get('days', type=int, default=30)  # 默认查询30天

        # 计算日期范围
        today_date = utils_home.get_today_date_beijing()
        start_date = today_date - timedelta(days=days)

        # 查询历史数据
        history_records = []
        async for record in await EveOverviewHistoryDBUtils.get_overview_data_by_date_range(
            user_id, start_date, today_date
        ):
            history_records.append({
                "date": record.date.isoformat(),
                "data": record.data
            })

        return jsonify({
            "status": 200,
            "data": history_records
        }), 200

    except KahunaException as e:
        traceback.print_exc()
        return jsonify({
            "status": 500,
            "message": str(e)
        }), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取历史数据失败: {traceback.format_exc()}")
        return jsonify({
            "status": 500,
            "message": "获取历史数据失败"
        }), 500


@api_home_bp.route('/autoSaveSetting', methods=['POST'])
@auth_required
@role_required(['vip_alpha'])
async def update_auto_save_setting():
    """更新自动保存设置"""
    try:
        user_id = g.current_user['user_id']
        request_data = await request.get_json()

        auto_save = request_data.get('auto_save', False)
        if not isinstance(auto_save, bool):
            return jsonify({
                "status": 400,
                "message": "auto_save参数必须是布尔值"
            }), 400

        # 更新设置
        await UserDataDBUtils.update_user_setting(
            user_id, 'auto_save_overview_data', auto_save
        )

        return jsonify({
            "status": 200,
            "data": {
                "message": "设置更新成功",
                "auto_save": auto_save
            }
        }), 200

    except KahunaException as e:
        traceback.print_exc()
        return jsonify({
            "status": 500,
            "message": str(e)
        }), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"更新自动保存设置失败: {traceback.format_exc()}")
        return jsonify({
            "status": 500,
            "message": "更新设置失败"
        }), 500


@api_home_bp.route('/autoSaveSetting', methods=['GET'])
@auth_required
@role_required(['vip_alpha'])
async def get_auto_save_setting():
    """获取自动保存设置"""
    try:
        user_id = g.current_user['user_id']

        # 获取设置，默认为False
        auto_save = await UserDataDBUtils.get_user_setting(
            user_id, 'auto_save_overview_data', False
        )

        return jsonify({
            "status": 200,
            "data": {
                "auto_save": auto_save
            }
        }), 200

    except KahunaException as e:
        traceback.print_exc()
        return jsonify({
            "status": 500,
            "message": str(e)
        }), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取自动保存设置失败: {traceback.format_exc()}")
        return jsonify({
            "status": 500,
            "message": "获取设置失败"
        }), 500


@api_home_bp.route('/runningJobsDetails', methods=['POST'])
@auth_required
async def get_running_jobs_details():
    """获取运行中任务详情"""
    try:
        # 获取请求参数
        request_data = await request.get_json()
        skip_container_filter = request_data.get("skip_container_filter", False) if request_data else False

        # 获取运行中任务详情
        jobs_details = await utils_home.get_running_jobs_details(
            g.current_user["user_id"],
            skip_container_filter=skip_container_filter
        )

        return jsonify({
            "status": 200,
            "data": jobs_details
        }), 200

    except KahunaException as e:
        traceback.print_exc()
        return jsonify({
            "status": 500,
            "message": str(e)
        }), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取运行中任务详情失败: {traceback.format_exc()}")
        return jsonify({
            "status": 500,
            "message": "获取运行中任务详情失败"
        }), 500


@api_home_bp.route('/orderStats', methods=['POST'])
@auth_required
@role_required(['vip_alpha'])
async def get_order_stats():
    try:
        request_data = await request.get_json() or {}
        period_type = request_data.get("period_type", "month")
        periods = request_data.get("periods", 12)

        if period_type not in ("day", "week", "month"):
            period_type = "month"
        if not isinstance(periods, int) or periods < 1:
            periods = 12

        data = await utils_home.get_orders_stats_data(
            g.current_user["user_id"], period_type, periods
        )

        return jsonify({"status": 200, "data": data}), 200

    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取订单统计失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取订单统计失败"}), 500


@api_home_bp.route('/orderStatsDetail', methods=['POST'])
@auth_required
@role_required(['vip_alpha'])
async def get_order_stats_detail():
    try:
        request_data = await request.get_json() or {}
        period_type = request_data.get("period_type")
        period_start_str = request_data.get("period_start")
        is_buy_order = request_data.get("is_buy_order", False)

        if not period_type or not period_start_str:
            return jsonify({"status": 400, "message": "缺少 period_type 或 period_start"}), 400

        period_start = date.fromisoformat(period_start_str)

        records = await EveCharacterOrdersStatsDetailDBUtils.get_detail_for_period(
            g.current_user["user_id"], period_type, period_start, is_buy_order
        )

        from src_v2.model.EVE.sde import SdeUtils
        items = []
        for r in records:
            name_zh = await SdeUtils.get_name_by_id(r.type_id, zh=True)
            name_en = await SdeUtils.get_name_by_id(r.type_id, zh=False)
            items.append({
                "type_id": r.type_id,
                "name_zh": name_zh or "",
                "name_en": name_en or "",
                "order_count": r.order_count,
                "volume": r.volume,
                "total_isk": r.total_isk,
            })

        return jsonify({"status": 200, "data": items}), 200

    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取订单统计明细失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取订单统计明细失败"}), 500


@api_home_bp.route('/searchSystems', methods=['GET'])
@auth_required
async def search_systems():
    """搜索星系（通过中英文名称模糊匹配，走 SDE 模块）
    
    Query params:
        q: 搜索关键字，至少 2 个字符
    Returns:
        {status: 200, data: [{system_id, system_name, system_name_zh}, ...], count: N}
    """
    try:
        keyword = request.args.get('q', '').strip()

        # 最小搜索长度 2 字符
        if len(keyword) < 2:
            return jsonify({"status": 200, "data": [], "count": 0})

        data = await SdeUtils.search_solar_systems(keyword)
        return jsonify({"status": 200, "data": data, "count": len(data)})

    except Exception:
        logger.error(f"搜索星系失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "搜索星系失败"}), 500


@api_home_bp.route('/coefficient/addAllAssetSystems', methods=['POST'])
@auth_required
async def add_all_asset_systems():
    """从用户资产中自动发现所有有资产的星系并添加到监控列表。

    POST body: {}

    查询 eve_asset_view 表获取用户资产的 distinct system_id，
    与现有监控列表合并（不覆盖已有条目），
    通过 get_system_info_batch 获取星系名称后返回。

    Returns:
        {status: 200, data: {added_count: N, systems: [...]}, message: "已添加 N 个星系"}
    """
    from src_v2.model.EVE.industry.coefficient_utils import get_system_info_batch

    try:
        user_name = g.current_user['user_id']

        # 1. 查询 eve_asset_view 中该用户所有有资产的不同星系 ID（封装模块内实现）
        asset_system_ids = await EveAssetViewDBUtils.select_distinct_system_ids_by_user_name(user_name)

        if not asset_system_ids:
            return jsonify({
                "status": 200,
                "data": {"added_count": 0, "systems": []},
                "message": "未找到资产星系",
            })

        # 2. 查询现有监控列表（封装模块内实现）
        existing_ids = set(
            await UserWatchedSystemDBUtils.select_system_ids_by_user_name(user_name)
        )

        # 3. 过滤出新星系（不覆盖已有）
        new_ids = [sid for sid in asset_system_ids if sid not in existing_ids]

        if not new_ids:
            return jsonify({
                "status": 200,
                "data": {"added_count": 0, "systems": []},
                "message": "已添加 0 个星系",
            })

        # 4. 批量插入新星系（幂等，on_conflict_do_nothing）
        added_count = await UserWatchedSystemDBUtils.batch_add_systems_ignore_conflict(
            user_name, new_ids
        )

        # 5. 获取星系信息用于响应
        systems_info = await get_system_info_batch(new_ids)

        return jsonify({
            "status": 200,
            "data": {
                "added_count": added_count,
                "systems": systems_info,
            },
            "message": f"已添加 {added_count} 个星系",
        })

    except Exception:
        logger.error(f"批量添加资产星系失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "批量添加资产星系失败"}), 500


@api_home_bp.route('/coefficient/watchlist', methods=['GET'])
@auth_required
async def get_watchlist():
    """获取用户关注星系列表（含系数和星系信息）

    Returns:
        {status: 200, data: [{system_id, system_name, region_name, manufacturing, reaction}, ...], count: N}
    """
    try:
        user_id = g.current_user['user_id']

        # 查询用户关注的全部星系 ID（封装模块内实现）
        system_ids = await UserWatchedSystemDBUtils.select_system_ids_by_user_name(user_id)

        if not system_ids:
            return jsonify({"status": 200, "data": [], "count": 0})

        # 并行获取所有星系的系数
        coeff_tasks = [get_system_coefficient(sid) for sid in system_ids]
        coeff_results = await asyncio.gather(*coeff_tasks)

        # 批量获取星系基本信息
        system_infos = await get_system_info_batch(system_ids)
        info_map = {si["system_id"]: si for si in system_infos}

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

        return jsonify({"status": 200, "data": data, "count": len(data)})

    except Exception:
        logger.error(f"获取关注列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取关注列表失败"}), 500


@api_home_bp.route('/coefficient/add', methods=['POST'])
@auth_required
async def add_watched_system():
    """添加星系到关注列表（幂等：重复添加不报错）

    POST body: {system_id: int}

    Returns:
        {status: 200, message: "已添加关注"}
    """
    try:
        user_id = g.current_user['user_id']
        request_data = await request.get_json()
        system_id = request_data.get('system_id') if request_data else None

        if not system_id or not isinstance(system_id, int):
            return jsonify({"status": 400, "message": "缺少 system_id 参数"}), 400

        # 幂等添加关注星系（on_conflict_do_nothing）
        await UserWatchedSystemDBUtils.add_system_ignore_conflict(user_id, system_id)

        return jsonify({"status": 200, "message": "已添加关注"})

    except Exception:
        logger.error(f"添加关注星系失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加关注失败"}), 500


@api_home_bp.route('/coefficient/remove', methods=['POST'])
@auth_required
async def remove_watched_system():
    """从关注列表移除星系

    POST body: {system_id: int}

    Returns:
        {status: 200, message: "已取消关注"}
    """
    try:
        user_id = g.current_user['user_id']
        request_data = await request.get_json()
        system_id = request_data.get('system_id') if request_data else None

        if not system_id or not isinstance(system_id, int):
            return jsonify({"status": 400, "message": "缺少 system_id 参数"}), 400

        # 移除关注星系（封装模块内实现）
        await UserWatchedSystemDBUtils.delete_by_user_and_system(user_id, system_id)

        return jsonify({"status": 200, "message": "已取消关注"})

    except Exception:
        logger.error(f"取消关注星系失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "取消关注失败"}), 500
