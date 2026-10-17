"""
pytest 全局配置与共享 fixture

为整个测试工程提供：
- 路径设置
- 数据库管理器 Mock
- Quart 测试客户端
- JWT 认证头部
- 配置 Mock（按需使用）
"""
import sys
import os

# ============================================================
# 路径设置
# ============================================================
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# ============================================================
# 通用 Fixture
# ============================================================
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ---- Mock 配置（需要覆盖配置的测试显式使用） ----
@pytest.fixture
def mock_config():
    """
    Mock 全局配置，替换 config.toml 读取。
    测试通过 fixture 参数或 @pytest.mark.usefixtures("mock_config") 显式启用。
    """
    fake_config = {
        "APP": {"SECRET_KEY": "test-secret-key-for-jwt"},
        "POSTGREDB": {
            "Host": "localhost",
            "Port": "5432",
            "Database": "test_db",
            "User": "test",
            "Password": "test",
        },
        "REDIS": {"Host": "localhost", "Port": "6379"},
        "NEO4J": {
            "Host": "localhost",
            "Port": "7687",
            "Username": "neo4j",
            "Password": "test",
        },
        "EVE": {
            "CLIENT_ID": "test-client-id",
            "SECRET_KEY": "test-secret-key",
            "CALLBACK_LOCAL_HOST": "localhost:9527/",
        },
        "SDEDB": {
            "Host": "localhost",
            "Port": "5432",
            "Database": "sde_test",
            "User": "test",
            "Password": "test",
        },
        "ESI": {},
        "EDITION": {"Edition": "community"},
    }

    class MockConfig:
        def get(self, section, key, fallback=None):
            return fake_config.get(section, {}).get(key, fallback)

        def getint(self, section, key, fallback=None):
            val = fake_config.get(section, {}).get(key)
            return int(val) if val is not None else fallback

        def getboolean(self, section, key, fallback=None):
            val = fake_config.get(section, {}).get(key)
            if val is None:
                return fallback
            return str(val).lower() in ("true", "1", "yes")

        def __getitem__(self, key):
            return fake_config[key]

        def __contains__(self, key):
            return key in fake_config

    with patch("src_v2.core.config.config.config", MockConfig()):
        yield


# ---- 数据库会话 Mock ----
@pytest.fixture
def mock_db_session():
    """Mock 的 PostgreSQL 异步会话，用于单元测试中替换真实数据库操作"""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_postgres_manager(mock_db_session):
    """Mock PostgreSQL 连接管理器"""
    manager = MagicMock()
    manager.get_session = MagicMock()
    manager.get_session.return_value.__aenter__ = AsyncMock(
        return_value=mock_db_session
    )
    manager.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    manager.session = mock_db_session
    manager.engine = MagicMock()
    return manager


@pytest.fixture
def mock_neo4j_manager():
    """Mock Neo4j 连接管理器"""
    manager = MagicMock()
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    mock_session.close = AsyncMock()
    manager.get_session = MagicMock()
    manager.get_session.return_value.__aenter__ = AsyncMock(
        return_value=mock_session
    )
    manager.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    return manager


@pytest.fixture
def mock_redis_manager():
    """Mock Redis 连接管理器"""
    manager = MagicMock()
    manager.redis = MagicMock()
    manager.redis.get = AsyncMock(return_value=None)
    manager.redis.set = AsyncMock(return_value=True)
    manager.redis.hget = AsyncMock(return_value=None)
    manager.redis.hset = AsyncMock(return_value=1)
    manager.redis.delete = AsyncMock(return_value=1)
    manager.redis.ping = AsyncMock(return_value=True)
    manager.redis.pipeline = MagicMock(return_value=MagicMock())
    return manager


# ---- Quart 测试客户端 ----
@pytest_asyncio.fixture
async def test_app(mock_postgres_manager, mock_redis_manager, mock_neo4j_manager):
    """
    创建 Quart 测试应用，Mock 所有数据库管理器。
    """
    with (
        patch(
            "src_v2.core.database.connect_manager.get_postgres_manager",
            return_value=mock_postgres_manager,
        ),
        patch(
            "src_v2.core.database.connect_manager.get_redis_manager",
            return_value=mock_redis_manager,
        ),
        patch(
            "src_v2.core.database.connect_manager.get_neo4j_manager",
            return_value=mock_neo4j_manager,
        ),
    ):
        from src_v2.backend.app import get_app

        app = get_app()
        app.config["TESTING"] = True
        async with app.test_app() as ta:
            yield ta


@pytest_asyncio.fixture
async def test_client(test_app):
    """Quart 测试客户端"""
    return test_app.test_client()


# ---- JWT 认证头部 ----
@pytest.fixture
def auth_headers():
    """创建有效的 JWT 认证头部（用户 test_user）"""
    import jwt
    from datetime import datetime, timedelta

    payload = {
        "user_name": "test_user",
        "exp": datetime.utcnow() + timedelta(hours=24),
    }
    token = jwt.encode(payload, "test-secret-key-for-jwt", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth_headers():
    """创建管理员 JWT 认证头部（用户 admin）"""
    import jwt
    from datetime import datetime, timedelta

    payload = {
        "user_name": "admin",
        "exp": datetime.utcnow() + timedelta(hours=24),
    }
    token = jwt.encode(payload, "test-secret-key-for-jwt", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def expired_auth_headers():
    """创建过期的 JWT 认证头部"""
    import jwt
    from datetime import datetime, timedelta

    payload = {
        "user_name": "test_user",
        "exp": datetime.utcnow() - timedelta(hours=1),
    }
    token = jwt.encode(payload, "test-secret-key-for-jwt", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def invalid_auth_headers():
    """创建无效格式的认证头部"""
    return {"Authorization": "NotBearer invalid_token_format"}


# ---- 通用测试数据 ----
@pytest.fixture
def sample_user_data():
    """标准测试用户数据"""
    return {
        "user_name": "test_user",
        "password": "test_password_123",
        "invite_code": "TEST-CODE-123",
    }
