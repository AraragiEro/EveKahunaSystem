from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Type
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from neo4j import AsyncGraphDatabase
from neo4j.exceptions import TransactionError

from redis.asyncio import Redis

from ..config.config import config
from ..log import logger

ConfigModel = declarative_base()
CacheModel = declarative_base()
PostgreModel = declarative_base()

from . import model

"""
需求：
1. 使用异步连接
2. 函数create_default_table会自动检查传入的declarative_base类作为基类的所有table是否已经存在于数据库中
    若已存在，检查表结构是否一致，若不一致则删除table重建
    若不存在，则创建
3. self.session保存session
"""
class PostgreDatabaseManager():
    def __init__(self):
        self.session = None
        self.engine = None
        self._session_maker = None

    def _is_development_mode(self) -> bool:
        """判断是否为开发环境"""
        env_mode = os.getenv('ENVIRONMENT', '').lower()
        return env_mode in ('dev', 'development', 'local')

    def _is_production_mode(self) -> bool:
        """判断是否为生产环境"""
        env_mode = os.getenv('ENVIRONMENT', '').lower()
        return env_mode in ('prod', 'production')

    async def _get_existing_table_structure(self, conn, table_name: str) -> dict:
        """获取数据库中已存在表的结构"""
        try:
            # 查询表的列信息
            query = text("""
                SELECT 
                    column_name, 
                    data_type, 
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_name = :table_name
                ORDER BY ordinal_position
            """)
            result = await conn.execute(query, {"table_name": table_name})
            columns = {}
            for row in result:
                columns[row[0]] = {
                    'data_type': row[1],
                    'max_length': row[2],
                    'nullable': row[3] == 'YES',
                    'default': row[4]
                }
            return columns
        except Exception as e:
            logger.error(f"获取表 {table_name} 结构失败: {e}")
            return {}

    def _get_model_table_structure(self, model_class) -> dict:
        """获取 SQLAlchemy 模型定义的表结构"""
        columns = {}
        for column in model_class.__table__.columns:
            columns[column.name] = {
                'type': str(column.type),
                'nullable': column.nullable,
                'primary_key': column.primary_key,
                'default': column.default
            }
        return columns

    def _get_postgresql_type(self, col_type):
        """将 SQLAlchemy 类型转换为 PostgreSQL 类型字符串"""
        from sqlalchemy.dialects import postgresql
        
        # 尝试使用 SQLAlchemy 的类型编译功能（最可靠的方法）
        try:
            # 使用 PostgreSQL 方言编译类型
            dialect = postgresql.dialect()
            compiled = col_type.compile(dialect=dialect)
            return str(compiled)
        except Exception:
            # 如果编译失败，使用简单的类型映射
            pass
        
        # 简单的类型映射作为后备方案
        type_mapping = {
            'Integer': 'INTEGER',
            'BigInteger': 'BIGINT',
            'Text': 'TEXT',
            'String': 'TEXT',
            'DateTime': 'TIMESTAMP',
            'Date': 'DATE',
            'Time': 'TIME',
            'Float': 'REAL',
            'Numeric': 'NUMERIC',
            'Boolean': 'BOOLEAN',
            'LargeBinary': 'BYTEA',
        }
        
        # 尝试通过类型名称匹配
        type_name = type(col_type).__name__
        if type_name in type_mapping:
            # 如果是 ARRAY 类型，需要特殊处理
            if hasattr(col_type, 'item_type'):
                base_type = self._get_postgresql_type(col_type.item_type)
                return f'{base_type}[]'
            return type_mapping[type_name]
        
        # 默认返回 TEXT
        return 'TEXT'

    async def _check_table_exists(self, conn, table_name: str) -> bool:
        """检查表是否存在"""
        query = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = :table_name
            )
        """)
        result = await conn.execute(query, {"table_name": table_name})
        return result.scalar()

    def _compare_table_structures(self, existing_structure: dict, model_structure: dict) -> bool:
        """
        比较数据库中的表结构和模型定义的表结构是否一致
        返回 True 表示一致，False 表示不一致
        """
        # 检查列数量
        if len(existing_structure) != len(model_structure):
            logger.info(f"表结构不一致：列数量不同 (数据库: {len(existing_structure)}, 模型: {len(model_structure)})")
            return False

        # 检查每个列
        for col_name, model_info in model_structure.items():
            if col_name not in existing_structure:
                logger.info(f"表结构不一致：缺少列 {col_name}")
                return False

            # 这里可以添加更详细的类型比对
            # 简化版本：只检查列名是否存在

        return True

    async def _drop_table(self, conn, table_name: str):
        """删除表"""
        try:
            await conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
            logger.info(f"已删除表: {table_name}")
        except Exception as e:
            logger.error(f"删除表 {table_name} 失败: {e}")
            raise

    def _extract_column_default(self, column):
        """
        提取列的默认值，返回可用于SQL的默认值字符串
        
        Args:
            column: SQLAlchemy Column 对象
            
        Returns:
            tuple: (default_value_sql, has_default) 
                - default_value_sql: SQL字符串，如果为None表示无默认值
                - has_default: 是否有默认值
        """
        from sqlalchemy.schema import ColumnDefault
        # FunctionElement 可能在不同的SQLAlchemy版本中位置不同
        # 使用 hasattr 检查而不是直接导入
        
        # 检查 server_default（数据库层面的默认值）
        if column.server_default is not None:
            if hasattr(column.server_default, 'arg'):
                # 处理 text() 包装的默认值
                default_arg = column.server_default.arg
                if isinstance(default_arg, str):
                    return default_arg, True
                elif hasattr(default_arg, 'text'):
                    return default_arg.text, True
            return str(column.server_default), True
        
        # 检查 default（应用层面的默认值）
        if column.default is not None:
            default = column.default
            # 处理 ColumnDefault 对象
            if isinstance(default, ColumnDefault):
                if hasattr(default, 'arg'):
                    arg = default.arg
                    # 处理函数调用（如 func.now()）
                    # 检查是否是SQL函数元素（有compile方法）
                    if hasattr(arg, 'compile') and callable(getattr(arg, 'compile', None)):
                        try:
                            # 编译为SQL
                            from sqlalchemy.dialects import postgresql
                            dialect = postgresql.dialect()
                            compiled = arg.compile(dialect=dialect)
                            return str(compiled), True
                        except Exception as e:
                            logger.warning(f"编译默认值函数失败: {e}")
                            return None, False
                    # 处理可调用对象
                    elif callable(arg):
                        try:
                            value = arg()
                            # 根据类型格式化
                            if isinstance(value, str):
                                return f"'{value}'", True
                            elif isinstance(value, datetime):
                                return f"'{value.isoformat()}'", True
                            else:
                                return str(value), True
                        except Exception as e:
                            logger.warning(f"执行默认值函数失败: {e}")
                            return None, False
                    # 处理静态值
                    else:
                        if isinstance(arg, str):
                            return f"'{arg}'", True
                        elif isinstance(arg, datetime):
                            return f"'{arg.isoformat()}'", True
                        else:
                            return str(arg), True
        
        return None, False

    async def _check_foreign_key_constraint_exists(self, conn, table_name: str, constraint_name: str) -> bool:
        """检查外键约束是否已存在"""
        query = text("""
            SELECT COUNT(*) FROM information_schema.table_constraints 
            WHERE constraint_name = :constraint_name 
            AND table_name = :table_name
            AND constraint_type = 'FOREIGN KEY'
        """)
        result = await conn.execute(query, {
            "constraint_name": constraint_name,
            "table_name": table_name
        })
        return result.scalar() > 0

    async def _validate_foreign_key_data(self, conn, table_name: str, col_name: str, 
                                         ref_table: str, ref_col: str) -> tuple:
        """
        验证外键数据完整性
        
        Returns:
            tuple: (is_valid, invalid_count, invalid_samples)
                - is_valid: 是否有效
                - invalid_count: 违反约束的行数
                - invalid_samples: 违反约束的示例数据（最多5条）
        """
        # 检查违反外键约束的数据
        check_sql = text(f"""
            SELECT t."{col_name}" 
            FROM "{table_name}" t
            WHERE t."{col_name}" IS NOT NULL 
            AND NOT EXISTS (
                SELECT 1 FROM "{ref_table}" r 
                WHERE r."{ref_col}" = t."{col_name}"
            )
            LIMIT 5
        """)
        result = await conn.execute(check_sql)
        invalid_samples = [row[0] for row in result]
        
        # 获取总数
        count_sql = text(f"""
            SELECT COUNT(*) 
            FROM "{table_name}" t
            WHERE t."{col_name}" IS NOT NULL 
            AND NOT EXISTS (
                SELECT 1 FROM "{ref_table}" r 
                WHERE r."{ref_col}" = t."{col_name}"
            )
        """)
        count_result = await conn.execute(count_sql)
        invalid_count = count_result.scalar() or 0
        
        return invalid_count == 0, invalid_count, invalid_samples

    def _get_foreign_key_constraint_sql(self, table_name: str, col_name: str, 
                                        ref_table: str, ref_col: str, 
                                        constraint_name: str, on_delete=None, on_update=None) -> str:
        """生成外键约束SQL语句"""
        sql = (
            f'ALTER TABLE "{table_name}" '
            f'ADD CONSTRAINT "{constraint_name}" '
            f'FOREIGN KEY ("{col_name}") '
            f'REFERENCES "{ref_table}" ("{ref_col}")'
        )
        
        if on_delete:
            sql += f' ON DELETE {on_delete}'
        if on_update:
            sql += f' ON UPDATE {on_update}'
        
        return sql

    async def _fix_sequence_for_table(self, conn, table_name: str, model_class):
        """
        检查并修复表的自增主键序列
        
        Args:
            conn: 数据库连接对象
            table_name: 表名
            model_class: 模型类
        """
        # 查找自增主键列
        autoincrement_pk_cols = [
            col for col in model_class.__table__.columns
            if col.primary_key and col.autoincrement
        ]
        
        if not autoincrement_pk_cols:
            return
        
        for col in autoincrement_pk_cols:
            col_name = col.name
            # 检查列类型，只有整数类型才需要序列
            from sqlalchemy import Integer, BigInteger, SmallInteger
            if not isinstance(col.type, (Integer, BigInteger, SmallInteger)):
                # 跳过非整数类型的主键（如 Text 类型的主键）
                logger.debug(f"跳过非整数类型的主键列 {table_name}.{col_name} (类型: {col.type})")
                continue
                
            sequence_name = f"{table_name}_{col_name}_seq"
            
            # 使用保存点来隔离序列修复操作，避免影响主事务
            # 保存点名称使用简化的格式，避免特殊字符问题
            savepoint_name = f"sp_{table_name[:20]}_{col_name}"
            savepoint_created = False
            try:
                # 创建保存点
                await conn.execute(text(f"SAVEPOINT {savepoint_name}"))
                savepoint_created = True
                
                # 检查序列是否存在
                check_sequence_query = text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_sequences 
                        WHERE schemaname = 'public' AND sequencename = :seq_name
                    )
                """)
                result = await conn.execute(check_sequence_query, {"seq_name": sequence_name})
                sequence_exists = result.scalar()
                
                # 检查列的默认值是否使用序列
                check_default_query = text("""
                    SELECT column_default 
                    FROM information_schema.columns 
                    WHERE table_name = :table_name AND column_name = :col_name
                """)
                result = await conn.execute(check_default_query, {
                    "table_name": table_name,
                    "col_name": col_name
                })
                default_value = result.scalar()
                
                # 检查默认值是否包含 nextval（PostgreSQL 序列函数）
                has_sequence_default = default_value and 'nextval' in str(default_value).lower()
                
                # 如果序列不存在或默认值不正确，需要修复
                if not sequence_exists or not has_sequence_default:
                    # 创建序列
                    if not sequence_exists:
                        # 获取当前最大值
                        max_val_query = text(f'SELECT COALESCE(MAX("{col_name}"), 0) FROM "{table_name}"')
                        max_result = await conn.execute(max_val_query)
                        max_val = max_result.scalar() or 0
                        
                        # 创建序列，起始值为当前最大值+1
                        create_seq_sql = text(
                            f"CREATE SEQUENCE IF NOT EXISTS {sequence_name} "
                            f"START WITH {max_val + 1}"
                        )
                        await conn.execute(create_seq_sql)
                        logger.info(f"已为表 {table_name} 的列 {col_name} 创建序列 {sequence_name}")
                    
                    # 设置列的默认值为序列的 nextval
                    alter_col_sql = text(
                        f'ALTER TABLE "{table_name}" '
                        f'ALTER COLUMN "{col_name}" '
                        f'SET DEFAULT nextval(\'{sequence_name}\')'
                    )
                    await conn.execute(alter_col_sql)
                    logger.info(f"已为表 {table_name} 的列 {col_name} 设置序列默认值")
                    
                    # 确保序列拥有者为表
                    owner_sql = text(f"ALTER SEQUENCE {sequence_name} OWNED BY \"{table_name}\".\"{col_name}\"")
                    await conn.execute(owner_sql)
                    logger.info(f"已设置序列 {sequence_name} 的拥有者")
                
                # 释放保存点
                if savepoint_created:
                    await conn.execute(text(f"RELEASE SAVEPOINT {savepoint_name}"))
                
            except Exception as e:
                # 回滚到保存点，不影响主事务
                if savepoint_created:
                    try:
                        await conn.execute(text(f"ROLLBACK TO SAVEPOINT {savepoint_name}"))
                        logger.warning(f"修复表 {table_name} 的列 {col_name} 序列失败，已回滚: {e}")
                    except Exception as rollback_error:
                        # 如果回滚也失败，记录错误但不抛出异常
                        logger.error(f"回滚保存点失败: {rollback_error}")
                else:
                    # 如果保存点创建失败，只记录警告
                    logger.warning(f"无法创建保存点修复表 {table_name} 的列 {col_name} 序列: {e}")
                # 不抛出异常，允许继续执行其他表的处理

    async def _migrate_table_incremental(self, conn, table_name: str, model_class):
        """
        生产环境增量迁移：使用 ALTER TABLE 进行增量迁移，不删除表
        
        Args:
            conn: 数据库连接对象
            table_name: 表名
            model_class: 模型类
        """
        is_dev = self._is_development_mode()
        existing_structure = await self._get_existing_table_structure(conn, table_name)
        model_structure = self._get_model_table_structure(model_class)
        
        # 1. 处理新增列
        for col_name, col_info in model_structure.items():
            if col_name not in existing_structure:
                col = model_class.__table__.columns[col_name]
                col_type = self._get_postgresql_type(col.type)
                
                # 步骤1：先添加为可空列
                add_col_sql = text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col_name}" {col_type}')
                await conn.execute(add_col_sql)
                logger.info(f"已添加可空列 {table_name}.{col_name}")
                
                # 步骤2：处理默认值
                default_value_sql, has_default = self._extract_column_default(col)
                if has_default and default_value_sql:
                    # 填充现有数据的默认值
                    update_sql = text(f'UPDATE "{table_name}" SET "{col_name}" = {default_value_sql} WHERE "{col_name}" IS NULL')
                    result = await conn.execute(update_sql)
                    row_count = result.rowcount if hasattr(result, 'rowcount') else 0
                    logger.info(f"已为 {row_count} 行数据填充默认值 {table_name}.{col_name}")
                
                # 步骤3：数据完整性验证
                check_null_sql = text(f'SELECT COUNT(*) FROM "{table_name}" WHERE "{col_name}" IS NULL')
                result = await conn.execute(check_null_sql)
                null_count = result.scalar() or 0
                
                if null_count > 0:
                    if not col.nullable:
                        # 需要NOT NULL但没有默认值
                        if not has_default:
                            error_msg = (
                                f"无法将列 {col_name} 设为 NOT NULL：\n"
                                f"- 表 {table_name} 中存在 {null_count} 行数据该列为 NULL\n"
                                f"- 模型定义中未提供默认值\n"
                                f"- 请先手动填充数据或添加默认值后再迁移"
                            )
                            if is_dev:
                                logger.warning(f"[开发模式] {error_msg}，将跳过NOT NULL约束")
                            else:
                                raise ValueError(error_msg)
                        else:
                            # 有默认值但未正确应用
                            logger.warning(f"列 {col_name} 仍有 {null_count} 行NULL值，但已设置默认值，将尝试重新填充")
                            update_sql = text(f'UPDATE "{table_name}" SET "{col_name}" = {default_value_sql} WHERE "{col_name}" IS NULL')
                            await conn.execute(update_sql)
                            # 再次检查
                            result = await conn.execute(check_null_sql)
                            null_count = result.scalar() or 0
                            if null_count > 0:
                                error_msg = f"列 {col_name} 仍有 {null_count} 行NULL值，无法添加NOT NULL约束"
                                if is_dev:
                                    logger.warning(f"[开发模式] {error_msg}，将跳过NOT NULL约束")
                                else:
                                    raise ValueError(error_msg)
                
                # 步骤4：添加NOT NULL约束（如果需要）
                if not col.nullable and null_count == 0:
                    alter_not_null_sql = text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{col_name}" SET NOT NULL')
                    await conn.execute(alter_not_null_sql)
                    logger.info(f"已为列 {col_name} 添加 NOT NULL 约束")
                
                # 步骤5：设置数据库默认值（如果有server_default）
                if col.server_default is not None:
                    default_value_sql, _ = self._extract_column_default(col)
                    if default_value_sql:
                        alter_default_sql = text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{col_name}" SET DEFAULT {default_value_sql}')
                        await conn.execute(alter_default_sql)
                        logger.info(f"已设置列 {col_name} 的数据库默认值")
        
        # 2. 添加外键约束
        for col in model_class.__table__.columns:
            for fk in col.foreign_keys:
                fk_name = f'fk_{table_name}_{col.name}'
                ref_table = fk.column.table.name
                ref_col = fk.column.name
                
                # 检查约束是否已存在
                if await self._check_foreign_key_constraint_exists(conn, table_name, fk_name):
                    logger.info(f"外键约束 {fk_name} 已存在，跳过")
                    continue
                
                # 检查引用表是否存在
                ref_table_exists = await self._check_table_exists(conn, ref_table)
                if not ref_table_exists:
                    if is_dev:
                        logger.warning(f"[开发模式] 引用表 {ref_table} 不存在，跳过外键约束 {fk_name}")
                        continue
                    else:
                        raise ValueError(f"无法添加外键约束 {fk_name}：引用表 {ref_table} 不存在")
                
                # 检查引用列是否存在
                ref_col_check = text("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = :ref_table AND column_name = :ref_col
                """)
                ref_col_result = await conn.execute(ref_col_check, {
                    "ref_table": ref_table,
                    "ref_col": ref_col
                })
                ref_col_exists = ref_col_result.scalar() > 0
                
                if not ref_col_exists:
                    raise ValueError(f"无法添加外键约束 {fk_name}：引用列 {ref_table}.{ref_col} 不存在")
                
                # 验证数据完整性
                skip_validation = os.getenv("POSTGRE_FK_SKIP_VALIDATION", "false").lower() == "true"
                if not skip_validation:
                    is_valid, invalid_count, invalid_samples = await self._validate_foreign_key_data(
                        conn, table_name, col.name, ref_table, ref_col
                    )
                    
                    if not is_valid:
                        error_msg = (
                            f"无法添加外键约束 {fk_name}：\n"
                            f"- 表 {table_name} 中存在 {invalid_count} 行数据违反外键约束\n"
                            f"- 违反约束的示例数据：{invalid_samples[:5]}\n"
                            f"- 请先清理或修正这些数据后再迁移"
                        )
                        if is_dev:
                            logger.warning(f"[开发模式] {error_msg}，将跳过外键约束")
                            continue
                        else:
                            raise ValueError(error_msg)
                
                # 添加外键约束
                try:
                    fk_sql = self._get_foreign_key_constraint_sql(
                        table_name, col.name, ref_table, ref_col, fk_name
                    )
                    await conn.execute(text(fk_sql))
                    logger.info(f"已为表 {table_name} 的列 {col.name} 添加外键约束 {fk_name}")
                except Exception as e:
                    if is_dev:
                        logger.warning(f"[开发模式] 添加外键约束失败: {e}")
                    else:
                        raise
        
        # 3. 添加索引
        for idx in model_class.__table__.indexes:
            if idx.name and not idx.unique:
                try:
                    idx_cols = ', '.join([f'"{col.name}"' for col in idx.columns])
                    create_idx_sql = text(
                        f'CREATE INDEX IF NOT EXISTS "{idx.name}" '
                        f'ON "{table_name}" ({idx_cols})'
                    )
                    await conn.execute(create_idx_sql)
                    logger.info(f"已为表 {table_name} 添加索引 {idx.name}")
                except Exception as e:
                    logger.warning(f"添加索引失败: {e}")
        
        # 4. 处理隐式索引
        for col in model_class.__table__.columns:
            if hasattr(col, 'index') and col.index and not col.primary_key:
                has_explicit_idx = False
                for idx in model_class.__table__.indexes:
                    if any(c.name == col.name for c in idx.columns):
                        has_explicit_idx = True
                        break
                
                if not has_explicit_idx:
                    implicit_idx_name = f"{table_name}_{col.name}_idx"
                    try:
                        create_idx_sql = text(
                            f'CREATE INDEX IF NOT EXISTS "{implicit_idx_name}" '
                            f'ON "{table_name}" ("{col.name}")'
                        )
                        await conn.execute(create_idx_sql)
                        logger.info(f"已为表 {table_name} 的列 {col.name} 添加隐式索引")
                    except Exception as e:
                        logger.warning(f"添加隐式索引失败: {e}")
        
        # 5. 修复序列
        await self._fix_sequence_for_table(conn, table_name, model_class)
        
        logger.info(f"表 {table_name} 增量迁移完成")

    async def create_default_table(self, conn, base_class: Type[DeclarativeMeta]):
        """
        创建默认表结构，自动检查和同步表结构

        Args:
            conn: 数据库连接对象
            base_class: declarative_base 创建的基类
        """
        is_dev = self._is_development_mode()
        is_prod = self._is_production_mode()
        force_rebuild = os.getenv("POSTGRE_FORCE_REBUILD", "false").lower() == "true"
        
        # 获取所有继承自该基类的模型
        tables_to_create = []
        tables_to_recreate = []
        tables_to_migrate_incremental = []

        for mapper in base_class.registry.mappers:
            model_class = mapper.class_
            table_name = model_class.__tablename__

            logger.info(f"检查表: {table_name}")

            # 检查表是否存在
            table_exists = await self._check_table_exists(conn, table_name)

            if table_exists:
                # 表存在，检查结构是否一致
                existing_structure = await self._get_existing_table_structure(conn, table_name)
                model_structure = self._get_model_table_structure(model_class)

                if not self._compare_table_structures(existing_structure, model_structure):
                    logger.info(f"表 {table_name} 结构不一致")
                    
                    # 开发环境：如果表无数据，直接删除重建
                    if is_dev:
                        has_rows_query = text(f'SELECT EXISTS (SELECT 1 FROM "{table_name}" LIMIT 1)')
                        has_rows_result = await conn.execute(has_rows_query)
                        has_rows = bool(has_rows_result.scalar())
                        
                        if not has_rows:
                            logger.info(f"[开发模式] 表 {table_name} 无数据，将直接删除重建")
                            await self._drop_table(conn, table_name)
                            tables_to_create.append((table_name, model_class))
                            continue
                    
                    # 生产环境或开发环境有数据：使用增量迁移
                    if is_prod or (is_dev and not force_rebuild):
                        logger.info(f"表 {table_name} 将使用增量迁移")
                        tables_to_migrate_incremental.append((table_name, model_class))
                    else:
                        # 开发环境且允许强制重建
                        logger.info(f"表 {table_name} 将重建（强制重建模式）")
                        tables_to_recreate.append((table_name, model_class))
                else:
                    logger.info(f"表 {table_name} 结构一致，检查序列配置")
                    # 即使结构一致，也要检查并修复序列配置
                    await self._fix_sequence_for_table(conn, table_name, model_class)
            else:
                # 表不存在，需要创建
                logger.info(f"表 {table_name} 不存在，将创建")
                tables_to_create.append((table_name, model_class))

        # 针对需要重建的表，执行原子迁移：创建临时新表 -> 复制交集列数据 -> 交换表名 -> 删除旧表
        for table_name, model_class in tables_to_recreate:
            try:
                # 读取旧表结构与模型结构
                existing_structure = await self._get_existing_table_structure(conn, table_name)
                model_structure = self._get_model_table_structure(model_class)

                # 校验：若存在新增且为 NOT NULL 的列
                added_not_null_cols = [
                    col_name for col_name, info in model_structure.items()
                    if col_name not in existing_structure and info.get('nullable') is False
                ]
                if added_not_null_cols:
                    if is_dev or force_rebuild:
                        logger.warning(
                            f"[开发模式] 表 {table_name} 存在新增 NOT NULL 列: {added_not_null_cols}，"
                            f"将使用默认值或允许 NULL 进行迁移"
                        )
                    elif not force_rebuild:
                        raise ValueError(
                            f"表 {table_name} 存在新增且为 NOT NULL 的列，无法安全迁移: {added_not_null_cols}"
                        )

                # 检查旧表是否有数据
                has_rows_query = text(f'SELECT EXISTS (SELECT 1 FROM "{table_name}" LIMIT 1)')
                has_rows_result = await conn.execute(has_rows_query)
                has_rows = bool(has_rows_result.scalar())

                # 生成临时表名（同库内唯一），最终表名保持与旧表一致
                timestamp_suffix = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
                temp_table_name = f"{table_name}__tmp__{timestamp_suffix}"
                backup_table_name = f"{table_name}__old__{timestamp_suffix}"

                # 使用原始 SQL 创建临时表（不包含外键约束）
                async def _create_temp_table_without_fk():
                    """创建临时表，仅包含列定义，不包含外键约束"""
                    columns_def = []
                    for col in model_class.__table__.columns:
                        col_def = f'"{col.name}" {self._get_postgresql_type(col.type)}'
                        if col.primary_key:
                            col_def += ' PRIMARY KEY'
                        if not col.nullable and not col.primary_key:
                            col_def += ' NOT NULL'
                        columns_def.append(col_def)
                    
                    # 创建表（不包含外键和索引）
                    create_sql = f'CREATE TABLE "{temp_table_name}" ({", ".join(columns_def)})'
                    await conn.execute(text(create_sql))
                
                await _create_temp_table_without_fk()

                if has_rows:
                    # 计算交集列（仅复制旧表中存在，且新表也存在的列）
                    common_columns = [
                        col for col in model_structure.keys() if col in existing_structure
                    ]
                    if common_columns:
                        cols_csv = ', '.join([f'"{c}"' for c in common_columns])
                        insert_sql = text(
                            f'INSERT INTO "{temp_table_name}" ({cols_csv})\n'
                            f'SELECT {cols_csv} FROM "{table_name}"'
                        )
                        await conn.execute(insert_sql)

                # 交换表名：旧表改为备份名，临时表改为正式名
                await conn.execute(text(f'ALTER TABLE "{table_name}" RENAME TO "{backup_table_name}"'))
                await conn.execute(text(f'ALTER TABLE "{temp_table_name}" RENAME TO "{table_name}"'))

                # 添加外键约束（如果模型中有定义）
                for col in model_class.__table__.columns:
                    for fk in col.foreign_keys:
                        # 生成外键约束名称
                        fk_name = f'fk_{table_name}_{col.name}'
                        # 获取引用的表和列
                        ref_table = fk.column.table.name
                        ref_col = fk.column.name
                        # 添加外键约束
                        try:
                            alter_sql = text(
                                f'ALTER TABLE "{table_name}" '
                                f'ADD CONSTRAINT "{fk_name}" '
                                f'FOREIGN KEY ("{col.name}") '
                                f'REFERENCES "{ref_table}" ("{ref_col}")'
                            )
                            await conn.execute(alter_sql)
                            logger.info(f"已为表 {table_name} 的列 {col.name} 添加外键约束")
                        except Exception as e:
                            logger.warning(f"添加外键约束失败（可能已存在）: {e}")

                # 添加索引（如果模型中有定义）
                for idx in model_class.__table__.indexes:
                    # 跳过主键索引和唯一约束（已在列定义中处理）
                    if idx.name and not idx.unique:
                        try:
                            idx_cols = ', '.join([f'"{col.name}"' for col in idx.columns])
                            create_idx_sql = text(
                                f'CREATE INDEX IF NOT EXISTS "{idx.name}" '
                                f'ON "{table_name}" ({idx_cols})'
                            )
                            await conn.execute(create_idx_sql)
                            logger.info(f"已为表 {table_name} 添加索引 {idx.name}")
                        except Exception as e:
                            logger.warning(f"添加索引失败: {e}")
                
                # 处理列上的 index=True（隐式索引）
                for col in model_class.__table__.columns:
                    # 检查列是否有 index=True 但不在 table.indexes 中
                    if hasattr(col, 'index') and col.index and not col.primary_key:
                        # 检查是否已有显式索引（通过列名匹配）
                        has_explicit_idx = False
                        for idx in model_class.__table__.indexes:
                            # 检查索引中是否包含此列
                            if any(c.name == col.name for c in idx.columns):
                                has_explicit_idx = True
                                break
                        
                        if not has_explicit_idx:
                            # 创建隐式索引（SQLAlchemy 通常命名为 {table_name}_{column_name}_idx）
                            implicit_idx_name = f"{table_name}_{col.name}_idx"
                            try:
                                create_idx_sql = text(
                                    f'CREATE INDEX IF NOT EXISTS "{implicit_idx_name}" '
                                    f'ON "{table_name}" ("{col.name}")'
                                )
                                await conn.execute(create_idx_sql)
                                logger.info(f"已为表 {table_name} 的列 {col.name} 添加隐式索引")
                            except Exception as e:
                                logger.warning(f"添加隐式索引失败: {e}")

                # 删除旧表备份
                await self._drop_table(conn, backup_table_name)

                logger.info(f"表 {table_name} 已根据模型结构完成原子迁移")
            except Exception as e:
                logger.error(f"表 {table_name} 迁移失败，回滚事务: {e}")
                raise

        # 执行增量迁移（生产环境或开发环境有数据时）
        for table_name, model_class in tables_to_migrate_incremental:
            try:
                await self._migrate_table_incremental(conn, table_name, model_class)
            except Exception as e:
                logger.error(f"表 {table_name} 增量迁移失败: {e}")
                if is_prod:
                    raise
                else:
                    logger.warning(f"[开发模式] 增量迁移失败，将继续处理其他表: {e}")

        # 创建所有需要新建的表
        if tables_to_create:
            await conn.run_sync(base_class.metadata.create_all)
            logger.info(f"表创建完成，共创建 {len(tables_to_create)} 个表")

    async def create_async_session(self, host: str, port: int, database: str, user: str, password: str):
        """创建异步数据库会话"""
        # 构建 PostgreSQL 异步连接 URL
        database_url = f'postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}'

        # 创建异步引擎
        self.engine = create_async_engine(
            database_url,
            pool_size=20,
            max_overflow=80,
            pool_timeout=300,
            pool_pre_ping=True,
            pool_recycle=1200,
            echo=False,
            future=True
        )

        # 创建会话工厂
        self._session_maker = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info(f"PostgreSQL 异步引擎创建成功: {host}:{port}/{database}")
        return self._session_maker

    async def init(self, base_classes: List[Type[DeclarativeMeta]] = None):
        """
        初始化数据库连接和表结构

        Args:
            base_classes: declarative_base 基类列表，用于创建表
        """
        logger.info("初始化 PostgreSQL 异步数据库")

        # 从配置中获取数据库连接信息（优先使用环境变量，然后是配置文件）
        try:
            host = os.getenv('POSTGRES_HOST') or config.get('POSTGREDB', 'Host', fallback='localhost')
            port = int(os.getenv('POSTGRES_PORT', 0)) or config.getint('POSTGREDB', 'Port', fallback=5432)
            database = os.getenv('POSTGRES_DB') or config.get('POSTGREDB', 'Database', fallback='kahunabot')
            user = os.getenv('POSTGRES_USER') or config.get('POSTGREDB', 'User', fallback='kahunabot')
            password = os.getenv('POSTGRES_PASSWORD') or config.get('POSTGREDB', 'Password', fallback='kahunabot')

            logger.info(f"PostgreSQL 配置: {host}:{port}/{database} (用户: {user})")
        except Exception as e:
            logger.warning(f"读取 PostgreSQL 配置失败，使用默认值: {e}")
            host = 'localhost'
            port = 5432
            database = 'kahunabot'
            user = 'kahunabot'
            password = 'kahunabot'

        # 创建会话
        await self.create_async_session(host, port, database, user, password)

        # 创建表结构
        if not base_classes:
            from .model import all_model
            base_classes = all_model
        async with self.engine.begin() as conn:
            for base_class in base_classes:
                await self.create_default_table(conn, base_class)

        logger.info("PostgreSQL 数据库初始化完成")

    @asynccontextmanager
    async def get_session(self):
        """获取新的数据库会话（异步上下文管理器）"""
        if not self._session_maker:
            raise RuntimeError("数据库未初始化，请先调用 init() 方法")

        session = self._session_maker()
        try:
            yield session
            # 如果没有异常，提交事务
            if session.in_transaction():
                await session.commit()
        except Exception:
            # 如果有异常，回滚事务
            if session.in_transaction():
                await session.rollback()
            raise
        finally:
            # 无论如何都要关闭会话，将连接返回到连接池
            try:
                await session.close()
            except Exception as e:
                logger.warning(f"关闭数据库会话时出错: {e}")

    async def close(self):
        """关闭数据库连接"""
        if self.engine:
            await self.engine.dispose()
            logger.info("PostgreSQL 数据库连接已关闭")

class RedisDatabaseManager():
    def __init__(self):
        self._redis = None
    
    async def init(self):
        try:
            host = os.getenv('REDIS_HOST') or config.get('REDIS', 'Host', fallback='localhost')
            port = int(os.getenv('REDIS_PORT', 0)) or config.getint('REDIS', 'Port', fallback=6379)
        except Exception as e:
            logger.error(f"读取 Redis 配置失败: {e}")
            host = 'localhost'
            port = 6379

        self._redis = Redis(
            host=host,
            port=port,
            decode_responses=True
        )

        # 删除forever:开头的key之外的数据
        # await self._redis.flushall()
        
        logger.info(f"Redis 连接成功: {host}:{port}")

    @property
    def redis(self):
        if not self._redis:
            raise RuntimeError("Redis 未初始化，请先调用 init() 方法")
        return self._redis

    @property
    def r(self):
        if not self._redis:
            raise RuntimeError("Redis 未初始化，请先调用 init() 方法")
        return self._redis

    async def delete_keys_by_pattern(self, pattern: str):
        redis = self._redis
        if not redis:
            raise RuntimeError("Redis 未初始化，请先调用 init() 方法")
        """根据模式删除 key（推荐方式）"""
        deleted_count = 0
        cursor = 0
        
        while True:
            # SCAN 返回 (cursor, [keys])
            cursor, keys = await redis.scan(cursor, match=pattern, count=100)
            
            if keys:
                # 批量删除
                deleted = await redis.delete(*keys)
                deleted_count += deleted
            
            # cursor 为 0 表示扫描完成
            if cursor == 0:
                break
        
        return deleted_count

class Neo4jDatabaseManager():
    def __init__(self):
        self._neo4j = None
        self.semaphore = asyncio.Semaphore(50)
    
    async def init(self):
        host = os.getenv('NEO4J_HOST') or config.get('NEO4J', 'Host', fallback='localhost')
        port = int(os.getenv('NEO4J_PORT', 0)) or config.getint('NEO4J', 'Port', fallback=7687)
        username = os.getenv('NEO4J_USERNAME') or config.get('NEO4J', 'Username', fallback='neo4j')
        password = os.getenv('NEO4J_PASSWORD') or config.get('NEO4J', 'Password', fallback='neo4j')

        self._neo4j = AsyncGraphDatabase.driver(
            f'bolt://{host}:{port}',
            auth=(username, password),
            max_connection_pool_size=200,  # 增加连接池大小以支持高并发
            connection_acquisition_timeout=120  # 增加连接获取超时时间到120秒
        )
        
        # 验证连接
        await self.verify_connectivity()
        logger.info(f"Neo4j 连接成功: {host}:{port}")

        # 初始化数据库模式（创建索引和约束）
        # await self.clean_all()
        await self.clean_all_index()
        from .neo4j_model_manager import neo4j_model_manager
        await neo4j_model_manager.init_schema()

    async def verify_connectivity(self):
        """验证连接是否可用"""
        try:
            await self._neo4j.verify_connectivity()
        except Exception as e:
            logger.error(f"Neo4j 连接验证失败: {e}")
            raise

    @property
    def neo4j(self):
        if not self._neo4j:
            raise RuntimeError("Neo4j 未初始化，请先调用 init() 方法")
        return self._neo4j

    @asynccontextmanager
    async def get_session(self):
        """获取 Neo4j 会话（异步上下文管理器）"""
        if not self._neo4j:
            raise RuntimeError("Neo4j 未初始化，请先调用 init() 方法")
        
        session = self._neo4j.session()
        try:
            yield session
        finally:
            await session.close()

    @asynccontextmanager
    async def get_transaction(self):
        """获取 Neo4j 事务（异步上下文管理器）"""
        async with self.get_session() as session:
            tx = await session.begin_transaction()
            try:
                yield tx
                await tx.commit()
            except Exception as e:
                # 检查事务是否已关闭（例如死锁时 Neo4j 会自动关闭事务）
                # 如果事务已关闭，尝试 rollback 会抛出 TransactionError
                try:
                    await tx.rollback()
                except TransactionError:
                    # 事务已关闭（例如由于死锁），这是正常情况，不需要回滚
                    # 记录调试信息但不抛出异常
                    logger.debug(f"Neo4j 事务已关闭，跳过回滚: {type(e).__name__}")
                except Exception as rollback_error:
                    # 其他类型的回滚错误，记录警告
                    logger.warning(f"Neo4j 事务回滚失败: {rollback_error}")
                raise
            finally:
                # 确保关闭事务，即使已经关闭也不会出错
                try:
                    await tx.close()
                except (TransactionError, Exception):
                    # 事务可能已经关闭，忽略关闭错误
                    pass

    async def close(self):
        """关闭 Neo4j 连接"""
        if self._neo4j:
            await self._neo4j.close()
            logger.info("Neo4j 连接已关闭")

    async def clean_all_data(self):
        """清理所有数据（节点和关系）"""
        async with self.get_transaction() as tx:
            result = await tx.run("MATCH (n) DETACH DELETE n RETURN count(n) as deleted_count")
            record = await result.single()
            deleted_count = record["deleted_count"] if record else 0
            logger.info(f"Neo4j 已清理所有数据，删除 {deleted_count} 个节点")
            return deleted_count

    async def clean_all_indexes(self):
        """清理所有索引（不包括由约束拥有的索引）"""
        async with self.get_session() as session:
            # 获取所有索引
            query = "SHOW INDEXES"
            result = await session.run(query)

            # 仅收集不属于约束的索引
            indexes = []
            async for record in result:
                index_name = record.get("name")
                owning_constraint = record.get("owningConstraint")
                # 只删除独立索引；由约束拥有的索引需要通过删除约束来移除
                if index_name and not owning_constraint:
                    indexes.append(index_name)

            if not indexes:
                logger.info("Neo4j 没有找到需要删除的独立索引")
                return 0

            # 删除所有独立索引
            async with self.get_transaction() as tx:
                deleted_count = 0
                for index_name in indexes:
                    try:
                        await tx.run(f"DROP INDEX {index_name} IF EXISTS")
                        deleted_count += 1
                        logger.info(f"删除索引: {index_name}")
                    except Exception as e:
                        logger.warning(f"删除索引失败 {index_name}: {e}")

                logger.info(f"Neo4j 已删除 {deleted_count} 个独立索引")
                return deleted_count

    async def clean_all_constraints(self):
        """清理所有约束"""
        async with self.get_session() as session:
            # 获取所有约束
            query = "SHOW CONSTRAINTS"
            result = await session.run(query)
            
            constraints = []
            async for record in result:
                constraint_name = record.get("name")
                if constraint_name:
                    constraints.append(constraint_name)
            
            if not constraints:
                logger.info("Neo4j 没有找到需要删除的约束")
                return 0
            
            # 删除所有约束
            async with self.get_transaction() as tx:
                deleted_count = 0
                for constraint_name in constraints:
                    try:
                        await tx.run(f"DROP CONSTRAINT {constraint_name} IF EXISTS")
                        deleted_count += 1
                        logger.info(f"删除约束: {constraint_name}")
                    except Exception as e:
                        logger.warning(f"删除约束失败 {constraint_name}: {e}")
                
                logger.info(f"Neo4j 已删除 {deleted_count} 个约束")
                return deleted_count

    async def clean_all(self):
        """清理所有数据、约束和索引（谨慎使用）"""
        logger.warning("开始清理 Neo4j 数据库的所有数据、索引和约束...")
        
        # 1. 清理所有数据
        deleted_nodes = await self.clean_all_data()
        
        # 2. 清理所有约束（先删除约束，再删除剩余索引）
        deleted_constraints = await self.clean_all_constraints()

        # 3. 清理所有独立索引
        deleted_indexes = await self.clean_all_indexes()
        
        logger.warning(
            f"Neo4j 数据库清理完成："
            f"删除 {deleted_nodes} 个节点, "
            f"删除 {deleted_indexes} 个索引, "
            f"删除 {deleted_constraints} 个约束"
        )
        
        return {
            "nodes_deleted": deleted_nodes,
            "indexes_deleted": deleted_indexes,
            "constraints_deleted": deleted_constraints
        }

    async def clean_all_index(self):
        """清理所有索引（兼容旧方法名）"""
        return await self.clean_all_indexes()

neo4j_manager = Neo4jDatabaseManager()
postgres_manager = PostgreDatabaseManager()
redis_manager = RedisDatabaseManager()