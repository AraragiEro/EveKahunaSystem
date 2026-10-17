# 矿物求解技术文档

## 概述

本文档介绍矿物求解功能使用的模组及其说明，并结合实现说明求解思路。矿物求解功能用于在 EVE Online 游戏中，根据矿物需求计算最优的矿石采购方案，支持通过购买压缩矿石精炼获得矿物，或直接购买矿物。

## 1. 使用的模组及说明

### 1.1 核心求解库

#### ortools.linear_solver (pywraplp)

**用途**: Google OR-Tools 线性规划求解器

**说明**:
- 使用 GLOP 求解器进行线性规划优化
- 用于求解矿物采购的最优方案
- 将矿物采购问题建模为线性规划问题，通过最小化成本来找到最优解

**使用位置**: `src_v2/model/EVE/industry/industry_utils/compressedAsteroid.py`

**关键方法**:
```python
from ortools.linear_solver import pywraplp
solver = pywraplp.Solver.CreateSolver('GLOP')
```

### 1.2 数据处理库

#### rapidfuzz

**用途**: 模糊字符串匹配库

**说明**:
- 已导入但当前实现中未使用
- 可能用于物品名称的模糊匹配功能

#### math

**用途**: Python 标准库，用于数学计算

**说明**:
- 用于取整、向下取整等数学运算
- 关键函数：`math.ceil()`（向上取整）、`math.floor()`（向下取整）

### 1.3 项目内部模组

#### SdeUtils

**文件位置**: `src_v2/model/EVE/sde/utils.py`

**用途**: 获取游戏静态数据

**主要方法**:
- `get_compressed_asteroid_type_ids()`: 获取压缩矿石分类（标准/卫星矿石、冰矿）
- `get_type_material_data_by_ids()`: 获取矿石-矿物产出关系数据
- `get_name_by_id()`: 获取物品英文名称
- `get_cn_name_by_id()`: 获取物品中文名称
- `get_volume_by_type_id()`: 获取物品体积

**说明**: 提供游戏静态数据库（SDE）的访问接口，用于获取矿石类型、矿物产出等基础数据。

#### MarketManager

**文件位置**: `src_v2/model/EVE/market/market_manager.py`

**用途**: 获取市场价格信息

**主要方法**:
- `get_jita_buy_price(type_id)`: 获取 Jita 收购价格（收单模式使用）

**说明**: 管理市场价格数据，提供 Jita 贸易中心的收购价格查询功能。

#### EveMarketRegionOrdersDBUtils

**文件位置**: `src_v2/core/database/kahuna_database_utils_v2.py`

**用途**: 获取市场订单数据

**主要方法**:
- `get_sell_orders_by_type_ids_grouped_by_price()`: 获取按价格聚合的卖单数据

**说明**: 从数据库查询市场订单，按价格分组汇总数量，用于计算购买指定数量时的平均单价。

#### AsyncCounter

**文件位置**: `src_v2/model/EVE/industry/industry_utils/async_counter.py`

**用途**: 异步计数器，提供线程安全的计数功能

**说明**:
- 使用 `asyncio.Lock()` 实现线程安全的计数
- 提供 `next_node()` 和 `next_relation()` 方法用于生成唯一ID
- 在相关模块中用于生成节点和关系的唯一ID（虽然在本文件中未直接使用，但在产业管理相关功能中使用）

**类结构**:
```python
class AsyncCounter:
    def __init__(self):
        self.node_counter = 0
        self.relation_counter = 0
        self._lock = asyncio.Lock()
    
    async def next_node(self) -> int
    async def next_relation(self) -> int
    async def init_count(self)
```

## 2. 求解思路说明

### 2.1 问题建模

将矿物采购问题建模为线性规划问题，通过优化算法找到成本最低的采购方案。

#### 决策变量

- `ore_vars[type_id]`: 每种矿石/矿物的购买数量
  - 标准/卫星矿石：以100份为单位
  - 冰矿/矿物：以1份为单位

#### 辅助变量

- `excess_vars[mineral_id]`: 每种矿物的多余产出
  - 用于处理矿石精炼后产生的多余矿物
- `shortage_vars[mineral_id]`: 每种矿物的不足数量
  - 用于处理无法满足的矿物需求

#### 约束条件

1. **矿物需求约束**:
   ```
   Σ(矿石贡献) - excess + shortage >= required_qty
   ```
   其中矿石贡献计算为：
   ```
   贡献 = 矿石数量 × 单位产出 × 化矿率
   ```

2. **数量上限约束**（仅扫单模式）:
   - 限制购买数量不超过市场可用数量
   - 标准/卫星矿石：`ore_vars[type_id] <= total_available / 100`
   - 冰矿/矿物：`ore_vars[type_id] <= total_available`

#### 目标函数

最小化总成本，包括采购成本、浪费惩罚和不足惩罚：

```
最小化: 矿石采购成本 + 浪费惩罚 + 不足惩罚

其中:
- 矿石采购成本 = Σ(矿石数量 × 单价)
- 浪费惩罚 = Σ(多余矿物数量 × 矿物价格 × waste_penalty)
- 不足惩罚 = Σ(不足矿物数量 × 矿物价格 × shortage_penalty)
```

**惩罚系数说明**:
- `waste_penalty` (默认0.1): 浪费惩罚系数，鼓励减少多余产出
- `shortage_penalty` (默认2): 不足惩罚系数，严重惩罚无法满足需求的情况

### 2.2 迭代优化算法

由于价格与数量存在循环依赖（价格取决于购买数量，购买数量又取决于价格），采用迭代优化算法：

#### 算法流程

1. **初始化阶段**:
   - 使用最低价格（扫单模式）或收购价格（收单模式）作为初始价格估计
   - 初始化价格字典 `ore_prices`

2. **迭代求解阶段**:
   ```
   for iteration in range(max_iterations):
       # 1. 使用当前价格构建线性规划模型
       solver = 创建求解器
       添加决策变量和约束条件
       设置目标函数（使用当前价格）
       
       # 2. 求解得到最优购买数量
       status = solver.Solve()
       
       # 3. 提取当前解
       current_solution = 提取矿石购买数量
       
       # 4. 根据购买数量重新计算实际价格
       if 扫单模式:
           根据数量查询市场订单，计算加权平均价格
       else:  # 收单模式
           使用固定的收购价格
       
       # 5. 检查价格是否收敛
       if 价格变化 < price_tolerance:
           break  # 收敛，退出迭代
       
       # 6. 更新价格用于下一次迭代
       ore_prices = new_prices
   ```

3. **收敛判断**:
   - 价格变化小于阈值 `price_tolerance`（默认0.01，即1%）
   - 或达到最大迭代次数 `max_iterations`（默认10次）
   - 收单模式下价格固定，只需一次迭代

#### 价格-数量循环依赖问题

**问题描述**:
- 购买数量越多，平均单价越高（因为需要购买更高价格的订单）
- 但购买数量又取决于价格（价格越高，可能选择其他矿石）

**解决方案**:
- 通过迭代优化，逐步调整价格和数量，直到收敛
- 每次迭代使用当前最优数量重新计算价格，然后重新求解

### 2.3 价格计算策略

#### 扫单模式

根据购买数量查询市场订单，计算加权平均价格：

1. **订单数据预处理**:
   - 将原始订单数据按价格升序排序
   - 转换为缓存结构：`[price, quantity, quantity_sum_lower, avg_price_lower]`
   - 其中 `quantity_sum_lower` 是小于当前价格的数量总和
   - `avg_price_lower` 是更低价格订单的数量加权平均价

2. **价格计算**:
   ```python
   def _get_asteroid_price_by_need(type_id, need_quantity):
       # 找到满足 quantity_sum_lower < need_quantity <= quantity_sum_lower + quantity 的档位
       # 计算加权平均价格：
       # avg_price = (lower_cost + current_cost) / need_quantity
       # 其中：
       #   lower_cost = avg_price_lower * quantity_sum_lower
       #   current_cost = price * (need_quantity - quantity_sum_lower)
   ```

3. **单位处理**:
   - 标准/卫星矿石：查询时使用真实份数（quantity × 100），返回"100份"的总价格
   - 冰矿/矿物：查询时使用真实份数，返回单份价格

#### 收单模式

使用固定的收购价格（buymax price）：

- 价格不随数量变化
- 使用 `MarketManager().get_jita_buy_price(type_id)` 获取
- 只需一次迭代即可完成求解

### 2.4 数量取整处理

由于游戏中的交易单位限制，需要对购买数量进行取整处理：

#### 取整规则

- **标准/卫星矿石**: 
  - 以100份为单位
  - 最终结果：`math.ceil(quantity) * 100`
  - 迭代过程中：保持原样（不乘以100），但价格查询时使用真实份数

- **冰矿/矿物**: 
  - 以1份为单位
  - 最终结果和迭代过程：`math.ceil(quantity)`

#### 取整时机

1. **迭代过程中**（用于价格查询）:
   - 使用 `_round_ore_quantity_for_iteration()` 方法
   - 只对冰矿和矿物取整，标准/卫星矿石保持原样

2. **最终结果**（用于实际采购）:
   - 使用 `_round_ore_quantity()` 方法
   - 所有类型都进行取整处理

### 2.5 化矿率处理

矿石精炼产物需要应用化矿率（refinement rate）：

#### 化矿率说明

- **默认值**: 0.906（即90.6%的产出率）
- **应用对象**: 所有通过矿石精炼获得的矿物
- **不应用对象**: 直接购买的矿物（化矿率为1）

#### 计算方法

1. **线性规划约束中**:
   ```
   贡献 = 矿石数量 × 单位产出 × 化矿率
   ```
   - 使用线性近似（不向下取整），便于线性规划求解

2. **最终结果计算中**:
   ```python
   # 标准/卫星矿石
   contribution = rounded_quantity * (mineral_yield / 100) * refinement_rate
   actual_yield = math.floor(contribution)  # 向下取整
   
   # 冰矿
   contribution = rounded_quantity * mineral_yield * refinement_rate
   actual_yield = math.floor(contribution)  # 向下取整
   ```
   - 应用化矿率后向下取整，得到实际产出

## 3. 实现细节

### 3.1 数据初始化流程

在 `_init_type_material_data()` 方法中完成数据初始化：

1. **获取压缩矿石类型ID列表**:
   ```python
   standard_and_moon_ore_ids, ice_ore_ids = await SdeUtils.get_compressed_asteroid_type_ids()
   ```

2. **获取矿石-矿物产出关系数据**:
   ```python
   type_material_data = await SdeUtils.get_type_material_data_by_ids(compressed_asteroid_type_ids)
   self._type_material_data_dict = {
       type_id: {materialTypeID: quantity, ...}
       for type_id in compressed_asteroid_type_ids
   }
   ```

3. **获取矿物价格**:
   ```python
   material_set = set(data["materialTypeID"] for data in type_material_data)
   self._material_price_dict = {
       material_id: await MarketManager().get_jita_buy_price(material_id)
       for material_id in material_set
   }
   ```

4. **获取矿石市场订单数据**:
   ```python
   asteroid_order_data = await EveMarketRegionOrdersDBUtils.get_sell_orders_by_type_ids_grouped_by_price(
       type_ids=compressed_asteroid_type_ids,
       location_id=JITA_TRADE_HUB_STRUCTURE_ID,
       region_id=REGION_FORGE_ID
   )
   ```

5. **转换订单数据为缓存结构**:
   ```python
   self._compressed_asteroid_stats = self._transform_asteroid_order_data(self._asteroid_order_data)
   ```

6. **获取矿物市场订单数据**（用于直接购买矿物）:
   ```python
   self._mineral_ids = list(material_set)
   mineral_order_data = await EveMarketRegionOrdersDBUtils.get_sell_orders_by_type_ids_grouped_by_price(...)
   self._mineral_stats = self._transform_asteroid_order_data(self._mineral_order_data)
   ```

### 3.2 订单数据转换

`_transform_asteroid_order_data()` 方法将原始订单数据转换为便于价格查询的缓存结构：

#### 输入格式

```python
{
    type_id: [[price, quantity], ...]  # 按价格升序
}
```

#### 输出格式

```python
{
    type_id: [
        [price, quantity, quantity_sum_lower, avg_price_lower],
        ...
    ]
}
```

#### 转换过程

1. 按价格升序排序订单
2. 遍历每个订单，计算累计值：
   - `quantity_sum_lower`: 小于当前价格的数量总和
   - `avg_price_lower`: 更低价格订单的数量加权平均价
3. 存储转换后的数据，便于后续快速查询

#### 优势

- **快速查询**: O(n) 时间复杂度找到对应价格档位
- **精确计算**: 直接使用累计值计算加权平均价格，无需重复计算

### 3.3 矿石数据构建

`_build_ore_data_from_dict()` 方法构建矿石数据列表：

1. **添加矿石数据**:
   ```python
   for type_id, mineral_yield in self._type_material_data_dict.items():
       ore_data.append({
           'ore_id': type_id,
           'ore_name': await SdeUtils.get_name_by_id(type_id),
           'ore_name_zh': await SdeUtils.get_cn_name_by_id(type_id),
           'mineral_yield': mineral_yield
       })
   ```

2. **添加矿物数据**（作为"矿石"条目）:
   ```python
   for mineral_id in self._mineral_ids:
       ore_data.append({
           'ore_id': mineral_id,
           'mineral_yield': {mineral_id: 1}  # 1份矿物产出1份自己
       })
   ```
   - 允许直接购买矿物，化矿率为1

### 3.4 结果提取与后处理

`_extract_results()` 方法提取并处理求解结果：

#### 处理步骤

1. **提取原始解**:
   ```python
   raw_ore_purchases = {
       ore_id: var.solution_value()
       for ore_id, var in ore_vars.items()
   }
   ```

2. **数量取整处理**:
   - 区分矿石和矿物
   - 对每种类型应用相应的取整规则
   - 计算取整后的成本和单价

3. **重新计算实际矿物产出**:
   ```python
   # 累加直接购买的矿物
   for mineral_id, quantity in direct_mineral_purchases.items():
       actual_mineral_yields[mineral_id] += quantity
   
   # 计算矿石精炼产出
   for ore_id, rounded_quantity in rounded_ore_purchases.items():
       mineral_yields = self._type_material_data_dict.get(ore_id, {})
       for mineral_id, mineral_yield in mineral_yields.items():
           # 应用化矿率并向下取整
           contribution = rounded_quantity * (mineral_yield / 100) * refinement_rate
           actual_yield = math.floor(contribution)
           actual_mineral_yields[mineral_id] += actual_yield
   ```

4. **计算多余矿物和不足矿物**:
   ```python
   # 对于需求列表中的矿物
   for mineral_id, required_qty in mineral_requirements.items():
       actual_yield = actual_mineral_yields.get(mineral_id, 0)
       excess = max(0.0, actual_yield - required_qty)
       excess_minerals[mineral_id] = excess
   
   # 对于不在需求列表中的矿物
   for mineral_id, actual_yield in actual_mineral_yields.items():
       if mineral_id not in mineral_requirements:
           excess_minerals[mineral_id] = actual_yield
   ```

5. **构建返回结果**:
   ```python
   solution = {
       'ore_purchases': rounded_ore_purchases,  # 矿石购买
       'ore_price_details': ore_price_details,  # 矿石价格详情
       'direct_mineral_purchases': direct_mineral_purchases,  # 直接购买的矿物
       'mineral_price_details': mineral_price_details,  # 矿物价格详情
       'excess_minerals': excess_minerals,  # 多余矿物
       'shortage_minerals': shortage_minerals,  # 不足矿物
       'total_cost': total_cost  # 总成本
   }
   ```

## 4. 使用示例

### 4.1 基本用法

```python
from src_v2.model.EVE.industry.industry_utils.compressedAsteroid import CompressedAsteroidUtils

# 创建工具实例
compressed_asteroid_utils = CompressedAsteroidUtils()

# 初始化数据
await compressed_asteroid_utils._init_type_material_data()

# 定义矿物需求
mineral_requirements = {
    34: 1000,   # 需要1000个三钛合金
    35: 500,    # 需要500个派克瑞特
    # ... 其他矿物
}

# 调用优化求解
result = await compressed_asteroid_utils.optimize(
    mineral_requirements=mineral_requirements,
    waste_penalty=0.1,
    shortage_penalty=2,
    max_iterations=10,
    price_tolerance=0.01,
    refinement_rate=0.906,
    purchase_mode='扫单'  # 或 '收单'
)

# 处理结果
if result['status'] == 'Optimal':
    solution = result['solution']
    print(f"总成本: {solution['total_cost']}")
    print(f"矿石购买: {solution['ore_purchases']}")
    print(f"多余矿物: {solution['excess_minerals']}")
    print(f"不足矿物: {solution['shortage_minerals']}")
```

### 4.2 参数说明

- `mineral_requirements`: 字典，键为矿物ID，值为需求数量
- `waste_penalty`: 浪费惩罚系数（默认0.1）
- `shortage_penalty`: 不足惩罚系数（默认2）
- `max_iterations`: 最大迭代次数（默认10）
- `price_tolerance`: 价格收敛阈值（默认0.01，即1%）
- `refinement_rate`: 化矿率（默认0.906）
- `purchase_mode`: 采购模式，'扫单' 或 '收单'（默认'扫单'）

## 5. 算法复杂度

- **时间复杂度**: O(max_iterations × (矿石数量 × 矿物数量 + 订单查询))
- **空间复杂度**: O(矿石数量 + 矿物数量 + 订单数据大小)

## 6. 注意事项

1. **价格数据**: 需要确保市场订单数据是最新的，否则计算结果可能不准确
2. **化矿率**: 默认化矿率为0.906，实际值可能因技能而异
3. **数量取整**: 最终结果会进行取整处理，可能导致实际产出略少于理论值
4. **迭代收敛**: 如果价格波动较大，可能需要增加迭代次数或调整收敛阈值
5. **收单模式**: 收单模式下价格固定，只需一次迭代，但价格可能高于扫单模式

## 7. 相关文件

- **主要实现**: `src_v2/model/EVE/industry/industry_utils/compressedAsteroid.py`
- **异步计数器**: `src_v2/model/EVE/industry/industry_utils/async_counter.py`
- **API接口**: `src_v2/backend/api/EVE/api_industry.py` (getCompressedAsteroidData)
- **前端组件**: `src_v2/frontend/src/views/industry/components/industryViewComponent/compressedAsteroidView.vue`
