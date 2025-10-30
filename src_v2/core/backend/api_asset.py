from quart import Blueprint, jsonify, request

# from ..service.asset_server.asset_manager import AssetManager

api_asset_bp = Blueprint('api_asset', __name__, url_prefix='/api/asset')

@api_asset_bp.route('/container/list', methods=['GET'])
async def get_container_list():
    res = []

    # for k, v in AssetManager.container_dict.items():
    #     res.append({
    #         'name': v.asset_name,
    #     })

    return res

@api_asset_bp.route('/container/delete', methods=['POST'])
async def delete_container():
    data = await request.json
    id = data.get('id')
    # AssetManager.container_dict.pop(id)
    return jsonify({'code': 200, 'message': '删除成功'})