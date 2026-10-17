# 自动化数据库迁移系统使用指南

## 概述

新的自动化迁移系统提供了完整的数据库生命周期管理，包括：

- ✅ **首次安装** - 自动创建所有表
- ✅ **模型变更** - 自动检测并迁移
- ✅ **版本历史** - 记录所有变更
- ✅ **一键回滚** - 出现问题时恢复
- ✅ **风险分级** - 安全策略控制

## 快速开始

### 1. 正常启动（自动迁移）

应用启动时会自动检测并执行迁移：

```python
from src_v2.core import init_database

# 正常启动，自动检测并执行迁移
await init_database()
```

### 2. 预览即将执行的变更（Dry-run）

```bash
# Windows PowerShell
$env:MIGRATION_DRY_RUN="true"
python run_server.py --init-only

# Linux/macOS
MIGRATION_DRY_RUN=true python run_server.py --init-only
```

### 3. 使用 CLI 工具

```bash
# 预览变更
python -m src_v2.core.database.migration_cli --dry-run

# 执行迁移
python -m src_v2.core.database.migration_cli

# 查看迁移历史
python -m src_v2.core.database.migration_cli --history

# 回滚上次迁移
python -m src_v2.core.database.migration_cli --rollback

# 开发模式（自动确认所有变更）
python -m src_v2.core.database.migration_cli --dev
```

## 迁移行为

### 首次安装

当数据库为空时，系统会自动：
1. 创建所有模型定义的表
2. 记录初始化版本
3. 输出：`🎉 数据库初始化完成，版本: 20250419_143052_a3f7d2`

### 后续升级

当检测到模型变化时，系统会：

#### 🟢 自动执行（安全变更）
- 新增表
- 新增列

#### 🟡 需确认（中等风险）
- 删除列（会备份数据）
- 修改列类型
- 修改 NULL 约束

#### 🔴 需人工处理（危险操作）
- 删除表
- 修改主键
- 大规模数据迁移

### 迁移报告示例

```
============================================================
数据库迁移计划 (共 4 项变更)
============================================================

🟢 自动执行 (2 项):
  ✓ 新增表 eve_industry_plan_task_claim
  ✓ 表 eve_industry_plan_task_claim 新增列 claimed_quantity

🟡 需确认 (1 项):
  ⚠ 表 user 将删除列 old_field
    SQL: CREATE TABLE "_backup_user_1713503452" AS SELECT...

🔴 需人工处理 (1 项):
  ✗ 表 orders 列 price 类型变更: INTEGER -> VARCHAR

============================================================
```

## 环境变量配置

> 说明：下表默认值是**数据库标识**（沿用历史命名），与产品名无关。产品自 2026-10-17 起对外名为
> **EveKahunaSystem**，开发仓库目录为 `EveKahunaSystem-Dev`；`kahunabot` 作为库名/用户名保持不动，改了会连不上既有数据。

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MIGRATION_DRY_RUN` | 仅预览不执行 | `false` |
| `MIGRATION_AUTO_CONFIRM` | 自动确认中等风险变更 | `false` |
| `POSTGRES_HOST` | PostgreSQL 主机 | `localhost` |
| `POSTGRES_PORT` | PostgreSQL 端口 | `5432` |
| `POSTGRES_DB` | 数据库名 | `kahunabot` |
| `POSTGRES_USER` | 用户名 | `kahunabot` |
| `POSTGRES_PASSWORD` | 密码 | `kahunabot` |

## 编程接口

### 基本使用

```python
from src_v2.core.database.connect_manager import postgres_manager
from src_v2.core.database.auto_migration import AutoMigrationManager
from src_v2.core.database.model import all_model

# 创建迁移管理器
migration_manager = AutoMigrationManager(postgres_manager)

# 执行迁移
context = await migration_manager.lifecycle_manage(
    base_classes=all_model,
    dry_run=False,
    auto_confirm=False,
    skip_dangerous=True
)

print(f"迁移完成，耗时: {context.execution_time_ms}ms")
print(f"执行变更数: {len(context.changes)}")
```

### 便捷函数

```python
from src_v2.core.database.auto_migration import auto_migrate_database
from src_v2.core.database.connect_manager import postgres_manager
from src_v2.core.database.model import all_model

# 一键迁移
context = await auto_migrate_database(
    db_manager=postgres_manager,
    base_classes=all_model,
    dry_run=False,
    auto_confirm=False
)
```

### 回滚操作

```python
from src_v2.core.database.auto_migration import AutoMigrationManager

migration_manager = AutoMigrationManager(postgres_manager)

# 回滚上次迁移
await migration_manager.rollback_last()
```

## 查询迁移历史

### 使用 SQL

```sql
-- 查看最近10条迁移记录
SELECT 
    version, 
    timestamp, 
    migration_type, 
    description, 
    success
FROM _migration_history
ORDER BY timestamp DESC
LIMIT 10;
```

### 使用 CLI

```bash
python -m src_v2.core.database.migration_cli --history
```

## 常见问题

### Q: 生产环境如何安全迁移？

**A:** 生产环境建议使用以下流程：

1. **备份数据**
   ```bash
   pg_dump -h localhost -U kahunabot kahunabot > backup.sql
   ```

2. **Dry-run 预览**
   ```bash
   MIGRATION_DRY_RUN=true python -m src_v2.core.database.migration_cli
   ```

3. **执行迁移**
   ```bash
   python -m src_v2.core.database.migration_cli
   ```

4. **验证结果**
   ```bash
   python -m src_v2.core.database.migration_cli --history
   ```

### Q: 如何处理危险变更？

**A:** 危险变更（如删除表）需要人工处理。系统会输出 SQL 建议，你可以：

1. 手动执行 SQL
2. 使用 `--force` 强制执行（谨慎！）
3. 分步执行：先备份数据，再执行变更

### Q: 回滚后数据会恢复吗？

**A:** 取决于变更类型：
- **新增列/表**: 回滚会删除，数据丢失
- **删除列**: 回滚会从备份恢复数据
- **修改类型**: 可能丢失数据，谨慎操作

### Q: 开发环境如何快速迭代？

**A:** 使用开发模式：

```bash
python -m src_v2.core.database.migration_cli --dev
```

或设置环境变量：

```bash
export MIGRATION_AUTO_CONFIRM=true
python run_server.py
```

## 与旧系统对比

| 功能 | 旧系统 | 新系统 |
|------|--------|--------|
| 首次安装 | ✅ | ✅ |
| 新增表 | ✅ | ✅ |
| 新增列 | ✅ | ✅ |
| 删除列 | ❌ | ✅（带备份） |
| 修改类型 | ❌ | ✅（警告） |
| 版本历史 | ❌ | ✅ |
| 一键回滚 | ❌ | ✅ |
| Dry-run | ❌ | ✅ |
| 风险分级 | ❌ | ✅ |

## 注意事项

1. **生产环境** - 始终先备份数据再迁移
2. **危险操作** - 系统会提示，不要强制跳过
3. **回滚限制** - 某些变更无法完美回滚
4. **并发问题** - 迁移期间避免多进程同时操作数据库

## 故障排查

### 迁移失败

查看日志输出，常见问题：
- 数据库连接失败 → 检查环境变量
- 权限不足 → 检查 PostgreSQL 用户权限
- 数据冲突 → 手动清理冲突数据

### 回滚失败

```bash
# 查看迁移历史
python -m src_v2.core.database.migration_cli --history

# 手动执行回滚 SQL（从 _migration_history.changes 字段获取）
```

### 数据丢失

联系 DBA 从备份恢复：
```bash
psql -h localhost -U kahunabot kahunabot < backup.sql
```
