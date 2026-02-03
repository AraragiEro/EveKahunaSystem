import traceback
from dataclasses import dataclass
from typing import Optional, Any, Dict

from quart import Blueprint, jsonify, request

from src_v2.model.EVE.asset.asset_manager import AssetManager
from src_v2.model.EVE.market.market_manager import MarketManager
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException

api_public_bp = Blueprint('api_public', __name__, url_prefix='/api/public')


# 响应数据模型
@dataclass
class PublicStorageDataResponse:
    """公开资产视图数据响应"""
    status: int
    data: Optional[Dict[str, Any]] = None
    tag: Optional[str] = None
    view_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


@dataclass
class ErrorResponse:
    """错误响应"""
    status: int
    message: str


@api_public_bp.route('/storage/<sid>', methods=['GET'])
# @validate_response(PublicStorageDataResponse)
async def get_public_storage_data(sid: str):
    """
    获取公开的资产视图数据
    
    根据资产视图SID获取公开的资产视图数据。如果资产视图未公开，将返回403错误。
    对于sell类型的视图，会自动填充价格数据。

    Tags:
        - 公开接口

    Parameters:
        - sid (path, string, required): 资产视图SID

    Responses:
        200: 成功返回资产视图数据
            - status: 状态码 (200)
            - data: 资产视图数据 (object, optional)
            - tag: 资产视图标签 (string, optional)
            - view_type: 视图类型 (string, optional)
            - config: 视图配置 (object, optional)
        403: 资产视图未公开
            - status: 状态码 (403)
            - message: 错误信息 (string)
        404: 资产视图不存在
            - status: 状态码 (404)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {...},
            "tag": "标签",
            "view_type": "sell",
            "config": {...}
        }
    """
    try:
        asset_manager = AssetManager()
        
        # 获取资产视图对象以获取 view_type 和 config
        asset_view_obj = await asset_manager.get_asset_view_by_sid(sid)
        if not asset_view_obj:
            return jsonify({"status": 404, "message": "资产视图不存在"}), 404
        
        if not asset_view_obj.public:
            return jsonify({"status": 403, "message": "该资产视图未公开"}), 403
        
        # 获取资产视图数据
        output = await asset_manager.get_asset_view_data(sid)
        
        # 如果是 sell 视图，填充价格数据
        if asset_view_obj.view_type == 'sell':
            await MarketManager().update_jita_price()
            output = await asset_manager.fill_sell_price_data(output, asset_view_obj.config)
        
        return jsonify({
            "status": 200, 
            "data": output, 
            "tag": asset_view_obj.tag,
            "view_type": asset_view_obj.view_type,
            "config": asset_view_obj.config
        })
    except KahunaException as e:
        traceback.print_exc()
        # 根据错误消息判断返回的状态码
        error_message = str(e)
        if '不存在' in error_message:
            return jsonify({"status": 404, "message": error_message}), 404
        elif '未公开' in error_message:
            return jsonify({"status": 403, "message": error_message}), 403
        else:
            return jsonify({"status": 500, "message": error_message}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取公开资产视图数据失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取公开资产视图数据失败"}), 500

