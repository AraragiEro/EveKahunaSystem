import datetime
import secrets
import jwt
from functools import wraps
from quart import request, jsonify, g
from quart import current_app as app

from src_v2.core.config.config import config
from src_v2.core.log import logger
from src_v2.core.permission.permission_manager import permission_manager

def verify_jwt_token(token: str):
    """验证JWT token"""
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def auth_required(f):
    """认证装饰器（优先 httpOnly Cookie，兼容 Bearer Header）"""

    @wraps(f)
    async def decorated_function(*args, **kwargs):
        # 优先读取 httpOnly Cookie
        token = request.cookies.get('auth_token')

        # 回退到 Authorization: Bearer <token> header
        if not token:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]

        if not token:
            response = jsonify({'error': '缺少认证token'})
            response.status_code = 401
            return response

        payload = verify_jwt_token(token)

        if not payload:
            response = jsonify({'error': '无效的token'})
            response.status_code = 401
            return response

        g.current_user = payload
        return await f(*args, **kwargs)

    return decorated_function


def check_csrf(f):
    """CSRF 保护装饰器（Double-Submit Cookie 模式）

    对 POST/PUT/PATCH/DELETE 请求，验证 X-CSRF-Token header 与 csrf_token cookie 匹配。
    GET/HEAD/OPTIONS 请求跳过验证。
    """

    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return await f(*args, **kwargs)

        csrf_cookie = request.cookies.get('csrf_token')
        csrf_header = request.headers.get('X-CSRF-Token')

        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            response = jsonify({'error': 'CSRF validation failed'})
            response.status_code = 403
            return response

        return await f(*args, **kwargs)

    return decorated_function


def register_csrf_protection(blueprint):
    """为 Blueprint 注册 CSRF 保护 before_request 钩子

    对所有 POST/PUT/PATCH/DELETE 请求执行 CSRF 验证。
    若请求携带有效认证（Cookie 或 Bearer header），强制执行 CSRF；
    公开端点（无认证信息）自动跳过。
    """

    @blueprint.before_request
    async def _csrf_check():
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return None

        # 仅 Cookie 认证需要 CSRF 保护（Bearer header 自带 CSRF 免疫）
        auth_cookie = request.cookies.get('auth_token')
        if not auth_cookie:
            return None  # Bearer header 或公开端点，跳过

        # Cookie 认证 → 强制执行 CSRF
        csrf_cookie = request.cookies.get('csrf_token')
        csrf_header = request.headers.get('X-CSRF-Token')

        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            response = jsonify({'error': 'CSRF validation failed'})
            response.status_code = 403
            return response

        return None


async def is_admin_user(user_id: str) -> bool:
    """判断用户是否具备 admin 角色（含其继承的父角色）

    管理员能力（代查他人资源）必须由此显式判定，绝不能以请求参数里的
    user_name 作为权限来源。
    """
    try:
        user_roles = await permission_manager.get_user_roles(user_id)
    except Exception as e:
        logger.warning(f"获取用户 {user_id} 的角色失败: {e}")
        return False

    all_roles = set(user_roles or [])
    for role in user_roles or []:
        try:
            descendant_roles = await permission_manager.get_all_descendant_roles(role)
            if descendant_roles:
                all_roles.update(descendant_roles)
        except Exception as e:
            logger.warning(f"获取角色 {role} 的父角色失败: {e}")
    return "admin" in all_roles


def get_service_api_key() -> str:
    """读取服务间认证密钥

    优先 [SERVICE] API_KEY，兼容旧配置 [MCP] API_KEY（二者填一个即可）。
    """
    return (
        config.get('SERVICE', 'API_KEY', fallback='')
        or config.get('MCP', 'API_KEY', fallback='')
        or ''
    ).strip()


def register_service_auth(blueprint, name: str = None):
    """为 Blueprint 注册服务间认证（共享 API Key 模式）

    适用场景：调用方是**其他服务/容器**（MCP 中间件、QQ 机器人），它们无法交互式登录，
    因此走不了 JWT 认证路径。方案是共享一把服务密钥，请求头携带 X-Internal-API-Key，
    服务端据此确认"请求来自可信服务"，从而信任该服务声明的用户身份（如 QQ 号）。

    行为：
    - 密钥未配置 → 一律 503（fail-closed，避免"忘记配置 = 不校验"这一历史漏洞成因）
    - 密钥缺失/错误 → 默认 401；MODE=warn 时仅告警放行（供灰度切换使用）
    - 不再使用 IP 白名单做认证：反向代理后 remote_addr 恒为内网地址，无法区分真实来源

    配置（config.toml）：
        [SERVICE]
        API_KEY = "<secrets.token_urlsafe(32) 生成>"   # 未配置则本蓝图拒绝所有请求
        MODE = "enforce"                                # enforce（默认）| warn（灰度期仅告警）
    """
    label = name or blueprint.name

    @blueprint.before_request
    async def _service_auth():
        expected = get_service_api_key()
        if not expected:
            logger.error(
                f"[service-auth] {label} 拒绝请求：config.toml 未配置 [SERVICE] API_KEY"
            )
            response = jsonify({'status': 503, 'message': 'Service API key not configured'})
            response.status_code = 503
            return response

        provided = request.headers.get('X-Internal-API-Key', '') or ''
        matched = False
        try:
            matched = secrets.compare_digest(
                provided.encode('utf-8'), expected.encode('utf-8')
            )
        except Exception:
            matched = False

        if matched:
            return None

        mode = (config.get('SERVICE', 'MODE', fallback='enforce') or 'enforce').strip().lower()
        if mode == 'warn':
            logger.warning(
                f"[service-auth] {label} 服务密钥缺失或错误（MODE=warn，已放行）"
                f" path={request.path} remote_addr={request.remote_addr}"
            )
            return None

        logger.warning(
            f"[service-auth] {label} 拒绝未授权请求 path={request.path}"
            f" remote_addr={request.remote_addr}"
        )
        response = jsonify({'status': 401, 'message': 'Unauthorized'})
        response.status_code = 401
        return response
