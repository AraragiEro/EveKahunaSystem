# 标准库导入
import json

# 本地导入 - 核心工具
from src_v2.core.database.connect_manager import redis_manager as rdm
from src_v2.core.database.neo4j_utils import Neo4jAssetUtils as NAU

# 本地导入 - EVE 模块
from src_v2.model.EVE.sde import SdeUtils


async def get_structure_list(user_id: str):
    """获取结构列表
    
    Args:
        user_id: 用户ID
    
    Returns:
        List[dict]: 结构列表
    """
    cache_str = await rdm.r.get(f'structure_suggestions:{user_id}:structure_list')
    if cache_str:
        return json.loads(cache_str)

    structure_list = await NAU.get_structure_nodes()
    res = [
        {
            "structure_id": structure["structure_id"],
            "structure_name": structure["structure_name"],
        } for structure in structure_list
    ]
    await rdm.r.set(f'structure_suggestions:{user_id}:structure_list', json.dumps(res), ex=60*60)
    return res


async def get_structure_assign_keyword_suggestions(assign_type: str, query):
    """获取结构分配关键字建议
    
    Args:
        assign_type: 分配类型 (group, meta, blueprint, marketGroup, category)
        query: 查询字符串
    
    Returns:
        List[dict]: 建议列表，每个元素包含 value 和 label
    """
    output = []
    if assign_type == 'group':
        group_fuzz_list = await SdeUtils.fuzz_group(query, list_len=10)
        output.extend([{"value": item, "label": item} for item in group_fuzz_list])
    elif assign_type == 'meta':
        meta_fuzz_list = await SdeUtils.fuzz_meta(query, list_len=10)
        output.extend([{"value": item, "label": item} for item in meta_fuzz_list])
    elif assign_type == 'blueprint':
        blueprint_fuzz_list = await SdeUtils.fuzz_blueprint(query, list_len=10)
        output.extend([{"value": item, "label": item} for item in blueprint_fuzz_list])
    elif assign_type == 'marketGroup':
        market_group_fuzz_list = await SdeUtils.fuzz_market_group(query, list_len=10)
        output.extend([{"value": item, "label": item} for item in market_group_fuzz_list])
    elif assign_type == 'category':
        category_fuzz_list = await SdeUtils.fuzz_category(query, list_len=10)
        output.extend([{"value": item, "label": item} for item in category_fuzz_list])

    return output

