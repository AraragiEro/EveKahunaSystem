"""
MetaGroups 表模型和特殊处理
"""
from sqlalchemy import Column, Integer, Text
from .database_manager import SDEModel


class MetaGroups(SDEModel):
    """MetaGroups 表模型 - 元组ID信息"""
    __tablename__ = 'metaGroups'
    
    metaGroupID = Column(Integer, primary_key=True, index=True)  # metaGroups.jsonl._key
    nameID_en = Column(Text, nullable=True)  # metaGroups.jsonl.name.en
    nameID_zh = Column(Text, nullable=True)  # metaGroups.jsonl.name.zh
    descriptionID_en = Column(Text, nullable=True)  # metaGroups.jsonl.description.en
    descriptionID_zh = Column(Text, nullable=True)  # metaGroups.jsonl.description.zh
    iconID = Column(Integer, nullable=True)  # metaGroups.jsonl.iconID
    iconSuffix = Column(Text, nullable=True)  # metaGroups.jsonl.iconSuffix


def process_meta_groups_row(row: dict) -> dict:
    """
    处理 MetaGroups 表的单行数据
    
    Args:
        row: 从 JSONL 解析的原始数据
    
    Returns:
        处理后的数据字典，可以直接用于数据库插入
    """
    processed = {
        'metaGroupID': row.get('_key'),
        'iconID': row.get('iconID'),
        'iconSuffix': row.get('iconSuffix'),
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
    
    return processed

