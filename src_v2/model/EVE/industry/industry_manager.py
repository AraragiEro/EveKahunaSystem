# 标准库导入
import asyncio
from copy import deepcopy
import json
import traceback
from asyncio import Queue
from enum import Flag
from itertools import product
from math import ceil, sqrt
from typing import Dict, List, Tuple
from datetime import date, datetime
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

# 本地导入 - 核心工具
from src_v2.core.database.connect_manager import (
    neo4j_manager,
    postgres_manager,
    redis_manager as rdm
)
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveIndustryPlanConfigFlowDBUtils,
    EveIndustryPlanDBUtils,
    EveIndustryPlanProductDBUtils,
    EveIndustryCalculateHistoryDBUtils
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

# 本地导入 - 相对导入
from .blueprint import BPManager as BPM
from .plan_configflow_operate import ConfigFlowOperateCenter

# 本地导入 - industry_utils 工具模块
from .industry_utils import (
    AsyncCounter,
    MarketTree,
    get_market_tree,
    create_config_flow_config,
    modify_config_flow_config,
    fetch_recommended_presets,
    delete_config_flow_config,
    get_config_flow_config_list,
    add_config_to_plan,
    get_config_flow_list,
    delete_config_from_plan,
    save_config_flow_to_plan,
    save_config_flow_preset,
    get_config_flow_presets,
    load_config_flow_preset,
    add_industrypermision,
    delete_industrypermision,
    get_user_all_container_permission,
    get_structure_list,
    get_structure_assign_keyword_suggestions,
    get_material_type,
    get_item_info,
    get_type_list,
    update_plan_status,
    get_plan_tableview_data
)



class IndustryManager(metaclass=SingletonMeta):
    def __init__(self):
        self.bp_node_analyse_queue = Queue()
        self.bp_relation_analyse_queue = Queue()
        # 计算任务队列和并发控制
        self.calculate_queue = asyncio.Queue()
        self.calculate_queue_items = []  # 用于跟踪队列中的任务，方便更新位置
        self.calculate_queue_lock = asyncio.Lock()  # 保护队列操作
        self.calculate_semaphore = asyncio.Semaphore(5)  # 最多5个并发任务
        self._queue_processor_task = None
        self._start_queue_processor()

        self._process_pool = None

    @classmethod
    async def create_plan(cls, user_name: str, plan_name: str, plan_settings: dict):
        plan_obj = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(user_name, plan_name)
        if plan_obj:
            raise KahunaException(f"计划已存在")
        plan_obj = EveIndustryPlanDBUtils.get_obj()
        plan_obj.user_name = user_name
        plan_obj.plan_name = plan_name
        plan_obj.settings = plan_settings
        await EveIndustryPlanDBUtils.merge(plan_obj)

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
            type_name = await SdeUtils.get_name_by_id(product.product_type_id)
            type_name_zh = await SdeUtils.get_cn_name_by_id(product.product_type_id)
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

    def _get_process_pool(self, max_workers=None):
        """获取进程池"""
        if self._process_pool is None:
            max_workers = max_workers or min(multiprocessing.cpu_count(), 4)  # 限制最大进程数
            self._process_pool = ProcessPoolExecutor(max_workers=max_workers)
        return self._process_pool

    @classmethod
    async def calculate_cost_and_market_histyory(cls, op: ConfigFlowOperateCenter, type_id_list, market_id: int = None):
        """
        成本与历史销量需要当场获取，涉及计算量较大，使用子进程。
        """
        semaphore = asyncio.Semaphore(5)
        
        # 初始化进度跟踪
        total_count = len(type_id_list)
        progress_key = None
        total_progress_key = None
        if market_id is not None:
            progress_key = f"market_cost_calculation_progress:{op.user_name}:{market_id}"
            total_progress_key = f"market_cost_calculation_total:{op.user_name}:{market_id}"
            await rdm.r.set(total_progress_key, total_count)
            await rdm.r.hset(progress_key, mapping={
                "status": "running",
                "completed": 0,
                "total": total_count,
                "current_step": "初始化计算任务"
            })
        
        async def calculate_cost_and_market_histyory_async(type_id: int, plan_data):
            async with semaphore:
                    # 创建操作中心对象
                sub_op = await ConfigFlowOperateCenter.create(
                    plan_data["user_name"],
                    plan_data["plan_name"],
                    plan_data["plan_settings"]
                )
                await sub_op.init_at_begin()
                
                # 执行计算步骤（与原方法保持一致）
                await IndustryManager.delete_plan_nodes(sub_op.plan_name, sub_op.user_name)
                await IndustryManager.create_plan_node(plan_data)
                await IndustryManager.create_plan_tree(plan_data, sub_op)
                all_relation_list = await NIU.get_relations("PLAN_BP_DEPEND_ON", {"user_name": sub_op.user_name, "plan_name": sub_op.plan_name})

                # 使用多进程计算计划状态
                IndustryManager()._process_pool = IndustryManager()._get_process_pool(max_workers=3)
                future = IndustryManager()._process_pool.submit(_run_async_calculation_in_process, type_id, sub_op, all_relation_list)
                # 使用 wrap_future 将 concurrent.futures.Future 转换为 asyncio.Future，避免阻塞事件循环
                logger.info(f"calculate_cost_and_market_histyory_async {type_id} start")
                asyncio_future = asyncio.wrap_future(future)
                result = await asyncio_future
                logger.info(f"calculate_cost_and_market_histyory_async {type_id} end")
            # await update_plan_status(sub_op, all_relation_list)
            # result = await get_plan_tableview_data(sub_op)
            return type_id, result

        cost_dict = {}
        futures = []
        for type_id in type_id_list:
            # 构造计划数据（可序列化的字典）
            plan_name = f"calculate_cost_and_market_histyory_{type_id}"
            plan_settings = op.plan_settings
            plan_settings["name"] = plan_name
            plan_settings["work_type"] = "whole"
            plan_settings["split_to_jobs"] = True
            # plan_settings["considerate_asset"] = True
            plan_settings["considerate_bp_relation"] = False
            plan_settings["considerate_running_job"] = False

            plan_data = {
                "plan_name": plan_name,
                "user_name": op.user_name,
                "plan_settings": plan_settings,
                "products": [{
                    "index_id": 1,
                    "product_type_id": type_id,
                    # 加大数量，避免计算结果不准确
                    "quantity": 1000
                }]
            }

            futures.append(asyncio.create_task(calculate_cost_and_market_histyory_async(type_id, plan_data)))

        # 使用 asyncio.as_completed 实时更新进度
        completed_count = 0
        result_key = None
        has_error = False
        if market_id is not None and progress_key:
            result_key = f"market_cost_calculation_result:{op.user_name}:{market_id}"
            for future in asyncio.as_completed(futures):
                try:
                    result = await future
                    completed_count += 1
                    cost_dict[result[0]] = {
                        "type_id": result[0],
                        "eiv_cost_dict": result[1]["eiv_cost_dict"],
                        "material_output": result[1]["material_output"],
                    }
                    # 更新进度
                    await rdm.r.hset(progress_key, mapping={
                        "status": "running",
                        "completed": completed_count,
                        "total": total_count,
                        "current_step": f"已完成 {completed_count}/{total_count}"
                    })
                except Exception as e:
                    logger.error(f"计算任务失败: {e}")
                    has_error = True
                    completed_count += 1
                    await rdm.r.hset(progress_key, mapping={
                        "status": "running",
                        "completed": completed_count,
                        "total": total_count,
                        "current_step": f"任务失败: {str(e)}"
                    })
            # 计算完成，将结果存储到 Redis
            if result_key:
                if has_error:
                    # 如果有错误，标记为失败
                    await rdm.r.hset(progress_key, mapping={
                        "status": "failed",
                        "completed": completed_count,
                        "total": total_count,
                        "current_step": "计算失败"
                    })
                else:
                    # 存储结果（不设置过期时间，作为缓存）
                    await rdm.r.set(result_key, json.dumps(cost_dict))
                    await rdm.r.hset(progress_key, mapping={
                        "status": "completed",
                        "completed": completed_count,
                        "total": total_count,
                        "current_step": "计算完成"
                    })
        else:
            # 如果没有 market_id，使用原来的方式
            results = await asyncio.gather(*futures)
            for result in results:
                cost_dict[result[0]] = result[1]

        return cost_dict

    @classmethod
    async def calculate_plan(cls, op: ConfigFlowOperateCenter):
        await rdm.r.set(op.total_progress_key, 0)
        await rdm.r.hset(op.current_progress_key, mapping={"name": "开始计算", "progress": 0})

        user_id = op.user_name
        plan_name = op.plan_name
        plan_data = {
            "plan_name": plan_name,
            "user_name": user_id,
            "plan_settings": op.plan_settings,
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
        
        # 这里只需要清理 Neo4j 中旧的计划节点和关系，不能删除 PostgreSQL 中的计划与产品配置，
        # 否则后续在 get_plan_tableview_data 中将无法读取到 plan_settings，导致 plan_obj 为 None。
        await rdm.r.hset(op.current_progress_key, mapping={"name": "删除计划节点", "progress": 100})
        await cls.delete_plan_nodes(plan_name, user_id)
        await rdm.r.set(op.total_progress_key, 20)
        
        await rdm.r.hset(op.current_progress_key, mapping={"name": "创建计划节点", "progress": 100})
        await cls.create_plan_node(plan_data)
        await rdm.r.set(op.total_progress_key, 40)

        await rdm.r.hset(op.current_progress_key, mapping={"name": "创建计划树", "progress": 0})
        await cls.create_plan_tree(plan_data, op)
        await rdm.r.set(op.total_progress_key, 60)

        await rdm.r.hset(op.current_progress_key, mapping={"name": "更新树状态", "progress": 0})
        all_relation_list = await NIU.get_relations("PLAN_BP_DEPEND_ON", {"user_name": op.user_name, "plan_name": op.plan_name})
        await update_plan_status(op, all_relation_list)
        await rdm.r.set(op.total_progress_key, 80)

        await rdm.r.hset(op.current_progress_key, mapping={"name": "数据汇总", "progress": 0})
        node_dict = {
            node['type_id']: node for node in await NIU.get_user_plan_node_with_distance(op.user_name, op.plan_name)
        }
        await MarketManager().update_jita_price()
        result_data = await get_plan_tableview_data(op, node_dict)
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
        # await tqdm_manager.add_mission(f"create_plan_{plan_name}", len(products))
        logger.info(f"create_plan_{plan_name} start, len: {len(products)}")
        count = 0
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
            count += 1
            # mission_count = await tqdm_manager.update_mission(f"create_plan_{plan_name}", 1)
            logger.info(f"create_plan_{plan_name} update, product: {product['product_type_id']}, count: {count}")
            now_progress = count / len(products) * 100
            if now_progress > last_progress + 1:
                await rdm.r.hset(op.current_progress_key, mapping={"name": "创建计划树", "progress": now_progress})
                last_progress = now_progress

            # index_root节点更新需求数量，更新状态为finished.
        # await tqdm_manager.complete_mission(f"create_plan_{plan_name}")
        logger.info(f"create_plan_{plan_name} complete")

    @classmethod
    async def delete_plan(cls, plan_name: str, user_name: str):
        """删除计划及其所有相关数据
        
        Args:
            plan_name: 计划名称
            user_name: 用户名
        """
        # 删除 PostgreSQL 数据库中的相关数据（完整删除接口使用）
        # 1. 删除计划产品
        await EveIndustryPlanProductDBUtils.delete_all_by_user_name_and_plan_name(user_name, plan_name)
        # 2. 删除计划配置流
        await EveIndustryPlanConfigFlowDBUtils.delete_by_user_name_and_plan_name(user_name, plan_name)
        # 3. 删除计划设置
        await EveIndustryPlanDBUtils.delete_by_user_name_and_plan_name(user_name, plan_name)
        # 4. 删除 Neo4j 中的计划节点及其关系
        await cls.delete_plan_nodes(plan_name, user_name)

    @classmethod
    async def delete_plan_nodes(cls, plan_name: str, user_name: str):
        """仅删除 Neo4j 中的计划节点及其 PLAN_BP_DEPEND_ON 树

        用于重新计算计划时清理旧的图数据，保留 PostgreSQL 中的计划与产品配置。
        """
        await NIU.delete_tree(
            "Plan",
            {"plan_name": plan_name, "user_name": user_name},
            "PLAN_BP_DEPEND_ON")


    @classmethod
    async def get_plan_tableview_data(cls, op: ConfigFlowOperateCenter, node_dict: dict):
        """获取计划表格视图数据（代理方法，保持向后兼容）"""
        return await get_plan_tableview_data(op, node_dict)

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
        type_name = await SdeUtils.get_cn_name_by_id(type_id)
        # await tqdm_manager.add_mission(f"create_plan_bp_tree_{type_id}_{type_name}_nodes", len(nodes_dict))
        # await tqdm_manager.add_mission(f"create_plan_bp_tree_{type_id}_{type_name}_relationships", len(relationships_list))
        logger.info(f"create_plan_bp_tree_{type_id}_{type_name} start, nodes_dict: {len(nodes_dict)}, relationships_list: {len(relationships_list)}")

        # 2. 创建PlanBlueprint节点树
        # 首先创建所有PlanBlueprint节点
        tasks = []
        async def merge_node_with_semaphore(plan_bp_index, plan_bp_properties):
            async with neo4j_manager.semaphore:
                await NIU.merge_node("PlanBlueprint", plan_bp_index, plan_bp_properties)
                # await tqdm_manager.update_mission(f"create_plan_bp_tree_{type_id}_{type_name}_nodes", 1)
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
                # await tqdm_manager.update_mission(f"create_plan_bp_tree_{type_id}_{type_name}_relationships", 1)

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

        # await tqdm_manager.complete_mission(f"create_plan_bp_tree_{type_id}_{type_name}_nodes")
        # await tqdm_manager.complete_mission(f"create_plan_bp_tree_{type_id}_{type_name}_relationships")
        logger.info(f"create_plan_bp_tree_{type_id}_{type_name} complete")

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
    async def fetch_recommended_presets(cls, user_id: str, preset_name: str):
        return await fetch_recommended_presets(user_id, preset_name)

    @classmethod
    async def modify_config_flow_config(cls, user_id: str, data):
        return await modify_config_flow_config(user_id, data)

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

    @classmethod
    async def save_config_flow_preset(cls, user_id: str, preset_name: str, config_list):
        return await save_config_flow_preset(user_id, preset_name, config_list)

    @classmethod
    async def get_config_flow_presets(cls, user_id: str):
        return await get_config_flow_presets(user_id)

    @classmethod
    async def load_config_flow_preset(cls, user_id: str, preset_id: int, plan_name: str):
        return await load_config_flow_preset(user_id, preset_id, plan_name)

    @classmethod
    async def get_plan_settings(cls, user_id: str, plan_name: str):
        plan_obj = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(user_id, plan_name)
        if not plan_obj:
            raise KahunaException(f"计划 {plan_name} 不存在")
        return plan_obj.settings

    # 物品信息方法（代理方法，保持向后兼容）
    @classmethod
    async def get_item_info(cls, type_id: int):
        return await get_item_info(type_id)

    # 计算任务队列管理方法
    def _start_queue_processor(self):
        """启动队列处理协程"""
        if self._queue_processor_task is None or self._queue_processor_task.done():
            self._queue_processor_task = asyncio.create_task(self._process_calculate_queue())
            logger.info("计算任务队列处理协程已启动")

    async def _process_calculate_queue(self):
        """处理计算任务队列的协程"""
        while True:
            try:
                # 从队列中获取任务
                task_info = await self.calculate_queue.get()
                user_id, plan_name = task_info
                
                # 从跟踪列表中移除
                async with self.calculate_queue_lock:
                    if (user_id, plan_name) in self.calculate_queue_items:
                        self.calculate_queue_items.remove((user_id, plan_name))
                    # 更新剩余任务的位置
                    await self._update_queue_positions()
                
                # 使用 semaphore 控制并发
                async with self.calculate_semaphore:
                    # 执行计算任务
                    await self._calculate_plan_async(user_id, plan_name)
                
                # 标记任务完成
                self.calculate_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("计算任务队列处理协程被取消")
                raise
            except Exception as e:
                logger.error(f"处理计算任务队列时出错: {traceback.format_exc()}")
                # 即使出错也要标记任务完成
                self.calculate_queue.task_done()

    async def _calculate_plan_async(self, user_id: str, plan_name: str):
        """异步计算计划的后台任务"""
        status_key = f"plan_calculate_status:{user_id}:{plan_name}"
        total_progress_key = f"plan_calculate_total_progress:{user_id}:{plan_name}"
        current_progress_key = f"plan_calculate_current_progress:{user_id}:{plan_name}"
        result_key = f"plan_calculate_result:{user_id}:{plan_name}"
        
        # 记录计算开始时间
        calculate_start_time = datetime.utcnow()
        history_record = None
        product_count = 0
        
        try:
            # 设置状态为运行中
            await rdm.r.set(status_key, "running")
            await rdm.r.expire(status_key, 3600)  # 1小时过期
            
            # 从数据库获取计划的产品条目数量（不同产品类型的数量）
            try:
                product_count = 0
                async for product in await EveIndustryPlanProductDBUtils.select_all_by_user_name_and_plan_name(user_id, plan_name):
                    product_count += 1  # 统计产品条目数量，而不是数量总和
            except Exception as e:
                logger.warning(f"获取计划产品条目数量失败: {e}, 将使用默认值0")
                product_count = 0
            
            # 执行计算
            plan_settings = await IndustryManager.get_plan_settings(user_id, plan_name)
            op = await ConfigFlowOperateCenter.create(user_id, plan_name, plan_settings)
            op.total_progress_key = total_progress_key
            op.current_progress_key = current_progress_key
            await rdm.r.set(op.total_progress_key, 0)
            await rdm.r.hset(op.current_progress_key, mapping={"name": "初始化蓝图、资产与报价信息", "progress": 0, "is_indeterminate": 0})
            await op.init_at_begin()
            
            # 创建计算历史记录
            history_record = EveIndustryCalculateHistoryDBUtils.get_obj()
            history_record.user_name = user_id
            history_record.plan_name = plan_name
            history_record.product_count = product_count
            history_record.calculate_start_time = calculate_start_time
            history_record.calculate_result = None  # 初始化为None，计算完成后更新
            await EveIndustryCalculateHistoryDBUtils.save_obj(history_record)
            
            result_data = await IndustryManager.calculate_plan(op)
            
            # 计算完成，设置状态为已完成
            await rdm.r.set(result_key, json.dumps(result_data))
            # await rdm.r.expire(result_key, 3600)
            await rdm.r.set(status_key, "completed")
            # await rdm.r.expire(status_key, 3600)
            
            # 更新历史记录：计算成功
            calculate_end_time = datetime.utcnow()
            if history_record:
                history_record.calculate_time = calculate_end_time
                history_record.calculate_result = result_data
                await EveIndustryCalculateHistoryDBUtils.save_obj(history_record)
            
            logger.info(f"计划 {plan_name} 计算完成")
        except KahunaException as e:
            # 计算失败，设置状态为失败
            traceback.print_exc()
            error_msg = str(e)
            await rdm.r.set(status_key, f"failed:{error_msg}")
            await rdm.r.expire(status_key, 3600)
            
            # 更新历史记录：计算失败
            calculate_end_time = datetime.utcnow()
            if history_record:
                history_record.calculate_time = calculate_end_time
                # 将错误信息保存到 calculate_result
                history_record.calculate_result = {"error": error_msg, "exception_type": "KahunaException"}
                await EveIndustryCalculateHistoryDBUtils.save_obj(history_record)
            
            logger.error(f"计划 {plan_name} 计算失败: {error_msg}")
        except Exception as e:
            # 计算失败，设置状态为失败
            traceback.print_exc()
            error_msg = f"计算过程发生错误: {str(e)}"
            await rdm.r.set(status_key, f"failed:{error_msg}")
            await rdm.r.expire(status_key, 3600)
            
            # 更新历史记录：计算失败
            calculate_end_time = datetime.utcnow()
            if history_record:
                history_record.calculate_time = calculate_end_time
                # 将错误信息保存到 calculate_result
                history_record.calculate_result = {"error": error_msg, "exception_type": "Exception", "traceback": traceback.format_exc()}
                await EveIndustryCalculateHistoryDBUtils.save_obj(history_record)
            
            logger.error(f"计划 {plan_name} 计算失败: {traceback.format_exc()}")

    async def _update_queue_positions(self):
        """更新队列中所有等待任务的位置"""
        # 使用跟踪列表更新位置
        for index, (user_id, plan_name) in enumerate(self.calculate_queue_items):
            status_key = f"plan_calculate_status:{user_id}:{plan_name}"
            current_status = await rdm.r.get(status_key)
            
            # 只更新等待状态的任务
            if current_status and current_status.startswith("waiting:"):
                # 更新队列位置（队列中前方的任务数）
                await rdm.r.set(status_key, f"waiting:{index}")
                await rdm.r.expire(status_key, 3600)

    @classmethod
    async def start_plan_calculation(cls, user_id: str, plan_name: str):
        """启动计划计算任务"""
        instance = cls()
        # 确保队列处理协程已启动
        instance._start_queue_processor()
        status_key = f"plan_calculate_status:{user_id}:{plan_name}"
        
        # 检查是否已有正在进行的计算
        current_status = await rdm.r.get(status_key)
        if current_status:
            if current_status == "pending" or current_status == "running":
                raise KahunaException("计算任务已在运行中")
            elif current_status.startswith("failed:"):
                # 如果之前失败，允许重新启动
                pass
            elif current_status == "completed":
                # 如果已完成，允许重新计算
                pass
        
        # 检查当前并发数（semaphore 的可用数量）
        available_slots = instance.calculate_semaphore._value
        
        if available_slots > 0:
            # 有可用槽位，直接启动任务（使用 semaphore）
            await rdm.r.set(status_key, "pending")
            await rdm.r.expire(status_key, 3600)
            # 创建任务，使用 semaphore 控制并发
            async def run_with_semaphore():
                async with instance.calculate_semaphore:
                    await instance._calculate_plan_async(user_id, plan_name)
                    # 任务完成后更新队列位置
                    await instance._update_queue_positions()
            asyncio.create_task(run_with_semaphore())
        else:
            # 没有可用槽位，加入队列
            async with instance.calculate_queue_lock:
                queue_position = len(instance.calculate_queue_items)
                instance.calculate_queue_items.append((user_id, plan_name))
                await rdm.r.set(status_key, f"waiting:{queue_position}")
                await rdm.r.expire(status_key, 3600)
                await instance.calculate_queue.put((user_id, plan_name))

    @classmethod
    async def get_calculation_status(cls, user_id: str, plan_name: str):
        """获取计算任务状态"""
        status_key = f"plan_calculate_status:{user_id}:{plan_name}"
        total_progress_key = f"plan_calculate_total_progress:{user_id}:{plan_name}"
        current_progress_key = f"plan_calculate_current_progress:{user_id}:{plan_name}"
        
        status = await rdm.r.get(status_key)
        total_progress = await rdm.r.get(total_progress_key)
        current_progress_hash = await rdm.r.hgetall(current_progress_key)
        
        if not status:
            return {
                "status": "idle",
                "total_progress": None,
                "current_step": None,
                "is_indeterminate": 1
            }
        
        # 解析状态
        if status.startswith("failed:"):
            error_msg = status[7:]  # 去掉 "failed:" 前缀
            return {
                "status": "failed",
                "error": error_msg,
                "total_progress": None,
                "current_step": None,
                "is_indeterminate": 1
            }
        elif status.startswith("waiting:"):
            # 解析等待状态和队列位置
            queue_position = int(status.split(":")[1]) if ":" in status else 0
            return {
                "status": "waiting",
                "queue_position": queue_position,
                "total_progress": None,
                "current_step": None,
                "is_indeterminate": 1
            }
        else:
            # 解析总进度
            total_progress_value = int(total_progress) if total_progress else None
            
            # 解析当前步骤进度（从 hash 中获取）
            current_step_data = None
            if current_progress_hash:
                try:
                    name = current_progress_hash.get("name", "")
                    progress_str = current_progress_hash.get("progress", "")
                    progress_value = float(progress_str) if progress_str else None
                    if name or progress_value is not None:
                        current_step_data = {
                            "name": name,
                            "progress": int(progress_value) if progress_value is not None else None,
                            "is_indeterminate": current_progress_hash.get("is_indeterminate", "0") == "1"
                        }
                except (ValueError, TypeError) as e:
                    logger.warning(f"解析当前步骤进度失败: {e}, hash数据: {current_progress_hash}")
                    current_step_data = None
            
            return {
                "status": status,
                "total_progress": total_progress_value,
                "current_step": current_step_data,
                "is_indeterminate": current_progress_hash.get("is_indeterminate", "0") == "1"
            }

    @classmethod
    async def get_calculation_result(cls, user_id: str, plan_name: str):
        """获取计算结果"""
        status_key = f"plan_calculate_status:{user_id}:{plan_name}"
        result_key = f"plan_calculate_result:{user_id}:{plan_name}"
        
        # 检查状态是否为已完成
        status = await rdm.r.get(status_key)
        if not status or status != "completed":
            raise KahunaException("计算尚未完成")
        
        # 从Redis获取计算结果
        result_data_str = await rdm.r.get(result_key)
        if result_data_str:
            try:
                result_data = json.loads(result_data_str)
            except (json.JSONDecodeError, TypeError):
                # 如果Redis中没有结果，回退到从数据库获取
                raise KahunaException("计算结果不存在，请重新计算")
        else:
            # 如果Redis中没有结果，从数据库获取
            raise KahunaException("计算结果不存在，请重新计算")
        
        return result_data

# MarketTree 类（代理类，保持向后兼容）
# 注意：MarketTree 类在 industry_utils 中定义，这里通过导入使用


# ============================================================================
# 多进程支持：在子进程中运行异步计算函数
# ============================================================================

def _run_async_calculation_in_process(type_id: int, op: ConfigFlowOperateCenter, all_relation_list: List[dict]):
    """
    在子进程中运行异步计算函数的同步包装函数
    
    注意：
    1. 这个函数必须是模块级函数（不能是类方法），以便可以被pickle序列化
    2. 参数必须是可序列化的（pickle）
    3. 子进程中会创建新的事件循环
    4. 子进程中需要重新初始化数据库连接等资源
    
    Args:
        plan_data: 可序列化的计划数据字典，包含：
            - plan_name: 计划名称
            - user_name: 用户名
            - plan_settings: 计划设置字典
            - products: 产品列表
    
    Returns:
        计算结果
    """
    # import asyncio
    # import sys
    
    # # 在子进程中创建新的事件循环
    # # 注意：子进程不能使用主进程的事件循环
    # if sys.platform == 'win32':
    #     # Windows 需要设置事件循环策略
    #     asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # # 创建新的事件循环
    # loop = asyncio.new_event_loop()
    # asyncio.set_event_loop(loop)
    
    # try:
    #     # 运行异步计算
    #     result = loop.run_until_complete(
    #         _async_calculation_worker(plan_data)
    #     )
    #     return result
    # finally:
    #     # 清理事件循环
    #     loop.close()
    return asyncio.run(_async_calculation_worker(type_id, op, all_relation_list))


async def _async_calculation_worker(type_id: int, op: ConfigFlowOperateCenter, all_relation_list: List[dict]):
    """
    在子进程中执行的异步计算逻辑
    
    注意：这个函数会在子进程中运行，需要：
    1. 重新初始化数据库连接
    2. 重新创建必要的对象
    
    Args:
        plan_data: 计划数据字典
    
    Returns:
        计算结果
    """
    # 重新初始化数据库连接（子进程需要自己的连接）
    from src_v2.core.log import logger
    import logging
    
    # 关闭子进程的所有日志输出
    # 1. 设置 logger 级别为 CRITICAL（最高级别，所有低于此级别的日志都不会输出）
    logger.setLevel(logging.CRITICAL)
    # 2. 移除所有处理器，彻底禁用日志输出
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    # 3. 禁用根 logger，防止其他模块重新初始化 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.CRITICAL)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    from src_v2.core import init_database, close_database
    from src_v2.model.EVE.sde.utils import lock_manager
    from src_v2.model.EVE.industry.blueprint import lock as blueprint_lock
    lock_manager.reset_lock()
    blueprint_lock.reset_lock()
    
    # 初始化数据库（子进程模式，不创建表结构）
    await init_database(subprocess=True)
    await SdeUtils.init_database(subprocess=True)
    
    try:
        # 执行计算步骤（与原方法保持一致）
        all_relation_list = await NIU.get_relations("PLAN_BP_DEPEND_ON", {"user_name": op.user_name, "plan_name": op.plan_name})
        await update_plan_status(op, all_relation_list, subprocess=True)
        node_dict = {
            node['type_id']: node for node in await NIU.get_user_plan_node_with_distance(op.user_name, op.plan_name)
        }
        await MarketManager().update_jita_price()
        result = await get_plan_tableview_data(op, node_dict, subprocess=True)
        return result
    finally:
        # 确保无论是否发生异常，都关闭数据库连接
        # 这对于多进程环境非常重要，避免连接泄漏
        try:
            await close_database()
        except Exception:
            # 子进程中已禁用日志，静默处理异常
            pass