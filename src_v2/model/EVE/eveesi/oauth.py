from quart import current_app as app
import jwt
import datetime
import time
import urllib.parse
from urllib.parse import urlparse, parse_qs, urlencode

import aiohttp
import asyncio
from requests_oauthlib import OAuth2Session
from src_v2.core.config.config import config
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException

CALLBACK_LOCAL_HOST = config.get("EVE", "CALLBACK_LOCAL_HOST", fallback=None)
CALL_BACK_API = "/api/EVE/oauth/callback"

PROXY_ADD = config.get("APP", "PROXY", fallback=None)
PROXY_PORT = config.get("APP", "PORT", fallback=None)
if PROXY_ADD and PROXY_PORT:
    PROXY = {
        "http": f"http://{PROXY_ADD}:{PROXY_PORT}",
        "https": f"http://{PROXY_ADD}:{PROXY_PORT}",
    }
else:
    PROXY = None

callback_url = (
    "https://" + CALLBACK_LOCAL_HOST + CALL_BACK_API if CALLBACK_LOCAL_HOST else None
)

OAUTH_TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
OAUTH_AUTHORIZE_URL = "https://login.eveonline.com/v2/oauth/authorize"

# OAuth2Session is kept ONLY for get_auth_url() URL generation (no HTTP)
oauth = OAuth2Session(
    client_id=config["EVE"]["CLIENT_ID"],
    redirect_uri=callback_url,
    scope=[k for k, v in dict(config["ESI"]).items() if v == "true"],
)

# Lazy-initialized global lock for serializing OAuth HTTP calls
_oauth_http_lock = None

def _get_oauth_lock():
    global _oauth_http_lock
    if _oauth_http_lock is None:
        _oauth_http_lock = asyncio.Lock()
    return _oauth_http_lock


async def _async_post_oauth_token(data: dict) -> dict:
    """Post to EVE OAuth token endpoint asynchronously with 30s timeout."""
    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    proxy_url = PROXY.get("https") if PROXY else None

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                OAUTH_TOKEN_URL,
                data=data,
                proxy=proxy_url,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise KahunaException(f"OAuth token request failed: HTTP {resp.status}: {body[:200]}")
                result = await resp.json()
                # Compute expires_at if not present in response
                if "expires_at" not in result and "expires_in" in result:
                    result["expires_at"] = int(time.time() + result["expires_in"])
                return result
    except aiohttp.ClientError as e:
        raise KahunaException(f"OAuth token request network error: {e}")


def get_auth_url(user_id: str = None):
    """Generate OAuth authorization URL (no HTTP - kept synchronous)."""
    authorizationUrl, base_state = oauth.authorization_url(OAUTH_AUTHORIZE_URL)

    if user_id:
        state_payload = {
            "user_id": user_id,
            "oauth_state": base_state,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
        }
        encoded_state = jwt.encode(
            state_payload, app.config["SECRET_KEY"], algorithm="HS256"
        )
        parsed = urlparse(authorizationUrl)
        query_params = parse_qs(parsed.query)
        query_params["state"] = [encoded_state]
        new_query = urlencode(query_params, doseq=True)
        authorizationUrl = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"
        oauth._state = encoded_state
        return authorizationUrl, encoded_state

    return authorizationUrl, base_state


async def get_token(AUTH_RES):
    """Async OAuth token grant (replaces sync oauth.fetch_token)."""
    try:
        secret_key = config["EVE"]["SECRET_KEY"]
        client_id = config["EVE"]["CLIENT_ID"]

        if not AUTH_RES.startswith(oauth.redirect_uri.split("?")[0]):
            logger.warning(f"授权响应URL与redirect_uri不匹配")

        parsed = urlparse(AUTH_RES)
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if not code:
            raise KahunaException("授权响应URL中缺少code参数")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": secret_key,
        }

        async with _get_oauth_lock():
            token_response = await _async_post_oauth_token(data)

        logger.info(f"成功获取token响应")

        access_token = token_response.get("access_token")
        refresh_token_val = token_response.get("refresh_token")
        expires_at = token_response.get("expires_at")

        if not access_token:
            logger.error("Token响应中缺少access_token")
            raise ValueError("Token响应中缺少access_token")

        return access_token, refresh_token_val, expires_at

    except KahunaException:
        raise
    except Exception as e:
        logger.error(f"获取token失败: {e}")
        logger.error(f"授权响应URL: {AUTH_RES}")
        raise


async def refresh_token(refresh_token_val):
    """Async ESI token refresh (replaces sync oauth.refresh_token)."""
    client_id = config["EVE"]["CLIENT_ID"]
    secret_key = config["EVE"]["SECRET_KEY"]
    token_suffix = refresh_token_val[-8:] if len(refresh_token_val) > 8 else "unknown"

    try:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token_val,
            "client_id": client_id,
            "client_secret": secret_key,
        }

        async with _get_oauth_lock():
            newtocker_dict = await _async_post_oauth_token(data)

    except KahunaException as e:
        logger.error(f"ESI token refresh failed for token ending with ...{token_suffix}: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"ESI token refresh failed for token ending with ...{token_suffix}", exc_info=True)
        raise

    return newtocker_dict
