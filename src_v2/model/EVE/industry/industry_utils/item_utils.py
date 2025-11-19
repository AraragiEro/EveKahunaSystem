# 本地导入 - EVE 模块
from src_v2.model.EVE.sde import SdeUtils
from src_v2.model.EVE.sde.database import InvTypes
from src_v2.model.EVE.sde.database_cn import InvTypes as InvTypes_zh


async def get_item_info(type_id: int) -> dict:
    """获取物品信息
    
    Args:
        type_id: 类型ID
    
    Returns:
        dict: 包含 type_id, type_name, type_name_zh, meta, group, market_group_list 的字典
    """
    return {
        "type_id": type_id,
        "type_name": SdeUtils.get_name_by_id(type_id),
        "type_name_zh": SdeUtils.get_cn_name_by_id(type_id),
        "meta": SdeUtils.get_metaname_by_typeid(type_id),
        "group": SdeUtils.get_groupname_by_id(type_id),
        "market_group_list": "-".join(SdeUtils.get_market_group_list(type_id))
    }


async def get_type_list() -> list:
    """获取类型列表
    
    Returns:
        List[dict]: 类型列表，每个元素包含 value 和 label
    """
    output = []
    output.extend([{"value": res.typeName, "label": res.typeName} for res in InvTypes.select(InvTypes.typeName)])
    output.extend([{"value": res.typeName, "label": res.typeName} for res in InvTypes_zh.select(InvTypes_zh.typeName)])
    return output

