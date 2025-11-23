"""
MarketGroups 表模型和特殊处理
"""
from sqlalchemy import Column, Integer, Text
from .database_manager import SDEModel


class MarketGroups(SDEModel):
    """MarketGroups 表模型 - 市场组ID信息"""
    __tablename__ = 'marketGroups'
    
    marketGroupID = Column(Integer, primary_key=True, index=True)  # marketGroups.jsonl._key
    nameID_en = Column(Text, nullable=True)  # marketGroups.jsonl.name.en
    nameID_zh = Column(Text, nullable=True)  # marketGroups.jsonl.name.zh
    descriptionID_en = Column(Text, nullable=True)  # marketGroups.jsonl.description.en
    descriptionID_zh = Column(Text, nullable=True)  # marketGroups.jsonl.description.zh
    hasTypes = Column(Integer, nullable=True)  # marketGroups.jsonl.hasTypes (布尔值转换为整数)
    iconID = Column(Integer, nullable=True)  # marketGroups.jsonl.iconID
    parentGroupID = Column(Integer, nullable=True)  # marketGroups.jsonl.parentGroupID


def process_market_groups_row(row: dict) -> dict:
    """
    处理 MarketGroups 表的单行数据
    
    Args:
        row: 从 JSONL 解析的原始数据
    
    Returns:
        处理后的数据字典，可以直接用于数据库插入
    """
    processed = {
        'marketGroupID': row.get('_key'),
        'iconID': row.get('iconID'),
        'parentGroupID': row.get('parentGroupID'),
    }
    
    # 处理多语言字段 name
    name_dict = row.get('name')
    if isinstance(name_dict, dict):
        processed['nameID_en'] = name_dict.get('en')
        processed['nameID_zh'] = name_dict.get('zh')
    else:
        processed['nameID_en'] = None
        processed['nameID_zh'] = None
    
    # 处理多语言字段 description（可能不存在）
    description_dict = row.get('description')
    if isinstance(description_dict, dict):
        processed['descriptionID_en'] = description_dict.get('en')
        processed['descriptionID_zh'] = description_dict.get('zh')
    else:
        processed['descriptionID_en'] = None
        processed['descriptionID_zh'] = None
    
    # 处理布尔值字段，转换为整数
    def bool_to_int(value):
        if isinstance(value, bool):
            return 1 if value else 0
        return value
    
    processed['hasTypes'] = bool_to_int(row.get('hasTypes'))
    
    return processed

