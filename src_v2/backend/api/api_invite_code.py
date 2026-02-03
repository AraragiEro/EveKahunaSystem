import traceback
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from quart import request, jsonify, g, Blueprint

from src_v2.backend.auth import auth_required
from src_v2.backend.api.permission_required import permission_required
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException
from src_v2.core.permission.permission_manager import permission_manager

api_invite_code_bp = Blueprint('api_invite_code', __name__, url_prefix='/api/invite-code')


# 请求数据模型
@dataclass
class GenerateInviteCodeRequest:
    """生成邀请码请求"""
    usedCountMax: int = 1


@dataclass
class ValidateInviteCodeRequest:
    """校验邀请码请求"""
    inviteCode: str


# 响应数据模型
@dataclass
class InviteCodeData:
    """邀请码数据"""
    inviteCode: str
    creatorUserName: str
    usedCountMax: int


@dataclass
class GenerateInviteCodeResponse:
    """生成邀请码响应"""
    status: int
    data: InviteCodeData


@dataclass
class InviteCodeListItem:
    """邀请码列表项"""
    inviteCode: str
    creatorUserName: str
    createDate: str
    usedCountCurrent: int
    usedCountMax: int
    remainingCount: int


@dataclass
class InviteCodeListResponse:
    """邀请码列表响应"""
    status: int
    data: List[InviteCodeListItem]


@dataclass
class InviteCodeUserItem:
    """邀请码用户项"""
    userName: str
    usedDate: str


@dataclass
class InviteCodeUsersResponse:
    """邀请码用户列表响应"""
    status: int
    data: List[InviteCodeUserItem]


@dataclass
class ValidateInviteCodeResponse:
    """校验邀请码响应"""
    status: int
    data: Dict[str, Any]


@dataclass
class ErrorResponse:
    """错误响应"""
    status: int
    message: str


@api_invite_code_bp.route("", methods=["POST"])
@auth_required
@permission_required(["admin:write"])
# @validate_request(GenerateInviteCodeRequest)
# @validate_response(GenerateInviteCodeResponse)
async def generate_invite_code():
    """
    生成邀请码
    
    生成一个新的邀请码，可以设置使用次数上限。创建者自动设置为当前登录用户。

    Tags:
        - 邀请码管理

    Security:
        - Bearer: []

    Request Body:
        - usedCountMax (integer, optional): 使用次数上限，默认1，必须为正整数

    Responses:
        200: 成功生成邀请码
            - status: 状态码 (200)
            - data: 邀请码信息，包含邀请码、创建者用户名、使用次数上限 (object)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "usedCountMax": 10
        }

    Example Response:
        {
            "status": 200,
            "data": {
                "inviteCode": "ABC123",
                "creatorUserName": "admin",
                "usedCountMax": 10
            }
        }
    """
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
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"生成邀请码失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "生成邀请码失败"}), 500


@api_invite_code_bp.route("", methods=["GET"])
@auth_required
@permission_required(["admin:read"])
# @validate_response(InviteCodeListResponse)
async def get_invite_code_list():
    """
    获取邀请码列表
    
    获取系统中所有邀请码的列表，可以筛选只显示可用的邀请码。

    Tags:
        - 邀请码管理

    Security:
        - Bearer: []

    Parameters:
        - onlyAvailable (query, boolean, optional): 是否只返回可用的邀请码，默认false

    Responses:
        200: 成功返回邀请码列表
            - status: 状态码 (200)
            - data: 邀请码列表，每个元素包含邀请码、创建者、创建日期、使用次数等信息 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "inviteCode": "ABC123",
                    "creatorUserName": "admin",
                    "createDate": "2024-01-01T00:00:00",
                    "usedCountCurrent": 5,
                    "usedCountMax": 10,
                    "remainingCount": 5
                }
            ]
        }
    """
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
        
        return {"status": 200, "data": formatted_codes}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取邀请码列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取邀请码列表失败"}), 500


@api_invite_code_bp.route("/<invite_code>/users", methods=["GET"])
@auth_required
@permission_required(["admin:read"])
# @validate_response(InviteCodeUsersResponse)
async def get_invite_code_users(invite_code: str):
    """
    获取使用该邀请码的用户列表
    
    获取使用指定邀请码注册的所有用户列表，包括用户名和使用日期。

    Tags:
        - 邀请码管理

    Security:
        - Bearer: []

    Parameters:
        - invite_code (path, string, required): 邀请码

    Responses:
        200: 成功返回用户列表
            - status: 状态码 (200)
            - data: 用户列表，每个元素包含用户名和使用日期 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "userName": "user1",
                    "usedDate": "2024-01-01T00:00:00"
                }
            ]
        }
    """
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
        
        return {"status": 200, "data": formatted_users}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取邀请码用户列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取邀请码用户列表失败"}), 500


@api_invite_code_bp.route("/validate", methods=["POST"])
# @validate_request(ValidateInviteCodeRequest)
# @validate_response(ValidateInviteCodeResponse)
async def validate_invite_code():
    """
    校验邀请码（公开接口，用于注册时校验）
    
    校验邀请码是否有效和可用。此接口为公开接口，不需要认证，用于用户注册前的邀请码校验。

    Tags:
        - 邀请码管理

    Request Body:
        - inviteCode (string, required): 要校验的邀请码

    Responses:
        200: 邀请码有效且可用
            - status: 状态码 (200)
            - data: 邀请码信息，包含有效性、可用性、创建日期等 (object)
        400: 邀请码无效或已使用完
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "inviteCode": "ABC123"
        }

    Example Response:
        {
            "status": 200,
            "data": {
                "valid": true,
                "available": true,
                "createDate": "2024-01-01T00:00:00"
            }
        }
    """
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
        
        return {"status": 200, "data": result}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"校验邀请码失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "校验邀请码失败"}), 500

