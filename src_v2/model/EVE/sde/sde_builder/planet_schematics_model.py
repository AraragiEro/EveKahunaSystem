"""
行星工业蓝图数据模型和特殊处理

解析 planetSchematics.jsonl：
{
    "_key": 97,
    "cycleTime": 3600,
    "name": {"en": "Robotics", "zh": "机器人技术", ...},
    "pins": [2470, 2472, 2474, 2480, 2484, 2485, 2491, 2494],
    "types": [
        {"_key": 3689, "isInput": true, "quantity": 10},
        {"_key": 9836, "isInput": true, "quantity": 10},
        {"_key": 9848, "isInput": false, "quantity": 3}
    ]
}

拆分为 2 张表：
  - planetSchematics：蓝图主信息（ID、周期、名称、pin 列表）
  - planetSchematicTypes：输入/输出物料明细
"""
from typing import Dict, Any, List, Tuple

from sqlalchemy import Column, Integer, Boolean, Text, JSON

from .database_manager import SDEModel


class PlanetSchematics(SDEModel):
    """行星工业蓝图主表"""

    __tablename__ = "planetSchematics"

    schematicID = Column(Integer, primary_key=True, nullable=False)
    cycleTime = Column(Integer, nullable=False)
    name_en = Column(Text, nullable=True)
    name_zh = Column(Text, nullable=True)
    pins = Column(JSON, nullable=True)  # 所需设施 type ID 列表


class PlanetSchematicTypes(SDEModel):
    """行星工业蓝图输入/输出物料表"""

    __tablename__ = "planetSchematicTypes"

    schematicID = Column(Integer, primary_key=True, nullable=False)
    typeID = Column(Integer, primary_key=True, nullable=False)
    isInput = Column(Boolean, primary_key=True, nullable=False)
    quantity = Column(Integer, nullable=False)


def process_planet_schematics_row(row: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    处理 planetSchematics.jsonl 的单行数据，拆分为主表 + 子表记录

    Args:
        row: 从 JSONL 解析的原始数据（已由 SDEParser 将 name 拆分为 name_en / name_zh）

    Returns:
        (schematic_record, types_records) 元组
        - schematic_record: PlanetSchematics 单条记录
        - types_records: PlanetSchematicTypes 记录列表
    """
    schematic_id = row.get("_key")
    if schematic_id is None:
        return {}, []

    # 主表记录
    schematic_record = {
        "schematicID": schematic_id,
        "cycleTime": row.get("cycleTime"),
        "name_en": row.get("name_en"),
        "name_zh": row.get("name_zh"),
        "pins": row.get("pins"),
    }

    # 子表记录：展平 types 数组
    types_records: List[Dict[str, Any]] = []
    types = row.get("types")
    if isinstance(types, list):
        for t in types:
            if not isinstance(t, dict):
                continue
            type_id = t.get("_key")
            quantity = t.get("quantity")
            if type_id is None or quantity is None:
                continue
            types_records.append(
                {
                    "schematicID": schematic_id,
                    "typeID": type_id,
                    "isInput": bool(t.get("isInput", False)),
                    "quantity": int(quantity),
                }
            )

    return schematic_record, types_records
