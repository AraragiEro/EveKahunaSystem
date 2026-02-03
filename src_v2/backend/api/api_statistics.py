import traceback
from dataclasses import dataclass
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

