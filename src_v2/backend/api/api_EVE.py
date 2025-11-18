import datetime, jwt
import traceback

from quart import Quart, request, jsonify, g, Blueprint, redirect
from quart import current_app as app
from src_v2.backend.auth import auth_required, verify_token
from werkzeug.security import check_password_hash, generate_password_hash

from src_v2.core.database.connect_manager import redis_manager
from src_v2.core.user.user_manager import UserManager
from src.service.log_server import logger

from src_v2.model.EVE.eveesi.oauth import get_auth_url, get_token, CALLBACK_LOCAL_HOST
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.utils import KahunaException

# app = Quart(__name__)
# app.config['SECRET_KEY'] = 'your-secret-key-here'
# QuartSchema(app)

api_EVE_bp = Blueprint('api_EVE', __name__, url_prefix='/api/EVE')

@api_EVE_bp.route("/oauth/authorize", methods=["GET"] )
@auth_required
async def get_oauth_url():
    try:
        # 从g.current_user获取用户ID
        user_id = g.current_user["user_id"]
        # 传递user_id到get_auth_url
        url, _ = get_auth_url(user_id=user_id)
        return jsonify({"status": 200, "url": url})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取授权链接失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取授权链接失败"}), 500


@api_EVE_bp.route("/oauth/callback", methods=["GET"])
async def eve_oauth_callback():
    """
    处理 EVE Online OAuth 的回调。
    """
    try:
        # 获取回调参数
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')

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
                state_payload = jwt.decode(state, app.config['SECRET_KEY'], algorithms=['HS256'])
                user_id = state_payload.get('user_id')
                original_oauth_state = state_payload.get('oauth_state')  # 获取原始state
                logger.debug(f"从state解析到用户ID: {user_id}, 原始oauth_state: {original_oauth_state}")
            except jwt.ExpiredSignatureError:
                logger.error("OAuth state已过期")
                return jsonify({"status": 400, "message": "认证链接已过期，请重新开始认证"}), 400
            except jwt.InvalidTokenError as e:
                logger.error(f"OAuth state无效: {e}")
                return jsonify({"status": 400, "message": "无法验证用户身份，请重新开始认证"}), 400
        
        # 如果无法从state获取user_id，记录错误
        if not user_id or not original_oauth_state:
            logger.error("无法从OAuth state中获取用户ID或原始state")
            return jsonify({"status": 400, "message": "无法验证用户身份，请重新开始认证"}), 400

        # 记录接收到的回调信息用于调试
        logger.debug(f"收到EVE OAuth回调 - code: {code[:10]}..., user_id: {user_id}")

        # 获取原始协议，优先从 X-Forwarded-Proto 获取，否则使用当前请求的协议
        scheme = request.headers.get('X-Forwarded-Proto', request.scheme)

        # 获取原始主机名，优先从 X-Forwarded-Host 获取，否则使用当前请求的主机
        host = "bottest.setcr-alero.icu"# request.headers.get('X-Forwarded-Host', request.host)

        # 获取完整的路径和查询参数
        full_path = request.full_path

        # 将URL中的state替换回原始的oauth_state，以便fetch_token验证
        from urllib.parse import urlparse, parse_qs, urlencode
        parsed = urlparse(full_path)
        query_params = parse_qs(parsed.query)
        # 替换state为原始的oauth_state
        query_params['state'] = [original_oauth_state]
        new_query = urlencode(query_params, doseq=True)
        # 重新构建用于fetch_token的URL（需要包含原始state）
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
                    "expires_at": expires_at
                },
                user_id  # 使用从state解析出的user_id
            )
        except KahunaException as e:
            logger.error(f"角色信息入库失败: {str(e)}")
            return jsonify({"status": 500, "message": str(e)}), 500
        except Exception as e:
            logger.error(f"角色信息入库失败: {traceback.format_exc()}")
            return jsonify({"status": 500, "message": "角色信息入库失败"}), 500

        logger.info(f"成功获取 EVE token。用户ID: {user_id}, Access token 过期时间: {expires_at}, 角色名称: {character.character_name}")

        # 设置用户认证缓存状态
        await redis_manager.redis.hset(f"esi_auth_status:user_{user_id}", mapping={"authStatus": "success", "characterName": character.character_name})
        await redis_manager.redis.expire(f"esi_auth_status:user_{user_id}", 300) # 5分钟
        # 完成后，将用户重定向回前端应用程序
        frontend_redirect_url = "https://" + CALLBACK_LOCAL_HOST + "/setting/characterSetting/auth/close" if CALLBACK_LOCAL_HOST else None
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
async def get_auth_status():
    try:
        user_id = g.current_user["user_id"]
        auth_status = await redis_manager.redis.hget(f"esi_auth_status:user_{user_id}", "authStatus")
        character_name = await redis_manager.redis.hget(f"esi_auth_status:user_{user_id}", "characterName")
        await redis_manager.redis.delete(f"esi_auth_status:user_{user_id}")
        return jsonify({"status": 200, "authStatus": auth_status, "characterName": character_name})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取认证状态失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取认证状态失败"}), 500