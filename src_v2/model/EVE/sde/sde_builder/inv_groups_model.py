"""
InvGroups 表模型和特殊处理
"""
from sqlalchemy import Column, Integer, Text
from .database_manager import SDEModel


class InvGroups(SDEModel):
    """InvGroups 表模型 - 组ID对应"""
    __tablename__ = 'invGroups'
    
    groupID = Column(Integer, primary_key=True, index=True)  # groups.jsonl._key
    categoryID = Column(Integer, nullable=True)  # groups.jsonl.categoryID
    groupName_en = Column(Text, nullable=True)  # groups.jsonl.name.en
    groupName_zh = Column(Text, nullable=True)  # groups.jsonl.name.zh
    iconID = Column(Integer, nullable=True)  # groups.jsonl.iconID
    useBasePrice = Column(Integer, nullable=True)  # groups.jsonl.useBasePrice (布尔值转换为整数)
    anchored = Column(Integer, nullable=True)  # groups.jsonl.anchored (布尔值转换为整数)
    anchorable = Column(Integer, nullable=True)  # groups.jsonl.anchorable (布尔值转换为整数)
    fittableNonSingleton = Column(Integer, nullable=True)  # groups.jsonl.fittableNonSingleton (布尔值转换为整数)
    published = Column(Integer, nullable=True)  # groups.jsonl.published (布尔值转换为整数)


def process_inv_groups_row(row: dict) -> dict:
    """
    处理 InvGroups 表的单行数据
    
    Args:
        row: 从 JSONL 解析的原始数据
    
    Returns:
        处理后的数据字典，可以直接用于数据库插入
    """
    processed = {
        'groupID': row.get('_key'),
        'categoryID': row.get('categoryID'),
        'iconID': row.get('iconID'),
    }
    
    # 处理多语言字段 name
    name_dict = row.get('name')
    if isinstance(name_dict, dict):
        processed['groupName_en'] = name_dict.get('en')
        processed['groupName_zh'] = name_dict.get('zh')
    else:
        processed['groupName_en'] = None
        processed['groupName_zh'] = None
    
    # 处理布尔值字段，转换为整数
    def bool_to_int(value):
        if isinstance(value, bool):
            return 1 if value else 0
        return value
    
    processed['useBasePrice'] = bool_to_int(row.get('useBasePrice'))
    processed['anchored'] = bool_to_int(row.get('anchored'))
    processed['anchorable'] = bool_to_int(row.get('anchorable'))
    processed['fittableNonSingleton'] = bool_to_int(row.get('fittableNonSingleton'))
    processed['published'] = bool_to_int(row.get('published'))
    
    return processed

