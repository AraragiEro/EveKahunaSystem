# CORE — src_v2/core

项目核心基础设施层：数据库访问、配置、权限、日志、渲染。

## 结构

```
core/
├── database/               # 数据库封装层 (15 文件)
│   ├── model.py            # SQLAlchemy ORM 模型定义
│   ├── connect_manager.py  # 多数据库连接生命周期管理
│   ├── kahuna_database_utils_v2.py  # PostgreSQL 操作封装
│   ├── neo4j_utils.py      # Neo4j 图数据库操作
│   ├── neo4j_models.py     # Neo4j 节点/关系模型
│   ├── neo4j_model_manager.py  # Neo4j 模型生命周期管理
│   ├── cache_model.py      # 缓存模型
│   ├── config_model.py     # 配置持久化模型
│   ├── message_board_utils.py  # 留言板数据操作
│   ├── auto_migration.py   # 自动迁移引擎 (AutoMigrationManager)
│   ├── migration_cli.py    # 迁移 CLI 工具
│   └── migrations/         # 迁移脚本记录
├── config/                 # 配置管理 (config.toml 解析)
├── log/                    # 统一日志模块 (from core.log import logger)
├── permission/             # RBAC 角色权限系统
├── picture_render/         # HTML → 图片渲染服务
├── user/                   # 用户管理 (注册、登录、绑定)
├── edition/                # 版本管理 (免费版/企业版)
├── resource/               # 资源文件管理
└── utils/                  # 通用工具函数
```

## 查找指南

| 需要做什么 | 位置 | 注意 |
|-----------|------|------|
| 新增/修改数据库表 | `database/model.py` → 运行迁移 CLI | 不要手动改数据库结构 |
| 执行数据库查询 | `database/kahuna_database_utils_v2.py` | API 层禁止直接操作 session |
| Neo4j 图数据操作 | `database/neo4j_utils.py` | 市场树、蓝图树 |
| 数据库迁移 | `database/auto_migration.py` | 安全/需确认/危险 三级风险 |
| 权限检查 | `permission/` | RBAC 装饰器 @permission_required |
| 添加日志 | `from core.log import logger` | 使用 f-string 格式化 |
| 图片渲染 | `picture_render/` | HTML 模板 → PNG 输出 |
| 用户认证 | `user/` + `backend/auth.py` | JWT token 管理 |

## 数据库分层

```
API 层 (backend/api/)
  ↓ 禁止直接调用 session ← 🔴 CRITICAL
业务层 (model/) → 调用封装模块
  ↓
core/database/ → connect_manager (连接池)
  ↓
PostgreSQL  |  Neo4j  |  Redis  |  SQLite
```

**严禁绕过**: API 层绝不能直接 `get_session()` / `sa_text()` / `select(Model)`。必须在 model 层或 core/database 中封装后调用。

## 关键文件依赖

- `connect_manager.py` → 被所有数据库模块依赖（PostgreSQL, Neo4j, Redis 连接管理）
- `model.py` → 被 `auto_migration.py` 和 `kahuna_database_utils_v2.py` 依赖
- `log/logger.py` → 全项目通用的日志入口
