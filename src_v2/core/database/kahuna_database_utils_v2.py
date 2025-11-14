from typing import AnyStr, AsyncGenerator
from sqlalchemy import delete, select, text, func, distinct, or_
from sqlalchemy.dialects.sqlite import insert as insert
from sqlalchemy.orm import aliased
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timedelta
import traceback

from .connect_manager import postgres_manager as dbm
from ..log import logger
from . import model


class _AsyncIteratorWrapper:
    """包装异步生成器，自动管理资源
    
    使用方式：
        async with await SomeDBUtils.select_all() as iterator:
            async for item in iterator:
                # 处理 item
                pass
        # 退出上下文管理器时，session 会自动关闭
    """
    def __init__(self, generator: AsyncGenerator, session):
        self._generator = generator
        self._session = session
        self._closed = False
    
    @classmethod
    async def from_stmt(cls, stmt):
        """基于给定的 SQLAlchemy 语句创建会话并返回异步迭代器包装器"""
        session = dbm._session_maker()  # pyright: ignore[reportOptionalCall]
        result = await session.execute(stmt)

        async def generator():
            try:
                for item in result.scalars():
                    yield item
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        return cls(generator(), session)
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self._closed:
            raise StopAsyncIteration
        try:
            return await self._generator.__anext__()
        except StopAsyncIteration:
            # 正常结束，立即清理资源（即使没有使用上下文管理器）
            await self._cleanup()
            raise
        except (GeneratorExit, Exception) as e:
            # 发生异常时也要清理资源
            await self._cleanup()
            if isinstance(e, GeneratorExit):
                raise
            # 其他异常继续抛出
            raise
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口，确保资源被清理"""
        await self._cleanup()
        return False  # 不抑制异常
    
    async def _cleanup(self):
        """清理资源"""
        if not self._closed:
            self._closed = True
            try:
                # 尝试关闭生成器
                if hasattr(self._generator, 'aclose'):
                    try:
                        await self._generator.aclose()
                    except Exception:
                        pass
            except Exception:
                pass
            # 关闭 session
            if self._session:
                try:
                    await self._session.close()
                except Exception:
                    pass
    
    async def aclose(self):
        """显式关闭（保持向后兼容）"""
        await self._cleanup()
    
    def __del__(self):
        """析构时确保资源被清理（虽然可能已经关闭）"""
        if not self._closed and self._session:
            # 注意：在 __del__ 中不能使用 await，所以这里只是标记
            # 实际清理由 asyncio 的事件循环处理
            # 如果对象被垃圾回收时还未关闭，会在事件循环中产生警告
            pass


class _CommonUtils:
    cls_model = None

    @classmethod
    async def insert_many(cls, rows_list):
        """异步批量插入多条记录

        :param rows_list: 要插入的数据列表，每项是一个字典
        :return: 结果代理对象"""
        if not cls.cls_model:
            raise Exception("cls_model 未设置，请勿直接使用基类")
        async with dbm.get_session() as session:
            stmt = insert(cls.cls_model).values(rows_list)
            result = await session.execute(stmt)
            return result

    @classmethod
    async def insert_many_or_update_async(cls, rows_list, index_elements):
        """
        异步批量插入或更新记录

        :param rows_list: 要插入的数据列表，每项是一个字典
        :param index_elements: 唯一索引字段列表
        :return: 结果代理对象
        """
        if not cls.cls_model:
            raise Exception("cls_model 未设置，请勿直接使用基类")
        async with dbm.get_session() as session:
            stmt = insert(cls.cls_model).values(rows_list)

            update_dict = {c.name: c for c in stmt.excluded if c.name not in index_elements}

            stmt = stmt.on_conflict_do_update(
                index_elements=index_elements,
                set_=update_dict
            )

            result = await session.execute(stmt)
            return result

    @classmethod
    async def insert_many_ignore_conflict(cls, rows_list, index_elements):
        if not cls.cls_model:
            raise Exception("cls_model 未设置，请勿直接使用基类")
        async with dbm.get_session() as session:
            stmt = insert(cls.cls_model).values(rows_list)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=index_elements
            )
            await session.execute(stmt)

    @classmethod
    async def select_all(cls):
        """返回所有记录的异步迭代器"""
        if not cls.cls_model:
            raise Exception("cls_model is None")
        stmt = select(cls.cls_model)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    def get_obj(cls):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        return cls.cls_model()

    @classmethod
    async def save_obj(cls, asset_owner_obj, session=None):
        if not session:
            async with dbm.get_session() as session:
                session.add(asset_owner_obj)
        else:
            session.add(asset_owner_obj)

    @classmethod
    async def merge(cls, obj):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        async with dbm.get_session() as session:
            await session.merge(obj)

    @classmethod
    async def delete_all(cls):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        async with dbm.get_session() as session:
            stmt = delete(cls.cls_model)
            await session.execute(stmt)

    @classmethod
    async def delete_obj(cls, obj):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        async with dbm.get_session() as session:
            # 将对象合并到当前会话
            merged_obj = await session.merge(obj)
            await session.delete(merged_obj)
            await session.commit()


class _CommonCacheUtils:
    cls_model = None
    cls_base_model = None

    @classmethod
    async def copy_base_to_cache(cls):
        if cls.cls_model == None or cls.cls_base_model == None:
            raise Exception("cls_model or cls_base_model is None")

        async with dbm.get_session() as session:
            try:
                # 清空cache表
                await session.execute(
                    delete(cls.cls_model)
                )

                # 将元数据表的数据复制到Cache表
                table_name = cls.cls_base_model.__tablename__
                cache_table_name = cls.cls_model.__tablename__
                await session.execute(
                    text(f"INSERT INTO {cache_table_name} SELECT * FROM {table_name}")
                )

                logger.info(f"从 {table_name} 复制到 {cache_table_name} 完成。")
            except Exception as e:
                print(traceback.format_stack())
                logger.error(f"从 {table_name} 复制到 {cache_table_name} 失败。")  # pyright: ignore[reportUnboundVariable]
                raise

class UserDBUtils(_CommonUtils):
    cls_model = model.User

    @classmethod
    async def select_user_by_user_name(cls, user_name: AnyStr):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def delete_user_by_user_username(cls, user_name: AnyStr, session=None):
        if not session:
            async with dbm.get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
            await session.execute(stmt)

    @classmethod
    async def select_passwd_hash_by_user_name(cls, user_name: AnyStr):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model.password_hash).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()

class UserDataDBUtils(_CommonUtils):
    cls_model = model.UserData
    @classmethod
    async def select_user_data_by_user_name(cls, user_name: AnyStr):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def delete_user_data_by_user_name(cls, user_name: AnyStr, session=None):
        if not session:
            async with dbm.get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
            await session.execute(stmt)

class RolesDBUtils(_CommonUtils):
    cls_model = model.Roles

    @classmethod
    async def select_role_by_role_name(cls, role_name: str) -> cls_model | None:
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.role_name == role_name)
            result = await session.execute(stmt)
            return result.scalars().first()
    
    @classmethod
    async def delete_roles_by_role_names(cls, role_names: list[str], session=None):
        """批量删除角色
        
        Args:
            role_names: 要删除的角色名称列表
            session: 可选的数据库会话，如果提供则使用该会话，否则创建新会话
        """
        if not role_names:
            return
        if not session:
            async with dbm.get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.role_name.in_(role_names))
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.role_name.in_(role_names))
            await session.execute(stmt)


class PermissionsDBUtils(_CommonUtils):
    cls_model = model.Permissions
    
    @classmethod
    async def select_permission_by_permission_name(cls, permission_name: str):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.permission_name == permission_name)
            result = await session.execute(stmt)
            return result.scalars().first()

class UserRolesDBUtils(_CommonUtils):
    cls_model = model.UserRoles
    
    @classmethod
    async def delete_user_roles_by_role_names(cls, role_names: list[str], session=None):
        """批量删除用户角色关联
        
        Args:
            role_names: 要删除的角色名称列表
            session: 可选的数据库会话，如果提供则使用该会话，否则创建新会话
        """
        if not role_names:
            return
        if not session:
            async with dbm.get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.role_name.in_(role_names))
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.role_name.in_(role_names))
            await session.execute(stmt)
    
    @classmethod
    async def select_user_role_by_user_name_and_role_name(cls, user_name: str, role_name: str):
        """查询用户角色关联"""
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(
                (cls.cls_model.user_name == user_name) &
                (cls.cls_model.role_name == role_name)
            )
            result = await session.execute(stmt)
            return result.scalars().first()
    
    @classmethod
    async def select_user_roles_by_user_name(cls, user_name: str):
        """查询用户的所有角色"""
        stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_user_roles_by_role_name(cls, role_name: str):
        """查询角色的所有用户"""
        stmt = select(cls.cls_model).where(cls.cls_model.role_name == role_name)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

class RolePermissionsDBUtils(_CommonUtils):
    cls_model = model.RolePermissions
    
    @classmethod
    async def delete_role_permissions_by_permission_name(cls, permission_name: str):
        async with dbm.get_session() as session:
            stmt = delete(cls.cls_model).where(cls.cls_model.permission_name == permission_name)
            await session.execute(stmt)

    @classmethod
    async def select_role_permissions_by_permission_name(cls, permission_name: str):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.permission_name == permission_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def delete_role_permissions_by_role_names(cls, role_names: list[str], session=None):
        """批量删除角色权限关联
        
        Args:
            role_names: 要删除的角色名称列表
            session: 可选的数据库会话，如果提供则使用该会话，否则创建新会话
        """
        if not role_names:
            return
        if not session:
            async with dbm.get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.role_name.in_(role_names))
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.role_name.in_(role_names))
            await session.execute(stmt)
    
    @classmethod
    async def select_role_permission_by_role_name_and_permission_name(cls, role_name: str, permission_name: str):
        """查询角色权限关联"""
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(
                (cls.cls_model.role_name == role_name) &
                (cls.cls_model.permission_name == permission_name)
            )
            result = await session.execute(stmt)
            return result.scalars().first()
    
    @classmethod
    async def select_role_permissions_by_role_name(cls, role_name: str):
        """查询角色的所有权限"""
        stmt = select(cls.cls_model).where(cls.cls_model.role_name == role_name)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

class RoleHierarchyDBUtils(_CommonUtils):
    cls_model = model.RoleHierarchy

    @classmethod
    async def select_all_by_parent_role_name(cls, parent_role_name: str):
        stmt = select(cls.cls_model).where(cls.cls_model.parent_role_name == parent_role_name)
        return await _AsyncIteratorWrapper.from_stmt(stmt)
    
    @classmethod
    async def select_all_by_child_role_name(cls, child_role_name: str):
        """查询所有以指定角色作为子角色的关系"""
        stmt = select(cls.cls_model).where(cls.cls_model.child_role_name == child_role_name)
        return await _AsyncIteratorWrapper.from_stmt(stmt)
    
    @classmethod
    async def select_parent_roles_by_role_name(cls, role_name: str):
        """查询角色的所有父角色（返回所有以该角色作为子角色的关系）"""
        stmt = select(cls.cls_model).where(cls.cls_model.child_role_name == role_name)
        return await _AsyncIteratorWrapper.from_stmt(stmt)
    
    @classmethod
    async def select_child_roles_by_role_name(cls, role_name: str):
        """查询角色的所有子角色（返回所有以该角色作为父角色的关系）"""
        stmt = select(cls.cls_model).where(cls.cls_model.parent_role_name == role_name)
        return await _AsyncIteratorWrapper.from_stmt(stmt)
    
    @classmethod
    async def delete_hierarchy_by_role_names(cls, hierarchy_pairs: list[list[str]], session=None):
        """批量删除特定的角色层级关系
        
        Args:
            hierarchy_pairs: 要删除的关系对列表，每个元素为 [parent_name, child_name]
            session: 可选的数据库会话，如果提供则使用该会话，否则创建新会话
        """
        if not hierarchy_pairs:
            return
        
        # 构建 OR 条件，匹配所有指定的关系对
        conditions = []
        for pair in hierarchy_pairs:
            if len(pair) != 2:
                raise ValueError(f"Invalid hierarchy pair: {pair}. Expected [parent_name, child_name]")
            parent_name, child_name = pair
            conditions.append(
                (cls.cls_model.parent_role_name == parent_name) &
                (cls.cls_model.child_role_name == child_name)
            )
        
        if not conditions:
            return
        
        if not session:
            async with dbm.get_session() as session:
                stmt = delete(cls.cls_model).where(or_(*conditions))
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(or_(*conditions))
            await session.execute(stmt)

class UserPermissionsDBUtils(_CommonUtils):
    cls_model = model.UserPermissions
    
    @classmethod
    async def select_user_permissions_by_user_name(cls, user_name: str):
        """查询用户的所有权限"""
        stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def delete_user_permissions_by_permission_name(cls, permission_name: str):
        async with dbm.get_session() as session:
            stmt = delete(cls.cls_model).where(cls.cls_model.permission_name == permission_name)
            await session.execute(stmt)

    @classmethod
    async def select_user_permissions_by_permission_name(cls, permission_name: str):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.permission_name == permission_name)
            result = await session.execute(stmt)
            return result.scalars().first()

class EveAuthedCharacterDBUtils(_CommonUtils):
    cls_model = model.EveAuthedCharacter

    @classmethod
    async def select_all_by_owner_user_name(cls, user_name: AnyStr):
        """根据用户名返回所有角色的异步迭代器"""
        stmt = select(cls.cls_model).where(cls.cls_model.owner_user_name == user_name)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def delete_character_by_character_id(cls, character_id: int):
        async with dbm.get_session() as session:
            stmt = delete(cls.cls_model).where(cls.cls_model.character_id == character_id)
            await session.execute(stmt)

    @classmethod
    async def select_character_by_character_name(cls, character_name: str):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.character_name == character_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_character_by_character_id(cls, character_id: int):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.character_id == character_id)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_all_characters_by_corporation_id(cls, corporation_id: int):
        """根据公司ID返回所有角色的异步迭代器"""
        stmt = select(cls.cls_model).where(cls.cls_model.corporation_id == corporation_id)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

class EvePublicCharacterInfoDBUtils(_CommonUtils):
    cls_model = model.EvePublicCharacterInfo

    @classmethod
    async def select_public_character_info_by_character_id(cls, character_id: int):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.character_id == character_id)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_public_character_info_by_name(cls, character_name: str):
        """根据角色名称查询角色信息"""
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.name == character_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_character_info_by_characterid_with_same_title(cls, character_id: int):
        """根据角色ID返回相同标题的角色信息的异步迭代器"""
        # 创建别名用于自连接
        alias = aliased(cls.cls_model)
        # 自连接：通过标题匹配，找到与给定character_id具有相同标题的所有角色
        stmt = select(cls.cls_model).join(
            alias, 
            cls.cls_model.title == alias.title
        ).where(alias.character_id == character_id)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

class EveCorporationDBUtils(_CommonUtils):
    cls_model = model.EveCorporation

    @classmethod
    async def select_corporation_by_corporation_id(cls, corporation_id: int) -> cls_model:
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.corporation_id == corporation_id)
            result = await session.execute(stmt)
            return result.scalars().first()

class EveAliasCharacterDBUtils(_CommonUtils):
    cls_model = model.EveAliasCharacter

    @classmethod
    async def select_alias_character_by_character_id(cls, character_id: int):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.alias_character_id == character_id)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_all_by_main_character_id(cls, main_character_id: int):
        stmt = select(cls.cls_model).where(cls.cls_model.main_character_id == main_character_id)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

class EveAssetPullMissionDBUtils(_CommonUtils):
    cls_model = model.EveAssetPullMission

    @classmethod
    async def select_mission_by_owner_id_and_owner_type(cls, asset_owner_id: int, asset_owner_type: str):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.asset_owner_id == asset_owner_id).where(cls.cls_model.asset_owner_type == asset_owner_type)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_mission_by_owner_id(cls, asset_owner_id: int):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.asset_owner_id == asset_owner_id)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_all_by_owner_id_and_owner_type(cls, asset_owner_id: int, asset_owner_type: str):
        stmt = select(cls.cls_model).where(cls.cls_model.asset_owner_id == asset_owner_id).where(cls.cls_model.asset_owner_type == asset_owner_type)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name).order_by(cls.cls_model.id)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

class EveIndustryPlanDBUtils(_CommonUtils):
    cls_model = model.EveIndustryPlan

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name).order_by(cls.cls_model.id)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_by_user_name_and_plan_name(cls, user_name: str, plan_name: str):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name).where(cls.cls_model.plan_name == plan_name)
            result = await session.execute(stmt)
            return result.scalars().first()

class EveIndustryPlanProductDBUtils(_CommonUtils):
    cls_model = model.EveIndustryPlanProduct

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name).order_by(cls.cls_model.id)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_all_by_user_name_and_plan_name(cls, user_name: str, plan_name: str):
        stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name).where(cls.cls_model.plan_name == plan_name)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def delete_all_by_user_name_and_plan_name(cls, user_name: str, plan_name: str, session=None):
        if not session:
            async with dbm.get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name).where(cls.cls_model.plan_name == plan_name)
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name).where(cls.cls_model.plan_name == plan_name)
            await session.execute(stmt)

class EveIndustryAssetContainerPermissionDBUtils(_CommonUtils):
    cls_model = model.EveIndustryAssetContainerPermission

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name).order_by(cls.cls_model.id)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

class EveIndustryPlanConfigFlowConfigDBUtils(_CommonUtils):
    cls_model = model.EveIndustryPlanConfigFlowConfig

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name).order_by(cls.cls_model.id)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_by_id(cls, id: int):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.id == id)
            result = await session.execute(stmt)
            return result.scalars().first()

class EveIndustryPlanConfigFlowDBUtils(_CommonUtils):
    cls_model = model.EveIndustryPlanConfigFlow

    @classmethod
    async def select_configflow_by_user_name_and_plan_name(cls, user_name: str, plan_name: str):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name).where(cls.cls_model.plan_name == plan_name)
            result = await session.execute(stmt)
            return result.scalars().first()