"""蓝图需求分析器 - 从 work_flow 中提取缺失蓝图汇总。"""
from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    """安全地将值转换为 int。"""
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _is_reaction_activity(activity_id: Any) -> bool:
    """检查活动 ID 是否属于反应类型。"""
    return activity_id in (9, 11)


async def _classify_missing_blueprint_type(type_id: int, active_id: Any) -> str:
    """将缺失的蓝图分类为：舰船 / 组件 / 反应 / 其他。

    复刻自 enterprise/api_astrbot_service.py:_classify_missing_blueprint_type，
    不导入企业模块。
    """
    from src_v2.model.EVE.sde.utils import SdeUtils

    if _is_reaction_activity(_safe_int(active_id, 0)):
        return "反应"

    category_name_zh = await SdeUtils.get_category_by_id(type_id, zh=True)
    if category_name_zh == "舰船":
        return "舰船"

    category_name_en = await SdeUtils.get_category_by_id(type_id, zh=False)
    if category_name_en == "Ship":
        return "舰船"

    market_group_list_en = await SdeUtils.get_market_group_list(type_id, zh=False)
    if any("Component" in str(group_name) for group_name in market_group_list_en):
        return "组件"

    market_group_list_zh = await SdeUtils.get_market_group_list(type_id, zh=True)
    if any("组件" in str(group_name) for group_name in market_group_list_zh):
        return "组件"

    return "其他"


async def analyze_blueprint_requirements(work_flow: list) -> list[dict]:
    """分析工作流中的缺失蓝图需求。

    遍历 work_flow，筛选 bp_object.fake 为 true 的条目，
    按 type_id 聚合，分类并查找 T2 发明源。

    参数:
        work_flow: 计划计算结果的 work_flow 列表。

    返回:
        每个元素包含以下字段的字典列表：
        - type_id: int             物品类型ID
        - type_name: str           英文名称
        - type_name_zh: str        中文名称
        - missing_blueprint_type: str  分类（舰船/组件/反应/其他）
        - bpc_count: int           所需 BPC 数量
        - bpc_details: list[dict]  每条 BPC 的 runs 详情 [{"runs": N}, ...]
        - runs_total: int          总运行次数
        - tech2_invention_source_bp_type_id: int | None  T2 发明源蓝图 type_id
        - tech2_invention_source_bp_type_name: str | None T2 发明源蓝图名称
    """
    from src_v2.model.EVE.sde.utils import SdeUtils
    from src_v2.model.EVE.industry.blueprint import BPManager as BPM

    grouped: dict[int, dict[str, Any]] = {}

    for work in work_flow:
        if not isinstance(work, dict):
            continue
        bp_object = work.get("bp_object")

        # 防御性检查：bp_object 必须为字典且 fake 为真
        if not isinstance(bp_object, dict) or not bp_object.get("fake"):
            continue

        type_id = _safe_int(work.get("type_id"), 0)
        if type_id <= 0:
            continue

        if type_id not in grouped:
            grouped[type_id] = {
                "type_id": type_id,
                "type_name": work.get("type_name", ""),
                "type_name_zh": work.get("type_name_zh", ""),
                "active_id": work.get("active_id"),
                "missing_blueprint_type": "",
                "bpc_count": 0,
                "bpc_runs_list": [],  # 暂存原始 runs，用于分组
                "runs_total": 0,
                "tech2_invention_source_bp_type_id": None,
                "tech2_invention_source_bp_type_name": None,
            }

        runs = max(_safe_int(work.get("runs"), 0), 0)
        grouped[type_id]["bpc_count"] += 1
        grouped[type_id]["bpc_runs_list"].append(runs)
        grouped[type_id]["runs_total"] += runs

    result = []
    for type_id in sorted(grouped.keys()):
        node = grouped[type_id]

        # 分类
        node["missing_blueprint_type"] = await _classify_missing_blueprint_type(
            type_id, node["active_id"]
        )

        # 将 runs 列表转换为 bpc_details（每个 BPC 的 runs 单独列出）
        node["bpc_details"] = [{"runs": r} for r in node["bpc_runs_list"]]

        # T2 发明源查找（仅 Tech II 物品）
        meta_name = await SdeUtils.get_metaname_by_typeid(type_id)
        if meta_name in ("Tech II", "二级科技"):
            try:
                tech2_bp_type_id = await BPM.get_bp_id_by_prod_typeid(type_id)
                if tech2_bp_type_id:
                    source_bp_type_id = (
                        await BPM.get_invention_source_bp_typeid_by_target_bp_typeid(
                            tech2_bp_type_id
                        )
                    )
                    if source_bp_type_id:
                        node["tech2_invention_source_bp_type_id"] = source_bp_type_id
                        node["tech2_invention_source_bp_type_name"] = (
                            await SdeUtils.get_name_by_id(source_bp_type_id)
                        )
            except Exception:
                pass  # T2 查询为尽力而为，失败时保持 None

        # 清理内部字段
        del node["bpc_runs_list"]
        del node["active_id"]

        result.append(node)

    return result
