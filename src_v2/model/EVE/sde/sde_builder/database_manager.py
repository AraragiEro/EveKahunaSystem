"""
SDE 数据库管理模块
管理独立的 sde 数据库连接
"""
import os
import asyncio
from typing import List, Type
from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager

from src_v2.core.config.config import config
from src_v2.core.log import logger

# 创建独立的 SDE 模型基类
SDEModel = declarative_base()


class SDEDatabaseManager:
    """SDE 数据库管理器，管理独立的 sde 数据库连接"""
    
    def __init__(self):
        self.session = None
        self.engine = None
        self._session_maker = None
        # 限制并发连接数的信号量，设置为 80（略小于 max_overflow=80，确保不超过连接池大小）
        self.semaphore = asyncio.Semaphore(80)
    
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
        
        # 创建异步会话工厂
        self._session_maker = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        logger.info(f"SDE PostgreSQL 异步引擎创建成功: {host}:{port}/{database}")
        return self._session_maker
    
    async def ensure_database_exists(self, host: str, port: int, database: str, user: str, password: str) -> bool:
        """
        确保数据库存在，如果不存在则创建
        
        Args:
            host: 数据库主机
            port: 数据库端口
            database: 数据库名
            user: 用户名
            password: 密码
        
        Returns:
            是否成功
        """
        try:
            # 先尝试连接到目标数据库
            test_url = f'postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}'
            test_engine = create_async_engine(test_url, pool_pre_ping=True)
            async with test_engine.connect() as conn:
                # 连接成功，数据库已存在
                await test_engine.dispose()
                logger.info(f"数据库 {database} 已存在")
                return True
        except Exception as e:
            # 检查是否是数据库不存在的错误
            error_str = str(e).lower()
            is_db_not_exist = (
                'database' in error_str and 'does not exist' in error_str
            ) or 'invalidcatalognameerror' in error_str
            
            if is_db_not_exist:
                logger.info(f"数据库 {database} 不存在，尝试创建...")
            else:
                # 其他连接错误（如认证失败、网络问题等）
                logger.warning(f"连接数据库 {database} 失败: {e}")
                logger.info("尝试创建数据库...")
            
            try:
                # 连接到 postgres 系统数据库来创建新数据库
                postgres_url = f'postgresql+asyncpg://{user}:{password}@{host}:{port}/postgres'
                postgres_engine = create_async_engine(postgres_url, pool_pre_ping=True)
                
                async with postgres_engine.begin() as conn:
                    from sqlalchemy import text
                    # 检查数据库是否已存在（可能在其他连接中刚创建）
                    check_sql = text("""
                        SELECT 1 FROM pg_database WHERE datname = :dbname
                    """)
                    result = await conn.execute(check_sql, {"dbname": database})
                    exists = result.first() is not None
                    
                    if not exists:
                        # 创建数据库
                        create_sql = text(f'CREATE DATABASE "{database}"')
                        await conn.execute(create_sql)
                        logger.info(f"已创建数据库: {database}")
                    else:
                        logger.info(f"数据库 {database} 已存在（在其他连接中创建）")
                
                await postgres_engine.dispose()
                return True
            except Exception as create_error:
                logger.error(f"创建数据库失败: {create_error}")
                logger.error("=" * 60)
                logger.error("数据库自动创建失败，请手动创建数据库")
                logger.error("=" * 60)
                logger.error("手动创建步骤：")
                logger.error("")
                logger.error("方法一：使用 psql 命令行工具")
                logger.error(f"  1. 连接到 PostgreSQL: psql -U {user} -h {host} -p {port} -d postgres")
                logger.error(f"  2. 执行创建命令: CREATE DATABASE \"{database}\";")
                logger.error(f"  3. 退出: \\q")
                logger.error("")
                logger.error("方法二：使用 SQL 命令（需要管理员权限）")
                logger.error(f"  CREATE DATABASE \"{database}\";")
                logger.error("")
                logger.error("方法三：使用 pgAdmin 或其他图形化工具")
                logger.error(f"  1. 连接到 PostgreSQL 服务器 ({host}:{port})")
                logger.error(f"  2. 右键点击 'Databases' -> 'Create' -> 'Database...'")
                logger.error(f"  3. 输入数据库名称: {database}")
                logger.error(f"  4. 点击 'Save' 保存")
                logger.error("")
                logger.error("创建完成后，请重新运行更新脚本")
                logger.error("=" * 60)
                logger.error("")
                logger.error("如果仍然失败，请检查：")
                logger.error("1. PostgreSQL 服务是否正在运行")
                logger.error(f"2. 用户 '{user}' 是否具有 CREATEDB 权限")
                logger.error(f"3. 连接信息是否正确 (host={host}, port={port})")
                logger.error(f"4. 防火墙是否允许连接到 PostgreSQL 端口 {port}")
                return False
    
    async def init(self, base_classes: List[Type[DeclarativeMeta]] = None):
        """
        初始化数据库连接和表结构
        
        Args:
            base_classes: declarative_base 基类列表，用于创建表
        """
        logger.info("初始化 SDE PostgreSQL 异步数据库")
        
        # 从配置中获取数据库连接信息（优先使用环境变量，然后是配置文件）
        try:
            host = os.getenv('SDE_POSTGRES_HOST') or config.get('SDEDB', 'Host', fallback='localhost')
            port = int(os.getenv('SDE_POSTGRES_PORT', 0)) or config.getint('SDEDB', 'Port', fallback=5432)
            database = os.getenv('SDE_POSTGRES_DB') or config.get('SDEDB', 'Database', fallback='sde')
            user = os.getenv('SDE_POSTGRES_USER') or config.get('SDEDB', 'User', fallback='sde')
            password = os.getenv('SDE_POSTGRES_PASSWORD') or config.get('SDEDB', 'Password', fallback='sde')
            
            logger.info(f"SDE PostgreSQL 配置: {host}:{port}/{database} (用户: {user})")
        except Exception as e:
            logger.warning(f"读取 SDE PostgreSQL 配置失败，使用默认值: {e}")
            host = 'localhost'
            port = 5432
            database = 'sde'
            user = 'sde'
            password = 'sde'
        
        # 确保数据库存在
        db_exists = await self.ensure_database_exists(host, port, database, user, password)
        if not db_exists:
            logger.error("无法确保数据库存在，初始化失败")
            raise RuntimeError(f"无法创建或连接到数据库: {database}")
        
        # 创建会话
        await self.create_async_session(host, port, database, user, password)
        
        # 创建表结构
        if base_classes and self.engine:
            async with self.engine.begin() as conn:
                from src_v2.core.database.connect_manager import PostgreDatabaseManager
                db_manager = PostgreDatabaseManager()
                for base_class in base_classes:
                    await db_manager.create_default_table(conn, base_class)
        
        logger.info("SDE PostgreSQL 数据库初始化完成")
    
    @asynccontextmanager
    async def get_session(self):
        """获取新的数据库会话（异步上下文管理器）"""
        if not self._session_maker:
            raise RuntimeError("数据库未初始化，请先调用 init() 方法")
        
        # 使用信号量限制并发连接数，防止连接池耗尽
        async with self.semaphore:
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
    
    @asynccontextmanager
    async def get_readonly_session(self):
        """获取只读数据库会话（异步上下文管理器，无事务开销）
        
        使用 autocommit 模式，不开启事务，适合所有只读查询操作。
        相比 get_session()，减少了事务开启和提交的开销。
        """
        if not self._session_maker:
            raise RuntimeError("数据库未初始化，请先调用 init() 方法")
        
        # 使用信号量限制并发连接数，防止连接池耗尽
        async with self.semaphore:
            session = self._session_maker()
            try:
                # 对于只读查询，不需要事务，直接执行
                # SQLAlchemy 默认情况下，如果没有显式开启事务，查询会在 autocommit 模式下执行
                yield session
                # 不提交事务（因为没有开启事务，避免不必要的 commit 开销）
            except Exception:
                # 只读查询失败时也不需要回滚（因为没有事务）
                raise
            finally:
                # 无论如何都要关闭会话，将连接返回到连接池
                try:
                    await session.close()
                except Exception as e:
                    logger.warning(f"关闭只读数据库会话时出错: {e}")
    
    async def close(self):
        """关闭数据库连接"""
        if self.engine:
            await self.engine.dispose()
            logger.info("SDE PostgreSQL 数据库连接已关闭")

