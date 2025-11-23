"""
MapSolarSystems 表模型和特殊处理
"""
from sqlalchemy import Column, Integer, Float, Text, String
from .database_manager import SDEModel


class MapSolarSystems(SDEModel):
    """MapSolarSystems 表模型 - 星系信息"""
    __tablename__ = 'mapSolarSystems'
    
    solarSystemID = Column(Integer, primary_key=True, index=True)  # mapSolarSystems.jsonl._key
    solarSystemName_en = Column(Text, nullable=True)  # mapSolarSystems.jsonl.name.en
    solarSystemName_zh = Column(Text, nullable=True)  # mapSolarSystems.jsonl.name.zh
    regionID = Column(Integer, nullable=True)  # mapSolarSystems.jsonl.regionID
    constellationID = Column(Integer, nullable=True)  # mapSolarSystems.jsonl.constellationID
    x = Column(Float, nullable=True)  # mapSolarSystems.jsonl.position.x
    y = Column(Float, nullable=True)  # mapSolarSystems.jsonl.position.y
    z = Column(Float, nullable=True)  # mapSolarSystems.jsonl.position.z
    luminosity = Column(Float, nullable=True)  # mapSolarSystems.jsonl.luminosity
    border = Column(Integer, nullable=True)  # mapSolarSystems.jsonl.border (布尔值转换为整数)
    hub = Column(Integer, nullable=True)  # mapSolarSystems.jsonl.hub (布尔值转换为整数)
    international = Column(Integer, nullable=True)  # mapSolarSystems.jsonl.international (布尔值转换为整数)
    regional = Column(Integer, nullable=True)  # mapSolarSystems.jsonl.regional (布尔值转换为整数)
    security = Column(Float, nullable=True)  # mapSolarSystems.jsonl.securityStatus
    radius = Column(Float, nullable=True)  # mapSolarSystems.jsonl.radius
    sunTypeID = Column(Integer, nullable=True)  # mapSolarSystems.jsonl.starID
    securityClass = Column(String(2), nullable=True)  # mapSolarSystems.jsonl.securityClass


def process_map_solar_systems_row(row: dict) -> dict:
    """
    处理 MapSolarSystems 表的单行数据
    
    Args:
        row: 从 JSONL 解析的原始数据
    
    Returns:
        处理后的数据字典，可以直接用于数据库插入
    """
    processed = {
        'solarSystemID': row.get('_key'),
        'regionID': row.get('regionID'),
        'constellationID': row.get('constellationID'),
        'luminosity': row.get('luminosity'),
        'radius': row.get('radius'),
        'sunTypeID': row.get('starID'),
        'securityClass': row.get('securityClass'),
    }
    
    # 处理多语言字段 name
    name_dict = row.get('name')
    if isinstance(name_dict, dict):
        processed['solarSystemName_en'] = name_dict.get('en')
        processed['solarSystemName_zh'] = name_dict.get('zh')
    else:
        processed['solarSystemName_en'] = None
        processed['solarSystemName_zh'] = None
    
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
    
    # 处理布尔值字段，转换为整数
    def bool_to_int(value):
        if isinstance(value, bool):
            return 1 if value else 0
        return value
    
    processed['border'] = bool_to_int(row.get('border'))
    processed['hub'] = bool_to_int(row.get('hub'))
    processed['international'] = bool_to_int(row.get('international'))
    processed['regional'] = bool_to_int(row.get('regional'))
    
    # 映射字段名：securityStatus -> security
    processed['security'] = row.get('securityStatus')
    
    return processed

