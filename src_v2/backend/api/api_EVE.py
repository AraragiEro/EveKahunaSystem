import traceback
from dataclasses import dataclass
from typing import Optional

import jwt
from quart import Blueprint
from quart import current_app as app
from quart import g, jsonify, redirect, request

from src_v2.backend.auth import auth_required
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.model.EVE.eveesi.oauth import CALLBACK_LOCAL_HOST, get_auth_url, get_token

# app = Quart(__name__)
# app.config['SECRET_KEY'] = 'your-secret-key-here'
# QuartSchema(app)

api_EVE_bp = Blueprint("api_EVE", __name__, url_prefix="/api/EVE")


# 响应数据模型
@dataclass
class OAuthAuthorizeResponse:
    """OAuth 授权链接响应"""

    status: int
    url: str


@dataclass
class ErrorResponse:
    """错误响应"""

    status: int
    message: str


@dataclass
class AuthStatusResponse:
    """认证状态响应"""

    status: int
    authStatus: Optional[str] = None
    characterName: Optional[str] = None


@api_EVE_bp.route("/oauth/authorize", methods=["GET"])
@auth_required
# @validate_response(OAuthAuthorizeResponse)
async def get_oauth_url():
    """
    获取 EVE Online OAuth 授权链接

    获取用于 EVE Online ESI API 授权的 OAuth 授权链接。
    用户需要访问返回的 URL 来完成授权流程。

    Tags:
        - EVE OAuth

    Security:
        - Bearer: []

    Responses:
        200: 成功返回授权链接
            - status: 状态码 (200)
            - url: OAuth 授权链接 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "url": "https://login.eveonline.com/v2/oauth/authorize?..."
        }
    """
    try:
        # 从g.current_user获取用户ID
        user_id = g.current_user["user_id"]
        # 传递user_id到get_auth_url
        url, _ = get_auth_url(user_id=user_id)
        return {"status": 200, "url": url}
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取授权链接失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取授权链接失败"}), 500


@api_EVE_bp.route("/oauth/callback", methods=["GET"])
async def eve_oauth_callback(
    code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None
):
    """
    处理 EVE Online OAuth 回调

    这是 EVE Online OAuth 授权流程的回调端点。当用户在 EVE Online 授权页面完成授权后，
    EVE Online 会将用户重定向到此端点，并携带授权码 (code) 和状态 (state)。

    此端点会：
    1. 验证回调参数（code、state）
    2. 从 state 中解析用户 ID 和原始 OAuth state
    3. 使用授权码交换访问令牌和刷新令牌
    4. 将角色信息保存到数据库
    5. 设置认证状态缓存
    6. 重定向用户回前端应用

    Tags:
        - EVE OAuth

    Parameters:
        - code (query, string, optional): OAuth 授权码，由 EVE Online 提供
        - state (query, string, optional): 状态参数，包含用户 ID 和原始 OAuth state 的 JWT token
        - error (query, string, optional): 错误信息，如果授权过程中出现错误

    Responses:
        302: 重定向到前端应用（成功时）
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Error Response:
        {
            "status": 400,
            "message": "缺少授权码"
        }
    """
    try:
        # 获取回调参数（如果函数参数未提供，则从 request.args 获取）
        if code is None:
            code = request.args.get("code")
        if state is None:
            state = request.args.get("state")
        if error is None:
            error = request.args.get("error")

        # 检查是否有错误
        if error:
            logger.error(f"EVE OAuth 回调包含错误: {error}")
            return jsonify({"status": 400, "message": f"OAuth错误: {error}"}), 400

        # 检查是否有授权码
        if not code:
            logger.error("EVE OAuth 回调缺少授权码")
            return jsonify({"status": 400, "message": "缺少授权码"}), 400

        # 从state中解析用户ID和原始oauth_state
        user_id = None
        original_oauth_state = None

        if state:
            try:
                # 解码state中的JWT token
                state_payload = jwt.decode(
                    state, app.config["SECRET_KEY"], algorithms=["HS256"]
                )
                user_id = state_payload.get("user_id")
                original_oauth_state = state_payload.get("oauth_state")  # 获取原始state
                logger.debug(
                    f"从state解析到用户ID: {user_id}, 原始oauth_state: {original_oauth_state}"
                )
            except jwt.ExpiredSignatureError:
                logger.error("OAuth state已过期")
                return jsonify(
                    {"status": 400, "message": "认证链接已过期，请重新开始认证"}
                ), 400
            except jwt.InvalidTokenError as e:
                logger.error(f"OAuth state无效: {e}")
                return jsonify(
                    {"status": 400, "message": "无法验证用户身份，请重新开始认证"}
                ), 400

        # 如果无法从state获取user_id，记录错误
        if not user_id or not original_oauth_state:
            logger.error("无法从OAuth state中获取用户ID或原始state")
            return jsonify(
                {"status": 400, "message": "无法验证用户身份，请重新开始认证"}
            ), 400

        # 记录接收到的回调信息用于调试
        logger.debug(f"收到EVE OAuth回调 - code: {code[:10]}..., user_id: {user_id}")

        # 获取原始协议，优先从 X-Forwarded-Proto 获取，否则使用当前请求的协议
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)

        # 获取原始主机名，优先从 X-Forwarded-Host 获取，否则使用当前请求的主机
        # request.headers.get('X-Forwarded-Host', request.host)
        host = "bottest.setcr-alero.icu"

        # 获取完整的路径和查询参数
        full_path = request.full_path

        # 构建用于fetch_token的URL
        # 注意：不再替换state，因为oauth._state现在已经是encoded_state
        # 详见 oauth.py 中的 get_auth_url 函数
        from urllib.parse import parse_qs, urlencode, urlparse

        parsed = urlparse(full_path)
        query_params = parse_qs(parsed.query)
        # 使用URL中的state（即encoded_state，与oauth._state匹配）
        new_query = urlencode(query_params, doseq=True)
        auth_response_url = f"{scheme}://{host}{parsed.path}?{new_query}"

        # 使用 auth_response_url 交换授权码以获取 token
        # 现在auth_response_url包含原始的oauth_state，fetch_token可以正确验证
        try:
            access_token, refresh_token, expires_at = get_token(auth_response_url)
        except KahunaException as e:
            logger.error(f"获取token失败: {str(e)}")
            return jsonify({"status": 500, "message": str(e)}), 500
        except Exception as e:
            logger.error(f"获取token失败: {traceback.format_exc()}")
            return jsonify({"status": 500, "message": "获取token失败"}), 500

        try:
            # 使用从state解析出的user_id，而不是g.current_user
            character = await CharacterManager().insert_new_character(
                {
                    "ac_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_at": expires_at,
                },
                user_id,  # 使用从state解析出的user_id
            )
        except KahunaException as e:
            logger.error(f"角色信息入库失败: {str(e)}")
            return jsonify({"status": 500, "message": str(e)}), 500
        except Exception as e:
            logger.error(f"角色信息入库失败: {traceback.format_exc()}")
            return jsonify({"status": 500, "message": "角色信息入库失败"}), 500

        logger.info(
            f"成功获取 EVE token。用户ID: {user_id}, Access token 过期时间: {expires_at}, 角色名称: {character.character_name}"
        )

        # 设置用户认证缓存状态
        await rdm().redis.hset(
            f"esi_auth_status:user_{user_id}",
            mapping={
                "authStatus": "success",
                "characterName": character.character_name,
            },
        )
        await rdm().redis.expire(f"esi_auth_status:user_{user_id}", 300)  # 5分钟
        # 完成后，将用户重定向回前端应用程序
        frontend_redirect_url = (
            "https://" + CALLBACK_LOCAL_HOST + "/setting/characterSetting/auth/close"
            if CALLBACK_LOCAL_HOST
            else None
        )
        return redirect(frontend_redirect_url)

    except KahunaException as e:
        logger.error(f"EVE OAuth 回调处理失败: {str(e)}")
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"EVE OAuth 回调处理失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "认证失败"}), 500

        # 如果出错，将用户重定向到前端的错误页面
        # frontend_error_url = "http://localhost:8080/auth-error"  # 请替换为您的前端错误页面 URL
        # return redirect(frontend_error_url)


@api_EVE_bp.route("/oauth/authStatus", methods=["GET"])
@auth_required
# @validate_response(AuthStatusResponse)
async def get_auth_status():
    """
    获取 EVE Online OAuth 认证状态

    获取当前用户的 EVE Online OAuth 认证状态。此接口会返回最近一次认证操作的结果，
    包括认证状态和角色名称。调用后会自动清除缓存的状态信息。

    Tags:
        - EVE OAuth

    Security:
        - Bearer: []

    Responses:
        200: 成功返回认证状态
            - status: 状态码 (200)
            - authStatus: 认证状态，可能的值: "success", "failed", null (string, optional)
            - characterName: 角色名称 (string, optional)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "authStatus": "success",
            "characterName": "Character Name"
        }

    Note:
        - 此接口会删除缓存的状态信息，每个状态只能获取一次
        - 如果认证状态不存在或已过期，authStatus 和 characterName 可能为 null
    """
    try:
        user_id = g.current_user["user_id"]
        auth_status = await rdm().redis.hget(
            f"esi_auth_status:user_{user_id}", "authStatus"
        )
        character_name = await rdm().redis.hget(
            f"esi_auth_status:user_{user_id}", "characterName"
        )
        await rdm().redis.delete(f"esi_auth_status:user_{user_id}")
        return {
            "status": 200,
            "authStatus": auth_status,
            "characterName": character_name,
        }
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取认证状态失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取认证状态失败"}), 500
