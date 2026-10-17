# -*- coding: utf-8 -*-
"""refresh token 存储（Redis）

安全设计要点：
- **明文 token 绝不写入 Redis**：Redis 中只保存 ``sha256(raw_token)`` 哈希；
- 每个 token 对应的 key 使用绝对过期时间（7 天，不因使用而续期），轮换时旧 token 立即失效；
- 维护 ``refresh_token:user:{user_id}`` 集合索引（存哈希），用于「注销账号 / 权限变更」时批量撤销；
- Redis 未初始化或出现异常时**降级**：issue 返回 ''，resolve/rotate 返回 None，revoke 静默返回，
  只记一次 warning，绝不向上抛异常（Redis 挂了也要能登录，只是拿不到 refresh token）。
"""

import hashlib
import uuid
from typing import Optional

from src_v2.core.database.connect_manager import get_redis_manager
from src_v2.core.log import logger

# refresh token 绝对过期时间：7 天（不续期）
REFRESH_TOKEN_TTL = 7 * 24 * 3600

# key 前缀（集中在此维护，避免散落在业务层）
_TOKEN_KEY_PREFIX = "refresh_token:"
_USER_INDEX_PREFIX = "refresh_token:user:"


def _hash_token(raw_token: str) -> str:
    """对明文 token 做 sha256，得到落库用的哈希"""
    return hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()


def _token_key(token_hash: str) -> str:
    return f"{_TOKEN_KEY_PREFIX}{token_hash}"


def _user_index_key(user_id: str) -> str:
    return f"{_USER_INDEX_PREFIX}{user_id}"


async def issue_refresh_token(user_id: str) -> str:
    """签发 refresh token

    :param user_id: 用户标识（本项目中即用户名）
    :return: 明文 raw token；Redis 不可用时返回 ''（降级：无 refresh token）
    """
    if not user_id:
        return ''

    raw_token = uuid.uuid4().hex
    token_hash = _hash_token(raw_token)
    try:
        redis = get_redis_manager().redis
        # token -> user_id，绝对过期 7 天
        await redis.setex(_token_key(token_hash), REFRESH_TOKEN_TTL, user_id)
        # 用户索引：该用户名下的所有 token 哈希
        index_key = _user_index_key(user_id)
        await redis.sadd(index_key, token_hash)
        await redis.expire(index_key, REFRESH_TOKEN_TTL)
        return raw_token
    except Exception as e:
        logger.warning(f"签发 refresh token 失败（Redis 不可用，降级为无 refresh token）: {e}")
        return ''


async def resolve_refresh_token(raw_token: str) -> Optional[str]:
    """校验 refresh token 并返回对应用户

    :param raw_token: 客户端持有的明文 token
    :return: user_id；无效或 Redis 异常返回 None
    """
    if not raw_token:
        return None

    try:
        redis = get_redis_manager().redis
        user_id = await redis.get(_token_key(_hash_token(raw_token)))
        return user_id or None
    except Exception as e:
        logger.warning(f"校验 refresh token 失败（Redis 不可用，按无效处理）: {e}")
        return None


async def rotate_refresh_token(raw_token: str) -> Optional[tuple[str, str]]:
    """轮换 refresh token：旧 token 立即失效，返回新的 raw token

    :param raw_token: 旧明文 token
    :return: (user_id, 新 raw token)；失败返回 None
    """
    if not raw_token:
        return None

    old_hash = _hash_token(raw_token)
    try:
        redis = get_redis_manager().redis
        user_id = await redis.get(_token_key(old_hash))
        if not user_id:
            return None

        new_raw_token = uuid.uuid4().hex
        new_hash = _hash_token(new_raw_token)
        # 先写入新 token，保证轮换过程中不掉线
        await redis.setex(_token_key(new_hash), REFRESH_TOKEN_TTL, user_id)
        # 旧 token 立即失效
        await redis.delete(_token_key(old_hash))

        index_key = _user_index_key(user_id)
        await redis.sadd(index_key, new_hash)
        await redis.srem(index_key, old_hash)
        await redis.expire(index_key, REFRESH_TOKEN_TTL)
        return user_id, new_raw_token
    except Exception as e:
        logger.warning(f"轮换 refresh token 失败（Redis 不可用，按无效处理）: {e}")
        return None


async def revoke_refresh_token(raw_token: str) -> None:
    """撤销单个 refresh token（登出、轮换失败清理）

    :param raw_token: 明文 token；Redis 异常时静默返回
    """
    if not raw_token:
        return

    token_hash = _hash_token(raw_token)
    try:
        redis = get_redis_manager().redis
        key = _token_key(token_hash)
        # 先取 user_id 以便同步清理用户索引
        user_id = await redis.get(key)
        await redis.delete(key)
        if user_id:
            await redis.srem(_user_index_key(user_id), token_hash)
    except Exception as e:
        logger.warning(f"撤销 refresh token 失败（Redis 不可用，忽略）: {e}")


async def revoke_all_for_user(user_id: str) -> int:
    """撤销某用户名下全部 refresh token（注销账号 / 权限变更）

    :param user_id: 用户标识
    :return: 实际撤销的 token 数量；Redis 异常返回 0
    """
    if not user_id:
        return 0

    index_key = _user_index_key(user_id)
    try:
        redis = get_redis_manager().redis
        token_hashes = await redis.smembers(index_key)
        count = 0
        if token_hashes:
            keys = [_token_key(h) for h in token_hashes]
            deleted = await redis.delete(*keys)
            count = int(deleted or 0)
        await redis.delete(index_key)
        return count
    except Exception as e:
        logger.warning(f"批量撤销 refresh token 失败（Redis 不可用，忽略）: {e}")
        return 0
