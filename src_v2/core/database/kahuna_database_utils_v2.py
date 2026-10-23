import traceback
import warnings
from datetime import date, datetime, timedelta
from typing import AnyStr, AsyncGenerator, Optional, Type

from sqlalchemy import delete, func, insert, or_, select, text
from sqlalchemy.orm import aliased

from ..log import logger
from ..utils import get_beijing_utctime
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
    async def count_all(cls) -> int:
        """返回注册用户总数"""
        async with get_postgres_manager().get_session() as session:
            result = await session.execute(
                select(func.count()).select_from(cls.cls_model)
            )
            return result.scalar() or 0

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

    @classmethod
    async def search_users_by_keyword(cls, keyword: str, limit: int = 20) -> list:
        """按用户名模糊搜索（ilike），返回 User 对象列表，上限 limit。

        对应 api_vip.py:274 的查询：select(User).where(user_name.ilike(f'%{query}%')).limit(limit)。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name.ilike(f"%{keyword}%"))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())


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
    async def select_character_by_character_name_and_owner(cls, character_name: str, owner_user_name: str):
        """按角色名 + 归属用户查询角色

        用于校验“该角色是否属于当前用户”，避免仅按名字全局查询导致的越权。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.character_name == character_name,
                cls.cls_model.owner_user_name == owner_user_name
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

    @classmethod
    async def get_distinct_corporation_ids(cls) -> list[int]:
        """获取所有已授权角色所属的去重公司ID列表"""
        async with get_postgres_manager().get_session() as session:
            result = await session.execute(
                select(func.distinct(cls.cls_model.corporation_id))
                .where(cls.cls_model.corporation_id.isnot(None))
                .where(cls.cls_model.corporation_id > 0)
            )
            return [row[0] for row in result.fetchall()]

    @classmethod
    async def select_all_characters(cls) -> list:
        """查询全部 ESI 授权角色，返回 list（区别于基类 select_all 的异步迭代器）。

        对应 api_admin_esi.py:59 的查询：select(EveAuthedCharacter) 全量加载。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model)
            result = await session.execute(stmt)
            return list(result.scalars().all())


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

    @classmethod
    async def select_corporations_by_ids(
        cls, corporation_ids: list[int]
    ) -> list:
        """根据公司ID列表批量查询公司信息"""
        if not corporation_ids:
            return []
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.corporation_id.in_(corporation_ids)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())


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

    @classmethod
    async def count_all(cls) -> int:
        """统计全产业链计划总数"""
        async with get_postgres_manager().get_session() as session:
            result = await session.execute(
                select(func.count()).select_from(cls.cls_model)
            )
            return result.scalar() or 0


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
    async def count_vip_users(cls) -> int:
        """统计当前有效的 VIP 用户数（vip_alpha + vip_omega 且未过期）

        说明：过期后 vip_level 不会被清空（历史开通记录保留在原行），
        因此必须按 vip_end_date 过滤，否则会把已过期用户也算成会员。
        vip_end_date 以北京时间 naive 值存储；NULL 视为未设置到期（长期有效）。
        """
        now = get_beijing_utctime(datetime.now())
        async with get_postgres_manager().get_session() as session:
            result = await session.execute(
                select(func.count()).select_from(cls.cls_model).where(
                    cls.cls_model.vip_level.in_(['vip_alpha', 'vip_omega']),
                    or_(
                        cls.cls_model.vip_end_date.is_(None),
                        cls.cls_model.vip_end_date > now,
                    ),
                )
            )
            return result.scalar() or 0

    @classmethod
    async def select_active_vip_user_names(cls) -> list[str]:
        """获取当前有效的 VIP 用户名列表（vip_alpha + vip_omega 且未过期）

        口径与 count_vip_users 一致：vip_end_date 为 NULL 视为未设置到期。
        """
        now = get_beijing_utctime(datetime.now())
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model.user_name).where(
                cls.cls_model.vip_level.in_(['vip_alpha', 'vip_omega']),
                or_(
                    cls.cls_model.vip_end_date.is_(None),
                    cls.cls_model.vip_end_date > now,
                ),
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

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

    @classmethod
    async def select_distinct_system_ids_by_user_name(
        cls, user_name: str
    ) -> list[int]:
        """查询用户资产视图中的去重星系 ID 列表（system_id 非空）。

        对应 api_home.py:1017 的查询：SELECT DISTINCT system_id FROM eve_asset_view
        WHERE user_name = :un AND system_id IS NOT NULL。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(func.distinct(cls.cls_model.system_id))
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.system_id.isnot(None))
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]


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
            # 数据库级别聚合：避免全表加载到Python内存
            duration_sec = func.extract(
                'epoch',
                cls.cls_model.calculate_time - cls.cls_model.calculate_start_time
            )

            stmt = (
                select(
                    cls.cls_model.product_count.label('product_count'),
                    func.min(duration_sec).label('min_duration'),
                    func.max(duration_sec).label('max_duration'),
                    func.avg(duration_sec).label('avg_duration'),
                    func.count().label('count'),
                )
                .where(
                    cls.cls_model.calculate_start_time.isnot(None),
                    cls.cls_model.calculate_time.isnot(None),
                    cls.cls_model.product_count.isnot(None),
                )
                .group_by(cls.cls_model.product_count)
                .order_by(cls.cls_model.product_count)
            )
            result = await session.execute(stmt)
            rows = result.all()

            result_list = []
            for row in rows:
                result_list.append({
                    "product_count": row.product_count,
                    "min_duration": float(row.min_duration),
                    "max_duration": float(row.max_duration),
                    "avg_duration": float(row.avg_duration),
                    "count": row.count,
                })

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

    @classmethod
    async def get_latest_by_user_and_plan(
        cls, user_name: str, plan_name: str
    ) -> Optional:
        """查询某用户某计划最近一次计算历史（calculate_start_time 降序取 1 条）。

        对应 api_industry.py:614 的查询：select(EveIndustryCalculateHistory)
        .where(user_name, plan_name).order_by(calculate_start_time.desc()).limit(1)。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.plan_name == plan_name)
                .order_by(cls.cls_model.calculate_start_time.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()


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
    async def get_records_by_type_ids(
        cls,
        type_ids: list[int],
        region_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> list:
        """
        批量查询多个 type_id 在指定区域与日期范围内的历史统计数据。

        :param type_ids: 物品类型ID列表
        :param region_id: 区域ID
        :param start_date: 起始日期（包含）
        :param end_date: 结束日期（不包含）
        :return: 查询结果记录列表（含 type_id 字段）
        """
        if not type_ids:
            return []
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.type_id.in_(type_ids),
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

    @classmethod
    async def get_top_orders(
        cls, type_id: int, region_id: int, limit: int = 5
    ) -> dict[str, dict]:
        """查询某物品某区域的 top-N 买卖单。

        对应 api_astrbot_service.py:874 的查询：
        买单按 price 降序取前 N 条、卖单按 price 升序取前 N 条。

        Args:
            type_id: 物品类型ID
            region_id: 区域ID
            limit: 每个方向的订单数量上限，默认 5

        Returns:
            {"buy_order": {str(order_id): {"price": float, "volume_remain": int}, ...},
             "sell_order": {str(order_id): {"price": float, "volume_remain": int}, ...}}
        """
        async with get_postgres_manager().get_session() as session:
            buy_stmt = (
                select(cls.cls_model)
                .where(
                    cls.cls_model.type_id == type_id,
                    cls.cls_model.region_id == region_id,
                    cls.cls_model.is_buy_order == True,
                )
                .order_by(cls.cls_model.price.desc())
                .limit(limit)
            )
            sell_stmt = (
                select(cls.cls_model)
                .where(
                    cls.cls_model.type_id == type_id,
                    cls.cls_model.region_id == region_id,
                    cls.cls_model.is_buy_order == False,
                )
                .order_by(cls.cls_model.price.asc())
                .limit(limit)
            )

            buy_rows = (await session.execute(buy_stmt)).scalars().all()
            sell_rows = (await session.execute(sell_stmt)).scalars().all()

            order_data: dict[str, dict] = {"buy_order": {}, "sell_order": {}}
            for row in buy_rows:
                order_data["buy_order"][str(row.order_id)] = {
                    "price": float(row.price),
                    "volume_remain": int(row.volume_remain),
                }
            for row in sell_rows:
                order_data["sell_order"][str(row.order_id)] = {
                    "price": float(row.price),
                    "volume_remain": int(row.volume_remain),
                }
            return order_data

    @classmethod
    async def get_orders_by_type_region_location(
        cls, type_id: int, region_id: int, location_id: int
    ) -> tuple[list, list]:
        """按 type/region/location 查询全部买卖单。

        对应 api_enterprise.py:1947 的查询：
        卖单按 price 升序、买单按 price 降序，返回全部订单对象。

        Returns:
            (sell_orders, buy_orders)：卖单列表（价格升序）、买单列表（价格降序）
        """
        async with get_postgres_manager().get_session() as session:
            # 查询卖单（价格升序）
            sell_stmt = (
                select(cls.cls_model)
                .where(
                    cls.cls_model.type_id == type_id,
                    cls.cls_model.region_id == region_id,
                    cls.cls_model.location_id == location_id,
                    cls.cls_model.is_buy_order == False,
                )
                .order_by(cls.cls_model.price.asc())
            )
            sell_result = await session.execute(sell_stmt)
            sell_orders = list(sell_result.scalars().all())

            # 查询买单（价格降序）
            buy_stmt = (
                select(cls.cls_model)
                .where(
                    cls.cls_model.type_id == type_id,
                    cls.cls_model.region_id == region_id,
                    cls.cls_model.location_id == location_id,
                    cls.cls_model.is_buy_order == True,
                )
                .order_by(cls.cls_model.price.desc())
            )
            buy_result = await session.execute(buy_stmt)
            buy_orders = list(buy_result.scalars().all())

            return sell_orders, buy_orders


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

    @classmethod
    async def select_all_by_user_name(cls, user_name: str) -> list:
        """查询用户全部自选市场（完整对象，按 created_at 降序）。

        对应 api_enterprise.py:178 的查询：select(EnterpriseMarket).where(user_name).order_by(created_at.desc())。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .order_by(cls.cls_model.created_at.desc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @classmethod
    async def create_market(cls, user_name: str, tag: str, now) -> model.EnterpriseMarket:
        """新建自选市场并提交，返回带 id 的对象。

        对应 api_enterprise.py:953：session.add(EnterpriseMarket(...)) + flush（取 id）+ commit。
        """
        async with get_postgres_manager().get_session() as session:
            market = cls.cls_model(
                user_name=user_name,
                tag=tag,
                created_at=now,
                updated_at=now,
            )
            session.add(market)
            await session.flush()  # 刷新以获取ID
            await session.commit()
            return market

    @classmethod
    async def delete_by_user_name_and_market_id(
        cls, user_name: str, market_id: int
    ) -> bool:
        """删除自选市场（先校验归属），返回是否删除成功。

        对应 api_enterprise.py:1027：查询校验归属 → 存在则删除 + commit。
        市场不存在或无权限时返回 False，调用方应返回 404。
        """
        async with get_postgres_manager().get_session() as session:
            # 先查询确保该市场属于当前用户
            stmt = select(cls.cls_model).where(
                cls.cls_model.id == market_id,
                cls.cls_model.user_name == user_name,
            )
            result = await session.execute(stmt)
            market = result.scalar_one_or_none()

            if not market:
                return False

            # 删除市场
            await session.delete(market)
            await session.commit()
            return True

    @classmethod
    async def update_product_type_ids(
        cls, user_name: str, market_id: int, product_type_ids: list[int], now
    ) -> bool:
        """更新自选市场物品列表（校验归属），返回是否更新成功。

        对应 api_enterprise.py:1312：查询校验归属 → 更新 product_type_ids + commit。
        市场不存在或无权限时返回 False，调用方应返回 404。
        """
        async with get_postgres_manager().get_session() as session:
            # 先查询确保该市场属于当前用户
            stmt = select(cls.cls_model).where(
                cls.cls_model.id == market_id,
                cls.cls_model.user_name == user_name,
            )
            result = await session.execute(stmt)
            market = result.scalar_one_or_none()

            if not market:
                return False

            # 更新 product_type_ids
            market.product_type_ids = product_type_ids
            market.updated_at = now
            await session.commit()
            return True

    @classmethod
    async def clear_product_type_ids(
        cls, user_name: str, market_id: int, now
    ) -> bool:
        """清空自选市场物品列表（校验归属），返回是否更新成功。

        对应 api_enterprise.py:1394：查询校验归属 → 清空 product_type_ids + commit。
        市场不存在或无权限时返回 False，调用方应返回 404。
        """
        return await cls.update_product_type_ids(user_name, market_id, [], now)

    @classmethod
    async def add_containers(
        cls, user_name: str, market_id: int, containers: list[dict], now
    ) -> Optional[tuple[int, int]]:
        """追加资产拉取容器（去重合并 asset_pull_permission）。

        对应 api_enterprise.py:1494：查询校验归属 → 基于 container_id+owner_id 去重合并 → 更新 + commit。

        Args:
            user_name: 用户名
            market_id: 市场ID
            containers: 容器列表，每项为 {"container_id": int, "owner_id": int}
            now: 当前时间（datetime）

        Returns:
            (added_count, total_count)：成功追加后的新增数量与总数；
            市场不存在或无权限时返回 None，调用方应返回 404。
        """
        async with get_postgres_manager().get_session() as session:
            # 先查询确保该市场属于当前用户
            stmt = select(cls.cls_model).where(
                cls.cls_model.id == market_id,
                cls.cls_model.user_name == user_name,
            )
            result = await session.execute(stmt)
            market = result.scalar_one_or_none()

            if not market:
                return None

            # 获取当前的 asset_pull_permission
            current_list = (
                list(market.asset_pull_permission)
                if market.asset_pull_permission
                else []
            )

            # 将当前列表转换为集合以便去重（基于 container_id + owner_id）
            current_set = set()
            for item in current_list:
                if isinstance(item, dict) and "container_id" in item and "owner_id" in item:
                    current_set.add((item["container_id"], item["owner_id"]))

            # 添加新容器并去重
            added_count = 0
            for container in containers:
                key = (container["container_id"], container["owner_id"])
                if key not in current_set:
                    current_set.add(key)
                    added_count += 1

            # 转换回列表格式
            new_list = [
                {"container_id": cid, "owner_id": oid} for cid, oid in current_set
            ]

            # 更新 asset_pull_permission
            market.asset_pull_permission = new_list
            market.updated_at = now
            await session.commit()

            return added_count, len(new_list)

    @classmethod
    async def remove_container(
        cls, user_name: str, market_id: int, container: dict, now
    ) -> tuple[bool, bool]:
        """移除单个容器（container_id+owner_id 精确匹配）。

        对应 api_enterprise.py:1614：查询校验归属 → 从 asset_pull_permission 中移除指定容器 → 更新 + commit。

        Args:
            user_name: 用户名
            market_id: 市场ID
            container: 容器对象，包含 container_id 和 owner_id
            now: 当前时间（datetime）

        Returns:
            (market_exists, removed)：
            - market_exists=False：市场不存在或无权限（调用方应返回 404「自选市场不存在或无权限」）
            - market_exists=True, removed=False：容器不存在（调用方应返回 404「容器不存在」）
            - market_exists=True, removed=True：移除成功
        """
        async with get_postgres_manager().get_session() as session:
            # 先查询确保该市场属于当前用户
            stmt = select(cls.cls_model).where(
                cls.cls_model.id == market_id,
                cls.cls_model.user_name == user_name,
            )
            result = await session.execute(stmt)
            market = result.scalar_one_or_none()

            if not market:
                return False, False

            # 获取当前的 asset_pull_permission
            current_list = (
                list(market.asset_pull_permission)
                if market.asset_pull_permission
                else []
            )

            # 检查容器是否存在（匹配 container_id 和 owner_id 的组合）
            container_id = container.get("container_id")
            owner_id = container.get("owner_id")
            found = False
            new_list = []
            for item in current_list:
                if isinstance(item, dict):
                    item_cid = item.get("container_id")
                    item_oid = item.get("owner_id")
                    if item_cid == container_id and item_oid == owner_id:
                        found = True
                        continue  # 跳过这个项目，即删除它
                new_list.append(item)

            if not found:
                return True, False

            # 更新 asset_pull_permission
            market.asset_pull_permission = new_list
            market.updated_at = now
            await session.commit()

            return True, True


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
    async def get_latest_overview_data_by_user_names(
        cls, user_names: list[str]
    ) -> dict[str, dict]:
        """批量获取一组用户各自最新一条 overview 历史数据

        用于仪表盘运营统计：Redis 实时缓存缺失时回退到历史快照。

        Args:
            user_names: 用户名列表

        Returns:
            {user_name: data_dict}，没有历史数据的用户不会出现在结果里
        """
        if not user_names:
            return {}
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name.in_(user_names))
                .order_by(
                    cls.cls_model.user_name.asc(),
                    cls.cls_model.date.desc(),
                )
            )
            result = await session.execute(stmt)
            latest: dict[str, dict] = {}
            for row in result.scalars().all():
                if row.user_name not in latest:
                    latest[row.user_name] = row.data
            return latest

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


class EveCharacterOrdersStatsDBUtils(_CommonUtils):
    """角色订单统计数据工具类"""

    cls_model = model.EveCharacterOrdersStats

    @classmethod
    async def upsert_orders_stats(cls, user_name: str, period_type: str,
                                  period_start: date, buy_count: int, sell_count: int,
                                  buy_vol: int, sell_vol: int,
                                  buy_isk: float, sell_isk: float):
        async with get_postgres_manager().get_session() as session:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(cls.cls_model).values(
                user_name=user_name,
                period_type=period_type,
                period_start=period_start,
                buy_order_count=buy_count,
                sell_order_count=sell_count,
                buy_volume=buy_vol,
                sell_volume=sell_vol,
                buy_total_isk=buy_isk,
                sell_total_isk=sell_isk,
                updated_at=datetime.utcnow(),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_name", "period_type", "period_start"],
                set_={
                    "buy_order_count": stmt.excluded.buy_order_count,
                    "sell_order_count": stmt.excluded.sell_order_count,
                    "buy_volume": stmt.excluded.buy_volume,
                    "sell_volume": stmt.excluded.sell_volume,
                    "buy_total_isk": stmt.excluded.buy_total_isk,
                    "sell_total_isk": stmt.excluded.sell_total_isk,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)
            await session.commit()

    @classmethod
    async def get_orders_stats(
        cls, user_name: str, period_type: str, limit: int = 12
    ):
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(
                    cls.cls_model.user_name == user_name,
                    cls.cls_model.period_type == period_type,
                )
                .order_by(cls.cls_model.period_start.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()


class EveCharacterOrdersStatsDetailDBUtils(_CommonUtils):
    """角色订单统计明数据库工具类"""

    cls_model = model.EveCharacterOrdersStatsDetail

    @classmethod
    async def upsert_detail(cls, user_name: str, period_type: str,
                            period_start: date, type_id: int, is_buy_order: bool,
                            order_count: int, volume: int, total_isk: float):
        async with get_postgres_manager().get_session() as session:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(cls.cls_model).values(
                user_name=user_name,
                period_type=period_type,
                period_start=period_start,
                type_id=type_id,
                is_buy_order=is_buy_order,
                order_count=order_count,
                volume=volume,
                total_isk=total_isk,
                updated_at=datetime.utcnow(),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_name", "period_type", "period_start", "type_id", "is_buy_order"],
                set_={
                    "order_count": stmt.excluded.order_count,
                    "volume": stmt.excluded.volume,
                    "total_isk": stmt.excluded.total_isk,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)
            await session.commit()

    @classmethod
    async def get_detail_for_period(
        cls, user_name: str, period_type: str, period_start: date, is_buy_order: bool
    ):
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(
                    cls.cls_model.user_name == user_name,
                    cls.cls_model.period_type == period_type,
                    cls.cls_model.period_start == period_start,
                    cls.cls_model.is_buy_order == is_buy_order,
                )
                .order_by(cls.cls_model.total_isk.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()


class EveCorporationContractDBUtils(_CommonUtils):
    """公司合同数据库工具类"""

    cls_model = model.EveCorporationContract

    @classmethod
    async def select_by_contract_id(cls, contract_id: int) -> Optional:
        """按 contract_id 查询合同单条。

        对应 api_contract.py:117 的查询：select(EveCorporationContract).where(contract_id == contract_id)。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(cls.cls_model).where(
                cls.cls_model.contract_id == contract_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()


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
        """根据分享token和工作流项key获取接取记录（返回第一条，兼容旧逻辑）

        Args:
            plan_token: 分享链接token
            workflow_item_key: 工作流项唯一标识（小写格式）

        Returns:
            接取记录对象，如果不存在则返回 None
        """
        async with get_postgres_manager().get_session() as session:
            # 使用大小写不敏感的比较，兼容旧数据
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.plan_token == plan_token)
                .where(func.lower(cls.cls_model.workflow_item_key) == workflow_item_key.lower())
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def select_by_plan_token_and_item_key_all(
        cls, plan_token: str, workflow_item_key: str
    ):
        """根据分享token和工作流项key获取所有接取记录

        Args:
            plan_token: 分享链接token
            workflow_item_key: 工作流项唯一标识（小写格式）

        Returns:
            接取记录列表
        """
        async with get_postgres_manager().get_session() as session:
            # 使用大小写不敏感的比较，兼容旧数据
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.plan_token == plan_token)
                .where(func.lower(cls.cls_model.workflow_item_key) == workflow_item_key.lower())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    @classmethod
    async def select_by_plan_token_item_key_and_user(
        cls, plan_token: str, workflow_item_key: str, claimed_by: str
    ):
        """根据分享token、工作流项key和用户获取接取记录

        Args:
            plan_token: 分享链接token
            workflow_item_key: 工作流项唯一标识（小写格式）
            claimed_by: 接取用户

        Returns:
            接取记录对象，如果不存在则返回 None
        """
        async with get_postgres_manager().get_session() as session:
            # 使用大小写不敏感的比较，兼容旧数据
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.plan_token == plan_token)
                .where(func.lower(cls.cls_model.workflow_item_key) == workflow_item_key.lower())
                .where(cls.cls_model.claimed_by == claimed_by)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def get_total_claimed_quantity(cls, plan_token: str, workflow_item_key: str):
        """获取工作流项的总接取数量

        Args:
            plan_token: 分享链接token
            workflow_item_key: 工作流项唯一标识（小写格式）

        Returns:
            总接取数量
        """
        async with get_postgres_manager().get_session() as session:
            # 使用大小写不敏感的比较，兼容旧数据
            stmt = (
                select(func.sum(cls.cls_model.claimed_quantity))
                .where(cls.cls_model.plan_token == plan_token)
                .where(func.lower(cls.cls_model.workflow_item_key) == workflow_item_key.lower())
                .where(cls.cls_model.status == "claimed")
            )
            result = await session.execute(stmt)
            total = result.scalar()
            # 添加日志
            from src_v2.core.log import logger
            logger.info(f"[DEBUG-DB] get_total_claimed_quantity: plan={plan_token[:20]}..., key={workflow_item_key[:30]}..., total={total or 0}")
            return total or 0

    @classmethod
    async def delete_by_plan_token_and_item_key(
        cls, plan_token: str, workflow_item_key: str, session=None
    ):
        """删除接取记录（取消接取）

        Args:
            plan_token: 分享链接token
            workflow_item_key: 工作流项唯一标识（小写格式）
            session: 可选的数据库会话
        """
        # 使用大小写不敏感的比较，兼容旧数据
        if not session:
            async with get_postgres_manager().get_session() as session:
                stmt = (
                    delete(cls.cls_model)
                    .where(cls.cls_model.plan_token == plan_token)
                    .where(func.lower(cls.cls_model.workflow_item_key) == workflow_item_key.lower())
                )
                await session.execute(stmt)
                await session.commit()
        else:
            stmt = (
                delete(cls.cls_model)
                .where(cls.cls_model.plan_token == plan_token)
                .where(func.lower(cls.cls_model.workflow_item_key) == workflow_item_key.lower())
            )
            await session.execute(stmt)

    @classmethod
    async def claim_or_append(
        cls,
        plan_token: str,
        workflow_item_key: str,
        claimed_by: str,
        quantity: int,
        now,
    ) -> tuple[str, int]:
        """事务性接取/追加接取：单会话内查询已有记录 → 无则新建、有则追加数量，处理唯一约束冲突重试。

        Args:
            plan_token: 分享链接token
            workflow_item_key: 工作流项唯一标识（小写格式）
            claimed_by: 接取用户
            quantity: 本次接取数量（已由调用方校验 ≥1）
            now: 当前时间（datetime，由调用方传入，保持时间源一致）

        Returns:
            (result, new_quantity)，result ∈ {"created", "appended", "conflict"}：
            - "created": 新建成功，new_quantity 为本次接取数量
            - "appended": 追加成功，new_quantity 为追加后的总数量
            - "conflict": 唯一约束冲突且重试后仍未找到当前用户记录（并发竞态），调用方应返回 409

        对应 api_public.py:559 的整个事务块（含 IntegrityError 重试逻辑）。
        注意：本方法内部完成单会话 + 冲突重试，调用方不得再拆分为多次 DBUtils 调用。
        """
        from sqlalchemy.exc import IntegrityError

        async def _query_existing(session):
            """在给定会话中查询用户是否已有接取记录（大小写不敏感 key 匹配）"""
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.plan_token == plan_token)
                .where(func.lower(cls.cls_model.workflow_item_key) == workflow_item_key.lower())
                .where(cls.cls_model.claimed_by == claimed_by)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

        async with get_postgres_manager().get_session() as session:
            existing_claim = await _query_existing(session)

            if existing_claim:
                # 追加数量
                old_qty = existing_claim.claimed_quantity
                existing_claim.claimed_quantity += quantity
                existing_claim.claimed_at = now
                await session.commit()
                logger.info(
                    f"[CLAIM-DB] 追加成功: user={claimed_by}, old_qty={old_qty}, "
                    f"add_qty={quantity}, new_qty={existing_claim.claimed_quantity}"
                )
                return ("appended", existing_claim.claimed_quantity)

            # 创建新的接取记录
            claim = cls.cls_model(
                plan_token=plan_token,
                workflow_item_key=workflow_item_key,
                claimed_by=claimed_by,
                claimed_quantity=quantity,
                status="claimed",
            )
            session.add(claim)
            try:
                await session.commit()
                logger.info(
                    f"[CLAIM-DB] 创建成功: user={claimed_by}, qty={quantity}"
                )
                return ("created", quantity)
            except IntegrityError:
                await session.rollback()
                # 唯一约束冲突：并发导致，重试查询
                logger.warning(
                    f"[CLAIM-DB] 接取时发生唯一约束冲突: key={workflow_item_key}, user={claimed_by}"
                )
                existing_claim = await _query_existing(session)
                if existing_claim:
                    # 当前用户已有记录，执行追加
                    existing_claim.claimed_quantity += quantity
                    existing_claim.claimed_at = now
                    await session.commit()
                    return ("appended", existing_claim.claimed_quantity)
                # 其他用户的记录导致的冲突
                logger.error(
                    "[CLAIM-DB] 冲突但重试未找到当前用户记录，可能是其他用户的记录"
                )
                return ("conflict", 0)

    @classmethod
    async def cancel_claim_by_user(
        cls, plan_token: str, workflow_item_key: str, claimed_by: str
    ) -> bool:
        """取消当前用户的接取记录（校验归属后删除），返回是否删除成功。

        对应 api_public.py:695 的查询 + 删除逻辑。
        不存在该用户的接取记录时返回 False，调用方应返回 404。
        """
        async with get_postgres_manager().get_session() as session:
            # 查询当前用户的接取记录（使用大小写不敏感的key匹配）
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.plan_token == plan_token)
                .where(func.lower(cls.cls_model.workflow_item_key) == workflow_item_key.lower())
                .where(cls.cls_model.claimed_by == claimed_by)
            )
            result = await session.execute(stmt)
            claim = result.scalars().first()

            if not claim:
                return False

            # 删除记录
            await session.delete(claim)
            await session.commit()
            return True

    @classmethod
    async def transfer_claim(
        cls, plan_token: str, workflow_item_key: str, new_claimed_by: str, now
    ) -> int:
        """转移接取记录归属（用 update 语句，修复 detached 对象跨会话修改不生效的隐患）。

        Args:
            plan_token: 分享链接token
            workflow_item_key: 工作流项唯一标识（小写格式）
            new_claimed_by: 新的接取人
            now: 当前时间（datetime）

        Returns:
            受影响行数（0 表示记录不存在，调用方应返回 404）

        对应 api_public.py:960 的转移逻辑，改用 update 语句原子更新。
        """
        from sqlalchemy import update

        async with get_postgres_manager().get_session() as session:
            stmt = (
                update(cls.cls_model)
                .where(cls.cls_model.plan_token == plan_token)
                .where(func.lower(cls.cls_model.workflow_item_key) == workflow_item_key.lower())
                .values(claimed_by=new_claimed_by, claimed_at=now)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0


class EsiUsageLogDBUtils(_CommonUtils):
    """ESI 请求调用日志数据库工具类"""

    cls_model = model.EsiUsageLog

    @classmethod
    async def insert_log(
        cls,
        timestamp: datetime,
        endpoint: str,
        pool_name: str = None,
        character_id: int = None,
        status_code: int = None,
        latency_ms: float = None,
        error_message: str = None,
    ):
        """插入一条 ESI 调用日志"""
        log = cls.cls_model(
            timestamp=timestamp,
            endpoint=endpoint,
            pool_name=pool_name,
            character_id=character_id,
            status_code=status_code,
            latency_ms=latency_ms,
            error_message=error_message,
        )
        await cls.save_obj(log)

    @classmethod
    async def query_logs(cls, limit: int = 100, offset: int = 0) -> list:
        """查询 ESI 调用日志，按时间倒序排列，支持分页"""
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .order_by(cls.cls_model.timestamp.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @classmethod
    async def cleanup_old_logs(cls, days: int = 7) -> int:
        """清理指定天数前的日志记录"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        async with get_postgres_manager().get_session() as session:
            stmt = delete(cls.cls_model).where(cls.cls_model.timestamp < cutoff)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    @classmethod
    async def get_total_count(cls) -> int:
        """获取日志总记录数"""
        async with get_postgres_manager().get_session() as session:
            result = await session.execute(
                select(func.count()).select_from(cls.cls_model)
            )
            return result.scalar() or 0


# ============ 第一批问题点2 合规修复新增封装（供 T4/T5 API 下沉调用） ============


class EveLpValueSnapshotDBUtils(_CommonUtils):
    """LP 价值快照表操作工具类（含明细表）"""

    cls_model = model.EveLpValueSnapshot
    cls_detail_model = model.EveLpValueSnapshotDetail

    @classmethod
    async def get_latest_snapshot_date(cls) -> Optional[date]:
        """获取最新快照日期，无数据返回 None。

        对应 api_lp.py:23 的查询：SELECT snapshot_date FROM eve_lp_value_snapshot
        ORDER BY snapshot_date DESC LIMIT 1。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model.snapshot_date)
                .order_by(cls.cls_model.snapshot_date.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar()

    @classmethod
    async def select_snapshots_by_date(cls, snapshot_date: date) -> list[dict]:
        """按快照日期查询所有军团快照（按 lp_sell_value 降序），返回 dict 列表（剥离 top_items_json/created_at/id）。

        对应 api_lp.py:35 的查询 + 精简逻辑。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.snapshot_date == snapshot_date)
                .order_by(cls.cls_model.lp_sell_value.desc())
            )
            result = await session.execute(stmt)
            snapshots = []
            for s in result.scalars().all():
                snapshots.append(
                    {
                        "snapshot_date": str(s.snapshot_date),
                        "corporation_id": s.corporation_id,
                        "corporation_name": s.corporation_name,
                        "corporation_name_zh": s.corporation_name_zh,
                        "faction_id": s.faction_id,
                        "lp_buy_value": s.lp_buy_value,
                        "lp_sell_value": s.lp_sell_value,
                        "lp_sell_value_all": s.lp_sell_value_all,
                        "total_offers": s.total_offers,
                        "evaluated_offers": s.evaluated_offers,
                        "excluded_offers": s.excluded_offers,
                    }
                )
            return snapshots

    @classmethod
    async def get_latest_snapshot_id_and_date(cls) -> Optional[tuple[int, date]]:
        """获取最新快照的 (id, snapshot_date)。

        对应 api_lp.py:62 的查询：SELECT id, snapshot_date FROM eve_lp_value_snapshot
        ORDER BY snapshot_date DESC LIMIT 1。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model.id, cls.cls_model.snapshot_date)
                .order_by(cls.cls_model.snapshot_date.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.first()
            if not row:
                return None
            return row[0], row[1]

    @classmethod
    async def select_snapshot_id_by_date_and_corp(
        cls, snapshot_date: date, corporation_id: int
    ) -> Optional[int]:
        """按日期+军团查快照 id。

        对应 api_lp.py:72 的查询：SELECT id FROM eve_lp_value_snapshot
        WHERE snapshot_date = :date AND corporation_id = :cid。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model.id)
                .where(cls.cls_model.snapshot_date == snapshot_date)
                .where(cls.cls_model.corporation_id == corporation_id)
            )
            result = await session.execute(stmt)
            return result.scalar()

    @classmethod
    async def select_details_by_snapshot_id(cls, snapshot_id: int) -> list[dict]:
        """按 snapshot_id 查询全部明细（excluded 升序、daily_value_30d 降序），返回 dict 列表（剥离 snapshot_id/id）。

        对应 api_lp.py:84 的查询 + 精简逻辑。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_detail_model)
                .where(cls.cls_detail_model.snapshot_id == snapshot_id)
                .order_by(
                    cls.cls_detail_model.excluded.asc(),
                    cls.cls_detail_model.daily_value_30d.desc(),
                )
            )
            result = await session.execute(stmt)
            items = []
            for d in result.scalars().all():
                items.append(
                    {
                        "corporation_id": d.corporation_id,
                        "offer_id": d.offer_id,
                        "type_id": d.type_id,
                        "type_name_en": d.type_name_en,
                        "type_name_zh": d.type_name_zh,
                        "quantity": d.quantity,
                        "lp_cost": d.lp_cost,
                        "isk_cost": d.isk_cost,
                        "market_buy_price": d.market_buy_price,
                        "market_sell_price": d.market_sell_price,
                        "daily_volume_30d": d.daily_volume_30d,
                        "daily_value_30d": d.daily_value_30d,
                        "lp_buy_value": d.lp_buy_value,
                        "lp_sell_value": d.lp_sell_value,
                        "is_in_top": d.is_in_top,
                        "excluded": d.excluded,
                        "excluded_reason": d.excluded_reason,
                    }
                )
            return items


class EveIndustryPlanTaskImplementationDBUtils(_CommonUtils):
    """工作流实施标记表操作工具类"""

    cls_model = model.EveIndustryPlanTaskImplementation

    @classmethod
    async def select_by_user_plan_calculation(
        cls, user_name: str, plan_name: str, calculation_id: int
    ) -> list:
        """查询某计划某计算周期的全部实施标记。

        对应 api_industry.py:3351 的查询：select(EveIndustryPlanTaskImplementation)
        .where(user_name, plan_name, calculation_id)。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.plan_name == plan_name)
                .where(cls.cls_model.calculation_id == calculation_id)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @classmethod
    async def select_one_by_key(
        cls,
        user_name: str,
        plan_name: str,
        calculation_id: int,
        workflow_item_key: str,
    ) -> Optional:
        """按完整主键查单条实施标记。

        对应 api_industry.py:3456/3522 的查询：
        select(EveIndustryPlanTaskImplementation).where(user_name, plan_name, calculation_id, workflow_item_key)。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.plan_name == plan_name)
                .where(cls.cls_model.calculation_id == calculation_id)
                .where(cls.cls_model.workflow_item_key == workflow_item_key)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @classmethod
    async def sync_implementations(
        cls,
        user_name: str,
        plan_name: str,
        calculation_id: int,
        client_items: list[dict],
        deleted_keys: list[str],
        parse_dt,
    ) -> tuple[list[dict], list[dict]]:
        """事务性同步实施标记（单会话内完成查询/新增/更新/删除/冲突检测）。

        Args:
            user_name: 用户名
            plan_name: 计划名
            calculation_id: 计算周期ID
            client_items: 客户端推送的变更项列表，每项含 workflow_item_key/implemented/runs_implemented/modified_at
            deleted_keys: 客户端删除的工作流项 key 列表
            parse_dt: 时间解析函数（由 API 传入 parse_naive_utc_datetime，避免 DBUtils 依赖业务时间解析细节）

        Returns:
            (conflicts, server_only_items)：冲突列表与服务器独有项列表
            - conflicts: [{"workflow_item_key", "server_value": {...}, "resolution": "use_server"}, ...]
            - server_only_items: [{"workflow_item_key", "implemented", "runs_implemented", "modified_at"}, ...]

        对应 api_industry.py:3446 整个 sync 事务块。
        注意：多步写操作必须整体在一个 session 内 commit，调用方不得拆分为多次 DBUtils 调用。
        """
        conflicts: list[dict] = []
        server_only_items: list[dict] = []

        async with get_postgres_manager().get_session() as session:
            # 处理客户端推送的变更
            for item in client_items:
                item_key = item.get("workflow_item_key")
                client_modified_at = item.get("modified_at")

                # 查询服务器上的记录
                stmt = (
                    select(cls.cls_model)
                    .where(cls.cls_model.user_name == user_name)
                    .where(cls.cls_model.plan_name == plan_name)
                    .where(cls.cls_model.calculation_id == calculation_id)
                    .where(cls.cls_model.workflow_item_key == item_key)
                )
                result = await session.execute(stmt)
                server_record = result.scalar_one_or_none()

                if server_record:
                    # 服务器已有记录，比较时间戳
                    server_modified_at = server_record.modified_at
                    client_time = parse_dt(client_modified_at) or datetime.utcnow()

                    # 如果客户端标记为未实施，删除服务器记录
                    if not item.get("implemented", True):
                        if client_time >= server_modified_at:
                            # 客户端更新且标记为未实施，删除服务器记录
                            await session.delete(server_record)
                            continue
                        # 如果服务器更新，则通知冲突

                    if client_time > server_modified_at:
                        # 客户端更新，覆盖服务器
                        server_record.implemented = item.get("implemented", True)
                        server_record.runs_implemented = item.get(
                            "runs_implemented"
                        )
                        server_record.modified_at = client_time
                        server_record.modified_by_client = "web_client"
                    elif client_time < server_modified_at:
                        # 服务器更新，通知客户端冲突
                        conflicts.append(
                            {
                                "workflow_item_key": item_key,
                                "server_value": {
                                    "implemented": server_record.implemented,
                                    "runs_implemented": server_record.runs_implemented,
                                    "modified_at": server_record.modified_at.isoformat(),
                                },
                                "resolution": "use_server",
                            }
                        )
                    # 如果时间相等，不做处理
                else:
                    # 服务器没有记录，且客户端标记为已实施，才创建新记录
                    if item.get("implemented", True):
                        new_record = cls.cls_model()
                        new_record.user_name = user_name
                        new_record.plan_name = plan_name
                        new_record.calculation_id = calculation_id
                        new_record.workflow_item_key = item_key
                        new_record.implemented = True
                        new_record.runs_implemented = item.get("runs_implemented")
                        new_record.modified_at = (
                            parse_dt(client_modified_at) or datetime.utcnow()
                        )
                        new_record.modified_by_client = "web_client"
                        session.add(new_record)
                    # 如果客户端标记为未实施且服务器没有记录，无需操作

            # 处理删除请求
            for key in deleted_keys:
                stmt = (
                    select(cls.cls_model)
                    .where(cls.cls_model.user_name == user_name)
                    .where(cls.cls_model.plan_name == plan_name)
                    .where(cls.cls_model.calculation_id == calculation_id)
                    .where(cls.cls_model.workflow_item_key == key)
                )
                result = await session.execute(stmt)
                server_record = result.scalar_one_or_none()
                if server_record:
                    await session.delete(server_record)

            # 查询服务器上客户端没有的项
            stmt = (
                select(cls.cls_model)
                .where(cls.cls_model.user_name == user_name)
                .where(cls.cls_model.plan_name == plan_name)
                .where(cls.cls_model.calculation_id == calculation_id)
            )
            result = await session.execute(stmt)
            all_server_items = result.scalars().all()

            client_keys = {item.get("workflow_item_key") for item in client_items}
            for server_item in all_server_items:
                if server_item.workflow_item_key not in client_keys:
                    server_only_items.append(
                        {
                            "workflow_item_key": server_item.workflow_item_key,
                            "implemented": server_item.implemented,
                            "runs_implemented": server_item.runs_implemented,
                            "modified_at": server_item.modified_at.isoformat()
                            if server_item.modified_at
                            else None,
                        }
                    )

            await session.commit()

        return conflicts, server_only_items


class UserWatchedSystemDBUtils(_CommonUtils):
    """用户关注星系列表操作工具类"""

    cls_model = model.UserWatchedSystem

    @classmethod
    async def select_system_ids_by_user_name(cls, user_name: str) -> list[int]:
        """查询用户关注的全部 system_id（按 created_at 升序）。

        对应 api_home.py:1086、internal_mcp.py:381 的查询：
        select(UserWatchedSystem.system_id).where(user_name).order_by(created_at)。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(cls.cls_model.system_id)
                .where(cls.cls_model.user_name == user_name)
                .order_by(cls.cls_model.created_at)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @classmethod
    async def add_system_ignore_conflict(cls, user_name: str, system_id: int) -> None:
        """幂等添加关注星系（on_conflict_do_nothing）。

        对应 api_home.py:1142 的查询：pg_insert(UserWatchedSystem).values(...)
        .on_conflict_do_nothing(index_elements=['user_name', 'system_id'])。
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        async with get_postgres_manager().get_session() as session:
            stmt = (
                pg_insert(cls.cls_model)
                .values(
                    user_name=user_name,
                    system_id=system_id,
                    created_at=datetime.utcnow(),
                )
                .on_conflict_do_nothing(
                    index_elements=["user_name", "system_id"]
                )
            )
            await session.execute(stmt)
            await session.commit()

    @classmethod
    async def batch_add_systems_ignore_conflict(
        cls, user_name: str, system_ids: list[int]
    ) -> int:
        """批量幂等添加关注星系，返回实际新增数量。

        对应 api_home.py:1051 的批量插入：session.add(UserWatchedSystem(...)) 循环。
        使用 on_conflict_do_nothing 保证幂等（重复 system_id 跳过）。
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        if not system_ids:
            return 0

        now = datetime.utcnow()
        async with get_postgres_manager().get_session() as session:
            rows = [
                {
                    "user_name": user_name,
                    "system_id": sid,
                    "created_at": now,
                }
                for sid in system_ids
            ]
            stmt = (
                pg_insert(cls.cls_model)
                .values(rows)
                .on_conflict_do_nothing(
                    index_elements=["user_name", "system_id"]
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0

    @classmethod
    async def delete_by_user_and_system(
        cls, user_name: str, system_id: int
    ) -> None:
        """移除关注星系。

        对应 api_home.py:1182 的查询：delete(UserWatchedSystem)
        .where(user_name, system_id)。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = delete(cls.cls_model).where(
                cls.cls_model.user_name == user_name,
                cls.cls_model.system_id == system_id,
            )
            await session.execute(stmt)
            await session.commit()
