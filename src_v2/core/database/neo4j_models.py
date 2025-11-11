"""
Neo4j 数据模型定义
使用 Python 类定义节点和关系的结构，类似于 SQLAlchemy 的模型定义方式
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


# ==================== 节点模型基类 ====================

class NodeModel:
    """节点模型基类"""
    
    @classmethod
    def get_labels(cls) -> List[str]:
        """获取节点标签列表"""
        return [cls.__name__]
    
    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        """获取索引定义"""
        return []
    
    @classmethod
    def get_constraints(cls) -> List[Dict[str, Any]]:
        """获取约束定义"""
        return []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 Neo4j 创建）"""
        result = {}
        for k, v in self.__dict__.items():
            if v is not None:
                # 处理 datetime 对象
                if isinstance(v, datetime):
                    result[k] = v.isoformat()
                else:
                    result[k] = v
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """从字典创建实例"""
        return cls(**data)


# ==================== Asset 相关节点模型 ====================

@dataclass
class Asset(NodeModel):
    """资产节点
    
    唯一性约束说明：
    - (owner_id, item_id) 组合必须唯一
    - 在 Neo4j Enterprise Edition 中会创建 NODE KEY 约束（数据库层面强制唯一性）
    - 在 Neo4j Community Edition 中会创建复合索引（应用层通过 MERGE 确保唯一性）
    - 所有创建 Asset 的操作必须使用 MERGE 而不是 CREATE
    """
    owner_type: str
    owner_id: int
    item_id: int
    is_blueprint_copy: bool = False
    is_singleton: bool = False
    location_flag: Optional[str] = None
    location_id: Optional[int] = None
    location_type: Optional[str] = None
    quantity: Optional[int] = None
    type_id: Optional[int] = None
    
    @classmethod
    def get_labels(cls) -> List[str]:
        return ["Asset"]
    
    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        """获取索引定义
        
        注意：使用复合索引替代 NODE_KEY 约束，确保 (owner_id, item_id) 的唯一性
        需要在应用层通过 MERGE 语句确保唯一性
        """
        return [
            {"property": "type_id", "type": "RANGE"},
            {"property": "owner_id", "type": "RANGE"},
            {"property": "location_type", "type": "RANGE"},
            {"properties": ["owner_id", "item_id"], "type": "COMPOSITE"}  # 复合索引替代 NODE_KEY 约束
        ]
    
    @classmethod
    def get_constraints(cls) -> List[Dict[str, Any]]:
        """获取约束定义（已废弃，使用索引替代）"""
        return []

@dataclass
class SolarSystem(NodeModel):
    """星系节点"""
    solar_system_id: int
    solar_system_name: Optional[str] = None
    region_id: Optional[int] = None
    region_name: Optional[str] = None
    
    @classmethod
    def get_labels(cls) -> List[str]:
        return ["SolarSystem"]
    
    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        return [
            {"property": "solar_system_id", "type": "RANGE"},
        ]
    
    @classmethod
    def get_constraints(cls) -> List[Dict[str, Any]]:
        """获取约束定义（已废弃，使用索引替代）"""
        return []

@dataclass
class Station(NodeModel):
    """空间站节点"""
    station_id: int
    station_name: Optional[str] = None
    
    @classmethod
    def get_labels(cls) -> List[str]:
        return ["Station"]

    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        return [
            {"property": "station_id", "type": "RANGE"},
        ]
    
    @classmethod
    def get_constraints(cls) -> List[Dict[str, Any]]:
        """获取约束定义（已废弃，使用索引替代）"""
        return []

@dataclass
class Structure(NodeModel):
    """结构节点"""
    structure_id: int
    structure_name: Optional[str] = None
    
    @classmethod
    def get_labels(cls) -> List[str]:
        return ["Structure"]
    
    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        return [
            {"property": "structure_id", "type": "RANGE"},
        ]
    
    @classmethod
    def get_constraints(cls) -> List[Dict[str, Any]]:
        """获取约束定义（已废弃，使用索引替代）"""
        return []

# ==================== 工业制造相关节点模型 ====================

@dataclass
class Plan(NodeModel):
    """计划节点"""
    user_name: str
    plan_name: str
    
    @classmethod
    def get_labels(cls) -> List[str]:
        return ["Plan"]
    
    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        return [
            {"property": "plan_name", "type": "RANGE"},
            {"property": "user_name", "type": "RANGE"},
        ]

@dataclass
class Blueprint(NodeModel):
    """蓝图节点"""
    type_id: int
    type_name: Optional[str] = None
    bp_type_id: Optional[int] = None
    bp_type_name: Optional[str] = None

    
    @classmethod
    def get_labels(cls) -> List[str]:
        return ["Blueprint"]
    
    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        return [
            {"property": "type_id", "type": "RANGE"}
        ]
    
    @classmethod
    def get_constraints(cls) -> List[Dict[str, Any]]:
        """获取约束定义（已废弃，使用索引替代）"""
        return []

@dataclass
class PlanBlueprint(NodeModel):
    """计划蓝图节点"""
    user_name: str
    plan_name: str
    type_id: int
    type_name: Optional[str] = None
    bp_type_id: Optional[int] = None
    bp_type_name: Optional[str] = None

    
    @classmethod
    def get_labels(cls) -> List[str]:
        return ["PlanBlueprint"]
    
    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        return [
            {"property": "user_name", "type": "RANGE"},
            {"property": "plan_name", "type": "RANGE"},
            {"property": "type_id", "type": "RANGE"}
        ]
    
    @classmethod
    def get_constraints(cls) -> List[Dict[str, Any]]:
        """获取约束定义（已废弃，使用索引替代）"""
        return []

# =================== 市场树型图 ===================
class MarketGroup(NodeModel):
    """市场组节点"""
    market_group_id: int
    market_group_name: Optional[str] = None
    market_group_name_cn: Optional[str] = None

    @classmethod
    def get_labels(cls) -> List[str]:
        return ["MarketGroup"]
    
    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        return [
            {"property": "market_group_id", "type": "RANGE"},
        ]

class Type(NodeModel):
    """类型节点"""
    type_id: int
    type_name: Optional[str] = None
    type_name_zh: Optional[str] = None

    meta_group_name: Optional[str] = None
    
    category_name: Optional[str] = None
    category_name_zh: Optional[str] = None
    
    @classmethod
    def get_labels(cls) -> List[str]:
        return ["Type"]

    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        return [
            {"property": "type_id", "type": "RANGE"},
        ]

# ==================== 关系定义 ====================

class RelationshipType(Enum):
    """关系类型枚举"""
    # Asset 关系
    LOCATED_IN = "LOCATED_IN"
    OWNED_BY = "OWNED_BY"
    IS_TYPE = "IS_TYPE"
    CONTAINS = "CONTAINS"
    IN_SYSTEM = "IN_SYSTEM"
    
    # 工业制造关系
    BP_DEPEND_ON = "BP_DEPEND_ON"
    PLAN_BP_DEPEND_ON = "PLAN_BP_DEPEND_ON"
    
    # EVE数据库关系
    EVE_MARKET_GROUP = "EVE_MARKET_GROUP"
    
    @classmethod
    def get_indexes(cls) -> Dict[Any, List[Dict[str, Any]]]:
        """获取所有关系类型的索引定义
        
        Returns:
            Dict[RelationshipType, List[Dict]]: 关系类型到索引定义列表的映射
        """
        return {
            cls.BP_DEPEND_ON: [
                {"property": "product", "type": "RANGE"},
                {"property": "material", "type": "RANGE"},
                # 如果需要复合索引：
                # {"properties": ["quantity", "unit_cost"], "type": "COMPOSITE"}
            ],
            cls.PLAN_BP_DEPEND_ON: [
                {"property": "user_name", "type": "RANGE"},
                {"property": "plan_name", "type": "RANGE"},
                {"property": "product", "type": "RANGE"},
                {"property": "material", "type": "RANGE"},  
                {"property": "index_id", "type": "RANGE"},
            ]
            # 可以添加其他关系类型的索引
            # cls.LOCATED_IN: [
            #     {"property": "distance", "type": "RANGE"}
            # ],
        }


@dataclass
class Relationship:
    """关系定义"""
    type: RelationshipType
    properties: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        """获取关系索引定义（可选）"""
        return []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "type": self.type.value,
            "properties": self.properties
        }


