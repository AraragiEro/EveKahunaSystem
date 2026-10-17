"""
NpcCorporations 表模型和特殊处理
"""
from sqlalchemy import Column, Integer, Text, JSON
from .database_manager import SDEModel


class NpcCorporations(SDEModel):
    """NpcCorporations 表模型 - NPC公司信息"""
    __tablename__ = 'npcCorporations'

    corporationID = Column(Integer, primary_key=True)  # npcCorporations.jsonl._key
    name_en = Column(Text, nullable=True)  # npcCorporations.jsonl.name.en
    name_zh = Column(Text, nullable=True)  # npcCorporations.jsonl.name.zh
    factionID = Column(Integer, nullable=True)  # npcCorporations.jsonl.factionID
    description_en = Column(Text, nullable=True)  # npcCorporations.jsonl.description.en
    description_zh = Column(Text, nullable=True)  # npcCorporations.jsonl.description.zh
    tickerName = Column(Text, nullable=True)  # npcCorporations.jsonl.tickerName
    stationID = Column(Integer, nullable=True)  # npcCorporations.jsonl.stationID
    solarSystemID = Column(Integer, nullable=True)  # npcCorporations.jsonl.solarSystemID
    raceID = Column(Integer, nullable=True)  # npcCorporations.jsonl.raceID
    ceoID = Column(Integer, nullable=True)  # npcCorporations.jsonl.ceoID
    iconID = Column(Integer, nullable=True)  # npcCorporations.jsonl.iconID
    lpOfferTables = Column(JSON, nullable=True)  # npcCorporations.jsonl.lpOfferTables


def process_npc_corporations_row(row: dict) -> dict:
    """
    处理 NpcCorporations 表的单行数据

    Args:
        row: 从 JSONL 解析的原始数据

    Returns:
        处理后的数据字典，可以直接用于数据库插入
    """
    processed = {
        'corporationID': row.get('_key'),
        'factionID': row.get('factionID'),
        'tickerName': row.get('tickerName'),
        'stationID': row.get('stationID'),
        'solarSystemID': row.get('solarSystemID'),
        'raceID': row.get('raceID'),
        'ceoID': row.get('ceoID'),
        'iconID': row.get('iconID'),
        'lpOfferTables': row.get('lpOfferTables'),
    }

    # 处理多语言字段 name
    name_dict = row.get('name')
    if isinstance(name_dict, dict):
        processed['name_en'] = name_dict.get('en')
        processed['name_zh'] = name_dict.get('zh')
    else:
        processed['name_en'] = None
        processed['name_zh'] = None

    # 处理多语言字段 description（可能不存在）
    description_dict = row.get('description')
    if isinstance(description_dict, dict):
        processed['description_en'] = description_dict.get('en')
        processed['description_zh'] = description_dict.get('zh')
    else:
        processed['description_en'] = None
        processed['description_zh'] = None

    return processed
