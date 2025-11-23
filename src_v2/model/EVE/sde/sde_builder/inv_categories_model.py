"""
InvCategories 表模型和特殊处理
"""
from sqlalchemy import Column, Integer, Text
from .database_manager import SDEModel


class InvCategories(SDEModel):
    """InvCategories 表模型 - 属性ID对应"""
    __tablename__ = 'invCategories'
    
    categoryID = Column(Integer, primary_key=True, index=True)  # categories.jsonl._key
    categoryName_en = Column(Text, nullable=True)  # categories.jsonl.name.en
    categoryName_zh = Column(Text, nullable=True)  # categories.jsonl.name.zh
    published = Column(Integer, nullable=True)  # categories.jsonl.published (布尔值转换为整数)
    iconID = Column(Integer, nullable=True)  # categories.jsonl.iconID


def process_inv_categories_row(row: dict) -> dict:
    """
    处理 InvCategories 表的单行数据
    
    Args:
        row: 从 JSONL 解析的原始数据
    
    Returns:
        处理后的数据字典，可以直接用于数据库插入
    """
    processed = {
        'categoryID': row.get('_key'),
        'iconID': row.get('iconID'),
    }
    
    # 处理多语言字段 name
    name_dict = row.get('name')
    if isinstance(name_dict, dict):
        processed['categoryName_en'] = name_dict.get('en')
        processed['categoryName_zh'] = name_dict.get('zh')
    else:
        processed['categoryName_en'] = None
        processed['categoryName_zh'] = None
    
    # 处理布尔值字段，转换为整数
    def bool_to_int(value):
        if isinstance(value, bool):
            return 1 if value else 0
        return value
    
    processed['published'] = bool_to_int(row.get('published'))
    
    return processed

