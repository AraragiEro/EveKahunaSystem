# -*- coding: utf-8 -*-
"""RED-phase tests for tax calculation in get_plan_tableview_data().

The `calculate_tax_items()` standalone function does NOT exist yet in
plan_utils.py.  All tests in this file are expected to FAIL
(AttributeError) because the function has not been implemented — this is
the desired RED state for TDD.

Once implemented (Task 10), these tests should all pass, confirming that
each eiv_cost_dict entry in the return value of get_plan_tableview_data()
correctly contains a ``tax_items`` list.


Tax calculation formula (from the spec)
---------------------------------------
    tax_amount = round(Σ(quantity × jita_buy_price for matching category)
                       × tax_rate / 100, 2)

Each ``tax_item`` dict::

    {
        "category": f"{target_category}税",
        "target_category": target_category,
        "tax_rate": tax_rate,
        "tax_amount": <rounded 2-decimal float>,
    }
"""

import importlib
from decimal import Decimal, ROUND_HALF_UP

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def plan_utils_mod():
    """Import ``plan_utils`` lazily via ``importlib``.

    Using ``importlib.import_module`` inside a fixture moves the import
    from collection-time to run-time, ensuring every test gets a proper
    AttributeError instead of a collection failure.
    """
    return importlib.import_module(
        "src_v2.model.EVE.industry.industry_utils.plan_utils",
    )


# ---------------------------------------------------------------------------
# Helpers – build minimal child / tax_conf dicts
# ---------------------------------------------------------------------------

def _make_child(
    category: str,
    quantity: int = 100,
    jita_buy_price: float = 10.0,
) -> dict:
    """Build a ``children`` entry matching the ``eiv_cost_dict`` shape."""
    return {
        "type_id": 12345,
        "type_name": f"Test ({category})",
        "index_id": "test_index",
        "quantity": quantity,
        "jita_buy_price": jita_buy_price,
        "jita_sell_price": round(jita_buy_price * 0.9, 2),
        "material_type_node": category,
    }


def _make_tax_conf(target_category: str, tax_rate: float) -> dict:
    """Build a TaxConfig-like dict."""
    return {
        "target_category": target_category,
        "tax_rate": tax_rate,
    }


# ---------------------------------------------------------------------------
# Tests – every test WILL fail until calculate_tax_items exists
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTaxCalculation:
    """Tests for tax calculation logic.

    Every test accesses ``plan_utils.calculate_tax_items()`` which does
    NOT exist yet → all tests fail with AttributeError (RED).
    """

    # ------------------------------------------------------------------
    # 1. Single tax config → one tax_item
    # ------------------------------------------------------------------

    def test_single_tax(self, plan_utils_mod):
        """One tax config targeting a category present in children."""
        children = [_make_child("矿物", quantity=100, jita_buy_price=10.0)]
        tax_confs = [_make_tax_conf("矿物", tax_rate=5.0)]

        # AttributeError — calculate_tax_items does not exist
        result = plan_utils_mod.calculate_tax_items(children, tax_confs)

        assert len(result) == 1
        item = result[0]
        assert item["category"] == "矿物税"
        assert item["target_category"] == "矿物"
        assert item["tax_rate"] == 5.0
        # 100 × 10.0 × 5.0 / 100 = 50.0
        assert item["tax_amount"] == 50.0

    # ------------------------------------------------------------------
    # 2. Multiple tax configs → multiple tax_items
    # ------------------------------------------------------------------

    def test_multiple_taxes(self, plan_utils_mod):
        """Multiple tax configs targeting different categories."""
        children = [
            _make_child("矿物", quantity=100, jita_buy_price=10.0),
            _make_child("燃料块", quantity=50, jita_buy_price=20.0),
        ]
        tax_confs = [
            _make_tax_conf("矿物", tax_rate=5.0),
            _make_tax_conf("燃料块", tax_rate=3.0),
        ]

        result = plan_utils_mod.calculate_tax_items(children, tax_confs)

        assert len(result) == 2

        # First: 100 × 10.0 × 5.0 / 100 = 50.0
        assert result[0]["category"] == "矿物税"
        assert result[0]["tax_amount"] == 50.0

        # Second: 50 × 20.0 × 3.0 / 100 = 30.0
        assert result[1]["category"] == "燃料块税"
        assert result[1]["tax_amount"] == 30.0

    # ------------------------------------------------------------------
    # 3. No tax configs → empty list
    # ------------------------------------------------------------------

    def test_no_taxes(self, plan_utils_mod):
        """Empty tax_confs → empty tax_items."""
        children = [_make_child("矿物", quantity=100, jita_buy_price=10.0)]
        tax_confs: list = []

        result = plan_utils_mod.calculate_tax_items(children, tax_confs)

        assert result == []

    # ------------------------------------------------------------------
    # 4. Tax config targets a category not present in children
    # ------------------------------------------------------------------

    def test_no_matching_category(self, plan_utils_mod):
        """Tax config targeting a category absent from children."""
        children = [_make_child("矿物", quantity=100, jita_buy_price=10.0)]
        tax_confs = [_make_tax_conf("燃料块", tax_rate=5.0)]

        result = plan_utils_mod.calculate_tax_items(children, tax_confs)

        assert len(result) == 1
        assert result[0]["target_category"] == "燃料块"
        # No children match "燃料块" → Σ = 0 → tax_amount = 0.0
        assert result[0]["tax_amount"] == 0.0

    # ------------------------------------------------------------------
    # 5. Precision: round to 2 decimal places
    # ------------------------------------------------------------------

    def test_tax_calculation_precision(self, plan_utils_mod):
        """tax_amount is rounded to 2 decimal places (banker's rounding)."""
        children = [
            # 3 × 1.11 × 5.0 / 100 = 0.1665 → round half up → 0.17
            _make_child("矿物", quantity=3, jita_buy_price=1.11),
        ]
        tax_confs = [_make_tax_conf("矿物", tax_rate=5.0)]

        result = plan_utils_mod.calculate_tax_items(children, tax_confs)

        expected = float(
            Decimal(str(3 * 1.11 * 5.0 / 100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP,
            ),
        )
        assert result[0]["tax_amount"] == expected
