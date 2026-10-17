# -*- coding: utf-8 -*-
"""RED-phase tests for TaxConfig validation.

The validate_tax_config() function does NOT exist yet in config_utils.py.
All tests in this file are expected to FAIL (AttributeError) because the
function has not been implemented — this is the desired RED state for TDD.

Once implemented (Task 8), these tests should all pass.
"""

import importlib

import pytest

from src_v2.core.utils import KahunaException

# Valid category list expected by the future validation
VALID_CATEGORIES = [
    "矿物",
    "冰矿产物",
    "燃料块",
    "元素",
    "气云",
    "行星工业",
    "杂货",
    "EIV成本",
]


@pytest.fixture(scope="module")
def config_utils_mod():
    """Import config_utils lazily via importlib."""
    return importlib.import_module(
        "src_v2.model.EVE.industry.industry_utils.config_utils"
    )


# ---------------------------------------------------------------------------
# RED-phase tests — every test accesses the non-existent
# validate_tax_config function and will FAIL with AttributeError.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTaxConfigValidation:
    """Tests for TaxConfig config_value validation.

    These will ALL fail (AttributeError) until validate_tax_config is
    implemented in config_utils.py.
    """

    def test_valid_tax_config(self, config_utils_mod):
        """Valid config_value should pass without error."""
        valid_value = {"target_category": "矿物", "tax_rate": 10.0}
        # WILL FAIL: validate_tax_config does not exist yet
        config_utils_mod.validate_tax_config(valid_value)

    def test_missing_target_category(self, config_utils_mod):
        """Missing target_category should raise KahunaException."""
        invalid_value = {"tax_rate": 10.0}
        with pytest.raises(KahunaException):
            # WILL FAIL: validate_tax_config does not exist yet
            config_utils_mod.validate_tax_config(invalid_value)

    def test_missing_tax_rate(self, config_utils_mod):
        """Missing tax_rate should raise KahunaException."""
        invalid_value = {"target_category": "矿物"}
        with pytest.raises(KahunaException):
            # WILL FAIL: validate_tax_config does not exist yet
            config_utils_mod.validate_tax_config(invalid_value)

    def test_tax_rate_not_number(self, config_utils_mod):
        """Non-numeric tax_rate should raise KahunaException."""
        invalid_value = {"target_category": "矿物", "tax_rate": "abc"}
        with pytest.raises(KahunaException):
            # WILL FAIL: validate_tax_config does not exist yet
            config_utils_mod.validate_tax_config(invalid_value)

    def test_invalid_target_category(self, config_utils_mod):
        """Unknown target_category should raise KahunaException."""
        invalid_value = {"target_category": "INVALID", "tax_rate": 10.0}
        with pytest.raises(KahunaException):
            # WILL FAIL: validate_tax_config does not exist yet
            config_utils_mod.validate_tax_config(invalid_value)

    def test_tax_rate_out_of_range(self, config_utils_mod):
        """tax_rate > 100.0 should raise KahunaException."""
        invalid_value = {"target_category": "矿物", "tax_rate": 150.0}
        with pytest.raises(KahunaException):
            # WILL FAIL: validate_tax_config does not exist yet
            config_utils_mod.validate_tax_config(invalid_value)
