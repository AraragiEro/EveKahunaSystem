import asyncio
from asyncio import Queue
from enum import Flag
from itertools import product
import json
from typing import Tuple, List, Dict
from math import ceil
from src_v2.core.database.neo4j_models import MarketGroup
from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU
from src_v2.core.database.neo4j_utils import Neo4jAssetUtils as NAU
from src_v2.core.database.connect_manager import neo4j_manager, redis_manager, postgres_manager
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveIndustryPlanDBUtils,
    EveIndustryPlanProductDBUtils,
    EveIndustryAssetContainerPermissionDBUtils,
    EveAssetPullMissionDBUtils,
    EveIndustryPlanConfigFlowConfigDBUtils,
    EveIndustryPlanConfigFlowDBUtils
    )
from src_v2.model.EVE.character import CharacterManager
from src_v2.core.utils import KahunaException, SingletonMeta
from src_v2.model.EVE.sde import SdeUtils
from src_v2.model.EVE.sde.database import (
    MarketGroups,
    InvTypes,
    InvGroups,
    InvCategories,
    MetaGroups,
    IndustryBlueprints
)
from src_v2.model.EVE.sde.database_cn import (
    MarketGroups as MarketGroups_zh,
    InvTypes as InvTypes_zh,
    InvGroups as InvGroups_zh,
    InvCategories as InvCategories_zh,
    MetaGroups as MetaGroups_zh,
    IndustryBlueprints as IndustryBlueprints_zh
)
from src_v2.core.log import logger
from .blueprint import BPManager as BPM
from src_v2.model.EVE.eveesi import eveesi

from src_v2.core.utils import tqdm_manager

from .plan_configflow_operate import ConfigFlowOperateCenter

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
    async def modify_plan_settings(cls, user_name: str, plan_name: str, plan_settings: dict):
        plan_obj = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(user_name, plan_name)
        if not plan_obj:
            raise KahunaException(f"计划不存在")
        plan_obj.settings = plan_settings
        await EveIndustryPlanDBUtils.merge(plan_obj)

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
    async def calculate_plan(cls, op: ConfigFlowOperateCenter):
        user_id = op.user_name
        plan_name = op.plan_name
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
        await cls.update_plan_status(plan_name, user_id, op)

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
                 "status": "complete", "need_calculate": True, "quantity": product["quantity"], "real_quantity": product["quantity"],
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
    async def get_plan_tableview_data(cls, op: ConfigFlowOperateCenter):
        """
        获取计划表格视图数据
        """
        user_name = op.user_name
        plan_name = op.plan_name
        plan_obj = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(user_name, plan_name)
        plan_settings = plan_obj.settings

        # 定义原材料大类
        material_type = ["矿石", "冰矿产物", "燃料块", "元素", "气云", "行星工业", "杂货"]

        node_dict = {
            node['type_id']: node for node in await NIU.get_user_plan_node_with_distance(user_name, plan_name)
        }

        # 更新关系中的数据
        # 工作，材料需求
        job_deal_set = set()
        stock_deal_set = set()
        running_job_deal_set = set()
        relations = await NIU.get_user_plan_relation(user_name, plan_name)
        await tqdm_manager.add_mission(f"收集关系数据 {plan_name}", len(relations))
        for relation in relations:
            relation_need_calculate = relation.get("need_calculate", None)
            # if not relation['need_calculate']:
            #     continue
            material_id = relation['material']
            product_id = relation['product']
            await tqdm_manager.update_mission(f"收集关系数据 {plan_name}", 1)
            node_dict[material_id].update({
                "quantity": node_dict[material_id].get('quantity', 0) + relation['quantity'],
                "real_quantity": node_dict[material_id].get('real_quantity', 0) + relation['real_quantity'],
            })
            # 考虑"root"节点情况
            # if product_id in node_dict:
                
            # 每个节点考虑一次库存, 存储当前库存，统计流程数量,记录运行中的任务
            # 考虑material库存, 每个 material_id 只处理一次
            if material_id not in stock_deal_set:
                stock_deal_set.add(material_id)
                if plan_settings['considerate_asset']:
                    material_assets_quantity = await op.get_type_assets_quantity(material_id)
                    node_dict[material_id]["store_quantity"] = material_assets_quantity
                    node_dict[material_id]["real_quantity"] = node_dict[material_id].get("real_quantity", 0) - material_assets_quantity
            
            # 处理product库存 每个 product_id 只处理一次
            if product_id not in stock_deal_set and product_id in node_dict:
                stock_deal_set.add(product_id)
                # 考虑库存
                if plan_settings['considerate_asset']:
                    product_assets_quantity = await op.get_type_assets_quantity(product_id)
                    node_dict[product_id]["store_quantity"] = product_assets_quantity
                    node_dict[product_id]["real_quantity"] = node_dict[product_id].get("real_quantity", 0) - product_assets_quantity
            
            # 处理product任务 每个 (product_id, index_id) 只处理一次
            if (product_id, relation["index_id"]) not in job_deal_set and product_id in node_dict:
                job_deal_set.add((product_id, relation["index_id"]))
                if relation_need_calculate:
                    job_list = json.loads(relation['job_list'])
                    real_job_list = json.loads(relation['real_job_list'])
                    node_dict[product_id].update({
                        "jobs": node_dict[product_id].get('jobs', 0) + sum(work['runs'] for work in job_list),
                        "real_jobs": node_dict[product_id].get('real_jobs', 0) + sum(work['runs'] for work in real_job_list),
                    })

            # 记录product运行中的任务, 每个 product_id 只处理一次
            if plan_settings['considerate_running_job']:
                if product_id not in running_job_deal_set and product_id in node_dict:
                    running_job_deal_set.add(product_id)
                    running_jobs = await op.get_running_job_count(product_id)
                    unfinish_output = running_jobs * relation['product_num']
                    node_dict[product_id]['running_jobs'] = f"{unfinish_output:,}({running_jobs}x{relation['product_num']})" if unfinish_output > 0 else 0
        await tqdm_manager.complete_mission(f"收集关系数据 {plan_name}")

        # 统计完缺失后，计算冗余量
        await tqdm_manager.add_mission(f"计算冗余量 统计运行中任务 {plan_name}", len(node_dict))
        for node in node_dict.values():
            node["real_quantity"] = node.get("real_quantity", 0)
            node["redundant"] = - node["real_quantity"] if node["real_quantity"] < 0 else 0
            node["real_quantity"] = node["real_quantity"] if node['real_quantity'] > 0 else 0

            await tqdm_manager.update_mission(f"计算冗余量 统计运行中任务 {plan_name}", 1)
        await tqdm_manager.complete_mission(f"计算冗余量 统计运行中任务 {plan_name}")

        # 根据距离根节点的距离分类
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
        await tqdm_manager.add_mission(f"分类节点 {plan_name}", len(node_dict))
        for node in node_dict.values():
            node['tpye_name_zh'] = SdeUtils.get_cn_name_by_id(node['type_id'])
            if op.get_node_type(node['type_id']) != "product":
                material_type_node = await cls._get_material_type(node)
                material_output[material_type_node]['children'].append(node)
            else:
                flow_output[node['max_distance'] - 1]["children"].append(node)
            await tqdm_manager.update_mission(f"分类节点 {plan_name}", 1)
        await tqdm_manager.complete_mission(f"分类节点 {plan_name}")

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
        type_name = SdeUtils.get_cn_name_by_id(type_id)
        await tqdm_manager.add_mission(f"create_plan_bp_tree_{type_id}_{type_name}_nodes", len(nodes_dict))
        await tqdm_manager.add_mission(f"create_plan_bp_tree_{type_id}_{type_name}_relationships", len(relationships_list))

        # 2. 创建PlanBlueprint节点树
        # 首先创建所有PlanBlueprint节点
        tasks = []
        async def merge_node_with_semaphore(plan_bp_index, plan_bp_properties):
            async with neo4j_manager.semaphore:
                await NIU.merge_node("PlanBlueprint", plan_bp_index, plan_bp_properties)
                await tqdm_manager.update_mission(f"create_plan_bp_tree_{type_id}_{type_name}_nodes", 1)
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
                await tqdm_manager.update_mission(f"create_plan_bp_tree_{type_id}_{type_name}_relationships", 1)

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

        await tqdm_manager.complete_mission(f"create_plan_bp_tree_{type_id}_{type_name}_nodes")
        await tqdm_manager.complete_mission(f"create_plan_bp_tree_{type_id}_{type_name}_relationships")

    @classmethod
    async def _relation_calculater(cls, plan_settings: dict, relation: dict, product_node_in_relation: List[dict], same_route_relations: List[dict]):
        op = plan_settings["operate_center"]

        self_relation = relation['relation']
        product_type_id = self_relation['product']
        material_type_id = self_relation['material']
        self_index_id = self_relation['index_id']
        self_order_id = self_relation['order_id']
        order_index = [relation['relation']['order_id'] for relation in same_route_relations].index(self_order_id)
        
        op.calculate_cache[(product_type_id, material_type_id, self_index_id)] = op.calculate_cache.get((product_type_id, material_type_id, self_index_id), 0) + 1

        # for relation in product_node_in_relation:
        #     if "quantity" not in relation['relation']:
        #         break

        # 判断是否需要计算 ==============================================================================================
        if not await op.get_relation_need_calculate(product_type_id):
            await NIU.update_relation_properties(
                "PLAN_BP_DEPEND_ON",
                {
                    "user_name": self_relation['user_name'],
                    "plan_name": self_relation["plan_name"],
                    "index_id": self_relation['index_id'],
                    "product": self_relation['product'],
                    "material": self_relation['material']
                },
                {
                    "quantity": 0,
                    "real_quantity": 0,
                    "index_quantity_work": 0,
                    "index_real_quantity_work": 0,
                    "product_remain": 0,
                    "real_product_remain": 0,
                    "real_work_remain": 0,
                    "status": "complete",
                    "need_calculate": False
                }
            )
            return
        
        # 收集父节点需求数量 ==============================================================================================
        all_index_quantity = sum([relation['relation']['quantity'] for relation in product_node_in_relation])
        all_index_real_quantity = sum([relation['relation']['real_quantity'] for relation in product_node_in_relation])
        self_index_quantity = sum([relation['relation']['quantity'] for relation in product_node_in_relation if relation['relation']['index_id'] == self_index_id])
        self_index_real_quantity = sum([relation['relation']['real_quantity'] for relation in product_node_in_relation if relation['relation']['index_id'] == self_index_id])

        # 对real_quantity进行处理，去掉库存和生产数量
        # quantity 代表总需求， real_quantity代表从上层传导下来的实际需求， 用quantity减去real是缺失
 
        # 库存 数量处理 ==============================================================================================
        
        if plan_settings['considerate_asset']:
            self_index_real_quantity = await op.deal_asset_quantity(self_index_real_quantity, product_type_id, self_index_id)
            all_index_real_quantity -= await op.get_type_assets_quantity(product_type_id)
        #     product_asset_quantity = await op.get_type_assets_quantity(product_type_id)
        #     self_index_real_quantity = self_index_real_quantity - product_asset_quantity

        # 运行中任务生产 数量处理 ==============================================================================================
        
        if plan_settings['considerate_running_job']:
            self_index_real_quantity = await op.deal_running_job_quantity(self_index_real_quantity, product_type_id, self_index_id)
            all_index_real_quantity -= await op.get_running_job_count(product_type_id)
        #     running_jobs_runs = await op.get_running_job_count(product_type_id)
        #     running_jobs_unfinish_output = running_jobs_runs * self_relation['product_num']
        #     self_index_real_quantity = self_index_real_quantity - running_jobs_unfinish_output

        if order_index == 0:
            last_order_index_remain = 0
            last_order_index_real_remain = 0
        else:
            last_order_index_remain = same_route_relations[order_index-1]['relation']['product_remain']
            last_order_index_real_remain = same_route_relations[order_index-1]['relation']['real_product_remain']

        # 计算最小流程
        min_all_index_quantity_work = ceil(all_index_quantity / self_relation['product_num'])
        min_all_index_real_quantity_work = ceil(all_index_real_quantity / self_relation['product_num'])
        min_self_index_quantity_work = ceil((self_index_quantity - last_order_index_remain) / self_relation['product_num'])
        min_self_index_real_quantity_work = ceil((self_index_real_quantity - last_order_index_real_remain) / self_relation['product_num'])
        # 剩余未分配流程
        if order_index == 0:
            real_all_index_remain_work = min_all_index_real_quantity_work
        else:
            real_all_index_remain_work = same_route_relations[order_index-1]['relation']['real_work_remain']

        # 根据配置 切分工作流 or 不切分 ==============================================================================================
        real_work_list = []
        if plan_settings['split_to_jobs']:
            max_job_run = await op.get_max_job_run(product_type_id)


            real_work_waiting_to_split = min_self_index_real_quantity_work
            while real_work_waiting_to_split > 0:
                # 决定本轮需要安排的流程数
                #   如果考虑蓝图，向op申请一张蓝图对象
                #   如果不考虑蓝图，申请一张假原图对象

                #   如果是whole, 取min(蓝图支持的流程， min_all_index_real_quantity_work, max_job_run)
                #   如果是in_order, 取min(蓝图支持的流程， real_work_waiting_to_split, max_job_run)
                #       如果bpc不切分，则上两个min不考虑max_job_run
                bp = await op.get_bp_object(product_type_id, plan_settings['considerate_bp_relation'])

                if bp['fake'] or bp["quantity"] == -1:
                    bp_support_runs = max_job_run
                else:
                    bp_support_runs = bp["runs"]
                if plan_settings["full_use_bp_cp"] and bp["runs"] != -1:
                    max_job_run = bp_support_runs

                if plan_settings["work_type"] == "whole":
                    this_round_work = min(bp_support_runs, real_all_index_remain_work, max_job_run)
                elif plan_settings["work_type"] == "in_order":
                    this_round_work = min(bp_support_runs, real_work_waiting_to_split, max_job_run)

                real_work_list.append({
                    "type_id": product_type_id,
                    "runs": this_round_work,
                    "bp_object": bp
                })
                real_work_waiting_to_split -= this_round_work
                real_all_index_remain_work -= this_round_work
        else:
            real_work_list = [{
                "type_id": product_type_id,
                "runs": min_self_index_real_quantity_work,
                "bp_object": await op.get_bp_object(product_type_id, False)
            }]
        job_list = [{
            "type_id": product_type_id,
            "runs": min_self_index_quantity_work,
            "bp_object": await op.get_bp_object(product_type_id, False)
        }]

        # 计算多余数量 ==============================================================================================
        real_product_quantity = self_relation['product_num'] * sum([work['runs'] for work in real_work_list])
        product_quantity = self_relation['product_num'] * sum([work['runs'] for work in job_list])
        self_product_remain = product_quantity - self_index_quantity + last_order_index_remain
        self_real_product_remain = real_product_quantity - self_index_real_quantity + last_order_index_real_remain

        # 根据系数计算工作流需要的材料数量 ==============================================================================================
        mater_eff, time_eff = await op.get_efficiency(product_type_id)
        fake_mater_eff, fake_time_eff = await op.get_conf_eff(product_type_id)

        real_quantity_material_need_list = [
            ceil(
                work['runs'] * self_relation['material_num'] * mater_eff *
                (fake_mater_eff if work['bp_object']['fake'] else (1 - 0.01 * work['bp_object']['material_efficiency']))
            ) for work in real_work_list
        ]
        activety_time = await BPM.get_production_time(product_type_id)
        real_quantity_time_need_list = [
            ceil(
                work['runs'] * activety_time * time_eff *
                (fake_time_eff if work['bp_object']['fake'] else (1 - 0.01 * work['bp_object']['time_efficiency']))
            ) for work in real_work_list
        ]
        quantity_material_need_list = [
            ceil(
                work['runs'] * self_relation['material_num'] * mater_eff *
                (fake_mater_eff if work['bp_object']['fake'] else (1 - 0.01 * work['bp_object']['material_efficiency']))
            ) for work in job_list
        ]
        quantity_material_need = sum(quantity_material_need_list)
        real_quantity_material_need = sum(real_quantity_material_need_list)
        real_quantity_time_need = sum(real_quantity_time_need_list)

        # TODO 系数成本计算 ==============================================================================================

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
                "real_work_remain": real_all_index_remain_work,
                "job_list": json.dumps(job_list),
                "real_job_list": json.dumps(real_work_list),
                "status": "complete",
                "need_calculate": True
            }
        )

        logger.debug(f"relation index {self_relation['index_id']} {self_relation['product']}->{self_relation['material']} calculate complete")
        await tqdm_manager.update_mission("relation_moniter_process", 1)

    @classmethod
    async def _is_update_complete(cls, user_name: str, plan_name: str):
        all_relation_list = await NIU.get_relations("PLAN_BP_DEPEND_ON", {"user_name": user_name, "plan_name": plan_name})
        for relation in all_relation_list:
            if relation['relation']['status'] != "complete":
                return False
        return True

    @classmethod
    async def _is_relation_calculate_avaliable(cls, relation: dict) -> Tuple[bool, List[dict], List[dict], dict]:
        self_relation = relation['relation']
        if self_relation['status'] == "complete":
            return False, [], [], relation
        self_index_id = self_relation['index_id']
        self_order_id = self_relation['order_id']

        same_route_relations = await NIU.get_relations(
            "PLAN_BP_DEPEND_ON",
            {
                "user_name": self_relation['user_name'],
                "plan_name": self_relation["plan_name"],
                "product": self_relation['product'],
                "material": self_relation['material']
                }
        )
        same_route_relations.sort(key=lambda x: x['relation']['order_id'])
        for i, relation in enumerate(same_route_relations):
            if i == 0:
                if relation['relation']['order_id'] == self_order_id:
                    break
                elif relation['relation']['status'] != "complete":
                    return False, [], [], relation
            else:
                if relation['relation']['order_id'] == self_order_id:
                    if same_route_relations[i-1]['relation']['status'] == "complete":
                        break
                    else:
                        return False, [], [], relation
                
        product_node_in_relation = await NIU.get_relations(
            "PLAN_BP_DEPEND_ON",
            {"user_name": self_relation['user_name'], "plan_name": self_relation["plan_name"]},
            target_label="PlanBlueprint",
            target_index={"type_id": self_relation['product']}
        )
        for r in product_node_in_relation:
            if r['relation']['status'] != "complete":
                return False, [], [], relation
        return True, product_node_in_relation, same_route_relations, relation

    @classmethod
    async def _relation_moniter_process(cls, user_name: str, plan_name: str, op: ConfigFlowOperateCenter):
        plan_node = await NIU.get_node_properties("Plan", {"user_name": user_name, "plan_name": plan_name})
        plan_settings = json.loads(plan_node['plan_settings'])
        plan_settings["operate_center"] = op
        all_relation_list = await NIU.get_relations("PLAN_BP_DEPEND_ON", {"user_name": user_name, "plan_name": plan_name})

        async def relation_calculater_with_semaphore(relation: dict, product_node_in_relation: List[dict], same_route_relations: List[dict]):
            async with neo4j_manager.semaphore:
                await cls._relation_calculater(plan_settings, relation, product_node_in_relation, same_route_relations)

        await tqdm_manager.add_mission("relation_moniter_process", len(all_relation_list))
        
        # finished_relation_set = set()
        while not await cls._is_update_complete(user_name, plan_name):
            check_tasks = [
                asyncio.create_task(cls._is_relation_calculate_avaliable(relation)) for relation in all_relation_list
            ]
            check_results = await asyncio.gather(*check_tasks)
            
            calculate_tasks = [
                asyncio.create_task(relation_calculater_with_semaphore(relation, product_node_in_relation, same_route_relations))
                for res, product_node_in_relation, same_route_relations, relation in check_results if res == True
            ]
            await asyncio.gather(*calculate_tasks)
            all_relation_list = await NIU.get_relations("PLAN_BP_DEPEND_ON", {"user_name": user_name, "plan_name": plan_name})
        await tqdm_manager.complete_mission("relation_moniter_process")
        logger.info(f"plan {plan_name} status update complete")

    @classmethod
    async def update_plan_status(cls, plan_name: str, user_name: str, op: ConfigFlowOperateCenter):
        await cls._relation_moniter_process(user_name, plan_name, op)

    @classmethod
    async def add_industrypermision(cls, user_id: str, data):
        container_data = data['container']
        asset_data = data['asset']
        structure_data = data['structure']
        system_data = data['system']

        async for container in await EveIndustryAssetContainerPermissionDBUtils.select_all_by_user_name(user_id):
            if container.asset_container_id == container_data['item_id']:
                raise KahunaException(f"容器 {container_data['item_id']} 已存在")

        permission_obj = EveIndustryAssetContainerPermissionDBUtils.get_obj()
        permission_obj.user_name = user_id
        permission_obj.asset_owner_id = asset_data['owner_id']
        permission_obj.asset_container_id = container_data['item_id']
        permission_obj.structure_id = structure_data['structure_id']
        permission_obj.system_id = system_data['system_id']
        permission_obj.tag = data['tag']
        await EveIndustryAssetContainerPermissionDBUtils.save_obj(permission_obj)

    @classmethod
    async def delete_industrypermision(cls, user_id: str, data):
        asset_owner_id = data['asset_owner_id']
        asset_container_id = data['asset_container_id']

        async for permission in await EveIndustryAssetContainerPermissionDBUtils.select_all_by_user_name(user_id):
            if permission.asset_owner_id == asset_owner_id and permission.asset_container_id == asset_container_id:
                await EveIndustryAssetContainerPermissionDBUtils.delete_obj(permission)
                return
        raise KahunaException(f"许可不存在")
    
    @classmethod
    async def get_user_all_container_permission(cls, user_id: str):
        all_container_permission = []
        async for container in await EveIndustryAssetContainerPermissionDBUtils.select_all_by_user_name(user_id):
            pull_mission = await EveAssetPullMissionDBUtils.select_mission_by_owner_id(container.asset_owner_id)
            if not pull_mission:
                continue
            access_character = await CharacterManager().get_character_by_character_id(pull_mission.access_character_id)
            owner_type = pull_mission.asset_owner_type
            if owner_type == 'character':
                owner = await eveesi.characters_character(pull_mission.asset_owner_id)
                owner_name = owner['name']
            elif owner_type == 'corp':
                owner = await eveesi.corporations_corporation_id(pull_mission.asset_owner_id)
                owner_name = owner['name']
            system_info = SdeUtils.get_system_info_by_id(container.system_id)
            structure_info_cache = await redis_manager.redis.hgetall(f'eveesi:universe_structures_structure:{container.structure_id}')
            if not structure_info_cache:
                structure_info_cache = await eveesi.universe_structures_structure(access_character.ac_token, container.structure_id)
                structure_info_cache.pop("position")
                await redis_manager.redis.hset(f'eveesi:universe_structures_structure:{container.structure_id}', mapping=structure_info_cache)
            
            container = {
                "asset_owner_id": container.asset_owner_id,
                "asset_container_id": container.asset_container_id,
                "structure_id": container.structure_id,
                "structure_name": structure_info_cache['name'],
                "system_id": container.system_id,
                "system_name": system_info['system_name'],
                "owner_type": owner_type,
                "owner_name": owner_name,
                "tag": container.tag,
            }
            all_container_permission.append(container)


        return all_container_permission

    @classmethod
    async def get_structure_list(cls):
        structure_list = await NAU.get_structure_nodes()
        res = [
            {
                "structure_id": structure["structure_id"],
                "structure_name": structure["structure_name"],
            } for structure in structure_list
        ]
        return res

    @classmethod
    async def get_structure_assign_keyword_suggestions(cls, assign_type: str):
        output = []
        SdeUtils
        if assign_type == 'group':
            output.extend([{"value": res.groupName, "label": res.groupName} for res in InvGroups.select(InvGroups.groupName)])
            output.extend([{"value": res.groupName, "label": res.groupName} for res in InvGroups_zh.select(InvGroups_zh.groupName)])
        elif assign_type == 'meta':
            output.extend([{"value": res.nameID, "label": res.nameID} for res in MetaGroups.select(MetaGroups.nameID)])
            output.extend([{"value": res.nameID, "label": res.nameID} for res in MetaGroups_zh.select(MetaGroups_zh.nameID)])
        elif assign_type == 'blueprint':
            query = (IndustryBlueprints
                    .select(InvTypes.typeName)
                    .join(InvTypes, on=(IndustryBlueprints.blueprintTypeID == InvTypes.typeID))
                    .where(InvTypes.marketGroupID != None))
            output.extend([{"value": res.invtypes.typeName, "label": res.invtypes.typeName} for res in query])
            query_zh = (IndustryBlueprints_zh
                       .select(InvTypes_zh.typeName)
                       .join(InvTypes_zh, on=(IndustryBlueprints_zh.blueprintTypeID == InvTypes_zh.typeID))
                       .where(InvTypes_zh.marketGroupID != None))
            output.extend([{"value": res.invtypes.typeName, "label": res.invtypes.typeName} for res in query_zh])
        elif assign_type == 'marketGroup':
            output.extend([{"value": res.nameID, "label": res.nameID} for res in MarketGroups.select(MarketGroups.nameID)])
            output.extend([{"value": res.nameID, "label": res.nameID} for res in MarketGroups_zh.select(MarketGroups_zh.nameID)])
        elif assign_type == 'category':
            output.extend([{"value": res.categoryName, "label": res.categoryName} for res in InvCategories.select(InvCategories.categoryName)])
            output.extend([{"value": res.categoryName, "label": res.categoryName} for res in InvCategories_zh.select(InvCategories_zh.categoryName)])

        return output

    @classmethod
    async def get_type_list(cls):
        output = []
        output.extend([{"value": res.typeName, "label": res.typeName} for res in InvTypes.select(InvTypes.typeName)])
        output.extend([{"value": res.typeName, "label": res.typeName} for res in InvTypes_zh.select(InvTypes_zh.typeName)])
        return output

    @classmethod
    async def create_config_flow_config(cls, user_id: str, data):
        config_obj = EveIndustryPlanConfigFlowConfigDBUtils.get_obj()
        config_obj.user_name = user_id
        config_obj.config_type = data['config_type']
        config_obj.config_value = data['config_value']
        await EveIndustryPlanConfigFlowConfigDBUtils.save_obj(config_obj)

    @classmethod
    async def get_config_flow_config_list(cls, user_id: str):
        res_list = []
        async for config in await EveIndustryPlanConfigFlowConfigDBUtils.select_all_by_user_name(user_id):
            res_list.append({
                "config_id": config.id,
                "config_type": config.config_type,
                "config_value": config.config_value
            })
        return res_list

    @classmethod
    async def add_config_to_plan(cls, user_id: str, data):
        plan_name = data['plan_name']
        config_id = data['config_id']
        config = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_id(config_id)
        if not config:
            raise KahunaException(f"配置不存在")
        plan_config_obj = await EveIndustryPlanConfigFlowDBUtils.select_configflow_by_user_name_and_plan_name(user_id, plan_name)
        if not plan_config_obj:
            plan_config_obj = EveIndustryPlanConfigFlowDBUtils.get_obj()
            plan_config_obj.user_name = user_id
            plan_config_obj.plan_name = plan_name
            plan_config_obj.config_list = [config_id]
            await EveIndustryPlanConfigFlowDBUtils.save_obj(plan_config_obj)
        else:
            if config_id in plan_config_obj.config_list:
                raise KahunaException(f"配置已存在")
            plan_config_obj.config_list.insert(0, config_id)
            await EveIndustryPlanConfigFlowDBUtils.merge(plan_config_obj)

    @classmethod
    async def get_config_flow_list(cls, user_id: str, plan_name: str):
        plan_config_flow_obj = await EveIndustryPlanConfigFlowDBUtils.select_configflow_by_user_name_and_plan_name(user_id, plan_name)
        if not plan_config_flow_obj:
            return []

        config_id_list = plan_config_flow_obj.config_list
        config_list = []
        for config_id in config_id_list:
            config = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_id(config_id)
            if not config:
                raise KahunaException(f"配置{config_id}不存在")
            config_list.append({
                "config_id": config.id,
                "config_type": config.config_type,
                "config_value": config.config_value
            })
            if config.config_type == 'StructureRigConfig':
                structure_info = await NIU.get_structure_node_by_id(config.config_value['structure_id'])
                config_list[-1]['config_value']['structure_name'] = structure_info.get('structure_name', None)
            logger.info(type(config.config_value))
            logger.info(config.config_value)
        return config_list

    @classmethod
    async def delete_config_from_plan(cls, user_id: str, data):
        plan_name = data['plan_name']
        config_id = data['config_id']
        plan_config_flow_obj = await EveIndustryPlanConfigFlowDBUtils.select_configflow_by_user_name_and_plan_name(user_id, plan_name)
        if not plan_config_flow_obj:
            raise KahunaException(f"配置不存在")
        plan_config_flow_obj.config_list.remove(config_id)
        await EveIndustryPlanConfigFlowDBUtils.merge(plan_config_flow_obj)

    @classmethod
    async def save_config_flow_to_plan(cls, user_id: str, plan_name: str, data):
        config_id_list = [d["config_id"] for d in data["config_list"]]
        config_flow_obj = await EveIndustryPlanConfigFlowDBUtils.select_configflow_by_user_name_and_plan_name(user_id, plan_name)
        if not config_flow_obj:
            config_flow_obj = EveIndustryPlanConfigFlowDBUtils.get_obj()
            config_flow_obj.user_name = user_id
            config_flow_obj.plan_name = plan_name
            config_flow_obj.config_list = config_id_list
            await EveIndustryPlanConfigFlowDBUtils.save_obj(config_flow_obj)
        else:
            config_flow_obj.config_list = config_id_list
            await EveIndustryPlanConfigFlowDBUtils.merge(config_flow_obj)

    @classmethod
    async def get_item_info(cls, type_id: int):
        return {
            "type_id": type_id,
            "type_name": SdeUtils.get_name_by_id(type_id),
            "type_name_zh": SdeUtils.get_cn_name_by_id(type_id),
            "meta": SdeUtils.get_metaname_by_typeid(type_id),
            "group": SdeUtils.get_groupname_by_id(type_id),
            "market_group_list": "-".join(SdeUtils.get_market_group_list(type_id))
        }

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