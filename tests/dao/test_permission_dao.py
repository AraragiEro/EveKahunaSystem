"""
Permission DAO 集成测试 (SQLite in-memory)

测试 RolesDBUtils, PermissionsDBUtils, RoleHierarchyDBUtils 的 CRUD 操作。
"""
import pytest

from src_v2.core.database import model
from src_v2.core.database.kahuna_database_utils_v2 import (
    RolesDBUtils,
    PermissionsDBUtils,
    RoleHierarchyDBUtils,
)

pytestmark = pytest.mark.dao


# ═══════════════════════════════════════════════════════════════════════
# RolesDBUtils
# ═══════════════════════════════════════════════════════════════════════

class TestRolesDBUtils:
    @pytest.mark.asyncio
    async def test_save_and_select_role(self, db_session):
        """save_obj 创建角色后 select_role_by_role_name 能找到"""
        role = model.Roles(role_name="admin", role_description="管理员角色")
        await RolesDBUtils.save_obj(role)

        found = await RolesDBUtils.select_role_by_role_name("admin")
        assert found is not None
        assert found.role_name == "admin"
        assert found.role_description == "管理员角色"

    @pytest.mark.asyncio
    async def test_select_nonexistent_role(self, db_session):
        """select_role_by_role_name 对不存在的角色返回 None"""
        found = await RolesDBUtils.select_role_by_role_name("nonexistent_role")
        assert found is None

    @pytest.mark.asyncio
    async def test_delete_role_via_delete_obj(self, db_session):
        """delete_obj 删除角色"""
        role = model.Roles(role_name="temp_role", role_description="临时角色")
        await RolesDBUtils.save_obj(role)
        assert await RolesDBUtils.select_role_by_role_name("temp_role") is not None

        await RolesDBUtils.delete_obj(role)
        assert await RolesDBUtils.select_role_by_role_name("temp_role") is None

    @pytest.mark.asyncio
    async def test_delete_roles_by_role_names_batch(self, db_session):
        """delete_roles_by_role_names 批量删除多个角色"""
        for name in ["role_a", "role_b", "role_c"]:
            role = model.Roles(role_name=name, role_description=f"角色 {name}")
            await RolesDBUtils.save_obj(role)

        # 确认存在
        for name in ["role_a", "role_b", "role_c"]:
            assert await RolesDBUtils.select_role_by_role_name(name) is not None

        await RolesDBUtils.delete_roles_by_role_names(["role_a", "role_c"])

        # role_a 和 role_c 被删除，role_b 保留
        assert await RolesDBUtils.select_role_by_role_name("role_a") is None
        assert await RolesDBUtils.select_role_by_role_name("role_b") is not None
        assert await RolesDBUtils.select_role_by_role_name("role_c") is None

    @pytest.mark.asyncio
    async def test_delete_roles_empty_list_noop(self, db_session):
        """delete_roles_by_role_names 传入空列表不报错"""
        await RolesDBUtils.delete_roles_by_role_names([])

    @pytest.mark.asyncio
    async def test_delete_all_roles(self, db_session):
        """delete_all 删除所有角色"""
        for name in ["r1", "r2", "r3"]:
            role = model.Roles(role_name=name, role_description=f"角色 {name}")
            await RolesDBUtils.save_obj(role)

        await RolesDBUtils.delete_all()

        for name in ["r1", "r2", "r3"]:
            assert await RolesDBUtils.select_role_by_role_name(name) is None


# ═══════════════════════════════════════════════════════════════════════
# PermissionsDBUtils
# ═══════════════════════════════════════════════════════════════════════

class TestPermissionsDBUtils:
    @pytest.mark.asyncio
    async def test_save_and_select_permission(self, db_session):
        """save_obj 创建权限后 select_permission_by_permission_name 能找到"""
        perm = model.Permissions(
            permission_name="read:users", permission_description="查看用户"
        )
        await PermissionsDBUtils.save_obj(perm)

        found = await PermissionsDBUtils.select_permission_by_permission_name(
            "read:users"
        )
        assert found is not None
        assert found.permission_name == "read:users"
        assert found.permission_description == "查看用户"

    @pytest.mark.asyncio
    async def test_select_nonexistent_permission(self, db_session):
        """select_permission_by_permission_name 对不存在的返回 None"""
        found = await PermissionsDBUtils.select_permission_by_permission_name(
            "no:perm"
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_merge_update_permission(self, db_session):
        """merge 更新已存在的权限描述"""
        perm = model.Permissions(
            permission_name="write:posts", permission_description="旧描述"
        )
        await PermissionsDBUtils.save_obj(perm)

        updated = model.Permissions(
            permission_name="write:posts", permission_description="新描述"
        )
        await PermissionsDBUtils.merge(updated)

        found = await PermissionsDBUtils.select_permission_by_permission_name(
            "write:posts"
        )
        assert found is not None
        assert found.permission_description == "新描述"

    @pytest.mark.asyncio
    async def test_delete_permission(self, db_session):
        """delete_obj 删除权限"""
        perm = model.Permissions(
            permission_name="delete:temp", permission_description="临时"
        )
        await PermissionsDBUtils.save_obj(perm)

        await PermissionsDBUtils.delete_obj(perm)
        found = await PermissionsDBUtils.select_permission_by_permission_name(
            "delete:temp"
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_delete_all_permissions(self, db_session):
        """delete_all 删除所有权限"""
        for name in ["p1", "p2"]:
            perm = model.Permissions(permission_name=name, permission_description=f"权限 {name}")
            await PermissionsDBUtils.save_obj(perm)

        await PermissionsDBUtils.delete_all()

        for name in ["p1", "p2"]:
            assert await PermissionsDBUtils.select_permission_by_permission_name(name) is None


# ═══════════════════════════════════════════════════════════════════════
# RoleHierarchyDBUtils
# ═══════════════════════════════════════════════════════════════════════

class TestRoleHierarchyDBUtils:
    async def _create_role(self, name: str):
        """辅助：创建角色"""
        role = model.Roles(role_name=name, role_description=f"角色 {name}")
        await RolesDBUtils.save_obj(role)

    async def _create_hierarchy(self, parent: str, child: str):
        """辅助：创建角色层级关系"""
        hierarchy = model.RoleHierarchy(parent_role_name=parent, child_role_name=child)
        await RoleHierarchyDBUtils.save_obj(hierarchy)

    @pytest.mark.asyncio
    async def test_create_and_query_by_parent(self, db_session):
        """select_all_by_parent_role_name 返回所有子角色"""
        await self._create_role("parent")
        await self._create_role("child1")
        await self._create_role("child2")
        await self._create_hierarchy("parent", "child1")
        await self._create_hierarchy("parent", "child2")

        children = []
        async with await RoleHierarchyDBUtils.select_all_by_parent_role_name("parent") as it:
            async for row in it:
                children.append(row.child_role_name)

        assert sorted(children) == ["child1", "child2"]

    @pytest.mark.asyncio
    async def test_create_and_query_by_child(self, db_session):
        """select_all_by_child_role_name 返回所有父角色"""
        await self._create_role("top")
        await self._create_role("mid")
        await self._create_role("bottom")
        await self._create_hierarchy("top", "bottom")
        await self._create_hierarchy("mid", "bottom")

        parents = []
        async with await RoleHierarchyDBUtils.select_all_by_child_role_name("bottom") as it:
            async for row in it:
                parents.append(row.parent_role_name)

        assert sorted(parents) == ["mid", "top"]

    @pytest.mark.asyncio
    async def test_select_empty_hierarchy(self, db_session):
        """select_all_by_parent_role_name 对无子角色的返回空"""
        await self._create_role("lonely")

        children = []
        async with await RoleHierarchyDBUtils.select_all_by_parent_role_name("lonely") as it:
            async for _ in it:
                children.append(_)

        assert len(children) == 0

    @pytest.mark.asyncio
    async def test_delete_hierarchy_by_role_names(self, db_session):
        """delete_hierarchy_by_role_names 批量删除层级关系"""
        await self._create_role("p")
        await self._create_role("c1")
        await self._create_role("c2")
        await self._create_role("c3")
        await self._create_hierarchy("p", "c1")
        await self._create_hierarchy("p", "c2")
        await self._create_hierarchy("p", "c3")

        # 删除两条关系
        await RoleHierarchyDBUtils.delete_hierarchy_by_role_names(
            [["p", "c1"], ["p", "c3"]]
        )

        # 验证 c2 仍存在
        remaining = []
        async with await RoleHierarchyDBUtils.select_all_by_parent_role_name("p") as it:
            async for row in it:
                remaining.append(row.child_role_name)

        assert remaining == ["c2"]

    @pytest.mark.asyncio
    async def test_delete_hierarchy_empty_list(self, db_session):
        """delete_hierarchy_by_role_names 空列表不报错"""
        await RoleHierarchyDBUtils.delete_hierarchy_by_role_names([])

    @pytest.mark.asyncio
    async def test_save_and_select_child_roles(self, db_session):
        """select_child_roles_by_role_name 返回所有子角色"""
        await self._create_role("boss")
        await self._create_role("worker1")
        await self._create_role("worker2")
        await self._create_hierarchy("boss", "worker1")
        await self._create_hierarchy("boss", "worker2")

        children = []
        async with await RoleHierarchyDBUtils.select_child_roles_by_role_name("boss") as it:
            async for row in it:
                children.append(row.child_role_name)

        assert sorted(children) == ["worker1", "worker2"]

    @pytest.mark.asyncio
    async def test_save_and_select_parent_roles(self, db_session):
        """select_parent_roles_by_role_name 返回所有父角色"""
        await self._create_role("grandparent")
        await self._create_role("parent")
        await self._create_role("me")
        await self._create_hierarchy("grandparent", "me")
        await self._create_hierarchy("parent", "me")

        parents = []
        async with await RoleHierarchyDBUtils.select_parent_roles_by_role_name("me") as it:
            async for row in it:
                parents.append(row.parent_role_name)

        assert sorted(parents) == ["grandparent", "parent"]
