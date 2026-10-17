# -*- coding: utf-8 -*-
"""EveIndustryPlan 和 EveIndustryPlanProduct DAO 集成测试 (SQLite in-memory)

测试 EveIndustryPlanDBUtils 和 EveIndustryPlanProductDBUtils 的 CRUD 操作。
"""
import pytest

from src_v2.core.database import model
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveIndustryPlanDBUtils,
    EveIndustryPlanProductDBUtils,
    EveIndustryPlanProductJSONBDBUtils,
)
from src_v2.core.utils import KahunaException
from src_v2.model.EVE.industry.industry_manager import IndustryManager

pytestmark = pytest.mark.dao


# ═══════════════════════════════════════════════════════════════════════
# EveIndustryPlanDBUtils
# ═══════════════════════════════════════════════════════════════════════

class TestEveIndustryPlanDBUtils:
    """EveIndustryPlanDBUtils 的 CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_plan_and_select_by_name(self, db_session):
        """save_obj 创建计划后 select_by_user_name_and_plan_name 能查到"""
        plan = model.EveIndustryPlan(
            user_name="test_user",
            plan_name="my_plan",
            share_token="token_abc123",
        )
        await EveIndustryPlanDBUtils.save_obj(plan)

        found = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(
            "test_user", "my_plan"
        )
        assert found is not None
        assert found.user_name == "test_user"
        assert found.plan_name == "my_plan"
        assert found.share_token == "token_abc123"

    @pytest.mark.asyncio
    async def test_select_nonexistent_plan(self, db_session):
        """不存在的计划返回 None"""
        found = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(
            "test_user", "nonexistent"
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_select_all_by_user_name(self, db_session):
        """select_all_by_user_name 返回用户的全部计划（异步迭代器）"""
        for i in range(3):
            plan = model.EveIndustryPlan(
                user_name="multi_plan_user",
                plan_name=f"plan_{i}",
                share_token=f"token_{i}",
            )
            await EveIndustryPlanDBUtils.save_obj(plan)

        # 为其他用户也创建一个（应不出现在结果中）
        other = model.EveIndustryPlan(
            user_name="other_user",
            plan_name="other_plan",
            share_token="other_token",
        )
        await EveIndustryPlanDBUtils.save_obj(other)

        iterator = await EveIndustryPlanDBUtils.select_all_by_user_name("multi_plan_user")
        plans = [p async for p in iterator]
        assert len(plans) == 3
        plan_names = {p.plan_name for p in plans}
        assert plan_names == {"plan_0", "plan_1", "plan_2"}

    @pytest.mark.asyncio
    async def test_select_by_share_token(self, db_session):
        """select_by_share_token 根据分享令牌查询计划"""
        plan = model.EveIndustryPlan(
            user_name="share_user",
            plan_name="shared_plan",
            share_token="unique_share_token",
        )
        await EveIndustryPlanDBUtils.save_obj(plan)

        found = await EveIndustryPlanDBUtils.select_by_share_token("unique_share_token")
        assert found is not None
        assert found.plan_name == "shared_plan"
        assert found.user_name == "share_user"

    @pytest.mark.asyncio
    async def test_select_by_share_token_nonexistent(self, db_session):
        """不存在的 share_token 返回 None"""
        found = await EveIndustryPlanDBUtils.select_by_share_token("no_such_token")
        assert found is None

    @pytest.mark.asyncio
    async def test_delete_plan(self, db_session):
        """delete_by_user_name_and_plan_name 删除计划"""
        plan = model.EveIndustryPlan(
            user_name="del_user",
            plan_name="del_plan",
            share_token="del_token",
        )
        await EveIndustryPlanDBUtils.save_obj(plan)
        assert (
            await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(
                "del_user", "del_plan"
            )
        ) is not None

        await EveIndustryPlanDBUtils.delete_by_user_name_and_plan_name(
            "del_user", "del_plan"
        )

        assert (
            await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(
                "del_user", "del_plan"
            )
        ) is None

    @pytest.mark.asyncio
    async def test_delete_multiple_plans_for_user(self, db_session):
        """删除同一用户的多个计划"""
        for i in range(2):
            plan = model.EveIndustryPlan(
                user_name="bulk_user",
                plan_name=f"bulk_plan_{i}",
                share_token=f"bulk_token_{i}",
            )
            await EveIndustryPlanDBUtils.save_obj(plan)

        # 另一个用户不受影响
        other = model.EveIndustryPlan(
            user_name="other_user",
            plan_name="keep_plan",
            share_token="keep_token",
        )
        await EveIndustryPlanDBUtils.save_obj(other)

        # 删除 bulk_user 的全部计划
        await EveIndustryPlanDBUtils.delete_by_user_name_and_plan_name(
            "bulk_user", "bulk_plan_0"
        )
        await EveIndustryPlanDBUtils.delete_by_user_name_and_plan_name(
            "bulk_user", "bulk_plan_1"
        )

        # 验证 bulk_user 计划已全部删除
        iterator = await EveIndustryPlanDBUtils.select_all_by_user_name("bulk_user")
        plans = [p async for p in iterator]
        assert len(plans) == 0

        # other_user 的计划不受影响
        iterator = await EveIndustryPlanDBUtils.select_all_by_user_name("other_user")
        plans = [p async for p in iterator]
        assert len(plans) == 1

    @pytest.mark.asyncio
    async def test_update_plan_via_merge(self, db_session):
        """merge 更新已存在的计划"""
        plan = model.EveIndustryPlan(
            user_name="merge_user",
            plan_name="merge_plan",
            share_token="merge_token",
            settings={"version": 1},
        )
        await EveIndustryPlanDBUtils.save_obj(plan)

        # 查询后修改并 merge
        found = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(
            "merge_user", "merge_plan"
        )
        found.settings = {"version": 2, "updated": True}
        found.public = True
        await EveIndustryPlanDBUtils.merge(found)

        # 重新查询验证
        updated = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(
            "merge_user", "merge_plan"
        )
        assert updated.settings == {"version": 2, "updated": True}
        assert updated.public is True

    @pytest.mark.asyncio
    async def test_update_share_info(self, db_session):
        """update_share_info 更新分享信息"""
        plan = model.EveIndustryPlan(
            user_name="share_info_user",
            plan_name="info_plan",
        )
        await EveIndustryPlanDBUtils.save_obj(plan)

        share_data = {
            "public": True,
            "share_token": "new_shared_token",
            "filter_snapshot": {"type_ids": [100, 200, 300]},
        }
        result = await EveIndustryPlanDBUtils.update_share_info(
            "share_info_user", "info_plan", share_data
        )
        assert result is not None
        assert result.public is True
        assert result.share_token == "new_shared_token"
        assert result.filter_snapshot == {"type_ids": [100, 200, 300]}

    @pytest.mark.asyncio
    async def test_update_share_info_nonexistent_plan(self, db_session):
        """update_share_info 对不存在的计划返回 None"""
        result = await EveIndustryPlanDBUtils.update_share_info(
            "nobody", "no_plan", {"public": True}
        )
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# EveIndustryPlanProductDBUtils
# ═══════════════════════════════════════════════════════════════════════

class TestEveIndustryPlanProductDBUtils:
    """EveIndustryPlanProductDBUtils 的 CRUD 测试"""

    @pytest.mark.asyncio
    async def test_save_and_query_product(self, db_session):
        """save_obj 创建产品后 select_all_by_user_name_and_plan_name 能查到"""
        product = model.EveIndustryPlanProduct(
            user_name="prod_user",
            plan_name="prod_plan",
            index_id=1,
            product_type_id=12345,
            quantity=100,
        )
        await EveIndustryPlanProductDBUtils.save_obj(product)

        iterator = await EveIndustryPlanProductDBUtils.select_all_by_user_name_and_plan_name(
            "prod_user", "prod_plan"
        )
        products = [p async for p in iterator]
        assert len(products) == 1
        assert products[0].product_type_id == 12345
        assert products[0].quantity == 100
        assert products[0].index_id == 1

    @pytest.mark.asyncio
    async def test_save_multiple_products(self, db_session):
        """保存多个产品后能全部查到"""
        for i in range(5):
            product = model.EveIndustryPlanProduct(
                user_name="multi_prod_user",
                plan_name="multi_plan",
                index_id=i,
                product_type_id=10000 + i,
                quantity=(i + 1) * 10,
            )
            await EveIndustryPlanProductDBUtils.save_obj(product)

        iterator = await EveIndustryPlanProductDBUtils.select_all_by_user_name_and_plan_name(
            "multi_prod_user", "multi_plan"
        )
        products = [p async for p in iterator]
        assert len(products) == 5

        # 验证数量正确
        quantities = {p.quantity for p in products}
        assert quantities == {10, 20, 30, 40, 50}

    @pytest.mark.asyncio
    async def test_delete_products_by_plan(self, db_session):
        """delete_all_by_user_name_and_plan_name 删除计划的所有产品"""
        for i in range(3):
            product = model.EveIndustryPlanProduct(
                user_name="del_prod_user",
                plan_name="del_plan",
                index_id=i,
                product_type_id=20000 + i,
                quantity=50,
            )
            await EveIndustryPlanProductDBUtils.save_obj(product)

        # 确认存在
        iterator = await EveIndustryPlanProductDBUtils.select_all_by_user_name_and_plan_name(
            "del_prod_user", "del_plan"
        )
        assert len([p async for p in iterator]) == 3

        await EveIndustryPlanProductDBUtils.delete_all_by_user_name_and_plan_name(
            "del_prod_user", "del_plan"
        )

        # 确认已全部删除
        iterator = await EveIndustryPlanProductDBUtils.select_all_by_user_name_and_plan_name(
            "del_prod_user", "del_plan"
        )
        assert len([p async for p in iterator]) == 0

    @pytest.mark.asyncio
    async def test_select_all_products_by_user(self, db_session):
        """select_all_by_user_name 跨计划查询用户的所有产品"""
        for plan_idx in range(2):
            for product_idx in range(2):
                product = model.EveIndustryPlanProduct(
                    user_name="all_prod_user",
                    plan_name=f"plan_{plan_idx}",
                    index_id=product_idx,
                    product_type_id=30000 + plan_idx * 10 + product_idx,
                    quantity=10,
                )
                await EveIndustryPlanProductDBUtils.save_obj(product)

        iterator = await EveIndustryPlanProductDBUtils.select_all_by_user_name(
            "all_prod_user"
        )
        products = [p async for p in iterator]
        assert len(products) == 4

        # 验证跨计划结果
        plan_names = {p.plan_name for p in products}
        assert plan_names == {"plan_0", "plan_1"}

    @pytest.mark.asyncio
    async def test_product_isolation_between_users(self, db_session):
        """不同用户的产品相互隔离"""
        # 用户 A 的产品
        product_a = model.EveIndustryPlanProduct(
            user_name="user_a",
            plan_name="plan_a",
            index_id=0,
            product_type_id=111,
            quantity=1,
        )
        await EveIndustryPlanProductDBUtils.save_obj(product_a)

        # 用户 B 的产品
        product_b = model.EveIndustryPlanProduct(
            user_name="user_b",
            plan_name="plan_b",
            index_id=0,
            product_type_id=222,
            quantity=2,
        )
        await EveIndustryPlanProductDBUtils.save_obj(product_b)

        # user_a 只能看到自己的
        iterator = await EveIndustryPlanProductDBUtils.select_all_by_user_name("user_a")
        products_a = [p async for p in iterator]
        assert len(products_a) == 1
        assert products_a[0].product_type_id == 111

        # user_b 只能看到自己的
        iterator = await EveIndustryPlanProductDBUtils.select_all_by_user_name("user_b")
        products_b = [p async for p in iterator]
        assert len(products_b) == 1
        assert products_b[0].product_type_id == 222


# ═══════════════════════════════════════════════════════════════════════
# 产品备注 (note) 功能测试 (TDD RED)
# ═══════════════════════════════════════════════════════════════════════

class TestIndustryPlanProductNote:
    """产品备注 note 功能的 DAO 集成测试"""

    @pytest.mark.asyncio
    async def test_save_plan_product_with_note(self, db_session):
        """保存包含备注的产品后，备注能正确持久化"""
        products = [
            {
                "type": "product",
                "type_id": 12345,
                "quantity": 100,
                "note": "测试备注",
            }
        ]
        await IndustryManager.save_plan_products(
            "note_user", "note_plan", products
        )

        plan_product = await EveIndustryPlanProductJSONBDBUtils.select_by_user_name_and_plan_name(
            "note_user", "note_plan"
        )
        assert plan_product is not None
        product_data = plan_product.product_data
        assert len(product_data) == 1
        assert product_data[0]["note"] == "测试备注"

    @pytest.mark.asyncio
    async def test_save_plan_product_without_note(self, db_session):
        """不提供备注时，product_data 不包含 note 字段"""
        products = [
            {
                "type": "product",
                "type_id": 12345,
                "quantity": 100,
            }
        ]
        await IndustryManager.save_plan_products(
            "no_note_user", "no_note_plan", products
        )

        plan_product = await EveIndustryPlanProductJSONBDBUtils.select_by_user_name_and_plan_name(
            "no_note_user", "no_note_plan"
        )
        assert plan_product is not None
        product_data = plan_product.product_data
        assert len(product_data) == 1
        assert "note" not in product_data[0]

    @pytest.mark.asyncio
    async def test_save_plan_product_note_too_long(self, db_session):
        """备注超过200字符时抛出 KahunaException"""
        products = [
            {
                "type": "product",
                "type_id": 12345,
                "quantity": 100,
                "note": "x" * 201,
            }
        ]
        with pytest.raises(KahunaException, match=".*备注.*"):
            await IndustryManager.save_plan_products(
                "long_note_user", "long_note_plan", products
            )

    @pytest.mark.asyncio
    async def test_grouped_product_with_note(self, db_session):
        """组内产品的备注能正确持久化"""
        products = [
            {
                "type": "group",
                "name": "测试组",
                "products": [
                    {
                        "type": "product",
                        "type_id": 12345,
                        "quantity": 100,
                        "note": "组内备注",
                    }
                ],
            }
        ]
        await IndustryManager.save_plan_products(
            "group_note_user", "group_note_plan", products
        )

        plan_product = await EveIndustryPlanProductJSONBDBUtils.select_by_user_name_and_plan_name(
            "group_note_user", "group_note_plan"
        )
        assert plan_product is not None
        product_data = plan_product.product_data
        assert len(product_data) == 1
        assert product_data[0]["type"] == "group"
        assert len(product_data[0]["products"]) == 1
        assert product_data[0]["products"][0]["note"] == "组内备注"
