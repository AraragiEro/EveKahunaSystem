from quart import current_app as app
import jwt
import datetime
import urllib.parse
from urllib.parse import urlparse, parse_qs, urlencode

from requests_oauthlib import OAuth2Session
from src_v2.core.config.config import config

# import logger
from src_v2.core.log import logger

CALLBACK_LOCAL_HOST = config.get("EVE", "CALLBACK_LOCAL_HOST", fallback=None)
# LOCAL_HTTP_ADD = config.get("EVE", "CALLBACK_LOCAL_ADD", fallback=None)
CALL_BACK_API = "/api/EVE/oauth/callback"

PROXY_ADD = config.get("APP", "PROXY", fallback=None)
PROXY_PORT = config.get("APP", "PORT", fallback=None)
if PROXY_ADD and PROXY_PORT:
    PROXY = {
        "http": f"http://{PROXY_ADD}:{PROXY_PORT}",
        "https": f"http://{PROXY_ADD}:{PROXY_PORT}"
    }
else:
    PROXY = None

callback_url = "https://" + CALLBACK_LOCAL_HOST + CALL_BACK_API if CALLBACK_LOCAL_HOST else None

oauth = OAuth2Session(
    client_id=config['EVE']['CLIENT_ID'],
    redirect_uri=callback_url,
    scope=[k for k, v in dict(config['ESI']).items() if v == 'true']
)

def get_auth_url(user_id: str = None):
    """
    生成OAuth认证URL
    :param user_id: 用户ID，将编码到state参数中
    :return: (authorizationUrl, state) 元组
    """
    
    # 生成基础state（OAuth2Session会自动生成）
    authorizationUrl, base_state = oauth.authorization_url('https://login.eveonline.com/v2/oauth/authorize')
    
    # 如果有user_id，将其编码到state中
    if user_id:
        # 创建一个包含user_id的临时token，编码到state
        # 这样可以验证state的有效性，防止篡改
        state_payload = {
            'user_id': user_id,
            'oauth_state': base_state,  # 保留原始state用于验证
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=10)  # 10分钟过期
        }
        encoded_state = jwt.encode(state_payload, app.config['SECRET_KEY'], algorithm='HS256')
        
        # 将编码后的state替换到URL中
        parsed = urlparse(authorizationUrl)
        query_params = parse_qs(parsed.query)
        query_params['state'] = [encoded_state]
        
        new_query = urlencode(query_params, doseq=True)
        authorizationUrl = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"
        
        return authorizationUrl, encoded_state
    
    return authorizationUrl, base_state

def get_token(AUTH_RES):
    try:
        secret_key = config['EVE']['SECRET_KEY']

        # 确保授权响应URL与redirect_uri匹配
        if not AUTH_RES.startswith(oauth.redirect_uri.split('?')[0]):
            logger.warning(f"授权响应URL与redirect_uri不匹配")
            logger.warning(f"Expected prefix: {oauth.redirect_uri.split('?')[0]}")
            logger.warning(f"Actual URL: {AUTH_RES}")

        # 获取token
        token_response = oauth.fetch_token(
            "https://login.eveonline.com/v2/oauth/token",
            authorization_response=AUTH_RES,
            client_secret=secret_key,
            proxies=PROXY
        )

        logger.info(f"成功获取token响应: {token_response}")

        access_token = oauth.token.get("access_token")
        refresh_token = oauth.token.get("refresh_token")
        expires_at = oauth.token.get("expires_at")

        if not access_token:
            logger.error("Token响应中缺少access_token")
            raise ValueError("Token响应中缺少access_token")

        return access_token, refresh_token, expires_at

    except Exception as e:
        logger.error(f"获取token失败: {e}")
        logger.error(f"授权响应URL: {AUTH_RES}")
        raise


def refresh_token(refresh_token):
    client_id = config['EVE']['CLIENT_ID']
    secret_key = config['EVE']['SECRET_KEY']
    newtocker_dict = oauth.refresh_token(
        "https://login.eveonline.com/v2/oauth/token",
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=secret_key , proxies=PROXY
    )

    """
    {
        "access_token",
        "token_type",
        "expires_in", [second]
        "refresh_token",
        "expires_at"
    }
    """
    return newtocker_dict