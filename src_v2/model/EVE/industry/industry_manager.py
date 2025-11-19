# 标准库导入
import asyncio
from copy import deepcopy
import json
from asyncio import Queue
from enum import Flag
from itertools import product
from math import ceil, sqrt
from typing import Dict, List, Tuple

# 本地导入 - 核心工具
from src_v2.core.database.connect_manager import (
    neo4j_manager,
    postgres_manager,
    redis_manager as rdm
)
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveAssetPullMissionDBUtils,
    EveIndustryAssetContainerPermissionDBUtils,
    EveIndustryPlanConfigFlowConfigDBUtils,
    EveIndustryPlanConfigFlowDBUtils,
    EveIndustryPlanDBUtils,
    EveIndustryPlanProductDBUtils
)
from src_v2.core.database.neo4j_utils import (
    Neo4jAssetUtils as NAU,
    Neo4jIndustryUtils as NIU
)
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException, SingletonMeta, tqdm_manager

# 本地导入 - EVE 模块
from src_v2.model.EVE.character import CharacterManager
from src_v2.model.EVE.eveesi import eveesi
from src_v2.model.EVE.market.market_manager import MarketManager
from src_v2.model.EVE.sde import SdeUtils
from src_v2.model.EVE.sde.database import InvTypes, MarketGroups

# 本地导入 - 相对导入
from .blueprint import BPManager as BPM
from .plan_configflow_operate import ConfigFlowOperateCenter

# 本地导入 - industry_utils 工具模块
from .industry_utils import (
    AsyncCounter,
    MarketTree,
    get_market_tree,
    create_config_flow_config,
    fetch_recommended_presets,
    delete_config_flow_config,
    get_config_flow_config_list,
    add_config_to_plan,
    get_config_flow_list,
    delete_config_from_plan,
    save_config_flow_to_plan,
    add_industrypermision,
    delete_industrypermision,
    get_user_all_container_permission,
    get_structure_list,
    get_structure_assign_keyword_suggestions,
    get_material_type,
    get_item_info,
    get_type_list
)



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
            logger.info(f"获取计划表格数据: {product.plan_name} {product.product_type_id} {product.quantity}")
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
        user_plan_obj = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(user_id, plan_name)
        if not user_plan_obj:
            raise KahunaException(f"计划不存在")
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
        await rdm.r.set(op.total_progress_key, 0)
        await rdm.r.hset(op.current_progress_key, mapping={"name": "开始计算", "progress": 0})

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
        
        await rdm.r.hset(op.current_progress_key, mapping={"name": "删除计划", "progress": 100})
        await cls.delete_plan(plan_name, user_id)
        await rdm.r.set(op.total_progress_key, 20)
        
        await rdm.r.hset(op.current_progress_key, mapping={"name": "创建计划节点", "progress": 100})
        await cls.create_plan_node(plan_data)
        await rdm.r.set(op.total_progress_key, 40)

        await rdm.r.hset(op.current_progress_key, mapping={"name": "创建计划树", "progress": 0})
        await cls.create_plan_tree(plan_data, op)
        await rdm.r.set(op.total_progress_key, 60)

        await rdm.r.hset(op.current_progress_key, mapping={"name": "更新树状态", "progress": 0})
        await cls.update_plan_status(plan_name, user_id, op)
        await rdm.r.set(op.total_progress_key, 80)

        await rdm.r.hset(op.current_progress_key, mapping={"name": "数据汇总", "progress": 0})
        result_data = await IndustryManager.get_plan_tableview_data(op)
        await rdm.r.set(op.total_progress_key, 100)
        return result_data

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
    async def create_plan_tree(cls, plan_data: dict, op: ConfigFlowOperateCenter):
        plan_name = plan_data["plan_name"]
        user_name = plan_data["user_name"]
        products = plan_data["products"]
        plan_user_dict = {"plan_name": plan_name, "user_name": user_name}
        counter = AsyncCounter()

        op.index_product_dict = {product["index_id"]: product["product_type_id"] for product in products}
        op.product_num_dict = {product["product_type_id"]: product["quantity"] for product in products}

        last_progress = 0
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
                {**plan_user_dict, "type_id": product["product_type_id"], "order_id": await counter.next_node()}
            )
            await cls._create_plan_bp_tree(plan_user_dict, product, counter)
            mission_count = await tqdm_manager.update_mission(f"create_plan_{plan_name}", 1)
            now_progress = mission_count / len(products) * 100
            if now_progress > last_progress + 10:
                await rdm.r.hset(op.current_progress_key, mapping={"name": "创建计划树", "progress": now_progress})
                last_progress = now_progress

            # index_root节点更新需求数量，更新状态为finished.
        await tqdm_manager.complete_mission(f"create_plan_{plan_name}")

    @classmethod
    async def delete_plan(cls, plan_name: str, user_name: str):
        await NIU.delete_tree(
            "Plan",
            {"plan_name": plan_name, "user_name": user_name},
            "PLAN_BP_DEPEND_ON")

    @classmethod
    async def _get_material_type(cls, type_id: int):
        """获取材料类型（内部方法，调用工具模块）"""
        return await get_material_type(type_id)

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

        await rdm.r.hset(op.current_progress_key, mapping={"name": "获取路径数据", "progress": 50, "is_indeterminate": 1})
        logger.info("收集路径深度")
        node_dict = {
            node['type_id']: node for node in await NIU.get_user_plan_node_with_distance(user_name, plan_name)
        }

        # 获取材料报价
        await rdm.r.hset(op.current_progress_key, mapping={"name": "获取材料报价", "progress": 50, "is_indeterminate": 1})
        await MarketManager().update_jita_price()

        job_deal_set = set()
        logger.info("收集关系数据")
        
        relations = await NIU.get_user_plan_relation(user_name, plan_name)
        await tqdm_manager.add_mission(f"收集关系数据 {plan_name}", len(relations))
        await rdm.r.hset(op.current_progress_key, mapping={"name": "收集关系数据", "progress": 0, "is_indeterminate": 1})
        last_progress = 0
        eiv_cost_dict = {}
        for relation in relations:
            relation_need_calculate = relation.get("need_calculate", None)

            # 汇总材料节点计算后真实需求数量【缺失】
            material_id = relation['material']
            product_id = relation['product']
            await tqdm_manager.update_mission(f"收集关系数据 {plan_name}", 1)
            node_dict[material_id].update({
                "quantity": node_dict[material_id].get('quantity', 0) + relation['quantity'],
                "real_quantity": node_dict[material_id].get('real_quantity', 0) + relation['real_quantity'],
            })

            # 汇总产品节点的eiv成本
            if product_id in node_dict:
                top_product_type_id = op.index_product_dict[relation["index_id"]]
                if top_product_type_id not in eiv_cost_dict:
                    eiv_cost_dict[top_product_type_id] = {
                        "eiv_cost": 0,
                        "type_id": top_product_type_id,
                        "type_name": SdeUtils.get_name_by_id(top_product_type_id),
                        "index_id": relation["index_id"],
                        "product_num": op.product_num_dict[top_product_type_id],
                        "children": [],
                    }
                # 所有边的eiv_cost汇总到最上层节点
                eiv_cost_dict[top_product_type_id].update({
                    "eiv_cost": eiv_cost_dict[top_product_type_id].get('eiv_cost', 0) + relation['real_eiv_cost_total'],
                })
                if op.get_node_type(relation['material']) != "product":
                    material_type_node = await cls._get_material_type(relation['material'])
                    jita_buy_price = await rdm.r.hget(f"market:price:jita:{relation['material']}", "max_buy")
                    eiv_cost_dict[top_product_type_id]['children'].append({
                        "type_id": relation['material'],
                        "type_name": SdeUtils.get_name_by_id(relation['material']),
                        "index_id": relation["index_id"],
                        "quantity": relation['quantity'],
                        "jita_buy_price": jita_buy_price if jita_buy_price else 0,
                        "material_type_node": material_type_node,
                    })
            
            # 汇总产品节点计算后真实任务数据【job】
            # 处理product任务 每个 (product_id, index_id) 只处理一次
            if (product_id, relation["index_id"]) not in job_deal_set and product_id in node_dict:
                job_deal_set.add((product_id, relation["index_id"]))
                if relation_need_calculate:
                    real_job_list,job_list = op.work_list_cache[(product_id, relation["index_id"])]
                    node_dict[product_id].update({
                        "jobs": node_dict[product_id].get('jobs', 0) + sum(work['runs'] for work in job_list),
                        "real_jobs": node_dict[product_id].get('real_jobs', 0) + sum(work['runs'] for work in real_job_list),
                        "real_job_list": node_dict[product_id].get('real_job_list', []) + real_job_list,
                    })
        await tqdm_manager.complete_mission(f"收集关系数据 {plan_name}")

        # 获取库存和冗余
        logger.info("获取库存和冗余")
        for node in node_dict.values():
            # 计算库存
            type_id = node['type_id']
            if plan_settings.get('considerate_asset', False):
                product_assets_quantity = await op.get_type_assets_quantity(type_id)
                node["store_quantity"] = product_assets_quantity
                node['real_quantity'] -= product_assets_quantity

            # 计算运行中任务产物
            if plan_settings.get('considerate_running_job', False):
                running_jobs = await op.get_running_job_count(type_id)
                unfinish_output = running_jobs * await BPM.get_bp_product_quantity_typeid(type_id)
                node['real_quantity'] -= unfinish_output
                node['running_jobs'] = f"{unfinish_output:,}({running_jobs}x{await BPM.get_bp_product_quantity_typeid(type_id)})" if unfinish_output > 0 else 0

            node["redundant"] = - node['real_quantity'] if node['real_quantity'] < 0 else 0

        # 根据距离根节点的距离分类
        logger.info("根据距离根节点的距离分类")
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

        logger.info("整理节点")
        work_flow = []
        await rdm.r.hset(op.current_progress_key, mapping={"name": "整理节点", "progress": 50, "is_indeterminate": 1})
        await tqdm_manager.add_mission(f"分类节点 {plan_name}", len(node_dict))
        for node in node_dict.values():
            # 整理库存状态
            node['tpye_name_zh'] = SdeUtils.get_cn_name_by_id(node['type_id'])
            if op.get_node_type(node['type_id']) != "product":
                material_type_node = await cls._get_material_type(node['type_id'])
                buy_price = await rdm.r.hget(f"market:price:jita:{node['type_id']}", "max_buy")
                sell_price = await rdm.r.hget(f"market:price:jita:{node['type_id']}", "min_sell")
                node['buy_price'] = buy_price if buy_price else 0
                node['sell_price'] = sell_price if sell_price else 0
                material_output[material_type_node]['children'].append(node)
            else:
                flow_output[node['max_distance'] - 1]["children"].append(node)
            mission_count = await tqdm_manager.update_mission(f"分类节点 {plan_name}", 1)
            now_progress = mission_count / len(node_dict) * 100
            if now_progress / 3 + 66 > last_progress + 10:
                last_progress = now_progress
            
            # 整理工作流输出
            work_flow.extend([{
                    "type_id": work["type_id"],
                    "active_id": await BPM.get_activity_id_by_product_typeid(work["type_id"]),
                    "type_name_zh": SdeUtils.get_cn_name_by_id(work["type_id"]),
                    "type_name": SdeUtils.get_name_by_id(work["type_id"]),
                    "avaliable": work["avaliable"],
                    "runs": work["runs"],
                    "bp_object": work["bp_object"],
                    "type_order_id": node["order_id"],
                    "mater_eff": work["mater_eff"],
                    "time_eff": work["time_eff"],
                } for work in node.get("real_job_list", []) if work
            ])

            # 整理蓝图库存
            await rdm.r.hset(op.current_progress_key, mapping={"name": "整理蓝图库存", "progress": 50, "is_indeterminate": 1})
            node['bp_quantity'], node['bp_jobs'] = await op.get_bp_status(node['type_id'])
        await tqdm_manager.complete_mission(f"分类节点 {plan_name}")
        
        # 整理物流信息
        # 建筑需求
        structure_material_need_dict = {}
        for work in [work for work in work_flow if work['avaliable']]:
            assign_structure_info = await op.get_type_assign_structure_info(work['type_id'])
            if assign_structure_info:
                if assign_structure_info['structure_id'] not in structure_material_need_dict:
                    structure_material_need_dict[assign_structure_info['structure_id']] = deepcopy(assign_structure_info)
                    structure_material_need_dict[assign_structure_info['structure_id']]["material_need"] = {}

                structure_node = structure_material_need_dict[assign_structure_info['structure_id']]
                work_material_need = await op.get_work_material_need(work)
                for material_type_id, material_quantity in work_material_need.items():
                    structure_node["material_need"][material_type_id] = \
                        structure_node["material_need"].get(material_type_id, 0) + material_quantity
        # 建筑供给
        structure_material_provide_dict = await op.get_structure_material_provide_dict()

        # 处理本地库存
        for structure_id, structure_info in structure_material_need_dict.items():
            for material_type_id, material_quantity in structure_info["material_need"].items():
                if structure_info["structure_id"] in structure_material_provide_dict:
                    provide_quantity = structure_material_provide_dict[structure_info["structure_id"]]["material_provide"].get(material_type_id, 0)
                    if provide_quantity >= material_quantity:
                        provide_quantity -= material_quantity
                        material_quantity = 0
                    else:
                        material_quantity -= provide_quantity
                        provide_quantity = 0
                    structure_material_provide_dict[structure_info["structure_id"]]["material_provide"][material_type_id] = provide_quantity
                    structure_info["material_need"][material_type_id] = material_quantity

        # 处理异地建筑供给
        # 计算物流线路
        # 遍历缺少物资的建筑与物资
        logistic_dict = {}
        for lack_structure_id, lack_structure_info in structure_material_need_dict.items():
            for lack_type_id, lack_quantity in lack_structure_info["material_need"].items():
                # 遍历供给的建筑与物资，寻找匹配
                for provide_structure_id, provide_structure_info in structure_material_provide_dict.items():
                    if lack_structure_id == provide_structure_id:
                        continue
                    if lack_quantity <= 0:
                        break
                    if lack_type_id in provide_structure_info["material_provide"]:
                        provide_quantity = provide_structure_info["material_provide"][lack_type_id]
                        if provide_quantity >= lack_quantity:
                            provide_quantity -= lack_quantity
                            lack_quantity = 0
                        else:
                            lack_quantity -= provide_quantity
                            provide_quantity = 0
                        # 匹配成功，更新供给和需求，记录物流线路
                        provide_structure_info["material_provide"][lack_type_id] = provide_quantity
                        lack_structure_info["material_need"][lack_type_id] = lack_quantity
                        if (lack_structure_id, provide_structure_id, lack_type_id) not in logistic_dict:
                            logistic_dict[(lack_structure_id, provide_structure_id, lack_type_id)] = {
                                "provide_quantity": provide_quantity,
                                "provide_structure_info": provide_structure_info,
                                "lack_structure_info": lack_structure_info,
                            }
                        else:
                            logistic_dict[(lack_structure_id, provide_structure_id, lack_type_id)]["provide_quantity"] += provide_quantity
        # 整理为可以持计划的数据
        save_logistic_data = []
        for d, logistic_info in logistic_dict.items():
            lack_structure_id, provide_structure_id, lack_type_id = d
            provide_structure_info = logistic_info["provide_structure_info"]
            lack_structure_info = logistic_info["lack_structure_info"]
            light_year = 9.461e15
            provide_system_info = SdeUtils.get_system_info_by_id(provide_structure_info["system_id"])
            lack_system_info = SdeUtils.get_system_info_by_id(lack_structure_info["system_id"])
            save_logistic_data.append({
                "lack_structure_id": lack_structure_id,
                "lack_structure_name": lack_structure_info["structure_name"],
                "provide_structure_id": provide_structure_id,
                "provide_structure_name": provide_structure_info["structure_name"],
                "provide_system_id": provide_structure_info["system_id"],
                "provide_system_name": provide_structure_info["system_name"],
                "provide_system_coordinate": [provide_system_info["x"] / light_year, provide_system_info["y"] / light_year, provide_system_info["z"] / light_year],
                "lack_system_id": lack_structure_info["system_id"],
                "lack_system_name": lack_structure_info["system_name"],
                "lack_system_coordinate": [lack_system_info["x"] / light_year, lack_system_info["y"] / light_year, lack_system_info["z"] / light_year],
                "provide_system_distance": sqrt(
                    (provide_system_info["x"] - lack_system_info["x"])**2 +
                    (provide_system_info["y"] - lack_system_info["y"])**2 +
                    (provide_system_info["z"] - lack_system_info["z"])**2
                ) / light_year,
                "lack_type_id": lack_type_id,
                "lack_type_name": SdeUtils.get_cn_name_by_id(lack_type_id),
                "provide_quantity": logistic_info["provide_quantity"],
                "provide_volume": SdeUtils.get_volume_by_type_id(lack_type_id) * logistic_info["provide_quantity"],
            })


        # 获取劳动力数据
        await rdm.r.hset(op.current_progress_key, mapping={"name": "获取劳动力数据", "progress": 50, "is_indeterminate": 1})
        running_job_tableview_data = await op.get_running_job_tableview_data()
        

        return {
            "flow_output": flow_output,
            "material_output": [material_output[t] for t in material_type],
            "eiv_cost_dict": eiv_cost_dict,
            "work_flow": work_flow,
            "purchase_output": None,
            "running_job_tableview_data": running_job_tableview_data,
            "logistic_dict": save_logistic_data
        }

    @staticmethod
    async def get_market_tree(node) -> List[Dict]:
        """获取市场树（代理方法，保持向后兼容）"""
        return await get_market_tree(node)

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
                **node_props,
                "order_id": await counter.next_node()
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
                    "real_eiv_cost_total": 0,
                    "need_calculate": False
                }
            )
            await tqdm_manager.update_mission("relation_moniter_process", 1)
            return
        
        # 收集父节点需求数量 ==============================================================================================
        all_index_quantity = sum([relation['relation']['quantity'] for relation in product_node_in_relation])
        all_index_real_quantity = sum([relation['relation']['real_quantity'] for relation in product_node_in_relation])
        self_index_quantity = sum([relation['relation']['quantity'] for relation in product_node_in_relation if relation['relation']['index_id'] == self_index_id])
        self_index_real_quantity = sum([relation['relation']['real_quantity'] for relation in product_node_in_relation if relation['relation']['index_id'] == self_index_id])
        
        # 保存未处理的需求数量用于后期计算冗余
        if product_type_id not in op.node_need_quantity:
            op.node_need_quantity[product_type_id] = all_index_quantity

        # 对real_quantity进行处理，去掉库存和生产数量
        # quantity 代表总需求， real_quantity代表从上层传导下来的实际需求， 用quantity减去real是缺失
 
        # 库存 数量处理 每个(product_type_id, index)只计算一次 ==============================================================================================
        
        if plan_settings.get('considerate_asset', False):
            all_index_real_quantity -= await op.get_type_assets_quantity(product_type_id)
            self_index_real_quantity = await op.deal_asset_quantity(self_index_real_quantity, product_type_id, self_index_id)
        #     product_asset_quantity = await op.get_type_assets_quantity(product_type_id)
        #     self_index_real_quantity = self_index_real_quantity - product_asset_quantity

        # 运行中任务生产 数量处理 每个(product_type_id, index)只计算一次 ==============================================================================================
        
        if plan_settings.get('considerate_running_job', False):
            all_index_real_quantity -= await op.get_running_job_count(product_type_id) * await BPM.get_bp_product_quantity_typeid(product_type_id)
            self_index_real_quantity = await op.deal_running_job_quantity(self_index_real_quantity, product_type_id, self_index_id)
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
        if product_type_id not in op.set_uped_jobs:
            op.set_uped_jobs[product_type_id] = min_all_index_real_quantity_work
        # 剩余未分配流程
        if order_index == 0:
            real_all_index_remain_work = min_all_index_real_quantity_work
        else:
            real_all_index_remain_work = same_route_relations[order_index-1]['relation']['real_work_remain']

        # 获取效率 ==============================================================================================
        mater_eff, time_eff = await op.get_efficiency(product_type_id)
        fake_mater_eff, fake_time_eff = await op.get_conf_eff(product_type_id)

        # 根据配置 切分工作流 or 不切分 每个(product_type_id, index)只计算一次 ==============================================================================================
        real_work_list = []
        if (product_type_id, self_index_id) not in op.work_list_cache:
            op.work_list_cache[(product_type_id, self_index_id)] = ([], [])
            max_job_run = await op.get_max_job_run(product_type_id)
            if plan_settings.get('split_to_jobs', False):
                real_work_waiting_to_split = min_self_index_real_quantity_work
                while real_work_waiting_to_split > 0:
                    # 决定本轮需要安排的流程数
                    #   如果考虑蓝图，向op申请一张蓝图对象
                    #   如果不考虑蓝图，申请一张假原图对象

                    #   如果是whole, 取min(蓝图支持的流程， min_all_index_real_quantity_work, max_job_run)
                    #   如果是in_order, 取min(蓝图支持的流程， real_work_waiting_to_split, max_job_run)
                    #       如果bpc不切分，则上两个min不考虑max_job_run
                    bp = await op.get_bp_object(product_type_id, real_work_waiting_to_split, plan_settings.get('considerate_bp_relation', False))

                    if bp['fake'] or bp["runs"] < 0:
                        bp_support_runs = max_job_run
                    else:
                        bp_support_runs = bp["runs"]

                    if plan_settings.get("full_use_bp_cp", False) and bp["runs"] > 0:
                        max_job_run = bp_support_runs

                    if plan_settings.get("work_type", "whole") == "whole":
                        this_round_work = min(bp_support_runs, op.set_uped_jobs[product_type_id], max_job_run)
                    elif plan_settings.get("work_type", "whole") == "in_order":
                        this_round_work = min(bp_support_runs, real_work_waiting_to_split, max_job_run)

                    real_work_list.append({
                        "type_id": product_type_id,
                        "runs": this_round_work,
                        "bp_object": bp,
                        "mater_eff": mater_eff * (fake_mater_eff if bp['fake'] else (1 - 0.01 * bp['material_efficiency'])),
                        "time_eff": time_eff * (fake_time_eff if bp['fake'] else (1 - 0.01 * bp['time_efficiency'])),
                    })
                    real_work_waiting_to_split -= this_round_work
                    op.set_uped_jobs[product_type_id] -= this_round_work

                # 计算完整任务数量（整除）和剩余工作量（取余）
                # full_job_num: 完整任务的数量（每个任务运行 max_job_run 次）
                # less_work: 剩余的工作量（小于 max_job_run）
                # 注意：ceil() 返回 float，// 运算符如果操作数有 float 则结果也是 float
                # 但 range() 需要 int，所以需要转换为 int
                if max_job_run > 0:
                    full_job_num = int(min_self_index_quantity_work // max_job_run)
                    less_work = int(min_self_index_quantity_work % max_job_run)
                else:
                    # 防止除零错误
                    full_job_num = 0
                    less_work = int(min_self_index_quantity_work)
                
                job_list = [{
                    "type_id": product_type_id,
                    "runs": max_job_run,  # 每个完整任务运行 max_job_run 次
                    "mater_eff": mater_eff * fake_mater_eff,
                    "time_eff": time_eff * fake_time_eff,
                    "bp_object": await op.get_bp_object(product_type_id, max_job_run, False)
                } for _ in range(full_job_num)]
                if less_work > 0:
                    job_list.append({
                        "type_id": product_type_id,
                        "runs": less_work,
                        "mater_eff": mater_eff * fake_mater_eff,
                        "time_eff": time_eff * fake_time_eff,
                        "bp_object": await op.get_bp_object(product_type_id, less_work, False)
                    })
            else:
                real_work_list = [{
                    "type_id": product_type_id,
                    "runs": min_self_index_real_quantity_work,
                    "mater_eff": mater_eff * fake_mater_eff,
                    "time_eff": time_eff * fake_time_eff,
                    "bp_object": await op.get_bp_object(product_type_id, min_self_index_real_quantity_work, False)
                }]
                job_list = [{
                    "type_id": product_type_id,
                    "runs": min_self_index_quantity_work,
                    "mater_eff": mater_eff * fake_mater_eff,
                    "time_eff": time_eff * fake_time_eff,
                    "bp_object": await op.get_bp_object(product_type_id, min_self_index_quantity_work, False)
                }]
            await op.calculate_work_material_avaliable(real_work_list)
            op.work_list_cache[(product_type_id, self_index_id)] = [real_work_list, job_list]
        else:
            while op.work_list_cache[(product_type_id, self_index_id)] == ([], []):
                await asyncio.sleep(0.1)
            real_work_list, job_list = op.work_list_cache[(product_type_id, self_index_id)]

        # 计算多余数量 ==============================================================================================
        real_product_quantity = self_relation['product_num'] * sum([work['runs'] for work in real_work_list])
        product_quantity = self_relation['product_num'] * sum([work['runs'] for work in job_list])
        self_product_remain = product_quantity - self_index_quantity + last_order_index_remain
        self_real_product_remain = real_product_quantity - self_index_real_quantity + last_order_index_real_remain

        # 根据系数计算工作流需要的材料数量 ==============================================================================================

        real_quantity_material_need_list = []
        for work in real_work_list:
            real_quantity_material_need_list.append(
                ceil(
                    work['runs'] * self_relation['material_num'] * (1 if self_relation['material_num'] == 1 else work['mater_eff'])
                )
            )
            logger.debug(f"real_quantity_material_need_list: {real_quantity_material_need_list}")
        # real_quantity_material_need_list = [
        #     ceil(
        #         work['runs'] * self_relation['material_num'] * (1 if self_relation['material_num'] == 1 else 
        #         (mater_eff * (fake_mater_eff if work['bp_object']['fake'] else (1 - 0.01 * work['bp_object']['material_efficiency']))))
        #     ) for work in real_work_list
        # ]
        activety_time = await BPM.get_production_time(product_type_id)
        real_quantity_time_need_list = [
            ceil(
                work['runs'] * activety_time * work["time_eff"]
            ) for work in real_work_list
        ]
        quantity_material_need_list = [
            ceil(
                # 有点绕
                work['runs'] * self_relation['material_num'] * (1 if self_relation['material_num'] == 1 else work['mater_eff'])
            ) for work in job_list
        ]

        # 系数成本计算 ==============================================================================================
        structure_info = await op.get_type_assign_structure_info(product_type_id)
        if not structure_info:
            raise KahunaException(f"物品 {product_type_id}: {SdeUtils.get_name_by_id(product_type_id)} 未分配建筑")
        material_adjust_price = await op.get_type_adjust_price(material_type_id)
        system_cost = await op.get_system_cost(structure_info['system_id'])
        actype = "manufacturing" if self_relation['activity_id'] == 1 else "reaction"
        eiv_cost = float(system_cost[actype]) * material_adjust_price * self_relation['material_num']
        real_eiv_cost_list = [eiv_cost * work['runs'] for work in job_list]

        quantity_material_need = sum(quantity_material_need_list)
        real_quantity_material_need = sum(real_quantity_material_need_list)
        real_quantity_time_need = sum(real_quantity_time_need_list)
        real_eiv_cost_total = sum(real_eiv_cost_list)

        
        

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
                "real_eiv_cost_total": real_eiv_cost_total,
                "index_quantity_work": min_self_index_quantity_work,
                "index_real_quantity_work": min_self_index_real_quantity_work,
                "product_remain": self_product_remain,
                "real_product_remain": self_real_product_remain,
                "real_work_remain": real_all_index_remain_work,
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
        last_progress = 0
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
            mission_count = await tqdm_manager.get_mission_count("relation_moniter_process")
            now_progress = mission_count / len(all_relation_list) * 100
            if now_progress > last_progress + 10:
                await rdm.r.hset(op.current_progress_key, mapping={"name": "更新树状态", "progress": now_progress, "is_indeterminate": 0})
                last_progress = now_progress
        await tqdm_manager.complete_mission("relation_moniter_process")
        logger.info(f"plan {plan_name} status update complete")

    @classmethod
    async def update_plan_status(cls, plan_name: str, user_name: str, op: ConfigFlowOperateCenter):
        await cls._relation_moniter_process(user_name, plan_name, op)

    # 权限管理方法（代理方法，保持向后兼容）
    @classmethod
    async def add_industrypermision(cls, user_id: str, data):
        return await add_industrypermision(user_id, data)

    @classmethod
    async def delete_industrypermision(cls, user_id: str, data):
        return await delete_industrypermision(user_id, data)
    
    @classmethod
    async def get_user_all_container_permission(cls, user_id: str):
        return await get_user_all_container_permission(user_id)

    # 结构相关方法（代理方法，保持向后兼容）
    @classmethod
    async def get_structure_list(cls, user_id: str):
        return await get_structure_list(user_id)

    @classmethod
    async def get_structure_assign_keyword_suggestions(cls, assign_type: str, query):
        return await get_structure_assign_keyword_suggestions(assign_type, query)

    # 类型列表方法（代理方法，保持向后兼容）
    @classmethod
    async def get_type_list(cls):
        return await get_type_list()

    # 配置管理方法（代理方法，保持向后兼容）
    @classmethod
    async def create_config_flow_config(cls, user_id: str, data):
        return await create_config_flow_config(user_id, data)

    @classmethod
    async def fetch_recommended_presets(cls, user_id: str):
        return await fetch_recommended_presets(user_id)

    @classmethod
    async def delete_config_flow_config(cls, user_id: str, data):
        return await delete_config_flow_config(user_id, data)

    @classmethod
    async def get_config_flow_config_list(cls, user_id: str):
        return await get_config_flow_config_list(user_id)

    @classmethod
    async def add_config_to_plan(cls, user_id: str, data):
        return await add_config_to_plan(user_id, data)

    @classmethod
    async def get_config_flow_list(cls, user_id: str, plan_name: str):
        return await get_config_flow_list(user_id, plan_name)

    @classmethod
    async def delete_config_from_plan(cls, user_id: str, data):
        return await delete_config_from_plan(user_id, data)

    @classmethod
    async def save_config_flow_to_plan(cls, user_id: str, plan_name: str, data):
        return await save_config_flow_to_plan(user_id, plan_name, data)

    # 物品信息方法（代理方法，保持向后兼容）
    @classmethod
    async def get_item_info(cls, type_id: int):
        return await get_item_info(type_id)

# MarketTree 类（代理类，保持向后兼容）
# 注意：MarketTree 类在 industry_utils 中定义，这里通过导入使用
