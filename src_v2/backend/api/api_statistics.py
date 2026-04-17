import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any, Dict, List

from quart import Blueprint, jsonify, request

from src_v2.backend.auth import auth_required
from src_v2.backend.api.permission_required import role_required
from src_v2.core.database.kahuna_database_utils_v2 import EveIndustryCalculateHistoryDBUtils
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException

api_statistics_bp = Blueprint('api_statistics', __name__, url_prefix='/api/admin/statistics')


# 响应数据模型
@dataclass
class StatisticsResponse:
    """统计响应"""
    status: int
    data: Optional[List[Dict[str, Any]]] = None


@dataclass
class ErrorResponse:
    """错误响应"""
    status: int
    message: str


@api_statistics_bp.route('/calculateHistory/hourly', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
# @validate_response(StatisticsResponse)
async def get_hourly_statistics():
    """
    获取过去一周每小时的计算统计（启动数、成功数、失败数）
    
    获取工业计算历史记录的每小时统计数据，包括启动数、成功数和失败数。
    可以指定查询过去多少天的数据，默认查询7天。

    Tags:
        - 统计管理

    Security:
        - Bearer: []

    Parameters:
        - days (query, integer, optional): 查询过去多少天的数据，默认7天，范围1-365

    Responses:
        200: 成功返回每小时统计数据
            - status: 状态码 (200)
            - data: 统计数据列表，每个元素包含小时、启动数、成功数、失败数等 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "hour": "2024-01-01 00:00:00",
                    "total": 10,
                    "success": 8,
                    "failed": 2
                }
            ]
        }
    """
    try:
        days = request.args.get('days', 7, type=int)
        if days <= 0 or days > 365:
            days = 7
        
        statistics = await EveIndustryCalculateHistoryDBUtils.get_hourly_statistics(days=days)
        
        return jsonify({
            "status": 200,
            "data": statistics
        })
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取每小时统计失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取每小时统计失败"}), 500

@api_statistics_bp.route('/calculateHistory/duration', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
# @validate_response(StatisticsResponse)
async def get_duration_statistics():
    """
    获取基于任务数量的完成时间区间统计（用于K线图）
    
    获取按任务数量分组的完成时间统计数据，包含最小值、最大值、平均值等。
    用于生成K线图展示不同任务数量下的计算时间分布。

    Tags:
        - 统计管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回完成时间区间统计数据
            - status: 状态码 (200)
            - data: 统计数据列表，按任务数量分组，包含最小值、最大值、平均值等 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "product_count": 10,
                    "min_duration": 1.5,
                    "max_duration": 3.2,
                    "avg_duration": 2.1
                }
            ]
        }
    """
    try:
        statistics = await EveIndustryCalculateHistoryDBUtils.get_duration_statistics_by_product_count()
        
        return jsonify({
            "status": 200,
            "data": statistics
        })
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取完成时间区间统计失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取完成时间区间统计失败"}), 500


@api_statistics_bp.route('/calculateHistory/userFrequency', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def get_user_frequency_statistics():
    """
    获取用户使用频率统计（高频用户排行）
    
    获取指定时间范围内每个用户的计算使用次数统计，包括总次数、成功次数、失败次数。
    结果按使用次数降序排列，可用于识别高频用户。

    Tags:
        - 统计管理

    Security:
        - Bearer: []

    Parameters:
        - days (query, integer, optional): 查询过去多少天的数据，默认30天，范围1-365
        - limit (query, integer, optional): 返回的用户数量上限，默认100，范围1-500

    Responses:
        200: 成功返回用户频率统计
            - status: 状态码 (200)
            - data: 用户频率统计列表 (array)
                - user_name: 用户名 (string)
                - total_count: 总计算次数 (integer)
                - success_count: 成功次数 (integer)
                - failed_count: 失败次数 (integer)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "user_name": "user1",
                    "total_count": 50,
                    "success_count": 45,
                    "failed_count": 5
                }
            ]
        }
    """
    try:
        days = request.args.get('days', 30, type=int)
        limit = request.args.get('limit', 100, type=int)
        
        if days <= 0 or days > 365:
            days = 30
        if limit <= 0 or limit > 500:
            limit = 100
        
        statistics = await EveIndustryCalculateHistoryDBUtils.get_user_frequency_statistics(days=days, limit=limit)
        
        return jsonify({
            "status": 200,
            "data": statistics
        })
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取用户频率统计失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取用户频率统计失败"}), 500


@api_statistics_bp.route('/calculateHistory/userDetail', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def get_user_calculate_detail():
    """
    获取特定用户在特定时间范围的计算历史详情
    
    查询指定用户在指定时间范围内的所有计算记录，包括计划名称、产品数量、
    计算时间、成功状态等详细信息。

    Tags:
        - 统计管理

    Security:
        - Bearer: []

    Parameters:
        - user_name (query, string, required): 用户名
        - start_date (query, string, required): 起始时间，格式为 ISO 8601 (YYYY-MM-DDTHH:MM:SS)
        - end_date (query, string, required): 结束时间，格式为 ISO 8601 (YYYY-MM-DDTHH:MM:SS)

    Responses:
        200: 成功返回用户计算历史详情
            - status: 状态码 (200)
            - data: 计算历史记录列表 (array)
                - id: 记录ID (integer)
                - user_name: 用户名 (string)
                - plan_name: 计划名称 (string)
                - product_count: 产品数量 (integer)
                - calculate_start_time: 计算开始时间 (string)
                - calculate_time: 计算完成时间 (string)
                - is_success: 是否成功 (boolean)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "id": 1,
                    "user_name": "user1",
                    "plan_name": "计划A",
                    "product_count": 10,
                    "calculate_start_time": "2024-01-01T10:00:00",
                    "calculate_time": "2024-01-01T10:05:00",
                    "is_success": true
                }
            ]
        }
    """
    try:
        user_name = request.args.get('user_name', '', type=str)
        start_date_str = request.args.get('start_date', '', type=str)
        end_date_str = request.args.get('end_date', '', type=str)
        
        # 参数验证
        if not user_name:
            return jsonify({"status": 400, "message": "用户名不能为空"}), 400
        if not start_date_str or not end_date_str:
            return jsonify({"status": 400, "message": "起始时间和结束时间不能为空"}), 400
        
        # 解析日期时间
        try:
            start_date = datetime.fromisoformat(start_date_str)
            end_date = datetime.fromisoformat(end_date_str)
        except ValueError:
            return jsonify({"status": 400, "message": "时间格式错误，请使用ISO 8601格式 (YYYY-MM-DDTHH:MM:SS)"}), 400
        
        # 验证时间范围
        if start_date > end_date:
            return jsonify({"status": 400, "message": "起始时间不能晚于结束时间"}), 400
        
        records = await EveIndustryCalculateHistoryDBUtils.get_user_calculate_history_by_date_range(
            user_name=user_name,
            start_date=start_date,
            end_date=end_date
        )
        
        return jsonify({
            "status": 200,
            "data": records
        })
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取用户计算详情失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取用户计算详情失败"}), 500

