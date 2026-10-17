import time
import traceback
from datetime import datetime

from quart import Blueprint, jsonify, request

from src_v2.backend.auth import auth_required
from src_v2.backend.api.permission_required import role_required
from src_v2.core.database.connect_manager import get_redis_manager
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveAuthedCharacterDBUtils,
    EsiUsageLogDBUtils,
)
from src_v2.core.log import logger
from src_v2.core.utils import get_beijing_utctime
from src_v2.model.EVE.eveesi.esi_req_manager import esi_manager
from src_v2.model.EVE.eveesi.esi_status import check_tq_status
from src_v2.model.EVE.eveesi.eveutils import get_request_async

api_admin_esi_bp = Blueprint('api_admin_esi', __name__, url_prefix='/api/admin/esi')


@api_admin_esi_bp.route('/tq-status', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def get_tq_status():
    """获取 EVE Online TQ 服务器状态"""
    try:
        status = await check_tq_status()
        return jsonify({"status": 200, "data": {"status": status}}), 200
    except Exception:
        logger.exception("获取 TQ 状态失败")
        return jsonify({"status": 200, "data": {"status": "unknown"}}), 200


@api_admin_esi_bp.route('/characters', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def list_characters():
    """
    列出所有 ESI 授权角色及其 token 状态

    支持过滤：
    - user_name: 按用户名模糊匹配 (LIKE %keyword%)
    - status: 按 token 状态过滤 (valid / about_to_expire / expired / unknown)

    Token 状态分类（基于北京时间）：
    - valid:           距离过期 > 5 分钟
    - about_to_expire: 距离过期 ≤ 5 分钟
    - expired:         已过期
    - unknown:         expires_time 为 NULL
    """
    try:
        user_name_filter = request.args.get('user_name', '').strip().lower()
        status_filter = request.args.get('status', '').strip().lower()

        # 从数据库获取所有角色（封装模块内实现）
        characters = await EveAuthedCharacterDBUtils.select_all_characters()

        # Python 端过滤 + 状态分类（便于测试和调试）
        now = get_beijing_utctime(datetime.now()).replace(tzinfo=None)

        records = []
        for char in characters:
            # user_name 模糊过滤
            if user_name_filter:
                owner = (char.owner_user_name or '').lower()
                if user_name_filter not in owner:
                    continue

            # 状态分类
            expires = char.expires_time
            if expires is None:
                status = "unknown"
            else:
                expires_naive = expires.replace(tzinfo=None) if hasattr(expires, 'tzinfo') and expires.tzinfo is not None else expires
                remaining = int((expires_naive - now).total_seconds())
                if remaining <= 0:
                    status = "expired"
                elif remaining <= 300:  # 5 分钟缓冲
                    status = "about_to_expire"
                else:
                    status = "valid"

            # status 过滤
            if status_filter and status != status_filter:
                continue

            records.append({
                "character_id": char.character_id,
                "character_name": char.character_name,
                "owner_user_name": char.owner_user_name,
                "birthday": char.birthday.isoformat() if char.birthday else None,
                "expires_time": char.expires_time.isoformat() if char.expires_time else None,
                "corporation_id": char.corporation_id,
                "director": char.director,
                "token_status": status,
            })

        return jsonify({
            "status": 200,
            "data": records,
            "total": len(records),
        })

    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取 ESI 角色列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取 ESI 角色列表失败"}), 500


@api_admin_esi_bp.route('/characters/<int:character_id>/test', methods=['POST'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def test_character_token(character_id: int):
    """
    测试指定角色的 ESI token

    通过 ESI API 调用 /characters/{character_id}/ 验证 token 有效性。
    每 30 秒冷却（使用 Redis key: esi_test_cooldown:{character_id}）。
    """
    cooldown_key = f"esi_test_cooldown:{character_id}"

    try:
        # 1) 查找角色
        character = await EveAuthedCharacterDBUtils.select_character_by_character_id(
            character_id
        )
        if not character:
            return jsonify({
                "status": 404,
                "message": f"角色 {character_id} 不存在",
            }), 404

        # 2) 检查 Redis 冷却
        redis_client = None
        try:
            rdm = get_redis_manager()
            redis_client = rdm.redis
            cooldown_ttl = await redis_client.ttl(cooldown_key)
            if cooldown_ttl > 0:
                return jsonify({
                    "status": 429,
                    "message": f"冷却中，请 {cooldown_ttl} 秒后再试",
                    "cooldown_remaining": cooldown_ttl,
                }), 429
        except Exception as e:
            logger.warning(f"Redis 冷却检查失败（不影响测试）: {e}")

        # 3) 获取 access_token
        access_token = character.access_token
        if not access_token:
            return jsonify({
                "status": 400,
                "message": "角色没有 access_token，无法测试",
                "success": False,
            }), 400

        # 4) 通过 ESI 管理器获取令牌（遵守速率限制）
        await esi_manager.get_tokens(required_tokens=60)

        # 5) 调用 ESI
        esi_url = f"https://esi.evetech.net/latest/characters/{character_id}/"
        start_time = time.time()
        try:
            data, pages, status_code, rate_limit_info = await get_request_async(
                esi_url,
                headers={"Authorization": f"Bearer {access_token}"},
                log=False,
                no_retry_code=[400, 401, 403, 404],
            )
        except Exception as e:
            latency_ms = round((time.time() - start_time) * 1000, 2)
            return jsonify({
                "status": 500,
                "message": f"ESI 请求异常: {str(e)}",
                "success": False,
                "latency_ms": latency_ms,
                "status_code": None,
                "error": str(e),
            }), 500

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        # 6) 设置 Redis 冷却 (30s)
        if redis_client is not None:
            try:
                await redis_client.setex(cooldown_key, 30, "1")
            except Exception as e:
                logger.warning(f"Redis 冷却设置失败: {e}")

        # 7) 返回结果
        success = status_code == 200
        if success:
            return jsonify({
                "status": 200,
                "message": "Token 有效",
                "data": {
                    "success": True,
                    "latency_ms": elapsed_ms,
                    "status_code": status_code,
                    "error": None,
                    "character_name": data.get("name") if data else None,
                },
            })
        else:
            return jsonify({
                "status": 200,
                "message": f"Token 测试完成（状态码: {status_code}）",
                "data": {
                    "success": False,
                    "latency_ms": elapsed_ms,
                    "status_code": status_code,
                    "error": f"ESI 返回状态码 {status_code}",
                    "character_name": None,
                },
            })

    except Exception as e:
        traceback.print_exc()
        logger.error(f"测试 ESI token 失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": f"测试 ESI token 失败: {str(e)}"}), 500


# ============================================================
# T7: GET /api/admin/esi/buckets — ESI 速率限制桶统计
# ============================================================


@api_admin_esi_bp.route('/buckets', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def get_esi_buckets():
    """获取 ESI 速率限制桶统计与错误计数"""
    try:
        stats = esi_manager.get_pool_stats()
        pools_data = stats.get("pools", {})
        func_mappings = stats.get("func_mappings", {})
        missing_headers = stats.get("missing_headers", [])

        # 构建 pool_name → endpoints 反向映射
        pool_to_endpoints: dict[str, list[str]] = {}
        for func_name, pool_name in func_mappings.items():
            if pool_name not in pool_to_endpoints:
                pool_to_endpoints[pool_name] = []
            pool_to_endpoints[pool_name].append(func_name)

        pools_list = []
        for pool_name, pool_info in pools_data.items():
            pools_list.append({
                "pool_name": pool_name,
                "rate": pool_info.get("rate", 0),
                "max": pool_info.get("max", 0),
                "remaining": pool_info.get("remaining", 0),
                "error_count": pool_info.get("error_count", 0),
                "endpoints": sorted(pool_to_endpoints.get(pool_name, [])),
            })

        return jsonify({
            "status": 200,
            "data": {
                "pools": pools_list,
                "missing_headers": missing_headers,
            },
        }), 200
    except Exception:
        logger.exception("获取 ESI 桶统计失败")
        return jsonify({"status": 500, "message": "获取 ESI 桶统计失败"}), 500


# ============================================================
# T8: GET /api/admin/esi/queue-depth — 请求队列深度
# ============================================================


@api_admin_esi_bp.route('/queue-depth', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def get_esi_queue_depth():
    """获取 ESI 请求队列深度信息"""
    try:
        depth = esi_manager.get_queue_depth()
        return jsonify({
            "status": 200,
            "data": {
                "backlog": depth["backlog"],
                "in_flight": depth["in_flight"],
            },
        }), 200
    except Exception:
        logger.exception("获取 ESI 队列深度失败")
        return jsonify({"status": 500, "message": "获取 ESI 队列深度失败"}), 500


# ============================================================
# T9: GET /api/admin/esi/usage-log — ESI 使用日志（分页）
# ============================================================


@api_admin_esi_bp.route('/usage-log', methods=['GET'])
@auth_required
@role_required(['admin'], 403, '需要管理员权限')
async def get_esi_usage_log():
    """获取 ESI 使用日志，支持分页"""
    try:
        limit = request.args.get('limit', '50')
        offset = request.args.get('offset', '0')

        try:
            limit = int(limit)
            offset = int(offset)
        except (ValueError, TypeError):
            return jsonify({"status": 400, "message": "limit 和 offset 必须是整数"}), 400

        if limit < 1:
            limit = 50
        if offset < 0:
            offset = 0

        items = await EsiUsageLogDBUtils.query_logs(limit=limit, offset=offset)
        total = await EsiUsageLogDBUtils.get_total_count()

        items_data = []
        for item in items:
            items_data.append({
                "id": item.id,
                "timestamp": item.timestamp.isoformat() if item.timestamp else None,
                "endpoint": item.endpoint,
                "pool_name": item.pool_name,
                "character_id": item.character_id,
                "status_code": item.status_code,
                "latency_ms": item.latency_ms,
                "error_message": item.error_message,
            })

        has_more = (offset + len(items)) < total

        return jsonify({
            "status": 200,
            "data": {
                "items": items_data,
                "total": total,
                "has_more": has_more,
            },
        }), 200
    except Exception:
        logger.exception("获取 ESI 使用日志失败")
        return jsonify({"status": 500, "message": "获取 ESI 使用日志失败"}), 500
