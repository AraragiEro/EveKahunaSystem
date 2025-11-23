"""
InvTypes 表模型和特殊处理
"""
from sqlalchemy import Column, Integer, Float, Text
from .database_manager import SDEModel
from .sde_config import GROUP_ID_PACKAGED_VOLUME, TYPE_ID_PACKAGE_VOLUME


class InvTypes(SDEModel):
    """InvTypes 表模型 - 所有物品类型信息"""
    __tablename__ = 'invTypes'
    
    typeID = Column(Integer, primary_key=True, index=True)  # types.jsonl._key
    groupID = Column(Integer, nullable=True)  # types.jsonl.groupID
    typeName_en = Column(Text, nullable=True, index=True)  # types.jsonl.name.en
    typeName_zh = Column(Text, nullable=True, index=True)  # types.jsonl.name.zh
    description_en = Column(Text, nullable=True)  # types.jsonl.description.en
    description_zh = Column(Text, nullable=True)  # types.jsonl.description.zh
    mass = Column(Float, nullable=True)  # types.jsonl.mass
    volume = Column(Float, nullable=True)  # types.jsonl.volume
    packagedVolume = Column(Float, nullable=True)  # 需要计算
    capacity = Column(Float, nullable=True)  # types.jsonl.capacity
    portionSize = Column(Integer, nullable=True)  # types.jsonl.portionSize
    factionID = Column(Integer, nullable=True)  # types.jsonl.factionID
    raceID = Column(Integer, nullable=True)  # types.jsonl.raceID
    basePrice = Column(Float, nullable=True)  # types.jsonl.basePrice
    published = Column(Integer, nullable=True)  # types.jsonl.published (布尔值转换为整数)
    marketGroupID = Column(Integer, nullable=True)  # types.jsonl.marketGroupID
    graphicID = Column(Integer, nullable=True)  # types.jsonl.graphicID
    radius = Column(Float, nullable=True)  # types.jsonl.radius
    iconID = Column(Integer, nullable=True)  # types.jsonl.iconID
    soundID = Column(Integer, nullable=True)  # types.jsonl.soundID
    sofFactionName = Column(Text, nullable=True)  # types.jsonl.sofFactionName
    sofMaterialSetID = Column(Integer, nullable=True)  # types.jsonl.sofMaterialSetID
    metaGroupID = Column(Integer, nullable=True)  # types.jsonl.metaGroupID
    variationparentTypeID = Column(Integer, nullable=True)  # types.jsonl.variationparentTypeID


def calculate_packaged_volume(type_id: int, group_id: int = None, volume: float = None) -> float:
    """
    计算 packagedVolume
    
    优先级：
    1. 如果存在于 TYPE_ID_PACKAGE_VOLUME 字典，则取值
    2. 如果存在于 GROUP_ID_PACKAGED_VOLUME 字典，则取值
    3. 如果存在 volume，则等于 volume
    4. 否则返回 None
    
    Args:
        type_id: 物品类型ID
        group_id: 组ID
        volume: 体积
    
    Returns:
        packagedVolume 值
    """
    # 优先级1: TYPE_ID_PACKAGE_VOLUME
    if type_id in TYPE_ID_PACKAGE_VOLUME:
        return float(TYPE_ID_PACKAGE_VOLUME[type_id])
    
    # 优先级2: GROUP_ID_PACKAGED_VOLUME
    if group_id and group_id in GROUP_ID_PACKAGED_VOLUME:
        return float(GROUP_ID_PACKAGED_VOLUME[group_id])
    
    # 优先级3: volume
    if volume is not None:
        return float(volume)
    
    # 默认返回 None
    return None


def process_inv_types_row(row: dict) -> dict:
    """
    处理 InvTypes 表的单行数据
    
    Args:
        row: 从 JSONL 解析的原始数据
    
    Returns:
        处理后的数据字典，可以直接用于数据库插入
    """
    processed = {
        'typeID': row.get('_key'),
        'groupID': row.get('groupID'),
        'mass': row.get('mass'),
        'volume': row.get('volume'),
        'capacity': row.get('capacity'),
        'portionSize': row.get('portionSize'),
        'factionID': row.get('factionID'),
        'raceID': row.get('raceID'),
        'basePrice': row.get('basePrice'),
        'marketGroupID': row.get('marketGroupID'),
        'graphicID': row.get('graphicID'),
        'radius': row.get('radius'),
        'iconID': row.get('iconID'),
        'soundID': row.get('soundID'),
        'sofFactionName': row.get('sofFactionName'),
        'sofMaterialSetID': row.get('sofMaterialSetID'),
        'metaGroupID': row.get('metaGroupID'),
        'variationparentTypeID': row.get('variationparentTypeID'),
    }
    
    # 处理 published (布尔值转换为整数)
    published = row.get('published')
    if isinstance(published, bool):
        processed['published'] = 1 if published else 0
    else:
        processed['published'] = published
    
    # 处理多语言字段 name
    name_dict = row.get('name')
    if isinstance(name_dict, dict):
        processed['typeName_en'] = name_dict.get('en')
        processed['typeName_zh'] = name_dict.get('zh')
    else:
        processed['typeName_en'] = None
        processed['typeName_zh'] = None
    
    # 处理多语言字段 description
    description_dict = row.get('description')
    if isinstance(description_dict, dict):
        processed['description_en'] = description_dict.get('en')
        processed['description_zh'] = description_dict.get('zh')
    else:
        processed['description_en'] = None
        processed['description_zh'] = None
    
    # 计算 packagedVolume
    processed['packagedVolume'] = calculate_packaged_volume(
        type_id=processed['typeID'],
        group_id=processed.get('groupID'),
        volume=processed.get('volume')
    )
    
    return processed

