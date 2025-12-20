import traceback
from quart import Blueprint, jsonify, request
from src_v2.backend.auth import auth_required
from src_v2.backend.api.permission_required import role_required
from src_v2.core.database.kahuna_database_utils_v2 import EveIndustryCalculateHistoryDBUtils
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException

api_statistics_bp = Blueprint('api_statistics', __name__, url_prefix='/api/admin/statistics')

@api_statistics_bp.route('/calculateHistory/hourly', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def get_hourly_statistics():
    """获取过去一周每小时的计算统计（启动数、成功数、失败数）
    
    Query Parameters:
        days: 查询过去多少天的数据，默认7天
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
async def get_duration_statistics():
    """获取基于任务数量的完成时间区间统计（用于K线图）
    
    Returns:
        按任务数量分组的统计数据，包含最小值、最大值、平均值等
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

