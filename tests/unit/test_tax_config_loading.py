# -*- coding: utf-8 -*-
"""RED-phase test for TaxConfig loading in ConfigFlowOperateCenter._async_init().

This test verifies that _async_init() can successfully process a TaxConfig
config entry. Currently, the elif chain in _async_init() does NOT include
'TaxConfig', so the code raises:

    KahunaException("配置类型TaxConfig不存在")

at line 202. This means the test will FAIL (RED phase).

Expected behavior after Task 9 (adds `elif config.config_type == 'TaxConfig':`):
- No exception is raised
- self.tax_confs is populated with the config_value
- This test PASSES
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src_v2.core.utils import KahunaException
from src_v2.model.EVE.industry.plan_configflow_operate import (
    ConfigFlowOperateCenter,
    EveIndustryPlanConfigFlowDBUtils,
    EveIndustryPlanConfigFlowConfigDBUtils,
)


@pytest.mark.unit
class TestTaxConfigLoading:
    """Tests for TaxConfig loading in ConfigFlowOperateCenter._async_init()."""

    async def test_tax_config_loading_succeeds(self):
        """TaxConfig should be loaded into self.tax_confs without error.

        RED phase: FAILS because _async_init() raises KahunaException
        for unknown config_type 'TaxConfig'. This is expected to fail
        until Task 9 adds the elif branch.
        """
        # ------------------------------------------------------------------
        # Arrange
        # ------------------------------------------------------------------
        user_name = "test_user"
        plan_name = "test_plan"
        plan_settings = {}
        config_value = {"target_category": "矿物", "tax_rate": 10.0}

        # Mock config object returned by DB
        mock_config = MagicMock()
        mock_config.config_type = "TaxConfig"
        mock_config.config_value = config_value

        # Mock config flow — contains a single config id [1]
        mock_config_flow = MagicMock()
        mock_config_flow.config_list = [1]

        # ------------------------------------------------------------------
        # Patch the two DBUtils classmethods used by _async_init()
        # ------------------------------------------------------------------
        with (
            patch.object(
                EveIndustryPlanConfigFlowDBUtils,
                "select_configflow_by_user_name_and_plan_name",
                new=AsyncMock(return_value=mock_config_flow),
            ),
            patch.object(
                EveIndustryPlanConfigFlowConfigDBUtils,
                "select_by_id",
                new=AsyncMock(return_value=mock_config),
            ),
        ):
            # ------------------------------------------------------------------
            # Act
            # ------------------------------------------------------------------
            # sub_process=True + dm=None avoids instantiating real DB managers
            center = ConfigFlowOperateCenter(
                user_name=user_name,
                plan_name=plan_name,
                plan_settings=plan_settings,
                sub_process=True,
                dm=None,
            )

            # This will RAISE KahunaException because 'TaxConfig' is unknown —
            #   the test FAILS here in RED phase.
            await center._async_init(user_name, plan_name)

            # ------------------------------------------------------------------
            # Assert — unreachable until TaxConfig is handled
            # ------------------------------------------------------------------
            # After successful loading, tax_confs should contain the config_value
            assert len(center.tax_confs) == 1
            assert center.tax_confs[0] == config_value
