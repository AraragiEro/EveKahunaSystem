from quart import request, jsonify, g, Blueprint
from src_v2.backend.auth import auth_required
from src_v2.backend.api.permission_required import permission_required
from src_v2.core.log import logger
import traceback
from src_v2.core.utils import KahunaException
from src_v2.core.database.kahuna_database_utils_v2 import VipStateDBUtils, UserDBUtils
from src_v2.core.database.connect_manager import postgres_manager as dbm
from sqlalchemy import select
from datetime import datetime

api_vip_bp = Blueprint('api_vip', __name__, url_prefix='/api/vip')


@api_vip_bp.route("", methods=["GET"])
@auth_required
@permission_required(["admin:read"])
async def get_all_vip_states():
    """获取所有VIP状态列表"""
    try:
        vip_states = []
        async with await VipStateDBUtils.select_all_vip_states() as iterator:
            async for vip_state in iterator:
                # 格式化日期
                vip_end_date_str = ''
                if vip_state.vip_end_date:
                    if hasattr(vip_state.vip_end_date, 'isoformat'):
                        vip_end_date_str = vip_state.vip_end_date.isoformat()
                    else:
                        vip_end_date_str = str(vip_state.vip_end_date)
                
                vip_states.append({
                    "userName": vip_state.user_name or '',
                    "vipLevel": vip_state.vip_level or '',
                    "vipEndDate": vip_end_date_str
                })
        
        return jsonify({"status": 200, "data": vip_states})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取VIP状态列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取VIP状态列表失败"}), 500


@api_vip_bp.route("/<user_name>", methods=["PUT"])
@auth_required
@permission_required(["admin:write"])
async def update_vip_state(user_name: str):
    """更新指定用户的VIP状态"""
    try:
        data = await request.get_json()
        vip_level = data.get('vipLevel')
        vip_end_date_str = data.get('vipEndDate')
        
        # 验证VIP等级
        if vip_level is not None and vip_level not in ['vip_alpha', 'vip_omega']:
            return jsonify({"status": 400, "message": "VIP等级必须是 vip_alpha 或 vip_omega"}), 400
        
        # 解析日期时间
        vip_end_date = None
        if vip_end_date_str:
            try:
                # 处理ISO格式日期字符串，支持带Z和不带时区的情况
                date_str = vip_end_date_str.replace('Z', '+00:00')
                # 如果字符串中没有时区信息，尝试直接解析
                if '+' not in date_str and date_str[-1] != 'Z' and 'T' in date_str:
                    vip_end_date = datetime.fromisoformat(date_str)
                elif '+' in date_str or date_str.endswith('+00:00'):
                    vip_end_date = datetime.fromisoformat(date_str)
                else:
                    # 尝试其他格式
                    vip_end_date = datetime.fromisoformat(date_str)
            except (ValueError, AttributeError) as e:
                logger.error(f"日期解析失败: {vip_end_date_str}, 错误: {e}")
                return jsonify({"status": 400, "message": f"日期时间格式错误: {str(e)}"}), 400
        
        # 更新VIP状态
        await VipStateDBUtils.update_vip_state(
            user_name=user_name,
            vip_level=vip_level,
            vip_end_date=vip_end_date
        )
        
        return jsonify({"status": 200, "message": "更新成功"})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"更新VIP状态失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "更新VIP状态失败"}), 500


@api_vip_bp.route("/search-users", methods=["GET"])
@auth_required
@permission_required(["admin:read"])
async def search_users():
    """搜索用户（用于自动补全）"""
    try:
        query = request.args.get('query', '').strip()
        limit = int(request.args.get('limit', 20))
        
        if not query:
            return jsonify({"status": 200, "data": []})
        
        users = []
        async with dbm.get_session() as session:
            # 使用LIKE进行模糊搜索
            stmt = select(UserDBUtils.cls_model).where(
                UserDBUtils.cls_model.user_name.ilike(f'%{query}%')
            ).limit(limit)
            result = await session.execute(stmt)
            for user in result.scalars():
                users.append({
                    "userName": user.user_name
                })
        
        return jsonify({"status": 200, "data": users})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"搜索用户失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "搜索用户失败"}), 500

