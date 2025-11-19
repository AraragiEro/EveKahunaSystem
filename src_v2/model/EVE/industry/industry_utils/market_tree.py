# 标准库导入
import asyncio
from typing import Dict, List

# 本地导入 - 核心工具
from src_v2.core.database.connect_manager import neo4j_manager
from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU
from src_v2.core.utils import tqdm_manager

# 本地导入 - EVE 模块
from src_v2.model.EVE.sde import SdeUtils
from src_v2.model.EVE.sde.database import InvTypes, MarketGroups

# 本地导入 - 相对导入
from ..blueprint import BPManager as BPM


async def get_market_tree(node) -> List[Dict]:
    """获取市场树
    
    Args:
        node: 节点ID或"root"
    
    Returns:
        List[Dict]: 节点字典列表
    """
    async with neo4j_manager.get_session() as session:
        if node == "root":
            query = """
            match (a:MarketGroup)
            where not exists { (a)-[]->() }
            return a
            """
            result = await session.run(query)
            nodes = []
            async for record in result:
                node_obj = record["a"]
                if node_obj:
                    node_dict = dict(node_obj)
                    node_dict["hasChildren"] = True
                    node_dict['row_id'] = node_dict['market_group_id']
                    node_dict["name"] = node_dict["name_id_zh"]
                    nodes.append(node_dict)
            return nodes
        else:
            query = f"""
            match (b)-[]->(a:MarketGroup {{market_group_id:{node}}}) return b
            """
            result = await session.run(query)
            nodes = []
            async for record in result:
                node_b = record.get("b")
                if node_b:
                    node_dict_b = dict(node_b)
                    if node_dict_b.get("type_id"):
                        bp_id = await BPM.get_bp_id_by_prod_typeid(node_dict_b["type_id"])
                        node_dict_b["hasChildren"] = False
                        node_dict_b["row_id"] = node_dict_b["type_id"]
                        node_dict_b["name"] = node_dict_b["type_name_zh"]
                        if bp_id:
                            node_dict_b["can_add_plan"] = True
                        else:
                            node_dict_b["can_add_plan"] = False
                    else:
                        node_dict_b["hasChildren"] = True
                        node_dict_b['row_id'] = node_dict_b['market_group_id']
                        node_dict_b["name"] = node_dict_b["name_id_zh"]
                    nodes.append(node_dict_b)
            return nodes


class MarketTree():
    """市场树管理类"""
    
    def __init__(self):
        pass

    @classmethod
    async def init_market_tree(cls, clean=False):
        """初始化市场树
        
        Args:
            clean: 是否清理现有数据
        """
        # 市场组入数据库
        # 拉取全量market_group数据
        if clean:
            await NIU.delete_label_node("MarketGroup")
        
        # 先创建所有节点
        async def create_market_group_node_with_semaphore(market_group: MarketGroups):
            async with neo4j_manager.semaphore:
                cn_name = SdeUtils.get_market_group_name_by_groupid(market_group.marketGroupID, zh=True)
                await NIU.merge_node(
                    "MarketGroup",
                    {"market_group_id": market_group.marketGroupID},
                    {
                        "market_group_id": market_group.marketGroupID,
                        "has_types": market_group.hasTypes,
                        "icon_id": market_group.iconID,
                        "name_id": market_group.nameID,
                        "name_id_zh": cn_name,
                    }
                )
                await tqdm_manager.update_mission("init_market_tree", 1)
        tasks = []
        market_group_data = MarketGroups.select()
        await tqdm_manager.add_mission("init_market_tree", len(market_group_data))
        for market_group in market_group_data:
            tasks.append(asyncio.create_task(create_market_group_node_with_semaphore(market_group)))
        await asyncio.gather(*tasks)
        await tqdm_manager.complete_mission("init_market_tree")

        # 再创建所有关系
        async def link_market_group_to_market_group_with_semaphore(market_group: MarketGroups):
            async with neo4j_manager.semaphore:
                cn_name = SdeUtils.get_market_group_name_by_groupid(market_group.marketGroupID, zh=True)
                await NIU.link_node(
                    "MarketGroup",
                    {"market_group_id": market_group.marketGroupID},
                    {"market_group_id": market_group.marketGroupID},
                    "EVE_MARKET_GROUP",
                    {},
                    {},
                    "MarketGroup",
                    {"market_group_id": market_group.parentGroupID},
                    {"market_group_id": market_group.parentGroupID},
                )
                await tqdm_manager.update_mission("link_type_to_market_group", 1)
        market_group_data = MarketGroups.select()
        tasks = []
        await tqdm_manager.add_mission("init_market_tree", len(market_group_data))
        for market_group in market_group_data:
            if market_group.parentGroupID:
                tasks.append(asyncio.create_task(link_market_group_to_market_group_with_semaphore(market_group)))
        await asyncio.gather(*tasks)
        await tqdm_manager.complete_mission("init_market_tree")

    @classmethod
    async def link_type_to_market_group(cls, clean=False):
        """将类型链接到市场组
        
        Args:
            clean: 是否清理现有数据
        """
        # type 数据入库
        # 拉取全量type数据
        if clean:
            await NIU.delete_label_node("Type")

        async def link_type_to_market_group_with_semaphore(type: InvTypes):
            async with neo4j_manager.semaphore:
                cn_name = SdeUtils.get_cn_name_by_id(type.typeID)
                meta_group_name = SdeUtils.get_metaname_by_metaid(type.typeID)
                category_name = SdeUtils.get_category_by_id(type.typeID)
                category_name_zh = SdeUtils.get_category_by_id(type.typeID, zh=True)
                bp_id = await BPM.get_bp_id_by_prod_typeid(type.typeID)

                await NIU.link_node(
                    "Type",
                    {"type_id": type.typeID},
                    {
                        "type_id": type.typeID,
                        "type_name": type.typeName,
                        "type_name_zh": cn_name,
                        "meta_group_name": meta_group_name,
                        "category_name": category_name,
                        "category_name_zh": category_name_zh,
                        "bp_id": bp_id
                    },
                    "EVE_MARKET_GROUP",
                    {},
                    {},
                    "MarketGroup",
                    {"market_group_id": type.marketGroupID},
                    {"market_group_id": type.marketGroupID}
                )
                await tqdm_manager.update_mission("link_type_to_market_group", 1)
        type_data = InvTypes.select()
        tasks = []
        await tqdm_manager.add_mission("link_type_to_market_group", len(type_data))
        for type in type_data:
            if type.marketGroupID:
                tasks.append(asyncio.create_task(link_type_to_market_group_with_semaphore(type)))
            else:
                await tqdm_manager.update_mission("link_type_to_market_group", 1)
        await asyncio.gather(*tasks)
        await tqdm_manager.complete_mission("link_type_to_market_group")

