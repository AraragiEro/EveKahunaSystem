import datetime
import traceback
from dataclasses import dataclass
from typing import List, Optional

import jwt
from quart import Blueprint, Quart
from quart import current_app as app
from quart import g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from src_v2.backend.auth import auth_required
from src_v2.core.log import logger
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.user.user_manager import UserManager
from src_v2.core.utils import KahunaException
from src_v2.model.EVE.character.character_manager import CharacterManager

# app = Quart(__name__)
# app.config['SECRET_KEY'] = 'your-secret-key-here'
# QuartSchema(app)

api_auth_bp = Blueprint('api_auth', __name__, url_prefix='/api/auth')


# 请求数据模型
@dataclass
class SignupRequest:
    """用户注册请求"""
    username: str
    password: str
    inviteCode: str


@dataclass
class LoginRequest:
    """用户登录请求"""
    username: str
    password: str


# 响应数据模型
@dataclass
class MessageResponse:
    """消息响应"""
    status: int
    message: str


@dataclass
class UserData:
    """用户数据"""
    id: str
    username: str
    roles: List[str]
    vipEndDate: Optional[str] = None


@dataclass
class LoginResponse:
    """登录响应"""
    status: int
    token: str
    user: UserData

@dataclass
class CurrentUserResponse:
    """当前用户信息响应"""
    status: int
    id: str
    username: str
    roles: List[str]
    vipEndDate: Optional[str] = None


@dataclass
class ErrorResponse:
    """错误响应"""
    status: int
    message: str

# 用户数据库模拟（实际应用中应使用真实数据库）
# users_db = {
#     'admin': {
#         'password_hash': generate_password_hash('admin123'),
#         'role': 'admin',
#         'email': 'admin@example.com'
#     }
# }


@api_auth_bp.route('/signup', methods=['POST'])
async def signup():
    """
    用户注册

    创建新用户账号。需要提供用户名、密码和有效的邀请码。注册成功后会自动使用邀请码。

    Tags:
        - 认证

    Request Body:
        - username (string, required): 用户名
        - password (string, required): 密码
        - inviteCode (string, required): 邀请码

    Responses:
        200: 注册成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误或邀请码无效
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "username": "newuser",
            "password": "password123",
            "inviteCode": "ABC123"
        }

    Example Response:
        {
            "status": 200,
            "message": "注册成功"
        }
    """
    try:
        data = await request.get_json()
        username = data.get('username')
        logger.debug(f"username: {username}")
        password = data.get('password')
        logger.debug(f"password: {password}")
        invite_code = data.get('inviteCode')
        logger.debug(f"invite_code: {invite_code}")

        if not invite_code:
            return jsonify({"status": 400, "message": "邀请码不能为空"}), 400

        # 校验邀请码
        validation_result = await permission_manager.validate_invite_code(invite_code)
        if not validation_result.get('valid'):
            return jsonify({"status": 400, "message": "邀请码不存在"}), 400

        if not validation_result.get('available'):
            return jsonify({"status": 400, "message": "邀请码已使用完"}), 400

        # 创建用户
        pass_hash = generate_password_hash(password)
        user = await UserManager().create_user(user_name=username, passwd_hash=pass_hash)
        await permission_manager.add_role_to_user(username, 'user')

        # 使用邀请码（记录使用历史）
        await permission_manager.use_invite_code(invite_code, username)

        return {"status": 200, "message": "注册成功"}
    except ValueError as e:
        return jsonify({"status": 400, "message": str(e)}), 400
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"注册失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "注册失败"}), 500


def create_token(user_id: str, role: str):
    """创建JWT token"""
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

@api_auth_bp.route('/login', methods=['POST'])
async def login(data: Optional[LoginRequest] = None, **kwargs):
    """
    用户登录

    使用用户名和密码登录，成功后返回JWT token和用户信息。

    Tags:
        - 认证

    Request Body:
        - username (string, required): 用户名
        - password (string, required): 密码

    Responses:
        200: 登录成功
            - status: 状态码 (200)
            - token: JWT认证令牌 (string)
            - user: 用户信息，包含ID、用户名、角色列表、VIP到期日期等 (object)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        401: 用户名或密码错误
            - status: 状态码 (401)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "username": "user1",
            "password": "password123"
        }

    Example Response:
        {
            "status": 200,
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "user": {
                "id": "user1",
                "username": "user1",
                "roles": ["user", "vip_alpha"],
                "vipEndDate": "2024-12-31T23:59:59"
            }
        }
    """
    try:
        # Use validated data if provided by decorator, otherwise get from request
        if data is not None:
            username = data.username
            password = data.password
        else:
            request_data = await request.get_json()
            username = request_data.get('username')
            password = request_data.get('password')

        if not username or not password:
            return {"status": 400, "message": "用户名和密码不能为空"}, 400

        passwd_hash = await UserManager().get_password_hash(username)
        if check_password_hash(passwd_hash, password) is False:
            return {"status": 401, "message": "用户名或密码错误"}, 401

        user = await UserManager().get_user(username)
        if not user:
            raise KeyError
        token = create_token(username, ",".join(await user.roles))
        roles = await user.roles
        # 获取vip等级
        vip_state = await permission_manager.get_vip_state(username)
        vip_end_date_str = None
        if vip_state:
            logger.info(f"vip_state: {vip_state.vip_level}")
            roles.append(vip_state.vip_level)
            # 格式化VIP到期日期
            if vip_state.vip_end_date:
                if hasattr(vip_state.vip_end_date, 'isoformat'):
                    vip_end_date_str = vip_state.vip_end_date.isoformat()
                else:
                    vip_end_date_str = str(vip_state.vip_end_date)
        else:
            logger.info(f"vip_state: None")

        user_data = {
            "id": username,
            "username": username,
            "roles": list(set(roles))
        }
        if vip_end_date_str:
            user_data["vipEndDate"] = vip_end_date_str

        return {
            "status": 200,
            "token": token,
            "user": user_data
        }
    except KahunaException as e:
        traceback.print_exc()
        return {"status": 500, "message": str(e)}, 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"登录失败: {traceback.format_exc()}")
        return {"status": 500, "message": "登录失败，请联系管理员"}, 500

# @validate_response(CurrentUserResponse)  # Disabled: causes response validation issues
@api_auth_bp.route('/me', methods=['GET'])
@auth_required
async def get_current_user():
    """
    获取当前用户信息

    获取当前登录用户的详细信息，包括用户ID、用户名、角色列表和VIP信息。

    Tags:
        - 认证

    Security:
        - Bearer: []

    Responses:
        200: 成功返回用户信息
            - status: 状态码 (200)
            - id: 用户ID (string)
            - username: 用户名 (string)
            - roles: 角色列表 (array)
            - vipEndDate: VIP到期日期，如果用户有VIP (string, optional)
        404: 用户不存在
            - status: 状态码 (404)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "id": "user1",
            "username": "user1",
            "roles": ["user", "vip_alpha"],
            "vipEndDate": "2024-12-31T23:59:59"
        }
    """
    try:
        user_id = g.current_user['user_id']
        user = await UserManager().get_user(user_id)
        if not user:
            return jsonify({"status": 404, "message": "用户不存在"}), 404

        # 获取vip等级
        roles = await user.roles
        vip_state = await permission_manager.get_vip_state(user_id)
        vip_end_date_str = None
        if vip_state:
            logger.info(f"vip_state: {vip_state.vip_level}")
            roles.append(vip_state.vip_level)
            if vip_state.vip_level == 'vip_omega':
                roles.append('vip_alpha')
            # 格式化VIP到期日期
            if vip_state.vip_end_date:
                if hasattr(vip_state.vip_end_date, 'isoformat'):
                    vip_end_date_str = vip_state.vip_end_date.isoformat()
                else:
                    vip_end_date_str = str(vip_state.vip_end_date)
        else:
            logger.info(f"vip_state: None")

        response_data = {
            "status": 200,
            "id": user.user_name,
            "username": user.user_name,
            "roles": list(set(roles)),
        }
        if vip_end_date_str:
            response_data["vipEndDate"] = vip_end_date_str

        return jsonify(response_data)
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取当前用户信息失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取当前用户信息失败"}), 500


@api_auth_bp.route('/logout', methods=['POST'])
@auth_required
async def logout():
    """
    用户登出

    用户登出系统。在实际应用中，可以将token加入黑名单。

    Tags:
        - 认证

    Security:
        - Bearer: []

    Responses:
        200: 登出成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "message": "登出成功"
        }
    """
    try:
        # 在实际应用中，可以将token加入黑名单
        return {"status": 200, "message": "登出成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"登出失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "登出失败"}), 500


@api_auth_bp.route('/deleteAccount', methods=['POST'])
@auth_required
async def delete_account():
    """
    注销账号

    永久删除当前用户的账号及其所有相关数据，包括角色数据、别名角色等。此操作不可恢复。

    Tags:
        - 认证

    Security:
        - Bearer: []

    Responses:
        200: 注销成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "message": "注销成功"
        }
    """
    try:
        user_id = g.current_user["user_id"]
        main_character_id = await UserManager().get_main_character_id(user_id)
        # 删除用户所有角色相关数据

        # 删除用户角色数据
        await CharacterManager().delete_all_alias_characters_of_main_character(main_character_id)
        await CharacterManager().delete_all_character_of_user(user_id)

        # 删除用户数据
        await UserManager().delete_user(user_id)

        return {"status": 200, "message": "注销成功"}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"注销账号失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "注销账号失败"}), 500
