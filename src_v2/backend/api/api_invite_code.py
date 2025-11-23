from quart import request, jsonify, g, Blueprint
from src_v2.backend.auth import auth_required
from src_v2.backend.api.permission_required import permission_required
from src_v2.core.log import logger
import traceback
from src_v2.core.utils import KahunaException
from src_v2.core.permission.permission_manager import permission_manager

api_invite_code_bp = Blueprint('api_invite_code', __name__, url_prefix='/api/invite-code')


@api_invite_code_bp.route("", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
async def generate_invite_code():
    """生成邀请码"""
    try:
        data = await request.get_json()
        creator_user_name = g.current_user['user_id']
        used_count_max = data.get('usedCountMax', 1)
        
        if not isinstance(used_count_max, int) or used_count_max <= 0:
            return jsonify({"status": 400, "message": "使用次数上限必须为正整数"}), 400
        
        invite_code = await permission_manager.generate_invite_code(
            creator_user_name=creator_user_name,
            used_count_max=used_count_max
        )
        
        return jsonify({
            "status": 200,
            "data": {
                "inviteCode": invite_code,
                "creatorUserName": creator_user_name,
                "usedCountMax": used_count_max
            }
        })
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"生成邀请码失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "生成邀请码失败"}), 500


@api_invite_code_bp.route("", methods=["GET"])
@auth_required
@permission_required(["admin:read"])
async def get_invite_code_list():
    """获取邀请码列表"""
    try:
        only_available = request.args.get('onlyAvailable', 'false').lower() == 'true'
        
        invite_codes = await permission_manager.get_invite_code_list(only_available=only_available)
        
        # 转换字段名为驼峰格式并格式化日期
        formatted_codes = []
        for code in invite_codes:
            # 确保数值字段不为 None
            used_count_current = code.get('used_count_current')
            if used_count_current is None:
                used_count_current = 0
            used_count_max = code.get('used_count_max')
            if used_count_max is None:
                used_count_max = 0
            
            # 格式化日期
            create_date = code.get('create_date')
            create_date_str = ''
            if create_date:
                if hasattr(create_date, 'isoformat'):
                    create_date_str = create_date.isoformat()
                else:
                    create_date_str = str(create_date)
            
            formatted_code = {
                "inviteCode": code.get('invite_code') or '',
                "creatorUserName": code.get('creator_user_name') or '',
                "createDate": create_date_str,
                "usedCountCurrent": used_count_current,
                "usedCountMax": used_count_max,
                "remainingCount": used_count_max - used_count_current
            }
            formatted_codes.append(formatted_code)
        
        return jsonify({"status": 200, "data": formatted_codes})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取邀请码列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取邀请码列表失败"}), 500


@api_invite_code_bp.route("/<invite_code>/users", methods=["GET"])
@auth_required
@permission_required(["admin:read"])
async def get_invite_code_users(invite_code: str):
    """获取使用该邀请码的用户列表"""
    try:
        users = await permission_manager.get_invite_code_users(invite_code)
        
        # 转换字段名为驼峰格式并格式化日期
        formatted_users = []
        for user in users:
            # 格式化日期
            used_date = user.get('used_date')
            used_date_str = ''
            if used_date:
                if hasattr(used_date, 'isoformat'):
                    used_date_str = used_date.isoformat()
                else:
                    used_date_str = str(used_date)
            
            formatted_user = {
                "userName": user.get('user_name') or '',
                "usedDate": used_date_str
            }
            formatted_users.append(formatted_user)
        
        return jsonify({"status": 200, "data": formatted_users})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取邀请码用户列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取邀请码用户列表失败"}), 500


@api_invite_code_bp.route("/validate", methods=["POST"])
async def validate_invite_code():
    """校验邀请码（公开接口，用于注册时校验）"""
    try:
        data = await request.get_json()
        invite_code = data.get('inviteCode')
        
        if not invite_code:
            return jsonify({"status": 400, "message": "邀请码不能为空"}), 400
        
        result = await permission_manager.validate_invite_code(invite_code)
        
        if not result.get('valid'):
            return jsonify({"status": 400, "message": "邀请码不存在"}), 400
        
        if not result.get('available'):
            return jsonify({"status": 400, "message": "邀请码已使用完"}), 400
        
        # 格式化日期
        if result.get('create_date'):
            result['createDate'] = result['create_date'].isoformat() if hasattr(result['create_date'], 'isoformat') else str(result['create_date'])
            del result['create_date']
        
        return jsonify({"status": 200, "data": result})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"校验邀请码失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "校验邀请码失败"}), 500

