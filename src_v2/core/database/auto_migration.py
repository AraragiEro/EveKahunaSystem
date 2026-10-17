"""
自动化数据库迁移管理器 - 完整生命周期管理

特性：
1. 首次运行自动创建所有表
2. 后续运行自动检测并应用变更
3. 版本历史记录
4. 一键回滚
5. 生产环境安全保护

使用示例：
    # 首次运行或后续升级
    await migration_manager.lifecycle_manage(base_classes=[PostgreModel])
    
    # Dry-run 预览
    await migration_manager.lifecycle_manage(dry_run=True)
    
    # 回滚上次迁移
    await migration_manager.rollback_last()
"""

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple, Type, Union

from sqlalchemy import (
    Column, Inspector, MetaData, Table, Text, inspect, text,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ..log import logger


class ChangeType(Enum):
    """变更类型"""
    ADD_TABLE = auto()            # 新增表 - 安全
    DROP_TABLE = auto()           # 删除表 - 危险
    ADD_COLUMN = auto()           # 新增列 - 安全
    DROP_COLUMN = auto()          # 删除列 - 危险
    ALTER_COLUMN_TYPE = auto()    # 修改列类型 - 危险
    ALTER_COLUMN_NULL = auto()    # 修改NULL约束 - 中等
    ALTER_COLUMN_DEFAULT = auto() # 修改默认值 - 低危
    ADD_INDEX = auto()            # 新增索引 - 安全
    DROP_INDEX = auto()           # 删除索引 - 低危
    ADD_CONSTRAINT = auto()       # 新增约束 - 中等
    DROP_CONSTRAINT = auto()      # 删除约束 - 危险
    RENAME_COLUMN = auto()        # 重命名列 - 需识别


class RiskLevel(Enum):
    """风险等级"""
    SAFE = "safe"           # 安全，可自动执行
    LOW = "low"             # 低风险，可自动执行
    MEDIUM = "medium"       # 中等风险，需确认
    HIGH = "high"           # 高风险，必须人工审核
    CRITICAL = "critical"   # 危险操作，强制人工处理


@dataclass
class SchemaChange:
    """Schema变更定义"""
    change_type: ChangeType
    table_name: str
    column_name: Optional[str] = None
    old_value: Any = None
    new_value: Any = None
    risk_level: RiskLevel = RiskLevel.SAFE
    sql_statements: List[str] = field(default_factory=list)
    rollback_sql: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    description: str = ""
    model_class: Optional[Type] = None
    
    def to_dict(self) -> Dict:
        return {
            "change_type": self.change_type.name,
            "table_name": self.table_name,
            "column_name": self.column_name,
            "risk_level": self.risk_level.value,
            "sql": self.sql_statements,
            "rollback_sql": self.rollback_sql,
            "description": self.description,
        }


@dataclass
class MigrationContext:
    """迁移上下文"""
    is_fresh_install: bool = False          # 是否全新安装
    existing_tables: Set[str] = field(default_factory=set)
    model_tables: Set[str] = field(default_factory=set)
    changes: List[SchemaChange] = field(default_factory=list)
    version: str = ""
    execution_time_ms: int = 0


class AutoMigrationManager:
    """
    自动化数据库迁移管理器
    
    完整生命周期管理：
    1. 首次运行 → 创建所有表
    2. 模型变化 → 自动检测并迁移
    3. 版本管理 → 记录所有变更
    4. 回滚支持 → 出现问题时恢复
    """
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.metadata_table = "_migration_metadata"
        self.history_table = "_migration_history"
        self.snapshot_table = "_schema_snapshot"
        
    # ============ 生命周期管理入口 ============
    
    async def lifecycle_manage(
        self,
        base_classes: List[Type],
        dry_run: bool = False,
        auto_confirm: bool = False,
        skip_dangerous: bool = True
    ) -> MigrationContext:
        """
        数据库生命周期管理主入口
        
        自动判断是首次安装还是升级，执行相应操作
        
        Args:
            base_classes: 模型基类列表
            dry_run: 是否只预览不执行
            auto_confirm: 是否自动确认中等风险操作
            skip_dangerous: 是否跳过危险操作
            
        Returns:
            MigrationContext: 迁移上下文信息
        """
        context = MigrationContext()
        start_time = time.time()
        
        async with self.db_manager.engine.begin() as conn:
            # 1. 初始化迁移元数据表
            await self._init_metadata_tables(conn)
            
            # 2. 检测当前状态
            context = await self._detect_environment(conn, base_classes)
            
            if context.is_fresh_install:
                # 首次安装：创建所有表
                logger.info("[NEW] 检测到首次安装，开始创建数据库...")
                await self._fresh_install(conn, base_classes, dry_run)
            else:
                # 升级：检测并应用变更
                logger.info(f"[UPGRADE] 检测到现有数据库，检查模型变更...")
                await self._upgrade_database(
                    conn, base_classes, context,
                    dry_run=dry_run,
                    auto_confirm=auto_confirm,
                    skip_dangerous=skip_dangerous
                )
            
            context.execution_time_ms = int((time.time() - start_time) * 1000)
            
        return context
    
    async def _detect_environment(
        self,
        conn: AsyncConnection,
        base_classes: List[Type]
    ) -> MigrationContext:
        """检测当前数据库环境"""
        context = MigrationContext()
        
        # 获取数据库中的现有表
        result = await conn.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
        """))
        context.existing_tables = {row[0] for row in result}
        
        # 获取模型定义的所有表
        for base_class in base_classes:
            for mapper in base_class.registry.mappers:
                model_class = mapper.class_
                context.model_tables.add(model_class.__tablename__)
        
        # 判断是否为全新安装
        # 条件：数据库为空 或 只有迁移元数据表
        system_tables = {self.metadata_table, self.history_table, self.snapshot_table}
        user_tables = context.existing_tables - system_tables
        
        context.is_fresh_install = len(user_tables) == 0
        
        logger.info(f"环境检测: 现有表 {len(context.existing_tables)} 个, "
                   f"模型表 {len(context.model_tables)} 个, "
                   f"全新安装: {context.is_fresh_install}")
        
        return context
    
    # ============ 首次安装流程 ============
    
    async def _fresh_install(
        self,
        conn: AsyncConnection,
        base_classes: List[Type],
        dry_run: bool
    ):
        """首次安装：创建所有表"""
        if dry_run:
            logger.info("[DRY-RUN] 将创建以下表:")
            for base_class in base_classes:
                for mapper in base_class.registry.mappers:
                    model_class = mapper.class_
                    logger.info(f"  - {model_class.__tablename__}")
            return
        
        # 1. 创建所有表
        for base_class in base_classes:
            await conn.run_sync(base_class.metadata.create_all)
            logger.info(f"[OK] 已创建 {len(base_class.metadata.tables)} 个表")
        
        # 2. 记录初始化版本
        version = self._generate_version()
        await self._record_migration(
            conn, version, [],
            migration_type="FRESH_INSTALL",
            description="首次安装：创建所有表"
        )
        
        logger.info(f"[DONE] 数据库初始化完成，版本: {version}")
    
    # ============ 升级流程 ============
    
    async def _upgrade_database(
        self,
        conn: AsyncConnection,
        base_classes: List[Type],
        context: MigrationContext,
        dry_run: bool,
        auto_confirm: bool,
        skip_dangerous: bool
    ):
        """升级数据库：检测并应用变更"""
        
        # 1. 检测所有变更（去重）
        all_changes = []
        seen_changes = set()  # 用于去重
        
        for base_class in base_classes:
            changes = await self._detect_changes(conn, base_class)
            for change in changes:
                # 使用 (table, column, type) 作为唯一键
                key = (change.table_name, change.column_name, change.change_type.name)
                if key not in seen_changes:
                    seen_changes.add(key)
                    all_changes.append(change)
        
        if not all_changes:
            logger.info("[OK] 没有发现需要迁移的变更")
            return
        
        # 2. 为每个变更生成 SQL
        for change in all_changes:
            await self._generate_sql(conn, change)
        
        # 3. 分类变更
        auto_changes, confirm_changes, manual_changes = self._categorize_changes(all_changes)
        
        # 4. 生成分类报告
        await self._print_migration_report(auto_changes, confirm_changes, manual_changes)
        
        if dry_run:
            logger.info("[DRY-RUN] 完成，未执行实际变更")
            context.changes = all_changes
            return
        
        # 5. 执行安全变更
        executed_changes = []
        
        if auto_changes:
            logger.info(f"[AUTO] 自动执行 {len(auto_changes)} 项安全变更...")
            await self._execute_changes(conn, auto_changes)
            executed_changes.extend(auto_changes)
        
        # 6. 处理需要确认的变更
        if confirm_changes:
            if auto_confirm:
                logger.info(f"[CONFIRM] 自动确认并执行 {len(confirm_changes)} 项变更...")
                await self._execute_changes(conn, confirm_changes)
                executed_changes.extend(confirm_changes)
            else:
                logger.warning(f"[PENDING] 有 {len(confirm_changes)} 项变更需要确认:")
                for change in confirm_changes:
                    logger.warning(f"   - {change.description}")
                    logger.warning(f"     SQL: {change.sql_statements[0][:100]}...")
        
        # 7. 报告危险变更
        if manual_changes:
            logger.error(f"[DANGER] 有 {len(manual_changes)} 项危险变更需要人工处理:")
            for change in manual_changes:
                logger.error(f"   - {change.description}")
            
            if not skip_dangerous:
                raise ValueError("存在危险变更，迁移已中止")
        
        # 8. 记录迁移历史
        if executed_changes:
            version = self._generate_version()
            await self._record_migration(
                conn, version, executed_changes,
                migration_type="UPGRADE",
                description=f"升级：执行 {len(executed_changes)} 项变更"
            )
            logger.info(f"[DONE] 迁移完成，版本: {version}")
        
        context.changes = executed_changes
    
    # ============ 变更检测 ============
    
    async def _detect_changes(
        self,
        conn: AsyncConnection,
        base_class: Type
    ) -> List[SchemaChange]:
        """检测模型与数据库的差异"""
        changes = []
        
        for mapper in base_class.registry.mappers:
            model_class = mapper.class_
            table_name = model_class.__tablename__
            
            # 检查表是否存在
            table_exists = await conn.run_sync(
                lambda conn: inspect(conn).has_table(table_name)
            )
            
            if not table_exists:
                # 新表
                changes.append(SchemaChange(
                    change_type=ChangeType.ADD_TABLE,
                    table_name=table_name,
                    risk_level=RiskLevel.SAFE,
                    description=f"新增表 {table_name}",
                    model_class=model_class,
                ))
            else:
                # 表存在，检查列变化
                column_changes = await self._detect_column_changes(
                    conn, model_class
                )
                changes.extend(column_changes)
        
        return changes
    
    async def _detect_column_changes(
        self,
        conn: AsyncConnection,
        model_class: Type
    ) -> List[SchemaChange]:
        """检测列级别的变化"""
        changes = []
        table_name = model_class.__tablename__
        
        # 获取数据库中的列
        def get_columns_sync(conn):
            return inspect(conn).get_columns(table_name)
        
        columns_result = await conn.run_sync(get_columns_sync)
        db_columns = {
            col["name"]: col 
            for col in columns_result
        }
        
        # 获取模型中的列
        model_columns = {
            col.name: col 
            for col in model_class.__table__.columns
        }
        
        # 1. 新增列
        for col_name, column in model_columns.items():
            if col_name not in db_columns:
                changes.append(SchemaChange(
                    change_type=ChangeType.ADD_COLUMN,
                    table_name=table_name,
                    column_name=col_name,
                    new_value=str(column.type),
                    risk_level=RiskLevel.SAFE,
                    description=f"表 {table_name} 新增列 {col_name}",
                ))
        
        # 2. 删除列
        for col_name in db_columns:
            if col_name not in model_columns:
                changes.append(SchemaChange(
                    change_type=ChangeType.DROP_COLUMN,
                    table_name=table_name,
                    column_name=col_name,
                    old_value=db_columns[col_name]["type"],
                    risk_level=RiskLevel.HIGH,
                    requires_confirmation=True,
                    description=f"表 {table_name} 将删除列 {col_name}",
                ))
        
        return changes
    
    # ============ SQL生成 ============
    
    async def _generate_sql(self, conn: AsyncConnection, change: SchemaChange):
        """为变更生成 SQL"""
        if change.change_type == ChangeType.ADD_TABLE:
            if change.model_class:
                from sqlalchemy.schema import CreateTable
                from sqlalchemy.dialects import postgresql
                ddl = CreateTable(change.model_class.__table__)
                sql = str(ddl.compile(dialect=postgresql.dialect()))
                change.sql_statements = [sql]
                change.rollback_sql = [f'DROP TABLE IF EXISTS "{change.table_name}"']
            else:
                change.sql_statements = [f"-- 表 {change.table_name} 缺少 model_class，无法生成 SQL"]
        
        elif change.change_type == ChangeType.ADD_COLUMN:
            sql = (f'ALTER TABLE "{change.table_name}" '
                   f'ADD COLUMN "{change.column_name}" {change.new_value}')
            change.sql_statements = [sql]
            change.rollback_sql = [
                f'ALTER TABLE "{change.table_name}" '
                f'DROP COLUMN "{change.column_name}"'
            ]
        
        elif change.change_type == ChangeType.DROP_COLUMN:
            # 生产环境：先备份数据
            backup_table = f"_backup_{change.table_name}_{int(time.time())}"
            change.sql_statements = [
                f'CREATE TABLE "{backup_table}" AS SELECT id, "{change.column_name}" FROM "{change.table_name}"',
                f'ALTER TABLE "{change.table_name}" DROP COLUMN "{change.column_name}"',
            ]
            change.rollback_sql = [
                f'ALTER TABLE "{change.table_name}" ADD COLUMN "{change.column_name}" {change.old_value}',
                f'UPDATE "{change.table_name}" SET "{change.column_name}" = backup."{change.column_name}" FROM "{backup_table}" backup',
                f'DROP TABLE "{backup_table}"',
            ]
    
    # ============ 执行和回滚 ============
    
    async def _execute_changes(self, conn: AsyncConnection, changes: List[SchemaChange]):
        """执行变更列表"""
        for change in changes:
            for sql in change.sql_statements:
                if not sql.startswith("--"):
                    logger.info(f"执行: {sql[:80]}...")
                    await conn.execute(text(sql))
    
    async def rollback_last(self, conn: AsyncConnection):
        """回滚最后一次迁移"""
        result = await conn.execute(text(f"""
            SELECT version, changes, migration_type 
            FROM {self.history_table}
            WHERE success = TRUE
            ORDER BY timestamp DESC
            LIMIT 1
        """))
        
        migration = result.fetchone()
        if not migration:
            raise ValueError("没有找到可回滚的迁移")
        
        version, changes_json, mig_type = migration
        changes = json.loads(changes_json)
        
        logger.info(f"回滚迁移 {version} ({mig_type})...")
        
        # 逆序执行回滚 SQL
        for change in reversed(changes):
            rollback_sql = change.get("rollback_sql", [])
            for sql in rollback_sql:
                logger.info(f"回滚: {sql[:80]}...")
                await conn.execute(text(sql))
        
        # 标记为已回滚
        await conn.execute(text(f"""
            UPDATE {self.history_table}
            SET success = FALSE, description = description || ' [已回滚]'
            WHERE version = :version
        """), {"version": version})
        
        logger.info(f"[DONE] 已回滚迁移 {version}")
    
    # ============ 辅助方法 ============
    
    async def _init_metadata_tables(self, conn: AsyncConnection):
        """初始化迁移元数据表"""
        # 历史记录表
        await conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {self.history_table} (
                id SERIAL PRIMARY KEY,
                version VARCHAR(64) UNIQUE NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                migration_type VARCHAR(32) NOT NULL,
                changes JSONB NOT NULL,
                description TEXT,
                success BOOLEAN DEFAULT TRUE
            )
        """))
        
        # Schema 快照表
        await conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {self.snapshot_table} (
                id SERIAL PRIMARY KEY,
                table_name VARCHAR(128) NOT NULL,
                column_name VARCHAR(128),
                schema_hash VARCHAR(64) NOT NULL,
                snapshot JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(table_name, column_name)
            )
        """))
    
    def _categorize_changes(
        self,
        changes: List[SchemaChange]
    ) -> Tuple[List[SchemaChange], List[SchemaChange], List[SchemaChange]]:
        """分类变更风险等级"""
        auto, confirm, manual = [], [], []
        
        for change in changes:
            if change.risk_level in (RiskLevel.SAFE, RiskLevel.LOW):
                auto.append(change)
            elif change.risk_level == RiskLevel.MEDIUM:
                if change.requires_confirmation:
                    confirm.append(change)
                else:
                    auto.append(change)
            elif change.risk_level == RiskLevel.HIGH:
                confirm.append(change)
            else:
                manual.append(change)
        
        return auto, confirm, manual
    
    async def _record_migration(
        self,
        conn: AsyncConnection,
        version: str,
        changes: List[SchemaChange],
        migration_type: str,
        description: str
    ):
        """记录迁移历史"""
        changes_json = json.dumps([c.to_dict() for c in changes])
        
        await conn.execute(text(f"""
            INSERT INTO {self.history_table} 
            (version, migration_type, changes, description)
            VALUES (:version, :type, :changes, :desc)
        """), {
            "version": version,
            "type": migration_type,
            "changes": changes_json,
            "desc": description,
        })
    
    def _generate_version(self) -> str:
        """生成版本号"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = hashlib.md5(
            str(time.time()).encode()
        ).hexdigest()[:6]
        return f"{timestamp}_{random_suffix}"
    
    async def _print_migration_report(
        self,
        auto_changes: List[SchemaChange],
        confirm_changes: List[SchemaChange],
        manual_changes: List[SchemaChange]
    ):
        """打印迁移报告"""
        total = len(auto_changes) + len(confirm_changes) + len(manual_changes)
        
        logger.info("=" * 60)
        logger.info(f"数据库迁移计划 (共 {total} 项变更)")
        logger.info("=" * 60)
        
        if auto_changes:
            logger.info(f"\n[AUTO] 自动执行 ({len(auto_changes)} 项):")
            for c in auto_changes:
                logger.info(f"  [OK] {c.description}")
        
        if confirm_changes:
            logger.info(f"\n[PENDING] 需确认 ({len(confirm_changes)} 项):")
            for c in confirm_changes:
                logger.info(f"  [WARN] {c.description}")
        
        if manual_changes:
            logger.info(f"\n[DANGER] 需人工处理 ({len(manual_changes)} 项):")
            for c in manual_changes:
                logger.info(f"  [ERROR] {c.description}")
        
        logger.info("\n" + "=" * 60)


# ============ 便捷的入口函数 ============

async def auto_migrate_database(
    db_manager,
    base_classes: List[Type],
    dry_run: bool = False,
    auto_confirm: bool = False
):
    """
    便捷函数：一键管理数据库生命周期
    
    Args:
        db_manager: 数据库管理器实例
        base_classes: 模型基类列表
        dry_run: 仅预览不执行
        auto_confirm: 自动确认中等风险变更
    """
    manager = AutoMigrationManager(db_manager)
    
    context = await manager.lifecycle_manage(
        base_classes=base_classes,
        dry_run=dry_run,
        auto_confirm=auto_confirm,
        skip_dangerous=True
    )
    
    return context
