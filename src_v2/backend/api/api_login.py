import datetime
import re
import traceback
import uuid
from dataclasses import dataclass
from typing import List, Optional

import jwt
from quart import Blueprint, Quart
from quart import current_app as app
from quart import g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from src_v2.backend.auth import auth_required, check_csrf
from src_v2.core.log import logger
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.user import refresh_token_store
from src_v2.core.user.user_manager import UserManager
from src_v2.core.utils import KahunaException, login_guard
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.backend.api import response_helper

# app = Quart(__name__)
# app.config['SECRET_KEY'] = 'your-secret-key-here'
# QuartSchema(app)

api_auth_bp = Blueprint('api_auth', __name__, url_prefix='/api/auth')

# 预生成的 dummy 哈希：用户不存在时也执行一次哈希校验，
# 使「用户不存在」与「密码错误」两条路径的耗时与行为一致，避免用户名枚举
_DUMMY_PASSWORD_HASH = generate_password_hash(uuid.uuid4().hex)

# 注册端点错误统一文案（不区分「用户名已存在」与其它创建失败，避免用户名枚举）
_SIGNUP_FAILED_MESSAGE = "注册失败，请更换用户名后重试"

# 密码强度要求：至少 8 位，且同时包含字母和数字
_PASSWORD_MIN_LENGTH = 8
_PASSWORD_HAS_LETTER = re.compile(r"[A-Za-z]")
_PASSWORD_HAS_DIGIT = re.compile(r"\d")


def _is_strong_password(password: str) -> bool:
    """密码强度校验：至少 8 位，且同时包含字母和数字"""
    if not password or len(password) < _PASSWORD_MIN_LENGTH:
        return False
    return bool(_PASSWORD_HAS_LETTER.search(password)) and bool(_PASSWORD_HAS_DIGIT.search(password))


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
        - password (string, required): 密码（至少 8 位，且同时包含字母和数字）
        - inviteCode (string, required): 邀请码

    Responses:
        200: 注册成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误、密码强度不足或邀请码无效（用户名已存在也归入此通用文案）
            - status: 状态码 (400)
            - message: 错误信息 (string)
        429: 注册请求过于频繁（同一 IP 每分钟最多 5 次）
            - status: 状态码 (429)
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
        username = None
        data = await request.get_json()
        username = data.get('username')
        password = data.get('password')
        invite_code = data.get('inviteCode')
        # 调试日志只记录载荷已接收，绝不打印明文密码与邀请码
        logger.debug("recv signup payload")

        # 注册限流：同一 IP 每分钟最多 5 次（Redis 异常时 fail-open 放行）
        client_ip = await login_guard.client_ip()
        if not await login_guard.hit(f"signup:ip:{client_ip}", 5, 60):
            return response_helper.fail("注册请求过于频繁，请稍后再试", 429)

        if not password or not _is_strong_password(password):
            return response_helper.bad_request("密码强度不足：至少 8 位且需包含字母和数字")

        if not invite_code:
            return response_helper.bad_request("邀请码不能为空")

        # 校验邀请码
        validation_result = await permission_manager.validate_invite_code(invite_code)
        if not validation_result.get('valid'):
            return response_helper.bad_request("邀请码不存在")

        if not validation_result.get('available'):
            return response_helper.bad_request("邀请码已使用完")

        # 创建用户
        pass_hash = generate_password_hash(password)
        user = await UserManager().create_user(user_name=username, passwd_hash=pass_hash)
        await permission_manager.add_role_to_user(username, 'user')

        # 使用邀请码（记录使用历史）
        await permission_manager.use_invite_code(invite_code, username)

        return {"status": 200, "message": "注册成功"}
    except ValueError as e:
        return response_helper.bad_request(str(e))
    except KahunaException:
        # 用户名已存在等业务异常统一走通用文案，不回显内部信息（防用户名枚举）
        logger.warning(f"注册失败（业务异常，已隐藏细节）: username={username}")
        return response_helper.bad_request(_SIGNUP_FAILED_MESSAGE)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"注册失败: {traceback.format_exc()}")
        return response_helper.server_error("注册失败")


def create_token(user_id: str, role: str):
    """创建 JWT access token（15min 短期）"""
    payload = {
        'user_id': user_id,
        'role': role,
        'type': 'access',
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')


async def create_refresh_token(user_id: str) -> str:
    """创建 refresh token（委托 refresh_token_store，哈希后存 Redis，7 天绝对过期）

    保留原函数名与签名，内部实现改为 refresh_token_store（明文不落 Redis）。
    """
    return await refresh_token_store.issue_refresh_token(user_id)


async def delete_refresh_token(token: str):
    """删除 refresh token（委托 refresh_token_store）"""
    await refresh_token_store.revoke_refresh_token(token)

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
        429: 登录尝试过于频繁（15 分钟内失败 5 次）
            - status: 状态码 (429)
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

        # 登录限流：用户名与 IP 各一个固定窗口计数（15 分钟 / 5 次）
        # 计数在密码校验之前检查，超限直接 429，不再校验密码；登录成功后会清空计数
        client_ip = await login_guard.client_ip()
        user_allowed = await login_guard.hit(f"login_fail:user:{username}", 5, 15 * 60)
        ip_allowed = await login_guard.hit(f"login_fail:ip:{client_ip}", 5, 15 * 60)
        if not (user_allowed and ip_allowed):
            return {"status": 429, "message": "登录尝试过于频繁，请稍后再试"}, 429

        passwd_hash = await UserManager().get_password_hash(username)
        if not passwd_hash:
            # 用户不存在：同样执行一次哈希校验，避免通过响应时间/异常行为枚举用户名
            check_password_hash(_DUMMY_PASSWORD_HASH, password)
            return {"status": 401, "message": "用户名或密码错误"}, 401
        if check_password_hash(passwd_hash, password) is False:
            return {"status": 401, "message": "用户名或密码错误"}, 401

        user = await UserManager().get_user(username)
        if not user:
            raise KeyError
        token = create_token(username, ",".join(await user.roles))
        refresh_token = await create_refresh_token(username)
        csrf_token = uuid.uuid4().hex
        # 登录成功清空失败计数
        await login_guard.reset(f"login_fail:user:{username}")
        await login_guard.reset(f"login_fail:ip:{client_ip}")
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

        from quart import make_response as _make_response
        response = await _make_response({
            "status": 200,
            "token": token,
            "user": user_data
        })
        cookie_secure = not app.config.get('TESTING', False) and not app.config.get('DEBUG', False)
        response.set_cookie('auth_token', token, httponly=True, secure=cookie_secure, samesite='Lax', max_age=900, path='/')
        if refresh_token:
            response.set_cookie('refresh_token', refresh_token, httponly=True, secure=cookie_secure, samesite='Lax', max_age=7*24*3600, path='/api/auth/refresh')
        response.set_cookie('csrf_token', csrf_token, httponly=False, secure=cookie_secure, samesite='Lax', max_age=7*24*3600, path='/')
        return response
    except KahunaException as e:
        traceback.print_exc()
        return {"status": 500, "message": str(e)}, 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"登录失败: {traceback.format_exc()}")
        return {"status": 500, "message": "登录失败，请联系管理员"}, 500


@api_auth_bp.route('/refresh', methods=['POST'])
async def refresh_token():
    """刷新 access token（使用 refresh_token cookie）

    读取 httpOnly refresh_token cookie，在 Redis 中校验并**轮换**：
    旧 token 立即失效，下发新的 refresh_token / access_token / csrf_token cookie。
    轮换失败（不存在、已失效、Redis 不可用）返回 401 并清除 refresh_token cookie。
    """
    try:
        refresh = request.cookies.get('refresh_token')
        cookie_secure = not app.config.get('TESTING', False) and not app.config.get('DEBUG', False)
        from quart import make_response as _make_response

        if not refresh:
            return {"status": 401, "message": "缺少 refresh token"}, 401

        # 轮换：旧 token 立即失效，返回 (user_id, 新 raw token)
        rotated = await refresh_token_store.rotate_refresh_token(refresh)
        if not rotated:
            response = await _make_response({"status": 401, "message": "无效或过期的 refresh token"})
            response.status_code = 401
            response.set_cookie('refresh_token', '', httponly=True, secure=cookie_secure, samesite='Lax', max_age=0, path='/api/auth/refresh')
            return response

        user_id, new_refresh_token = rotated

        # 获取用户角色
        user = await UserManager().get_user(user_id)
        if not user:
            # 用户已不存在：撤销刚签发的新 token，避免残留
            await refresh_token_store.revoke_refresh_token(new_refresh_token)
            response = await _make_response({"status": 401, "message": "用户不存在"})
            response.status_code = 401
            response.set_cookie('refresh_token', '', httponly=True, secure=cookie_secure, samesite='Lax', max_age=0, path='/api/auth/refresh')
            return response

        roles = ",".join(await user.roles)
        new_token = create_token(user_id, roles)

        response = await _make_response({"status": 200, "message": "token 已刷新"})
        response.set_cookie('auth_token', new_token, httponly=True, secure=cookie_secure, samesite='Lax', max_age=900, path='/')
        # 重新下发轮换后的 refresh_token（7 天绝对过期，path 保持 /api/auth/refresh）
        response.set_cookie('refresh_token', new_refresh_token, httponly=True, secure=cookie_secure, samesite='Lax', max_age=7*24*3600, path='/api/auth/refresh')
        # 同时刷新 csrf_token，避免 csrf cookie 过期导致后续 POST 请求 403
        response.set_cookie('csrf_token', uuid.uuid4().hex, httponly=False, secure=cookie_secure, samesite='Lax', max_age=7*24*3600, path='/')
        return response
    except Exception as e:
        traceback.print_exc()
        logger.error(f"刷新 token 失败: {traceback.format_exc()}")
        return {"status": 500, "message": "刷新失败"}, 500


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
        jwt_role = g.current_user.get('role', 'user')

        # 基础响应：从 JWT 直接构建，不依赖数据库
        response_data = {
            "status": 200,
            "id": user_id,
            "username": user_id,
            "roles": [jwt_role],
        }

        # 从数据库丰富角色和VIP信息（错误容忍：DB不可用不影响认证状态）
        try:
            user = await UserManager().get_user(user_id)
            if user:
                roles = await user.roles
                response_data["roles"] = list(set(roles + [jwt_role]))

                vip_state = await permission_manager.get_vip_state(user_id)
                if vip_state:
                    response_data["roles"].append(vip_state.vip_level)
                    if vip_state.vip_level == 'vip_omega':
                        response_data["roles"].append('vip_alpha')
                    response_data["roles"] = list(set(response_data["roles"]))
                    if vip_state.vip_end_date:
                        response_data["vipEndDate"] = (
                            vip_state.vip_end_date.isoformat()
                            if hasattr(vip_state.vip_end_date, 'isoformat')
                            else str(vip_state.vip_end_date)
                        )
        except Exception as db_err:
            logger.warning(f"获取用户详细信息时DB查询失败(已降级): {db_err}")

        # 同时刷新 csrf_token cookie，防止 csrf 过期导致后续 POST 请求 403
        cookie_secure = not app.config.get('TESTING', False) and not app.config.get('DEBUG', False)
        response = jsonify(response_data)
        response.set_cookie('csrf_token', uuid.uuid4().hex, httponly=False, secure=cookie_secure, samesite='Lax', max_age=7*24*3600, path='/')
        return response
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取当前用户信息失败: {traceback.format_exc()}")
        return response_helper.server_error("获取当前用户信息失败")


@api_auth_bp.route('/logout', methods=['POST'])
@auth_required
@check_csrf
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
        # 清除 refresh_token（撤销当前这一个 token）
        refresh = request.cookies.get('refresh_token')
        if refresh:
            await refresh_token_store.revoke_refresh_token(refresh)
        # 清除 Cookie
        from quart import make_response as _make_response
        response = await _make_response({"status": 200, "message": "登出成功"})
        cookie_secure = not app.config.get('TESTING', False) and not app.config.get('DEBUG', False)
        response.set_cookie('auth_token', '', httponly=True, secure=cookie_secure, samesite='Lax', max_age=0, path='/')
        response.set_cookie('refresh_token', '', httponly=True, secure=cookie_secure, samesite='Lax', max_age=0, path='/api/auth/refresh')
        response.set_cookie('csrf_token', '', httponly=False, secure=cookie_secure, samesite='Lax', max_age=0, path='/')
        return response
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"登出失败: {traceback.format_exc()}")
        return response_helper.server_error("登出失败")


@api_auth_bp.route('/deleteAccount', methods=['POST'])
@auth_required
@check_csrf
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

        # 撤销该用户全部 refresh token（账号已注销，所有会话都应失效）
        try:
            await refresh_token_store.revoke_all_for_user(user_id)
        except Exception as revoke_err:
            logger.warning(f"注销账号时撤销 refresh token 失败: {revoke_err}")

        # 清除认证 Cookie
        from quart import make_response as _make_response
        response = await _make_response({"status": 200, "message": "注销成功"})
        cookie_secure = not app.config.get('TESTING', False) and not app.config.get('DEBUG', False)
        response.set_cookie('auth_token', '', httponly=True, secure=cookie_secure, samesite='Lax', max_age=0, path='/')
        response.set_cookie('refresh_token', '', httponly=True, secure=cookie_secure, samesite='Lax', max_age=0, path='/api/auth/refresh')
        response.set_cookie('csrf_token', '', httponly=False, secure=cookie_secure, samesite='Lax', max_age=0, path='/')
        return response
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"注销账号失败: {traceback.format_exc()}")
        return response_helper.server_error("注销账号失败")
