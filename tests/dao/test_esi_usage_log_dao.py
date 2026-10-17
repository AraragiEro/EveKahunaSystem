"""
EsiUsageLog DAO 集成测试 (SQLite in-memory)

测试 EsiUsageLogDBUtils 的 CRUD 与清理操作。
"""
import pytest
from datetime import datetime, timedelta

from src_v2.core.database import model
from src_v2.core.database.kahuna_database_utils_v2 import EsiUsageLogDBUtils

pytestmark = pytest.mark.dao


class TestEsiUsageLogDBUtils:
    @pytest.mark.asyncio
    async def test_insert_and_query(self, db_session):
        """insert_log 后 query_logs 能查询到记录"""
        now = datetime.utcnow()
        await EsiUsageLogDBUtils.insert_log(
            timestamp=now,
            endpoint="/characters/123/",
            pool_name="public_pool",
            character_id=12345,
            status_code=200,
            latency_ms=150.5,
        )

        logs = await EsiUsageLogDBUtils.query_logs()
        assert len(logs) == 1
        assert logs[0].endpoint == "/characters/123/"
        assert logs[0].pool_name == "public_pool"
        assert logs[0].character_id == 12345
        assert logs[0].status_code == 200
        assert logs[0].latency_ms == 150.5

    @pytest.mark.asyncio
    async def test_offset_pagination(self, db_session):
        """query_logs 支持 offset/limit 分页，按时间倒序返回"""
        now = datetime.utcnow()
        for i in range(5):
            await EsiUsageLogDBUtils.insert_log(
                timestamp=now + timedelta(seconds=i),
                endpoint=f"/test/{i}",
                character_id=10000 + i,
            )

        # limit=2, offset=0 → 取最近2条（id=4,3）
        page1 = await EsiUsageLogDBUtils.query_logs(limit=2, offset=0)
        assert len(page1) == 2
        assert page1[0].character_id == 10004
        assert page1[1].character_id == 10003

        # limit=2, offset=2 → 取后续2条（id=2,1）
        page2 = await EsiUsageLogDBUtils.query_logs(limit=2, offset=2)
        assert len(page2) == 2
        assert page2[0].character_id == 10002
        assert page2[1].character_id == 10001

    @pytest.mark.asyncio
    async def test_cleanup_old_logs(self, db_session):
        """cleanup_old_logs 删除指定天数前的记录"""
        now = datetime.utcnow()

        # 插入旧记录（8天前）
        old_time = now - timedelta(days=8)
        await EsiUsageLogDBUtils.insert_log(
            timestamp=old_time, endpoint="/old/1", character_id=1
        )
        await EsiUsageLogDBUtils.insert_log(
            timestamp=old_time, endpoint="/old/2", character_id=2
        )

        # 插入新记录（1天前）
        new_time = now - timedelta(days=1)
        await EsiUsageLogDBUtils.insert_log(
            timestamp=new_time, endpoint="/new/1", character_id=3
        )

        total = await EsiUsageLogDBUtils.get_total_count()
        assert total == 3

        # 清理7天前的旧记录
        deleted = await EsiUsageLogDBUtils.cleanup_old_logs(days=7)
        assert deleted == 2

        total_after = await EsiUsageLogDBUtils.get_total_count()
        assert total_after == 1

        remaining = await EsiUsageLogDBUtils.query_logs()
        assert remaining[0].character_id == 3

    @pytest.mark.asyncio
    async def test_empty_table(self, db_session):
        """空表时 query_logs 返回空列表，get_total_count 返回0"""
        logs = await EsiUsageLogDBUtils.query_logs()
        assert logs == []

        total = await EsiUsageLogDBUtils.get_total_count()
        assert total == 0
