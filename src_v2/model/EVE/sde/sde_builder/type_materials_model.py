"""
TypeMaterials 表模型和特殊处理

用于解析 typeMaterials.jsonl：
{"_key": 18, "materials": [{"materialTypeID": 34, "quantity": 175}, {"materialTypeID": 36, "quantity": 70}]}
"""
from typing import List, Dict, Any

from sqlalchemy import Column, Integer

from .database_manager import SDEModel


class TypeMaterials(SDEModel):
    """TypeMaterials 表模型 - 物品基础材料信息"""

    __tablename__ = "typeMaterials"

    # 约定：_key 视为 typeID
    typeID = Column(Integer, primary_key=True, nullable=False, index=True)
    materialTypeID = Column(Integer, primary_key=True, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)


def process_type_materials_row(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    处理 typeMaterials.jsonl 的单行数据

    输入示例：
        {
            "_key": 18,
            "materials": [
                {"materialTypeID": 34, "quantity": 175},
                {"materialTypeID": 36, "quantity": 70}
            ]
        }

    返回：
        [
            {"typeID": 18, "materialTypeID": 34, "quantity": 175},
            {"typeID": 18, "materialTypeID": 36, "quantity": 70},
        ]
    """
    type_id = row.get("_key")
    materials = row.get("materials") or []

    if type_id is None:
        # 没有主键，直接跳过
        return []

    records: List[Dict[str, Any]] = []

    if isinstance(materials, list):
        for material in materials:
            if not isinstance(material, dict):
                continue

            material_type_id = material.get("materialTypeID")
            quantity = material.get("quantity")

            if material_type_id is None or quantity is None:
                continue

            records.append(
                {
                    "typeID": type_id,
                    "materialTypeID": material_type_id,
                    "quantity": int(quantity),
                }
            )

    return records


