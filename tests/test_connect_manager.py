"""
PostgreDatabaseManager 测试用例
测试数据库管理器的各项功能
"""
import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch, call
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base

# 假设 connect_manager.py 的导入路径
# 根据实际项目结构调整导入路径
import sys
import os
# sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src_v2.core.database import connect_manager
from src_v2.core.database.connect_manager import PostgreDatabaseManager
TARGET_MODULE_PATH = 'src_v2.core.database.connect_manager'
# 创建测试用的模型基类
PostgreBaseModel = declarative_base()

class PostgreModel(PostgreBaseModel):
    """测试用的模型类"""
    __tablename__ = 'test_table'

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    description = Column(Text)
    created_at = Column(DateTime)


class TestPostgreDatabaseManager:
    """PostgreDatabaseManager 测试类"""

    @pytest.fixture
    def manager(self):
        """创建测试用的数据库管理器实例"""
        # 动态导入以避免导入错误
        return PostgreDatabaseManager()

    def test_init(self, manager):
        """测试初始化方法"""
        assert manager.session is None
        assert manager.engine is None
        assert manager._session_maker is None

    @pytest.mark.asyncio
    async def test_check_table_exists_true(self, manager):
        """测试检查表存在的情况"""
        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_conn.execute.return_value = mock_result

        result = await manager._check_table_exists(mock_conn, 'test_table')

        assert result is True
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_table_exists_false(self, manager):
        """测试检查表不存在的情况"""
        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_conn.execute.return_value = mock_result

        result = await manager._check_table_exists(mock_conn, 'nonexistent_table')

        assert result is False
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_existing_table_structure(self, manager):
        """测试获取已存在表的结构"""
        mock_conn = AsyncMock()
        mock_result = [
            ('id', 'integer', None, 'NO', None),
            ('name', 'character varying', 100, 'YES', None),
            ('description', 'text', None, 'YES', None),
        ]
        mock_conn.execute.return_value = mock_result

        structure = await manager._get_existing_table_structure(mock_conn, 'test_table')

        assert 'id' in structure
        assert structure['id']['data_type'] == 'integer'
        assert structure['id']['nullable'] is False
        assert 'name' in structure
        assert structure['name']['max_length'] == 100

    @pytest.mark.asyncio
    async def test_get_existing_table_structure_exception(self, manager):
        """测试获取表结构时发生异常"""
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("Database error")

        structure = await manager._get_existing_table_structure(mock_conn, 'test_table')

        assert structure == {}

    def test_get_model_table_structure(self, manager):
        """测试获取模型定义的表结构"""
        structure = manager._get_model_table_structure(PostgreModel)

        assert 'id' in structure
        assert structure['id']['primary_key'] is True
        assert 'name' in structure
        assert 'description' in structure
        assert 'created_at' in structure

    def test_compare_table_structures_identical(self, manager):
        """测试比较相同的表结构"""
        existing = {
            'id': {'data_type': 'integer', 'nullable': False},
            'name': {'data_type': 'varchar', 'nullable': True}
        }
        model = {
            'id': {'type': 'INTEGER', 'nullable': False},
            'name': {'type': 'VARCHAR', 'nullable': True}
        }

        result = manager._compare_table_structures(existing, model)

        assert result is True

    def test_compare_table_structures_different_column_count(self, manager):
        """测试比较不同列数的表结构"""
        existing = {
            'id': {'data_type': 'integer', 'nullable': False},
            'name': {'data_type': 'varchar', 'nullable': True}
        }
        model = {
            'id': {'type': 'INTEGER', 'nullable': False},
            'name': {'type': 'VARCHAR', 'nullable': True},
            'email': {'type': 'VARCHAR', 'nullable': True}
        }

        result = manager._compare_table_structures(existing, model)

        assert result is False

    def test_compare_table_structures_missing_column(self, manager):
        """测试比较缺少列的表结构"""
        existing = {
            'id': {'data_type': 'integer', 'nullable': False}
        }
        model = {
            'id': {'type': 'INTEGER', 'nullable': False},
            'name': {'type': 'VARCHAR', 'nullable': True}
        }

        result = manager._compare_table_structures(existing, model)

        assert result is False

    @pytest.mark.asyncio
    async def test_drop_table_success(self, manager):
        """测试成功删除表"""
        mock_conn = AsyncMock()

        await manager._drop_table(mock_conn, 'test_table')

        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_drop_table_failure(self, manager):
        """测试删除表失败"""
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("Cannot drop table")

        with pytest.raises(Exception):
            await manager._drop_table(mock_conn, 'test_table')

    @pytest.mark.asyncio
    async def test_create_async_session(self, manager):
        """测试创建异步会话"""
        with patch(f'{TARGET_MODULE_PATH}.create_async_engine') as mock_create_engine, \
             patch(f'{TARGET_MODULE_PATH}.sessionmaker') as mock_sessionmaker:

            mock_engine = MagicMock()
            mock_create_engine.return_value = mock_engine
            mock_session_maker = MagicMock()
            mock_sessionmaker.return_value = mock_session_maker

            result = await manager.create_async_session(
                host='localhost',
                port=5432,
                database='testdb',
                user='testuser',
                password='testpass'
            )

            assert manager.engine == mock_engine
            assert manager._session_maker == mock_session_maker
            mock_create_engine.assert_called_once()
            mock_sessionmaker.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_default_table_new_table(self, manager):
        """测试创建新表"""
        mock_conn = AsyncMock()

        # 模拟表不存在
        manager._check_table_exists = AsyncMock(return_value=False)
        mock_conn.run_sync = AsyncMock()

        # 创建一个简单的测试基类
        test_base = PostgreModel

        await manager.create_default_table(mock_conn, test_base)

        manager._check_table_exists.assert_called()

    @pytest.mark.asyncio
    async def test_create_default_table_existing_identical(self, manager):
        """测试表已存在且结构相同"""
        mock_conn = AsyncMock()

        # 模拟表存在且结构相同
        manager._check_table_exists = AsyncMock(return_value=True)
        manager._get_existing_table_structure = AsyncMock(return_value={
            'id': {'data_type': 'integer', 'nullable': False}
        })
        manager._get_model_table_structure = Mock(return_value={
            'id': {'type': 'INTEGER', 'nullable': False}
        })
        manager._compare_table_structures = Mock(return_value=True)

        test_base = PostgreModel

        await manager.create_default_table(mock_conn, test_base)

        manager._check_table_exists.assert_called()

    @pytest.mark.asyncio
    async def test_create_default_table_existing_different(self, manager):
        """测试表已存在但结构不同"""
        mock_conn = AsyncMock()

        # 模拟表存在但结构不同
        manager._check_table_exists = AsyncMock(return_value=True)
        manager._get_existing_table_structure = AsyncMock(return_value={
            'id': {'data_type': 'integer', 'nullable': False}
        })
        manager._get_model_table_structure = Mock(return_value={
            'id': {'type': 'INTEGER', 'nullable': False},
            'name': {'type': 'VARCHAR', 'nullable': True}
        })
        manager._compare_table_structures = Mock(return_value=False)
        manager._drop_table = AsyncMock()
        mock_conn.run_sync = AsyncMock()

        test_base = PostgreModel

        await manager.create_default_table(mock_conn, test_base)

        manager._drop_table.assert_called()

    @pytest.mark.asyncio
    async def test_init_with_environment_variables(self, manager):
        """测试使用环境变量初始化"""
        with patch.dict(os.environ, {
            'POSTGRES_HOST': 'test-host',
            'POSTGRES_PORT': '5433',
            'POSTGRES_DB': 'test-db',
            'POSTGRES_USER': 'test-user',
            'POSTGRES_PASSWORD': 'test-pass'
        }), \
        patch.object(manager, 'create_async_session', new_callable=AsyncMock) as mock_create_session, \
        patch.object(manager, 'create_default_table', new_callable=AsyncMock) as mock_create_default_table, \
        patch(f'{TARGET_MODULE_PATH}.create_async_engine') as mock_engine:

            mock_engine_instance = MagicMock()
            mock_engine.return_value = mock_engine_instance
            manager.engine = mock_engine_instance
            mock_engine_instance.begin = MagicMock()
            mock_conn = AsyncMock()
            mock_engine_instance.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine_instance.begin.return_value.__aexit__ = AsyncMock(return_value=None)

            await manager.init(base_classes=[PostgreModel])

            mock_create_session.assert_called_once_with(
                'test-host',  # host
                5433,  # port
                'test-db',  # database
                'test-user',  # user
                'test-pass'  # password
            )
            # 验证 create_default_table 被调用
            mock_create_default_table.assert_called_once_with(mock_conn, PostgreModel)

    @pytest.mark.asyncio
    async def test_init_with_config_file(self, manager):
        """测试使用配置文件初始化"""
        with patch.dict(os.environ, {}, clear=True), \
        patch(f'{TARGET_MODULE_PATH}.config') as mock_config, \
        patch.object(manager, 'create_async_session', new_callable=AsyncMock) as mock_create_session, \
        patch(f'{TARGET_MODULE_PATH}.create_async_engine') as mock_engine:

            mock_config.get.side_effect = lambda section, key, fallback=None: {
                ('POSTGREDB', 'Host'): 'config-host',
                ('POSTGREDB', 'Database'): 'config-db',
                ('POSTGREDB', 'User'): 'config-user',
                ('POSTGREDB', 'Password'): 'config-pass'
            }.get((section, key), fallback)

            mock_config.getint.side_effect = lambda section, key, fallback=None: {
                ('POSTGREDB', 'Port'): 5432
            }.get((section, key), fallback)

            mock_engine_instance = MagicMock()
            mock_engine.return_value = mock_engine_instance
            manager.engine = mock_engine_instance
            mock_engine_instance.begin = MagicMock()
            mock_engine_instance.begin.return_value.__aenter__ = AsyncMock()
            mock_engine_instance.begin.return_value.__aexit__ = AsyncMock()

            await manager.init()

            mock_create_session.assert_called_once()

    def test_get_session_success(self, manager):
        """测试成功获取会话"""
        mock_session_maker = MagicMock()
        mock_session = MagicMock(spec=AsyncSession)
        mock_session_maker.return_value = mock_session
        manager._session_maker = mock_session_maker

        session = manager.get_session()

        assert session == mock_session
        mock_session_maker.assert_called_once()

    def test_get_session_not_initialized(self, manager):
        """测试未初始化时获取会话"""
        with pytest.raises(RuntimeError) as exc_info:
            manager.get_session()

        assert "数据库未初始化" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_close(self, manager):
        """测试关闭数据库连接"""
        mock_engine = AsyncMock()
        manager.engine = mock_engine

        await manager.close()

        mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_engine(self, manager):
        """测试没有引擎时关闭连接"""
        manager.engine = None

        # 不应抛出异常
        await manager.close()


# 集成测试（需要真实的 PostgreSQL 数据库）
@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv('POSTGRES_TEST_ENABLED') != '1',
    reason="需要设置 POSTGRES_TEST_ENABLED=1 环境变量来运行集成测试"
)
class TestPostgreDatabaseManagerIntegration:
    """PostgreDatabaseManager 集成测试类"""

    @pytest_asyncio.fixture
    async def manager_with_db(self):
        """创建连接到真实数据库的管理器实例"""
        manager = PostgreDatabaseManager()

        # 使用测试数据库配置
        await manager.init(base_classes=[PostgreModel])

        yield manager

        # 清理
        await manager.close()

    @pytest.mark.asyncio
    async def test_full_workflow(self, manager_with_db):
        """测试完整的数据库操作流程"""
        # 获取会话
        session = manager_with_db.get_session()

        async with session:
            # 创建测试数据
            test_obj = PostgreModel(
                name='Test Name',
                description='Test Description'
            )
            session.add(test_obj)
            await session.commit()

            # 查询测试数据
            from sqlalchemy import select
            result = await session.execute(select(PostgreModel))
            items = result.scalars().all()

            assert len(items) > 0
            assert items[0].name == 'Test Name'

class TestRedisDatabaseManager:
    """RedisDatabaseManager 测试类"""

    @pytest.fixture
    def manager(self):
        return connect_manager.RedisDatabaseManager()

    def test_redis_property_before_init(self, manager):
        """未初始化时访问 redis 属性应抛出异常"""
        with pytest.raises(RuntimeError):
            _ = manager.redis

    @pytest.mark.asyncio
    async def test_init_with_environment_variables(self, manager):
        """使用环境变量初始化 Redis"""
        with patch.dict(os.environ, {
            'REDIS_HOST': 'redis-host',
            'REDIS_PORT': '6380',
        }, clear=False), \
        patch(f'{TARGET_MODULE_PATH}.Redis') as mock_redis_cls:

            mock_redis_instance = MagicMock()
            mock_redis_cls.return_value = mock_redis_instance

            await manager.init()

            mock_redis_cls.assert_called_once_with(host='redis-host', port=6380, decode_responses=True)
            assert manager.redis is mock_redis_instance


# 集成测试（需要真实的 Redis 服务）
@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv('REDIS_TEST_ENABLED') != '1',
    reason="需要设置 REDIS_TEST_ENABLED=1 环境变量来运行 Redis 集成测试"
)
class TestRedisDatabaseManagerIntegration:
    """RedisDatabaseManager 集成测试类"""

    @pytest_asyncio.fixture
    async def manager_with_redis(self):
        manager = connect_manager.RedisDatabaseManager()
        # 使用环境变量或配置文件中的 Redis 参数
        await manager.init()
        yield manager
        # 当前无显式关闭方法，保持连接由客户端自身管理

    @pytest.mark.asyncio
    async def test_ping(self, manager_with_redis):
        redis = manager_with_redis.redis
        assert await redis.ping() is True

    @pytest.mark.asyncio
    async def test_set_get_string(self, manager_with_redis):
        redis = manager_with_redis.redis
        key = 'it:test:key'
        value = 'hello-world'
        assert await redis.set(key, value) is True
        got = await redis.get(key)
        # aioredis 返回 bytes
        assert got in (value.encode('utf-8'), value)

    @pytest.mark.asyncio
    async def test_init_with_config_file(self, manager_with_redis):
        """使用配置文件初始化 Redis（无环境变量）"""
        with patch.dict(os.environ, {}, clear=True), \
        patch(f'{TARGET_MODULE_PATH}.config') as mock_config, \
        patch(f'{TARGET_MODULE_PATH}.Redis') as mock_redis_cls:

            mock_config.get.side_effect = lambda section, key, fallback=None: {
                ('REDIS', 'Host'): 'cfg-redis-host',
            }.get((section, key), fallback)
            mock_config.getint.side_effect = lambda section, key, fallback=None: {
                ('REDIS', 'Port'): 6379,
            }.get((section, key), fallback)

            mock_redis_instance = MagicMock()
            mock_redis_cls.return_value = mock_redis_instance

            await manager_with_redis.init()

            mock_redis_cls.assert_called_once_with(host='cfg-redis-host', port=6379, decode_responses=True)
            assert manager_with_redis.redis is mock_redis_instance


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--asyncio-mode=auto'])
