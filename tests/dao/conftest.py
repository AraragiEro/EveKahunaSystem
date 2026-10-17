"""
DAO 层测试 conftest

提供 SQLite in-memory 数据库 fixture，Mock get_postgres_manager() 以支持 DAO 单元测试。
"""
import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from sqlalchemy import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 导入 PostgreModel 以获取 metadata（表注册信息）
from src_v2.core.database.connect_manager import PostgreModel

# 导入 model 模块，确保所有模型表注册到 PostgreModel.metadata
import src_v2.core.database.model  # noqa: F401 - 注册模型表


# ── 辅助：使 PostgreSQL 专有类型兼容 SQLite ──────────────────────────
def _patch_pg_types_for_sqlite():
    """将 metadata 中 SQLite 不支持的类型替换为兼容类型。

    - JSONB → JSON（SQLite 用 TEXT 存储 JSON）
    - ARRAY → JSON（SQLite 无原生数组，用 JSON 文本存储）
    """
    from sqlalchemy import JSON

    for table in list(PostgreModel.metadata.tables.values()):
        for col in list(table.columns):
            # ARRAY 类型（包括 ARRAY(JSONB)、ARRAY(Integer) 等）
            if isinstance(col.type, ARRAY):
                col.type = JSON()
            # JSONB 类型
            elif hasattr(col.type, "astext_type"):
                # JSONB 继承自 JSON，通过 astext_type 属性识别
                from sqlalchemy.dialects.postgresql import JSONB as PGJSONB

                if isinstance(col.type, PGJSONB):
                    col.type = JSON()


# ── SQLite 内存数据库 Fixture ─────────────────────────────────────────
@pytest_asyncio.fixture(scope="function")
async def db_session():
    """
    创建 SQLite in-memory 数据库并 Mock get_postgres_manager。

    - 每次测试创建全新引擎和表，确保隔离性
    - Mock 的 get_session() 在正常退出时自动 commit
    - 测试结束后 dispose 引擎
    """
    # 修正 PostgreSQL 专有类型 → SQLite 兼容类型
    _patch_pg_types_for_sqlite()

    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)

    # 创建所有注册表
    async with engine.begin() as conn:
        await conn.run_sync(PostgreModel.metadata.create_all)

    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Mock get_session() — 模拟 connect_manager.PostgreDatabaseManager.get_session()
    @asynccontextmanager
    async def mock_get_session():
        session = session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    mock_manager = MagicMock()
    mock_manager.get_session = mock_get_session
    mock_manager.session_maker = session_maker

    # patch kahuna_database_utils_v2 模块中的 get_postgres_manager 引用
    with patch(
        "src_v2.core.database.kahuna_database_utils_v2.get_postgres_manager",
        return_value=mock_manager,
    ):
        yield

    await engine.dispose()
