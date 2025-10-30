from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, AnyStr, Type
import os
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, JSON
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import event
from win32gui import PostThreadMessage

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

    async def create_default_table(self, conn, base_class: Type[DeclarativeMeta]):
        """
        创建默认表结构，自动检查和同步表结构

        Args:
            conn: 数据库连接对象
            base_class: declarative_base 创建的基类
        """
        # 获取所有继承自该基类的模型
        tables_to_create = []
        tables_to_recreate = []

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
                    logger.info(f"表 {table_name} 结构不一致，将重建")
                    tables_to_recreate.append((table_name, model_class))
                else:
                    logger.info(f"表 {table_name} 结构一致，跳过")
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

                # 校验：若存在新增且为 NOT NULL 的列，则直接抛出异常
                added_not_null_cols = [
                    col_name for col_name, info in model_structure.items()
                    if col_name not in existing_structure and info.get('nullable') is False
                ]
                if added_not_null_cols and os.getenv("POSTGRE_FORCE_REBUILD", "false").lower() != "true":
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

                # 使用 SQLAlchemy 根据模型定义创建临时新表
                def _create_temp_table(sync_conn):
                    # 将模型表复制到新的 MetaData，并命名为临时表名
                    new_meta = model_class.metadata.__class__()
                    new_table = model_class.__table__.tometadata(new_meta, name=temp_table_name)
                    new_table.create(bind=sync_conn)
                await conn.run_sync(_create_temp_table)

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

                # 删除旧表备份
                await self._drop_table(conn, backup_table_name)

                logger.info(f"表 {table_name} 已根据模型结构完成原子迁移")
            except Exception as e:
                logger.error(f"表 {table_name} 迁移失败，回滚事务: {e}")
                raise

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
            from .model import __all__
            base_classes = __all__
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
            await session.commit()  # 如果没有异常，提交事务
        except Exception:
            await session.rollback()  # 如果有异常，回滚事务
            raise
        finally:
            await session.close()  # 无论如何都要关闭会话

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

        logger.info(f"Redis 连接成功: {host}:{port}")

    @property
    def redis(self):
        if not self._redis:
            raise RuntimeError("Redis 未初始化，请先调用 init() 方法")
        return self._redis

postgres_manager = PostgreDatabaseManager()
redis_manager = RedisDatabaseManager()