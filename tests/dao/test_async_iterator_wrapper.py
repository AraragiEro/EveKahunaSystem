# -*- coding: utf-8 -*-
"""_AsyncIteratorWrapper 单元测试

测试异步生成器包装器的资源管理行为：
- 工厂方法 from_stmt
- 正常迭代与自动清理
- 上下文管理器
- 异常处理与回滚
- 重复清理防护
- __del__ 资源警告
"""

import warnings

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src_v2.core.database.kahuna_database_utils_v2 import _AsyncIteratorWrapper


@pytest.mark.dao
class TestAsyncIteratorWrapper:
    """_AsyncIteratorWrapper 测试类"""

    @pytest.fixture
    def mock_session(self):
        """Mock 异步会话"""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        session.in_transaction = MagicMock(return_value=False)
        return session

    @pytest.fixture
    def sample_items(self):
        """测试数据"""
        return [10, 20, 30]

    @pytest.fixture
    def async_gen(self, sample_items):
        """正常异步生成器"""
        async def _gen():
            for item in sample_items:
                yield item
        return _gen()

    # ── from_stmt 工厂 ─────────────────────────────────────

    async def test_from_stmt_normal(self, mock_session, sample_items):
        """from_stmt 应创建包装器、执行语句并保存 result"""
        mock_result = MagicMock()
        mock_result.scalars.return_value = sample_items
        mock_session.execute.return_value = mock_result

        with patch(
            "src_v2.core.database.kahuna_database_utils_v2.get_postgres_manager"
        ) as mock_get:
            mock_mgr = MagicMock()
            mock_mgr.session_maker.return_value = mock_session
            mock_get.return_value = mock_mgr

            wrapper = await _AsyncIteratorWrapper.from_stmt("select 1")

            assert wrapper._session is mock_session
            assert wrapper._closed is False
            assert wrapper._result is mock_result
            mock_session.execute.assert_called_once_with("select 1")

    async def test_from_stmt_no_session_maker(self):
        """from_stmt 在 session_maker 为 None 时抛出 RuntimeError"""
        with patch(
            "src_v2.core.database.kahuna_database_utils_v2.get_postgres_manager"
        ) as mock_get:
            mock_mgr = MagicMock()
            mock_mgr.session_maker = None
            mock_get.return_value = mock_mgr

            with pytest.raises(RuntimeError, match="数据库未初始化"):
                await _AsyncIteratorWrapper.from_stmt("select 1")

    # ── 正常迭代 ───────────────────────────────────────────

    async def test_normal_iteration(self, mock_session, sample_items):
        """async for 正常迭代 → 结束时提交事务并自动清理"""
        mock_result = MagicMock()
        mock_result.scalars.return_value = sample_items
        mock_session.execute.return_value = mock_result

        with patch(
            "src_v2.core.database.kahuna_database_utils_v2.get_postgres_manager"
        ) as mock_get:
            mock_mgr = MagicMock()
            mock_mgr.session_maker.return_value = mock_session
            mock_get.return_value = mock_mgr

            wrapper = await _AsyncIteratorWrapper.from_stmt("select 1")
            results = [item async for item in wrapper]

        assert results == sample_items
        # 内层生成器提交事务
        mock_session.commit.assert_called_once()
        # 包装器清理关闭 session
        mock_session.close.assert_called_once()
        assert wrapper._closed is True
        assert wrapper._session is None
        assert wrapper._result is None

    # ── 上下文管理器 ───────────────────────────────────────

    async def test_context_manager(self, mock_session, sample_items):
        """async with 上下文管理器退出时清理 session"""
        mock_result = MagicMock()
        mock_result.scalars.return_value = sample_items
        mock_session.execute.return_value = mock_result

        with patch(
            "src_v2.core.database.kahuna_database_utils_v2.get_postgres_manager"
        ) as mock_get:
            mock_mgr = MagicMock()
            mock_mgr.session_maker.return_value = mock_session
            mock_get.return_value = mock_mgr

            wrapper = await _AsyncIteratorWrapper.from_stmt("select 1")
            async with wrapper:
                results = [item async for item in wrapper]

        assert results == sample_items
        mock_session.close.assert_called_once()
        assert wrapper._closed is True
        assert wrapper._session is None

    # ── 显式关闭 ──────────────────────────────────────────

    async def test_explicit_aclose(self, async_gen, mock_session):
        """显式调用 aclose 应清理生成器并关闭 session"""
        wrapper = _AsyncIteratorWrapper(async_gen, mock_session)
        assert wrapper._closed is False

        await wrapper.aclose()

        mock_session.close.assert_called_once()
        assert wrapper._closed is True
        assert wrapper._session is None
        assert wrapper._result is None

    # ── 迭代异常 ──────────────────────────────────────────

    async def test_exception_during_iteration(self, mock_session):
        """迭代中产生异常 → 内层生成器回滚事务 + 包装器清理"""
        def _iter_with_error():
            yield 1
            yield 2
            raise ValueError("db error")

        mock_result = MagicMock()
        mock_result.scalars.return_value = _iter_with_error()
        mock_session.execute.return_value = mock_result

        with patch(
            "src_v2.core.database.kahuna_database_utils_v2.get_postgres_manager"
        ) as mock_get:
            mock_mgr = MagicMock()
            mock_mgr.session_maker.return_value = mock_session
            mock_get.return_value = mock_mgr

            wrapper = await _AsyncIteratorWrapper.from_stmt("select 1")
            results = []
            with pytest.raises(ValueError, match="db error"):
                async for item in wrapper:
                    results.append(item)

        assert results == [1, 2]
        # 内层生成器的异常处理
        mock_session.rollback.assert_called_once()
        # 包装器的清理
        mock_session.close.assert_called_once()
        assert wrapper._closed is True

    # ── 事务回滚 ──────────────────────────────────────────

    async def test_in_transaction_rollback(self, async_gen, mock_session):
        """清理时 session 仍在事务中 → 先回滚再关闭"""
        mock_session.in_transaction.return_value = True

        wrapper = _AsyncIteratorWrapper(async_gen, mock_session)
        await wrapper.aclose()

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
        assert wrapper._closed is True

    # ── 防重复清理 ────────────────────────────────────────

    async def test_double_cleanup_prevented(self, async_gen, mock_session):
        """_closed 标志确保 cleanup 只执行一次"""
        wrapper = _AsyncIteratorWrapper(async_gen, mock_session)

        await wrapper.aclose()
        await wrapper.aclose()

        # close 只应被调用一次
        mock_session.close.assert_called_once()
        assert wrapper._closed is True

    # ── 关闭后不再迭代 ─────────────────────────────────────

    async def test_anext_after_close(self, async_gen, mock_session):
        """关闭后调用 __anext__ 应返回 StopAsyncIteration"""
        wrapper = _AsyncIteratorWrapper(async_gen, mock_session)
        await wrapper.aclose()

        with pytest.raises(StopAsyncIteration):
            await wrapper.__anext__()

    # ── __del__ 资源警告 ───────────────────────────────────

    def test_del_warning(self, mock_session):
        """未关闭时 __del__ 发出 ResourceWarning"""
        wrapper = _AsyncIteratorWrapper(MagicMock(), mock_session)
        wrapper._closed = False

        with pytest.warns(ResourceWarning, match="session 尚未关闭"):
            wrapper.__del__()

    def test_del_no_warning_when_closed(self, mock_session):
        """已关闭时 __del__ 不发出警告"""
        wrapper = _AsyncIteratorWrapper(MagicMock(), mock_session)
        wrapper._closed = True

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            # 不应触发 ResourceWarning
            wrapper.__del__()

    def test_del_no_warning_no_session(self):
        """session 为 None 时 __del__ 不发出警告"""
        wrapper = _AsyncIteratorWrapper(MagicMock(), None)
        wrapper._closed = False

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            # 不应触发 ResourceWarning
            wrapper.__del__()
