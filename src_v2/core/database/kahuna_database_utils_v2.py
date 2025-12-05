from typing import AnyStr, AsyncGenerator
from sqlalchemy import delete, select, text, func, distinct, or_, insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
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
        self._result = None  # 保存 result 引用，防止被垃圾回收
    
    @classmethod
    async def from_stmt(cls, stmt):
        """基于给定的 SQLAlchemy 语句创建会话并返回异步迭代器包装器"""
        if not dbm._session_maker:
            raise RuntimeError("数据库未初始化，请先调用 init() 方法")
        
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

        wrapper = cls(generator(), session)
        wrapper._result = result  # 保存 result 引用
        return wrapper
    
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
            # 先关闭生成器
            try:
                if hasattr(self._generator, 'aclose'):
                    try:
                        await self._generator.aclose()
                    except (StopAsyncIteration, GeneratorExit):
                        pass
                    except Exception as e:
                        logger.warning(f"关闭生成器时出错: {e}")
            except Exception as e:
                logger.warning(f"清理生成器时出错: {e}")
            
            # 确保 session 被正确关闭并返回到连接池
            if self._session:
                try:
                    # 如果 session 还有未提交的事务，先回滚
                    if self._session.in_transaction():
                        try:
                            await self._session.rollback()
                        except Exception as e:
                            logger.warning(f"回滚事务时出错: {e}")
                    # 关闭 session，将连接返回到连接池
                    await self._session.close()
                except Exception as e:
                    logger.warning(f"关闭 session 时出错: {e}")
            
            # 清理引用
            self._session = None
            self._result = None
    
    async def aclose(self):
        """显式关闭（保持向后兼容）"""
        await self._cleanup()
    
    def __del__(self):
        """析构时确保资源被清理（虽然可能已经关闭）"""
        if not self._closed and self._session:
            # 注意：在 __del__ 中不能使用 await，所以这里只是标记
            # 实际清理由 asyncio 的事件循环处理
            # 如果对象被垃圾回收时还未关闭，会在事件循环中产生警告
            # 记录警告以便调试
            import warnings
            warnings.warn(
                f"_AsyncIteratorWrapper 对象被垃圾回收时 session 尚未关闭。"
                f"请确保使用 'async with' 上下文管理器或显式调用 aclose()。",
                ResourceWarning,
                stacklevel=2
            )


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
        :param index_elements: 唯一索引字段列表（字符串列表或 Column 对象列表）
        :return: 结果代理对象
        """
        if not cls.cls_model:
            raise Exception("cls_model 未设置，请勿直接使用基类")
        async with dbm.get_session() as session:
            # 使用 PostgreSQL 的 insert（支持 on_conflict_do_update）
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            
            stmt = pg_insert(cls.cls_model).values(rows_list)

            # 将字符串列表转换为 Column 对象列表（如果需要）
            if index_elements and isinstance(index_elements[0], str):
                index_cols = [getattr(cls.cls_model, col_name) for col_name in index_elements]
                index_col_names = set(index_elements)  # 字符串列表
            else:
                index_cols = index_elements
                index_col_names = {col.name if hasattr(col, 'name') else str(col) for col in index_cols}

            # 构建更新字典，排除索引字段和主键字段
            # 使用 excluded 表别名来引用被插入的值
            update_dict = {}
            for col in cls.cls_model.__table__.columns:
                # 排除索引字段和主键字段
                if col.name not in index_col_names and not col.primary_key:
                    # 使用 excluded 表别名访问列
                    update_dict[col.name] = getattr(stmt.excluded, col.name)

            stmt = stmt.on_conflict_do_update(
                index_elements=index_cols,
                set_=update_dict
            )

            result = await session.execute(stmt)
            await session.commit()
            return result

    @classmethod
    async def insert_many_ignore_conflict(cls, rows_list, index_elements):
        if not cls.cls_model:
            raise Exception("cls_model 未设置，请勿直接使用基类")
        async with dbm.get_session() as session:
            # 使用 PostgreSQL 的 insert（支持 on_conflict_do_nothing）
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            
            stmt = pg_insert(cls.cls_model).values(rows_list)
            
            # 将字符串列表转换为 Column 对象列表（如果需要）
            if index_elements and isinstance(index_elements[0], str):
                index_cols = [getattr(cls.cls_model, col_name) for col_name in index_elements]
            else:
                index_cols = index_elements
            
            stmt = stmt.on_conflict_do_nothing(
                index_elements=index_cols
            )
            await session.execute(stmt)
            await session.commit()

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
    async def merge(cls, obj, session=None):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        if not session:
            async with dbm.get_session() as session:
                await session.merge(obj)
        else:
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

    @classmethod
    async def delete_by_user_name_and_plan_name(cls, user_name: str, plan_name: str, session=None):
        if not session:
            async with dbm.get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name).where(cls.cls_model.plan_name == plan_name)
                await session.execute(stmt)
                await session.commit()
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name).where(cls.cls_model.plan_name == plan_name)
            await session.execute(stmt)

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
                await session.commit()
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

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name).order_by(cls.cls_model.id)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def delete_by_user_name_and_plan_name(cls, user_name: str, plan_name: str, session=None):
        if not session:
            async with dbm.get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name).where(cls.cls_model.plan_name == plan_name)
                await session.execute(stmt)
                await session.commit()
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name).where(cls.cls_model.plan_name == plan_name)
            await session.execute(stmt)

class EveIndustrryPlanConfigFlowPresetDBUtils(_CommonUtils):
    cls_model = model.EveIndustrryPlanConfigFlowPreset

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name).order_by(cls.cls_model.id)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_by_user_name_and_preset_name(cls, user_name: str, preset_name: str):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name).where(cls.cls_model.preset_name == preset_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_by_id(cls, id: int):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.id == id)
            result = await session.execute(stmt)
            return result.scalars().first()

class InvitCodeDBUtils(_CommonUtils):
    cls_model = model.InvitCode

    @classmethod
    async def select_invite_code_by_code(cls, invite_code: str, session=None):
        """根据邀请码查询"""
        if not session:
            async with dbm.get_session() as session:
                stmt = select(cls.cls_model).where(cls.cls_model.invite_code == invite_code)
                result = await session.execute(stmt)
                return result.scalars().first()
        else:
            stmt = select(cls.cls_model).where(cls.cls_model.invite_code == invite_code)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_invite_codes_by_creator(cls, creator_user_name: str):
        """根据创建者查询邀请码列表"""
        stmt = select(cls.cls_model).where(cls.cls_model.creator_user_name == creator_user_name).order_by(cls.cls_model.create_date.desc())
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_all_invite_codes(cls, only_available: bool = False):
        """查询所有邀请码，支持筛选未使用完的"""
        if only_available:
            stmt = select(cls.cls_model).where(
                cls.cls_model.used_count_current < cls.cls_model.used_count_max
            ).order_by(cls.cls_model.create_date.desc())
        else:
            stmt = select(cls.cls_model).order_by(cls.cls_model.create_date.desc())
        return await _AsyncIteratorWrapper.from_stmt(stmt)

class InviteCodeUsedHistoryDBUtils(_CommonUtils):
    cls_model = model.InviteCodeUsedHistory

    @classmethod
    async def select_history_by_invite_code(cls, invite_code: str):
        """根据邀请码查询使用记录"""
        stmt = select(cls.cls_model).where(cls.cls_model.invite_code == invite_code).order_by(cls.cls_model.used_date.desc())
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_history_by_user(cls, used_user_name: str):
        """根据用户查询使用记录"""
        stmt = select(cls.cls_model).where(cls.cls_model.used_user_name == used_user_name).order_by(cls.cls_model.used_date.desc())
        return await _AsyncIteratorWrapper.from_stmt(stmt)

class VipStateDBUtils(_CommonUtils):
    cls_model = model.VipState

    @classmethod
    async def select_vip_state_by_user_name(cls, user_name: str):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_all_vip_states(cls):
        """查询所有VIP状态记录"""
        return await cls.select_all()

    @classmethod
    async def update_vip_state(cls, user_name: str, vip_level: str = None, vip_end_date = None):
        """更新指定用户的VIP状态
        
        :param user_name: 用户名
        :param vip_level: VIP等级（可选）
        :param vip_end_date: VIP到期时间（可选，datetime对象）
        """
        async with dbm.get_session() as session:
            # 先查询现有记录
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            vip_state = result.scalars().first()
            
            if vip_state:
                # 更新现有记录
                if vip_level is not None:
                    vip_state.vip_level = vip_level
                if vip_end_date is not None:
                    vip_state.vip_end_date = vip_end_date
                await session.merge(vip_state)
            else:
                # 创建新记录
                vip_state = cls.cls_model(
                    user_name=user_name,
                    vip_level=vip_level,
                    vip_end_date=vip_end_date
                )
                session.add(vip_state)
            
            await session.commit()
            return vip_state
            

class EveAssetViewDBUtils(_CommonUtils):
    cls_model = model.EveAssetView

    @classmethod
    async def select_by_sid(cls, sid: str):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.sid == sid)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_by_user_name(cls, user_name: str):
        stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
        return await _AsyncIteratorWrapper.from_stmt(stmt)

class EveIndustryCalculateHistoryDBUtils(_CommonUtils):
    cls_model = model.EveIndustryCalculateHistory

    @classmethod
    async def get_hourly_statistics(cls, days: int = 7):
        """获取过去N天每小时的计算统计（启动数、成功数、失败数）
        
        Args:
            days: 查询过去多少天的数据，默认7天
            
        Returns:
            list: 包含每小时统计数据的列表，格式为 [{'hour': '2024-01-01 10:00:00', 'total': 10, 'success': 8, 'failed': 2}, ...]
        """
        async with dbm.get_session() as session:
            # 计算起始时间
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days)
            
            # 查询过去N天的所有记录
            stmt = select(cls.cls_model).where(
                cls.cls_model.calculate_start_time >= start_time
            ).order_by(cls.cls_model.calculate_start_time)
            result = await session.execute(stmt)
            records = result.scalars().all()
            
            # 按小时分组统计
            hourly_stats = {}
            for record in records:
                if not record.calculate_start_time:
                    continue
                    
                # 按小时分组（格式：YYYY-MM-DD HH:00:00）
                hour_key = record.calculate_start_time.replace(minute=0, second=0, microsecond=0)
                hour_str = hour_key.strftime('%Y-%m-%d %H:00:00')
                
                if hour_str not in hourly_stats:
                    hourly_stats[hour_str] = {'total': 0, 'success': 0, 'failed': 0}
                
                hourly_stats[hour_str]['total'] += 1
                
                # 判断成功/失败：通过 calculate_result 字段判断
                # 如果 calculate_result 包含错误信息或为 None，则视为失败
                is_success = True
                if record.calculate_result is None:
                    is_success = False
                elif isinstance(record.calculate_result, dict):
                    # 检查是否有错误相关的键
                    error_keys = ['error', 'exception', 'failed', 'failure']
                    if any(key in str(record.calculate_result).lower() for key in error_keys):
                        is_success = False
                elif isinstance(record.calculate_result, str):
                    if 'error' in record.calculate_result.lower() or 'exception' in record.calculate_result.lower():
                        is_success = False
                
                # 如果 calculate_time 为空，说明计算未完成，视为失败
                if record.calculate_time is None:
                    is_success = False
                
                if is_success:
                    hourly_stats[hour_str]['success'] += 1
                else:
                    hourly_stats[hour_str]['failed'] += 1
            
            # 转换为列表并排序
            result_list = [
                {
                    'hour': hour,
                    'total': stats['total'],
                    'success': stats['success'],
                    'failed': stats['failed']
                }
                for hour, stats in sorted(hourly_stats.items())
            ]
            
            return result_list

    @classmethod
    async def get_duration_statistics_by_product_count(cls):
        """获取基于任务数量的完成时间区间统计（用于K线图）
        
        Returns:
            list: 包含按任务数量分组的统计数据，格式为 [
                {
                    'product_count': 10,
                    'min_duration': 5.2,
                    'max_duration': 15.8,
                    'avg_duration': 10.5,
                    'count': 20
                },
                ...
            ]
        """
        async with dbm.get_session() as session:
            # 查询所有有完整时间信息的记录（需要开始时间和结束时间）
            stmt = select(cls.cls_model).where(
                cls.cls_model.calculate_start_time.isnot(None),
                cls.cls_model.calculate_time.isnot(None),
                cls.cls_model.product_count.isnot(None)
            )
            result = await session.execute(stmt)
            records = result.scalars().all()
            
            # 按任务数量精确分组（每个具体的product_count值作为一个组）
            groups = {}
            for record in records:
                # 确保product_count不为None
                if record.product_count is None:
                    continue
                
                product_count = int(record.product_count)  # 确保是整数
                
                # 计算持续时间（秒）
                if record.calculate_time is None or record.calculate_start_time is None:
                    continue
                    
                duration = (record.calculate_time - record.calculate_start_time).total_seconds()
                
                # 只处理有效的持续时间（大于0）
                if duration < 0:
                    continue
                
                # 使用具体的product_count值作为分组键
                if product_count not in groups:
                    groups[product_count] = []
                
                groups[product_count].append(duration)
            
            # 计算每个组的统计信息
            result_list = []
            for product_count in sorted(groups.keys()):
                durations = groups[product_count]
                if durations and len(durations) > 0:
                    result_list.append({
                        'product_count': product_count,
                        'min_duration': float(min(durations)),
                        'max_duration': float(max(durations)),
                        'avg_duration': float(sum(durations) / len(durations)),
                        'count': len(durations)
                    })
            
            return result_list


class EveMarketRegionHistoryStatisticDBUtils(_CommonUtils):
    """
    EVE 区域市场历史统计表操作工具类

    使用 Postgre 主库中的 `EveMarketRegionHistoryStatistic` 模型，
    提供基于 (type_id, region_id, date) 唯一键的批量插入/更新能力。
    """
    cls_model = model.EveMarketRegionHistoryStatistic

    @classmethod
    async def insert_many_or_update(cls, rows_list: list[dict]):
        """
        基于 (type_id, region_id, date) 作为唯一键进行批量插入或更新。

        :param rows_list: 每一项为一条历史统计记录的字典
        """
        if not rows_list:
            return
        # 复用基类的通用实现，指定唯一索引字段
        return await cls.insert_many_or_update_async(
            rows_list,
            index_elements=["type_id", "region_id", "date"],
        )


class EveMarketRegionOrdersDBUtils(_CommonUtils):
    """
    EVE 区域市场订单表操作工具类

    使用 Postgre 主库中的 `EveMarketRegionOrders` 模型，提供按 region_id
    批量删除和批量插入订单的能力。
    """

    cls_model = model.EveMarketRegionOrders

    @classmethod
    async def delete_by_region_id(cls, region_id: int):
        """
        删除指定 region_id 的所有订单记录。
        """
        async with dbm.get_session() as session:
            stmt = delete(cls.cls_model).where(cls.cls_model.region_id == region_id)
            await session.execute(stmt)

    @classmethod
    async def get_sell_orders_by_type_ids_grouped_by_price(
        cls,
        type_ids: list[int],
        location_id: int,
        region_id: int
    ) -> dict[int, list[list[float, int]]]:
        """
        查询指定类型ID列表的卖单，按价格分组汇总数量。
        
        :param type_ids: 类型ID列表
        :param location_id: 位置ID（如Jita交易中心）
        :param region_id: 区域ID（如Forge区域）
        :return: 格式为 {type_id: [[price, quantity], ...]} 的字典，按price升序排序
        """
        if not type_ids:
            return {}
        
        async with dbm.get_session() as session:
            stmt = select(
                cls.cls_model.type_id,
                cls.cls_model.price,
                func.sum(cls.cls_model.volume_remain).label('total_quantity')
            ).where(
                cls.cls_model.type_id.in_(type_ids),
                cls.cls_model.location_id == location_id,
                cls.cls_model.is_buy_order == False,
                cls.cls_model.region_id == region_id
            ).group_by(
                cls.cls_model.type_id,
                cls.cls_model.price
            ).order_by(
                cls.cls_model.type_id,
                cls.cls_model.price
            )
            
            result = await session.execute(stmt)
            rows = result.all()
            
            # 构建返回格式：{type_id: [[price, quantity], ...]}
            order_data = {}
            for row in rows:
                type_id = row.type_id
                price = float(row.price)
                quantity = int(row.total_quantity)
                
                if type_id not in order_data:
                    order_data[type_id] = []
                
                order_data[type_id].append([price, quantity])
            
            # 每个type_id内的列表按price升序排序（虽然查询已经排序，但确保一下）
            for type_id in order_data:
                order_data[type_id].sort(key=lambda x: x[0])
            
            return order_data