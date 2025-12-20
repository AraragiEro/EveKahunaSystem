import math
from rapidfuzz.process import cpdist
from ortools.linear_solver import pywraplp
from typing import List, Optional

from src_v2.model.EVE.sde.utils import SdeUtils
from src_v2.model.EVE.market.market_manager import MarketManager, JITA_TRADE_HUB_STRUCTURE_ID, REGION_FORGE_ID
from src_v2.core.database.kahuna_database_utils_v2 import EveMarketRegionOrdersDBUtils
from src_v2.core.log import logger

class CompressedAsteroidUtils:
    
    def __init__(self):
        self._type_material_data_dict = None
        self._material_price_dict = {}
        self._asteroid_order_data = None  # 原始按价格聚合的卖单数据 {type_id: [[price, quantity], ...]}
        # 转换后的缓存结构:
        # { type_id: [[price, quantity, quantity_sum_lower, avg_price_lower], ...] }
        self._compressed_asteroid_stats = None
        self._asteroid_price_args = {}
        self._standard_and_moon_ore_ids: Optional[List[int]] = None
        self._ice_ore_ids: Optional[List[int]] = None
        self._refinement_rate: float = 0.906  # 化矿率，默认0.906
        # 矿物相关数据
        self._mineral_order_data = None  # 原始按价格聚合的矿物卖单数据 {type_id: [[price, quantity], ...]}
        self._mineral_stats = None  # 转换后的矿物统计缓存 { type_id: [[price, quantity, quantity_sum_lower, avg_price_lower], ...] }
        self._mineral_ids: Optional[List[int]] = None  # 所有可购买的矿物ID列表
        self._volume_cache: dict = {}  # 体积缓存 {type_id: volume}
        
    async def _init_type_material_data(self):
        # 获取两个分类列表
        standard_and_moon_ore_ids, ice_ore_ids = await SdeUtils.get_compressed_asteroid_type_ids()
        self._standard_and_moon_ore_ids = standard_and_moon_ore_ids
        self._ice_ore_ids = ice_ore_ids
        
        # 合并两个列表用于后续数据查询
        compressed_asteroid_type_ids = standard_and_moon_ore_ids + ice_ore_ids
        
        type_material_data = await SdeUtils.get_type_material_data_by_ids(compressed_asteroid_type_ids)
        
        # 化矿数据
        self._type_material_data_dict = {type_id: {
            data["materialTypeID"]: data["quantity"] for data in type_material_data if data["typeID"] == type_id
        } for type_id in compressed_asteroid_type_ids}

        # 矿物价格
        material_set = set(data["materialTypeID"] for data in type_material_data)
        self._material_price_dict = {material_id: await MarketManager().get_jita_buy_price(material_id) for material_id in material_set}

        # 矿石订单处理
        # 查询所有压缩矿石类型在Jita的卖单，按价格分组汇总数量
        asteroid_order_data = await EveMarketRegionOrdersDBUtils.get_sell_orders_by_type_ids_grouped_by_price(
            type_ids=compressed_asteroid_type_ids,
            location_id=JITA_TRADE_HUB_STRUCTURE_ID,
            region_id=REGION_FORGE_ID
        )
        
        # 存储原始订单数据
        self._asteroid_order_data = asteroid_order_data

        # 基于原始订单数据构建缓存结构，便于后续按需求数量快速计算平均单价
        self._compressed_asteroid_stats = self._transform_asteroid_order_data(self._asteroid_order_data)

        # 矿物订单处理
        # 收集所有矿物ID
        self._mineral_ids = list(material_set)
        
        # 查询所有矿物在Jita的卖单，按价格分组汇总数量
        mineral_order_data = await EveMarketRegionOrdersDBUtils.get_sell_orders_by_type_ids_grouped_by_price(
            type_ids=self._mineral_ids,
            location_id=JITA_TRADE_HUB_STRUCTURE_ID,
            region_id=REGION_FORGE_ID
        )
        
        # 存储原始订单数据
        self._mineral_order_data = mineral_order_data
        
        # 基于原始订单数据构建缓存结构，便于后续按需求数量快速计算平均单价
        self._mineral_stats = self._transform_asteroid_order_data(self._mineral_order_data)

        return self._compressed_asteroid_stats

    @staticmethod
    def _transform_asteroid_order_data(asteroid_order_data):
        """
        将原始订单结构:
        {
          type_id: [[price, quantity], ...]  # 按价格升序
        }

        转换为:
        {
          type_id: [
            [price, quantity, quantity_sum_lower, avg_price_lower],
            ...
          ]
        }

        其中:
        - quantity_sum_lower: 小于当前 price 的数量总和
        - avg_price_lower: 这些更低价格订单的数量加权平均价；若不存在更低价订单，则为 0
        """
        if asteroid_order_data is None:
            return {}

        transformed = {}

        for type_id, orders in asteroid_order_data.items():
            if not orders:
                transformed[type_id] = []
                continue

            # 确保按价格升序
            # 订单元素假定为 [price, quantity]
            sorted_orders = sorted(orders, key=lambda x: x[0])

            cum_qty = 0.0       # 小于当前价格的累计数量
            cum_cost = 0.0      # 小于当前价格的累计金额 (price * quantity 之和)
            stats_list = []

            for price, qty in sorted_orders:
                quantity_sum_lower = cum_qty
                if cum_qty == 0:
                    avg_price_lower = 0.0
                else:
                    avg_price_lower = cum_cost / cum_qty

                stats_list.append([
                    float(price),
                    float(qty),
                    float(quantity_sum_lower),
                    float(avg_price_lower),
                ])

                # 更新累计
                cum_qty += qty
                cum_cost += price * qty

            # quantity_sum_lower 随遍历单调递增，已按 quantity_sum_lower 有序，无需再次排序
            transformed[type_id] = stats_list

        return transformed

    async def _ensure_asteroid_stats_ready(self):
        """
        确保 _compressed_asteroid_stats 已构建。
        在需要按数量计算均价前调用。
        """
        if self._compressed_asteroid_stats is not None:
            return

        # 若还未初始化原始订单数据，则先进行初始化
        if self._asteroid_order_data is None:
            await self._init_type_material_data()

        self._compressed_asteroid_stats = self._transform_asteroid_order_data(self._asteroid_order_data)
    
    async def _ensure_mineral_stats_ready(self):
        """
        确保 _mineral_stats 已构建。
        在需要按数量计算矿物均价前调用。
        """
        if self._mineral_stats is not None:
            return

        # 若还未初始化原始订单数据，则先进行初始化
        if self._mineral_order_data is None:
            await self._init_type_material_data()

        self._mineral_stats = self._transform_asteroid_order_data(self._mineral_order_data)

    async def _get_asteroid_price_by_need(self, type_id: int, need_quantity: float):
        """
        根据需求数量 need_quantity，计算购买该数量压缩矿石或矿物的平均单价。

        利用缓存结构中每一档:
        [price, quantity, quantity_sum_lower, avg_price_lower]

        对于满足:
          quantity_sum_lower < need_quantity <= quantity_sum_lower + quantity
        的当前档位，利用:
        - quantity_sum_lower
        - avg_price_lower
        - 当前档位 price, quantity

        计算买入 need_quantity 这一整段的加权平均单价。
        """
        if need_quantity <= 0:
            return 0.0

        # 判断是矿石还是矿物
        if self._is_mineral(type_id):
            await self._ensure_mineral_stats_ready()
            stats_dict = self._mineral_stats
        else:
            await self._ensure_asteroid_stats_ready()
            stats_dict = self._compressed_asteroid_stats

        if not stats_dict:
            return None

        type_stats = stats_dict.get(type_id)
        if not type_stats:
            return None

        need_quantity = float(need_quantity)

        # 遍历找到满足 quantity_sum_lower < x <= quantity_sum_lower + quantity 的档位
        for price, qty, quantity_sum_lower, avg_price_lower in type_stats:
            upper_qty = quantity_sum_lower + qty
            if quantity_sum_lower < need_quantity <= upper_qty:
                # 低于当前价格部分的总量与均价
                lower_qty = quantity_sum_lower

                if lower_qty <= 0:
                    # 全部从当前价格档买入
                    return float(price)

                # 低价部分总成本
                lower_cost = avg_price_lower * lower_qty
                # 当前价格档中，为满足 need_quantity 需要的数量
                need_in_current_level = need_quantity - lower_qty
                current_cost = price * need_in_current_level

                avg_price = (lower_cost + current_cost) / need_quantity
                return float(avg_price)

        # 若需求数量超过所有订单总和，返回 None
        return None

    async def _get_total_available_quantity(self, type_id: int) -> float:
        """获取市场上该物品的总可用数量"""
        if self._is_mineral(type_id):
            await self._ensure_mineral_stats_ready()
            stats_dict = self._mineral_stats
        else:
            await self._ensure_asteroid_stats_ready()
            stats_dict = self._compressed_asteroid_stats
        
        if not stats_dict:
            return 0.0
        
        type_stats = stats_dict.get(type_id)
        if not type_stats:
            return 0.0
        
        # 最后一个条目的 quantity_sum_lower + quantity 就是总数量
        if type_stats:
            last_price, last_qty, last_quantity_sum_lower, last_avg_price_lower = type_stats[-1]
            return float(last_quantity_sum_lower + last_qty)
        
        return 0.0

    def _get_mineral_price(self, mineral_id: int) -> float:
        return self._material_price_dict.get(mineral_id, 0.0)
    
    def _is_ice_ore(self, type_id: int) -> bool:
        """判断是否为冰矿"""
        if self._ice_ore_ids is None:
            return False
        return type_id in self._ice_ore_ids
    
    def _is_mineral(self, type_id: int) -> bool:
        """判断是否为矿物"""
        if self._mineral_ids is None:
            return False
        return type_id in self._mineral_ids
    
    def _round_ore_quantity_for_iteration(self, type_id: int, quantity: float) -> float:
        """根据矿石类型向上取整（用于迭代过程中的价格查询）
        
        在迭代过程中使用，只对冰矿和矿物取整，标准/卫星矿石保持原样
        因为约束条件中的数量应该保持原样，但价格需要乘以100
        
        Args:
            type_id: 矿石类型ID或矿物ID
            quantity: 原始数量
            
        Returns:
            取整后的数量（用于价格查询）
            - 冰矿和矿物：向上取整到1
            - 标准矿石和卫星矿石：保持原样（不乘以100）
        """
        if self._is_ice_ore(type_id) or self._is_mineral(type_id):
            # 冰矿和矿物：向上取整到1
            return math.ceil(quantity)
        else:
            # 标准矿石和卫星矿石：保持原样，不乘以100
            return quantity
    
    def _round_ore_quantity(self, type_id: int, quantity: float) -> float:
        """根据矿石类型向上取整（用于最终结果）
        
        Args:
            type_id: 矿石类型ID或矿物ID
            quantity: 原始数量
            
        Returns:
            取整后的数量
            - 冰矿和矿物：向上取整到1
            - 标准矿石和卫星矿石：向上取整到100（math.ceil(quantity) * 100）
        """
        if self._is_ice_ore(type_id) or self._is_mineral(type_id):
            # 冰矿和矿物：向上取整到1
            return math.ceil(quantity)
        else:
            # 标准矿石和卫星矿石：向上取整到100
            return math.ceil(quantity) * 100

    async def _build_ore_data_from_dict(self):
        """
        从 _type_material_data_dict 构建矿石数据列表
        返回格式: [{'ore_id': type_id, 'mineral_yield': {mineral_id: quantity}, 'volume': volume}, ...]
        
        同时为每种矿物添加"矿石"条目，矿物产出自己，数量为1（化矿率1）
        同时缓存所有矿石和矿物的体积数据
        """
        ore_data = []
        
        # 添加矿石数据
        if self._type_material_data_dict:
            for type_id, mineral_yield in self._type_material_data_dict.items():
                # 获取并缓存体积
                if type_id not in self._volume_cache:
                    volume = await SdeUtils.get_volume_by_type_id(type_id)
                    self._volume_cache[type_id] = volume if volume is not None else 0.0
                else:
                    volume = self._volume_cache[type_id]
                
                ore_data.append({
                    'ore_id': type_id,
                    'ore_name': await SdeUtils.get_name_by_id(type_id),
                    'ore_name_zh': await SdeUtils.get_cn_name_by_id(type_id),
                    'mineral_yield': mineral_yield,
                    'volume': volume
                })
        
        # 为每种矿物添加"矿石"条目（产出自己，化矿率1）
        if self._mineral_ids:
            for mineral_id in self._mineral_ids:
                # 获取并缓存体积
                if mineral_id not in self._volume_cache:
                    volume = await SdeUtils.get_volume_by_type_id(mineral_id)
                    self._volume_cache[mineral_id] = volume if volume is not None else 0.0
                else:
                    volume = self._volume_cache[mineral_id]
                
                ore_data.append({
                    'ore_id': mineral_id,
                    'ore_name': await SdeUtils.get_name_by_id(mineral_id),
                    'ore_name_zh': await SdeUtils.get_cn_name_by_id(mineral_id),
                    'mineral_yield': {mineral_id: 1},  # 1份矿物产出1份自己
                    'volume': volume
                })
        
        return ore_data

    async def _get_initial_ore_price(self, type_id: int, purchase_mode: str = '扫单') -> Optional[float]:
        """
        获取初始价格（用于第一次迭代）
        使用最低价格或平均价格作为初始估计
        
        注意：返回的价格单位需要与约束条件中的数量单位一致
        - 冰矿和矿物：返回单份价格
        - 标准/卫星矿石：返回"100份"的总价格（单份价格 * 100）
        
        参数:
            type_id: 矿石类型ID或矿物ID
            purchase_mode: 采购模式，'扫单' 或 '收单'
        """
        # 收单模式：使用 buymax 价格
        if purchase_mode == '收单':
            from src_v2.model.EVE.market.market_manager import MarketManager
            buymax_price = await MarketManager().get_jita_buy_price(type_id)
            if buymax_price <= 0:
                return None
            
            # 根据类型处理价格
            if self._is_ice_ore(type_id) or self._is_mineral(type_id):
                # 冰矿和矿物：直接返回单份价格
                return float(buymax_price)
            else:
                # 标准/卫星矿石：返回"100份"的总价格
                return float(buymax_price * 100)
        
        # 扫单模式：使用原有逻辑
        # 判断是矿石还是矿物
        if self._is_mineral(type_id):
            await self._ensure_mineral_stats_ready()
            stats_dict = self._mineral_stats
        else:
            await self._ensure_asteroid_stats_ready()
            stats_dict = self._compressed_asteroid_stats
        
        if not stats_dict:
            return None
        
        type_stats = stats_dict.get(type_id)
        if not type_stats:
            return None
        
        # 使用最低价格作为初始估计
        if type_stats:
            base_price = float(type_stats[0][0])  # 第一个价格（最低价，单份价格）
            
            # 根据类型处理价格
            if self._is_ice_ore(type_id) or self._is_mineral(type_id):
                # 冰矿和矿物：直接返回单份价格
                return base_price
            else:
                # 标准/卫星矿石：返回"100份"的总价格
                # 因为约束条件中的数量是"100份"的单位，所以价格也应该是"100份"的总价格
                return base_price * 100
        
        return None

    async def optimize(
        self,
        mineral_requirements: dict,
        waste_penalty: float = 0.1,
        shortage_penalty: float = 2,
        max_iterations: int = 50,
        price_tolerance: float = 0.01,
        quantity_tolerance: float = 0.01,
        refinement_rate: float = 0.906,
        purchase_mode: str = '扫单',
        liquidity_impact: float = 0.0,
        purchase_time_limit: float = 7.0,
        shipping_cost_per_volume: float = 0.0,
    ):
        """
        使用 OR-Tools 进行优化，利用类中已有的数据和方法
        
        参数:
            mineral_requirements: 矿物需求字典 {mineral_id: required_quantity}
            waste_penalty: 浪费惩罚系数（默认0.1）
            shortage_penalty: 不足惩罚系数（默认2）
            max_iterations: 最大迭代次数（默认10）
            price_tolerance: 价格收敛阈值（默认0.01，即1%）
            refinement_rate: 化矿率（默认0.906），即矿石精炼产物最终需要乘这个系数并向下取整
            purchase_mode: 采购模式，'扫单' 或 '收单'（默认'扫单'）
        
        返回:
            优化结果字典，包含状态和解决方案
        """
        # 确保数据已初始化
        if self._type_material_data_dict is None:
            await self._init_type_material_data()
        
        # 保存化矿率
        self._refinement_rate = refinement_rate
        
        # 从类中已有的数据构建矿石数据
        ore_data = await self._build_ore_data_from_dict()
        if not ore_data:
            return {
                'status': 'Infeasible',
                'solution': None,
                'message': '没有可用的矿石数据'
            }
        
        # 过滤无效价格的矿石/矿物
        valid_ore_data = []
        invalid_items = []
        for ore in ore_data:
            type_id = ore['ore_id']
            initial_price = await self._get_initial_ore_price(type_id, purchase_mode)
            if initial_price is None or initial_price <= 0:
                invalid_items.append([type_id, ore['ore_name']])
                continue
            valid_ore_data.append(ore)
        
        if invalid_items:
            logger.warning(f"以下物品无法获得有效价格，已从求解中排除: {invalid_items}")
        
        ore_data = valid_ore_data
        if not ore_data:
            return {
                'status': 'Infeasible',
                'solution': None,
                'message': '没有可用的有效价格数据'
            }
        
        # 初始化价格
        # base_ore_prices：基础价格（收单=buymax，扫单=订单最低价 / 100份总价），不包含流动性溢价
        # ore_prices：本轮迭代中实际用于求解的价格（可能叠加了流动性溢价）
        base_ore_prices = {}
        ore_prices = {}
        for ore in ore_data:
            type_id = ore['ore_id']
            base_price = await self._get_initial_ore_price(type_id, purchase_mode)
            base_ore_prices[type_id] = base_price
            ore_prices[type_id] = base_price
        
        # 迭代优化：处理价格-数量循环依赖
        previous_prices = None
        previous_solution = None
        for iteration in range(max_iterations):
            # 创建求解器
            solver = pywraplp.Solver.CreateSolver('GLOP')
            if not solver:
                raise ValueError("无法创建求解器")
            
            # 决策变量：每种矿石的购买数量
            ore_vars = {}
            for ore in ore_data:
                ore_vars[ore['ore_id']] = solver.NumVar(
                    0, solver.infinity(),
                    f"ore_{ore['ore_id']}"
                )
            
            # 添加购买数量上限约束（仅扫单模式）
            if purchase_mode == '扫单':
                for ore in ore_data:
                    type_id = ore['ore_id']
                    total_available = await self._get_total_available_quantity(type_id)
                    if total_available > 0:
                        # 根据矿石类型处理单位（标准矿石需要转换为100份单位）
                        if self._is_ice_ore(type_id) or self._is_mineral(type_id):
                            upper_bound = total_available
                        else:
                            upper_bound = total_available / 100  # 转换为100份单位
                        ore_vars[type_id].SetUb(upper_bound)
            
            # 收集所有可能产出的矿物（包括不在需求列表中的）
            all_mineral_ids = set(mineral_requirements.keys())
            for ore in ore_data:
                all_mineral_ids.update(ore['mineral_yield'].keys())
            
            # 辅助变量：多余矿物（为所有可能的矿物创建）
            excess_vars = {}
            for mineral_id in all_mineral_ids:
                excess_vars[mineral_id] = solver.NumVar(
                    0, solver.infinity(),
                    f"excess_{mineral_id}"
                )
            
            # 辅助变量：不足矿物（为所有可能的矿物创建）
            shortage_vars = {}
            for mineral_id in all_mineral_ids:
                shortage_vars[mineral_id] = solver.NumVar(
                    0, solver.infinity(),
                    f"shortage_{mineral_id}"
                )
            
            # 约束：满足矿物需求（为所有可能的矿物创建约束）
            # 贡献数量 = floor(矿石数量 × 单位矿石贡献 × 化矿率)
            # 在线性规划中使用线性近似：矿石数量 × 单位矿石贡献 × 化矿率
            # 约束改为不等式：Σ(矿石贡献) - excess + shortage >= required_qty
            for mineral_id in all_mineral_ids:
                # 获取该矿物的需求（如果不在需求列表中，需求为0）
                required_qty = mineral_requirements.get(mineral_id, 0)
                
                constraint = solver.Constraint(
                    required_qty, required_qty  # 下界是 required_qty，上界是无穷大
                )
                
                # 添加矿石贡献（应用化矿率）
                for ore in ore_data:
                    yield_amount = ore['mineral_yield'].get(mineral_id, 0)
                    if yield_amount > 0:
                        ore_id = ore['ore_id']
                        # 如果是矿物（直接购买），化矿率为1；否则使用refinement_rate
                        if self._is_mineral(ore_id):
                            # 矿物：化矿率为1，贡献 = 购买数量 × 1
                            effective_yield = yield_amount  # yield_amount 为 1，所以 effective_yield = 1
                        else:
                            # 矿石：应用化矿率，贡献 = 矿石数量 × 单位矿石贡献 × 化矿率
                            effective_yield = yield_amount * refinement_rate
                        constraint.SetCoefficient(ore_vars[ore_id], effective_yield)
                
                # 减去多余量
                constraint.SetCoefficient(excess_vars[mineral_id], -1)
                # 加上不足量
                # constraint.SetCoefficient(shortage_vars[mineral_id], 1)
            
            # 目标函数
            objective = solver.Objective()
            
            # 成本部分：使用当前迭代的价格 + 运输成本
            for ore in ore_data:
                type_id = ore['ore_id']
                if type_id not in ore_prices:
                    logger.warning(f"矿石 {type_id} 没有价格，跳过")
                    continue
                
                # 基础价格系数
                cost_coefficient = ore_prices[type_id]
                
                # 添加运输成本（如果启用）
                if shipping_cost_per_volume > 0:
                    volume = ore.get('volume', 0.0)
                    if volume > 0:
                        # 注意：对于标准/卫星矿石，ore_vars[type_id] 的单位是"100份"
                        # 所以需要转换为真实份数来计算体积
                        if self._is_ice_ore(type_id) or self._is_mineral(type_id):
                            # 冰矿和矿物：数量是真实份数
                            shipping_cost_coefficient = volume * shipping_cost_per_volume
                        else:
                            # 标准/卫星矿石：数量是"100份"单位，需要乘以100得到真实份数
                            shipping_cost_coefficient = volume * shipping_cost_per_volume * 100.0
                        cost_coefficient += shipping_cost_coefficient
                
                objective.SetCoefficient(
                    ore_vars[type_id],
                    cost_coefficient
                )
            
            # 浪费惩罚部分（对所有可能的矿物都应用）
            for mineral_id in all_mineral_ids:
                mineral_price = self._get_mineral_price(mineral_id)
                objective.SetCoefficient(
                    excess_vars[mineral_id],
                    waste_penalty * mineral_price
                )
            
            # 不足惩罚部分（对所有可能的矿物都应用）
            # for mineral_id in all_mineral_ids:
            #     mineral_price = self._get_mineral_price(mineral_id)
            #     objective.SetCoefficient(
            #         shortage_vars[mineral_id],
            #         shortage_penalty * mineral_price
            #     )
            
            objective.SetMinimization()
            
            # 求解
            status = solver.Solve()
            
            if status != pywraplp.Solver.OPTIMAL:
                return await self._extract_results(
                    ore_vars,
                    excess_vars,
                    shortage_vars,
                    status,
                    solver,
                    ore_prices,
                    mineral_requirements,
                    refinement_rate,
                    base_ore_prices=base_ore_prices,
                    purchase_mode=purchase_mode,
                    liquidity_impact=liquidity_impact,
                )
            
            # 提取当前解
            current_solution = {
                ore_id: var.solution_value()
                for ore_id, var in ore_vars.items()
            }
            
            # 流动性检查：如果过去30天的平均交易量在指定天数内的总交易量无法满足对应矿石的需求时，在下一轮求解中剔除该矿石
            # 只在迭代次数 > 0 时进行剔除（第一轮迭代不剔除，因为需要先有解才能判断需求）
            ores_were_removed = False
            if iteration > 0:
                ores_to_remove = await self._check_liquidity_and_filter_ores(current_solution, ore_data, purchase_time_limit)
                if ores_to_remove:
                    # 从 ore_data 中移除这些矿石
                    ore_data = [ore for ore in ore_data if ore['ore_id'] not in ores_to_remove]
                    
                    # 从 ore_prices 和 base_ore_prices 中移除这些矿石的价格
                    for ore_id in ores_to_remove:
                        ore_prices.pop(ore_id, None)
                        base_ore_prices.pop(ore_id, None)
                    
                    logger.info(
                        f"第 {iteration + 1} 轮迭代：已剔除 {len(ores_to_remove)} 个流动性不足的矿石: {ores_to_remove}, ore_data剩余数量: {len(ore_data)}"
                    )
                    
                    # 如果所有矿石都被剔除了，返回不可行解
                    if not ore_data:
                        return {
                            'status': 'Infeasible',
                            'solution': None,
                            'message': '所有矿石因流动性不足被剔除'
                        }
                    
                    # 标记有矿石被剔除，需要继续迭代重新求解
                    ores_were_removed = True
            
            # 对矿石购买数量进行取整处理（用于价格查询）
            # 只对冰矿取整，标准/卫星矿石保持原样，因为约束条件中的数量应该保持原样
            rounded_solution_for_price = {}
            for type_id, quantity in current_solution.items():
                if quantity > 0:
                    rounded_solution_for_price[type_id] = self._round_ore_quantity_for_iteration(type_id, quantity)
                else:
                    rounded_solution_for_price[type_id] = 0.0
            
            # 根据取整后的解更新价格
            # 对于标准/卫星矿石，需要查询购买100份的价格（因为约束条件中的数量是"100份"的单位）
            # 这里用当前的 ore_prices 作为基础拷贝，避免丢失已有的价格键，从而保证
            # ore_data 中出现的 type_id 在后续使用 ore_prices 时一定存在，避免 KeyError
            new_prices = ore_prices.copy()
            price_changed = False
            for type_id, quantity in rounded_solution_for_price.items():
                # 如果矿石已被剔除，跳过价格更新
                if type_id not in ore_prices:
                    continue
                if quantity > 0:
                    if purchase_mode == '收单':
                        # 收单模式：
                        # - 若 liquidity_impact == 0，则价格始终等于基础 buymax 价格（不做回归）
                        # - 若 liquidity_impact > 0，则根据购买数量 Q 叠加流动性溢价，参与迭代回归
                        base_price = base_ore_prices.get(type_id)
                        if base_price is None or base_price <= 0:
                            new_price = None
                        elif liquidity_impact <= 0:
                            # 无流动性溢价：始终使用 buymax
                            new_price = base_price
                        else:
                            # 带流动性溢价：先换算为单份基础价格，再根据数量计算 multiplier
                            if self._is_ice_ore(type_id) or self._is_mineral(type_id):
                                base_unit_price = base_price
                                # 冰矿/矿物：quantity 已经是真实份数
                                Q = quantity
                            else:
                                # 标准/卫星矿石：base_price 是 100 份总价，换算为单份基础价格
                                base_unit_price = base_price / 100.0
                                # 约束中数量是“100份”单位，真实份数需要乘以 100
                                Q = quantity * 100.0

                            multiplier = await self._get_liquidity_multiplier(
                                type_id=int(type_id),
                                quantity=float(Q),
                                liquidity_impact=float(liquidity_impact),
                            )
                            effective_unit_price = base_unit_price * multiplier

                            if self._is_ice_ore(type_id) or self._is_mineral(type_id):
                                # 冰矿和矿物：价格是单份价格
                                new_price = effective_unit_price
                            else:
                                # 标准/卫星矿石：价格是“100份”的总价格
                                new_price = effective_unit_price * 100.0
                    else:
                        # 扫单模式：根据数量和订单计算价格
                        if self._is_ice_ore(type_id) or self._is_mineral(type_id):
                            # 冰矿和矿物：查询价格时使用取整后的数量（已经是真实份数）
                            new_price = await self._get_asteroid_price_by_need(type_id, quantity)
                        else:
                            # 标准/卫星矿石：查询价格时需要使用真实份数（quantity * 100）
                            # 因为约束条件中的数量是"100份"的单位，但价格查询需要真实份数
                            real_quantity = quantity * 100
                            price_per_unit = await self._get_asteroid_price_by_need(type_id, real_quantity)
                            if price_per_unit is None:
                                new_price = None
                            else:
                                # 价格返回的是购买real_quantity份的平均单价（每份的价格）
                                # 我们需要的是"100份"的总价格，所以应该是：单价 * 100
                                new_price = price_per_unit * 100
                    
                    if new_price is None or new_price <= 0:
                        # 如果无法获得有效价格，则保留上一轮的价格，不更新
                        # 这样可以避免在下一轮中 ore_prices 丢失该 type_id，导致后续访问时报错
                        continue

                    # 记录新的价格
                    new_prices[type_id] = new_price
                    
                    # 检查价格是否变化（收单模式下价格固定，不需要检查变化）
                    # 记录价格变化幅度（用于扫单模式的价格收敛判定，收单模式单独处理）
                    old_price = ore_prices.get(type_id, 0)
                    if old_price > 0:
                        price_change = abs(new_price - old_price) / old_price
                        if price_change > price_tolerance:
                            price_changed = True

            # 收敛判定
            if purchase_mode == '扫单':
                # 扫单模式：保持原有价格收敛规则
                # 如果有矿石被剔除，必须继续迭代重新求解，不能提前退出
                if not price_changed and previous_prices is not None and not ores_were_removed:
                    result = await self._extract_results(
                        ore_vars,
                        excess_vars,
                        shortage_vars,
                        status,
                        solver,
                        new_prices,
                        mineral_requirements,
                        refinement_rate,
                        base_ore_prices=base_ore_prices,
                        purchase_mode=purchase_mode,
                        liquidity_impact=liquidity_impact,
                    )
                    return result
            else:
                # 收单模式
                if liquidity_impact <= 0:
                    # 无流动性溢价：价格固定为 buymax
                    # 如果有矿石被剔除，必须继续迭代重新求解，不能提前退出
                    if not ores_were_removed:
                        result = await self._extract_results(
                            ore_vars,
                            excess_vars,
                            shortage_vars,
                            status,
                            solver,
                            new_prices,
                            mineral_requirements,
                            refinement_rate,
                            base_ore_prices=base_ore_prices,
                            purchase_mode=purchase_mode,
                            liquidity_impact=liquidity_impact,
                        )
                        return result
                else:
                    # 带流动性溢价：价格和数量都需要迭代回归
                    quantity_changed = False
                    if previous_solution is not None:
                        for ore_id, qty in current_solution.items():
                            prev_qty = previous_solution.get(ore_id, 0.0)
                            if prev_qty <= 0 and qty <= 0:
                                continue
                            denom = max(abs(prev_qty), 1e-6)
                            delta = abs(qty - prev_qty) / denom
                            if delta > quantity_tolerance:
                                quantity_changed = True
                                break

                    # 如果有矿石被剔除，必须继续迭代重新求解，不能提前退出
                    if (not price_changed) and (not quantity_changed) and previous_solution is not None and not ores_were_removed:
                        result = await self._extract_results(
                            ore_vars,
                            excess_vars,
                            shortage_vars,
                            status,
                            solver,
                            new_prices,
                            mineral_requirements,
                            refinement_rate,
                            base_ore_prices=base_ore_prices,
                            purchase_mode=purchase_mode,
                            liquidity_impact=liquidity_impact,
                        )
                        return result

            # 更新价格和解用于下一次迭代
            previous_prices = ore_prices.copy()
            ore_prices = new_prices
            previous_solution = current_solution
        
        # 达到最大迭代次数，返回最后一次的结果
        result = await self._extract_results(
            ore_vars,
            excess_vars,
            shortage_vars,
            status,
            solver,
            ore_prices,
            mineral_requirements,
            refinement_rate,
            base_ore_prices=base_ore_prices,
            purchase_mode=purchase_mode,
            liquidity_impact=liquidity_impact,
        )
        return result

    async def _apply_liquidity_premium(self, result: dict, liquidity_impact: float) -> dict:
        """
        在收单模式下，根据近30天Jita日均成交量为每种物品叠加流动性溢价。

        算法：
        - Q: 本次计划购买数量（单位：件）
        - v̄: 近30天日均成交量 (total_volume_30d / 30)
        - r = Q / (v̄ + eps)
        - impact_raw = log(1 + r)
        - impact = min(impact_raw, impact_max)
        - multiplier = 1 + liquidity_impact * impact
        - unit_price_new = unit_price * multiplier
        """
        if not result or result.get('status') != 'Optimal':
            return result

        try:
            solution = result.get('solution') or {}
            ore_purchases = solution.get('ore_purchases') or {}
            direct_mineral_purchases = solution.get('direct_mineral_purchases') or {}
            ore_price_details = solution.get('ore_price_details') or {}
            mineral_price_details = solution.get('mineral_price_details') or {}

            # 参数
            eps = 1e-6
            impact_max = 3.0

            total_cost = 0.0

            # 处理矿石和冰矿（通过 ore_purchases 购买的部分）
            for type_id, quantity in ore_purchases.items():
                if quantity <= 0:
                    continue
                price_info = ore_price_details.get(type_id)
                if not price_info:
                    continue

                # 获取30天历史成交量
                history = await MarketManager().get_type_id_history_detail(REGION_FORGE_ID, int(type_id))
                total_volume_30d = history.get('total_volume_30d', 0.0) if isinstance(history, dict) else 0.0
                if total_volume_30d <= 0:
                    # 无历史数据，沿用原价
                    total_cost += float(price_info.get('total_price', 0.0))
                    continue

                v_bar = total_volume_30d / 30.0
                r = float(quantity) / (v_bar + eps)
                impact_raw = math.log1p(r)
                impact = min(impact_raw, impact_max)
                multiplier = 1.0 + liquidity_impact * impact

                # 记录基准价格和溢价信息，便于前端展示
                base_unit_price = float(price_info.get('base_unit_price', price_info.get('unit_price', 0.0)))
                unit_price = float(price_info.get('unit_price', 0.0))
                new_unit_price = unit_price * multiplier
                new_total_price = new_unit_price * float(quantity)
                price_info['base_unit_price'] = float(base_unit_price)
                price_info['liquidity_multiplier'] = float(multiplier)
                price_info['liquidity_impact'] = float(liquidity_impact)
                price_info['liquidity_premium_rate'] = float(multiplier - 1.0)
                price_info['unit_price'] = float(new_unit_price)
                price_info['total_price'] = float(new_total_price)
                total_cost += new_total_price

            # 处理直接购买的矿物
            for type_id, quantity in direct_mineral_purchases.items():
                if quantity <= 0:
                    continue
                price_info = mineral_price_details.get(type_id)
                if not price_info:
                    continue

                history = await MarketManager().get_type_id_history_detail(REGION_FORGE_ID, int(type_id))
                total_volume_30d = history.get('total_volume_30d', 0.0) if isinstance(history, dict) else 0.0
                if total_volume_30d <= 0:
                    total_cost += float(price_info.get('total_price', 0.0))
                    continue

                v_bar = total_volume_30d / 30.0
                r = float(quantity) / (v_bar + eps)
                impact_raw = math.log1p(r)
                impact = min(impact_raw, impact_max)
                multiplier = 1.0 + liquidity_impact * impact

                # 记录基准价格和溢价信息，便于前端展示
                base_unit_price = float(price_info.get('base_unit_price', price_info.get('unit_price', 0.0)))
                unit_price = float(price_info.get('unit_price', 0.0))
                new_unit_price = unit_price * multiplier
                new_total_price = new_unit_price * float(quantity)
                price_info['base_unit_price'] = float(base_unit_price)
                price_info['liquidity_multiplier'] = float(multiplier)
                price_info['liquidity_impact'] = float(liquidity_impact)
                price_info['liquidity_premium_rate'] = float(multiplier - 1.0)
                price_info['unit_price'] = float(new_unit_price)
                price_info['total_price'] = float(new_total_price)
                total_cost += new_total_price

            # 更新总成本
            solution['total_cost'] = float(total_cost)
            # 记录参数，便于前端调试
            solution['liquidity_impact'] = float(liquidity_impact)
        except Exception as e:
            logger.error(f"应用收单流动性溢价失败: {e}", exc_info=True)

        return result
    
    async def _get_liquidity_multiplier(self, type_id: int, quantity: float, liquidity_impact: float) -> float:
        """
        根据近30天成交量和本次计划购买数量计算流动性溢价乘数。
        返回值 multiplier 满足 multiplier >= 1.0。
        """
        if liquidity_impact <= 0 or quantity <= 0:
            return 1.0

        try:
            history = await MarketManager().get_type_id_history_detail(REGION_FORGE_ID, int(type_id))
            total_volume_30d = history.get('total_volume_30d', 0.0) if isinstance(history, dict) else 0.0
            if total_volume_30d <= 0:
                return 1.0

            eps = 1e-6
            impact_max = 3.0

            v_bar = total_volume_30d / 30.0
            r = float(quantity) / (v_bar + eps)
            impact_raw = math.log1p(r)
            impact = min(impact_raw, impact_max)
            multiplier = 1.0 + float(liquidity_impact) * impact
            if multiplier < 1.0:
                multiplier = 1.0
            return float(multiplier)
        except Exception as e:
            logger.error(
                f"计算流动性溢价乘数失败: type_id={type_id}, quantity={quantity}, "
                f"liquidity_impact={liquidity_impact}, error={e}",
                exc_info=True,
            )
            return 1.0

    async def _check_liquidity_and_filter_ores(
        self,
        current_solution: dict,
        ore_data: List[dict],
        purchase_time_limit: float = 7.0
    ) -> List[int]:
        """
        检查矿石流动性，返回需要剔除的矿石ID列表。
        
        如果矿石的需求数量超过了基于30天平均交易量计算的指定天数内的预期交易量，则标记为需要剔除。
        
        参数:
            current_solution: 当前解，包含每种矿石的购买数量 {ore_id: quantity}
            ore_data: 矿石数据列表，包含矿石信息
            purchase_time_limit: 采购时间上限（天），用于计算预期交易量，默认7天
            
        返回:
            需要剔除的矿石ID列表
        """
        ores_to_remove = []
        
        for ore in ore_data:
            type_id = ore['ore_id']
            quantity = current_solution.get(type_id, 0.0)
            
            # 如果矿石需求数量为0，跳过检查
            if quantity <= 0:
                continue
            
            try:
                # 获取历史交易量数据
                history = await MarketManager().get_type_id_history_detail(REGION_FORGE_ID, int(type_id))
                total_volume_30d = history.get('total_volume_30d', 0.0) if isinstance(history, dict) else 0.0
                
                # 如果历史交易量数据不存在，则不剔除该矿石（保留原有行为）
                # if total_volume_30d <= 0:
                #     continue
                
                # 计算30天平均交易量
                avg_volume_30d = total_volume_30d / 30.0
                
                # 计算基于30天平均的指定天数内的预期交易量
                expected_volume = avg_volume_30d * float(purchase_time_limit)
                
                # 获取矿石需求数量（需要转换为真实份数）
                # 标准/卫星矿石：current_solution 中的数量是"100份"单位，需要转换为真实份数（乘以100）
                # 冰矿/矿物：current_solution 中的数量已经是真实份数
                if self._is_ice_ore(type_id) or self._is_mineral(type_id):
                    # 冰矿和矿物：数量已经是真实份数
                    real_quantity = quantity
                else:
                    # 标准/卫星矿石：数量是"100份"单位，需要乘以100得到真实份数
                    real_quantity = quantity * 100.0
                
                # 如果预期交易量无法满足矿石需求，则标记为需要剔除
                if expected_volume < real_quantity:
                    ores_to_remove.append(type_id)
                    logger.warning(
                        f"矿石 {type_id} ({ore.get('ore_name', 'Unknown')}) 流动性不足，将在下一轮求解中剔除。"
                        f"需求数量: {real_quantity:.2f}, 预期{purchase_time_limit}天交易量: {expected_volume:.2f} "
                        f"(30天平均: {avg_volume_30d:.2f}/天)"
                    )
                    
            except Exception as e:
                logger.error(
                    f"检查矿石流动性失败: type_id={type_id}, error={e}",
                    exc_info=True,
                )
                # 发生错误时不剔除，保留原有行为
                continue
        
        return ores_to_remove

    
    async def _extract_results(self, ore_vars, excess_vars, shortage_vars, status, solver, ore_prices=None, mineral_requirements=None, refinement_rate=0.906, base_ore_prices=None, purchase_mode: str = '扫单', liquidity_impact: float = 0.0):
        """提取结果，对矿石购买数量进行取整处理，并重新计算多余矿物和不足矿物"""
        if status != pywraplp.Solver.OPTIMAL:
            status_names = {
                pywraplp.Solver.OPTIMAL: 'Optimal',
                pywraplp.Solver.FEASIBLE: 'Feasible',
                pywraplp.Solver.INFEASIBLE: 'Infeasible',
                pywraplp.Solver.UNBOUNDED: 'Unbounded'
            }
            return {
                'status': status_names.get(status, 'Unknown'),
                'solution': None
            }
        
        # 提取原始解
        raw_ore_purchases = {
            ore_id: var.solution_value()
            for ore_id, var in ore_vars.items()
        }
        
        # 对矿石和矿物购买数量进行取整处理（最终结果）
        # 标准/卫星矿石的数量要乘以100，得到真实的份数
        rounded_ore_purchases = {}  # 矿石购买
        direct_mineral_purchases = {}  # 直接购买的矿物
        ore_price_details = {}  # 记录每种矿石的单价和总价
        mineral_price_details = {}  # 记录每种直接购买矿物的单价和总价
        total_cost = 0.0
        
        for ore_id, quantity in raw_ore_purchases.items():
            if quantity > 0:
                # 如果矿石不在 ore_prices 中，说明它已经被剔除了（例如流动性不足），应该跳过
                # 必须在添加到结果之前检查，避免将已剔除的矿石加入最终结果
                if not ore_prices or ore_id not in ore_prices:
                    # 矿石已被剔除，跳过处理
                    continue
                
                # 最终结果：标准/卫星矿石的数量要乘以100
                rounded_quantity = self._round_ore_quantity(ore_id, quantity)
                
                # 区分矿石和矿物
                if self._is_mineral(ore_id):
                    # 直接购买的矿物
                    direct_mineral_purchases[ore_id] = rounded_quantity
                else:
                    # 矿石
                    rounded_ore_purchases[ore_id] = rounded_quantity
                
                # 计算取整后的成本和单价
                # 注意：ore_prices 中的价格已经是用于求解的“最终价格”
                # - 标准/卫星矿石：价格是“100份”的总价，单价需要除以 100
                # - 冰矿和矿物：价格是单份价格
                if ore_prices and ore_id in ore_prices:
                    if self._is_ice_ore(ore_id) or self._is_mineral(ore_id):
                        # 冰矿和矿物：价格是单份价格，数量是真实份数
                        unit_price = ore_prices[ore_id]  # 单份价格
                        total_price = rounded_quantity * unit_price
                        total_cost += total_price
                        
                        # 记录单价、总价和基础价格（若有）
                        base_unit_price = None
                        if purchase_mode == '收单' and base_ore_prices and ore_id in base_ore_prices:
                            # 收单模式：使用基础价格（buymax价格）
                            base_unit_price = float(base_ore_prices[ore_id])
                        else:
                            # 扫单模式：基础价格等于当前单价（没有流动性溢价）
                            base_unit_price = float(unit_price)
                        if self._is_mineral(ore_id):
                            mineral_price_details[ore_id] = {
                                'unit_price': float(unit_price),
                                'total_price': float(total_price),
                                'quantity': float(rounded_quantity),
                                'base_unit_price': base_unit_price,
                            }
                            if purchase_mode == '收单' and base_unit_price > 0:
                                multiplier = float(unit_price) / base_unit_price
                                mineral_price_details[ore_id]['liquidity_multiplier'] = float(multiplier)
                                mineral_price_details[ore_id]['liquidity_impact'] = float(liquidity_impact)
                                mineral_price_details[ore_id]['liquidity_premium_rate'] = float(multiplier - 1.0)
                        else:
                            ore_price_details[ore_id] = {
                                'unit_price': float(unit_price),
                                'total_price': float(total_price),
                                'quantity': float(rounded_quantity),
                                'base_unit_price': base_unit_price,
                            }
                            if purchase_mode == '收单' and base_unit_price > 0:
                                multiplier = float(unit_price) / base_unit_price
                                ore_price_details[ore_id]['liquidity_multiplier'] = float(multiplier)
                                ore_price_details[ore_id]['liquidity_impact'] = float(liquidity_impact)
                                ore_price_details[ore_id]['liquidity_premium_rate'] = float(multiplier - 1.0)
                    else:
                        # 标准/卫星矿石：价格是“100份”总价，数量是真实份数（已乘以100）
                        # 单价 = 价格 / 100（转换为单份价格）
                        # 成本 = 真实份数 * 单份价格 = 数量 * (价格/100)
                        final_price_100 = ore_prices[ore_id]
                        unit_price = final_price_100 / 100.0  # 转换为单份价格
                        total_price = rounded_quantity * unit_price
                        total_cost += total_price
                        
                        # 记录单价、总价和基础价格（若有）
                        base_unit_price = None
                        if purchase_mode == '收单' and base_ore_prices and ore_id in base_ore_prices:
                            # 收单模式：使用基础价格（buymax价格）
                            base_unit_price = float(base_ore_prices[ore_id]) / 100.0
                        else:
                            # 扫单模式：基础价格等于当前单价（没有流动性溢价）
                            base_unit_price = float(unit_price)
                        ore_price_details[ore_id] = {
                            'unit_price': float(unit_price),
                            'total_price': float(total_price),
                            'quantity': float(rounded_quantity),
                            'base_unit_price': base_unit_price,
                        }
                        if purchase_mode == '收单' and base_unit_price > 0:
                            multiplier = float(unit_price) / base_unit_price
                            ore_price_details[ore_id]['liquidity_multiplier'] = float(multiplier)
                            ore_price_details[ore_id]['liquidity_impact'] = float(liquidity_impact)
                            ore_price_details[ore_id]['liquidity_premium_rate'] = float(multiplier - 1.0)
                else:
                    # 如果没有价格信息，尝试使用原始解的平均价格（不准确，但作为后备）
                    # 这种情况理论上不应该发生，因为 optimize() 方法总是传递价格
                    avg_price = solver.Objective().Value() / sum(raw_ore_purchases.values()) if sum(raw_ore_purchases.values()) > 0 else 0
                    if self._is_ice_ore(ore_id) or self._is_mineral(ore_id):
                        unit_price = avg_price
                        total_price = rounded_quantity * unit_price
                        total_cost += total_price
                        
                        # 记录单价和总价（使用估算价格）
                        # 后备情况下，base_unit_price 等于 unit_price
                        base_unit_price = float(unit_price)
                        if self._is_mineral(ore_id):
                            mineral_price_details[ore_id] = {
                                'unit_price': float(unit_price),
                                'total_price': float(total_price),
                                'quantity': float(rounded_quantity),
                                'base_unit_price': base_unit_price,
                            }
                        else:
                            ore_price_details[ore_id] = {
                                'unit_price': float(unit_price),
                                'total_price': float(total_price),
                                'quantity': float(rounded_quantity),
                                'base_unit_price': base_unit_price,
                            }
                    else:
                        # 对于标准/卫星矿石，平均价格也是“100份”总价，需要除以100
                        unit_price = avg_price / 100.0
                        total_price = rounded_quantity * unit_price
                        total_cost += total_price
                        
                        # 记录单价和总价（使用估算价格）
                        # 后备情况下，base_unit_price 等于 unit_price
                        base_unit_price = float(unit_price)
                        ore_price_details[ore_id] = {
                            'unit_price': float(unit_price),
                            'total_price': float(total_price),
                            'quantity': float(rounded_quantity),
                            'base_unit_price': base_unit_price,
                        }
            # else:
            #     rounded_ore_purchases[ore_id] = 0.0
        
        # 如果没有价格信息且 total_cost 为 0，使用原始目标函数值作为后备
        if not ore_prices and total_cost == 0.0:
            total_cost = solver.Objective().Value()
        
        # 重新计算所有矿物的实际产出和多余产出（基于取整后的矿石数量和直接购买的矿物）
        # 贡献数量 = floor(矿石数量 × 单位矿石贡献 × 化矿率)
        # 直接购买的矿物：贡献 = 购买数量 × 1（化矿率1）
        actual_mineral_yields = {}  # 所有矿物的实际产出
        excess_minerals = {}  # 多余矿物
        
        # 首先累加直接购买的矿物（化矿率1，不需要向下取整）
        for mineral_id, quantity in direct_mineral_purchases.items():
            actual_mineral_yields[mineral_id] = actual_mineral_yields.get(mineral_id, 0) + quantity
        
        if self._type_material_data_dict:
            # 遍历所有购买的矿石，计算每种矿物的实际产出
            for ore_id, rounded_quantity in rounded_ore_purchases.items():
                if rounded_quantity > 0:
                    # 获取该矿石产出的所有矿物
                    mineral_yields = self._type_material_data_dict.get(ore_id, {})
                    
                    for mineral_id, mineral_yield in mineral_yields.items():
                        if mineral_yield > 0:
                            # 对于标准/卫星矿石，rounded_quantity 是真实份数（已乘以100）
                            # 但 mineral_yield 是基于100份的产出，所以需要除以100
                            if self._is_ice_ore(ore_id):
                                # 冰矿：mineral_yield 是基于1份的产出
                                # 贡献 = floor(真实份数 × 单位产出 × 化矿率)
                                contribution = rounded_quantity * mineral_yield * refinement_rate
                            else:
                                # 标准/卫星矿石：mineral_yield 是基于100份的产出
                                # 贡献 = floor(真实份数 × (单位产出/100) × 化矿率)
                                contribution = rounded_quantity * (mineral_yield / 100) * refinement_rate
                            
                            # 向下取整并累加
                            actual_yield = math.floor(contribution)
                            actual_mineral_yields[mineral_id] = actual_mineral_yields.get(mineral_id, 0) + actual_yield
            
            # 计算多余矿物
            if mineral_requirements:
                # 对于需求列表中的矿物：多余产出 = 实际产出 - 需求
                for mineral_id, required_qty in mineral_requirements.items():
                    actual_yield = actual_mineral_yields.get(mineral_id, 0)
                    excess = max(0.0, actual_yield - required_qty)
                    excess_minerals[mineral_id] = float(excess)
                
                # 对于不在需求列表中的矿物：实际产出就是多余产出
                for mineral_id, actual_yield in actual_mineral_yields.items():
                    if mineral_id not in mineral_requirements:
                        excess_minerals[mineral_id] = float(actual_yield)
            else:
                # 如果没有需求信息，所有实际产出都是多余产出
                excess_minerals = {mineral_id: float(yield_qty) for mineral_id, yield_qty in actual_mineral_yields.items()}
        else:
            # 如果没有矿石数据，使用求解器的原始解（不准确，但作为后备）
            excess_minerals = {
                mineral_id: var.solution_value()
                for mineral_id, var in excess_vars.items()
            }
        
        # 提取不足矿物（从求解器获取）
        shortage_minerals = {}
        if shortage_vars:
            for mineral_id, var in shortage_vars.items():
                shortage_value = var.solution_value()
                if shortage_value > 0:
                    shortage_minerals[mineral_id] = float(shortage_value)
        
        solution = {
            'ore_purchases': rounded_ore_purchases,  # 矿石购买（通过精炼获得矿物）
            'ore_price_details': ore_price_details,  # 每种矿石的单价和总价
            'direct_mineral_purchases': direct_mineral_purchases,  # 直接购买的矿物
            'mineral_price_details': mineral_price_details,  # 每种直接购买矿物的单价和总价
            'excess_minerals': excess_minerals,  # 重新计算的多余矿物
            'shortage_minerals': shortage_minerals,  # 不足矿物
            'total_cost': total_cost
        }
        
        return {
            'status': 'Optimal',
            'solution': solution
        }