# -*- coding: utf-8 -*-
"""
Tax Calculation 集成测试

端到端验证 calculate_tax_items 函数的完整税务计算流程。
该函数是独立函数，无需数据库或外部 API 即可直接测试。
"""

import pytest

from src_v2.model.EVE.industry.industry_utils.plan_utils import calculate_tax_items


@pytest.mark.integration
class TestTaxIntegration:
    """calculate_tax_items 端到端集成测试"""

    def test_calculate_tax_items_with_valid_data(self):
        """完整税务计算流程：多分类材料 + 多税率配置 → 验证结果结构和数值"""
        # 构造 children，模拟 eiv_cost_dict 结构
        # 矿类材料总成本: 3*10000 + 5*8000 = 30000 + 40000 = 70000
        # PI 材料总成本: 10*500 + 20*300 = 5000 + 6000 = 11000
        # 杂货总成本: 1*2000 = 2000
        children = [
            {
                'material_type_node': '矿',
                'quantity': 3,
                'jita_buy_price': 10000,
            },
            {
                'material_type_node': '矿',
                'quantity': 5,
                'jita_buy_price': 8000,
            },
            {
                'material_type_node': 'PI',
                'quantity': 10,
                'jita_buy_price': 500,
            },
            {
                'material_type_node': 'PI',
                'quantity': 20,
                'jita_buy_price': 300,
            },
            {
                'material_type_node': '杂货',
                'quantity': 1,
                'jita_buy_price': 2000,
            },
        ]

        # 构造 tax_confs: 对矿 2.5% 税，对 PI 5% 税
        tax_confs = [
            {'target_category': '矿', 'tax_rate': 2.5},
            {'target_category': 'PI', 'tax_rate': 5.0},
        ]

        result = calculate_tax_items(children, tax_confs)

        # 验证结果长度
        assert len(result) == 2

        # 验证第一条结果（矿税）
        assert result[0]['category'] == '矿税'
        assert result[0]['target_category'] == '矿'
        assert result[0]['tax_rate'] == 2.5
        # 矿总成本 = 70000, 税 = round(70000 * 2.5 / 100, 2) = round(1750.0, 2) = 1750.0
        assert result[0]['tax_amount'] == 1750.0

        # 验证第二条结果（PI税）
        assert result[1]['category'] == 'PI税'
        assert result[1]['target_category'] == 'PI'
        assert result[1]['tax_rate'] == 5.0
        # PI总成本 = 11000, 税 = round(11000 * 5.0 / 100, 2) = round(550.0, 2) = 550.0
        assert result[1]['tax_amount'] == 550.0

    def test_calculate_tax_items_empty_taxes(self):
        """空税率配置 → 返回空列表"""
        children = [
            {
                'material_type_node': '矿',
                'quantity': 1,
                'jita_buy_price': 1000,
            },
        ]
        tax_confs = []

        result = calculate_tax_items(children, tax_confs)

        assert result == []
