"""
User DAO 集成测试 (SQLite in-memory)

测试 UserDBUtils, UserDataDBUtils, UserQQBindingDBUtils 的 CRUD 操作。
"""
import pytest
from datetime import datetime

from src_v2.core.database import model
from src_v2.core.database.kahuna_database_utils_v2 import (
    UserDBUtils,
    UserDataDBUtils,
    UserQQBindingDBUtils,
)

pytestmark = pytest.mark.dao


# ═══════════════════════════════════════════════════════════════════════
# UserDBUtils
# ═══════════════════════════════════════════════════════════════════════

class TestUserDBUtils:
    @pytest.mark.asyncio
    async def test_save_and_select_user(self, db_session):
        """save_obj 创建用户后 select_user_by_user_name 能找到"""
        user = model.User(
            user_name="test_user",
            create_date=datetime.utcnow(),
            password_hash="hash_abc",
        )
        await UserDBUtils.save_obj(user)

        found = await UserDBUtils.select_user_by_user_name("test_user")
        assert found is not None
        assert found.user_name == "test_user"
        assert found.password_hash == "hash_abc"

    @pytest.mark.asyncio
    async def test_select_nonexistent_user(self, db_session):
        """select_user_by_user_name 对不存在的用户返回 None"""
        found = await UserDBUtils.select_user_by_user_name("nobody")
        assert found is None

    @pytest.mark.asyncio
    async def test_merge_update_user(self, db_session):
        """merge 更新已存在的用户"""
        user = model.User(
            user_name="merge_user",
            create_date=datetime.utcnow(),
            password_hash="old_hash",
        )
        await UserDBUtils.save_obj(user)

        # 创建新实例模拟更新
        updated = model.User(
            user_name="merge_user",
            create_date=datetime.utcnow(),
            password_hash="new_hash",
        )
        await UserDBUtils.merge(updated)

        found = await UserDBUtils.select_user_by_user_name("merge_user")
        assert found is not None
        assert found.password_hash == "new_hash"

    @pytest.mark.asyncio
    async def test_delete_user_by_username(self, db_session):
        """delete_user_by_user_username 删除用户"""
        user = model.User(
            user_name="to_delete",
            create_date=datetime.utcnow(),
            password_hash="hash",
        )
        await UserDBUtils.save_obj(user)

        # 确认存在
        assert await UserDBUtils.select_user_by_user_name("to_delete") is not None

        await UserDBUtils.delete_user_by_user_username("to_delete")

        # 确认已删除
        assert await UserDBUtils.select_user_by_user_name("to_delete") is None

    @pytest.mark.asyncio
    async def test_delete_all_users(self, db_session):
        """delete_all 删除所有用户"""
        for i in range(3):
            user = model.User(
                user_name=f"bulk_user_{i}",
                create_date=datetime.utcnow(),
                password_hash=f"hash_{i}",
            )
            await UserDBUtils.save_obj(user)

        # 确认存在
        assert await UserDBUtils.select_user_by_user_name("bulk_user_0") is not None

        await UserDBUtils.delete_all()

        # 全部删除
        for i in range(3):
            assert await UserDBUtils.select_user_by_user_name(f"bulk_user_{i}") is None


# ═══════════════════════════════════════════════════════════════════════
# UserDataDBUtils
# ═══════════════════════════════════════════════════════════════════════

class TestUserDataDBUtils:
    @pytest.mark.asyncio
    async def test_save_and_select_user_data(self, db_session):
        """保存 UserData 后能通过 select_user_data_by_user_name 查询"""
        # 先创建 User（FK 约束）
        user = model.User(
            user_name="data_user",
            create_date=datetime.utcnow(),
            password_hash="hash",
        )
        await UserDBUtils.save_obj(user)

        user_data = model.UserData(user_name="data_user", user_qq=123456)
        await UserDataDBUtils.save_obj(user_data)

        found = await UserDataDBUtils.select_user_data_by_user_name("data_user")
        assert found is not None
        assert found.user_name == "data_user"
        assert found.user_qq == 123456

    @pytest.mark.asyncio
    async def test_select_nonexistent_user_data(self, db_session):
        """select_user_data_by_user_name 对不存在的返回 None"""
        found = await UserDataDBUtils.select_user_data_by_user_name("nobody_data")
        assert found is None

    @pytest.mark.asyncio
    async def test_update_and_get_user_setting(self, db_session):
        """update_user_setting 设置后 get_user_setting 能读取"""
        user = model.User(
            user_name="settings_user",
            create_date=datetime.utcnow(),
            password_hash="hash",
        )
        await UserDBUtils.save_obj(user)

        user_data = model.UserData(user_name="settings_user")
        await UserDataDBUtils.save_obj(user_data)

        # 更新设置
        await UserDataDBUtils.update_user_setting(
            "settings_user", "theme", "dark"
        )
        await UserDataDBUtils.update_user_setting(
            "settings_user", "lang", "zh"
        )

        # 读取设置
        assert await UserDataDBUtils.get_user_setting("settings_user", "theme") == "dark"
        assert await UserDataDBUtils.get_user_setting("settings_user", "lang") == "zh"

    @pytest.mark.asyncio
    async def test_get_user_setting_default_value(self, db_session):
        """get_user_setting 对不存在的 key 返回默认值"""
        user = model.User(
            user_name="default_user",
            create_date=datetime.utcnow(),
            password_hash="hash",
        )
        await UserDBUtils.save_obj(user)

        user_data = model.UserData(user_name="default_user")
        await UserDataDBUtils.save_obj(user_data)

        assert await UserDataDBUtils.get_user_setting(
            "default_user", "nonexistent", default_value=42
        ) == 42

    @pytest.mark.asyncio
    async def test_delete_user_data(self, db_session):
        """delete_user_data_by_user_name 删除用户数据"""
        user = model.User(
            user_name="del_data",
            create_date=datetime.utcnow(),
            password_hash="hash",
        )
        await UserDBUtils.save_obj(user)

        user_data = model.UserData(user_name="del_data")
        await UserDataDBUtils.save_obj(user_data)
        assert await UserDataDBUtils.select_user_data_by_user_name("del_data") is not None

        await UserDataDBUtils.delete_user_data_by_user_name("del_data")
        assert await UserDataDBUtils.select_user_data_by_user_name("del_data") is None


# ═══════════════════════════════════════════════════════════════════════
# UserQQBindingDBUtils
# ═══════════════════════════════════════════════════════════════════════

class TestUserQQBindingDBUtils:
    @pytest.mark.asyncio
    async def test_save_and_select_by_user_name(self, db_session):
        """保存 QQ 绑定后能通过 user_name 查询"""
        user = model.User(
            user_name="qq_user",
            create_date=datetime.utcnow(),
            password_hash="hash",
        )
        await UserDBUtils.save_obj(user)

        binding = model.UserQQBinding(
            user_name="qq_user", user_qq=987654321, bind_time=datetime.utcnow()
        )
        await UserQQBindingDBUtils.save_obj(binding)

        found = await UserQQBindingDBUtils.select_by_user_name("qq_user")
        assert found is not None
        assert found.user_qq == 987654321

    @pytest.mark.asyncio
    async def test_save_and_select_by_user_qq(self, db_session):
        """保存 QQ 绑定后能通过 user_qq 查询"""
        user = model.User(
            user_name="qq_user2",
            create_date=datetime.utcnow(),
            password_hash="hash",
        )
        await UserDBUtils.save_obj(user)

        binding = model.UserQQBinding(
            user_name="qq_user2", user_qq=555555, bind_time=datetime.utcnow()
        )
        await UserQQBindingDBUtils.save_obj(binding)

        found = await UserQQBindingDBUtils.select_by_user_qq(555555)
        assert found is not None
        assert found.user_name == "qq_user2"

    @pytest.mark.asyncio
    async def test_select_nonexistent_binding(self, db_session):
        """select_by_user_name 对不存在的返回 None"""
        assert await UserQQBindingDBUtils.select_by_user_name("no_one") is None

    @pytest.mark.asyncio
    async def test_unique_constraint_on_user_qq(self, db_session):
        """unique 约束：相同 user_qq 不能插入两次"""
        user1 = model.User(
            user_name="u1",
            create_date=datetime.utcnow(),
            password_hash="hash",
        )
        user2 = model.User(
            user_name="u2",
            create_date=datetime.utcnow(),
            password_hash="hash",
        )
        await UserDBUtils.save_obj(user1)
        await UserDBUtils.save_obj(user2)

        binding1 = model.UserQQBinding(
            user_name="u1", user_qq=123123, bind_time=datetime.utcnow()
        )
        await UserQQBindingDBUtils.save_obj(binding1)

        # 相同 user_qq 再次保存应抛出 IntegrityError
        binding2 = model.UserQQBinding(
            user_name="u2", user_qq=123123, bind_time=datetime.utcnow()
        )
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await UserQQBindingDBUtils.save_obj(binding2)

    @pytest.mark.asyncio
    async def test_delete_by_user_name(self, db_session):
        """delete_by_user_name 删除指定用户的绑定"""
        user = model.User(
            user_name="del_qq",
            create_date=datetime.utcnow(),
            password_hash="hash",
        )
        await UserDBUtils.save_obj(user)

        binding = model.UserQQBinding(
            user_name="del_qq", user_qq=777777, bind_time=datetime.utcnow()
        )
        await UserQQBindingDBUtils.save_obj(binding)
        assert await UserQQBindingDBUtils.select_by_user_name("del_qq") is not None

        await UserQQBindingDBUtils.delete_by_user_name("del_qq")
        assert await UserQQBindingDBUtils.select_by_user_name("del_qq") is None

    @pytest.mark.asyncio
    async def test_delete_by_user_qq(self, db_session):
        """delete_by_user_qq 删除指定 QQ 的绑定"""
        user = model.User(
            user_name="del_qq2",
            create_date=datetime.utcnow(),
            password_hash="hash",
        )
        await UserDBUtils.save_obj(user)

        binding = model.UserQQBinding(
            user_name="del_qq2", user_qq=888888, bind_time=datetime.utcnow()
        )
        await UserQQBindingDBUtils.save_obj(binding)
        assert await UserQQBindingDBUtils.select_by_user_qq(888888) is not None

        await UserQQBindingDBUtils.delete_by_user_qq(888888)
        assert await UserQQBindingDBUtils.select_by_user_qq(888888) is None
