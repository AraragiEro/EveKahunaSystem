import json
import traceback
from datetime import timedelta
from typing import List, Optional, Tuple

from quart import Blueprint, g, jsonify, request

from src_v2.backend.api.permission_required import role_required
from src_v2.backend.auth import auth_required
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.kahuna_database_utils_v2 import EveOverviewHistoryDBUtils, UserDataDBUtils
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException

from . import utils_home

api_home_bp = Blueprint('api_home', __name__, url_prefix='/api/EVE/home')


@api_home_bp.route('/overview', methods=['POST'])
@auth_required
@role_required(['vip_alpha'])
async def get_overview():
    # 获取 JSON 请求体参数
    character_ids: Optional[List[int]] = None
    asset_mission_filters: Optional[List[Tuple[str, int]]] = None

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

    # 钱包价值
    wallet_value = {}
    try:
        wallet_value = await utils_home.get_wallet_value(g.current_user["user_id"], character_ids=character_ids)
    except Exception:
        logger.error("获取钱包价值失败: %s", traceback.format_exc())

    # 订单价值
    order_value = {}
    try:
        order_value = await utils_home.get_order_value(g.current_user["user_id"], character_ids=character_ids)
    except Exception:
        logger.error("获取订单价值失败: %s", traceback.format_exc())

    # 运行中流程价值
    running_process_value = 0.0
    try:
        running_process_data = await utils_home.calculate_running_process_value(g.current_user["user_id"])
        running_process_value = running_process_data.get("total_value", 0.0)
    except Exception:
        logger.error("获取运行中流程价值失败: %s", traceback.format_exc())

    # 标记资产价值
    marked_asset_value = 0.0
    try:
        marked_asset_value = await utils_home.get_marked_asset_value(
            g.current_user["user_id"],
            asset_mission_filters=asset_mission_filters
        )
    except Exception:
        logger.error("获取标记资产价值失败: %s", traceback.format_exc())

    # 非标记资产价值
    unmarked_asset_value = 0.0
    try:
        unmarked_asset_value = await utils_home.get_unmarked_asset_value(
            g.current_user["user_id"],
            asset_mission_filters=asset_mission_filters
        )
    except Exception:
        logger.error("获取非标记资产价值失败: %s", traceback.format_exc())

    res = {
        "orderValue": order_value,
        "walletValue": wallet_value,
        "runningProcessValue": running_process_value,
        "markedAssetValue": marked_asset_value,
        "unmarkedAssetValue": unmarked_asset_value
    }
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
@role_required(['vip_alpha'])
async def get_running_jobs_details():
    """获取运行中任务详情"""
    try:
        # 获取运行中任务详情
        jobs_details = await utils_home.get_running_jobs_details(
            g.current_user["user_id"]
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
