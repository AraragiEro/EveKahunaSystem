# MODEL — src_v2/model

EVE Online 业务领域模型，市场数据、工业制造、ESI API 客户端。

## 结构

```
model/
├── EVE/
│   ├── market/          # 市场价格、订单、历史数据
│   ├── industry/        # 工业制造规划、蓝图、成本计算
│   ├── sde/             # SDE 静态数据库访问 (utils.py → SdeUtils)
│   ├── eveesi/          # ESI API 客户端 (OAuth, 请求管理)
│   ├── asset/           # 角色/公司资产查询
│   ├── character/       # 角色技能、属性
│   ├── home/            # 首页仪表盘数据聚合
│   ├── lp_store/        # LP 商店兑换计算
│   └── eve_constants.py # EVE 常量 (categoryID, groupID...)
└── google_API/          # Google Sheets 集成
```

## 查找指南

| 需求 | 位置 | 关键类/函数 |
|------|------|-----------|
| 市场查价 | `EVE/market/` | 价格查询、订单数据、历史图表 |
| 成本计算 | `EVE/industry/` | 蓝图树遍历、材料需求、制造费用 |
| 工业规划 | `EVE/industry/` | 生产计划生成、缺失蓝图检测 |
| SDE 查询 (物品名→ID) | `EVE/sde/utils.py` | `SdeUtils` 类 |
| ESI API 调用 | `EVE/eveesi/` | 角色/公司 ESI 端点 |
| 资产扫描 | `EVE/asset/` | 安全扫描、位置解析 |
| OAuth 认证 | `EVE/eveesi/` | ESI SSO, token 刷新 |
| Google Sheets | `google_API/` | 读写 Google 表格 |

## 关键模式

- **SDE 访问**: 所有 SDE 查询通过 `SdeUtils` 封装，禁止在 API 层直接操作 SDE 数据库
- **ESI 调用**: `eveesi/` 封装 ESI API 请求，包含 OAuth token 管理和速率限制
- **工业计算**: 蓝图树使用 Neo4j 图数据库存储，通过 `model_utils.py` 访问
- **数据模型**: 业务数据结构使用 dataclass 定义，与 API 响应模型分离

## 依赖关系

```
API 层 (backend/api/) 
  → model/EVE/xxx/  (业务模型，可调用)
  → core/database/  (数据库工具，禁止直接调用 - 通过 model 层封装)
```
