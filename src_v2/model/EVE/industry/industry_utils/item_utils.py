# 本地导入 - EVE 模块
from src_v2.model.EVE.sde import SdeUtils
from src_v2.model.EVE.sde.sde_builder import InvTypes
from src_v2.model.EVE.sde.utils import get_db_manager
from sqlalchemy import select


async def get_item_info(type_id: int) -> dict:
    """获取物品信息
    
    Args:
        type_id: 类型ID
    
    Returns:
        dict: 包含 type_id, type_name, type_name_zh, meta, group, market_group_list 的字典
    """
    return {
        "type_id": type_id,
        "type_name": await SdeUtils.get_name_by_id(type_id),
        "type_name_zh": await SdeUtils.get_cn_name_by_id(type_id),
        "meta": await SdeUtils.get_metaname_by_typeid(type_id),
        "group": await SdeUtils.get_groupname_by_id(type_id),
        "market_group_list": "-".join(await SdeUtils.get_market_group_list(type_id))
    }


async def get_type_list() -> list:
    """获取类型列表
    
    Returns:
        List[dict]: 类型列表，每个元素包含 value 和 label
    """
    output = []
    async with (await get_db_manager()).get_session() as session:
        # 获取英文名称
        stmt = select(InvTypes.typeName_en).where(InvTypes.typeName_en.isnot(None))
        result = await session.execute(stmt)
        output.extend([{"value": row[0], "label": row[0]} for row in result if row[0]])
        
        # 获取中文名称
        stmt = select(InvTypes.typeName_zh).where(InvTypes.typeName_zh.isnot(None))
        result = await session.execute(stmt)
        output.extend([{"value": row[0], "label": row[0]} for row in result if row[0]])
    return output

