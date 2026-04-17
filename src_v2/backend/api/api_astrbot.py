import asyncio
import math
import random
import traceback
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from quart import Blueprint, jsonify, request

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.kahuna_database_utils_v2 import UserQQBindingDBUtils
from src_v2.core.log import logger
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.model.google_API.google_sheet_api import google_sheet_api

api_astrbot_bp = Blueprint('api_astrbot', __name__, url_prefix='/api/astrbot')
CHOUJIANG_SPREADSHEET_ID = "1PBUaQzVJUxHt_MXc1VteQ9RmJUkLlaB2XHcDL75KHW0"

QQ_BIND_REDIS_PREFIX = "kahunasystem:qq_bind"
API_INFO_TOKEN_REDIS_PREFIX = "kahunasystem:api_info_token"

_ASTRBOT_API_REGISTRY: dict[str, dict[str, Any]] = {}


def _build_qq_bind_key(bind_uuid: str) -> str:
    return f"{QQ_BIND_REDIS_PREFIX}:{bind_uuid}"


def _build_api_info_token_key(access_token: str) -> str:
    return f"{API_INFO_TOKEN_REDIS_PREFIX}:{access_token}"


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


def _build_entry_brief(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": entry.get("entry_id"),
        "description": entry.get("description"),
    }


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


from src_v2.enterprise.api import api_astrbot_service  # noqa: F401


@api_astrbot_bp.route('/kahunasystem/api/list', methods=['GET'])
async def list_all_kahunasystem_api():
    data_list = [_build_entry_brief(entry)
                 for entry in _ASTRBOT_API_REGISTRY.values()]
    return jsonify({"status": 200, "data": data_list})


@api_astrbot_bp.route('/kahunasystem/api/info', methods=['POST'])
async def kahunasystem_api_info():
    data = await request.get_json() or {}
    api_id = data.get("args") or data.get("api_id") or ""
    if not isinstance(api_id, str):
        return jsonify({"status": 400, "message": "args 需要是 string"}), 400
    api_id = api_id.strip()
    if not api_id:
        return jsonify({"status": 400, "message": "api_id 不能为空"}), 400

    entry = _ASTRBOT_API_REGISTRY.get(api_id)
    if not entry:
        return jsonify({"status": 404, "message": f"未找到 api_id: {api_id}"}), 404

    access_token = uuid4().hex
    redis_key = _build_api_info_token_key(access_token)
    await rdm().redis.set(redis_key, api_id, ex=300)
    data = _build_entry_detail(entry)
    data["access_token"] = access_token

    return jsonify({"status": 200, "data": data})


@api_astrbot_bp.route('/kahunasystem/api/run', methods=['POST'])
async def run_kahunasystem_api():
    data = await request.get_json() or {}
    api_id = (data.get("api_id") or "").strip()
    args = data.get("args") or {}
    QQ = data.get("QQ") or data.get("qq")
    args["QQ"] = QQ
    args["qq"] = QQ
    if not api_id:
        return jsonify({"status": 400, "message": "api_id 不能为空"}), 400
    if not isinstance(args, dict):
        return jsonify({"status": 400, "message": "args 需要是 dict"}), 400

    access_token = data.get("access_token")
    if not access_token:
        return jsonify({"status": 400, "message": "请先访问 api info 获取 access_token"}), 400
    redis_key = _build_api_info_token_key(str(access_token))
    token_api_id = await rdm().redis.get(redis_key)
    if not token_api_id:
        return jsonify({"status": 400, "message": "access_token 无效或已过期，请先访问 api info 获取"}), 400
    if isinstance(token_api_id, bytes):
        token_api_id = token_api_id.decode("utf-8", errors="ignore")
    if token_api_id != api_id:
        return jsonify({"status": 400, "message": "access_token 与 api_id 不匹配"}), 400
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
        return jsonify({"status": 400, "message": "uuid 不能为空"}), 400

    redis_key = _build_qq_bind_key(bind_uuid)
    try:
        if qq_value is None:
            return jsonify({"status": 400, "message": "QQ 不能为空"}), 400

        try:
            user_qq = int(str(qq_value).strip())
        except (TypeError, ValueError):
            return jsonify({"status": 400, "message": "QQ 必须是数字"}), 400

        user_name = await rdm().redis.get(redis_key)
        if not user_name:
            return jsonify({"status": 400, "message": "绑定指令已过期或无效"}), 400

        await UserQQBindingDBUtils.bind_user_qq(user_name=user_name, user_qq=user_qq)
        return jsonify({"status": 200, "message": "绑定成功", "userQQ": user_qq}), 200
    except Exception:
        traceback.print_exc()
        logger.error(f"QQ 绑定失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "绑定失败"}), 500
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
        return jsonify({"status": 400, "message": "QQ 不能为空"}), 400

    try:
        user_qq = int(str(qq_value).strip())
    except (TypeError, ValueError):
        return jsonify({"status": 400, "message": "QQ 必须是数字"}), 400

    try:
        result = await _resolve_vip_state_by_qq(user_qq)
        return jsonify(result), 200
    except Exception:
        traceback.print_exc()
        logger.error(f"获取 QQ VIP 状态失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取 QQ VIP 状态失败"}), 500


# -------------------------------------------------------------
# 抽奖相关API
# -------------------------------------------------------------
from aiocache import cached
from aiocache.serializers import PickleSerializer
@cached(ttl=3600, serializer=PickleSerializer())
async def kahunasystem_choujiang_IDlist():
    try:
        resp = google_sheet_api.execute_with_retry(
            lambda service: service.spreadsheets().values().get(
                spreadsheetId=CHOUJIANG_SPREADSHEET_ID,
                range="'抽奖数据库'!A2:A28",
            ),
            retries=2,
            retry_interval=0.8,
        )

        value = resp.get("values", [])
        res = {
            name[0]: index + 2 for index, name in enumerate(value)
        }   
        
        return res
    except Exception:
        traceback.print_exc()
        logger.error(f"获取公司医疗抵扣额度失败: {traceback.format_exc()}, value: {value}")
        return []

async def kahunasystem_choujiang_get_id_by_name(name: str):
    IDlist = await kahunasystem_choujiang_IDlist()
    if name not in IDlist:
        raise ValueError(f"name 不存在: {name}, IDlist: {IDlist}")
    
    return IDlist[name]

async def kahunasystem_choujiang_get_remain_paps():
    try:
        resp = google_sheet_api.execute_with_retry(
            lambda service: service.spreadsheets().values().get(
                spreadsheetId=CHOUJIANG_SPREADSHEET_ID,
                range=f"'抽奖数据库'!C2:C28",
            ),
            retries=2,
            retry_interval=0.8,
        )

        value = resp.get("values", [[0]])
        paps = [int(value[index][0]) if value[index] else 0 for index in range(len(value))]
        
        return paps
    except Exception:
        traceback.print_exc()
        logger.error(f"获取剩余pap失败: {traceback.format_exc()}, ")
        return []

async def kahunasystem_choujiang_get_pity_counts(expected_count: int):
    try:
        if expected_count <= 0:
            return []
        end_row = 30 + expected_count
        resp = google_sheet_api.execute_with_retry(
            lambda service: service.spreadsheets().values().get(
                spreadsheetId=CHOUJIANG_SPREADSHEET_ID,
                range=f"'抽奖数据库'!A31:A{end_row}",
            ),
            retries=2,
            retry_interval=0.8,
        )
        values = resp.get("values", [])
        res = []
        for i in range(expected_count):
            row = values[i] if i < len(values) else []
            cell = row[0] if row else 0
            try:
                res.append(int(cell))
            except Exception:
                res.append(0)
        return res
    except Exception:
        traceback.print_exc()
        logger.error(f"获取保底计数失败: {traceback.format_exc()}")
        return [0] * max(0, int(expected_count))

async def kahunasystem_choujiang_get_round_used_paps(round_id: int, expected_count: int):
    try:
        if expected_count <= 0:
            return []
        if round_id <= 0:
            round_id = 1
        # 轮次列与 save_state 保持一致：round1 -> D 列（A/B/C 预留给基础数据）。
        col = _number_to_column(int(round_id) + 3)
        end_row = 1 + expected_count
        resp = google_sheet_api.execute_with_retry(
            lambda service: service.spreadsheets().values().get(
                spreadsheetId=CHOUJIANG_SPREADSHEET_ID,
                range=f"'抽奖数据库'!{col}2:{col}{end_row}",
            ),
            retries=2,
            retry_interval=0.8,
        )
        values = resp.get("values", [])
        res = []
        for i in range(expected_count):
            row = values[i] if i < len(values) else []
            cell = row[0] if row else 0
            try:
                res.append(int(cell))
            except Exception:
                res.append(0)
        return res
    except Exception:
        traceback.print_exc()
        logger.error(f"获取轮次已用pap失败: {traceback.format_exc()}")
        return [0] * max(0, int(expected_count))

def _number_to_column(col_num: int) -> str:
    if col_num <= 0:
        raise ValueError(f"列号必须大于0: {col_num}")
    chars = []
    n = col_num
    while n > 0:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(ord('A') + rem))
    return "".join(reversed(chars))


def _round_block_range(sheet_name: str, round_id: int, start_row: int, row_count: int, block_width: int) -> str:
    if round_id <= 0:
        raise ValueError(f"round_id 必须大于0: {round_id}")
    if start_row <= 0:
        raise ValueError(f"start_row 必须大于0: {start_row}")
    if row_count <= 0:
        raise ValueError(f"row_count 必须大于0: {row_count}")
    if block_width <= 0:
        raise ValueError(f"block_width 必须大于0: {block_width}")
    start_col_num = (round_id - 1) * block_width + 1
    end_col_num = start_col_num + block_width - 1
    start_col = _number_to_column(start_col_num)
    end_col = _number_to_column(end_col_num)
    end_row = start_row + row_count - 1
    return f"'{sheet_name}'!{start_col}{start_row}:{end_col}{end_row}"


def _parse_reward_line(reward_line: str) -> tuple[str, str, int]:
    parts = [p.strip() for p in reward_line.split(":")]
    if len(parts) < 3:
        raise ValueError(f"奖品格式错误: {reward_line}")
    rarity = parts[0]
    reward_name = ":".join(parts[1:-1]).strip()
    count_raw = parts[-1]
    count = int(count_raw)
    if not reward_name:
        raise ValueError(f"奖品名称不能为空: {reward_line}")
    if count <= 0:
        raise ValueError(f"奖品数量必须大于0: {reward_line}")
    return rarity, reward_name, count


def _weighted_pick(participants: list[dict[str, Any]]) -> tuple[dict[str, Any], float, float]:
    total_weight = sum(float(p["weight"]) for p in participants)
    if total_weight <= 0:
        raise ValueError("参与者总权重必须大于0")
    roll = random.random() * total_weight
    curr = 0.0
    for p in participants:
        curr += float(p["weight"])
        if roll <= curr:
            return p, roll, total_weight
    return participants[-1], roll, total_weight


def _ssr_probability_by_pity(pity_count: int) -> float:
    draw_idx = pity_count + 1
    soft_start = int(CHOUJIANG_RUN_SSR_SOFT_PITY_START)
    guarantee_draw = int(CHOUJIANG_RUN_SSR_GUARANTEE_DRAW)
    base_prob = float(CHOUJIANG_RUN_SSR_BASE_PROB)
    soft_max_prob = float(CHOUJIANG_RUN_SSR_SOFT_PITY_MAX_PROB)
    soft_end = guarantee_draw - 1
    if draw_idx <= soft_start:
        return base_prob
    if draw_idx <= soft_end:
        # 软保底区间线性提升
        span = max(1, soft_end - soft_start)
        return base_prob + (draw_idx - soft_start) * (soft_max_prob - base_prob) / span
    return 1.0


def _allocate_draw_counts_by_sqrt(used_map: dict[str, int], total_draws: int = 160) -> dict[str, int]:
    if total_draws <= 0:
        raise ValueError(f"total_draws 必须大于0: {total_draws}")
    effects = {name: math.sqrt(max(0, int(v))) for name, v in used_map.items()}
    total_effect = sum(effects.values())
    if total_effect <= 0:
        return {name: 0 for name in used_map.keys()}

    raw = {name: total_draws * effects[name] / total_effect for name in used_map.keys()}
    base = {name: int(math.floor(raw[name])) for name in used_map.keys()}
    remain = total_draws - sum(base.values())
    frac_order = sorted(
        used_map.keys(),
        key=lambda n: (raw[n] - base[n], effects[n], used_map[n], n),
        reverse=True,
    )
    for i in range(remain):
        base[frac_order[i]] += 1
    return base


def _pick_reward_from_inventory(
    reward_inventory: list[dict[str, Any]],
    empty_multiplier: int | None = None,
    reward_hit_coefficient: float = 1.0,
    force_reward: bool = False,
) -> dict[str, Any] | None:
    available = [x for x in reward_inventory if int(x["remaining"]) > 0]
    if not available:
        return None
    if empty_multiplier is None:
        empty_multiplier = int(CHOUJIANG_RUN_NORMAL_EMPTY_MULTIPLIER)
    reward_hit_coefficient = max(0.01, float(reward_hit_coefficient))
    total_left = sum(int(x["remaining"]) for x in available)
    empty_slots = 0
    if not force_reward:
        # 中奖系数越大，空结果权重越小，普通奖品整体中奖率越高。
        effective_empty_multiplier = max(0.0, float(empty_multiplier)) / reward_hit_coefficient
        empty_slots = int(total_left * effective_empty_multiplier)
        roll = random.randint(1, total_left + empty_slots)
        if roll <= empty_slots:
            return {
                "rarity": "EMPTY",
                "reward_name": "未中奖",
            }
        roll -= empty_slots
    else:
        roll = random.randint(1, total_left)
    curr = 0
    for item in available:
        curr += int(item["remaining"])
        if roll <= curr:
            item["remaining"] -= 1
            return {
                "rarity": item["rarity"],
                "reward_name": item["reward_name"],
            }
    return None


def _compute_ssr_final_probabilities(weight_map: dict[str, int]) -> dict[str, float]:
    clean = {k: int(v) for k, v in weight_map.items() if int(v) > 0}
    if not clean:
        return {}
    if len(clean) == 1:
        only = next(iter(clean.keys()))
        return {only: 1.0}

    total_w = sum(clean.values())
    top_name = max(clean.keys(), key=lambda n: clean[n])
    top_w = clean[top_name]
    top_share = top_w / total_w if total_w > 0 else 0.0

    if top_share <= 0.5:
        return {name: w / total_w for name, w in clean.items()}

    rest = {k: v for k, v in clean.items() if k != top_name}
    rest_prob = _compute_ssr_final_probabilities(rest)
    final_prob = {name: 0.0 for name in clean.keys()}
    final_prob[top_name] = 0.5
    for name, p in rest_prob.items():
        final_prob[name] = 0.5 * p
    return final_prob


def _run_ssr_owner_draw(weight_map: dict[str, int]) -> tuple[str | None, list[dict[str, Any]]]:
    logs: list[dict[str, Any]] = []
    current = {k: int(v) for k, v in weight_map.items() if int(v) > 0}
    if not current:
        logs.append({"step": "empty", "message": "无SSR权重，无法抽取归属"})
        return None, logs

    while True:
        if len(current) == 1:
            winner = next(iter(current.keys()))
            logs.append({
                "step": "single_left",
                "remaining": current,
                "winner": winner,
            })
            return winner, logs

        total_w = sum(current.values())
        top_name = max(current.keys(), key=lambda n: current[n])
        top_w = current[top_name]
        top_share = top_w / total_w if total_w > 0 else 0.0
        logs.append({
            "step": "round_check",
            "remaining": current.copy(),
            "total_weight": total_w,
            "top_name": top_name,
            "top_weight": top_w,
            "top_share": round(top_share, 8),
        })

        if top_share <= 0.5:
            candidates = [{"name": name, "weight": w} for name, w in current.items()]
            picked, roll, weight_sum = _weighted_pick(candidates)
            winner = picked["name"]
            logs.append({
                "step": "weighted_pick",
                "roll": round(float(roll), 8),
                "weight_sum": round(float(weight_sum), 8),
                "winner": winner,
                "remaining": current.copy(),
            })
            return winner, logs

        coin = random.random()
        coin_hit = coin < 0.5
        logs.append({
            "step": "top_5050",
            "top_name": top_name,
            "coin": round(float(coin), 8),
            "hit": coin_hit,
        })
        if coin_hit:
            logs.append({
                "step": "top_win",
                "winner": top_name,
            })
            return top_name, logs

        current.pop(top_name, None)
        logs.append({
            "step": "top_removed_by_miss",
            "removed": top_name,
            "remaining": current.copy(),
        })


async def kahunasystem_choujiang_get_this_round_reward(round_id: int | None = None):
    use_round_id = int(round_id or 1)
    row = _number_to_column(use_round_id)
    resp = google_sheet_api.execute_with_retry(
        lambda service: service.spreadsheets().values().get(
            spreadsheetId=CHOUJIANG_SPREADSHEET_ID,
            range=f"'奖品'!{row}2:{row}100",
        ),
        retries=2,
        retry_interval=0.8,
    )
    value = resp.get("values", [])
    res = [p[0].strip() for p in value if p and str(p[0]).strip() != ""]
    
    return res

class ChoujiangState:
    def __init__(self):
        self.active_id = 0
        self.active = False

        self.IDs = {}
        self.remain_paps = []
        self.this_round_used_paps = []
        self.user_pity_count_by_name: dict[str, int] = {}
        self.user_pity_count_by_name_tmp: dict[str, int] = {}

        self.this_round_log = []
        self.tmp_result = {}

    async def load_IDs(self):
        self.IDs = await kahunasystem_choujiang_IDlist()
        # 保底计数按用户名长期维护；仅在新用户出现时补默认值，不主动清空既有数据。
        for name in self.IDs.keys():
            self.user_pity_count_by_name.setdefault(name, 0)
            self.user_pity_count_by_name_tmp.setdefault(name, 0)
        # 加载保底计数快照（按ID顺序写入）。
        sorted_names = [name for name, _user_id in sorted(self.IDs.items(), key=lambda x: x[1])]
        pity_values = await kahunasystem_choujiang_get_pity_counts(len(sorted_names))
        for idx, name in enumerate(sorted_names):
            pity_val = int(pity_values[idx]) if idx < len(pity_values) else 0
            self.user_pity_count_by_name[name] = pity_val
            self.user_pity_count_by_name_tmp[name] = pity_val
        # 预加载当前轮次在线已用pap，避免本地状态与线上脱节。
        load_round_id = int(self.active_id or 1)
        self.this_round_used_paps = await kahunasystem_choujiang_get_round_used_paps(load_round_id, len(self.IDs))

    async def set_round(self, round_id: int):
        self.active_id = round_id
        
        self.remain_paps = await kahunasystem_choujiang_get_remain_paps()
        self.this_round_used_paps = await kahunasystem_choujiang_get_round_used_paps(
            int(round_id),
            len(self.remain_paps),
        )

    async def next_round(self):
        await self.set_round(self.active_id + 1)

    async def set_user_paps_used(self, user_name: str, paps: int):
        user_id = self.IDs.get(user_name)
        if user_id is None:
            raise ValueError(f"user_name 不存在: {user_name}, IDs: {self.IDs}")
        
        if paps > self.remain_paps[user_id - 2]:
            raise ValueError(f"paps 超出剩余pap: {paps}, 剩余pap: {self.remain_paps[user_id - 2]}")

        self.this_round_used_paps[user_id - 2] = paps
        
        return {
            "remain_paps": self.remain_paps[user_id - 2],
            "this_round_used_paps": self.this_round_used_paps[user_id - 2],
        }

@api_astrbot_bp.route('/kahunasystem/choujiang/set_active', methods=['POST'])
async def kahunasystem_choujiang_set_active():
    try:
        data = await request.get_json() or {}
        active = data.get("active") or False
        choujiang_state.active = active
        return jsonify({"status": 200, "data": {
            "active": choujiang_state.active,
        }}), 200
    except Exception:
        traceback.print_exc()
        logger.error(f"设置抽奖状态失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "设置抽奖状态失败"}), 500

choujiang_state = ChoujiangState()
@api_astrbot_bp.route('/kahunasystem/choujiang/init', methods=['POST'])
async def kahunasystem_choujiang_init():
    try:
        global choujiang_state
        choujiang_state = ChoujiangState()
        await choujiang_state.load_IDs()
        choujiang_state.active = False
        await choujiang_state.set_round(1)
        data = {
            name: choujiang_state.remain_paps[choujiang_state.IDs[name] - 2] for name in choujiang_state.IDs.keys()
        }
        pity_data = {
            name: int(choujiang_state.user_pity_count_by_name.get(name, 0))
            for name in choujiang_state.IDs.keys()
        }
        return jsonify({"status": 200, "data": data, "pity_count_by_name": pity_data}), 200
    except Exception:
        traceback.print_exc()
        logger.error(f"初始化抽奖失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "初始化失败"}), 500

@api_astrbot_bp.route('/kahunasystem/choujiang/set_user_paps_used', methods=['POST'])
async def kahunasystem_choujiang_set_user_paps_used():
    try:
        if not choujiang_state.active:
            return jsonify({"status": 400, "message": "抽奖未激活"}), 400
        data = await request.get_json() or {}
        name = data.get("name") or data.get("userName") or ""
        paps = int(data.get("paps") or 0)
        if not name:
            return jsonify({"status": 400, "message": "name 不能为空"}), 400
        if paps <= 0:
            return jsonify({"status": 400, "message": "paps 必须大于0"}), 400
        await choujiang_state.set_user_paps_used(name, paps)
        return jsonify({"status": 200, "data": {
            "remain_paps": choujiang_state.remain_paps[choujiang_state.IDs[name] - 2] - paps,
            "this_round_used_paps": choujiang_state.this_round_used_paps[choujiang_state.IDs[name] - 2],
        }}), 200
    except Exception as e:
        traceback.print_exc()
        logger.error(f"设置用户pap使用失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": f"设置用户pap使用失败, {e}"}), 500

@api_astrbot_bp.route('/kahunasystem/choujiang/set_round', methods=['POST'])
async def kahunasystem_choujiang_set_round():
    try:
        data = await request.get_json() or {}
        round_id = int(data.get("round_id") or 1)
        await choujiang_state.set_round(round_id)
        return jsonify({"status": 200, "data": {
            "round_id": round_id,
        }}), 200
    except Exception:
        traceback.print_exc()
        logger.error(f"设置轮次失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "设置轮次失败"}), 500

@api_astrbot_bp.route('/kahunasystem/choujiang/next_round', methods=['POST'])
async def kahunasystem_choujiang_next_round():
    try:
        await choujiang_state.next_round()
        data = {
            name: choujiang_state.remain_paps[choujiang_state.IDs[name] - 2] for name in choujiang_state.IDs.keys()
        }
        return jsonify({"status": 200, "data": {
            "remain_paps": choujiang_state.remain_paps,
            "this_round_used_paps": choujiang_state.this_round_used_paps,
        }}), 200
    except Exception:
        traceback.print_exc()
        logger.error(f"切换轮次失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "切换轮次失败"}), 500

# kahunasystem_choujiang_run 全局配置参数（便于测试与调参）
CHOUJIANG_RUN_TOTAL_DRAWS = 160
CHOUJIANG_RUN_BASE_REWARD_PER_PAP = 7_000_000
CHOUJIANG_RUN_SSR_BASE_PROB = 0.005
CHOUJIANG_RUN_SSR_SOFT_PITY_START = 70
CHOUJIANG_RUN_SSR_GUARANTEE_DRAW = 80
CHOUJIANG_RUN_SSR_SOFT_PITY_MAX_PROB = 1.0
CHOUJIANG_RUN_NORMAL_EMPTY_MULTIPLIER = 3
CHOUJIANG_RUN_NORMAL_REWARD_HIT_COEFFICIENT = 1.0

@api_astrbot_bp.route('/kahunasystem/choujiang/run', methods=['POST'])
async def kahunasystem_choujiang_run():
    try:
        round_id = int(choujiang_state.active_id or 1)
        rewards_raw = await kahunasystem_choujiang_get_this_round_reward(round_id)
        participants = []
        for name, user_id in sorted(choujiang_state.IDs.items(), key=lambda x: x[1]):
            idx = int(user_id) - 2
            if idx < 0 or idx >= len(choujiang_state.this_round_used_paps):
                continue
            used = int(choujiang_state.this_round_used_paps[idx] or 0)
            participants.append({
                "name": name,
                "id": int(user_id),
                "used_paps": used,
                "base_reward_isk": used * CHOUJIANG_RUN_BASE_REWARD_PER_PAP,
            })
        active_participants = [p for p in participants if p["used_paps"] > 0]
        if not active_participants:
            return jsonify({"status": 400, "message": "本轮没有投入资源的参与者"}), 400

        used_map = {p["name"]: int(p["used_paps"]) for p in active_participants}
        draw_count_map = _allocate_draw_counts_by_sqrt(used_map, total_draws=CHOUJIANG_RUN_TOTAL_DRAWS)
        total_draw_count = sum(draw_count_map.values())
        # 每次run开始均从正式保底快照拷贝，确保未save_state时重复run条件一致。
        choujiang_state.user_pity_count_by_name_tmp = {
            name: int(choujiang_state.user_pity_count_by_name.get(name, 0))
            for name in choujiang_state.IDs.keys()
        }

        normal_reward_inventory = []
        ssr_reward_inventory = []
        for reward_line in rewards_raw:
            rarity, reward_name, count = _parse_reward_line(reward_line)
            item = {
                "rarity": rarity,
                "reward_name": reward_name,
                "initial": count,
                "remaining": count,
            }
            if rarity.upper() == "SSR":
                ssr_reward_inventory.append(item)
            else:
                normal_reward_inventory.append(item)
        normal_reward_initial_total = sum(int(item["initial"]) for item in normal_reward_inventory)
        # 低保上限按普通奖品总量自动计算：约每 N 抽至少出一次普通奖品。
        normal_reward_low_guarantee_limit = (
            max(1, int(math.floor(total_draw_count / normal_reward_initial_total)))
            if normal_reward_initial_total > 0 else None
        ) - 1

        id_by_name = {p["name"]: p["id"] for p in participants}
        pity_count = {
            p["name"]: int(choujiang_state.user_pity_count_by_name_tmp.get(p["name"], 0))
            for p in active_participants
        }
        ssr_weight = {p["name"]: 0 for p in active_participants}
        user_rewards: dict[str, dict[str, dict[str, Any]]] = {}
        draw_settlement_logs = []
        draw_queue: list[str] = []
        for p in active_participants:
            draw_queue.extend([p["name"]] * int(draw_count_map.get(p["name"], 0)))
        random.shuffle(draw_queue)
        user_draw_no_map = {p["name"]: 0 for p in active_participants}
        normal_reward_low_guarantee_counter = 0
        draw_no = 0
        for name in draw_queue:
            draw_no += 1
            user_draw_no_map[name] += 1
            user_draw_no = int(user_draw_no_map[name])
            cur_pity = int(pity_count[name])
            ssr_prob = _ssr_probability_by_pity(cur_pity)
            roll = random.random()
            is_ssr = roll < ssr_prob
            # 第160抽固定给一个SSR权重。
            force_160th_ssr_weight = (draw_no == 160)
            if force_160th_ssr_weight:
                is_ssr = True
            # 轮次收尾保障：若剩余抽次不足以覆盖剩余普通奖品，则当前抽强制走普通奖品分发逻辑。
            remaining_normal_rewards = sum(int(item["remaining"]) for item in normal_reward_inventory)
            remaining_draws_including_current = total_draw_count - draw_no + 1
            force_normal_reward_by_exhaust = (
                remaining_normal_rewards > 0 and remaining_normal_rewards >= remaining_draws_including_current
            )
            if force_normal_reward_by_exhaust and not force_160th_ssr_weight:
                is_ssr = False

            log_item: dict[str, Any] = {
                "round_id": round_id,
                "draw_no": draw_no,
                "user_draw_no": user_draw_no,
                "name": name,
                "user_id": id_by_name[name],
                "pity_before": cur_pity,
                "ssr_prob": round(float(ssr_prob), 8),
                "roll": round(float(roll), 8),
                "normal_reward_low_guarantee_limit": normal_reward_low_guarantee_limit,
                "normal_reward_low_guarantee_counter_before": normal_reward_low_guarantee_counter,
            }
            if force_160th_ssr_weight:
                log_item["ssr_forced"] = True
            if force_normal_reward_by_exhaust:
                log_item["normal_reward_forced"] = "exhaust"

            if is_ssr:
                ssr_weight[name] += 1
                pity_count[name] = 0
                log_item.update({
                    "result_type": "SSR_WEIGHT",
                    "reward_name": "SSR权重+1",
                    "ssr_weight_after": ssr_weight[name],
                    "pity_after": 0,
                })
                if force_160th_ssr_weight:
                    log_item["reward_name"] = "SSR权重+1(第160抽保底)"
            else:
                pity_count[name] = min(79, cur_pity + 1)
                if remaining_normal_rewards > 0 and normal_reward_low_guarantee_counter < 0:
                    normal_reward_low_guarantee_counter += 1
                    log_item["normal_reward_blocked"] = "counter_negative"
                    log_item.update({
                        "result_type": "EMPTY",
                        "reward_name": "未中奖",
                        "pity_after": pity_count[name],
                    })
                    log_item["normal_reward_low_guarantee_counter_after"] = normal_reward_low_guarantee_counter
                    draw_settlement_logs.append(log_item)
                    continue
                force_normal_reward_by_low_guarantee = (
                    remaining_normal_rewards > 0 and
                    normal_reward_low_guarantee_limit is not None and
                    normal_reward_low_guarantee_counter >= normal_reward_low_guarantee_limit
                )
                if force_normal_reward_by_low_guarantee:
                    log_item["normal_reward_forced"] = "low_guarantee"
                reward_picked = _pick_reward_from_inventory(
                    normal_reward_inventory,
                    reward_hit_coefficient=CHOUJIANG_RUN_NORMAL_REWARD_HIT_COEFFICIENT,
                    force_reward=(force_normal_reward_by_exhaust or force_normal_reward_by_low_guarantee),
                )
                if reward_picked is not None:
                    rarity = reward_picked["rarity"]
                    reward_name = reward_picked["reward_name"]
                    if rarity == "EMPTY":
                        normal_reward_low_guarantee_counter += 1
                        log_item.update({
                            "result_type": "EMPTY",
                            "reward_name": reward_name,
                            "pity_after": pity_count[name],
                        })
                    else:
                        if normal_reward_low_guarantee_limit is not None:
                            # 未到上限就提前出奖时，计数器扣减上限；允许进入负值。
                            normal_reward_low_guarantee_counter -= normal_reward_low_guarantee_limit
                        reward_key = f"{rarity}:{reward_name}"
                        if name not in user_rewards:
                            user_rewards[name] = {}
                        if reward_key not in user_rewards[name]:
                            user_rewards[name][reward_key] = {
                                "rarity": rarity,
                                "reward_name": reward_name,
                                "count": 0,
                            }
                        user_rewards[name][reward_key]["count"] += 1
                        log_item.update({
                            "result_type": "REWARD",
                            "rarity": rarity,
                            "reward_name": reward_name,
                            "pity_after": pity_count[name],
                        })
                else:
                    normal_reward_low_guarantee_counter += 1
                    log_item.update({
                        "result_type": "EMPTY",
                        "reward_name": "奖品库存已空",
                        "pity_after": pity_count[name],
                    })
            log_item["normal_reward_low_guarantee_counter_after"] = normal_reward_low_guarantee_counter

            draw_settlement_logs.append(log_item)

        for name, value in pity_count.items():
            choujiang_state.user_pity_count_by_name_tmp[name] = int(value)

        ssr_final_prob = _compute_ssr_final_probabilities(ssr_weight)
        ssr_owner_name, ssr_calculation_logs = _run_ssr_owner_draw(ssr_weight)
        ssr_owner = None
        ssr_award_logs = []
        if ssr_owner_name is not None:
            ssr_owner = {
                "winner": ssr_owner_name,
                "user_id": id_by_name.get(ssr_owner_name),
                "ssr_weight": int(ssr_weight.get(ssr_owner_name, 0)),
            }
            # SSR条目仅在SSR归属阶段发放：归属者一次性领取本轮SSR池库存
            for item in ssr_reward_inventory:
                grant_count = int(item["remaining"])
                if grant_count <= 0:
                    continue
                item["remaining"] = 0
                reward_key = f"{item['rarity']}:{item['reward_name']}"
                if ssr_owner_name not in user_rewards:
                    user_rewards[ssr_owner_name] = {}
                if reward_key not in user_rewards[ssr_owner_name]:
                    user_rewards[ssr_owner_name][reward_key] = {
                        "rarity": item["rarity"],
                        "reward_name": item["reward_name"],
                        "count": 0,
                    }
                user_rewards[ssr_owner_name][reward_key]["count"] += grant_count
                ssr_award_logs.append({
                    "owner": ssr_owner_name,
                    "rarity": item["rarity"],
                    "reward_name": item["reward_name"],
                    "count": grant_count,
                })

        rewards_by_user = []
        participants_invest_and_prob = []
        ssr_weight_and_prob = []
        for p in participants:
            name = p["name"]
            rewards = sorted(user_rewards.get(name, {}).values(), key=lambda x: (x["rarity"], x["reward_name"]))
            rewards_by_user.append({
                "name": name,
                "user_id": p["id"],
                "rewards": rewards,
                "total_reward_count": sum(int(item["count"]) for item in rewards),
            })
            if name in used_map:
                participants_invest_and_prob.append({
                    "name": name,
                    "user_id": p["id"],
                    "used_paps": p["used_paps"],
                    "base_reward_isk": p["base_reward_isk"],
                    "draw_count": int(draw_count_map.get(name, 0)),
                    "draw_ratio": round(float(draw_count_map.get(name, 0)) / CHOUJIANG_RUN_TOTAL_DRAWS, 8),
                    "ssr_weight": int(ssr_weight.get(name, 0)),
                    "ssr_final_prob": round(float(ssr_final_prob.get(name, 0.0)), 8),
                })
                ssr_weight_and_prob.append({
                    "name": name,
                    "user_id": p["id"],
                    "weight": int(ssr_weight.get(name, 0)),
                    "prob": round(float(ssr_final_prob.get(name, 0.0)), 8),
                })

        inventory_summary = [
            {
                "pool": "NORMAL",
                "rarity": item["rarity"],
                "reward_name": item["reward_name"],
                "initial": int(item["initial"]),
                "remaining": int(item["remaining"]),
                "used": int(item["initial"]) - int(item["remaining"]),
            }
            for item in normal_reward_inventory
        ] + [
            {
                "pool": "SSR_FINAL",
                "rarity": item["rarity"],
                "reward_name": item["reward_name"],
                "initial": int(item["initial"]),
                "remaining": int(item["remaining"]),
                "used": int(item["initial"]) - int(item["remaining"]),
            }
            for item in ssr_reward_inventory
        ]

        choujiang_state.this_round_log = draw_settlement_logs

        logs_clear_range = _round_block_range("抽奖日志", round_id, 1, 400, 8)
        logs_sheet_rows = [
            ["轮次ID", round_id, "生成时间", datetime.now().isoformat(timespec="seconds")],
            ["抽次", "玩家", "玩家内抽次", "结果类型", "奖品/结果", "SSR概率", "roll", "保底前->后"],
        ]
        for item in draw_settlement_logs:
            logs_sheet_rows.append([
                item["draw_no"],
                item["name"],
                item["user_draw_no"],
                item.get("result_type", ""),
                item.get("reward_name", ""),
                item.get("ssr_prob", ""),
                item.get("roll", ""),
                f"{item.get('pity_before', '')}->{item.get('pity_after', '')}",
            ])
        logs_sheet_rows.append([])
        logs_sheet_rows.append(["SSR归属计算日志"])
        logs_sheet_rows.append(["步骤", "剩余权重", "说明"])
        for step in ssr_calculation_logs:
            logs_sheet_rows.append([
                step.get("step", ""),
                str(step.get("remaining", "")),
                str({k: v for k, v in step.items() if k not in {"step", "remaining"}}),
            ])
        logs_sheet_rows.append([])
        logs_sheet_rows.append(["SSR归属发奖日志"])
        logs_sheet_rows.append(["归属者", "稀有度", "奖品", "数量"])
        for item in ssr_award_logs:
            logs_sheet_rows.append([item["owner"], item["rarity"], item["reward_name"], item["count"]])
        logs_write_range = _round_block_range("抽奖日志", round_id, 1, len(logs_sheet_rows), 8)

        result_clear_range = _round_block_range("抽奖结果", round_id, 1, 220, 8)
        result_sheet_rows = [
            ["轮次ID", round_id, "总抽奖次数", total_draw_count, "SSR归属", ssr_owner_name or "无", "参与人数", len(active_participants)],
            ["参与者", "用户ID", "投入PAP", "基础奖励ISK", "分配抽数", "SSR权重", "SSR最终几率", "奖品明细"],
        ]
        reward_by_name = {x["name"]: x for x in rewards_by_user}
        for p in participants_invest_and_prob:
            rewards = reward_by_name.get(p["name"], {}).get("rewards", [])
            reward_text = ", ".join([f"{r['rarity']}:{r['reward_name']}x{r['count']}" for r in rewards])
            result_sheet_rows.append([
                p["name"],
                p["user_id"],
                p["used_paps"],
                p["base_reward_isk"],
                p["draw_count"],
                p["ssr_weight"],
                p["ssr_final_prob"],
                reward_text,
            ])
        result_sheet_rows.append([])
        result_sheet_rows.append(["奖池", "奖品库存", "初始", "已发放", "剩余"])
        for inv in inventory_summary:
            result_sheet_rows.append([inv["pool"], f"{inv['rarity']}:{inv['reward_name']}", inv["initial"], inv["used"], inv["remaining"]])
        result_write_range = _round_block_range("抽奖结果", round_id, 1, len(result_sheet_rows), 8)

        google_sheet_api.execute_with_retry(
            lambda service: service.spreadsheets().values().batchClear(
                spreadsheetId=CHOUJIANG_SPREADSHEET_ID,
                body={"ranges": [logs_clear_range, result_clear_range]},
            ),
            retries=2,
            retry_interval=0.8,
        )
        google_sheet_api.execute_with_retry(
            lambda service: service.spreadsheets().values().batchUpdate(
                spreadsheetId=CHOUJIANG_SPREADSHEET_ID,
                body={
                    "data": [
                        {
                            "majorDimension": "ROWS",
                            "range": logs_write_range,
                            "values": logs_sheet_rows,
                        },
                        {
                            "majorDimension": "ROWS",
                            "range": result_write_range,
                            "values": result_sheet_rows,
                        },
                    ],
                    "valueInputOption": "USER_ENTERED",
                },
            ),
            retries=2,
            retry_interval=0.8,
        )
        choujiang_state.tmp_result = {
            "round_id": round_id,
            "participants_invest_and_prob": participants_invest_and_prob,
            "rewards_by_user": rewards_by_user,
            "ssr_weight_and_prob": ssr_weight_and_prob,
            "ssr_owner": ssr_owner,
            "draw_settlement_logs": draw_settlement_logs,
            "ssr_calculation_logs": ssr_calculation_logs,
            "ssr_award_logs": ssr_award_logs,
            "inventory_summary": inventory_summary,
            "draw_count_map": draw_count_map,
        }

        return jsonify({
            "status": 200,
            "data": choujiang_state.tmp_result,
        }), 200
    except Exception as e:
        traceback.print_exc()
        logger.error(f"运行抽奖失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": f"运行抽奖失败, {e}"}), 500

@api_astrbot_bp.route('/kahunasystem/choujiang/get_tmp_result', methods=['POST'])
async def kahunasystem_choujiang_get_tmp_result():
    return jsonify({"status": 200, "data": choujiang_state.tmp_result}), 200

@api_astrbot_bp.route('/kahunasystem/choujiang/get_active_reward', methods=['GET'])
async def kahunasystem_choujiang_get_active_reward():
    try:
        round_id = int(choujiang_state.active_id or 1)
        rewards = await kahunasystem_choujiang_get_this_round_reward(round_id)
        if not rewards:
            return jsonify({
                "status": 200,
                "data": {
                    "round_id": round_id,
                    "time": "",
                    "rewards": [],
                },
            }), 200
        return jsonify({
            "status": 200,
            "data": {
                "round_id": round_id,
                "time": rewards[0],
                "rewards": rewards[1:],
            },
        }), 200
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取当前轮次抽奖奖品失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": f"获取当前轮次抽奖奖品失败, {e}"}), 500

@api_astrbot_bp.route('/kahunasystem/choujiang/get_reward', methods=['POST'])
async def kahunasystem_choujiang_get_reward():
    try:
        data = await request.get_json() or {}
        # start_raw = data.get("start")
        # end_raw = data.get("end")
        start_raw = 1
        end_raw = 10

        if start_raw in (None, ""):
            return jsonify({"status": 400, "message": "start 不能为空"}), 400
        try:
            start = int(start_raw)
        except (TypeError, ValueError):
            return jsonify({"status": 400, "message": "start 必须是整数"}), 400
        if start <= 0:
            return jsonify({"status": 400, "message": "start 必须大于0"}), 400

        if end_raw in (None, ""):
            end = start
        else:
            try:
                end = int(end_raw)
            except (TypeError, ValueError):
                return jsonify({"status": 400, "message": "end 必须是整数"}), 400
            if end <= 0:
                return jsonify({"status": 400, "message": "end 必须大于0"}), 400

        if end < start:
            return jsonify({"status": 400, "message": "end 不能小于 start"}), 400

        rewards_by_round = []
        for round_id in range(start, end + 1):
            rewards = await kahunasystem_choujiang_get_this_round_reward(round_id)
            rewards_by_round.append({
                "round_id": round_id,
                "time": rewards[0],
                "rewards": rewards[1:],
            })

        return jsonify({
            "status": 200,
            "data": {
                "start": start,
                "end": end,
                "rewards_by_round": rewards_by_round,
            },
        }), 200
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取奖品失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": f"获取奖品失败, {e}"}), 500

@api_astrbot_bp.route('/kahunasystem/choujiang/get_paps_status', methods=['POST'])
async def kahunasystem_choujiang_get_paps_status():
    data = await request.get_json() or {}
    name = data.get("name") or data.get("userName") or ""
    if not name:
        return jsonify({"status": 400, "message": "name 不能为空"}), 400
    user_id = choujiang_state.IDs.get(name)
    if user_id is None:
        return jsonify({"status": 400, "message": "name 不存在"}), 400
    
    return jsonify({"status": 200, "data": {
        "remain_paps": choujiang_state.remain_paps[user_id - 2],
        "this_round_used_paps": choujiang_state.this_round_used_paps[user_id - 2],
        "pity_count": int(choujiang_state.user_pity_count_by_name.get(name, 0))
    }}), 200

@api_astrbot_bp.route('/kahunasystem/choujiang/save_state', methods=['POST'])
async def kahunasystem_choujiang_save_state():
    try:
        rows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']
        row = rows[choujiang_state.active_id + 2]
        # 保存时提交本次run临时保底到正式保底。
        for name in choujiang_state.IDs.keys():
            choujiang_state.user_pity_count_by_name[name] = int(choujiang_state.user_pity_count_by_name_tmp.get(name, 0))
        pity_rows = []
        for name, _user_id in sorted(choujiang_state.IDs.items(), key=lambda x: x[1]):
            pity_rows.append([int(choujiang_state.user_pity_count_by_name.get(name, 0))])
        pity_end_row = 30 + max(1, len(pity_rows))
        resp = google_sheet_api.execute_with_retry(
            lambda service: service.spreadsheets().values().batchUpdate (
                spreadsheetId=CHOUJIANG_SPREADSHEET_ID,
                body={
                    "data": [
                        {
                            "majorDimension": "ROWS",
                            "range": f"'抽奖数据库'!{row}2:{row}28",
                            "values": [
                                [paps] for paps in choujiang_state.this_round_used_paps
                            ]
                        },
                        {
                            "majorDimension": "ROWS",
                            "range": f"'抽奖数据库'!A31:A{pity_end_row}",
                            "values": pity_rows if pity_rows else [[0]],
                        },
                    ],
                    "valueInputOption": "USER_ENTERED",
                },
            ),
            retries=2,
            retry_interval=0.8,
        )

        return jsonify({"status": 200, "message": "保存状态成功"}), 200
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存状态失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存状态失败"}), 500
