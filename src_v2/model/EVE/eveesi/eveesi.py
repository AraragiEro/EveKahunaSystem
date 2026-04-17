import asyncio
from datetime import datetime, timezone

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

# kahuna logger
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException
from .esi_req_manager import esi_request

from .esi_api.character import *
from .esi_api.market import *
from .esi_api.corporation import *
from .esi_api.industry import *
from .esi_api.universe import *
from .esi_api.search import *
from .esi_api.assets import *
from .esi_api.wallet import *

permission_set = set()


async def verify_token(access_token: str, log: bool = True):
    """
    本地解码JWT token获取角色信息

    注意: ESI /verify 端点已于 2026年3月24日移除
    现在使用本地JWT解码获取token中的角色信息

    EVE JWT token 结构:
    {
        "scp": [...],                      # scopes数组
        "jti": "...",                     # JWT ID
        "kid": "...",                     # Key ID
        "sub": "CHARACTER:EVE:123456789", # 角色ID (格式: CHARACTER:EVE:<id>)
        "name": "Character Name",         # 角色名
        "iat": 1234567890,                # 签发时间
        "exp": 1234567890,                # 过期时间
        "iss": "login.eveonline.com",     # 签发者
        "aud": ["EVE Online", "client_id"] # 受众
    }

    Args:
        access_token: OAuth2 access token (JWT格式)
        log: 是否记录日志

    Returns:
        dict: 包含角色信息的字典
        {
            "CharacterID": int,
            "CharacterName": str,
            "ExpiresOn": str (ISO格式),
            "Scopes": str (空格分隔),
            "TokenType": "Character",
            "CharacterOwnerHash": str
        }

    Raises:
        KahunaException: token无效或过期
    """
    try:
        # 本地解码JWT payload（不验证签名，仅获取信息）
        # 签名验证在请求ESI API时由服务器完成
        payload = jwt.decode(
            access_token, options={"verify_signature": False, "verify_exp": True}
        )

        # 解析角色ID (sub格式: "CHARACTER:EVE:<character_id>")
        sub = payload.get("sub", "")
        character_id = None
        if sub.startswith("CHARACTER:EVE:"):
            try:
                character_id = int(sub.split(":")[2])
            except (IndexError, ValueError):
                pass

        if character_id is None:
            raise KahunaException(f"无法从JWT解析角色ID: sub={sub}")

        # 构建与旧ESI /verify端点兼容的返回格式
        result = {
            "CharacterID": character_id,
            "CharacterName": payload.get("name", ""),
            "ExpiresOn": datetime.fromtimestamp(
                payload.get("exp", 0), tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Scopes": " ".join(payload.get("scp", [])),
            "TokenType": "Character",
            "CharacterOwnerHash": payload.get("jti", "")[:28],
        }

        if log:
            logger.info(
                f"成功解析JWT: 角色={result['CharacterName']}, ID={character_id}"
            )

        return result

    except ExpiredSignatureError:
        logger.error("JWT token已过期")
        raise KahunaException("认证令牌已过期，请重新授权")
    except InvalidTokenError as e:
        logger.error(f"无效的JWT token: {e}")
        raise KahunaException("无效的认证令牌")
    except KahunaException:
        raise
    except Exception as e:
        logger.error(f"解析JWT失败: {e}")
        raise KahunaException(f"认证信息解析失败: {e}")
