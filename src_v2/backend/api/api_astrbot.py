import asyncio
import traceback
from typing import Any, Callable
from uuid import uuid4

from quart import Blueprint, jsonify, request

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.kahuna_database_utils_v2 import UserQQBindingDBUtils
from src_v2.core.log import logger
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.utils.redis_key_utils import build_api_info_token_key, build_qq_bind_key

api_astrbot_bp = Blueprint('api_astrbot', __name__, url_prefix='/api/astrbot')

_ASTRBOT_API_REGISTRY: dict[str, dict[str, Any]] = {}


async def _resolve_vip_state_by_qq(user_qq: int) -> dict[str, Any]:
    binding = await UserQQBindingDBUtils.select_by_user_qq(user_qq)
    if not binding:
        return {"status": 200, "is_bind": False, "message": "QQ 未绑定"}

    vip_state = await permission_manager.get_vip_state(binding.user_name)
    vip_level_name = "Free"
    vip_level_code = None
    vip_end_date = None
    if vip_state and getattr(vip_state, "vip_level", None):
        vip_level_code = vip_state.vip_level
        if vip_level_code == "vip_alpha":
            vip_level_name = "Alpha"
        elif vip_level_code == "vip_omega":
            vip_level_name = "Omega"
        else:
            vip_level_name = "Free"

        if getattr(vip_state, "vip_end_date", None):
            if hasattr(vip_state.vip_end_date, "isoformat"):
                vip_end_date = vip_state.vip_end_date.isoformat()
            else:
                vip_end_date = str(vip_state.vip_end_date)

    return {
        "status": 200,
        "is_bind": True,
        "data": {
            "userName": binding.user_name or "",
            "vipLevel": vip_level_name,
            "vipLevelCode": vip_level_code,
            "vipEndDate": vip_end_date
        }
    }


def astrbot_entry(
    entry_id: str,
    description: str,
    args: Any = None,
    args_example: Any = None,
    res: Any = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if not entry_id:
            raise ValueError("entry_id 不能为空")
        if entry_id in _ASTRBOT_API_REGISTRY:
            raise ValueError(f"entry_id 重复: {entry_id}")
        _ASTRBOT_API_REGISTRY[entry_id] = {
            "entry_id": entry_id,
            "description": description,
            "args": args,
            "args_example": args_example,
            "res_example": res,
            "handler": func,
        }
        return func

    return decorator


def _build_entry_detail(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("entry_id"),
        "description": entry.get("description"),
        "args": entry.get("args"),
        "args_example": entry.get("args_example"),
        "res_example": entry.get("res_example"),
    }


async def _call_astrbot_entry(entry_id: str, args: dict[str, Any]) -> tuple[dict[str, Any], int]:
    entry = _ASTRBOT_API_REGISTRY.get(entry_id)
    if not entry:
        return {"status": 404, "message": f"api_id 不存在: {entry_id}"}, 404

    handler = entry.get("handler")
    if handler is None:
        return {"status": 500, "message": f"api_id 未绑定处理函数: {entry_id}"}, 500

    try:
        result = handler(args)
        if asyncio.iscoroutine(result):
            result = await result
        if isinstance(result, tuple) and len(result) == 2:
            payload, status = result
            return payload, int(status)
        if isinstance(result, dict):
            return result, 200
        return {"status": 500, "message": f"api_id 返回数据格式不正确: {entry_id}"}, 500
    except Exception:
        traceback.print_exc()
        logger.error(
            f"调用 astrbot api 失败: api_id={entry_id}, err={traceback.format_exc()}")
        return {"status": 500, "message": "调用 api 失败"}, 500


# 企业版 astrbot 服务为可选依赖：导入时通过装饰器注册 _astrbot_* 业务处理器。
# 社区版（无 src_v2/enterprise 目录）缺失时跳过注册，/api/astrbot 基础接口照常可用。
try:
    from src_v2.enterprise.api import api_astrbot_service  # noqa: F401
except ImportError:  # 社区版 / 开源版独立运行
    logger.warning("企业版 astrbot 服务不可用（src_v2.enterprise 缺失），仅提供基础 /api/astrbot 接口")
from src_v2.backend.api import response_helper


@api_astrbot_bp.route('/kahunasystem/api/info', methods=['POST'])
async def kahunasystem_api_info():
    data = await request.get_json() or {}
    api_id = data.get("args") or data.get("api_id") or ""
    if not isinstance(api_id, str):
        return response_helper.bad_request("args 需要是 string")
    api_id = api_id.strip()
    if not api_id:
        return response_helper.bad_request("api_id 不能为空")

    entry = _ASTRBOT_API_REGISTRY.get(api_id)
    if not entry:
        return response_helper.not_found(f"未找到 api_id: {api_id}")

    access_token = uuid4().hex
    redis_key = build_api_info_token_key(access_token)
    await rdm().redis.set(redis_key, api_id, ex=300)
    data = _build_entry_detail(entry)
    data["access_token"] = access_token

    return response_helper.ok(data)


@api_astrbot_bp.route('/kahunasystem/api/run', methods=['POST'])
async def run_kahunasystem_api():
    data = await request.get_json() or {}
    api_id = (data.get("api_id") or "").strip()
    args = data.get("args") or {}
    QQ = data.get("QQ") or data.get("qq")
    args["QQ"] = QQ
    args["qq"] = QQ
    if not api_id:
        return response_helper.bad_request("api_id 不能为空")
    if not isinstance(args, dict):
        return response_helper.bad_request("args 需要是 dict")

    access_token = data.get("access_token")
    if not access_token:
        return response_helper.bad_request("请先访问 api info 获取 access_token")
    redis_key = build_api_info_token_key(str(access_token))
    token_api_id = await rdm().redis.get(redis_key)
    if not token_api_id:
        return response_helper.bad_request("access_token 无效或已过期，请先访问 api info 获取")
    if isinstance(token_api_id, bytes):
        token_api_id = token_api_id.decode("utf-8", errors="ignore")
    if token_api_id != api_id:
        return response_helper.bad_request("access_token 与 api_id 不匹配")
    await rdm().redis.delete(redis_key)
    args.pop("access_token", None)

    payload, status = await _call_astrbot_entry(api_id, args)
    return jsonify(payload), status


@api_astrbot_bp.route('/kahunasystem/qq/bind', methods=['POST'])
async def kahunasystem_bind_qq():
    data = await request.get_json() or {}
    qq_value = data.get("QQ") or data.get("qq")
    bind_uuid = (data.get("uuid") or data.get("UUID") or "").strip()
    if not bind_uuid:
        return response_helper.bad_request("uuid 不能为空")

    redis_key = build_qq_bind_key(bind_uuid)
    try:
        if qq_value is None:
            return response_helper.bad_request("QQ 不能为空")

        try:
            user_qq = int(str(qq_value).strip())
        except (TypeError, ValueError):
            return response_helper.bad_request("QQ 必须是数字")

        user_name = await rdm().redis.get(redis_key)
        if not user_name:
            return response_helper.bad_request("绑定指令已过期或无效")

        await UserQQBindingDBUtils.bind_user_qq(user_name=user_name, user_qq=user_qq)
        return response_helper.ok(message="绑定成功", userQQ=user_qq)
    except Exception:
        traceback.print_exc()
        logger.error(f"QQ 绑定失败: {traceback.format_exc()}")
        return response_helper.server_error("绑定失败")
    finally:
        try:
            await rdm().redis.delete(redis_key)
        except Exception as delete_error:
            logger.warning(f"删除 QQ 绑定指令失败: {delete_error}")


@api_astrbot_bp.route('/kahunasystem/qq/vip', methods=['POST'])
async def kahunasystem_qq_vip_state():
    data = await request.get_json() or {}
    qq_value = data.get("QQ") or data.get("qq")
    if qq_value is None:
        return response_helper.bad_request("QQ 不能为空")

    try:
        user_qq = int(str(qq_value).strip())
    except (TypeError, ValueError):
        return response_helper.bad_request("QQ 必须是数字")

    try:
        result = await _resolve_vip_state_by_qq(user_qq)
        return jsonify(result), 200
    except Exception:
        traceback.print_exc()
        logger.error(f"获取 QQ VIP 状态失败: {traceback.format_exc()}")
        return response_helper.server_error("获取 QQ VIP 状态失败")

