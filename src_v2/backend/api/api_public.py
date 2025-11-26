import traceback
from quart import Blueprint, jsonify, request
from src_v2.model.EVE.asset.asset_manager import AssetManager
from src_v2.model.EVE.market.market_manager import MarketManager
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException

api_public_bp = Blueprint('api_public', __name__, url_prefix='/api/public')

@api_public_bp.route('/storage/<sid>', methods=['GET'])
async def get_public_storage_data(sid: str):
    """获取公开的资产视图数据
    
    :param sid: 资产视图SID
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
        # 根据错误消息判断返回的状态码
        error_message = str(e)
        if '不存在' in error_message:
            return jsonify({"status": 404, "message": error_message}), 404
        elif '未公开' in error_message:
            return jsonify({"status": 403, "message": error_message}), 403
        else:
            return jsonify({"status": 500, "message": error_message}), 500
    except Exception as e:
        logger.error(f"获取公开资产视图数据失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取公开资产视图数据失败"}), 500

