"""
PI (Planetary Interaction) 利润计算引擎

核心功能：
1. 从 SDE 数据库构建 PI 物品层级关系 (P0-P4)
2. 查找从低级材料到目标产品的所有生产路径
3. 计算每条路径所需的工厂比例
4. 基于市场价格计算利润率和收益

P0 = 行星提取设施 (cycleTime=1800s)
P1-P4 = 加工设施 (cycleTime=3600s)
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select

from src_v2.core.database.connect_manager import get_redis_manager
from src_v2.core.log import logger
from src_v2.model.EVE.sde.sde_builder.database_manager import get_sde_database_manager as sde_database_manager
from src_v2.model.EVE.sde.sde_builder.inv_types_model import InvTypes
from src_v2.model.EVE.sde.sde_builder.planet_schematics_model import (
    PlanetSchematics,
    PlanetSchematicTypes,
)

# ============================================================================
# P4 自定义输入配置 — 特定 P4 产品不按标准 PI 链计算，使用固定输入模板
# ============================================================================

P4_CUSTOM_INPUTS: Dict[int, List[int]] = {
    # 广播节点
    2867: [2329, 9840, 2392, 9828, 3683, 2397, 3779],
    # 反破损快速反应无人机
    2868: [9840, 3775, 3689, 9842, 9838],
    # 有机砂浆喷注器
    2870: [2390, 3683, 2392, 2393, 3645, 9848],
    # 递推计算模块
    2871: [9834, 2346, 2396, 2393, 2399, 2398],
    # 自协调能源核心
    2872: [9828, 2392, 2397, 2395, 3779, 44, 9830],
    # 湿件主机
    2876: [2396, 3828, 2349, 2367, 2395],
}


# ============================================================================
# 数据类
# ============================================================================


@dataclass
class PISchematicInfo:
    """单个 PI 蓝图的完整信息"""

    schematic_id: int
    cycle_time: int
    name_zh: str
    name_en: str
    tier: int  # 0=P0 提取器, 1-4=P1-P4 加工器
    inputs: List[Tuple[int, int]]  # [(typeID, quantity), ...]
    outputs: List[Tuple[int, int]]  # [(typeID, quantity), ...]


@dataclass
class FactoryTier:
    """生产路径中某一层的工厂信息"""

    tier: int
    type_id: int
    name_zh: str
    factory_count: float  # 相对于 1 个目标工厂的数量
    cycle_time: int
    output_per_cycle: int
    input_per_cycle: Dict[int, int]  # {typeID: 每周期需要数量}


@dataclass
class ProductionPath:
    """一条完整生产路径（从原材料到目标产品）"""

    tiers: List[FactoryTier]
    path_description: str  # e.g. "P1→P2→P3"


@dataclass
class PathProfit:
    """单条路径的利润分析"""

    path: ProductionPath
    input_items: List[dict]  # [{type_id, name_zh, quantity, unit_price, total_cost}]
    output_item: dict  # {type_id, name_zh, quantity, unit_price, total_revenue}
    input_total_cost: float
    output_total_revenue: float
    profit: float
    profit_margin_pct: float
    tier_details: List[dict] = field(default_factory=list)  # 每层数据: [{tier, type_id, name_zh, factory_count, inputs: [{type_id, name_zh, quantity, unit_price, total_cost}], output_qty, output_price, tier_cost, tier_revenue, tier_profit, tier_margin_pct}]


@dataclass
class ProductSummary:
    """单个产品的综合分析"""

    type_id: int
    name_zh: str
    name_en: str
    tier: int
    output_per_cycle: int
    cycle_time: int
    path_count: int
    best_profit_path: Optional[PathProfit]  # 最高利润率路径
    all_paths: List[PathProfit] = field(default_factory=list)


# ============================================================================
# 核心计算器
# ============================================================================


class PIProfitCalculator:
    """PI 利润计算器

    使用前必须先调用 await build_hierarchy() 初始化层级数据。
    """

    def __init__(self):
        self._hierarchy: Dict[int, PISchematicInfo] = {}  # schematicID → info
        self._type_tiers: Dict[int, int] = {}  # typeID → tier (产出该类型的蓝图tier)
        self._type_names: Dict[int, Tuple[str, str]] = {}  # typeID → (name_zh, name_en)
        self._type_to_schematic: Dict[int, int] = {}  # typeID → schematicID (产出方)
        self._p0_schematic_ids: Set[int] = set()
        self._built = False

    # -----------------------------------------------------------------------
    # 1. 构建层级
    # -----------------------------------------------------------------------

    async def build_hierarchy(self) -> None:
        """从 SDE 数据库加载所有 PI 蓝图数据并计算层级关系。

        算法：
        1. P0 蓝图 = 输入材料不在任何蓝图的输出中 (纯原材料)
        2. P0 蓝图 tier=0，其输出类型的 type_tier=0
        3. 对于非 P0 蓝图：tier = max(输入类型的 tier) + 1
           （迭代执行直到全部赋值完毕）
        """
        logger.info("PIProfitCalculator: 开始构建 PI 层级...")

        self._hierarchy.clear()
        self._type_tiers.clear()
        self._type_names.clear()
        self._type_to_schematic.clear()
        self._p0_schematic_ids.clear()

        async with sde_database_manager().get_readonly_session() as session:
            # 加载所有蓝图主记录
            schem_stmt = select(PlanetSchematics)
            schem_result = await session.execute(schem_stmt)
            schematics: List[PlanetSchematics] = schem_result.scalars().all()

            # 加载所有蓝图物料明细
            types_stmt = select(PlanetSchematicTypes)
            types_result = await session.execute(types_stmt)
            schem_types: List[PlanetSchematicTypes] = types_result.scalars().all()

        # 按蓝图 ID 分组物料
        inputs_by_schematic: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        outputs_by_schematic: Dict[int, List[Tuple[int, int]]] = defaultdict(list)

        for st in schem_types:
            pair = (st.typeID, st.quantity)
            if st.isInput:
                inputs_by_schematic[st.schematicID].append(pair)
            else:
                outputs_by_schematic[st.schematicID].append(pair)

        # 收集所有作为某蓝图输出的 typeID
        all_output_type_ids: Set[int] = set()
        for outputs in outputs_by_schematic.values():
            for type_id, _ in outputs:
                all_output_type_ids.add(type_id)

        # 确定 P0 蓝图：其输入类型不在任何蓝图的输出中
        raw_type_ids: Set[int] = set()
        for s_id, inputs in inputs_by_schematic.items():
            for type_id, _ in inputs:
                if type_id not in all_output_type_ids:
                    raw_type_ids.add(type_id)
                    self._p0_schematic_ids.add(s_id)

        # 构建临时蓝图信息
        temp_info: Dict[int, dict] = {}
        for s in schematics:
            temp_info[s.schematicID] = {
                "schematic_id": s.schematicID,
                "cycle_time": s.cycleTime,
                "name_zh": s.name_zh or "",
                "name_en": s.name_en or "",
                "inputs": inputs_by_schematic.get(s.schematicID, []),
                "outputs": outputs_by_schematic.get(s.schematicID, []),
            }

        # 分配 tier：P0 → 0
        schematic_tiers: Dict[int, int] = {}
        for s_id in self._p0_schematic_ids:
            schematic_tiers[s_id] = 0
            for type_id, _ in temp_info[s_id]["outputs"]:
                # P0 提取器产出的是 P1 材料
                self._type_tiers[type_id] = 1
                self._type_to_schematic[type_id] = s_id

        # 迭代分配非 P0 蓝图
        remaining_ids = set(temp_info.keys()) - self._p0_schematic_ids
        max_iterations = 10
        iteration = 0

        while remaining_ids and iteration < max_iterations:
            iteration += 1
            assigned: Dict[int, int] = {}

            for s_id in list(remaining_ids):
                info = temp_info[s_id]
                input_tiers: List[int] = []
                all_known = True

                for type_id, _ in info["inputs"]:
                    if type_id in self._type_tiers:
                        input_tiers.append(self._type_tiers[type_id])
                    else:
                        all_known = False
                        break

                if all_known and input_tiers:
                    tier = max(input_tiers)
                    assigned[s_id] = tier
                    for type_id, _ in info["outputs"]:
                        self._type_tiers[type_id] = tier + 1
                        self._type_to_schematic[type_id] = s_id

            if not assigned:
                logger.warning(
                    f"PI 层级分配在第 {iteration} 轮停滞，"
                    f"剩余 {len(remaining_ids)} 个蓝图无法确定 tier"
                )
                break

            for s_id, tier in assigned.items():
                schematic_tiers[s_id] = tier
                remaining_ids.remove(s_id)

        # 构建最终的 hierarchy
        for s_id, info in temp_info.items():
            # 产出物品的 P 级别作为显示 tier（从 _type_tiers 获取）
            output_tier = 0
            for type_id, _ in info["outputs"]:
                output_tier = self._type_tiers.get(type_id, 0)
                break  # PI 蓝图每个只有一个产出

            self._hierarchy[s_id] = PISchematicInfo(
                schematic_id=s_id,
                cycle_time=info["cycle_time"],
                name_zh=info["name_zh"],
                name_en=info["name_en"],
                tier=output_tier,
                inputs=info["inputs"],
                outputs=info["outputs"],
            )

        # 批量加载所有涉及 typeID 的名称
        all_type_ids = (
            all_output_type_ids
            | raw_type_ids
            | {t for inputs in inputs_by_schematic.values() for t, _ in inputs}
        )
        await self._load_type_names(all_type_ids)

        self._built = True
        logger.info(
            f"PIProfitCalculator: 层级构建完成 - "
            f"共 {len(self._hierarchy)} 个蓝图, "
            f"{len(self._p0_schematic_ids)} 个 P0, "
            f"{len(all_output_type_ids)} 个产出类型"
        )

    async def _load_type_names(self, type_ids: Set[int]) -> None:
        """批量从 invTypes 加载物品名称。"""
        if not type_ids:
            return

        async with sde_database_manager().get_readonly_session() as session:
            stmt = select(InvTypes.typeID, InvTypes.typeName_zh, InvTypes.typeName_en).where(
                InvTypes.typeID.in_(list(type_ids))
            )
            result = await session.execute(stmt)
            for row in result:
                self._type_names[row.typeID] = (row.typeName_zh or "", row.typeName_en or "")

    # -----------------------------------------------------------------------
    # 2. 获取可分析产品
    # -----------------------------------------------------------------------

    async def get_products(self, min_tier: int = 2) -> List[ProductSummary]:
        """获取所有可分析的 P2+ 产品。

        Args:
            min_tier: 最低 tier，默认 2 (P2 及以上)

        Returns:
            产品摘要列表
        """
        if not self._built:
            await self.build_hierarchy()

        products: List[ProductSummary] = []
        seen: Set[int] = set()

        for info in self._hierarchy.values():
            if info.tier < min_tier:
                continue
            for type_id, qty in info.outputs:
                if type_id in seen:
                    continue
                seen.add(type_id)
                zh, en = self._type_names.get(type_id, ("", ""))
                products.append(
                    ProductSummary(
                        type_id=type_id,
                        name_zh=zh,
                        name_en=en,
                        tier=info.tier,
                        output_per_cycle=qty,
                        cycle_time=info.cycle_time,
                        path_count=info.tier - 1,  # P2=1条, P3=2条, P4=3条路径
                        best_profit_path=None,
                        all_paths=[],
                    )
                )

        return products

    # -----------------------------------------------------------------------
    # 3. 查找生产路径
    # -----------------------------------------------------------------------

    async def find_production_paths(self, type_id: int) -> List[ProductionPath]:
        """查找从 P1 原材料到目标产品的所有生产路径。

        从目标产品的蓝图开始，通过 BFS 逆向追踪所有输入依赖。
        叶子节点是 type_tier=0 的 P1 材料。

        Args:
            type_id: 目标产品 typeID

        Returns:
            所有可能的 ProductionPath 列表
        """
        if not self._built:
            await self.build_hierarchy()

        # 找到产出该 type_id 的蓝图
        if type_id not in self._type_to_schematic:
            logger.warning(f"PI: 未找到产出 typeID {type_id} 的蓝图")
            return []

        root_schematic_id = self._type_to_schematic[type_id]
        root_info = self._hierarchy.get(root_schematic_id)
        if root_info is None:
            return []

        # 使用 BFS 构建依赖链
        # 每个节点: (schematic_id, parent_type_id, parent_qty_needed)
        # 返回多个 path（如果有备选蓝图产出同一中间产品）
        paths_raw: List[List[Tuple[int, int, int]]] = []  # [(schematic_id, type_id, qty_needed), ...]

        def _backtrack(
            current: List[Tuple[int, int, int]],
            remaining_inputs: List[Tuple[int, int, int]],
        ):
            """递归构建路径。

            current: 当前路径中已处理的节点
            remaining_inputs: 待处理的输入 (parent_schematic_id, type_id, qty_needed)
            """
            if not remaining_inputs:
                # 叶子节点 - 路径完成
                paths_raw.append(list(current))
                return

            parent_s_id, inp_type_id, qty_needed = remaining_inputs[0]
            rest = remaining_inputs[1:]

            # 查找产出此输入的蓝图
            if inp_type_id not in self._type_to_schematic:
                # 无蓝图产出 → 这是原材料，跳过
                _backtrack(current + [(0, inp_type_id, qty_needed)], rest)
                return

            producer_s_id = self._type_to_schematic[inp_type_id]
            producer_info = self._hierarchy.get(producer_s_id)
            if producer_info is None:
                _backtrack(current + [(0, inp_type_id, qty_needed)], rest)
                return

            # 递归处理此蓝图的输入
            new_remaining = list(rest)
            for child_type_id, child_qty in producer_info.inputs:
                new_remaining.append((producer_s_id, child_type_id, child_qty))

            _backtrack(
                current + [(producer_s_id, inp_type_id, qty_needed)],
                new_remaining,
            )

        # 从根蓝图开始
        initial_remaining: List[Tuple[int, int, int]] = []
        for inp_type_id, inp_qty in root_info.inputs:
            initial_remaining.append((root_schematic_id, inp_type_id, inp_qty))

        # 展开所有路径（处理可能的备选蓝图）
        all_expanded_paths: List[List[Tuple[int, int, int]]] = []

        def _expand_paths(
            node_list: List[Tuple[int, int, int]],
            remainder: List[Tuple[int, int, int]],
        ):
            """展开备选蓝图 → 多条路径。"""
            if not remainder:
                all_expanded_paths.append(list(node_list))
                return

            parent_s_id, child_type_id, child_qty = remainder[0]
            rest_remainder = remainder[1:]

            # 查找所有产出此 child_type_id 的蓝图
            if child_type_id in self._type_to_schematic:
                producer_s_id = self._type_to_schematic[child_type_id]
                producer_info = self._hierarchy.get(producer_s_id)
                if producer_info and producer_info.tier > 1:
                    # 有处理蓝图 → 继续展开
                    new_remainder = list(rest_remainder)
                    for grandchild_type_id, grandchild_qty in producer_info.inputs:
                        new_remainder.append((producer_s_id, grandchild_type_id, grandchild_qty))
                    _expand_paths(
                        node_list + [(producer_s_id, child_type_id, child_qty)],
                        new_remainder,
                    )
                    return

            # 无法继续展开 → 叶子节点
            _expand_paths(node_list + [(0, child_type_id, child_qty)], rest_remainder)

        _expand_paths(
            [(root_schematic_id, type_id, sum(o[1] for o in root_info.outputs))],
            initial_remaining,
        )

        # 转换为 ProductionPath 对象
        paths: List[ProductionPath] = []
        for raw_path in all_expanded_paths:
            tiers_list, path_desc = self._build_path_from_raw(raw_path)
            if tiers_list:
                paths.append(ProductionPath(tiers=tiers_list, path_description=path_desc))

        return paths

    def _build_path_from_raw(
        self, raw_path: List[Tuple[int, int, int]]
    ) -> Tuple[List[FactoryTier], str]:
        """将原始路径数据转换为 FactoryTier 列表和描述。

        raw_path: [(schematic_id, type_id, qty_needed), ...]
        """
        # 按 schematic_id 分组，每层计算工厂数量
        # 重新组织：从叶子（低tier）到根（高tier）
        schem_entries: Dict[int, dict] = {}  # schematic_id → {type_id, inputs, ...}

        for s_id, type_id, qty_needed in raw_path:
            if s_id == 0:
                continue
            if s_id not in schem_entries:
                info = self._hierarchy.get(s_id)
                if info is None:
                    continue
                schem_entries[s_id] = {
                    "tier": info.tier,
                    "type_id": type_id,
                    "name_zh": info.name_zh,
                    "cycle_time": info.cycle_time,
                    "output_per_cycle": sum(o[1] for o in info.outputs),
                    "inputs": dict(info.inputs),
                }

        if not schem_entries:
            return [], ""

        # 按 tier 排序（从低到高）
        sorted_entries = sorted(schem_entries.values(), key=lambda x: x["tier"])
        path_desc_parts = [f"P{e['tier']}" for e in sorted_entries]
        path_desc = "→".join(path_desc_parts)

        tiers_list: List[FactoryTier] = []
        for entry in sorted_entries:
            ft = FactoryTier(
                tier=entry["tier"],
                type_id=entry["type_id"],
                name_zh=entry["name_zh"],
                factory_count=1.0,  # 稍后由 calculate_factory_chain 填充
                cycle_time=entry["cycle_time"],
                output_per_cycle=entry["output_per_cycle"],
                input_per_cycle=entry["inputs"],
            )
            tiers_list.append(ft)

        return tiers_list, path_desc

    # -----------------------------------------------------------------------
    # 4. 计算工厂链
    # -----------------------------------------------------------------------

    def calculate_factory_chain(
        self, schematic_id: int, stop_tier: int = 0,
        stop_materials: Optional[Set[int]] = None,
    ) -> ProductionPath:
        """计算从根蓝图开始的工厂需求链。

        Args:
            schematic_id: 根蓝图 ID
            stop_tier: 截断层级（0=不截断，N=在 type_tier≤N 的输入处停止）
            stop_materials: 停止材料集合（这些 type_id 不再继续分解）
        """
        if schematic_id not in self._hierarchy:
            return ProductionPath(tiers=[], path_description="")

        root_info = self._hierarchy[schematic_id]
        all_tiers_list: List[FactoryTier] = []
        path_desc_parts: List[str] = []
        # type_id → factory_count 缓存，避免重复计算
        factory_counts: Dict[int, float] = {}

        def _compute(s_id: int, parent_factory_count: float = 1.0) -> float:
            """递归计算蓝图 s_id 所需的工厂数量。

            Returns: 此蓝图所需的工厂数量
            """
            info = self._hierarchy.get(s_id)
            if info is None:
                return parent_factory_count

            # 确定此蓝图的产出 typeID
            output_type_id = None
            output_qty = 0
            for ot, oq in info.outputs:
                output_type_id = ot
                output_qty += oq

            if output_type_id is None or output_qty == 0:
                return parent_factory_count

            # 检查缓存
            if output_type_id in factory_counts:
                return factory_counts[output_type_id]

            # 计算此蓝图的工厂数量
            my_factory_count = parent_factory_count

            # 构建此层的 FactoryTier
            ft = FactoryTier(
                tier=info.tier,
                type_id=output_type_id,
                name_zh=info.name_zh,
                factory_count=my_factory_count,
                cycle_time=info.cycle_time,
                output_per_cycle=output_qty,
                input_per_cycle=dict(info.inputs),
            )
            all_tiers_list.append(ft)

            # 递归计算所有输入的上游工厂
            for inp_type_id, inp_qty in info.inputs:
                # 停止材料：在清单内的材料不再继续分解
                if stop_materials and inp_type_id in stop_materials:
                    continue
                # 层级截断：停止在 type_tier ≤ stop_tier 的输入处
                if stop_tier > 0 and self._type_tiers.get(inp_type_id, -1) <= stop_tier:
                    continue
                # 查找产出此输入的蓝图
                if inp_type_id not in self._type_to_schematic:
                    continue
                child_s_id = self._type_to_schematic[inp_type_id]
                child_info = self._hierarchy.get(child_s_id)
                if child_info is None:
                    continue

                child_output_qty = sum(o[1] for o in child_info.outputs)

                # 计算子工厂需求
                # need_rate = inp_qty / info.cycle_time
                # child_rate = child_output_qty / child_info.cycle_time
                # child_factories = need_rate / child_rate
                # = (inp_qty * child_info.cycle_time) / (info.cycle_time * child_output_qty)
                child_factories = (inp_qty * child_info.cycle_time) / (
                    info.cycle_time * child_output_qty
                ) * my_factory_count

                _compute(child_s_id, child_factories)

            factory_counts[output_type_id] = my_factory_count
            return my_factory_count

        _compute(schematic_id, 1.0)

        # 按 tier 排序（从低到高，使叶子在前）
        all_tiers_list.sort(key=lambda x: x.tier)
        path_desc_parts = [f"P{ft.tier}" for ft in all_tiers_list]
        path_desc = "→".join(path_desc_parts)

        return ProductionPath(tiers=all_tiers_list, path_description=path_desc)

    # -----------------------------------------------------------------------
    # 5. 计算利润
    # -----------------------------------------------------------------------

    async def calculate_path_profit(
        self, path: ProductionPath, price_base: str = "sell",
        material_price_base: str = "sell",
    ) -> PathProfit:
        """计算一条生产路径的利润。

        Args:
            path: 生产路径
            price_base: 产出品价格基准 - "buy"(收购), "sell"(出售), "mid"(中间价)
            material_price_base: 原材料价格基准
        """
        if not path.tiers:
            zh, en = self._type_names.get(0, ("未知", "Unknown"))
            return PathProfit(
                path=path,
                input_items=[],
                output_item={"type_id": 0, "name_zh": zh, "quantity": 0, "unit_price": 0, "total_revenue": 0},
                input_total_cost=0.0,
                output_total_revenue=0.0,
                profit=0.0,
                profit_margin_pct=0.0,
            )

        target_tier = path.tiers[-1]  # 最高 tier = 目标产品

        # 提取叶子输入：输入物品的生产蓝图不在当前链中 → 叶子
        leaf_inputs: Dict[int, float] = {}  # typeID → total_qty_needed

        # 构建链中蓝图的 ID 集合
        chain_schematic_ids: Set[int] = set()
        for ft in path.tiers:
            s_id = self._type_to_schematic.get(ft.type_id)
            if s_id is not None:
                chain_schematic_ids.add(s_id)

        for ft in path.tiers:
            for inp_type_id, inp_qty in ft.input_per_cycle.items():
                producer_s_id = self._type_to_schematic.get(inp_type_id)
                if producer_s_id is None:
                    continue
                if producer_s_id in chain_schematic_ids:
                    # 输入由链内蓝图生产 → 不是叶子
                    continue
                # 叶子节点：累加需求量（考虑工厂倍数）
                leaf_inputs[inp_type_id] = leaf_inputs.get(inp_type_id, 0.0) + (
                    inp_qty * ft.factory_count
                )

        # 获取价格（材料与产品分别使用不同基准）
        def _price_key(base: str) -> str:
            return {"buy": "max_buy", "sell": "min_sell", "mid": "mid"}.get(base, "min_sell")
        material_key = _price_key(material_price_base)
        product_key = _price_key(price_base)

        # 计算输入成本（使用材料价格基准）
        input_items: List[dict] = []
        input_total_cost = 0.0

        for type_id, qty in leaf_inputs.items():
            price_data = await self._get_price(type_id)
            unit_price = self._extract_price(price_data, material_key)
            total_cost = qty * unit_price
            input_total_cost += total_cost

            zh, en = self._type_names.get(type_id, ("", ""))
            input_items.append(
                {
                    "type_id": type_id,
                    "name_zh": zh,
                    "name_en": en,
                    "quantity": round(qty, 4),
                    "unit_price": round(unit_price, 2),
                    "total_cost": round(total_cost, 2),
                }
            )

        # 计算产出收益
        output_type_id = target_tier.type_id
        output_qty = target_tier.output_per_cycle * target_tier.factory_count
        price_data = await self._get_price(output_type_id)
        unit_price = self._extract_price(price_data, product_key)
        output_total_revenue = output_qty * unit_price

        zh, en = self._type_names.get(output_type_id, ("", ""))
        output_item = {
            "type_id": output_type_id,
            "name_zh": zh,
            "name_en": en,
            "quantity": round(output_qty, 4),
            "unit_price": round(unit_price, 2),
            "total_revenue": round(output_total_revenue, 2),
        }

        profit = output_total_revenue - input_total_cost
        profit_margin_pct = (profit / input_total_cost * 100) if input_total_cost > 0 else 0.0

        # 逐层成本明细
        tier_details: List[dict] = []
        cumulative_cost = 0.0
        for ft in path.tiers:
            tier_inputs: List[dict] = []
            tier_input_cost = 0.0
            for inp_type_id, inp_qty in ft.input_per_cycle.items():
                total_qty = inp_qty * ft.factory_count
                pdata = await self._get_price(inp_type_id)
                inp_price = self._extract_price(pdata, material_key)
                inp_total = total_qty * inp_price
                tier_input_cost += inp_total
                zh, en = self._type_names.get(inp_type_id, ("", ""))
                tier_inputs.append({
                    "type_id": inp_type_id,
                    "name_zh": zh,
                    "quantity": round(total_qty, 4),
                    "unit_price": round(inp_price, 2),
                    "total_cost": round(inp_total, 2),
                })
            cumulative_cost += tier_input_cost
            # 产出价值
            out_qty = ft.output_per_cycle * ft.factory_count
            pdata = await self._get_price(ft.type_id)
            out_price = self._extract_price(pdata, product_key)
            tier_revenue = out_qty * out_price
            tier_profit = tier_revenue - tier_input_cost
            tier_margin = (tier_profit / tier_input_cost * 100) if tier_input_cost > 0 else 0.0
            # 工厂产出物名称：优先使用 _type_names，回退到蓝图表名
            output_names = self._type_names.get(ft.type_id, ("", ""))
            output_name_zh = output_names[0] or ft.name_zh or ""
            tier_details.append({
                "tier": ft.tier,
                "type_id": ft.type_id,
                "name_zh": output_name_zh,
                "factory_count": round(ft.factory_count, 2),
                "inputs": tier_inputs,
                "tier_input_cost": round(tier_input_cost, 2),
                "cumulative_cost": round(cumulative_cost, 2),
                "output_qty": round(out_qty, 4),
                "output_price": round(out_price, 2),
                "tier_revenue": round(tier_revenue, 2),
                "tier_profit": round(tier_profit, 2),
                "tier_margin_pct": round(tier_margin, 2),
            })

        return PathProfit(
            path=path,
            input_items=input_items,
            output_item=output_item,
            input_total_cost=round(input_total_cost, 2),
            output_total_revenue=round(output_total_revenue, 2),
            profit=round(profit, 2),
            profit_margin_pct=round(profit_margin_pct, 2),
            tier_details=tier_details,
        )

    # -----------------------------------------------------------------------
    # 6. 综合计算单个产品
    # -----------------------------------------------------------------------

    async def calculate_product(
        self, type_id: int, price_base: str = "sell",
        material_price_base: str = "sell",
    ) -> Optional[ProductSummary]:
        """对单个产品执行完整的路径发现 + 工厂计算 + 利润分析。

        Args:
            type_id: 目标产品 typeID
            price_base: 价格基准

        Returns:
            ProductSummary 或 None（如产品不可分析）
        """
        if not self._built:
            await self.build_hierarchy()

        # 查找产出此产品的蓝图
        if type_id not in self._type_to_schematic:
            return None

        schematic_id = self._type_to_schematic[type_id]
        info = self._hierarchy.get(schematic_id)
        if info is None:
            return None

        zh, en = self._type_names.get(type_id, ("", ""))

        summary = ProductSummary(
            type_id=type_id,
            name_zh=zh,
            name_en=en,
            tier=info.tier,
            output_per_cycle=sum(o[1] for o in info.outputs),
            cycle_time=info.cycle_time,
            path_count=0,
            best_profit_path=None,
            all_paths=[],
        )

        # ===== 自定义 P4：停止材料 =====
        stop_materials: Optional[Set[int]] = None
        if type_id in P4_CUSTOM_INPUTS:
            stop_materials = set(P4_CUSTOM_INPUTS[type_id])

        # ===== 标准 PI 链计算 =====
        target_tier = info.tier
        full_paths: List[ProductionPath] = []
        for start_tier in range(1, target_tier):
            chain = self.calculate_factory_chain(
                schematic_id, stop_tier=start_tier, stop_materials=stop_materials
            )
            if chain.tiers:
                # 路径描述：从起始材料层级到目标产品层级
                parts = [f"P{t}" for t in range(start_tier, target_tier + 1)]
                chain.path_description = "→".join(parts)
                full_paths.append(chain)

        # 计算每条路径的利润
        all_path_profits: List[PathProfit] = []
        best: Optional[PathProfit] = None

        for chain in full_paths:
            profit = await self.calculate_path_profit(chain, price_base, material_price_base)
            all_path_profits.append(profit)
            if best is None or profit.profit_margin_pct > best.profit_margin_pct:
                best = profit

        summary.path_count = len(full_paths)
        summary.all_paths = all_path_profits
        summary.best_profit_path = best

        return summary

    # -----------------------------------------------------------------------
    # 7. 批量计算
    # -----------------------------------------------------------------------

    async def calculate_all(self, price_base: str = "sell", material_price_base: str = "sell") -> List[ProductSummary]:
        """对所有 P2+ 产品执行利润分析。

        Args:
            price_base: 价格基准

        Returns:
            所有产品的 ProductSummary 列表
        """
        if not self._built:
            await self.build_hierarchy()

        products = await self.get_products(min_tier=2)
        results: List[ProductSummary] = []

        for product in products:
            full = await self.calculate_product(product.type_id, price_base, material_price_base)
            if full is not None:
                results.append(full)

        # 按层级降序，同层级内按利润率降序
        results.sort(
            key=lambda p: (
                p.tier,
                p.best_profit_path.profit_margin_pct if p.best_profit_path else 0,
            ),
            reverse=True,
        )

        return results

    # -----------------------------------------------------------------------
    # 内部辅助方法
    # -----------------------------------------------------------------------

    async def _get_price(self, type_id: int, zone: str = "jita") -> Optional[dict]:
        """从 Redis Hash 获取单个物品的市场价格。

        市场数据存储在 Redis Hash 中: market_price:{zone}:{type_id}
        字段: max_buy, min_sell 等
        """
        try:
            rdm = get_redis_manager()
            redis_client = getattr(rdm, "r", None) or getattr(rdm, "redis", None)
            if redis_client:
                key = f"market_price:{zone}:{type_id}"
                data = await redis_client.hgetall(key)
                if data:
                    # hgetall 返回 {b"max_buy": b"123.45", ...} 或已 decode 的 dict
                    return {
                        k: float(v) if isinstance(v, (str, bytes)) else v
                        for k, v in (data or {}).items()
                    }
        except Exception as e:
            logger.warning(f"PI: 获取价格失败 typeID={type_id}: {e}")
        return None

    @staticmethod
    def _extract_price(price_data: Optional[dict], price_key: str) -> float:
        """从价格数据中提取指定价格。

        Args:
            price_data: Redis 中的价格数据
            price_key: "max_buy", "min_sell", 或 "mid"

        Returns:
            价格浮点数，默认 0.0
        """
        if price_data is None:
            return 0.0
        if price_key == "mid":
            buy = price_data.get("max_buy", 0) or 0
            sell = price_data.get("min_sell", 0) or 0
            return (buy + sell) / 2.0
        return float(price_data.get(price_key, 0) or 0)
