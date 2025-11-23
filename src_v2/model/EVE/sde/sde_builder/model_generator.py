"""
SDE 动态模型生成器
根据 JSONL 文件动态生成数据库表结构
"""
import os
from typing import Dict, Any, Optional
from sqlalchemy import text, Column, Integer, BigInteger, Float, Boolean, Text, DateTime, JSON
from sqlalchemy.dialects.postgresql import JSONB

from src_v2.core.log import logger
from .parser import SDEParser
from .database_manager import SDEModel
from .inv_types_model import InvTypes
from .blueprints_model import (
    IndustryBlueprints, IndustryActivities, IndustryActivityMaterials, IndustryActivityProducts
)
from .meta_groups_model import MetaGroups
from .market_groups_model import MarketGroups
from .map_solar_systems_model import MapSolarSystems
from .map_regions_model import MapRegions
from .inv_categories_model import InvCategories
from .inv_groups_model import InvGroups


class SDEModelGenerator:
    """SDE 模型生成器"""
    
    TYPE_MAPPING = {
        'Integer': 'INTEGER',
        'BigInteger': 'BIGINT',
        'Float': 'REAL',
        'Boolean': 'BOOLEAN',
        'Text': 'TEXT',
        'DateTime': 'TIMESTAMP',
        'JSON': 'JSONB',  # PostgreSQL 使用 JSONB
    }
    
    def __init__(self, parser: SDEParser):
        self.parser = parser
    
    async def create_table_from_file(self, conn, file_path: str, table_name: str) -> bool:
        """
        根据文件动态创建表结构
        
        Args:
            conn: 数据库连接
            file_path: JSONL 文件路径
            table_name: 表名
        
        Returns:
            是否成功
        """
        # 特殊处理：invTypes 表
        if table_name == 'types' or table_name == 'invTypes':
            return await self.create_inv_types_table(conn)
        
        # 特殊处理：blueprints 表
        if table_name == 'blueprints':
            return await self.create_blueprints_tables(conn)
        
        # 特殊处理：metaGroups 表
        if table_name == 'metaGroups':
            return await self.create_meta_groups_table(conn)
        
        # 特殊处理：marketGroups 表
        if table_name == 'marketGroups':
            return await self.create_market_groups_table(conn)
        
        # 特殊处理：mapSolarSystems 表
        if table_name == 'mapSolarSystems':
            return await self.create_map_solar_systems_table(conn)
        
        # 特殊处理：mapRegions 表
        if table_name == 'mapRegions':
            return await self.create_map_regions_table(conn)
        
        # 特殊处理：invCategories 表
        if table_name == 'categories' or table_name == 'invCategories':
            return await self.create_inv_categories_table(conn)
        
        # 特殊处理：invGroups 表
        if table_name == 'groups' or table_name == 'invGroups':
            return await self.create_inv_groups_table(conn)
        
        # 通用处理：其他表
        # 分析文件结构
        structure = self.parser.analyze_file_structure(file_path)
        
        if not structure:
            logger.error(f"无法分析文件结构: {file_path}")
            return False
        
        # 检查表是否已存在
        check_sql = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = :table_name
            )
        """)
        result = await conn.execute(check_sql, {"table_name": table_name})
        table_exists = result.scalar()
        
        if table_exists:
            logger.info(f"表 {table_name} 已存在，跳过创建")
            return True
        
        # 构建 CREATE TABLE 语句
        columns_def = []
        
        # 主键字段
        if '_key' in structure:
            key_type = structure['_key']
            if key_type in ('Integer', 'BigInteger'):
                columns_def.append(f'"_key" {self.TYPE_MAPPING.get(key_type, "INTEGER")} PRIMARY KEY')
            else:
                columns_def.append(f'"_key" TEXT PRIMARY KEY')
        else:
            # 如果没有 _key，使用默认的 INTEGER
            columns_def.append('"_key" INTEGER PRIMARY KEY')
        
        # 其他字段
        for field_name, field_type in structure.items():
            if field_name == '_key':
                continue
            
            pg_type = self.TYPE_MAPPING.get(field_type, 'TEXT')
            columns_def.append(f'"{field_name}" {pg_type}')
        
        # 创建表
        create_sql = f'CREATE TABLE "{table_name}" ({", ".join(columns_def)})'
        
        try:
            await conn.execute(text(create_sql))
            logger.info(f"已创建表: {table_name}")
            return True
        except Exception as e:
            logger.error(f"创建表失败: {table_name}, 错误: {e}")
            return False
    
    async def create_inv_types_table(self, conn) -> bool:
        """
        创建 InvTypes 表（使用 SQLAlchemy 模型）
        
        Args:
            conn: 数据库连接
        
        Returns:
            是否成功
        """
        try:
            # 确保 InvTypes 模型已经被导入和注册
            # InvTypes 继承自 SDEModel，所以会被 SDEModel.registry 识别
            
            # 使用 PostgreDatabaseManager 的 create_default_table 方法
            # 它会自动检查表是否存在，如果不存在则创建，如果存在则检查结构是否一致
            from src_v2.core.database.connect_manager import PostgreDatabaseManager
            db_manager = PostgreDatabaseManager()
            
            # 确保 InvTypes 类已经被导入（通过导入语句）
            # 由于 InvTypes 继承自 SDEModel，调用 create_default_table 时会自动扫描所有注册的模型
            await db_manager.create_default_table(conn, SDEModel)
            
            logger.info("已创建/检查 InvTypes 表")
            return True
        except Exception as e:
            logger.error(f"创建 InvTypes 表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def create_blueprints_tables(self, conn) -> bool:
        """
        创建蓝图相关表（4个表，使用 SQLAlchemy 模型）
        
        Args:
            conn: 数据库连接
        
        Returns:
            是否成功
        """
        try:
            # 确保蓝图模型已经被导入和注册
            # 蓝图模型继承自 SDEModel，所以会被 SDEModel.registry 识别
            
            # 使用 PostgreDatabaseManager 的 create_default_table 方法
            # 它会自动检查表是否存在，如果不存在则创建，如果存在则检查结构是否一致
            from src_v2.core.database.connect_manager import PostgreDatabaseManager
            db_manager = PostgreDatabaseManager()
            
            # 确保蓝图模型类已经被导入（通过导入语句）
            # 由于蓝图模型继承自 SDEModel，调用 create_default_table 时会自动扫描所有注册的模型
            await db_manager.create_default_table(conn, SDEModel)
            
            logger.info("已创建/检查蓝图表（IndustryBlueprints, IndustryActivities, "
                       "IndustryActivityMaterials, IndustryActivityProducts）")
            return True
        except Exception as e:
            logger.error(f"创建蓝图表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def create_meta_groups_table(self, conn) -> bool:
        """
        创建 MetaGroups 表（使用 SQLAlchemy 模型）
        
        Args:
            conn: 数据库连接
        
        Returns:
            是否成功
        """
        try:
            # 确保 MetaGroups 模型已经被导入和注册
            # MetaGroups 继承自 SDEModel，所以会被 SDEModel.registry 识别
            
            # 使用 PostgreDatabaseManager 的 create_default_table 方法
            # 它会自动检查表是否存在，如果不存在则创建，如果存在则检查结构是否一致
            from src_v2.core.database.connect_manager import PostgreDatabaseManager
            db_manager = PostgreDatabaseManager()
            
            # 确保 MetaGroups 类已经被导入（通过导入语句）
            # 由于 MetaGroups 继承自 SDEModel，调用 create_default_table 时会自动扫描所有注册的模型
            await db_manager.create_default_table(conn, SDEModel)
            
            logger.info("已创建/检查 MetaGroups 表")
            return True
        except Exception as e:
            logger.error(f"创建 MetaGroups 表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def create_market_groups_table(self, conn) -> bool:
        """
        创建 MarketGroups 表（使用 SQLAlchemy 模型）
        
        Args:
            conn: 数据库连接
        
        Returns:
            是否成功
        """
        try:
            # 确保 MarketGroups 模型已经被导入和注册
            # MarketGroups 继承自 SDEModel，所以会被 SDEModel.registry 识别
            
            # 使用 PostgreDatabaseManager 的 create_default_table 方法
            # 它会自动检查表是否存在，如果不存在则创建，如果存在则检查结构是否一致
            from src_v2.core.database.connect_manager import PostgreDatabaseManager
            db_manager = PostgreDatabaseManager()
            
            # 确保 MarketGroups 类已经被导入（通过导入语句）
            # 由于 MarketGroups 继承自 SDEModel，调用 create_default_table 时会自动扫描所有注册的模型
            await db_manager.create_default_table(conn, SDEModel)
            
            logger.info("已创建/检查 MarketGroups 表")
            return True
        except Exception as e:
            logger.error(f"创建 MarketGroups 表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def create_map_solar_systems_table(self, conn) -> bool:
        """
        创建 MapSolarSystems 表（使用 SQLAlchemy 模型）
        
        Args:
            conn: 数据库连接
        
        Returns:
            是否成功
        """
        try:
            # 确保 MapSolarSystems 模型已经被导入和注册
            # MapSolarSystems 继承自 SDEModel，所以会被 SDEModel.registry 识别
            
            # 使用 PostgreDatabaseManager 的 create_default_table 方法
            # 它会自动检查表是否存在，如果不存在则创建，如果存在则检查结构是否一致
            from src_v2.core.database.connect_manager import PostgreDatabaseManager
            db_manager = PostgreDatabaseManager()
            
            # 确保 MapSolarSystems 类已经被导入（通过导入语句）
            # 由于 MapSolarSystems 继承自 SDEModel，调用 create_default_table 时会自动扫描所有注册的模型
            await db_manager.create_default_table(conn, SDEModel)
            
            logger.info("已创建/检查 MapSolarSystems 表")
            return True
        except Exception as e:
            logger.error(f"创建 MapSolarSystems 表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def create_map_regions_table(self, conn) -> bool:
        """
        创建 MapRegions 表（使用 SQLAlchemy 模型）
        
        Args:
            conn: 数据库连接
        
        Returns:
            是否成功
        """
        try:
            # 确保 MapRegions 模型已经被导入和注册
            # MapRegions 继承自 SDEModel，所以会被 SDEModel.registry 识别
            
            # 使用 PostgreDatabaseManager 的 create_default_table 方法
            # 它会自动检查表是否存在，如果不存在则创建，如果存在则检查结构是否一致
            from src_v2.core.database.connect_manager import PostgreDatabaseManager
            db_manager = PostgreDatabaseManager()
            
            # 确保 MapRegions 类已经被导入（通过导入语句）
            # 由于 MapRegions 继承自 SDEModel，调用 create_default_table 时会自动扫描所有注册的模型
            await db_manager.create_default_table(conn, SDEModel)
            
            logger.info("已创建/检查 MapRegions 表")
            return True
        except Exception as e:
            logger.error(f"创建 MapRegions 表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def create_inv_categories_table(self, conn) -> bool:
        """
        创建 InvCategories 表（使用 SQLAlchemy 模型）
        
        Args:
            conn: 数据库连接
        
        Returns:
            是否成功
        """
        try:
            # 确保 InvCategories 模型已经被导入和注册
            # InvCategories 继承自 SDEModel，所以会被 SDEModel.registry 识别
            
            # 使用 PostgreDatabaseManager 的 create_default_table 方法
            # 它会自动检查表是否存在，如果不存在则创建，如果存在则检查结构是否一致
            from src_v2.core.database.connect_manager import PostgreDatabaseManager
            db_manager = PostgreDatabaseManager()
            
            # 确保 InvCategories 类已经被导入（通过导入语句）
            # 由于 InvCategories 继承自 SDEModel，调用 create_default_table 时会自动扫描所有注册的模型
            await db_manager.create_default_table(conn, SDEModel)
            
            logger.info("已创建/检查 InvCategories 表")
            return True
        except Exception as e:
            logger.error(f"创建 InvCategories 表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def create_inv_groups_table(self, conn) -> bool:
        """
        创建 InvGroups 表（使用 SQLAlchemy 模型）
        
        Args:
            conn: 数据库连接
        
        Returns:
            是否成功
        """
        try:
            # 确保 InvGroups 模型已经被导入和注册
            # InvGroups 继承自 SDEModel，所以会被 SDEModel.registry 识别
            
            # 使用 PostgreDatabaseManager 的 create_default_table 方法
            # 它会自动检查表是否存在，如果不存在则创建，如果存在则检查结构是否一致
            from src_v2.core.database.connect_manager import PostgreDatabaseManager
            db_manager = PostgreDatabaseManager()
            
            # 确保 InvGroups 类已经被导入（通过导入语句）
            # 由于 InvGroups 继承自 SDEModel，调用 create_default_table 时会自动扫描所有注册的模型
            await db_manager.create_default_table(conn, SDEModel)
            
            logger.info("已创建/检查 InvGroups 表")
            return True
        except Exception as e:
            logger.error(f"创建 InvGroups 表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def create_all_tables(self, conn, extract_dir: str) -> bool:
        """
        为所有需要解析的文件创建表
        
        Args:
            conn: 数据库连接
            extract_dir: 解压目录
        
        Returns:
            是否成功
        """
        files_to_parse = self.parser.get_files_to_parse(extract_dir)
        
        if not files_to_parse:
            logger.warning("没有找到需要创建表的文件")
            return False
        
        success_count = 0
        for file_path in files_to_parse:
            filename = os.path.basename(file_path)
            table_name = os.path.splitext(filename)[0]
            
            # 特殊处理：types.jsonl -> invTypes 表
            if table_name == 'types':
                table_name = 'invTypes'
            
            if await self.create_table_from_file(conn, file_path, table_name):
                success_count += 1
        
        logger.info(f"表创建完成: {success_count}/{len(files_to_parse)}")
        return success_count == len(files_to_parse)

