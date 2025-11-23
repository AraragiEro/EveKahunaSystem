"""
MapRegions 表模型和特殊处理
"""
from sqlalchemy import Column, Integer, Float, Text
from .database_manager import SDEModel


class MapRegions(SDEModel):
    """MapRegions 表模型 - 星域信息"""
    __tablename__ = 'mapRegions'
    
    regionID = Column(Integer, primary_key=True, index=True)  # mapRegions.jsonl._key
    regionName_en = Column(Text, nullable=True)  # mapRegions.jsonl.name.en
    regionName_zh = Column(Text, nullable=True)  # mapRegions.jsonl.name.zh
    x = Column(Float, nullable=True)  # mapRegions.jsonl.position.x
    y = Column(Float, nullable=True)  # mapRegions.jsonl.position.y
    z = Column(Float, nullable=True)  # mapRegions.jsonl.position.z
    factionID = Column(Integer, nullable=True)  # mapRegions.jsonl.factionID
    nameID_en = Column(Text, nullable=True)  # mapRegions.jsonl.name.en
    nameID_zh = Column(Text, nullable=True)  # mapRegions.jsonl.name.zh
    descriptionID_en = Column(Text, nullable=True)  # mapRegions.jsonl.description.en
    descriptionID_zh = Column(Text, nullable=True)  # mapRegions.jsonl.description.zh


def process_map_regions_row(row: dict) -> dict:
    """
    处理 MapRegions 表的单行数据
    
    Args:
        row: 从 JSONL 解析的原始数据
    
    Returns:
        处理后的数据字典，可以直接用于数据库插入
    """
    processed = {
        'regionID': row.get('_key'),
        'factionID': row.get('factionID'),
    }
    
    # 处理多语言字段 name
    name_dict = row.get('name')
    if isinstance(name_dict, dict):
        processed['regionName_en'] = name_dict.get('en')
        processed['regionName_zh'] = name_dict.get('zh')
        # nameID 与 regionName 相同
        processed['nameID_en'] = name_dict.get('en')
        processed['nameID_zh'] = name_dict.get('zh')
    else:
        processed['regionName_en'] = None
        processed['regionName_zh'] = None
        processed['nameID_en'] = None
        processed['nameID_zh'] = None
    
    # 处理嵌套对象 position，提取 x, y, z
    position_dict = row.get('position')
    if isinstance(position_dict, dict):
        processed['x'] = position_dict.get('x')
        processed['y'] = position_dict.get('y')
        processed['z'] = position_dict.get('z')
    else:
        processed['x'] = None
        processed['y'] = None
        processed['z'] = None
    
    # 处理多语言字段 description（可能不存在）
    description_dict = row.get('description')
    if isinstance(description_dict, dict):
        processed['descriptionID_en'] = description_dict.get('en')
        processed['descriptionID_zh'] = description_dict.get('zh')
    else:
        processed['descriptionID_en'] = None
        processed['descriptionID_zh'] = None
    
    return processed

