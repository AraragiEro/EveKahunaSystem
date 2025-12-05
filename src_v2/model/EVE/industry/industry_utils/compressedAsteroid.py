import math
from rapidfuzz.process import cpdist
from ortools.linear_solver import pywraplp
from typing import List, Optional

from src_v2.model.EVE.sde.utils import SdeUtils
from src_v2.core.database.connect_manager import redis_manager as rdm
from src_v2.model.EVE.market.market_manager import MarketManager, JITA_TRADE_HUB_STRUCTURE_ID, REGION_FORGE_ID
from src_v2.core.database.kahuna_database_utils_v2 import EveMarketRegionOrdersDBUtils

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

    async def _get_asteroid_price_by_need(self, type_id: int, need_quantity: float):
        """
        根据需求数量 need_quantity，计算购买该数量压缩矿石的平均单价。

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

        await self._ensure_asteroid_stats_ready()

        if not self._compressed_asteroid_stats:
            return None

        type_stats = self._compressed_asteroid_stats.get(type_id)
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

        # 若需求数量超过所有订单总和，返回惩罚性单价以否决该方案
        last_price, last_qty, last_quantity_sum_lower, last_avg_price_lower = type_stats[-1]
        total_qty = last_quantity_sum_lower + last_qty
        if total_qty <= 0:
            return 100000000.0

        # 需求超出总量，返回惩罚性单价
        return 100000000.0

    def _get_mineral_price(self, mineral_id: int) -> float:
        return self._material_price_dict.get(mineral_id, 0.0)
    
    def _is_ice_ore(self, type_id: int) -> bool:
        """判断是否为冰矿"""
        if self._ice_ore_ids is None:
            return False
        return type_id in self._ice_ore_ids
    
    def _round_ore_quantity_for_iteration(self, type_id: int, quantity: float) -> float:
        """根据矿石类型向上取整（用于迭代过程中的价格查询）
        
        在迭代过程中使用，只对冰矿取整，标准/卫星矿石保持原样
        因为约束条件中的数量应该保持原样，但价格需要乘以100
        
        Args:
            type_id: 矿石类型ID
            quantity: 原始数量
            
        Returns:
            取整后的数量（用于价格查询）
            - 冰矿：向上取整到1
            - 标准矿石和卫星矿石：保持原样（不乘以100）
        """
        if self._is_ice_ore(type_id):
            # 冰矿：向上取整到1
            return math.ceil(quantity)
        else:
            # 标准矿石和卫星矿石：保持原样，不乘以100
            return quantity
    
    def _round_ore_quantity(self, type_id: int, quantity: float) -> float:
        """根据矿石类型向上取整（用于最终结果）
        
        Args:
            type_id: 矿石类型ID
            quantity: 原始数量
            
        Returns:
            取整后的数量
            - 冰矿：向上取整到1
            - 标准矿石和卫星矿石：向上取整到100（math.ceil(quantity) * 100）
        """
        if self._is_ice_ore(type_id):
            # 冰矿：向上取整到1
            return math.ceil(quantity)
        else:
            # 标准矿石和卫星矿石：向上取整到100
            return math.ceil(quantity) * 100

    def _build_ore_data_from_dict(self):
        """
        从 _type_material_data_dict 构建矿石数据列表
        返回格式: [{'ore_id': type_id, 'mineral_yield': {mineral_id: quantity}}, ...]
        """
        if not self._type_material_data_dict:
            return []
        
        ore_data = []
        for type_id, mineral_yield in self._type_material_data_dict.items():
            ore_data.append({
                'ore_id': type_id,
                'mineral_yield': mineral_yield
            })
        return ore_data

    async def _get_initial_ore_price(self, type_id: int, purchase_mode: str = '扫单') -> float:
        """
        获取初始价格（用于第一次迭代）
        使用最低价格或平均价格作为初始估计
        
        注意：返回的价格单位需要与约束条件中的数量单位一致
        - 冰矿：返回单份价格
        - 标准/卫星矿石：返回"100份"的总价格（单份价格 * 100）
        
        参数:
            type_id: 矿石类型ID
            purchase_mode: 采购模式，'扫单' 或 '收单'
        """
        # 收单模式：使用 buymax 价格
        if purchase_mode == '收单':
            from src_v2.model.EVE.market.market_manager import MarketManager
            buymax_price = await MarketManager().get_jita_buy_price(type_id)
            if buymax_price <= 0:
                return 100000000.0  # 惩罚性价格
            
            # 根据矿石类型处理价格
            if self._is_ice_ore(type_id):
                # 冰矿：直接返回单份价格
                return float(buymax_price)
            else:
                # 标准/卫星矿石：返回"100份"的总价格
                return float(buymax_price * 100)
        
        # 扫单模式：使用原有逻辑
        await self._ensure_asteroid_stats_ready()
        
        if not self._compressed_asteroid_stats:
            return 100000000.0  # 惩罚性价格
        
        type_stats = self._compressed_asteroid_stats.get(type_id)
        if not type_stats:
            return 100000000.0
        
        # 使用最低价格作为初始估计
        if type_stats:
            base_price = float(type_stats[0][0])  # 第一个价格（最低价，单份价格）
            
            # 根据矿石类型处理价格
            if self._is_ice_ore(type_id):
                # 冰矿：直接返回单份价格
                return base_price
            else:
                # 标准/卫星矿石：返回"100份"的总价格
                # 因为约束条件中的数量是"100份"的单位，所以价格也应该是"100份"的总价格
                return base_price * 100
        
        return 100000000.0

    async def optimize(
        self,
        mineral_requirements: dict,
        waste_penalty: float = 0.1,
        max_iterations: int = 10,
        price_tolerance: float = 0.01,
        refinement_rate: float = 0.906,
        purchase_mode: str = '扫单'
    ):
        """
        使用 OR-Tools 进行优化，利用类中已有的数据和方法
        
        参数:
            mineral_requirements: 矿物需求字典 {mineral_id: required_quantity}
            waste_penalty: 浪费惩罚系数（默认0.1）
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
        ore_data = self._build_ore_data_from_dict()
        if not ore_data:
            return {
                'status': 'Infeasible',
                'solution': None,
                'message': '没有可用的矿石数据'
            }
        
        # 初始化价格：使用最低价格作为初始估计
        ore_prices = {}
        for ore in ore_data:
            type_id = ore['ore_id']
            ore_prices[type_id] = await self._get_initial_ore_price(type_id, purchase_mode)
        
        # 迭代优化：处理价格-数量循环依赖
        previous_prices = None
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
            
            # 约束：满足矿物需求（为所有可能的矿物创建约束）
            # 贡献数量 = floor(矿石数量 × 单位矿石贡献 × 化矿率)
            # 在线性规划中使用线性近似：矿石数量 × 单位矿石贡献 × 化矿率
            for mineral_id in all_mineral_ids:
                # 获取该矿物的需求（如果不在需求列表中，需求为0）
                required_qty = mineral_requirements.get(mineral_id, 0)
                
                constraint = solver.Constraint(
                    required_qty, required_qty  # 下界和上界都是 required_qty
                )
                
                # 添加矿石贡献（应用化矿率）
                for ore in ore_data:
                    yield_amount = ore['mineral_yield'].get(mineral_id, 0)
                    if yield_amount > 0:
                        # 应用化矿率：贡献 = 矿石数量 × 单位矿石贡献 × 化矿率
                        effective_yield = yield_amount * refinement_rate
                        constraint.SetCoefficient(ore_vars[ore['ore_id']], effective_yield)
                
                # 减去多余量
                constraint.SetCoefficient(excess_vars[mineral_id], -1)
            
            # 目标函数
            objective = solver.Objective()
            
            # 成本部分：使用当前迭代的价格
            for ore in ore_data:
                type_id = ore['ore_id']
                objective.SetCoefficient(
                    ore_vars[type_id],
                    ore_prices[type_id]
                )
            
            # 浪费惩罚部分（对所有可能的矿物都应用）
            for mineral_id in all_mineral_ids:
                mineral_price = self._get_mineral_price(mineral_id)
                objective.SetCoefficient(
                    excess_vars[mineral_id],
                    waste_penalty * mineral_price
                )
            
            objective.SetMinimization()
            
            # 求解
            status = solver.Solve()
            
            if status != pywraplp.Solver.OPTIMAL:
                return await self._extract_results(ore_vars, excess_vars, status, solver, ore_prices, mineral_requirements, refinement_rate)
            
            # 提取当前解
            current_solution = {
                ore_id: var.solution_value()
                for ore_id, var in ore_vars.items()
            }
            
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
            new_prices = {}
            price_changed = False
            for type_id, quantity in rounded_solution_for_price.items():
                if quantity > 0:
                    # 收单模式：使用 buymax 价格
                    if purchase_mode == '收单':
                        from src_v2.model.EVE.market.market_manager import MarketManager
                        buymax_price = await MarketManager().get_jita_buy_price(type_id)
                        if buymax_price <= 0:
                            new_price = 100000000.0  # 惩罚性价格
                        else:
                            if self._is_ice_ore(type_id):
                                # 冰矿：直接使用单份价格
                                new_price = float(buymax_price)
                            else:
                                # 标准/卫星矿石：返回"100份"的总价格
                                new_price = float(buymax_price * 100)
                    else:
                        # 扫单模式：根据数量和订单计算价格
                        if self._is_ice_ore(type_id):
                            # 冰矿：查询价格时使用取整后的数量（已经是真实份数）
                            new_price = await self._get_asteroid_price_by_need(type_id, quantity)
                        else:
                            # 标准/卫星矿石：查询价格时需要使用真实份数（quantity * 100）
                            # 因为约束条件中的数量是"100份"的单位，但价格查询需要真实份数
                            real_quantity = quantity * 100
                            price_per_unit = await self._get_asteroid_price_by_need(type_id, real_quantity)
                            if price_per_unit is None:
                                new_price = 100000000.0  # 惩罚性价格
                            else:
                                # 价格返回的是购买real_quantity份的平均单价（每份的价格）
                                # 我们需要的是"100份"的总价格，所以应该是：单价 * 100
                                new_price = price_per_unit * 100
                    
                    if new_price is None:
                        new_price = 100000000.0  # 惩罚性价格
                    new_prices[type_id] = new_price
                    
                    # 检查价格是否变化（收单模式下价格固定，不需要检查变化）
                    if purchase_mode != '收单':
                        old_price = ore_prices.get(type_id, 0)
                        if old_price > 0:
                            price_change = abs(new_price - old_price) / old_price
                            if price_change > price_tolerance:
                                price_changed = True
                else:
                    new_prices[type_id] = ore_prices.get(type_id, 100000000.0)
            
            # 如果价格收敛，返回结果
            # 收单模式下价格固定，第一次迭代后即可返回
            # 扫单模式下需要检查价格是否收敛
            if purchase_mode == '收单':
                return await self._extract_results(ore_vars, excess_vars, status, solver, new_prices, mineral_requirements, refinement_rate)
            elif not price_changed and previous_prices is not None:
                return await self._extract_results(ore_vars, excess_vars, status, solver, new_prices, mineral_requirements, refinement_rate)
            
            # 更新价格用于下一次迭代
            previous_prices = ore_prices.copy()
            ore_prices = new_prices
        
        # 达到最大迭代次数，返回最后一次的结果
        return await self._extract_results(ore_vars, excess_vars, status, solver, ore_prices, mineral_requirements, refinement_rate)

    
    async def _extract_results(self, ore_vars, excess_vars, status, solver, ore_prices=None, mineral_requirements=None, refinement_rate=0.906):
        """提取结果，对矿石购买数量进行取整处理，并重新计算多余矿物"""
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
        
        # 对矿石购买数量进行取整处理（最终结果）
        # 标准/卫星矿石的数量要乘以100，得到真实的份数
        rounded_ore_purchases = {}
        ore_price_details = {}  # 记录每种矿石的单价和总价
        total_cost = 0.0
        
        for ore_id, quantity in raw_ore_purchases.items():
            if quantity > 0:
                # 最终结果：标准/卫星矿石的数量要乘以100
                rounded_quantity = self._round_ore_quantity(ore_id, quantity)
                rounded_ore_purchases[ore_id] = rounded_quantity
                
                # 计算取整后的成本和单价
                # 注意：ore_prices 中的价格已经是"100份"的价格（在迭代中已乘以100）
                # 对于标准/卫星矿石：成本 = 真实份数 * 单份价格 = 数量 * (价格/100)
                # 对于冰矿：成本 = 数量 * 价格（价格是单份价格）
                if ore_prices and ore_id in ore_prices:
                    if self._is_ice_ore(ore_id):
                        # 冰矿：价格是单份价格，数量是真实份数
                        unit_price = ore_prices[ore_id]  # 单份价格
                        ore_total_price = rounded_quantity * unit_price
                        total_cost += ore_total_price
                    else:
                        # 标准/卫星矿石：价格是"100份"的价格，数量是真实份数（已乘以100）
                        # 单价 = 价格 / 100（转换为单份价格）
                        # 成本 = 真实份数 * 单份价格 = 数量 * (价格/100)
                        unit_price = ore_prices[ore_id] / 100  # 转换为单份价格
                        ore_total_price = rounded_quantity * unit_price
                        total_cost += ore_total_price
                    
                    # 记录单价和总价
                    ore_price_details[ore_id] = {
                        'unit_price': float(unit_price),
                        'total_price': float(ore_total_price),
                        'quantity': float(rounded_quantity)
                    }
                else:
                    # 如果没有价格信息，尝试使用原始解的平均价格（不准确，但作为后备）
                    # 这种情况理论上不应该发生，因为 optimize() 方法总是传递价格
                    avg_price = solver.Objective().Value() / sum(raw_ore_purchases.values()) if sum(raw_ore_purchases.values()) > 0 else 0
                    if self._is_ice_ore(ore_id):
                        unit_price = avg_price
                        ore_total_price = rounded_quantity * unit_price
                        total_cost += ore_total_price
                    else:
                        # 对于标准/卫星矿石，平均价格也是"100份"的价格，需要除以100
                        unit_price = avg_price / 100
                        ore_total_price = rounded_quantity * unit_price
                        total_cost += ore_total_price
                    
                    # 记录单价和总价（使用估算价格）
                    ore_price_details[ore_id] = {
                        'unit_price': float(unit_price),
                        'total_price': float(ore_total_price),
                        'quantity': float(rounded_quantity)
                    }
            # else:
            #     rounded_ore_purchases[ore_id] = 0.0
        
        # 如果没有价格信息且 total_cost 为 0，使用原始目标函数值作为后备
        if not ore_prices and total_cost == 0.0:
            total_cost = solver.Objective().Value()
        
        # 重新计算所有矿物的实际产出和多余产出（基于取整后的矿石数量）
        # 贡献数量 = floor(矿石数量 × 单位矿石贡献 × 化矿率)
        actual_mineral_yields = {}  # 所有矿物的实际产出
        excess_minerals = {}  # 多余矿物
        
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
        
        solution = {
            'ore_purchases': rounded_ore_purchases,
            'ore_price_details': ore_price_details,  # 每种矿石的单价和总价
            'excess_minerals': excess_minerals,  # 重新计算的多余矿物
            'total_cost': total_cost
        }
        
        return {
            'status': 'Optimal',
            'solution': solution
        }