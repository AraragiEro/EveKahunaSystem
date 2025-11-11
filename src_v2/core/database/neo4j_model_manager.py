"""
Neo4j 模型管理器 - 负责创建索引和管理模型

支持的索引类型：
1. 单属性索引:
   在模型的 get_indexes() 方法中返回：
   {"property": "property_name", "type": "RANGE"}

2. 复合索引:
   在模型的 get_indexes() 方法中返回：
   {"properties": ["prop1", "prop2", ...], "type": "COMPOSITE"}
   
   示例：
   @classmethod
   def get_indexes(cls) -> List[Dict[str, Any]]:
       return [
           {"property": "id", "type": "RANGE"},  # 单属性索引
           {"properties": ["owner_id", "item_id"], "type": "COMPOSITE"},  # 复合索引
       ]

注意：
- 复合索引要求至少2个属性
- 索引不能保证唯一性，需要在应用层通过 MERGE 语句确保唯一性（不要使用 CREATE）
- 所有约束相关功能已移除，使用索引替代
"""
from typing import List, Type, Dict, Any, TYPE_CHECKING
from .neo4j_models import NodeModel
from .connect_manager import neo4j_manager
from ..log import logger

if TYPE_CHECKING:
    from .neo4j_models import RelationshipType


class Neo4jModelManager:
    """Neo4j 模型管理器"""
    
    def __init__(self):
        self.registered_models: List[Type[NodeModel]] = []
    
    def register_model(self, model_class: Type[NodeModel]):
        """注册模型类"""
        if model_class not in self.registered_models:
            self.registered_models.append(model_class)
            logger.info(f"注册 Neo4j 模型: {model_class.__name__}")
    
    def register_models(self, *model_classes: Type[NodeModel]):
        """批量注册模型"""
        for model_class in model_classes:
            self.register_model(model_class)
    
    async def create_indexes(self):
        """创建所有模型的索引"""
        async with neo4j_manager.get_transaction() as tx:
            for model_class in self.registered_models:
                await self._create_model_indexes(tx, model_class)
    
    async def _create_model_indexes(self, tx, model_class: Type[NodeModel]):
        """创建单个模型的索引
        
        Args:
            tx: 事务对象
            model_class: 模型类
        """
        labels_list = model_class.get_labels()
        # Neo4j 索引语法不支持多标签，使用第一个标签（主标签）
        primary_label = labels_list[0] if labels_list else model_class.__name__
        indexes = model_class.get_indexes()
        
        for index_def in indexes:
            index_type = index_def.get("type", "RANGE")
            
            # 处理单属性索引
            if "property" in index_def:
                property_name = index_def["property"]
                index_name = f"{primary_label.lower()}_{property_name}_index"
                
                query = f"""
                CREATE INDEX {index_name} IF NOT EXISTS
                FOR (n:{primary_label})
                ON (n.{property_name})
                """
                
                try:
                    await tx.run(query)
                    logger.info(f"创建索引: {index_name} 在 {primary_label}.{property_name}")
                except Exception as e:
                    logger.warning(f"创建索引失败 {index_name}: {e}")
            
            # 处理复合索引
            elif "properties" in index_def and index_type == "COMPOSITE":
                properties = index_def["properties"]
                if not isinstance(properties, list) or len(properties) < 2:
                    logger.warning(f"复合索引需要至少2个属性，跳过: {properties}")
                    continue
                
                props_str = "_".join(properties)
                index_name = f"{primary_label.lower()}_{props_str}_composite_index"
                props_cypher = ", ".join([f"n.{prop}" for prop in properties])
                
                query = f"""
                CREATE INDEX {index_name} IF NOT EXISTS
                FOR (n:{primary_label})
                ON ({props_cypher})
                """
                
                try:
                    await tx.run(query)
                    logger.info(f"创建复合索引: {index_name} 在 {primary_label}({', '.join(properties)})")
                except Exception as e:
                    logger.warning(f"创建复合索引失败 {index_name}: {e}")
    
    async def drop_all_constraints(self):
        """删除所有约束（谨慎使用）"""
        async with neo4j_manager.get_session() as session:
            query = "SHOW CONSTRAINTS"
            result = await session.run(query)
            
            constraints = []
            async for record in result:
                constraints.append(record["name"])
            
            async with neo4j_manager.get_transaction() as tx:
                for constraint_name in constraints:
                    try:
                        await tx.run(f"DROP CONSTRAINT {constraint_name} IF EXISTS")
                        logger.info(f"删除约束: {constraint_name}")
                    except Exception as e:
                        logger.warning(f"删除约束失败 {constraint_name}: {e}")
    
    async def drop_all_indexes(self):
        """删除所有索引（谨慎使用）"""
        async with neo4j_manager.get_session() as session:
            query = "SHOW INDEXES"
            result = await session.run(query)
            
            indexes = []
            async for record in result:
                indexes.append(record["name"])
            
            async with neo4j_manager.get_transaction() as tx:
                for index_name in indexes:
                    try:
                        await tx.run(f"DROP INDEX {index_name} IF EXISTS")
                        logger.info(f"删除索引: {index_name}")
                    except Exception as e:
                        logger.warning(f"删除索引失败 {index_name}: {e}")
    
    async def create_relationship_indexes(self):
        """创建所有关系的索引"""
        from .neo4j_models import RelationshipType
        
        # 从 RelationshipType 获取索引定义
        relationship_indexes = RelationshipType.get_indexes()
        
        async with neo4j_manager.get_transaction() as tx:
            for rel_type, indexes in relationship_indexes.items():
                await self._create_relationship_indexes(tx, rel_type, indexes)
    
    async def _create_relationship_indexes(self, tx, rel_type: 'RelationshipType', indexes: List[Dict[str, Any]]):
        """创建单个关系类型的索引
        
        Args:
            tx: 事务对象
            rel_type: 关系类型
            indexes: 索引定义列表
        """
        rel_type_str = rel_type.value
        
        for index_def in indexes:
            index_type = index_def.get("type", "RANGE")
            
            # 处理单属性关系索引
            if "property" in index_def:
                property_name = index_def["property"]
                index_name = f"{rel_type_str.lower()}_{property_name}_rel_index"
                
                query = f"""
                CREATE INDEX {index_name} IF NOT EXISTS
                FOR ()-[r:{rel_type_str}]-()
                ON (r.{property_name})
                """
                
                try:
                    await tx.run(query)
                    logger.info(f"创建关系索引: {index_name} 在 {rel_type_str}.{property_name}")
                except Exception as e:
                    logger.warning(f"创建关系索引失败 {index_name}: {e}")
            
            # 处理复合关系索引
            elif "properties" in index_def and index_type == "COMPOSITE":
                properties = index_def["properties"]
                if not isinstance(properties, list) or len(properties) < 2:
                    logger.warning(f"复合关系索引需要至少2个属性，跳过: {properties}")
                    continue
                
                props_str = "_".join(properties)
                index_name = f"{rel_type_str.lower()}_{props_str}_rel_composite_index"
                props_cypher = ", ".join([f"r.{prop}" for prop in properties])
                
                query = f"""
                CREATE INDEX {index_name} IF NOT EXISTS
                FOR ()-[r:{rel_type_str}]-()
                ON ({props_cypher})
                """
                
                try:
                    await tx.run(query)
                    logger.info(f"创建复合关系索引: {index_name} 在 {rel_type_str}({', '.join(properties)})")
                except Exception as e:
                    logger.warning(f"创建复合关系索引失败 {index_name}: {e}")
    
    async def init_schema(self):
        """初始化数据库模式（创建所有索引）"""
        logger.info("开始初始化 Neo4j 数据库模式...")
        
        # 创建所有节点索引（包括单属性索引和复合索引）
        await self.create_indexes()
        
        # 创建所有关系索引
        await self.create_relationship_indexes()
        
        logger.info("Neo4j 数据库模式初始化完成")


# 全局模型管理器实例
neo4j_model_manager = Neo4jModelManager()

# 注册所有模型
from .neo4j_models import (
    Asset, SolarSystem, Station, Structure,
    Plan, Blueprint, PlanBlueprint,
    MarketGroup, Type
)

neo4j_model_manager.register_models(
    Asset, SolarSystem, Station, Structure,
    Plan, Blueprint, PlanBlueprint,
    MarketGroup, Type
)


