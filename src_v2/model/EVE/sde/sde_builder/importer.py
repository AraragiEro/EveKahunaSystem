"""
SDE 导入模块
将解析后的数据批量导入 PostgreSQL
"""
import os
import json
from typing import List, Dict, Any, Optional, Iterator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src_v2.core.log import logger
from .parser import SDEParser
from .model_generator import SDEModelGenerator
from .inv_types_model import InvTypes, process_inv_types_row
from .blueprints_model import (
    IndustryBlueprints, IndustryActivities, IndustryActivityMaterials, IndustryActivityProducts,
    process_blueprints_row
)
from .meta_groups_model import MetaGroups, process_meta_groups_row
from .inv_groups_model import InvGroups, process_inv_groups_row
from .inv_categories_model import InvCategories, process_inv_categories_row
from .market_groups_model import MarketGroups, process_market_groups_row
from .map_solar_systems_model import MapSolarSystems, process_map_solar_systems_row
from .map_regions_model import MapRegions, process_map_regions_row


class SDEImporter:
    """SDE 数据导入器"""
    
    def __init__(self, db_manager, parser: SDEParser):
        """
        初始化导入器
        
        Args:
            db_manager: SDEDatabaseManager 实例
            parser: SDEParser 实例
        """
        self.db_manager = db_manager
        self.parser = parser
        self.model_generator = SDEModelGenerator(parser)
        self.batch_size = 5000  # 批量大小
    
    async def get_current_version(self) -> Optional[int]:
        """
        获取当前数据库中的版本号
        
        Returns:
            版本号，如果不存在返回 None
        """
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    text('SELECT "buildNumber" FROM "_sde" WHERE "_key" = :key'),
                    {"key": "sde"}
                )
                row = result.first()
                if row:
                    return row[0]
                return None
        except Exception as e:
            logger.warning(f"获取当前版本号失败: {e}")
            return None
    
    async def truncate_table(self, conn, table_name: str) -> bool:
        """
        清空表数据（使用 TRUNCATE）
        
        Args:
            conn: 数据库连接
            table_name: 表名
        
        Returns:
            是否成功
        """
        # 先检查表是否存在
        check_sql = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = :table_name
            )
        """)
        result = await conn.execute(check_sql, {"table_name": table_name})
        table_exists = result.scalar()
        
        if not table_exists:
            logger.info(f"表 {table_name} 不存在，跳过清空操作")
            return True
        
        # 使用 SAVEPOINT 来隔离错误，避免事务被中止
        # 清理保存点名称，只保留字母数字和下划线
        savepoint_name = f"sp_truncate_{table_name}".replace('"', '').replace("'", "").replace('-', '_')
        # PostgreSQL 保存点名称限制为 63 个字符
        if len(savepoint_name) > 60:
            savepoint_name = savepoint_name[:60]
        
        try:
            # 创建保存点
            await conn.execute(text(f'SAVEPOINT {savepoint_name}'))
            
            try:
                # 使用 TRUNCATE CASCADE 自动处理外键依赖
                await conn.execute(text(f'TRUNCATE TABLE "{table_name}" CASCADE'))
                logger.info(f"已清空表: {table_name}")
                # 释放保存点
                await conn.execute(text(f'RELEASE SAVEPOINT {savepoint_name}'))
                return True
            except Exception as e:
                # TRUNCATE 失败，回滚到保存点
                logger.warning(f"TRUNCATE 表 {table_name} 失败: {e}，尝试使用 DELETE")
                await conn.execute(text(f'ROLLBACK TO SAVEPOINT {savepoint_name}'))
                
                try:
                    # 创建新的保存点用于 DELETE
                    delete_savepoint = f"{savepoint_name}_delete"
                    await conn.execute(text(f'SAVEPOINT {delete_savepoint}'))
                    # 回退到 DELETE
                    await conn.execute(text(f'DELETE FROM "{table_name}"'))
                    logger.info(f"已使用 DELETE 清空表: {table_name}")
                    # 释放保存点
                    await conn.execute(text(f'RELEASE SAVEPOINT {delete_savepoint}'))
                    return True
                except Exception as e2:
                    # DELETE 也失败，回滚到保存点
                    await conn.execute(text(f'ROLLBACK TO SAVEPOINT {delete_savepoint}'))
                    logger.error(f"DELETE 表 {table_name} 也失败: {e2}")
                    return False
        except Exception as outer_e:
            # 保存点操作失败，记录错误
            logger.error(f"清空表 {table_name} 时发生错误: {outer_e}")
            return False
    
    async def disable_foreign_keys(self, conn) -> bool:
        """
        临时禁用外键约束（PostgreSQL 特有）
        
        Args:
            conn: 数据库连接
        
        Returns:
            是否成功
        """
        try:
            await conn.execute(text("SET session_replication_role = 'replica'"))
            logger.info("已禁用外键约束检查")
            return True
        except Exception as e:
            logger.warning(f"禁用外键约束失败: {e}")
            return False
    
    async def enable_foreign_keys(self, conn) -> bool:
        """
        重新启用外键约束
        
        Args:
            conn: 数据库连接
        
        Returns:
            是否成功
        """
        try:
            await conn.execute(text("SET session_replication_role = 'origin'"))
            logger.info("已启用外键约束检查")
            return True
        except Exception as e:
            logger.warning(f"启用外键约束失败: {e}")
            return False
    
    async def bulk_insert_via_copy(self, conn, table_name: str, columns: List[str], 
                                   data_batch: List[Dict[str, Any]]) -> bool:
        """
        使用 PostgreSQL COPY 命令批量插入数据（最快）
        注意：由于 asyncpg 的 COPY 需要特殊处理，这里暂时返回 False 以使用批量 INSERT
        
        Args:
            conn: 数据库连接
            table_name: 表名
            columns: 列名列表
            data_batch: 数据批次
        
        Returns:
            是否成功（暂时总是返回 False 以使用批量 INSERT）
        """
        # TODO: 实现真正的 COPY 命令（需要直接使用 asyncpg 的 copy_from_stream）
        # 目前暂时使用批量 INSERT
        return False
    
    async def bulk_insert_via_sql(self, conn, table_name: str, columns: List[str],
                                  data_batch: List[Dict[str, Any]]) -> bool:
        """
        使用批量 INSERT 语句插入数据
        
        Args:
            conn: 数据库连接
            table_name: 表名
            columns: 列名列表
            data_batch: 数据批次
        
        Returns:
            是否成功
        """
        if not data_batch:
            return True
        
        # PostgreSQL/asyncpg 限制：参数数量不能超过 32767
        # 计算每个批次的最大行数
        max_params = 32767
        num_columns = len(columns)
        max_rows_per_batch = max(1, max_params // num_columns)
        
        # 如果批次太大，拆分成多个小批次
        if len(data_batch) <= max_rows_per_batch:
            # 批次大小合适，直接插入
            return await self._execute_batch_insert(conn, table_name, columns, data_batch)
        else:
            # 批次太大，拆分成多个小批次
            logger.debug(f"批次太大 ({len(data_batch)} 行, {num_columns} 列)，拆分成多个小批次 (每批最多 {max_rows_per_batch} 行)")
            for i in range(0, len(data_batch), max_rows_per_batch):
                sub_batch = data_batch[i:i + max_rows_per_batch]
                success = await self._execute_batch_insert(conn, table_name, columns, sub_batch)
                if not success:
                    return False
            return True
    
    async def _execute_batch_insert(self, conn, table_name: str, columns: List[str],
                                    data_batch: List[Dict[str, Any]]) -> bool:
        """
        执行单个批次的插入操作
        
        Args:
            conn: 数据库连接
            table_name: 表名
            columns: 列名列表
            data_batch: 数据批次（已确保不超过参数限制）
        
        Returns:
            是否成功
        """
        if not data_batch:
            return True
        
        try:
            column_names = ', '.join([f'"{col}"' for col in columns])
            
            # 构建批量插入语句，使用 VALUES 子句
            # 格式: INSERT INTO table (col1, col2) VALUES (val1, val2), (val3, val4), ...
            values_parts = []
            params = {}
            param_index = 0
            
            for row_idx, row in enumerate(data_batch):
                row_values = []
                for col in columns:
                    param_name = f"p{param_index}"
                    value = row.get(col)
                    if isinstance(value, (dict, list)):
                        # JSON 类型，转换为 JSON 字符串
                        params[param_name] = json.dumps(value, ensure_ascii=False)
                    else:
                        params[param_name] = value
                    row_values.append(f":{param_name}")
                    param_index += 1
                values_parts.append(f"({', '.join(row_values)})")
            
            values_clause = ', '.join(values_parts)
            insert_sql = f'INSERT INTO "{table_name}" ({column_names}) VALUES {values_clause}'
            
            # 执行批量插入
            await conn.execute(text(insert_sql), params)
            
            logger.debug(f"通过批量 INSERT 插入了 {len(data_batch)} 条记录到 {table_name}")
            return True
        
        except Exception as e:
            logger.error(f"批量 INSERT 失败: {e}")
            raise
    
    async def import_file(self, conn, file_path: str, table_name: str) -> int:
        """
        导入单个文件的数据
        
        Args:
            conn: 数据库连接
            file_path: 文件路径
            table_name: 表名
        
        Returns:
            导入的记录数
        """
        logger.info(f"开始导入文件: {file_path} -> 表: {table_name}")
        
        # 特殊处理：invTypes 表
        if table_name == 'types' or table_name == 'invTypes':
            logger.debug("使用特殊处理导入 invTypes 表")
            return await self.import_inv_types(conn, file_path)
        
        # 特殊处理：blueprints 表
        if table_name == 'blueprints':
            logger.info("检测到 blueprints.jsonl，使用特殊处理导入蓝图表")
            return await self.import_blueprints(conn, file_path)
        
        # 特殊处理：metaGroups 表
        if table_name == 'metaGroups':
            logger.debug("使用特殊处理导入 metaGroups 表")
            return await self.import_meta_groups(conn, file_path)
        
        # 特殊处理：invGroups 表
        if table_name == 'groups' or table_name == 'invGroups':
            logger.debug("使用特殊处理导入 invGroups 表")
            return await self.import_inv_groups(conn, file_path)
        
        # 特殊处理：invCategories 表
        if table_name == 'categories' or table_name == 'invCategories':
            logger.debug("使用特殊处理导入 invCategories 表")
            return await self.import_inv_categories(conn, file_path)
        
        # 特殊处理：marketGroups 表
        if table_name == 'marketGroups':
            logger.debug("使用特殊处理导入 marketGroups 表")
            return await self.import_market_groups(conn, file_path)
        
        # 特殊处理：mapSolarSystems 表
        if table_name == 'mapSolarSystems':
            logger.debug("使用特殊处理导入 mapSolarSystems 表")
            return await self.import_map_solar_systems(conn, file_path)
        
        # 特殊处理：mapRegions 表
        if table_name == 'mapRegions':
            logger.debug("使用特殊处理导入 mapRegions 表")
            return await self.import_map_regions(conn, file_path)
        
        # 通用处理：其他表
        # 解析文件获取数据
        data_iterator = self.parser.parse_file(file_path)
        
        # 获取第一行数据以确定列结构
        first_row = None
        batch = []
        total_count = 0
        
        try:
            for row in data_iterator:
                if first_row is None:
                    first_row = row
                    columns = list(row.keys())
                    logger.info(f"表 {table_name} 的列: {columns}")
                
                batch.append(row)
                
                # 达到批量大小时执行插入
                if len(batch) >= self.batch_size:
                    # 尝试使用 COPY，失败则使用批量 INSERT
                    success = await self.bulk_insert_via_copy(conn, table_name, columns, batch)
                    if not success:
                        await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                    
                    total_count += len(batch)
                    batch = []
                    
                    if total_count % 50000 == 0:
                        logger.info(f"已导入 {total_count} 条记录到 {table_name}")
            
            # 插入剩余数据
            if batch:
                success = await self.bulk_insert_via_copy(conn, table_name, columns, batch)
                if not success:
                    await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                total_count += len(batch)
            
            logger.info(f"文件导入完成: {file_path} -> 表: {table_name}, 共 {total_count} 条记录")
            return total_count
        
        except Exception as e:
            logger.error(f"导入文件失败: {file_path}, 错误: {e}")
            raise
    
    async def import_inv_types(self, conn, file_path: str) -> int:
        """
        特殊处理：导入 InvTypes 表数据
        
        Args:
            conn: 数据库连接
            file_path: types.jsonl 文件路径
        
        Returns:
            导入的记录数
        """
        import json
        
        logger.info(f"使用特殊处理导入 InvTypes 表: {file_path}")
        
        table_name = 'invTypes'
        columns = [
            'typeID', 'groupID', 'typeName_en', 'typeName_zh', 'description_en', 'description_zh',
            'mass', 'volume', 'packagedVolume', 'capacity', 'portionSize', 'factionID', 'raceID',
            'basePrice', 'published', 'marketGroupID', 'graphicID', 'radius', 'iconID', 'soundID',
            'sofFactionName', 'sofMaterialSetID', 'metaGroupID', 'variationparentTypeID'
        ]
        
        batch = []
        total_count = 0
        line_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        # 解析原始 JSON
                        raw_row = json.loads(line)
                        
                        # 使用特殊处理函数处理数据
                        processed_row = process_inv_types_row(raw_row)
                        
                        batch.append(processed_row)
                        line_count += 1
                        
                        # 达到批量大小时执行插入
                        if len(batch) >= self.batch_size:
                            await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                            total_count += len(batch)
                            batch = []
                            
                            if total_count % 50000 == 0:
                                logger.info(f"已导入 {total_count} 条记录到 {table_name}")
                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"第 {line_count + 1} 行 JSON 解析失败: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"第 {line_count + 1} 行处理失败: {e}")
                        continue
            
            # 插入剩余数据
            if batch:
                await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                total_count += len(batch)
            
            logger.info(f"InvTypes 表导入完成: {file_path}, 共 {total_count} 条记录")
            return total_count
        
        except Exception as e:
            logger.error(f"导入 InvTypes 表失败: {file_path}, 错误: {e}")
            raise
    
    async def import_blueprints(self, conn, file_path: str) -> int:
        """
        特殊处理：导入蓝图相关表数据（4个表）
        
        Args:
            conn: 数据库连接
            file_path: blueprints.jsonl 文件路径
        
        Returns:
            导入的总记录数（4个表的总和）
        """
        import json
        
        logger.info(f"使用特殊处理导入蓝图表: {file_path}")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logger.error(f"蓝图文件不存在: {file_path}")
            return 0
        
        logger.info(f"开始读取蓝图文件: {file_path}")
        
        # 定义4个表的列名
        blueprints_columns = ['blueprintTypeID', 'maxProductionLimit']
        activities_columns = ['blueprintTypeID', 'activityID', 'time']
        materials_columns = ['blueprintTypeID', 'activityID', 'materialTypeID', 'quantity']
        products_columns = ['blueprintTypeID', 'activityID', 'productTypeID', 'quantity', 'probability']
        
        # 批量收集数据
        blueprints_batch = []
        activities_batch = []
        materials_batch = []
        products_batch = []
        
        total_blueprints = 0
        total_activities = 0
        total_materials = 0
        total_products = 0
        line_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        # 解析原始 JSON
                        raw_row = json.loads(line)
                        
                        # 使用特殊处理函数处理数据
                        bp_records, act_records, mat_records, prod_records = process_blueprints_row(raw_row)
                        
                        # 调试：记录前几条数据的处理情况
                        if line_count <= 3:
                            logger.debug(f"处理第 {line_count} 行: BlueprintID={raw_row.get('blueprintTypeID')}, "
                                        f"BP={len(bp_records)}, Act={len(act_records)}, "
                                        f"Mat={len(mat_records)}, Prod={len(prod_records)}")
                        
                        # 添加到批次
                        blueprints_batch.extend(bp_records)
                        activities_batch.extend(act_records)
                        materials_batch.extend(mat_records)
                        products_batch.extend(prod_records)
                        
                        line_count += 1
                        
                        # 计算总批次大小（所有4个表的总记录数）
                        total_batch_size = (len(blueprints_batch) + len(activities_batch) + 
                                           len(materials_batch) + len(products_batch))
                        
                        # 达到批量大小时执行插入（检查总记录数或任一表达到批量大小）
                        if total_batch_size >= self.batch_size or len(blueprints_batch) >= self.batch_size:
                            # 插入 IndustryBlueprints
                            if blueprints_batch:
                                try:
                                    await self.bulk_insert_via_sql(conn, 'industryBlueprints', blueprints_columns, blueprints_batch)
                                    total_blueprints += len(blueprints_batch)
                                    blueprints_batch = []
                                except Exception as e:
                                    logger.error(f"批量插入 IndustryBlueprints 失败: {e}")
                                    raise
                            
                            # 插入 IndustryActivities
                            if activities_batch:
                                try:
                                    await self.bulk_insert_via_sql(conn, 'industryActivities', activities_columns, activities_batch)
                                    total_activities += len(activities_batch)
                                    activities_batch = []
                                except Exception as e:
                                    logger.error(f"批量插入 IndustryActivities 失败: {e}")
                                    raise
                            
                            # 插入 IndustryActivityMaterials
                            if materials_batch:
                                try:
                                    await self.bulk_insert_via_sql(conn, 'industryActivityMaterials', materials_columns, materials_batch)
                                    total_materials += len(materials_batch)
                                    materials_batch = []
                                except Exception as e:
                                    logger.error(f"批量插入 IndustryActivityMaterials 失败: {e}")
                                    raise
                            
                            # 插入 IndustryActivityProducts
                            if products_batch:
                                try:
                                    await self.bulk_insert_via_sql(conn, 'industryActivityProducts', products_columns, products_batch)
                                    total_products += len(products_batch)
                                    products_batch = []
                                except Exception as e:
                                    logger.error(f"批量插入 IndustryActivityProducts 失败: {e}")
                                    raise
                            
                            total_all = total_blueprints + total_activities + total_materials + total_products
                            if total_all % 50000 == 0:
                                logger.info(f"已导入蓝图数据: Blueprints={total_blueprints}, Activities={total_activities}, "
                                          f"Materials={total_materials}, Products={total_products}, 总计={total_all}")
                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"第 {line_count + 1} 行 JSON 解析失败: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"第 {line_count + 1} 行处理失败: {e}")
                        continue
            
            # 插入剩余数据
            if blueprints_batch:
                try:
                    await self.bulk_insert_via_sql(conn, 'industryBlueprints', blueprints_columns, blueprints_batch)
                    total_blueprints += len(blueprints_batch)
                    logger.debug(f"插入剩余 IndustryBlueprints 记录: {len(blueprints_batch)} 条")
                except Exception as e:
                    logger.error(f"插入剩余 IndustryBlueprints 记录失败: {e}")
                    raise
            
            if activities_batch:
                try:
                    await self.bulk_insert_via_sql(conn, 'industryActivities', activities_columns, activities_batch)
                    total_activities += len(activities_batch)
                    logger.debug(f"插入剩余 IndustryActivities 记录: {len(activities_batch)} 条")
                except Exception as e:
                    logger.error(f"插入剩余 IndustryActivities 记录失败: {e}")
                    raise
            
            if materials_batch:
                try:
                    await self.bulk_insert_via_sql(conn, 'industryActivityMaterials', materials_columns, materials_batch)
                    total_materials += len(materials_batch)
                    logger.debug(f"插入剩余 IndustryActivityMaterials 记录: {len(materials_batch)} 条")
                except Exception as e:
                    logger.error(f"插入剩余 IndustryActivityMaterials 记录失败: {e}")
                    raise
            
            if products_batch:
                try:
                    await self.bulk_insert_via_sql(conn, 'industryActivityProducts', products_columns, products_batch)
                    total_products += len(products_batch)
                    logger.debug(f"插入剩余 IndustryActivityProducts 记录: {len(products_batch)} 条")
                except Exception as e:
                    logger.error(f"插入剩余 IndustryActivityProducts 记录失败: {e}")
                    raise
            
            total_all = total_blueprints + total_activities + total_materials + total_products
            logger.info(f"蓝图表导入完成: {file_path}")
            logger.info(f"  IndustryBlueprints: {total_blueprints} 条记录")
            logger.info(f"  IndustryActivities: {total_activities} 条记录")
            logger.info(f"  IndustryActivityMaterials: {total_materials} 条记录")
            logger.info(f"  IndustryActivityProducts: {total_products} 条记录")
            logger.info(f"  总计: {total_all} 条记录")
            return total_all
        
        except Exception as e:
            logger.error(f"导入蓝图表失败: {file_path}, 错误: {e}")
            raise
    
    async def import_meta_groups(self, conn, file_path: str) -> int:
        """
        特殊处理：导入 MetaGroups 表数据
        
        Args:
            conn: 数据库连接
            file_path: metaGroups.jsonl 文件路径
        
        Returns:
            导入的记录数
        """
        import json
        
        logger.info(f"使用特殊处理导入 MetaGroups 表: {file_path}")
        
        table_name = 'metaGroups'
        columns = [
            'metaGroupID', 'nameID_en', 'nameID_zh', 'descriptionID_en', 'descriptionID_zh',
            'iconID', 'iconSuffix'
        ]
        
        batch = []
        total_count = 0
        line_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        # 解析原始 JSON
                        raw_row = json.loads(line)
                        
                        # 使用特殊处理函数处理数据
                        processed_row = process_meta_groups_row(raw_row)
                        
                        batch.append(processed_row)
                        line_count += 1
                        
                        # 达到批量大小时执行插入
                        if len(batch) >= self.batch_size:
                            await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                            total_count += len(batch)
                            batch = []
                            
                            if total_count % 50000 == 0:
                                logger.info(f"已导入 {total_count} 条记录到 {table_name}")
                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"第 {line_count + 1} 行 JSON 解析失败: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"第 {line_count + 1} 行处理失败: {e}")
                        continue
            
            # 插入剩余数据
            if batch:
                await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                total_count += len(batch)
            
            logger.info(f"MetaGroups 表导入完成: {file_path}, 共 {total_count} 条记录")
            return total_count
        
        except Exception as e:
            logger.error(f"导入 MetaGroups 表失败: {file_path}, 错误: {e}")
            raise
    
    async def import_inv_groups(self, conn, file_path: str) -> int:
        """
        特殊处理：导入 InvGroups 表数据
        
        Args:
            conn: 数据库连接
            file_path: groups.jsonl 文件路径
        
        Returns:
            导入的记录数
        """
        import json
        
        logger.info(f"使用特殊处理导入 InvGroups 表: {file_path}")
        
        table_name = 'invGroups'
        columns = [
            'groupID', 'categoryID', 'groupName_en', 'groupName_zh', 'iconID',
            'useBasePrice', 'anchored', 'anchorable', 'fittableNonSingleton', 'published'
        ]
        
        batch = []
        total_count = 0
        line_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        # 解析原始 JSON
                        raw_row = json.loads(line)
                        
                        # 使用特殊处理函数处理数据
                        processed_row = process_inv_groups_row(raw_row)
                        
                        batch.append(processed_row)
                        line_count += 1
                        
                        # 达到批量大小时执行插入
                        if len(batch) >= self.batch_size:
                            await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                            total_count += len(batch)
                            batch = []
                            
                            if total_count % 50000 == 0:
                                logger.info(f"已导入 {total_count} 条记录到 {table_name}")
                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"第 {line_count + 1} 行 JSON 解析失败: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"第 {line_count + 1} 行处理失败: {e}")
                        continue
            
            # 插入剩余数据
            if batch:
                await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                total_count += len(batch)
            
            logger.info(f"InvGroups 表导入完成: {file_path}, 共 {total_count} 条记录")
            return total_count
        
        except Exception as e:
            logger.error(f"导入 InvGroups 表失败: {file_path}, 错误: {e}")
            raise
    
    async def import_inv_categories(self, conn, file_path: str) -> int:
        """
        特殊处理：导入 InvCategories 表数据
        
        Args:
            conn: 数据库连接
            file_path: categories.jsonl 文件路径
        
        Returns:
            导入的记录数
        """
        import json
        
        logger.info(f"使用特殊处理导入 InvCategories 表: {file_path}")
        
        table_name = 'invCategories'
        columns = [
            'categoryID', 'categoryName_en', 'categoryName_zh', 'published', 'iconID'
        ]
        
        batch = []
        total_count = 0
        line_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        # 解析原始 JSON
                        raw_row = json.loads(line)
                        
                        # 使用特殊处理函数处理数据
                        processed_row = process_inv_categories_row(raw_row)
                        
                        batch.append(processed_row)
                        line_count += 1
                        
                        # 达到批量大小时执行插入
                        if len(batch) >= self.batch_size:
                            await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                            total_count += len(batch)
                            batch = []
                            
                            if total_count % 50000 == 0:
                                logger.info(f"已导入 {total_count} 条记录到 {table_name}")
                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"第 {line_count + 1} 行 JSON 解析失败: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"第 {line_count + 1} 行处理失败: {e}")
                        continue
            
            # 插入剩余数据
            if batch:
                await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                total_count += len(batch)
            
            logger.info(f"InvCategories 表导入完成: {file_path}, 共 {total_count} 条记录")
            return total_count
        
        except Exception as e:
            logger.error(f"导入 InvCategories 表失败: {file_path}, 错误: {e}")
            raise
    
    async def import_market_groups(self, conn, file_path: str) -> int:
        """
        特殊处理：导入 MarketGroups 表数据
        
        Args:
            conn: 数据库连接
            file_path: marketGroups.jsonl 文件路径
        
        Returns:
            导入的记录数
        """
        import json
        
        logger.info(f"使用特殊处理导入 MarketGroups 表: {file_path}")
        
        table_name = 'marketGroups'
        columns = [
            'marketGroupID', 'nameID_en', 'nameID_zh', 'descriptionID_en', 'descriptionID_zh',
            'hasTypes', 'iconID', 'parentGroupID'
        ]
        
        batch = []
        total_count = 0
        line_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        # 解析原始 JSON
                        raw_row = json.loads(line)
                        
                        # 使用特殊处理函数处理数据
                        processed_row = process_market_groups_row(raw_row)
                        
                        batch.append(processed_row)
                        line_count += 1
                        
                        # 达到批量大小时执行插入
                        if len(batch) >= self.batch_size:
                            await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                            total_count += len(batch)
                            batch = []
                            
                            if total_count % 50000 == 0:
                                logger.info(f"已导入 {total_count} 条记录到 {table_name}")
                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"第 {line_count + 1} 行 JSON 解析失败: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"第 {line_count + 1} 行处理失败: {e}")
                        continue
            
            # 插入剩余数据
            if batch:
                await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                total_count += len(batch)
            
            logger.info(f"MarketGroups 表导入完成: {file_path}, 共 {total_count} 条记录")
            return total_count
        
        except Exception as e:
            logger.error(f"导入 MarketGroups 表失败: {file_path}, 错误: {e}")
            raise
    
    async def import_map_solar_systems(self, conn, file_path: str) -> int:
        """
        特殊处理：导入 MapSolarSystems 表数据
        
        Args:
            conn: 数据库连接
            file_path: mapSolarSystems.jsonl 文件路径
        
        Returns:
            导入的记录数
        """
        import json
        
        logger.info(f"使用特殊处理导入 MapSolarSystems 表: {file_path}")
        
        table_name = 'mapSolarSystems'
        columns = [
            'solarSystemID', 'solarSystemName_en', 'solarSystemName_zh', 'regionID', 'constellationID',
            'x', 'y', 'z', 'luminosity', 'border', 'hub', 'international', 'regional',
            'security', 'radius', 'sunTypeID', 'securityClass'
        ]
        
        batch = []
        total_count = 0
        line_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        # 解析原始 JSON
                        raw_row = json.loads(line)
                        
                        # 使用特殊处理函数处理数据
                        processed_row = process_map_solar_systems_row(raw_row)
                        
                        batch.append(processed_row)
                        line_count += 1
                        
                        # 达到批量大小时执行插入
                        if len(batch) >= self.batch_size:
                            await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                            total_count += len(batch)
                            batch = []
                            
                            if total_count % 50000 == 0:
                                logger.info(f"已导入 {total_count} 条记录到 {table_name}")
                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"第 {line_count + 1} 行 JSON 解析失败: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"第 {line_count + 1} 行处理失败: {e}")
                        continue
            
            # 插入剩余数据
            if batch:
                await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                total_count += len(batch)
            
            logger.info(f"MapSolarSystems 表导入完成: {file_path}, 共 {total_count} 条记录")
            return total_count
        
        except Exception as e:
            logger.error(f"导入 MapSolarSystems 表失败: {file_path}, 错误: {e}")
            raise
    
    async def import_map_regions(self, conn, file_path: str) -> int:
        """
        特殊处理：导入 MapRegions 表数据
        
        Args:
            conn: 数据库连接
            file_path: mapRegions.jsonl 文件路径
        
        Returns:
            导入的记录数
        """
        import json
        
        logger.info(f"使用特殊处理导入 MapRegions 表: {file_path}")
        
        table_name = 'mapRegions'
        columns = [
            'regionID', 'regionName_en', 'regionName_zh', 'x', 'y', 'z',
            'factionID', 'nameID_en', 'nameID_zh', 'descriptionID_en', 'descriptionID_zh'
        ]
        
        batch = []
        total_count = 0
        line_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        # 解析原始 JSON
                        raw_row = json.loads(line)
                        
                        # 使用特殊处理函数处理数据
                        processed_row = process_map_regions_row(raw_row)
                        
                        batch.append(processed_row)
                        line_count += 1
                        
                        # 达到批量大小时执行插入
                        if len(batch) >= self.batch_size:
                            await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                            total_count += len(batch)
                            batch = []
                            
                            if total_count % 50000 == 0:
                                logger.info(f"已导入 {total_count} 条记录到 {table_name}")
                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"第 {line_count + 1} 行 JSON 解析失败: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"第 {line_count + 1} 行处理失败: {e}")
                        continue
            
            # 插入剩余数据
            if batch:
                await self.bulk_insert_via_sql(conn, table_name, columns, batch)
                total_count += len(batch)
            
            logger.info(f"MapRegions 表导入完成: {file_path}, 共 {total_count} 条记录")
            return total_count
        
        except Exception as e:
            logger.error(f"导入 MapRegions 表失败: {file_path}, 错误: {e}")
            raise
    
    async def full_update(self, extract_dir: str) -> bool:
        """
        执行全量更新
        
        Args:
            extract_dir: 解压目录
        
        Returns:
            是否成功
        """
        logger.info("开始执行全量更新")
        
        # 获取需要导入的文件列表
        files_to_parse = self.parser.get_files_to_parse(extract_dir)
        
        # 检查是否包含 blueprints.jsonl
        blueprints_found = any('blueprints.jsonl' in f for f in files_to_parse)
        if not blueprints_found:
            logger.warning("警告: blueprints.jsonl 不在文件列表中，蓝图数据将不会被导入")
            logger.warning("请检查 config.toml 中的 Parse_Whitelist 是否包含 'blueprints'")
        else:
            logger.info("检测到 blueprints.jsonl，将使用特殊处理导入蓝图表")
        
        if not files_to_parse:
            logger.warning("没有找到需要导入的文件")
            return False
        
        logger.info(f"准备导入 {len(files_to_parse)} 个文件: {[os.path.basename(f) for f in files_to_parse]}")
        
        # 检查数据库引擎是否已初始化
        if not self.db_manager.engine:
            logger.error("数据库引擎未初始化，请先调用 init_database()")
            return False
        
        # 开始事务
        async with self.db_manager.engine.begin() as conn:
            try:
                # 阶段一：准备阶段
                current_version = await self.get_current_version()
                logger.info(f"当前数据库版本: {current_version}")
                
                # 阶段二：数据清理阶段
                logger.info("开始清理旧数据")
                
                # 尝试禁用外键约束
                fk_disabled = await self.disable_foreign_keys(conn)
                
                # 清空所有表（除了 _sde，它会在最后处理）
                tables_to_clear = []
                for file_path in files_to_parse:
                    filename = os.path.basename(file_path)
                    table_name = os.path.splitext(filename)[0]
                    if table_name != '_sde':
                        # 特殊处理：types.jsonl -> invTypes 表
                        if table_name == 'types':
                            table_name = 'invTypes'
                            tables_to_clear.append(table_name)
                        # 特殊处理：blueprints.jsonl -> 4个蓝图表
                        elif table_name == 'blueprints':
                            tables_to_clear.extend([
                                'industryBlueprints',
                                'industryActivities',
                                'industryActivityMaterials',
                                'industryActivityProducts'
                            ])
                        else:
                            tables_to_clear.append(table_name)
                
                # 清空表
                for table_name in tables_to_clear:
                    await self.truncate_table(conn, table_name)
                
                # 清空 _sde 表
                await self.truncate_table(conn, '_sde')
                
                # 阶段三：创建表结构（如果不存在）
                logger.info("检查并创建表结构")
                await self.model_generator.create_all_tables(conn, extract_dir)
                
                # 阶段四：数据导入阶段
                logger.info("开始导入新数据")
                
                # 先导入 _sde 表（版本信息）
                for file_path in files_to_parse:
                    filename = os.path.basename(file_path)
                    table_name = os.path.splitext(filename)[0]
                    if table_name == '_sde':
                        await self.import_file(conn, file_path, table_name)
                        break
                
                # 导入其他表
                for file_path in files_to_parse:
                    filename = os.path.basename(file_path)
                    table_name = os.path.splitext(filename)[0]
                    if table_name != '_sde':
                        # 特殊处理：types.jsonl -> invTypes 表
                        if table_name == 'types':
                            table_name = 'invTypes'
                        # 注意：blueprints.jsonl 保持原样，在 import_file 中会特殊处理
                        logger.debug(f"准备导入文件: {filename} -> 表名: {table_name}")
                        await self.import_file(conn, file_path, table_name)
                
                # 阶段五：验证和提交阶段
                logger.info("验证数据完整性")
                
                # 重新启用外键约束
                if fk_disabled:
                    await self.enable_foreign_keys(conn)
                
                # 验证关键表是否有数据
                result = await conn.execute(text('SELECT COUNT(*) FROM "_sde"'))
                count = result.scalar()
                if count == 0:
                    raise Exception("_sde 表没有数据，更新失败")
                
                logger.info("全量更新完成，提交事务")
                # 事务会在 with 块结束时自动提交
                return True
            
            except Exception as e:
                logger.error(f"全量更新失败: {e}")
                # 事务会自动回滚
                raise

