import asyncio
from asyncio import Queue
from enum import Flag
from itertools import product
import json
from typing import Tuple, List, Dict
from math import ceil
from src_v2.core.database.neo4j_models import MarketGroup
from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU
from src_v2.core.database.connect_manager import neo4j_manager, redis_manager, postgres_manager
from src_v2.core.database.kahuna_database_utils_v2 import EveIndustryPlanDBUtils, EveIndustryPlanProductDBUtils
from src_v2.core.utils import KahunaException, SingletonMeta
from src_v2.model.EVE.sde import SdeUtils
from src_v2.model.EVE.sde.database import MarketGroups, InvTypes
from src_v2.core.log import logger
from .blueprint import BPManager as BPM

from src_v2.core.utils import tqdm_manager


# 异步计数器
class AsyncCounter():
    def __init__(self):
        self.node_counter = 0
        self.relation_counter = 0
        self._lock = asyncio.Lock()
    
    async def next_node(self) -> int:
        """
        返回当前node计数并+1
        
        Returns:
            int: 返回当前的node_counter值，然后将其+1
        """
        async with self._lock:
            current = self.node_counter
            self.node_counter += 1
            return current
    
    async def next_relation(self) -> int:
        """
        返回当前relation计数并+1
        
        Returns:
            int: 返回当前的relation_counter值，然后将其+1
        """
        async with self._lock:
            current = self.relation_counter
            self.relation_counter += 1
            return current
    
    async def init_count(self):
        """
        重置所有计数器为0
        """
        async with self._lock:
            self.node_counter = 0
            self.relation_counter = 0



class IndustryManager(metaclass=SingletonMeta):
    def __init__(self):
        self.bp_node_analyse_queue = Queue()
        self.bp_relation_analyse_queue = Queue()

    @classmethod
    async def create_plan(cls, user_name: str, plan_name: str, plan_settings: dict):
        plan_obj = EveIndustryPlanDBUtils.get_obj()
        plan_obj.plan_name = plan_name
        plan_obj.user_name = user_name
        plan_obj.settings = plan_settings
        await EveIndustryPlanDBUtils.save_obj(plan_obj)

    @classmethod
    async def get_plan(cls, user_name: str):
        row_id_counter = AsyncCounter()
        plan_list = {}
        async for plan in await EveIndustryPlanDBUtils.select_all_by_user_name(user_name):
            plan_list[plan.plan_name] = {
                "row_id": await row_id_counter.next_node(),
                "plan_name": plan.plan_name,
                "user_name": plan.user_name,
                "plan_settings": plan.settings,
                "products": []
            }
        
        async for product in await EveIndustryPlanProductDBUtils.select_all_by_user_name(user_name):
            type_name = SdeUtils.get_name_by_id(product.product_type_id)
            type_name_zh = SdeUtils.get_cn_name_by_id(product.product_type_id)
            plan_list[product.plan_name]["products"].append({
                "row_id": await row_id_counter.next_node(),
                "index_id": product.index_id,
                "product_type_id": product.product_type_id,
                "quantity": product.quantity,
                "type_name": type_name,
                "type_name_zh": type_name_zh
            })

        return list(plan_list.values())

    @classmethod
    async def add_plan_product(cls, user_id: str, plan_name: str, type_id: int, quantity: int):
        plan_list = []
        async for plan in await EveIndustryPlanProductDBUtils.select_all_by_user_name_and_plan_name(user_id, plan_name):
            plan_list.append(plan)

        plan_product_obj = EveIndustryPlanProductDBUtils.get_obj()
        plan_product_obj.user_name = user_id
        plan_product_obj.plan_name = plan_name
        plan_product_obj.index_id = len(plan_list) + 1
        plan_product_obj.product_type_id = type_id
        plan_product_obj.quantity = quantity
        await EveIndustryPlanProductDBUtils.save_obj(plan_product_obj)

    @classmethod
    async def save_plan_products(cls, user_id: str, plan_name: str, products: List[dict]):
        counter = AsyncCounter()
        async with postgres_manager.get_session() as session:
            await EveIndustryPlanProductDBUtils.delete_all_by_user_name_and_plan_name(user_id, plan_name, session)
            for product in products:
                plan_product_obj = EveIndustryPlanProductDBUtils.get_obj()
                plan_product_obj.user_name = user_id
                plan_product_obj.plan_name = plan_name
                plan_product_obj.index_id = await counter.next_node()
                plan_product_obj.product_type_id = product["product_type_id"]
                plan_product_obj.quantity = product["quantity"]
                await EveIndustryPlanProductDBUtils.save_obj(plan_product_obj, session)

    @classmethod
    async def calculate_plan(cls, user_id: str, plan_name: str):
        plan_obj = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(user_id, plan_name)
        plan_data = {
            "plan_name": plan_name,
            "user_name": user_id,
            "plan_settings": plan_obj.settings,
            "products": []
        }
        async for product in await EveIndustryPlanProductDBUtils.select_all_by_user_name_and_plan_name(user_id, plan_name):
            plan_data["products"].append({
                "index_id": product.index_id,
                "product_type_id": product.product_type_id,
                "quantity": product.quantity
            })
        if not plan_data["products"]:
            raise KahunaException(f"计划 {plan_name} 没有添加产品")
        await cls.delete_plan(plan_name, user_id)
        await cls.create_plan_node(plan_data)
        await cls.create_plan_tree(plan_data)
        await cls.update_plan_status(plan_name, user_id)

    @classmethod
    async def create_plan_node(cls, plan_data: dict):
        """
        plan_data: {
            "plan_name": str,
            "user_name": str,
            "plan_settings": {
                "considerate_asset": bool,
                "considerate_running_job": bool,
                
                "split_to_jobs": bool,
                "considerate_bp_relation": bool,
                
                "work_type": str # in_order | whole
            }
        }
        """

        node_index = {
            "plan_name": plan_data["plan_name"],
            "user_name": plan_data["user_name"],
        }
        node_properties = {
            "plan_name": plan_data["plan_name"],
            "user_name": plan_data["user_name"],
            "plan_settings": json.dumps(plan_data["plan_settings"]),
        }
        await NIU.merge_node("Plan", node_index, node_properties)

    @classmethod
    async def create_plan_tree(cls, plan_data: dict):
        plan_name = plan_data["plan_name"]
        user_name = plan_data["user_name"]
        products = plan_data["products"]
        plan_user_dict = {"plan_name": plan_name, "user_name": user_name}
        counter = AsyncCounter()

        await tqdm_manager.add_mission(f"create_plan_{plan_name}", len(products))
        for product in products:
            # 将树连接到plan节点
            await NIU.link_node(
                "Plan",
                plan_user_dict,
                plan_user_dict,
                "PLAN_BP_DEPEND_ON",
                {**plan_user_dict, "index_id": product["index_id"], "product": "root", "material": product["product_type_id"]},
                {**plan_user_dict, "index_id": product["index_id"], "product": "root", "material": product["product_type_id"],
                 "status": "complete", "quantity": product["quantity"], "real_quantity": product["quantity"],
                 "product_num": 1, "material_num": product["quantity"], "order_id": await counter.next_relation()},
                "PlanBlueprint",
                {**plan_user_dict, "type_id": product["product_type_id"]},
                {**plan_user_dict, "type_id": product["product_type_id"]}
            )
            await cls._create_plan_bp_tree(plan_user_dict, product, counter)
            await tqdm_manager.update_mission(f"create_plan_{plan_name}", 1)

            # index_root节点更新需求数量，更新状态为finished.
        await tqdm_manager.complete_mission(f"create_plan_{plan_name}")

    @classmethod
    async def delete_plan(cls, plan_name: str, user_name: str):
        await NIU.delete_tree(
            "Plan",
            {"plan_name": plan_name, "user_name": user_name},
            "PLAN_BP_DEPEND_ON")

    @classmethod
    async def _get_material_type(cls, node_dict: dict):
        group = node_dict['group_name']
        category = node_dict['category']
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

    @classmethod
    async def get_plan_tableview_data(cls, plan_name: str, user_name: str):
        material_type = ["矿石", "冰矿产物", "燃料块", "元素", "气云", "行星工业", "杂货"]

        node_dict = {
            node['type_id']: node for node in await NIU.get_user_plan_node_with_distance(user_name, plan_name)
        }
        for relation in await NIU.get_user_plan_relation(user_name, plan_name):
            material_id = relation['material']
            product_id = relation['product']
            node_dict[material_id].update({
                "quantity": node_dict[material_id].get('quantity', 0) + relation['quantity'],
                "real_quantity": node_dict[material_id].get('real_quantity', 0) + relation['real_quantity'],
            })
            # 考虑"root"节点情况
            if product_id in node_dict:
                node_dict[product_id].update({
                    "jobs": node_dict[product_id].get('jobs', 0) + sum(relation['job_list']),
                    "real_jobs": node_dict[product_id].get('real_jobs', 0) + sum(relation['real_job_list']),
                })

        distance_list = list(set([node['max_distance'] for node in node_dict.values()]))
        distance_list.sort()
        flow_output = [
            {
                "layer_id": index,
                "children": []
            } for index in distance_list
        ]
        material_output = {
            t: {
                "layer_id": t,
                "children": []
            } for t in material_type
        }
        for node in node_dict.values():
            node['tpye_name_zh'] = SdeUtils.get_cn_name_by_id(node['type_id'])
            if "jobs" not in node:
                material_type_node = await cls._get_material_type(node)
                material_output[material_type_node]['children'].append(node)
            else:
                flow_output[node['max_distance']]["children"].append(node)
        return {
            "flow_output": flow_output,
            "material_output": [material_output[t] for t in material_type]
        }

    @staticmethod
    async def get_market_tree(node) -> List[Dict]:
        """获取市场树
        
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

    @classmethod
    async def _init_index_root_status(cls, plan_user_dict: dict, product_data: dict):
        pass

    @classmethod
    async def _create_plan_bp_tree(cls, plan_user_dict: dict, product_data: dict, counter: AsyncCounter):
        """
        从neo4j中搜索blueprint的typeid的节点，并找到以BP_DEPEND_ON连接的所有子节点，
        以这棵树为蓝本复制一个以PlanBlueprint代替Blueprint的节点树。
        
        Args:
            plan_user_dict: 包含 plan_name 和 user_name 的字典
            product_data: 包含 id, type_id, quantity 的字典
                {
                    "id": 1,
                    "type_id": 28661,
                    "quantity": 16
                }
        """

        type_id = product_data["product_type_id"]
        quantity = product_data.get("quantity", 1)
        index_id = product_data.get("index_id", 0)
        
        # 1. 查询Blueprint树（从给定的type_id开始，通过BP_DEPEND_ON关系）
        # 查询所有Blueprint节点和BP_DEPEND_ON关系
        # 使用MATCH找到根节点及其所有子节点
        nodes_dict, relationships_list = await NIU.get_blueprint_tree(type_id)
        await tqdm_manager.add_mission(f"create_plan_bp_tree_{type_id}_nodes", len(nodes_dict))
        await tqdm_manager.add_mission(f"create_plan_bp_tree_{type_id}_relationships", len(relationships_list))

        # 2. 创建PlanBlueprint节点树
        # 首先创建所有PlanBlueprint节点
        tasks = []
        async def merge_node_with_semaphore(plan_bp_index, plan_bp_properties):
            async with neo4j_manager.semaphore:
                await NIU.merge_node("PlanBlueprint", plan_bp_index, plan_bp_properties)
                await tqdm_manager.update_mission(f"create_plan_bp_tree_{type_id}_nodes", 1)
        for node_type_id, node_props in nodes_dict.items():
            # 构建PlanBlueprint节点的索引和属性
            plan_bp_index = {
                **plan_user_dict,
                "type_id": node_type_id
            }
            
            # 从Blueprint节点复制属性，但添加plan_user_dict的属性
            plan_bp_properties = {
                **plan_user_dict,
                **node_props
            }
            
            tasks.append(
                asyncio.create_task(
                    merge_node_with_semaphore(plan_bp_index, plan_bp_properties)
                )
            )
        
        await asyncio.gather(*tasks)
        
        # 3. 创建关系
        tasks = []
        async def link_node_with_semaphore(source_index, target_index, plan_rel_index, plan_rel_properties):
            async with neo4j_manager.semaphore:
                await NIU.link_node(
                    "PlanBlueprint",  # 源节点标签
                    source_index,  # 源节点索引
                    source_index,  # 源节点属性（与索引相同）
                    "PLAN_BP_DEPEND_ON",  # 关系类型
                    plan_rel_index,  # 关系索引
                    plan_rel_properties,  # 关系属性
                    "PlanBlueprint",  # 目标节点标签
                    target_index,  # 目标节点索引
                    target_index  # 目标节点属性（与索引相同）
                )
                await tqdm_manager.update_mission(f"create_plan_bp_tree_{type_id}_relationships", 1)

        for parent_type_id, child_type_id, rel_props in relationships_list:
            # 构建源节点（父节点）的索引
            source_index = {
                **plan_user_dict,
                "type_id": parent_type_id
            }
            
            # 构建目标节点（子节点）的索引
            target_index = {
                **plan_user_dict,
                "type_id": child_type_id
            }
            
            # 构建关系属性，包含plan_user_dict和原始关系的属性
            plan_rel_properties = {
                **plan_user_dict,
                "index_id": index_id,
                **rel_props,  # 包含原始BP_DEPEND_ON关系的属性（如material_num, product_num等）
                "status": "disable",
                "order_id": await counter.next_relation()
            }
            
            # 构建关系索引（用于匹配已存在的关系）
            plan_rel_index = {
                **plan_user_dict,
                "index_id": index_id,
                "product": parent_type_id,
                "material": child_type_id
            }
            
            tasks.append(asyncio.create_task(link_node_with_semaphore(
                source_index, target_index, plan_rel_index, plan_rel_properties
            )))
        
        await asyncio.gather(*tasks)

        await tqdm_manager.complete_mission(f"create_plan_bp_tree_{type_id}_nodes")
        await tqdm_manager.complete_mission(f"create_plan_bp_tree_{type_id}_relationships")

    @classmethod
    async def _relation_calculater(cls, plan_settings: dict, relation: dict, product_node_in_relation: List[dict], same_route_relations: List[dict]):
        # 获取
        self_relation = relation['relation']
        self_index_id = self_relation['index_id']
        self_order_id = self_relation['order_id']
        order_index = [relation['relation']['order_id'] for relation in same_route_relations].index(self_order_id)

        # 收集父节点需求数量
        all_index_quantity = sum([relation['relation']['quantity'] for relation in product_node_in_relation])
        all_index_real_quantity = sum([relation['relation']['real_quantity'] for relation in product_node_in_relation])
        self_index_quantity = sum([relation['relation']['quantity'] for relation in product_node_in_relation if relation['relation']['index_id'] == self_index_id])
        self_index_real_quantity = sum([relation['relation']['real_quantity'] for relation in product_node_in_relation if relation['relation']['index_id'] == self_index_id])

        # TODO 库存 与 运行中任务生产数量处理
        # 对real_quantity进行处理，去掉库存和生产数量
        # quantity 代表总需求， real_quantity代表从上层传导下来的实际需求， 用quantity减去real是缺失

        if order_index == 0:
            last_order_index_remain = 0
            last_order_index_real_remain = 0
        else:
            last_order_index_remain = same_route_relations[order_index-1]['relation']['product_remain']
            last_order_index_real_remain = same_route_relations[order_index-1]['relation']['real_product_remain']

        # 计算最小流程
        # min_all_index_quantity_work = ceil(all_index_quantity / self_relation['product_num'])
        # min_all_index_real_quantity_work = ceil(all_index_real_quantity / self_relation['product_num'])
        min_self_index_quantity_work = ceil((self_index_quantity - last_order_index_remain) / self_relation['product_num'])
        min_self_index_real_quantity_work = ceil((self_index_real_quantity - last_order_index_real_remain) / self_relation['product_num'])
        #    计算多余数量
        self_product_remain = min_self_index_quantity_work * self_relation['product_num'] - self_index_quantity + last_order_index_remain
        self_real_product_remain = min_self_index_real_quantity_work * self_relation['product_num'] - self_index_real_quantity + last_order_index_real_remain

        # TODO 根据配置 切分工作流 or 不切分
        job_list = [min_self_index_quantity_work]
        real_job_list = [min_self_index_real_quantity_work]

        # TODO 根据系数计算工作流需要的材料数量

        quantity_material_need = min_self_index_quantity_work * self_relation['material_num']
        real_quantity_material_need = min_self_index_real_quantity_work * self_relation['material_num']

        # 更新状态
        res = await NIU.update_relation_properties(
            "PLAN_BP_DEPEND_ON",
            {
                "user_name": self_relation['user_name'],
                "plan_name": self_relation["plan_name"],
                "index_id": self_relation['index_id'],
                "product": self_relation['product'],
                "material": self_relation['material']
            },
            {
                "quantity": quantity_material_need,
                "real_quantity": real_quantity_material_need,
                "index_quantity_work": min_self_index_quantity_work,
                "index_real_quantity_work": min_self_index_real_quantity_work,
                "product_remain": self_product_remain,
                "real_product_remain": self_real_product_remain,
                "job_list": job_list,
                "real_job_list": real_job_list,
                "status": "complete"
            }
        )
        logger.debug(f"relation index {self_relation['index_id']} {self_relation['product']}->{self_relation['material']} calculate complete")

    @classmethod
    async def _is_update_complete(cls, user_name: str, plan_name: str):
        all_relation_list = await NIU.get_relations("PLAN_BP_DEPEND_ON", {"user_name": user_name, "plan_name": plan_name})
        for relation in all_relation_list:
            if relation['relation']['status'] != "complete":
                return False
        return True

    @classmethod
    async def _is_relation_calculate_avaliable(cls, relation: dict) -> Tuple[bool, List[dict], List[dict]]:
        self_relation = relation['relation']
        if self_relation['status'] == "complete":
            return False, [], []
        self_index_id = self_relation['index_id']
        self_order_id = self_relation['order_id']

        same_route_relations = await NIU.get_relations(
            "PLAN_BP_DEPEND_ON",
            {"user_name": self_relation['user_name'], "plan_name": self_relation["plan_name"],
            "product": self_relation['product'], "material": self_relation['material']}
        )
        same_route_relations.sort(key=lambda x: x['relation']['order_id'])
        for i, relation in enumerate(same_route_relations):
            if i == 0:
                if relation['relation']['order_id'] == self_order_id:
                    break
                elif relation['relation']['status'] != "complete":
                    return False, [], []
            else:
                if relation['relation']['order_id'] == self_order_id:
                    if same_route_relations[i-1]['relation']['status'] == "complete":
                        break
                    else:
                        return False, [], []
                
        product_node_in_relation = await NIU.get_relations(
            "PLAN_BP_DEPEND_ON",
            {"user_name": self_relation['user_name'], "plan_name": self_relation["plan_name"]},
            target_label="PlanBlueprint",
            target_index={"type_id": self_relation['product']}
        )
        for r in product_node_in_relation:
            if r['relation']['status'] != "complete":
                return False, [], []
        return True, product_node_in_relation, same_route_relations

    @classmethod
    async def _relation_moniter_process(cls, user_name: str, plan_name: str):
        plan_node = await NIU.get_node_properties("Plan", {"user_name": user_name, "plan_name": plan_name})
        plan_settings = json.loads(plan_node['plan_settings'])
        all_relation_list = await NIU.get_relations("PLAN_BP_DEPEND_ON", {"user_name": user_name, "plan_name": plan_name})

        await tqdm_manager.add_mission("relation_moniter_process", len(all_relation_list))
        while not await cls._is_update_complete(user_name, plan_name):
            for relation in all_relation_list:
                res, product_node_in_relation, same_route_relations = await cls._is_relation_calculate_avaliable(relation)
                if res:
                    await cls._relation_calculater(plan_settings, relation, product_node_in_relation, same_route_relations)
                    await tqdm_manager.update_mission("relation_moniter_process", 1)
        await tqdm_manager.complete_mission("relation_moniter_process")
        logger.info(f"plan {plan_name} status update complete")

    @classmethod
    async def update_plan_status(cls, plan_name: str, user_name: str):
        await cls._relation_moniter_process(user_name, plan_name)

class MarketTree():
    def __init__(self):
        pass

    @classmethod
    async def init_market_tree(cls, clean=False):
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