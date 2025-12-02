"""
plan_utils 模块
提供计划状态更新和表格视图数据获取的CPU密集型函数
"""

# 标准库导入
import asyncio
from copy import deepcopy
from math import ceil, sqrt
from typing import Dict, List, Tuple

# 本地导入 - 核心工具
from src_v2.core.database.connect_manager import (
    neo4j_manager,
    redis_manager as rdm
)
# from src_v2.core.database.neo4j_utils import (
#     Neo4jIndustryUtils as NIU
# )
from src_v2.core.log import logger
# from src_v2.core.utils import tqdm_manager

# 本地导入 - EVE 模块
# from src_v2.model.EVE.market.market_manager import MarketManager
from src_v2.model.EVE.sde import SdeUtils

# 本地导入 - 相对导入
from ..blueprint import BPManager as BPM
from ..plan_configflow_operate import ConfigFlowOperateCenter
from .material_utils import get_material_type

async def _get_uncomplete_relation_list(op: ConfigFlowOperateCenter):
    """获取未完成的关系列表"""
    res = []
    for relation in op.all_ralation_dict.values():
        if relation['relation']['status'] != "complete":
            res.append(relation)
    return res


async def _is_relation_calculate_avaliable(op: ConfigFlowOperateCenter, relation: dict) -> Tuple[bool, List[dict], List[dict], dict]:
    """判断关系是否可计算"""
    self_relation = relation['relation']
    if self_relation['status'] == "complete":
        return False, [], [], relation
    self_index_id = self_relation['index_id']
    self_order_id = self_relation['order_id']

    same_route_relations = op.all_relation_between_nodes_dict[(self_relation['product'], self_relation['material'])]
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
                
    product_node_in_relation = op.all_node_in_relation_dict[self_relation['product']]
    for r in product_node_in_relation:
        if r['relation']['status'] != "complete":
            return False, [], [], relation
    return True, product_node_in_relation, same_route_relations, relation


async def _relation_calculater(plan_settings: dict, relation: dict, product_node_in_relation: List[dict], same_route_relations: List[dict], op: ConfigFlowOperateCenter):
    """关系计算器"""
    self_relation = relation['relation']
    product_type_id = self_relation['product']
    material_type_id = self_relation['material']
    self_index_id = self_relation['index_id']
    self_order_id = self_relation['order_id']
    order_index = [relation['relation']['order_id'] for relation in same_route_relations].index(self_order_id)
    
    op.calculate_cache[(product_type_id, material_type_id, self_index_id)] = op.calculate_cache.get((product_type_id, material_type_id, self_index_id), 0) + 1

    # 判断是否需要计算 ==============================================================================================
    if not await op.get_relation_need_calculate(product_type_id):
        op.all_ralation_dict[(product_type_id, material_type_id, self_index_id)]['relation'].update({
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
        })
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

    # 运行中任务生产 数量处理 每个(product_type_id, index)只计算一次 ==============================================================================================
    
    if plan_settings.get('considerate_running_job', False):
        all_index_real_quantity -= await op.get_running_job_count(product_type_id) * await BPM.get_bp_product_quantity_typeid(product_type_id)
        self_index_real_quantity = await op.deal_running_job_quantity(self_index_real_quantity, product_type_id, self_index_id)

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
    fake_bp_mater_eff, fake_bp_time_eff = await op.get_conf_eff(product_type_id)

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
                this_round_max_job_run = max_job_run
                if bp['fake'] or bp["runs"] < 0:
                    bp_support_runs = max_job_run
                else:
                    bp_support_runs = bp["runs"]

                if plan_settings.get("full_use_bp_cp", False) and bp["runs"] > 0:
                    this_round_max_job_run = bp_support_runs

                if plan_settings.get("work_type", "whole") == "whole":
                    this_round_work = min(bp_support_runs, op.set_uped_jobs[product_type_id], this_round_max_job_run)
                elif plan_settings.get("work_type", "whole") == "in_order":
                    this_round_work = min(bp_support_runs, real_work_waiting_to_split, this_round_max_job_run)

                real_work_list.append({
                    "type_id": product_type_id,
                    "runs": this_round_work,
                    "bp_object": bp,
                    "mater_eff": mater_eff * (fake_bp_mater_eff if bp['fake'] else (1 - 0.01 * bp['material_efficiency'])),
                    "time_eff": time_eff * (fake_bp_time_eff if bp['fake'] else (1 - 0.01 * bp['time_efficiency'])),
                })
                real_work_waiting_to_split -= this_round_work
                op.set_uped_jobs[product_type_id] -= this_round_work
            
            # ==========================================================
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
                "mater_eff": mater_eff * fake_bp_mater_eff,
                "time_eff": time_eff * fake_bp_time_eff,
                "bp_object": await op.get_bp_object(product_type_id, max_job_run, False)
            } for _ in range(full_job_num)]
            if less_work > 0:
                job_list.append({
                    "type_id": product_type_id,
                    "runs": less_work,
                    "mater_eff": mater_eff * fake_bp_mater_eff,
                    "time_eff": time_eff * fake_bp_time_eff,
                    "bp_object": await op.get_bp_object(product_type_id, less_work, False)
                })
        else:
            # ==========================================================
            # 不切分工作流
            # ==========================================================
            real_work_list = [{
                "type_id": product_type_id,
                "runs": min_self_index_real_quantity_work,
                "mater_eff": mater_eff * fake_bp_mater_eff,
                "time_eff": time_eff * fake_bp_time_eff,
                "bp_object": await op.get_bp_object(product_type_id, min_self_index_real_quantity_work, False)
            }]
            job_list = [{
                "type_id": product_type_id,
                "runs": min_self_index_quantity_work,
                "mater_eff": mater_eff * fake_bp_mater_eff,
                "time_eff": time_eff * fake_bp_time_eff,
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
        # raise KahunaException(f"物品 {product_type_id}: {await SdeUtils.get_name_by_id(product_type_id)} 未分配建筑")
        system_cost = {"manufacturing": 0.14 / 100, "reaction": 0.14 / 100}
    else:
        system_cost = await op.get_system_cost(structure_info['system_id'])
    
    material_adjust_price = await op.get_type_adjust_price(material_type_id)
    
    actype = "manufacturing" if self_relation['activity_id'] == 1 else "reaction"
    if "manufacturing" not in system_cost or "reaction" not in system_cost:
        logger.error(f"system_cost {system_cost} not have {actype}")
    eiv_cost = float(float(system_cost[actype]) + 0.04) * material_adjust_price * self_relation['material_num']
    real_eiv_cost_list = [eiv_cost * work['runs'] for work in job_list]
    quantity_material_need = sum(quantity_material_need_list)
    real_quantity_material_need = sum(real_quantity_material_need_list)
    real_quantity_time_need = sum(real_quantity_time_need_list)
    real_eiv_cost_total = sum(real_eiv_cost_list)

    # 更新状态
    op.all_ralation_dict[(product_type_id, material_type_id, self_index_id)]["relation"].update({
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
    })

    logger.debug(f"relation index {self_relation['index_id']} {self_relation['product']}->{self_relation['material']} calculate complete")
    # await tqdm_manager.update_mission("relation_moniter_process", 1)


async def update_plan_status(op: ConfigFlowOperateCenter, all_relation_list: List[dict], subprocess=False):
    """关系监控处理"""
    user_name = op.user_name
    plan_name = op.plan_name
    plan_settings = op.plan_settings

    all_ralation_dict = {}
    all_node_in_relation_dict = {}
    all_relation_between_nodes_dict = {}
    # 整理两个字典
    # 所有点的入边
    # 每两个点之间的边
    for relation in all_relation_list:
        if relation['relation']['material'] not in all_node_in_relation_dict:
            all_node_in_relation_dict[relation['relation']['material']] = []
        if (relation['relation']['product'], relation['relation']['material']) not in all_relation_between_nodes_dict:
            all_relation_between_nodes_dict[(relation['relation']['product'], relation['relation']['material'])] = []
        all_node_in_relation_dict[relation['relation']['material']].append(relation)
        all_relation_between_nodes_dict[(relation['relation']['product'], relation['relation']['material'])].append(relation)
        all_ralation_dict[(relation['relation']['product'], relation['relation']['material'], relation['relation']['index_id'])] = relation
    op.all_node_in_relation_dict = all_node_in_relation_dict
    op.all_relation_between_nodes_dict = all_relation_between_nodes_dict
    op.all_ralation_dict = all_ralation_dict

    async def relation_calculater_with_semaphore(relation: dict, product_node_in_relation: List[dict], same_route_relations: List[dict]):
        # async with neo4j_manager.semaphore:
        await _relation_calculater(plan_settings, relation, product_node_in_relation, same_route_relations, op)

    # await tqdm_manager.add_mission("relation_moniter_process", len(all_relation_list))
    
    last_progress = 0
    uncomplete_relation_list = await _get_uncomplete_relation_list(op)
    while uncomplete_relation_list:
        check_tasks = [
            asyncio.create_task(_is_relation_calculate_avaliable(op, relation)) for relation in uncomplete_relation_list
        ]
        check_results = await asyncio.gather(*check_tasks)

        calculate_tasks = [
            asyncio.create_task(relation_calculater_with_semaphore(relation, product_node_in_relation, same_route_relations))
            for res, product_node_in_relation, same_route_relations, relation in check_results if res == True
        ]
        await asyncio.gather(*calculate_tasks)

        # mission_count = await tqdm_manager.get_mission_count("relation_moniter_process")
        uncomplete_relation_list = await _get_uncomplete_relation_list(op)
        now_progress = (len(all_relation_list) - len(uncomplete_relation_list)) / len(all_relation_list) * 100
        if now_progress > last_progress + 1:
            if not subprocess:
                await rdm.r.hset(op.current_progress_key, mapping={"name": "更新树状态", "progress": now_progress, "is_indeterminate": 0})
            last_progress = now_progress

    # await tqdm_manager.complete_mission("relation_moniter_process")
    logger.info(f"plan {plan_name} status update complete")

async def get_plan_tableview_data(op: ConfigFlowOperateCenter, node_dict: dict, subprocess=False):
    """
    获取计划表格视图数据
    """
    user_name = op.user_name
    plan_name = op.plan_name
    plan_settings = op.plan_settings

    # 定义原材料大类
    material_type = ["矿石", "冰矿产物", "燃料块", "元素", "气云", "行星工业", "杂货"]

    if not subprocess:
        await rdm.r.hset(op.current_progress_key, mapping={"name": "获取路径数据", "progress": 50, "is_indeterminate": 1})
    logger.info("收集路径深度")
    # node_dict = {
    #     node['type_id']: node for node in await NIU.get_user_plan_node_with_distance(user_name, plan_name)
    # }

    # 获取材料报价
    if not subprocess:
        await rdm.r.hset(op.current_progress_key, mapping={"name": "获取材料报价", "progress": 50, "is_indeterminate": 1})
    # await MarketManager().update_jita_price()

    job_deal_set = set()
    logger.info("收集关系数据")
    
    relations = [r['relation'] for r in op.all_ralation_dict.values()]
    # await tqdm_manager.add_mission(f"收集关系数据 {plan_name}", len(relations))
    if not subprocess:
        await rdm.r.hset(op.current_progress_key, mapping={"name": "收集关系数据", "progress": 0, "is_indeterminate": 1})
    last_progress = 0
    eiv_cost_dict = {}
    for relation in relations:
        relation_need_calculate = relation.get("need_calculate", None)

        # 汇总材料节点计算后真实需求数量【缺失】
        material_id = relation['material']
        product_id = relation['product']
        # await tqdm_manager.update_mission(f"收集关系数据 {plan_name}", 1)
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
                    "type_name": await SdeUtils.get_name_by_id(top_product_type_id),
                    "index_id": relation["index_id"],
                    "product_num": op.product_num_dict[top_product_type_id],
                    "asset_quantity": await op.get_type_assets_quantity(top_product_type_id),
                    "children": [],
                }
            # 所有边的eiv_cost汇总到最上层节点
            eiv_cost_dict[top_product_type_id].update({
                "eiv_cost": eiv_cost_dict[top_product_type_id].get('eiv_cost', 0) + relation['real_eiv_cost_total'],
            })
            if op.get_node_type(relation['material']) != "product":
                material_type_node = await get_material_type(relation['material'])
                jita_buy_price = await rdm.r.hget(f"market_price:jita:{relation['material']}", "max_buy")
                jita_sell_price = await rdm.r.hget(f"market_price:jita:{relation['material']}", "min_sell")
                eiv_cost_dict[top_product_type_id]['children'].append({
                    "type_id": relation['material'],
                    "type_name": await SdeUtils.get_name_by_id(relation['material']),
                    "index_id": relation["index_id"],
                    "quantity": relation['quantity'],
                    "jita_buy_price": jita_buy_price if jita_buy_price else 0,
                    "jita_sell_price": jita_sell_price if jita_sell_price else 0,
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
    # await tqdm_manager.complete_mission(f"收集关系数据 {plan_name}")

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
    if not subprocess:
        await rdm.r.hset(op.current_progress_key, mapping={"name": "整理节点", "progress": 50, "is_indeterminate": 1})
    # await tqdm_manager.add_mission(f"分类节点 {plan_name}", len(node_dict))
    mission_count = 0
    for node in node_dict.values():
        # 整理库存状态
        node['tpye_name_zh'] = await SdeUtils.get_cn_name_by_id(node['type_id'])
        if op.get_node_type(node['type_id']) != "product":
            material_type_node = await get_material_type(node['type_id'])
            buy_price = await rdm.r.hget(f"market_price:jita:{node['type_id']}", "max_buy")
            sell_price = await rdm.r.hget(f"market_price:jita:{node['type_id']}", "min_sell")
            node['buy_price'] = buy_price if buy_price else 0
            node['sell_price'] = sell_price if sell_price else 0
            material_output[material_type_node]['children'].append(node)
        else:
            flow_output[node['max_distance'] - 1]["children"].append(node)
        # mission_count = await tqdm_manager.update_mission(f"分类节点 {plan_name}", 1)
        
        
        # 整理工作流输出
        work_flow.extend([{
                "type_id": work["type_id"],
                "active_id": await BPM.get_activity_id_by_product_typeid(work["type_id"]),
                "type_name_zh": await SdeUtils.get_cn_name_by_id(work["type_id"]),
                "type_name": await SdeUtils.get_name_by_id(work["type_id"]),
                "avaliable": work["avaliable"],
                "runs": work["runs"],
                "bp_object": work["bp_object"],
                "type_order_id": node["order_id"],
                "mater_eff": work["mater_eff"],
                "time_eff": work["time_eff"],
            } for work in node.get("real_job_list", []) if work
        ])

        # 整理蓝图库存
        if not subprocess:
            await rdm.r.hset(op.current_progress_key, mapping={"name": "整理蓝图库存", "progress": 50, "is_indeterminate": 1})
        node['bp_quantity'], node['bp_jobs'] = await op.get_bp_status(node['type_id'], plan_settings.get('considerate_bp_relation', False))

        mission_count += 1
        now_progress = mission_count / len(node_dict) * 100
        if now_progress / 3 + 66 > last_progress + 1:
            last_progress = now_progress
    # await tqdm_manager.complete_mission(f"分类节点 {plan_name}")
    
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
                        this_logistic_quantity = lack_quantity
                        lack_quantity = 0
                    else:
                        lack_quantity -= provide_quantity
                        this_logistic_quantity = provide_quantity
                        provide_quantity = 0
                    # 匹配成功，更新供给和需求，记录物流线路
                    provide_structure_info["material_provide"][lack_type_id] = provide_quantity
                    lack_structure_info["material_need"][lack_type_id] = lack_quantity
                    if (lack_structure_id, provide_structure_id, lack_type_id) not in logistic_dict:
                        logistic_dict[(lack_structure_id, provide_structure_id, lack_type_id)] = {
                            "provide_quantity": this_logistic_quantity,
                            "provide_structure_info": provide_structure_info,
                            "lack_structure_info": lack_structure_info,
                        }
                    else:
                        logistic_dict[(lack_structure_id, provide_structure_id, lack_type_id)]["provide_quantity"] += this_logistic_quantity
    # 整理为可执行的计划的数据
    save_logistic_data = []
    for d, logistic_info in logistic_dict.items():
        lack_structure_id, provide_structure_id, lack_type_id = d
        provide_structure_info = logistic_info["provide_structure_info"]
        lack_structure_info = logistic_info["lack_structure_info"]
        light_year = 9.461e15
        provide_system_info = await SdeUtils.get_system_info_by_id(provide_structure_info["system_id"])
        lack_system_info = await SdeUtils.get_system_info_by_id(lack_structure_info["system_id"])
        if not provide_system_info or not lack_system_info:
            logger.error(f"物流线路 {d} 缺少星系信息")
            continue
        save_logistic_data.append({
            "lack_structure_id": lack_structure_id,
            "lack_structure_name": lack_structure_info["structure_name"],
            "provide_structure_id": provide_structure_id,
            "provide_structure_name": provide_structure_info["structure_name"],
            "provide_system_id": provide_structure_info["system_id"],
            "provide_system_name": provide_structure_info["system_name"],
            "provide_system_coordinate": [provide_system_info["x"] / light_year, provide_system_info["y"] / light_year, provide_system_info["z"] / light_year],
            "lack_system_id": lack_system_info["system_id"],
            "lack_system_name": lack_system_info["system_name"],
            "lack_system_coordinate": [lack_system_info["x"] / light_year, lack_system_info["y"] / light_year, lack_system_info["z"] / light_year],
            "provide_system_distance": sqrt(
                (provide_system_info["x"] - lack_system_info["x"])**2 +
                (provide_system_info["y"] - lack_system_info["y"])**2 +
                (provide_system_info["z"] - lack_system_info["z"])**2
            ) / light_year,
            "lack_type_id": lack_type_id,
            "lack_type_name": await SdeUtils.get_cn_name_by_id(lack_type_id),
            "provide_quantity": logistic_info["provide_quantity"],
            "provide_volume": await SdeUtils.get_volume_by_type_id(lack_type_id) * logistic_info["provide_quantity"],
        })


    # 获取劳动力数据
    if not subprocess:
        await rdm.r.hset(op.current_progress_key, mapping={"name": "获取劳动力数据", "progress": 50, "is_indeterminate": 1})
    running_job_tableview_data = await op.get_running_job_tableview_data(plan_settings.get("considerate_running_job", False))
    
    return {
        "flow_output": flow_output,
        "material_output": [material_output[t] for t in material_type],
        "eiv_cost_dict": eiv_cost_dict,
        "work_flow": work_flow,
        "purchase_output": None,
        "running_job_tableview_data": running_job_tableview_data,
        "logistic_dict": save_logistic_data,
        "plan_settings": plan_settings
    }

