from typing import AnyStr
from sqlalchemy import delete, select, text, func, distinct
from sqlalchemy.dialects.sqlite import insert as insert
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timedelta
import traceback

from .connect_manager import postgres_manager as dbm
from ..log import logger
from . import model


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
        if not cls.cls_model:
            raise Exception("cls_model is None")
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model)
            result = await session.execute(stmt)
            return result.scalars().all()


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
    async def delete_all(cls):
        if not cls.cls_model:
            raise Exception("cls_model is None")
        async with dbm.get_session() as session:
            stmt = delete(cls.cls_model)
            await session.execute(stmt)

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
                logger.error(f"从 {table_name} 复制到 {cache_table_name} 失败。")
                raise

class UserDBUtils(_CommonUtils):
    cls_model = model.User

    @classmethod
    async def select_user_where_user_name(cls, user_name: AnyStr):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def delete_user_where_user_username(cls, user_name: AnyStr, session=None):
        if not session:
            async with dbm.get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
            await session.execute(stmt)

    @classmethod
    async def select_passwd_hash_where_user_name(cls, user_name: AnyStr):
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model.password_hash).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()

class UserDataDBUtils(_CommonUtils):
    cls_model = model.UserData

    @classmethod
    async def select_all_where_user_name(cls, user_name: AnyStr) -> cls_model:
        async with dbm.get_session() as session:
            stmt = select(cls.cls_model).where(cls.cls_model.user_name == user_name)
            result = await session.execute(stmt)
            return result.scalars().first()

    @classmethod
    async def delete_userdata_where_username(cls, user_name: AnyStr, session=None):
        if not session:
            async with dbm.get_session() as session:
                stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
                await session.execute(stmt)
        else:
            stmt = delete(cls.cls_model).where(cls.cls_model.user_name == user_name)
            await session.execute(stmt)
