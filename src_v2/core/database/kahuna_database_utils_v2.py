import traceback
import warnings
from datetime import date, datetime, timedelta
from typing import AnyStr, AsyncGenerator, Optional, Type

from sqlalchemy import delete, func, insert, or_, select, text
from sqlalchemy.orm import aliased

from ..log import logger
from . import model
from .connect_manager import get_postgres_manager


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
        if not get_postgres_manager().session_maker:
            raise RuntimeError("数据库未初始化，请先调用 init() 方法")

        session = get_postgres_manager().session_maker()
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
                if hasattr(self._generator, "aclose"):
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

            warnings.warn(
                "_AsyncIteratorWrapper 对象被垃圾回收时 session 尚未关闭。"
                "请确保使用 'async with' 上下文管理器或显式调用 aclose()。",
                ResourceWarning,
                stacklevel=2,
            )


class _CommonUtils:
    cls_model: Optional[Type] = None

    @classmethod
    async def insert_many(cls, rows_list):
        """异步批量插入多条记录

        :param rows_list: 要插入的数据列表，每项是一个字典
        :return: 结果代理对象"""
        if not cls.cls_model:
            raise Exception("cls_model 未设置，请勿直接使用基类")
        async with get_postgres_manager().get_session() as session:
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
        async with get_postgres_manager().get_session() as session:
            # 使用 PostgreSQL 的 insert（支持 on_conflict_do_update）
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(cls.cls_model).values(rows_list)

            # 将字符串列表转换为 Column 对象列表（如果需要）
            if index_elements and isinstance(index_elements[0], str):
                index_cols = [
                    getattr(cls.cls_model, col_name) for col_name in index_elements
                ]
                index_col_names = set(index_elements)  # 字符串列表
            else:
                index_cols = index_elements
                index_col_names = {
                    col.name if hasattr(col, "name") else str(col) for col in index_cols
                }

            # 构建更新字典，排除索引字段和主键字段
            # 使用 excluded 表别名来引用被插入的值
            update_dict = {}
            for col in cls.cls_model.__table__.columns:
                # 排除索引字段和主键字段
                if col.name not in index_col_names and not col.primary_key:
                    # 使用 excluded 表别名访问列
                    update_dict[col.name] = getattr(stmt.excluded, col.name)

            stmt = stmt.on_conflict_do_update(
                index_elements=index_cols, set_=update_dict
            )

            result = await session.execute(stmt)
            await session.commit()
            return result

    @classmethod
    async def insert_many_ignore_conflict(cls, rows_list, index_elements):
        if not cls.cls_model:
            raise Exception("cls_model 未设置，请勿直接使用基类")
        async with get_postgres_manager().get_session() as session:
            # 使用 PostgreSQL 的 insert（支持 on_conflict_do_nothing）
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(cls.cls_model).values(rows_list)

            # 将字符串列表转换为 Column 对象列表（如果需要）
            if index_elements and isinstance(index_elements[0], str):
                index_cols = [
                    getattr(cls.cls_model, col_name) for col_name in index_elements
                ]
            else:
                index_cols = index_elements

            stmt = stmt.on_conflict_do_nothing(index_elements=index_cols)
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
            async with get_postgres_manager().get_session() as session:
                session.add(asset_owner_obj)
        else:
            session.add(asset_owner_obj)

    @classmethod
    async def merge(cls, obj, session=None):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        if not session:
            async with get_postgres_manager().get_session() as session:
                await session.merge(obj)
        else:
            await session.merge(obj)

    @classmethod
    async def delete_all(cls):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        async with get_postgres_manager().get_session() as session:
            stmt = delete(cls.cls_model)
            await session.execute(stmt)

    @classmethod
    async def delete_obj(cls, obj):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        async with get_postgres_manager().get_session() as session:
            # 将对象合并到当前会话
            merged_obj = await session.merge(obj)
            await session.delete(merged_obj)
            await session.commit()


class _CommonCacheUtils:
    cls_model: Optional[Type] = None
    cls_base_model: Optional[Type] = None

    @classmethod
    async def copy_base_to_cache(cls):
        if cls.cls_model == None or cls.cls_base_model == None:
            raise Exception("cls_model or cls_base_model is None")

        async with get_postgres_manager().get_session() as session:
            try:
                # 清空cache表
                await session.execute(delete(cls.cls_model))

                # 将元数据表的数据复制到Cache表
                table_name = cls.cls_base_model.__tablename__
                cache_table_name = cls.cls_model.__tablename__
                await session.execute(
                    text(f"INSERT INTO {cache_table_name} SELECT * FROM {table_name}")
                )

                logger.info(f"从 {table_name} 复制到 {cache_table_name} 完成。")
            except Exception as e:
                print(traceback.format_stack())
                # pyright: ignore[reportUnboundVariable]
                logger.error(f"从 {table_name} 复制到 {cache_table_name} 失败。")
                raise


class UserDBUtils(_CommonUtils):
    cls_model = model.User

    @classmethod
    async def select_user_by_user_name(cls, user_name: AnyStr):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def delete_user_by_user_username(cls, user_name: AnyStr, session=None):
        if not session:
            async with get_postgres_manager().get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
            await session.execute(stmt)

    @classmethod
    async def select_passwd_hash_by_user_name(cls, user_name: AnyStr):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model.password_hash).where(
                cls.cls_model.user_name == user_name
            )
            result = await session.execute(stmt)
            return result.scalars().first()


class UserDataDBUtils(_CommonUtils):
    cls_model = model.UserData

    @classmethod
    async def select_user_data_by_user_name(cls, user_name: AnyStr):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def delete_user_data_by_user_name(cls, user_name: AnyStr, session=None):
        if not session:
            async with get_postgres_manager().get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
            await session.execute(stmt)

    @classmethod
    async def update_user_setting(cls, user_name: str, setting_key: str, setting_value):
        """更新用户设置中的指定键值

        Args:
            user_name: 用户名
            setting_key: 设置键名
            setting_value: 设置值
        """
        async with get_postgres_manager().get_session() as session:
            user_data = await cls.select_user_data_by_user_name(user_name)
            if not user_data:
                raise ValueError(f"用户 {user_name} 不存在")

            # 如果setting为None，初始化为空字典
            if user_data.setting is None:
                user_data.setting = {}

            # 更新设置
            if not isinstance(user_data.setting, dict):
                user_data.setting = {}

            user_data.setting[setting_key] = setting_value
            await session.merge(user_data)
            await session.commit()
            return user_data

    @classmethod
    async def get_user_setting(
        cls, user_name: str, setting_key: str, default_value=None
    ):
        """获取用户设置中的指定键值

        Args:
            user_name: 用户名
            setting_key: 设置键名
            default_value: 默认值（如果不存在）

        Returns:
            设置值或默认值
        """
        user_data = await cls.select_user_data_by_user_name(user_name)
        if not user_data or not user_data.setting:
            return default_value

        if not isinstance(user_data.setting, dict):
            return default_value

        return user_data.setting.get(setting_key, default_value)


class UserQQBindingDBUtils(_CommonUtils):
    cls_model = model.UserQQBinding

    @classmethod
    async def select_by_user_name(cls, user_name: AnyStr):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_by_user_qq(cls, user_qq: int):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_qq == user_qq)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def delete_by_user_name(cls, user_name: AnyStr, session=None):
        if not session:
            async with get_postgres_manager().get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
            await session.execute(stmt)

    @classmethod
    async def delete_by_user_qq(cls, user_qq: int, session=None):
        if not session:
            async with get_postgres_manager().get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.user_qq == user_qq)
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.user_qq == user_qq)
            await session.execute(stmt)

    @classmethod
    async def bind_user_qq(cls, user_name: str, user_qq: int):
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        bind_time = datetime.utcnow()
        async with get_postgres_manager().get_session() as session:
            await session.execute(
                delete(cls.cls_model).where(cls.cls_model.user_qq == user_qq)
            )
            stmt = pg_insert(cls.cls_model).values(
                user_name=user_name, user_qq=user_qq, bind_time=bind_time
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[cls.cls_model.user_name],
                set_={"user_qq": user_qq, "bind_time": bind_time},
            )
            await session.execute(stmt)
            await session.commit()

            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()


class RolesDBUtils(_CommonUtils):
    cls_model = model.Roles

    @classmethod
    async def select_role_by_role_name(cls, role_name: str) -> model.Roles | None:
        async with get_postgres_manager().get_session() as session:
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
            async with get_postgres_manager().get_session() as session:
                stmt = delete(cls.cls_model).where(
                    cls.cls_model.role_name.in_(role_names)
                )
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.role_name.in_(role_names))
            await session.execute(stmt)


class PermissionsDBUtils(_CommonUtils):
    cls_model = model.Permissions

    @classmethod
    async def select_permission_by_permission_name(cls, permission_name: str):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.permission_name == permission_name
            )
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
            async with get_postgres_manager().get_session() as session:
                stmt = delete(cls.cls_model).where(
                    cls.cls_model.role_name.in_(role_names)
                )
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.role_name.in_(role_names))
            await session.execute(stmt)

    @classmethod
    async def select_user_role_by_user_name_and_role_name(
        cls, user_name: str, role_name: str
    ):
        """查询用户角色关联"""
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                (cls.cls_model.user_name == user_name)
                & (cls.cls_model.role_name == role_name)
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
        async with get_postgres_manager().get_session() as session:
            stmt = delete(cls.cls_model).where(
                cls.cls_model.permission_name == permission_name
            )
            await session.execute(stmt)

    @classmethod
    async def select_role_permissions_by_permission_name(cls, permission_name: str):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.permission_name == permission_name
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def delete_role_permissions_by_role_names(
        cls, role_names: list[str], session=None
    ):
        """批量删除角色权限关联

        Args:
            role_names: 要删除的角色名称列表
            session: 可选的数据库会话，如果提供则使用该会话，否则创建新会话
        """
        if not role_names:
            return
        if not session:
            async with get_postgres_manager().get_session() as session:
                stmt = delete(cls.cls_model).where(
                    cls.cls_model.role_name.in_(role_names)
                )
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.role_name.in_(role_names))
            await session.execute(stmt)

    @classmethod
    async def select_role_permission_by_role_name_and_permission_name(
        cls, role_name: str, permission_name: str
    ):
        """查询角色权限关联"""
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                (cls.cls_model.role_name == role_name)
                & (cls.cls_model.permission_name == permission_name)
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
        stmt = select(cls.cls_model).where(
            cls.cls_model.parent_role_name == parent_role_name
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_all_by_child_role_name(cls, child_role_name: str):
        """查询所有以指定角色作为子角色的关系"""
        stmt = select(cls.cls_model).where(
            cls.cls_model.child_role_name == child_role_name
        )
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
    async def delete_hierarchy_by_role_names(
        cls, hierarchy_pairs: list[list[str]], session=None
    ):
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
                raise ValueError(
                    f"Invalid hierarchy pair: {pair}. Expected [parent_name, child_name]"
                )
            parent_name, child_name = pair
            conditions.append(
                (cls.cls_model.parent_role_name == parent_name)
                & (cls.cls_model.child_role_name == child_name)
            )

        if not conditions:
            return

        if not session:
            async with get_postgres_manager().get_session() as session:
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
        async with get_postgres_manager().get_session() as session:
            stmt = delete(cls.cls_model).where(
                cls.cls_model.permission_name == permission_name
            )
            await session.execute(stmt)

    @classmethod
    async def select_user_permissions_by_permission_name(cls, permission_name: str):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.permission_name == permission_name
            )
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
        async with get_postgres_manager().get_session() as session:
            stmt = delete(cls.cls_model).where(
                cls.cls_model.character_id == character_id
            )
            await session.execute(stmt)

    @classmethod
    async def select_character_by_character_name(cls, character_name: str):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.character_name == character_name
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_character_by_character_id(cls, character_id: int):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.character_id == character_id
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_all_characters_by_corporation_id(cls, corporation_id: int):
        """根据公司ID返回所有角色的异步迭代器"""
        stmt = select(cls.cls_model).where(
            cls.cls_model.corporation_id == corporation_id
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)


class EvePublicCharacterInfoDBUtils(_CommonUtils):
    cls_model = model.EvePublicCharacterInfo

    @classmethod
    async def select_public_character_info_by_character_id(cls, character_id: int):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.character_id == character_id
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_public_character_info_by_name(cls, character_name: str):
        """根据角色名称查询角色信息"""
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.name == character_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_character_info_by_characterid_with_same_title(
        cls, character_id: int
    ):
        """根据角色ID返回相同标题的角色信息的异步迭代器"""
        # 创建别名用于自连接
        alias = aliased(cls.cls_model)
        # 自连接：通过标题匹配，找到与给定character_id具有相同标题的所有角色
        stmt = (
            select(cls.cls_model)
            .join(alias, cls.cls_model.title == alias.title)
            .where(alias.character_id == character_id)
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)


class EveCorporationDBUtils(_CommonUtils):
    cls_model = model.EveCorporation

    @classmethod
    async def select_corporation_by_corporation_id(
        cls, corporation_id: int
    ) -> cls_model:
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.corporation_id == corporation_id
            )
            result = await session.execute(stmt)
            return result.scalars().first()


class EveAliasCharacterDBUtils(_CommonUtils):
    cls_model = model.EveAliasCharacter

    @classmethod
    async def select_alias_character_by_character_id(cls, character_id: int):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.alias_character_id == character_id
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_all_by_main_character_id(cls, main_character_id: int):
        stmt = select(cls.cls_model).where(
            cls.cls_model.main_character_id == main_character_id
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)


class EveAssetPullMissionDBUtils(_CommonUtils):
    cls_model = model.EveAssetPullMission

    @classmethod
    async def select_mission_by_owner_id_and_owner_type(
        cls, asset_owner_id: int, asset_owner_type: str
    ):
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.asset_owner_id == asset_owner_id)
                .where(cls.cls_model.asset_owner_type == asset_owner_type)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_mission_by_owner_id(cls, asset_owner_id: int):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.asset_owner_id == asset_owner_id
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_all_by_owner_id_and_owner_type(
        cls, asset_owner_id: int, asset_owner_type: str
    ):
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.asset_owner_id == asset_owner_id)
            .where(cls.cls_model.asset_owner_type == asset_owner_type)
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.user_name == user_name)
            .order_by(cls.cls_model.id)
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)


class EveIndustryPlanDBUtils(_CommonUtils):
    cls_model = model.EveIndustryPlan

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.user_name == user_name)
            .order_by(cls.cls_model.id)
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_by_user_name_and_plan_name(cls, user_name: str, plan_name: str):
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.plan_name == plan_name)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def delete_by_user_name_and_plan_name(
        cls, user_name: str, plan_name: str, session=None
    ):
        if not session:
            async with get_postgres_manager().get_session() as session:
                stmt = (
                    delete(cls.cls_model)
                    .where(cls.cls_model.user_name == user_name)
                    .where(cls.cls_model.plan_name == plan_name)
                )
                await session.execute(stmt)
                await session.commit()
        else:
            stmt = (
                delete(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.plan_name == plan_name)
            )
            await session.execute(stmt)

    # ===== 分享功能相关方法 =====

    @classmethod
    async def select_by_share_token(cls, share_token: str):
        """根据分享token获取计划

        Args:
            share_token: 分享令牌

        Returns:
            计划对象，如果不存在则返回 None
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.share_token == share_token)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def update_share_info(
        cls, user_name: str, plan_name: str, share_data: dict, session=None
    ):
        """更新计划分享信息

        Args:
            user_name: 用户名
            plan_name: 计划名称
            share_data: 分享数据字典，可包含 public, share_token, filter_snapshot
            session: 可选的数据库会话
        """

        async def _update(session):
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.plan_name == plan_name)
            )
            result = await session.execute(stmt)
            plan = result.scalars().first()

            if plan:
                # 更新分享相关字段
                if "public" in share_data:
                    plan.public = share_data["public"]
                if "share_token" in share_data:
                    plan.share_token = share_data["share_token"]
                if "filter_snapshot" in share_data:
                    plan.filter_snapshot = share_data["filter_snapshot"]

                await session.commit()
                return plan
            return None

        if not session:
            async with get_postgres_manager().get_session() as session:
                return await _update(session)
        else:
            return await _update(session)


class EveIndustryPlanProductDBUtils(_CommonUtils):
    cls_model = model.EveIndustryPlanProduct

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.user_name == user_name)
            .order_by(cls.cls_model.id)
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_all_by_user_name_and_plan_name(
        cls, user_name: str, plan_name: str
    ):
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.user_name == user_name)
            .where(cls.cls_model.plan_name == plan_name)
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def delete_all_by_user_name_and_plan_name(
        cls, user_name: str, plan_name: str, session=None
    ):
        if not session:
            async with get_postgres_manager().get_session() as session:
                stmt = (
                    delete(cls.cls_model)
                    .where(cls.cls_model.user_name == user_name)
                    .where(cls.cls_model.plan_name == plan_name)
                )
                await session.execute(stmt)
                await session.commit()
        else:
            stmt = (
                delete(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.plan_name == plan_name)
            )
            await session.execute(stmt)


class EveIndustryPlanProductJSONBDBUtils(_CommonUtils):
    cls_model = model.EveIndustryPlanProductJSONB

    @classmethod
    async def select_by_user_name_and_plan_name(cls, user_name: str, plan_name: str):
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.plan_name == plan_name)
            )
            result = await session.execute(stmt)
            return result.scalars().first()


class EveIndustryAssetContainerPermissionDBUtils(_CommonUtils):
    cls_model = model.EveIndustryAssetContainerPermission

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.user_name == user_name)
            .order_by(cls.cls_model.id)
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_by_container_id_and_owner_id(
        cls, container_id: int, owner_id: int
    ):
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.asset_container_id == container_id)
                .where(cls.cls_model.asset_owner_id == owner_id)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_by_container_id_owner_id_and_user_name(
        cls, container_id: int, owner_id: int, user_name: str
    ):
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.asset_container_id == container_id)
                .where(cls.cls_model.asset_owner_id == owner_id)
                .where(cls.cls_model.user_name == user_name)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_by_container_id_owner_id_user_name_location_flag(
        cls, container_id: int, owner_id: int, user_name: str, location_flag: str
    ):
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.asset_container_id == container_id)
                .where(cls.cls_model.asset_owner_id == owner_id)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.location_flag == location_flag)
            )
            result = await session.execute(stmt)
            return result.scalars().first()


class EveIndustryPlanConfigFlowConfigDBUtils(_CommonUtils):
    cls_model = model.EveIndustryPlanConfigFlowConfig

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.user_name == user_name)
            .order_by(cls.cls_model.id)
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_by_id(cls, id: int, pdm=None):
        if pdm:
            m = pdm
        else:
            m = get_postgres_manager()
        async with m.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.id == id)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_by_user_name_and_config_type_and_config_value(
        cls, user_name: str, config_type: str, config_value: dict
    ):
        """查询是否存在相同的配置

        Args:
            user_name: 用户名
            config_type: 配置类型
            config_value: 配置值（字典）

        Returns:
            如果存在则返回配置对象，否则返回 None
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.user_name == user_name,
                cls.cls_model.config_type == config_type,
                cls.cls_model.config_value == config_value,
            )
            result = await session.execute(stmt)
            return result.scalars().first()


class EveIndustryPlanConfigFlowDBUtils(_CommonUtils):
    cls_model = model.EveIndustryPlanConfigFlow

    @classmethod
    async def select_configflow_by_user_name_and_plan_name(
        cls, user_name: str, plan_name: str, pdm=None
    ):
        if pdm:
            m = pdm
        else:
            m = get_postgres_manager()
        async with m.get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.plan_name == plan_name)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.user_name == user_name)
            .order_by(cls.cls_model.id)
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def delete_by_user_name_and_plan_name(
        cls, user_name: str, plan_name: str, session=None
    ):
        if not session:
            async with get_postgres_manager().get_session() as session:
                stmt = (
                    delete(cls.cls_model)
                    .where(cls.cls_model.user_name == user_name)
                    .where(cls.cls_model.plan_name == plan_name)
                )
                await session.execute(stmt)
                await session.commit()
        else:
            stmt = (
                delete(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.plan_name == plan_name)
            )
            await session.execute(stmt)


class EveIndustrryPlanConfigFlowPresetDBUtils(_CommonUtils):
    cls_model = model.EveIndustrryPlanConfigFlowPreset

    @classmethod
    async def select_all_by_user_name(cls, user_name: str):
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.user_name == user_name)
            .order_by(cls.cls_model.id)
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_by_user_name_and_preset_name(
        cls, user_name: str, preset_name: str
    ):
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.preset_name == preset_name)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_by_id(cls, id: int):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.id == id)
            result = await session.execute(stmt)
            return result.scalars().first()


class InvitCodeDBUtils(_CommonUtils):
    cls_model = model.InvitCode

    @classmethod
    async def select_invite_code_by_code(cls, invite_code: str, session=None):
        """根据邀请码查询"""
        if not session:
            async with get_postgres_manager().get_session() as session:
                stmt = select(cls.cls_model).where(
                    cls.cls_model.invite_code == invite_code
                )
                result = await session.execute(stmt)
                return result.scalars().first()
        else:
            stmt = select(cls.cls_model).where(cls.cls_model.invite_code == invite_code)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_invite_codes_by_creator(cls, creator_user_name: str):
        """根据创建者查询邀请码列表"""
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.creator_user_name == creator_user_name)
            .order_by(cls.cls_model.create_date.desc())
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_all_invite_codes(cls, only_available: bool = False):
        """查询所有邀请码，支持筛选未使用完的"""
        if only_available:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.used_count_current < cls.cls_model.used_count_max)
                .order_by(cls.cls_model.create_date.desc())
            )
        else:
            stmt = select(cls.cls_model).order_by(cls.cls_model.create_date.desc())
        return await _AsyncIteratorWrapper.from_stmt(stmt)


class InviteCodeUsedHistoryDBUtils(_CommonUtils):
    cls_model = model.InviteCodeUsedHistory

    @classmethod
    async def select_history_by_invite_code(cls, invite_code: str):
        """根据邀请码查询使用记录"""
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.invite_code == invite_code)
            .order_by(cls.cls_model.used_date.desc())
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def select_history_by_user(cls, used_user_name: str):
        """根据用户查询使用记录"""
        stmt = (
            select(cls.cls_model)
            .where(cls.cls_model.used_user_name == used_user_name)
            .order_by(cls.cls_model.used_date.desc())
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)


class VipStateDBUtils(_CommonUtils):
    cls_model = model.VipState

    @classmethod
    async def select_vip_state_by_user_name(cls, user_name: str):
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_all_vip_states(cls):
        """查询所有VIP状态记录"""
        return await cls.select_all()

    @classmethod
    async def update_vip_state(
        cls, user_name: str, vip_level: str = None, vip_end_date=None
    ):
        """更新指定用户的VIP状态

        :param user_name: 用户名
        :param vip_level: VIP等级（可选）
        :param vip_end_date: VIP到期时间（可选，datetime对象）
        """
        async with get_postgres_manager().get_session() as session:
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
                    user_name=user_name, vip_level=vip_level, vip_end_date=vip_end_date
                )
                session.add(vip_state)

            await session.commit()
            return vip_state


class EveAssetViewDBUtils(_CommonUtils):
    cls_model = model.EveAssetView

    @classmethod
    async def select_by_sid(cls, sid: str):
        async with get_postgres_manager().get_session() as session:
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
        async with get_postgres_manager().get_session() as session:
            # 计算起始时间
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days)

            # 查询过去N天的所有记录
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.calculate_start_time >= start_time)
                .order_by(cls.cls_model.calculate_start_time)
            )
            result = await session.execute(stmt)
            records = result.scalars().all()

            # 按小时分组统计
            hourly_stats = {}
            for record in records:
                if not record.calculate_start_time:
                    continue

                # 按小时分组（格式：YYYY-MM-DD HH:00:00）
                hour_key = record.calculate_start_time.replace(
                    minute=0, second=0, microsecond=0
                )
                hour_str = hour_key.strftime("%Y-%m-%d %H:00:00")

                if hour_str not in hourly_stats:
                    hourly_stats[hour_str] = {"total": 0, "success": 0, "failed": 0}

                hourly_stats[hour_str]["total"] += 1

                # 判断成功/失败：通过 calculate_result 字段判断
                # 如果 calculate_result 包含错误信息或为 None，则视为失败
                is_success = True
                if record.calculate_result is None:
                    is_success = False
                elif isinstance(record.calculate_result, dict):
                    # 检查是否有错误相关的键
                    error_keys = ["error", "exception", "failed", "failure"]
                    if any(
                        key in str(record.calculate_result).lower()
                        for key in error_keys
                    ):
                        is_success = False
                elif isinstance(record.calculate_result, str):
                    if (
                        "error" in record.calculate_result.lower()
                        or "exception" in record.calculate_result.lower()
                    ):
                        is_success = False

                # 如果 calculate_time 为空，说明计算未完成，视为失败
                if record.calculate_time is None:
                    is_success = False

                if is_success:
                    hourly_stats[hour_str]["success"] += 1
                else:
                    hourly_stats[hour_str]["failed"] += 1

            # 转换为列表并排序
            result_list = [
                {
                    "hour": hour,
                    "total": stats["total"],
                    "success": stats["success"],
                    "failed": stats["failed"],
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
        async with get_postgres_manager().get_session() as session:
            # 查询所有有完整时间信息的记录（需要开始时间和结束时间）
            stmt = select(cls.cls_model).where(
                cls.cls_model.calculate_start_time.isnot(None),
                cls.cls_model.calculate_time.isnot(None),
                cls.cls_model.product_count.isnot(None),
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

                duration = (
                    record.calculate_time - record.calculate_start_time
                ).total_seconds()

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
                    result_list.append(
                        {
                            "product_count": product_count,
                            "min_duration": float(min(durations)),
                            "max_duration": float(max(durations)),
                            "avg_duration": float(sum(durations) / len(durations)),
                            "count": len(durations),
                        }
                    )

            return result_list

    @classmethod
    async def get_user_frequency_statistics(cls, days: int = 30, limit: int = 100):
        """获取用户使用频率统计（高频用户排行）

        Args:
            days: 查询过去多少天的数据，默认30天
            limit: 返回的用户数量上限，默认100

        Returns:
            list: 用户频率统计列表，按使用次数降序排列
                格式为 [{'user_name': 'user1', 'total_count': 50, 'success_count': 45, 'failed_count': 5}, ...]
        """
        async with get_postgres_manager().get_session() as session:
            # 计算起始时间
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days)

            # 查询过去N天的所有记录
            stmt = select(cls.cls_model).where(
                cls.cls_model.calculate_start_time >= start_time
            )
            result = await session.execute(stmt)
            records = result.scalars().all()

            # 按用户分组统计
            user_stats = {}
            for record in records:
                if not record.user_name:
                    continue

                user_name = record.user_name
                if user_name not in user_stats:
                    user_stats[user_name] = {
                        "user_name": user_name,
                        "total_count": 0,
                        "success_count": 0,
                        "failed_count": 0,
                    }

                user_stats[user_name]["total_count"] += 1

                # 判断成功/失败
                is_success = True
                if record.calculate_result is None:
                    is_success = False
                elif isinstance(record.calculate_result, dict):
                    error_keys = ["error", "exception", "failed", "failure"]
                    if any(
                        key in str(record.calculate_result).lower()
                        for key in error_keys
                    ):
                        is_success = False
                elif isinstance(record.calculate_result, str):
                    if (
                        "error" in record.calculate_result.lower()
                        or "exception" in record.calculate_result.lower()
                    ):
                        is_success = False

                if record.calculate_time is None:
                    is_success = False

                if is_success:
                    user_stats[user_name]["success_count"] += 1
                else:
                    user_stats[user_name]["failed_count"] += 1

            # 转换为列表并按使用次数降序排列
            result_list = list(user_stats.values())
            result_list.sort(key=lambda x: x["total_count"], reverse=True)

            # 限制返回数量
            return result_list[:limit]

    @classmethod
    async def get_user_calculate_history_by_date_range(
        cls, user_name: str, start_date: datetime, end_date: datetime
    ):
        """获取特定用户在特定时间范围的计算历史

        Args:
            user_name: 用户名
            start_date: 起始时间
            end_date: 结束时间

        Returns:
            list: 计算历史记录列表
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(
                    cls.cls_model.user_name == user_name,
                    cls.cls_model.calculate_start_time >= start_date,
                    cls.cls_model.calculate_start_time <= end_date,
                )
                .order_by(cls.cls_model.calculate_start_time.desc())
            )
            result = await session.execute(stmt)
            records = result.scalars().all()

            # 转换为字典列表
            result_list = []
            for record in records:
                # 判断成功/失败
                is_success = True
                if record.calculate_result is None:
                    is_success = False
                elif isinstance(record.calculate_result, dict):
                    error_keys = ["error", "exception", "failed", "failure"]
                    if any(
                        key in str(record.calculate_result).lower()
                        for key in error_keys
                    ):
                        is_success = False
                elif isinstance(record.calculate_result, str):
                    if (
                        "error" in record.calculate_result.lower()
                        or "exception" in record.calculate_result.lower()
                    ):
                        is_success = False

                if record.calculate_time is None:
                    is_success = False

                result_list.append(
                    {
                        "id": record.id,
                        "user_name": record.user_name,
                        "plan_name": record.plan_name,
                        "product_count": record.product_count,
                        "calculate_start_time": record.calculate_start_time.isoformat()
                        if record.calculate_start_time
                        else None,
                        "calculate_time": record.calculate_time.isoformat()
                        if record.calculate_time
                        else None,
                        "is_success": is_success,
                    }
                )

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

    @classmethod
    async def get_records_by_date_range(
        cls,
        type_id: int,
        region_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> list:
        """
        查询指定 type_id、region_id 在指定日期范围内的历史统计数据。

        :param type_id: 物品类型ID
        :param region_id: 区域ID
        :param start_date: 起始日期（包含）
        :param end_date: 结束日期（不包含）
        :return: 查询结果记录列表
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.type_id == type_id,
                cls.cls_model.region_id == region_id,
                cls.cls_model.date >= start_date,
                cls.cls_model.date < end_date,
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    @classmethod
    async def get_latest_record(
        cls,
        type_id: int,
        region_id: int,
    ):
        """
        获取指定 type_id、region_id 的最新历史统计记录。

        :param type_id: 物品类型ID
        :param region_id: 区域ID
        :return: 最新记录，如果没有则返回 None
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(
                    cls.cls_model.type_id == type_id,
                    cls.cls_model.region_id == region_id,
                )
                .order_by(cls.cls_model.date.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()


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
        async with get_postgres_manager().get_session() as session:
            stmt = delete(cls.cls_model).where(cls.cls_model.region_id == region_id)
            await session.execute(stmt)

    @classmethod
    async def get_sell_orders_by_type_ids_grouped_by_price(
        cls, type_ids: list[int], location_id: int, region_id: int
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

        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(
                    cls.cls_model.type_id,
                    cls.cls_model.price,
                    func.sum(cls.cls_model.volume_remain).label("total_quantity"),
                )
                .where(
                    cls.cls_model.type_id.in_(type_ids),
                    cls.cls_model.location_id == location_id,
                    cls.cls_model.is_buy_order == False,
                    cls.cls_model.region_id == region_id,
                )
                .group_by(cls.cls_model.type_id, cls.cls_model.price)
                .order_by(cls.cls_model.type_id, cls.cls_model.price)
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

    @classmethod
    async def save_orders_via_temp_table(
        cls, region_id: int, orders_generator, total_count: int, progress_callback=None
    ):
        """
        使用临时表方案保存订单数据，避免多次append操作。

        :param region_id: 区域ID
        :param orders_generator: 订单数据生成器，每次yield一个批次的数据列表
        :param total_count: 总订单数量，用于进度跟踪
        :param progress_callback: 进度回调函数，接收已处理数量作为参数
        """
        import uuid

        temp_table_name = f"eve_market_region_orders_tmp_{uuid.uuid4().hex[:8]}"

        try:
            async with get_postgres_manager().engine.begin() as conn:
                # 1. 创建临时表（使用相同的结构，但不包含id字段，因为原表的id是自增的）
                columns_def = []
                for col in cls.cls_model.__table__.columns:
                    # 跳过id字段，因为原表的id是自增的
                    if col.name == "id":
                        continue
                    col_def = f'"{col.name}" {cls._get_postgresql_type(col.type)}'
                    # 保留NOT NULL约束（除了created_at/updated_at）
                    if not col.nullable and col.name not in (
                        "created_at",
                        "updated_at",
                    ):
                        col_def += " NOT NULL"
                    columns_def.append(col_def)

                create_sql = text(f'''
                    CREATE TEMP TABLE "{temp_table_name}" (
                        {", ".join(columns_def)}
                    )
                ''')
                await conn.execute(create_sql)

                # 2. 分批插入数据到临时表
                batch_size = 2000
                processed_count = 0

                # 构建列名列表（排除id，因为临时表不需要自增id）
                column_names = [
                    col.name
                    for col in cls.cls_model.__table__.columns
                    if col.name != "id"
                ]
                cols_csv = ", ".join([f'"{c}"' for c in column_names])

                async def _insert_batch(batch: list):
                    if not batch:
                        return

                    # 构建批量插入语句，使用 VALUES 子句
                    # 格式: INSERT INTO table (col1, col2) VALUES (val1, val2), (val3, val4), ...
                    values_parts = []
                    params = {}
                    param_index = 0

                    for row in batch:
                        row_values = []
                        for col in column_names:
                            param_name = f"p{param_index}"
                            params[param_name] = row.get(col)
                            row_values.append(f":{param_name}")
                            param_index += 1
                        values_parts.append(f"({', '.join(row_values)})")

                    values_clause = ", ".join(values_parts)
                    insert_sql = text(f'''
                        INSERT INTO "{temp_table_name}" ({cols_csv})
                        VALUES {values_clause}
                    ''')
                    await conn.execute(insert_sql, params)

                batch = []
                for row in orders_generator:
                    batch.append(row)
                    if len(batch) >= batch_size:
                        await _insert_batch(batch)
                        if progress_callback:
                            await progress_callback(len(batch))
                        batch = []

                # 插入剩余数据
                if batch:
                    await _insert_batch(batch)
                    if progress_callback:
                        await progress_callback(len(batch))

                # 3. 删除原表中该region的数据
                delete_sql = text(f"""
                    DELETE FROM {cls.cls_model.__tablename__}
                    WHERE region_id = :region_id
                """)
                await conn.execute(delete_sql, {"region_id": region_id})

                # 4. 将临时表数据复制到原表
                column_names = [
                    col.name
                    for col in cls.cls_model.__table__.columns
                    if col.name != "id"
                ]
                cols_csv = ", ".join([f'"{c}"' for c in column_names])
                copy_sql = text(f'''
                    INSERT INTO {cls.cls_model.__tablename__} ({cols_csv})
                    SELECT {cols_csv} FROM "{temp_table_name}"
                ''')
                await conn.execute(copy_sql)

                # 5. 临时表会在连接关闭时自动删除（因为是TEMP TABLE）

        except Exception as e:
            logger.error(
                f"使用临时表保存订单数据失败 region_id={region_id}: {e}",
                exc_info=True,
            )
            raise

    @staticmethod
    def _get_postgresql_type(sqlalchemy_type):
        """将SQLAlchemy类型转换为PostgreSQL类型字符串"""
        from sqlalchemy.dialects import postgresql

        # 尝试使用 SQLAlchemy 的类型编译功能（最可靠的方法）
        try:
            # 使用 PostgreSQL 方言编译类型
            dialect = postgresql.dialect()
            compiled = sqlalchemy_type.compile(dialect=dialect)
            return str(compiled)
        except Exception:
            # 如果编译失败，使用简单的类型映射
            pass

        # 简单的类型映射作为后备方案
        type_mapping = {
            "Integer": "INTEGER",
            "BigInteger": "BIGINT",
            "Text": "TEXT",
            "String": "TEXT",
            "DateTime": "TIMESTAMP",
            "Date": "DATE",
            "Time": "TIME",
            "Float": "DOUBLE PRECISION",
            "Numeric": "NUMERIC",
            "Boolean": "BOOLEAN",
            "LargeBinary": "BYTEA",
        }

        # 尝试通过类型名称匹配
        type_name = type(sqlalchemy_type).__name__
        if type_name in type_mapping:
            return type_mapping[type_name]

        # 默认返回TEXT
        return "TEXT"


class EnterpriseMarketDBUtils(_CommonUtils):
    """企业市场数据库工具类"""

    cls_model = model.EnterpriseMarket

    @classmethod
    async def select_market_id_tag_list_by_user_name(cls, user_name: str):
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model.id, cls.cls_model.tag)
                .where(cls.cls_model.user_name == user_name)
                .order_by(cls.cls_model.created_at.desc())
            )
            result = await session.execute(stmt)
            return result.all()

    @classmethod
    async def select_by_user_name_and_market_id(cls, user_name: str, market_id: int):
        """
        根据用户与市场ID获取市场记录

        Args:
            user_name: 用户名
            market_id: 市场ID
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.user_name == user_name, cls.cls_model.id == market_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @classmethod
    async def collect_all_product_type_ids(cls) -> list[int]:
        """
        从数据库查询所有 EnterpriseMarket 记录，收集并合并去重 product_type_ids

        Returns:
            list[int]: 去重后的 product_type_ids 列表
        """
        from typing import Set

        type_id_set: Set[int] = set()

        try:
            async with get_postgres_manager().get_session() as session:
                stmt = select(cls.cls_model)
                result = await session.execute(stmt)

                for market in result.scalars():
                    if market.product_type_ids:
                        # product_type_ids 是 ARRAY(Integer)，可能是列表
                        for type_id in market.product_type_ids:
                            if type_id is not None:
                                type_id_set.add(type_id)

            type_id_list = sorted(list(type_id_set))
            logger.info(
                f"从自选市场收集到 {len(type_id_list)} 个唯一的 product_type_id"
            )
            return type_id_list

        except Exception as e:
            logger.error(f"收集 product_type_ids 失败: {e}", exc_info=True)
            return []


class EveOverviewHistoryDBUtils(_CommonUtils):
    """Overview历史数据数据库工具类"""

    cls_model = model.EveOverviewHistory

    @classmethod
    async def save_overview_data(cls, user_name: str, date: date, data: dict):
        """保存或更新指定日期的overview数据

        Args:
            user_name: 用户名
            date: 日期（Date类型，仅年月日）
            data: overview数据（字典）

        Returns:
            保存的历史记录对象
        """
        async with get_postgres_manager().get_session() as session:
            # 使用 PostgreSQL 的 insert（支持 on_conflict_do_update）实现真正的 upsert
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            # 构建插入语句
            stmt = pg_insert(cls.cls_model).values(
                user_name=user_name, date=date, data=data
            )

            # 基于唯一约束 (user_name, date) 进行冲突处理
            # 如果冲突则更新 data 字段
            index_cols = [cls.cls_model.user_name, cls.cls_model.date]
            stmt = stmt.on_conflict_do_update(
                index_elements=index_cols, set_={"data": stmt.excluded.data}
            )

            await session.execute(stmt)
            await session.commit()

            # 重新查询返回
            stmt = select(cls.cls_model).where(
                cls.cls_model.user_name == user_name, cls.cls_model.date == date
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def get_overview_data_by_date(cls, user_name: str, date: date):
        """获取指定日期的overview数据

        Args:
            user_name: 用户名
            date: 日期（Date类型）

        Returns:
            历史记录对象或None
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.user_name == user_name, cls.cls_model.date == date
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def get_overview_data_by_date_range(
        cls, user_name: str, start_date: date, end_date: date
    ):
        """获取指定日期范围内的overview数据

        Args:
            user_name: 用户名
            start_date: 开始日期（Date类型）
            end_date: 结束日期（Date类型）

        Returns:
            历史记录列表，按日期升序排列
        """
        stmt = (
            select(cls.cls_model)
            .where(
                cls.cls_model.user_name == user_name,
                cls.cls_model.date >= start_date,
                cls.cls_model.date <= end_date,
            )
            .order_by(cls.cls_model.date.asc())
        )
        return await _AsyncIteratorWrapper.from_stmt(stmt)

    @classmethod
    async def check_date_exists(cls, user_name: str, date: date) -> bool:
        """检查指定日期是否已有数据

        Args:
            user_name: 用户名
            date: 日期（Date类型）

        Returns:
            True如果存在，False如果不存在
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(func.count(cls.cls_model.id)).where(
                cls.cls_model.user_name == user_name, cls.cls_model.date == date
            )
            result = await session.execute(stmt)
            count = result.scalar()
            return count > 0 if count else False

    @classmethod
    async def get_latest_overview_data_excluding_today(
        cls, user_name: str, exclude_date: date
    ):
        """获取除指定日期外的最近一次overview历史记录

        Args:
            user_name: 用户名
            exclude_date: 要排除的日期（通常是今天）

        Returns:
            历史记录对象或None（如果没有找到）
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(
                    cls.cls_model.user_name == user_name,
                    cls.cls_model.date < exclude_date,
                )
                .order_by(cls.cls_model.date.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def get_earliest_overview_data(cls, user_name: str):
        """获取最早的一次overview历史记录

        Args:
            user_name: 用户名

        Returns:
            历史记录对象或None（如果没有找到）
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .order_by(cls.cls_model.date.asc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def get_overview_data_near_date(cls, user_name: str, target_date: date):
        """获取指定日期附近的历史数据
        先尝试查询目标日期的精确数据，如果没有则查询目标日期之前最近的数据

        Args:
            user_name: 用户名
            target_date: 目标日期

        Returns:
            历史记录对象或None（如果没有找到）
        """
        async with get_postgres_manager().get_session() as session:
            # 先尝试查询目标日期的精确数据
            stmt = select(cls.cls_model).where(
                cls.cls_model.user_name == user_name, cls.cls_model.date == target_date
            )
            result = await session.execute(stmt)
            record = result.scalars().first()
            if record:
                return record

            # 如果没有精确数据，查询目标日期之前最近的数据
            stmt = (
                select(cls.cls_model)
                .where(
                    cls.cls_model.user_name == user_name,
                    cls.cls_model.date < target_date,
                )
                .order_by(cls.cls_model.date.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalars().first()


class EveCorporationContractDBUtils(_CommonUtils):
    """公司合同数据库工具类"""

    cls_model = model.EveCorporationContract


class EnterpriseMarketCostHistoryDBUtils(_CommonUtils):
    """企业版市场成本历史缓存数据库工具类"""

    cls_model = model.EnterpriseMarketCostHistory

    @classmethod
    async def get_by_type_id(cls, type_id: int):
        """根据 type_id 获取缓存数据

        Args:
            type_id: 物品类型ID

        Returns:
            缓存记录对象，如果不存在则返回 None
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.type_id == type_id)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def save_or_update(cls, type_id: int, history_data: dict):
        """保存或更新缓存数据

        Args:
            type_id: 物品类型ID
            history_data: 历史成本数据字典

        Returns:
            保存的记录对象
        """
        async with get_postgres_manager().get_session() as session:
            # 使用 PostgreSQL 的 insert（支持 on_conflict_do_update）实现真正的 upsert
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            # 构建插入语句
            stmt = pg_insert(cls.cls_model).values(
                type_id=type_id, history_data=history_data
            )

            # 基于主键 type_id 进行冲突处理
            # 如果冲突则更新 history_data 字段
            stmt = stmt.on_conflict_do_update(
                index_elements=[cls.cls_model.type_id],
                set_={"history_data": stmt.excluded.history_data},
            )

            await session.execute(stmt)
            await session.commit()

            # 重新查询返回
            stmt = select(cls.cls_model).where(cls.cls_model.type_id == type_id)
            result = await session.execute(stmt)
            return result.scalars().first()


# ============ 工作流分享功能数据库工具类 ============


class EveIndustryPlanTaskClaimDBUtils(_CommonUtils):
    """工作流任务接取记录数据库工具类"""

    cls_model = model.EveIndustryPlanTaskClaim

    @classmethod
    async def select_by_plan_token(cls, plan_token: str):
        """根据分享token获取所有接取记录

        Args:
            plan_token: 分享链接token

        Returns:
            接取记录列表
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.plan_token == plan_token)
            result = await session.execute(stmt)
            return result.scalars().all()

    @classmethod
    async def select_by_plan_token_and_item_key(
        cls, plan_token: str, workflow_item_key: str
    ):
        """根据分享token和工作流项key获取接取记录

        Args:
            plan_token: 分享链接token
            workflow_item_key: 工作流项唯一标识

        Returns:
            接取记录对象，如果不存在则返回 None
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.plan_token == plan_token)
                .where(cls.cls_model.workflow_item_key == workflow_item_key)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def delete_by_plan_token_and_item_key(
        cls, plan_token: str, workflow_item_key: str, session=None
    ):
        """删除接取记录（取消接取）

        Args:
            plan_token: 分享链接token
            workflow_item_key: 工作流项唯一标识
            session: 可选的数据库会话
        """
        if not session:
            async with get_postgres_manager().get_session() as session:
                stmt = (
                    delete(cls.cls_model)
                    .where(cls.cls_model.plan_token == plan_token)
                    .where(cls.cls_model.workflow_item_key == workflow_item_key)
                )
                await session.execute(stmt)
                await session.commit()
        else:
            stmt = (
                delete(cls.cls_model)
                .where(cls.cls_model.plan_token == plan_token)
                .where(cls.cls_model.workflow_item_key == workflow_item_key)
            )
            await session.execute(stmt)
