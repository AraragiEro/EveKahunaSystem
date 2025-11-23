# 本地导入 - EVE 模块
from src_v2.model.EVE.sde import SdeUtils


async def get_material_type(type_id: int) -> str:
    """根据类型ID获取材料类型
    
    Args:
        type_id: 类型ID
    
    Returns:
        str: 材料类型名称（矿石、冰矿产物、燃料块、元素、气云、行星工业、杂货）
    """
    group = await SdeUtils.get_groupname_by_id(type_id)
    category = await SdeUtils.get_category_by_id(type_id)
    # 根据 group 或 category 进行判断和分类
    if group == "Mineral":
        return "矿石"
    elif group == 'Ice Product':
        return "冰矿产物"
    elif group == "Fuel Block":
        return "燃料块"
    elif group == "Moon Materials":
        return "元素"
    elif group == "Harvestable Cloud":
        return "气云"
    elif category == "Planetary Commodities":
        return "行星工业"
    else:
        return "杂货"

