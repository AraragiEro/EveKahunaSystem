# -*- coding: utf-8 -*-
"""
get_material_type 单元测试

测试材料类型分类函数在各种 group/category 下的返回值。

RED test: test_mineral_returns_kuangwu 当前会失败，
因为 get_material_type() 对 group=="Mineral" 返回 "矿石"，
但期望改为 "矿物"。
"""

import pytest
from unittest.mock import AsyncMock, patch

# 所有 group→期望值映射（按 material_utils.py 中顺序）
_GROUP_MAP = {
    "Mineral": "矿物",  # ← RED: 目前返回 "矿石"，期望 "矿物"
    "Ice Product": "冰矿产物",
    "Fuel Block": "燃料块",
    "Moon Materials": "元素",
    "Harvestable Cloud": "气云",
}

_CATEGORY_MAP = {
    "Planetary Commodities": "行星工业",
}


@pytest.mark.unit
class TestGetMaterialType:
    """get_material_type 函数单元测试"""

    @staticmethod
    def _make_mock_sde(group: str | None = None, category: str | None = None):
        """
        创建 SdeUtils mock，使 get_groupname_by_id / get_category_by_id
        返回指定值。
        """
        mock = AsyncMock()
        mock.get_groupname_by_id = AsyncMock(return_value=group)
        mock.get_category_by_id = AsyncMock(return_value=category)
        return mock

    @pytest.mark.asyncio
    async def test_mineral_returns_kuangwu(self):
        """Mineral → 返回 "矿物"（当前返回 "矿石"，此测试为 RED）"""
        mock_sde = self._make_mock_sde(group="Mineral", category=None)
        with patch(
            "src_v2.model.EVE.industry.industry_utils.material_utils.SdeUtils",
            new=mock_sde,
        ):
            from src_v2.model.EVE.industry.industry_utils.material_utils import (
                get_material_type,
            )

            result = await get_material_type(12345)
            assert result == "矿物", f"期望 '矿物'，得到 '{result}'"

    @pytest.mark.asyncio
    async def test_ice_product_returns_bingkuang(self):
        """Ice Product → 返回 "冰矿产物"（应通过）"""
        mock_sde = self._make_mock_sde(group="Ice Product", category=None)
        with patch(
            "src_v2.model.EVE.industry.industry_utils.material_utils.SdeUtils",
            new=mock_sde,
        ):
            from src_v2.model.EVE.industry.industry_utils.material_utils import (
                get_material_type,
            )

            result = await get_material_type(12345)
            assert result == "冰矿产物"

    @pytest.mark.asyncio
    async def test_fuel_block_returns_ranliao(self):
        """Fuel Block → 返回 "燃料块"（应通过）"""
        mock_sde = self._make_mock_sde(group="Fuel Block", category=None)
        with patch(
            "src_v2.model.EVE.industry.industry_utils.material_utils.SdeUtils",
            new=mock_sde,
        ):
            from src_v2.model.EVE.industry.industry_utils.material_utils import (
                get_material_type,
            )

            result = await get_material_type(12345)
            assert result == "燃料块"

    @pytest.mark.asyncio
    async def test_moon_materials_returns_yuansu(self):
        """Moon Materials → 返回 "元素"（应通过）"""
        mock_sde = self._make_mock_sde(group="Moon Materials", category=None)
        with patch(
            "src_v2.model.EVE.industry.industry_utils.material_utils.SdeUtils",
            new=mock_sde,
        ):
            from src_v2.model.EVE.industry.industry_utils.material_utils import (
                get_material_type,
            )

            result = await get_material_type(12345)
            assert result == "元素"

    @pytest.mark.asyncio
    async def test_harvestable_cloud_returns_qiyun(self):
        """Harvestable Cloud → 返回 "气云"（应通过）"""
        mock_sde = self._make_mock_sde(group="Harvestable Cloud", category=None)
        with patch(
            "src_v2.model.EVE.industry.industry_utils.material_utils.SdeUtils",
            new=mock_sde,
        ):
            from src_v2.model.EVE.industry.industry_utils.material_utils import (
                get_material_type,
            )

            result = await get_material_type(12345)
            assert result == "气云"

    @pytest.mark.asyncio
    async def test_planetary_commodities_returns_xingxing(self):
        """Planetary Commodities → 返回 "行星工业"（应通过）"""
        mock_sde = self._make_mock_sde(
            group="Some Other Group", category="Planetary Commodities"
        )
        with patch(
            "src_v2.model.EVE.industry.industry_utils.material_utils.SdeUtils",
            new=mock_sde,
        ):
            from src_v2.model.EVE.industry.industry_utils.material_utils import (
                get_material_type,
            )

            result = await get_material_type(12345)
            assert result == "行星工业"

    @pytest.mark.asyncio
    async def test_unknown_returns_zahuo(self):
        """未知 group/category → 返回 "杂货"（应通过）"""
        mock_sde = self._make_mock_sde(group="Unknown", category="Something Else")
        with patch(
            "src_v2.model.EVE.industry.industry_utils.material_utils.SdeUtils",
            new=mock_sde,
        ):
            from src_v2.model.EVE.industry.industry_utils.material_utils import (
                get_material_type,
            )

            result = await get_material_type(99999)
            assert result == "杂货"
