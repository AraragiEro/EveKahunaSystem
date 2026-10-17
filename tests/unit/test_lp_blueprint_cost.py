# -*- coding: utf-8 -*-
"""RED-phase tests for LpBlueprintCostCalculator.

Tests the calc_blueprint_cost() method which computes the ISK cost
of a faction product by combining LP offer data with LP/ISK exchange rates.

Formula (from the spec):
    (min_lp_buy_value * lp_cost + isk_cost) / products_per_run

All tests are expected to FAIL initially (RED) because the
LpBlueprintCostCalculator class does not exist yet.
"""

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixture - lazy import so collection doesn't fail on missing module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def lp_module():
    """Import lp_blueprint_cost lazily via importlib.

    Using importlib.import_module inside a fixture moves the import
    from collection-time to run-time, ensuring every test gets a proper
    ModuleNotFoundError instead of a collection failure.
    """
    return importlib.import_module(
        "src_v2.model.EVE.industry.industry_utils.lp_blueprint_cost",
    )


# ---------------------------------------------------------------------------
# Helpers - build mocks
# ---------------------------------------------------------------------------

def _make_mock_db_session(rows: list, scalar_value=None):
    """Build an AsyncMock session whose execute() returns the given rows.

    Args:
        rows: List of MagicMock row objects (for .all() queries).
        scalar_value: Value returned by .scalar_one_or_none().
                      When None (default), uses rows[0] (the row object).
                      Set to a plain value for scalar queries (e.g. lp_buy_value).
    """
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()

    # Simulate session.execute(stmt) -> result
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    mock_result.scalar_one_or_none.return_value = (
        scalar_value if scalar_value is not None
        else (rows[0] if rows else None)
    )
    mock_result.scalar.return_value = rows[0] if rows else None
    session.execute = AsyncMock(return_value=mock_result)

    return session


def _session_ctx(session):
    """Wrap a session in an async context manager for get_session()."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


def _make_multi_session_pg(sessions):
    """Mock postgres manager that returns different sessions per get_session() call."""
    mgr = MagicMock()
    mgr.get_session.side_effect = [_session_ctx(s) for s in sessions]
    return mgr


def _make_lp_offer_row(lp_cost, isk_cost, corporation_id, lp_buy_value=None):
    """Create a mock row resembling an EveLpValueSnapshotDetail row."""
    row = MagicMock()
    row.lp_cost = lp_cost
    row.isk_cost = isk_cost
    row.corporation_id = corporation_id
    row.lp_buy_value = lp_buy_value  # BPC评估值（_evaluate_bpc结果），None则走军团快照回退
    return row


# ---------------------------------------------------------------------------
# Helpers - plan_utils integration mocks
# ---------------------------------------------------------------------------


def _make_mock_op(calc_lp_enabled: bool = False):
    """Create a mock op (ConfigFlowOperateCenter) for plan_utils integration tests.

    Args:
        calc_lp_enabled: Whether calculate_lp_blueprint_cost is enabled.

    Returns:
        A MagicMock configured with enough attributes to reach the LP
        blueprint cost integration code in get_plan_tableview_data().
    """
    op = MagicMock()
    op.user_name = "test_user"
    op.plan_name = "test_plan"
    op.plan_settings = {"calculate_lp_blueprint_cost": calc_lp_enabled}
    op.current_progress_key = "test:progress"
    op.all_ralation_dict = {
        "rel1": {
            "relation": {
                "material": 1001,
                "product": 1002,
                "quantity": 10,
                "real_quantity": 5,
                "real_eiv_cost_total": 1000,
                "index_id": "idx1",
            },
        },
    }
    op.index_product_dict = {"idx1": 3516}
    op.product_num_dict = {3516: 1}
    op.get_type_assets_quantity = AsyncMock(return_value=0)
    op.get_node_type = MagicMock(return_value="product")
    op.get_running_job_count = AsyncMock(return_value=0)
    op.get_bp_status = AsyncMock(return_value=(0, 0))
    op.get_type_assign_structure_info = AsyncMock(return_value=None)
    op.get_structure_material_provide_dict = AsyncMock(return_value={})
    op.get_running_job_tableview_data = AsyncMock(return_value=[])
    op.sdm = None
    op.tax_confs = []
    return op


def _make_node_dict():
    """Create a minimal node_dict that satisfies get_plan_tableview_data.

    Keys correspond to the material (1001) and product (1002) type_ids
    used in _make_mock_op().  Both nodes need ``real_quantity`` because
    the inventory section (line 627) accesses it unconditionally.
    """
    return {
        1001: {
            "type_id": 1001, "max_distance": 1, "order_id": 1,
            "quantity": 0, "real_quantity": 0,
        },
        1002: {
            "type_id": 1002, "max_distance": 1, "order_id": 1,
            "quantity": 0, "real_quantity": 0,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestLpBlueprintCostCalculator:
    """Tests for LpBlueprintCostCalculator.calc_blueprint_cost()."""

    @patch("src_v2.model.EVE.industry.industry_utils.lp_blueprint_cost.SdeUtils")
    @patch("src_v2.model.EVE.industry.industry_utils.lp_blueprint_cost.BPManager")
    async def test_calc_faction_bpc_cost(self, mock_bpm, mock_sde, lp_module):
        """Fed Navy Comet BPC -> correct ISK cost per product."""
        # -- Arrange: Mock SdeUtils --
        mock_sde.get_metaname_by_typeid = AsyncMock(return_value="Faction")

        # -- Arrange: Mock BPManager --
        mock_bpm.get_bp_id_by_prod_typeid = AsyncMock(return_value=3517)
        mock_bpm.get_bp_product_quantity_typeid = AsyncMock(return_value=1)

        # -- Arrange: LP offer session (type_id=3517) --
        offer_row = _make_lp_offer_row(
            lp_cost=15000, isk_cost=10000000, corporation_id=1000044,
            lp_buy_value=1500,
        )
        offer_session = _make_mock_db_session([offer_row])

        # single session: offer query only (detail lp_buy_value used, skip snapshot)
        mock_pg = _make_multi_session_pg([offer_session])

        # -- Act --
        calc = lp_module.LpBlueprintCostCalculator()
        sdm_mock = MagicMock()
        result = await calc.calc_blueprint_cost(
            product_type_id=3516, db=mock_pg, sdm=sdm_mock,
        )

        # -- Assert --
        # Formula: (1500 * 15000 + 10000000) / 1 = 32500000.0
        assert result == 32500000.0

        # Verify helper calls
        mock_sde.get_metaname_by_typeid.assert_called_once_with(
            3516, pdm=sdm_mock,
        )
        mock_bpm.get_bp_id_by_prod_typeid.assert_called_once_with(
            3516, pdm=sdm_mock,
        )
        mock_bpm.get_bp_product_quantity_typeid.assert_called_once_with(
            3516, pdm=sdm_mock,
        )

    @patch("src_v2.model.EVE.industry.industry_utils.lp_blueprint_cost.SdeUtils")
    async def test_calc_no_lp_data_returns_zero(self, mock_sde, lp_module):
        """Empty LP snapshot -> returns 0.0 and logs warning."""
        # -- Arrange --
        mock_sde.get_metaname_by_typeid = AsyncMock(return_value="Faction")

        empty_session = _make_mock_db_session([])
        mock_pg = _make_multi_session_pg([empty_session])

        with patch(
            "src_v2.model.EVE.industry.industry_utils.lp_blueprint_cost.BPManager"
        ) as mock_bpm:
            mock_bpm.get_bp_id_by_prod_typeid = AsyncMock(return_value=3517)

            with patch(
                "src_v2.model.EVE.industry.industry_utils.lp_blueprint_cost.logger"
            ) as mock_logger:
                mock_logger.warning = MagicMock()

                calc = lp_module.LpBlueprintCostCalculator()
                result = await calc.calc_blueprint_cost(
                    product_type_id=3516, db=mock_pg, sdm=MagicMock(),
                )

                assert result == 0.0
                mock_logger.warning.assert_called()

    @patch("src_v2.model.EVE.industry.industry_utils.lp_blueprint_cost.SdeUtils")
    @patch("src_v2.model.EVE.industry.industry_utils.lp_blueprint_cost.BPManager")
    async def test_calc_multiple_corps_picks_lowest(
        self, mock_bpm, mock_sde, lp_module,
    ):
        """Two corps with different lp_buy_value -> picks lowest (cheapest)."""
        # -- Arrange: Mock SdeUtils --
        mock_sde.get_metaname_by_typeid = AsyncMock(return_value="Faction")

        # -- Arrange: Mock BPManager --
        mock_bpm.get_bp_id_by_prod_typeid = AsyncMock(return_value=3517)
        mock_bpm.get_bp_product_quantity_typeid = AsyncMock(return_value=1)

        # -- Arrange: LP offer session (2 corps, same BPC) --
        corp_a_row = _make_lp_offer_row(
            lp_cost=10000, isk_cost=5000000, corporation_id=1000044,
            lp_buy_value=1500,
        )
        corp_b_row = _make_lp_offer_row(
            lp_cost=10000, isk_cost=5000000, corporation_id=1000045,
            lp_buy_value=1000,
        )
        offer_session = _make_mock_db_session([corp_a_row, corp_b_row])

        # single session: offer query only (detail lp_buy_value used)
        mock_pg = _make_multi_session_pg([offer_session])

        # -- Act --
        calc = lp_module.LpBlueprintCostCalculator()
        result = await calc.calc_blueprint_cost(
            product_type_id=3516, db=mock_pg, sdm=MagicMock(),
        )

        # -- Assert --
        # picks lp_buy_value=1000 (lowest)
        # (1000 * 10000 + 5000000) / 1 = 15000000.0
        assert result == 15000000.0

    # ------------------------------------------------------------------ #
    #  Integration tests — plan_utils <-> LpBlueprintCostCalculator
    # ------------------------------------------------------------------ #

    @patch(
        "src_v2.model.EVE.industry.industry_utils.plan_utils.SdeUtils.get_name_by_id",
        new_callable=AsyncMock,
    )
    @patch(
        "src_v2.model.EVE.industry.industry_utils.plan_utils.BPM.get_bp_product_quantity_typeid",
        new_callable=AsyncMock,
    )
    @patch(
        "src_v2.model.EVE.industry.industry_utils.plan_utils.calculate_tax_items",
    )
    @patch(
        "src_v2.model.EVE.industry.industry_utils.plan_utils.LpBlueprintCostCalculator",
    )
    async def test_calc_switch_off_skips_calculation(
        self, mock_calc_cls, mock_tax, mock_bpm_qty, mock_name, lp_module,
    ):
        """``calculate_lp_blueprint_cost`` off → calculator NOT called.

        Verify that ``get_plan_tableview_data`` does NOT instantiate or
        invoke ``LpBlueprintCostCalculator`` when the config switch is off.
        """
        # -- Arrange --
        mock_name.return_value = "Test Item"
        mock_bpm_qty.return_value = 1
        mock_tax.return_value = []

        op = _make_mock_op(calc_lp_enabled=False)
        node_dict = _make_node_dict()

        from src_v2.model.EVE.industry.industry_utils.plan_utils import (
            get_plan_tableview_data,
        )

        inrdm = MagicMock()
        inrdm.r = MagicMock()

        # -- Act --
        result = await get_plan_tableview_data(
            op, node_dict, subprocess=True, inrdm=inrdm, sdm=None,
        )

        # -- Assert --
        # Calculator class was never instantiated
        mock_calc_cls.assert_not_called()

        # eiv_cost_dict entry should NOT have blueprint_cost
        eiv_entry = result["eiv_cost_dict"].get(3516, {})
        assert "blueprint_cost" not in eiv_entry, (
            "blueprint_cost should not be present when switch is off"
        )

    @patch(
        "src_v2.model.EVE.industry.industry_utils.plan_utils.SdeUtils.get_name_by_id",
        new_callable=AsyncMock,
    )
    @patch(
        "src_v2.model.EVE.industry.industry_utils.plan_utils.BPM.get_bp_product_quantity_typeid",
        new_callable=AsyncMock,
    )
    @patch(
        "src_v2.model.EVE.industry.industry_utils.plan_utils.calculate_tax_items",
    )
    @patch(
        "src_v2.model.EVE.industry.industry_utils.plan_utils.LpBlueprintCostCalculator",
    )
    async def test_calc_exception_returns_zero(
        self, mock_calc_cls, mock_tax, mock_bpm_qty, mock_name, lp_module,
    ):
        """Calculator exception → ``blueprint_cost`` defaults to ``0.0``.

        Verify that the ``try/except`` in ``get_plan_tableview_data``
        catches exceptions from ``calc_blueprint_cost`` and still sets
        the ``blueprint_cost`` field to ``0.0`` (defence-in-depth).
        """
        # -- Arrange --
        mock_name.return_value = "Test Item"
        mock_bpm_qty.return_value = 1
        mock_tax.return_value = []

        # Make the calculator's method raise
        mock_calc = MagicMock()
        mock_calc.calc_blueprint_cost = AsyncMock(
            side_effect=RuntimeError("LP data unavailable"),
        )
        mock_calc_cls.return_value = mock_calc

        op = _make_mock_op(calc_lp_enabled=True)
        node_dict = _make_node_dict()

        from src_v2.model.EVE.industry.industry_utils.plan_utils import (
            get_plan_tableview_data,
        )

        inrdm = MagicMock()
        inrdm.r = MagicMock()

        # -- Act --
        result = await get_plan_tableview_data(
            op, node_dict, subprocess=True, inrdm=inrdm, sdm=None,
        )

        # -- Assert --
        eiv_entry = result["eiv_cost_dict"].get(3516, {})
        assert eiv_entry.get("blueprint_cost") == 0.0, (
            "blueprint_cost should be 0.0 when calculator raises"
        )

        mock_calc.calc_blueprint_cost.assert_called_once_with(
            3516, sdm=None, db=None,
        )
