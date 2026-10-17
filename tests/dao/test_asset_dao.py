# -*- coding: utf-8 -*-
"""EveAssetView DAO 集成测试 (SQLite in-memory)

测试 EveAssetViewDBUtils 的 CRUD 操作和 JSONB 存储。
"""
import pytest

from src_v2.core.database import model
from src_v2.core.database.kahuna_database_utils_v2 import EveAssetViewDBUtils

pytestmark = pytest.mark.dao


# ═══════════════════════════════════════════════════════════════════════
# EveAssetViewDBUtils
# ═══════════════════════════════════════════════════════════════════════

class TestEveAssetViewDBUtils:
    """EveAssetViewDBUtils 的 CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_view_and_select_by_sid(self, db_session):
        """save_obj 创建视图后 select_by_sid 能查到"""
        view = model.EveAssetView(
            sid="view_001",
            user_name="test_user",
            tag="production",
            view_type="industry",
            public=True,
        )
        await EveAssetViewDBUtils.save_obj(view)

        found = await EveAssetViewDBUtils.select_by_sid("view_001")
        assert found is not None
        assert found.sid == "view_001"
        assert found.user_name == "test_user"
        assert found.tag == "production"
        assert found.view_type == "industry"
        assert found.public is True

    @pytest.mark.asyncio
    async def test_select_by_sid_nonexistent(self, db_session):
        """select_by_sid 对不存在的 sid 返回 None"""
        found = await EveAssetViewDBUtils.select_by_sid("nonexistent_sid")
        assert found is None

    @pytest.mark.asyncio
    async def test_select_by_user_name(self, db_session):
        """select_by_user_name 返回用户的所有视图（异步迭代器）"""
        for i in range(3):
            view = model.EveAssetView(
                sid=f"view_{i}",
                user_name="multi_view_user",
                tag=f"tag_{i}",
            )
            await EveAssetViewDBUtils.save_obj(view)

        # 其他用户的视图不应出现在结果中
        other = model.EveAssetView(
            sid="other_view",
            user_name="other_user",
        )
        await EveAssetViewDBUtils.save_obj(other)

        iterator = await EveAssetViewDBUtils.select_by_user_name("multi_view_user")
        views = [v async for v in iterator]
        assert len(views) == 3
        sids = {v.sid for v in views}
        assert sids == {"view_0", "view_1", "view_2"}

    @pytest.mark.asyncio
    async def test_select_by_user_name_empty(self, db_session):
        """没有视图的用户返回空结果"""
        iterator = await EveAssetViewDBUtils.select_by_user_name("no_views_here")
        views = [v async for v in iterator]
        assert len(views) == 0

    @pytest.mark.asyncio
    async def test_delete_view(self, db_session):
        """delete_obj 删除视图后 select_by_sid 返回 None"""
        view = model.EveAssetView(
            sid="to_delete",
            user_name="del_user",
        )
        await EveAssetViewDBUtils.save_obj(view)

        assert await EveAssetViewDBUtils.select_by_sid("to_delete") is not None

        await EveAssetViewDBUtils.delete_obj(view)

        assert await EveAssetViewDBUtils.select_by_sid("to_delete") is None

    @pytest.mark.asyncio
    async def test_update_view_via_merge(self, db_session):
        """merge 更新已存在的视图"""
        view = model.EveAssetView(
            sid="update_view",
            user_name="update_user",
            tag="old_tag",
        )
        await EveAssetViewDBUtils.save_obj(view)

        found = await EveAssetViewDBUtils.select_by_sid("update_view")
        found.tag = "new_tag"
        found.view_type = "custom_type"
        found.public = True
        await EveAssetViewDBUtils.merge(found)

        updated = await EveAssetViewDBUtils.select_by_sid("update_view")
        assert updated.tag == "new_tag"
        assert updated.view_type == "custom_type"
        assert updated.public is True

    @pytest.mark.asyncio
    async def test_jsonb_config_roundtrip(self, db_session):
        """config 字段 JSONB 往返：Python dict → DB → Python dict"""
        config_data = {
            "columns": ["name", "quantity", "price"],
            "filters": {"min_quantity": 100, "max_price": 5000000},
            "sort_by": "name",
            "group_by": "category",
        }

        view = model.EveAssetView(
            sid="config_test",
            user_name="config_user",
            config=config_data,
        )
        await EveAssetViewDBUtils.save_obj(view)

        found = await EveAssetViewDBUtils.select_by_sid("config_test")
        assert found.config == config_data
        assert found.config["columns"] == ["name", "quantity", "price"]
        assert found.config["filters"]["min_quantity"] == 100

    @pytest.mark.asyncio
    async def test_jsonb_filter_roundtrip(self, db_session):
        """filter 字段 JSONB 往返：复杂嵌套结构"""
        filter_data = {
            "type_ids": [123, 456, 789],
            "group": "ships",
            "price_range": {"min": 1000000, "max": 500000000},
            "exclude": {"categories": ["ammo", "drone"], "meta_groups": [1, 2, 3]},
        }

        view = model.EveAssetView(
            sid="filter_test",
            user_name="filter_user",
            filter=filter_data,
        )
        await EveAssetViewDBUtils.save_obj(view)

        found = await EveAssetViewDBUtils.select_by_sid("filter_test")
        assert found.filter == filter_data
        assert found.filter["type_ids"] == [123, 456, 789]
        assert found.filter["price_range"]["max"] == 500000000

    @pytest.mark.asyncio
    async def test_jsonb_both_config_and_filter(self, db_session):
        """同时存储 config 和 filter JSONB 字段"""
        config = {"theme": "dark", "refresh_interval": 30}
        filter_data = {"type_ids": [999], "only_public": True}

        view = model.EveAssetView(
            sid="dual_jsonb",
            user_name="dual_user",
            config=config,
            filter=filter_data,
        )
        await EveAssetViewDBUtils.save_obj(view)

        found = await EveAssetViewDBUtils.select_by_sid("dual_jsonb")
        assert found.config == config
        assert found.filter == filter_data

    @pytest.mark.asyncio
    async def test_jsonb_none_default(self, db_session):
        """未设置 JSONB 列时默认为 None"""
        view = model.EveAssetView(
            sid="no_jsonb",
            user_name="nojson_user",
            tag="basic",
        )
        await EveAssetViewDBUtils.save_obj(view)

        found = await EveAssetViewDBUtils.select_by_sid("no_jsonb")
        assert found.config is None
        assert found.filter is None
        assert found.tag == "basic"

    @pytest.mark.asyncio
    async def test_merge_update_jsonb(self, db_session):
        """merge 更新 JSONB 字段"""
        view = model.EveAssetView(
            sid="merge_jsonb",
            user_name="merge_user",
            config={"version": 1},
        )
        await EveAssetViewDBUtils.save_obj(view)

        found = await EveAssetViewDBUtils.select_by_sid("merge_jsonb")
        found.config = {"version": 2, "updated": True, "new_field": [1, 2, 3]}
        found.filter = {"active": True}
        await EveAssetViewDBUtils.merge(found)

        updated = await EveAssetViewDBUtils.select_by_sid("merge_jsonb")
        assert updated.config == {"version": 2, "updated": True, "new_field": [1, 2, 3]}
        assert updated.filter == {"active": True}

    @pytest.mark.asyncio
    async def test_primary_key_uniqueness(self, db_session):
        """sid 是主键，重复插入应抛出 IntegrityError"""
        view1 = model.EveAssetView(
            sid="pk_test",
            user_name="user1",
        )
        await EveAssetViewDBUtils.save_obj(view1)

        from sqlalchemy.exc import IntegrityError

        view2 = model.EveAssetView(
            sid="pk_test",  # 相同 sid
            user_name="user2",
        )
        with pytest.raises(IntegrityError):
            await EveAssetViewDBUtils.save_obj(view2)
