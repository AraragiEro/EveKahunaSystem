# -*- coding: utf-8 -*-
"""RED-phase tests for coefficient_utils module.

The module ``src_v2.model.EVE.industry.coefficient_utils`` does NOT exist yet.
All tests are expected to FAIL (ModuleNotFoundError / ImportError) — this is
the desired RED state for TDD.

Once implemented (GREEN phase), these tests should all pass, confirming
correct behavior of ``get_system_coefficient()`` and ``get_system_info_batch()``.

Test cases for ``get_system_coefficient()``:
  1. Cached coefficient — hgetall returns valid data → float values
  2. No cache — hgetall returns None → null values
  3. No cache — hgetall returns empty dict → null values
  4. Partial data — hgetall returns only manufacturing → manufacturing=float, reaction=None
  5. Redis exception — hgetall raises → null values (graceful fallback)
  6. Bytes keys/values — hgetall returns bytes dict → float values

Test cases for ``get_system_info_batch()``:
  7. Batch with valid IDs → list of dicts with system_id/system_name/region_name
  8. Empty list → empty list
  9. Unknown IDs are skipped → only known systems in results
"""

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===========================================================================
# Fixtures — Redis hgetall mock scenarios
# ===========================================================================

@pytest.fixture
def mock_redis_with_data():
    """Redis mock: hgetall returns str-keyed dict for known system IDs."""
    manager = MagicMock()
    manager.r = MagicMock()

    async def _hgetall(key: str):
        if "30000142" in key:
            return {"manufacturing": "0.023", "reaction": "0.018"}
        if "30000143" in key:
            return {"manufacturing": "0.031", "reaction": "0.015"}
        return None

    manager.r.hgetall = AsyncMock(side_effect=_hgetall)
    return manager


@pytest.fixture
def mock_redis_none():
    """Redis mock: hgetall returns None (key does not exist)."""
    manager = MagicMock()
    manager.r = MagicMock()
    manager.r.hgetall = AsyncMock(return_value=None)
    return manager


@pytest.fixture
def mock_redis_empty_dict():
    """Redis mock: hgetall returns empty dict."""
    manager = MagicMock()
    manager.r = MagicMock()
    manager.r.hgetall = AsyncMock(return_value={})
    return manager


@pytest.fixture
def mock_redis_partial():
    """Redis mock: hgetall returns data missing 'reaction'."""
    manager = MagicMock()
    manager.r = MagicMock()
    manager.r.hgetall = AsyncMock(return_value={"manufacturing": "0.023"})
    return manager


@pytest.fixture
def mock_redis_exception():
    """Redis mock: hgetall raises an exception (connection error)."""
    manager = MagicMock()
    manager.r = MagicMock()
    manager.r.hgetall = AsyncMock(side_effect=Exception("Redis connection failed"))
    return manager


@pytest.fixture
def mock_redis_bytes():
    """Redis mock: hgetall returns bytes-keyed dict (no decode)."""
    manager = MagicMock()
    manager.r = MagicMock()
    manager.r.hgetall = AsyncMock(
        return_value={b"manufacturing": b"0.023", b"reaction": b"0.018"}
    )
    return manager


@pytest.fixture
def mock_sde_utils():
    """Mock SdeUtils.get_system_info_by_id to return canned data."""

    async def _get_info(system_id: int, zh: bool = False, pdm=None):
        data = {
            30000142: {
                "system_name": "Jita",
                "system_id": 30000142,
                "region_id": 10000002,
                "region_name": "The Forge",
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
            },
            30000143: {
                "system_name": "Perimeter",
                "system_id": 30000143,
                "region_id": 10000002,
                "region_name": "The Forge",
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
            },
        }
        return data.get(system_id)

    return _get_info


# ===========================================================================
# Tests — get_system_coefficient
# ===========================================================================

@pytest.mark.unit
class TestGetSystemCoefficient:
    """Tests for get_system_coefficient()."""

    # -- helper to import and patch module-level ``rdm`` ------------------

    def _import_mod(self):
        return importlib.import_module(
            "src_v2.model.EVE.industry.coefficient_utils"
        )

    @pytest.mark.asyncio
    async def test_cached_coefficient(self, mock_redis_with_data):
        """hgetall returns valid data → float values."""
        mod = self._import_mod()
        with patch.object(mod, "rdm", return_value=mock_redis_with_data):
            result = await mod.get_system_coefficient(30000142)

        assert result["manufacturing"] == 0.023
        assert result["reaction"] == 0.018

    @pytest.mark.asyncio
    async def test_no_cache_none(self, mock_redis_none):
        """hgetall returns None → null values."""
        mod = self._import_mod()
        with patch.object(mod, "rdm", return_value=mock_redis_none):
            result = await mod.get_system_coefficient(99999999)

        assert result["manufacturing"] is None
        assert result["reaction"] is None

    @pytest.mark.asyncio
    async def test_no_cache_empty_dict(self, mock_redis_empty_dict):
        """hgetall returns empty dict → null values."""
        mod = self._import_mod()
        with patch.object(mod, "rdm", return_value=mock_redis_empty_dict):
            result = await mod.get_system_coefficient(30000142)

        assert result["manufacturing"] is None
        assert result["reaction"] is None

    @pytest.mark.asyncio
    async def test_partial_data(self, mock_redis_partial):
        """hgetall returns only manufacturing → reaction is None."""
        mod = self._import_mod()
        with patch.object(mod, "rdm", return_value=mock_redis_partial):
            result = await mod.get_system_coefficient(30000142)

        assert result["manufacturing"] == 0.023
        assert result["reaction"] is None

    @pytest.mark.asyncio
    async def test_redis_exception(self, mock_redis_exception):
        """hgetall raises exception → graceful fallback to null values."""
        mod = self._import_mod()
        with patch.object(mod, "rdm", return_value=mock_redis_exception):
            result = await mod.get_system_coefficient(30000142)

        assert result["manufacturing"] is None
        assert result["reaction"] is None

    @pytest.mark.asyncio
    async def test_bytes_keys_values(self, mock_redis_bytes):
        """hgetall returns bytes-keyed dict → float values."""
        mod = self._import_mod()
        with patch.object(mod, "rdm", return_value=mock_redis_bytes):
            result = await mod.get_system_coefficient(30000142)

        assert result["manufacturing"] == 0.023
        assert result["reaction"] == 0.018


# ===========================================================================
# Tests — get_system_info_batch
# ===========================================================================

@pytest.mark.unit
class TestGetSystemInfoBatch:
    """Tests for get_system_info_batch()."""

    def _import_mod(self):
        return importlib.import_module(
            "src_v2.model.EVE.industry.coefficient_utils"
        )

    @pytest.mark.asyncio
    async def test_batch_system_info(self, mock_sde_utils):
        """Valid system IDs → list of {system_id, system_name, region_name}."""
        mod = self._import_mod()
        with patch(
            "src_v2.model.EVE.sde.utils.SdeUtils.get_system_info_by_id",
            mock_sde_utils,
        ):
            result = await mod.get_system_info_batch([30000142, 30000143])

        assert len(result) == 2
        assert result[0] == {
            "system_id": 30000142,
            "system_name": "Jita",
            "region_name": "The Forge",
        }
        assert result[1] == {
            "system_id": 30000143,
            "system_name": "Perimeter",
            "region_name": "The Forge",
        }

    @pytest.mark.asyncio
    async def test_empty_batch(self):
        """Empty list → empty list."""
        mod = self._import_mod()
        result = await mod.get_system_info_batch([])

        assert result == []

    @pytest.mark.asyncio
    async def test_batch_with_unknown_ids(self, mock_sde_utils):
        """Unknown system ID returns None → skipped in results."""
        mod = self._import_mod()
        with patch(
            "src_v2.model.EVE.sde.utils.SdeUtils.get_system_info_by_id",
            mock_sde_utils,
        ):
            # 99999999 is not in mock_sde_utils data → returns None
            result = await mod.get_system_info_batch([30000142, 99999999])

        assert len(result) == 1
        assert result[0]["system_id"] == 30000142
