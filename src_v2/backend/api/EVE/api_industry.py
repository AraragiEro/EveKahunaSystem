import asyncio
import datetime
import json
import math
import re
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import jwt
from quart import Blueprint, Quart
from quart import current_app as app
from quart import g, jsonify, redirect, request
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from src_v2.backend.api.permission_required import role_required
from src_v2.backend.auth import auth_required, verify_token
from src_v2.core.database.connect_manager import get_neo4j_manager
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU
from src_v2.core.log import logger
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.user.user_manager import UserManager
from src_v2.core.utils import KahunaException
from src_v2.model.EVE.industry.blueprint import BPManager as BPM
from src_v2.model.EVE.industry.industry_manager import IndustryManager
from src_v2.model.EVE.industry.industry_utils.compressedAsteroid import CompressedAsteroidUtils
from src_v2.model.EVE.industry.industry_utils.material_utils import get_material_type
from src_v2.model.EVE.industry.plan_configflow_operate import ConfigFlowOperateCenter
from src_v2.model.EVE.market.market_manager import MarketManager
from src_v2.model.EVE.sde.utils import SdeUtils

api_industry_bp = Blueprint(
    'api_industry', __name__, url_prefix='/api/EVE/industry')


# 响应数据模型（通用）
@dataclass
class ErrorResponse:
    """错误响应"""
    status: int
    message: str


@api_industry_bp.route("/getMarketTree", methods=["POST"])
@auth_required
async def get_market_tree():
    """
    获取市场树

    获取指定市场节点的子节点树结构。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - node (string, required): 市场节点

    Responses:
        200: 成功返回市场树
            - status: 状态码 (200)
            - data: 市场树数据 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "node": "root"
        }

    Example Response:
        {
            "status": 200,
            "data": [...]
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        market_tree = await IndustryManager.get_market_tree(data["node"])
        logger.info(f"获取 市场节点 {data['node']} 的子节点 {len(market_tree)} 个")
        return jsonify({"data": market_tree, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取市场树失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取市场树失败"}), 500


@api_industry_bp.route("/searchMarketTypes", methods=["POST"])
@auth_required
async def search_market_types():
    """
    搜索市场类型

    根据关键词从SDE中搜索符合条件的type_id列表，过滤出可被蓝图生产的类型，然后从neo4j中获取对应的市场节点。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - keyword (string, required): 搜索关键字

    Responses:
        200: 成功返回搜索结果
            - status: 状态码 (200)
            - data: 匹配的类型列表，每个元素包含type_id和type_name_zh (array)
            - count: 结果数量 (integer)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "keyword": "物品名称"
        }

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "type_id": 123,
                    "type_name_zh": "物品中文名称"
                }
            ],
            "count": 1
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]
    keyword = data.get('keyword', '').strip()

    try:
        if not keyword:
            return jsonify({"status": 400, "message": "搜索关键字不能为空"}), 400

        # 步骤1: 使用fuzz_type获取type_name候选列表
        max_results = 10  # 限制结果数量
        fuzz_list = await SdeUtils.fuzz_type(keyword, list_len=max_results * 2)

        # 步骤2: 获取type_id和中文名称，并过滤出有蓝图的类型
        primary_results = []
        for type_name in fuzz_list:
            if len(primary_results) >= max_results:
                break
            type_id = await SdeUtils.get_id_by_name(type_name)
            if type_id:
                type_name_zh = await SdeUtils.get_cn_name_by_id(type_id)
                if type_name_zh:
                    # 步骤3: 检查是否有蓝图可生产
                    bp_id = await BPM.get_bp_id_by_prod_typeid(type_id)
                    if bp_id:  # 只保留有蓝图的type_id
                        primary_results.append({
                            'type_id': type_id,
                            'type_name_zh': type_name_zh
                        })

        if not primary_results:
            return jsonify({
                "status": 200,
                "data": [],
                "count": 0
            })

        # 步骤4: 从neo4j查询Type节点
        type_ids = [item['type_id'] for item in primary_results]
        neo4j_manager_instance = get_neo4j_manager()
        async with neo4j_manager_instance.get_session() as session:
            query = """
            MATCH (t:Type)
            WHERE t.type_id IN $type_ids
            RETURN t
            """
            result = await session.run(query, {"type_ids": type_ids})

            # 创建type_id到type_name_zh的映射
            type_id_to_name_zh = {
                item['type_id']: item['type_name_zh'] for item in primary_results}

            # 步骤5: 处理查询结果，先存储到字典中
            type_id_to_node = {}
            async for record in result:
                node_obj = record.get("t")
                if node_obj:
                    node_dict = dict(node_obj)
                    type_id = node_dict.get("type_id")
                    if type_id:
                        # 按照market_tree.py:57-65的处理方式
                        node_dict["hasChildren"] = False
                        node_dict["row_id"] = type_id
                        node_dict["name"] = node_dict.get(
                            "type_name_zh") or node_dict.get("type_name", "")
                        # 如果neo4j中没有type_name_zh，使用我们之前获取的
                        if not node_dict.get("type_name_zh") and type_id in type_id_to_name_zh:
                            node_dict["type_name_zh"] = type_id_to_name_zh[type_id]
                            node_dict["name"] = type_id_to_name_zh[type_id]
                        node_dict["can_add_plan"] = True  # 因为已经过滤过，都有蓝图
                        type_id_to_node[type_id] = node_dict

            # 按照原始type_ids的顺序构建结果列表，保留相关度排序
            market_nodes = []
            for type_id in type_ids:
                if type_id in type_id_to_node:
                    market_nodes.append(type_id_to_node[type_id])

        logger.info(
            f"用户 {user_id} 搜索关键词 '{keyword}'，找到 {len(market_nodes)} 个可生产的市场类型")
        return jsonify({
            "status": 200,
            "data": market_nodes,
            "count": len(market_nodes)
        })
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"搜索市场类型失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "搜索市场类型失败"}), 500


@api_industry_bp.route("/createPlan", methods=["POST"])
@auth_required
async def create_plan():
    """
    创建计划

    创建新的工业计划。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - name (string, required): 计划名称
        - 其他计划配置参数

    Responses:
        200: 创建成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "name": "计划名称",
            ...
        }

    Example Response:
        {
            "status": 200,
            "message": "计划创建成功"
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        plan_name = data["name"]
        data.pop("name")
        await IndustryManager().create_plan(user_id, plan_name, data)
        return jsonify({"message": "计划创建成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"创建计划失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建计划失败"}), 500


@api_industry_bp.route("/getPlanTableData", methods=["POST"])
@auth_required
async def get_plan_table_data():
    """
    获取计划表格数据

    获取当前用户的计划列表。管理员可以获取所有用户的计划。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回计划列表
            - status: 状态码 (200)
            - data: 计划列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "name": "计划名称",
                    ...
                }
            ]
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]
    logger.info(f"获取计划表格数据: {user_id}")

    try:
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles)
        for role in user_roles:
            descendant_roles = await permission_manager.get_all_descendant_roles(role)
            all_roles.update(descendant_roles)

        # 如果用户有admin角色，返回所有用户的计划
        if "admin" in all_roles:
            logger.info(f"管理员 {user_id} 获取所有用户的计划")
            plan_table_data = await IndustryManager.get_all_plans()
        else:
            plan_table_data = await IndustryManager.get_plan(user_id)

        logger.info(f"获取计划表格数据: {plan_table_data} ")
        return jsonify({"data": plan_table_data, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取计划表格数据失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取计划表格数据失败"}), 500


@api_industry_bp.route("/addPlanProduct", methods=["POST"])
@auth_required
async def add_plan_product():
    """
    添加计划产品

    向指定计划添加产品。管理员可以为其他用户添加产品。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - plan_name (string, required): 计划名称
        - type_id (integer, required): 产品类型ID
        - quantity (integer, required): 数量
        - user_name (string, optional): 用户名（仅管理员可用）

    Responses:
        200: 添加成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "plan_name": "计划名称",
            "type_id": 123,
            "quantity": 10
        }

    Example Response:
        {
            "status": 200,
            "message": "产品添加成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    try:
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(current_user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 添加用户 {user_id} 的计划产品: {data['plan_name']}")
        else:
            user_id = current_user_id

        await IndustryManager.add_plan_product(user_id, data["plan_name"], data["type_id"], data["quantity"])
        return jsonify({"message": "产品添加成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"添加产品失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加产品失败"}), 500


@api_industry_bp.route("/savePlanProducts", methods=["POST"])
@auth_required
async def save_plan_products():
    """
    保存计划产品

    批量保存计划的产品列表。管理员可以为其他用户保存产品。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - plan_name (string, required): 计划名称
        - products (array, required): 产品列表，每个元素包含type_id和quantity
        - user_name (string, optional): 用户名（仅管理员可用）

    Responses:
        200: 保存成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "plan_name": "计划名称",
            "products": [
                {
                    "type_id": 123,
                    "quantity": 10
                }
            ]
        }

    Example Response:
        {
            "status": 200,
            "message": "产品保存成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    try:
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(current_user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 保存用户 {user_id} 的计划产品: {data['plan_name']}")
        else:
            user_id = current_user_id

        await IndustryManager.save_plan_products(user_id, data["plan_name"], data["products"])
        return jsonify({"message": "产品保存成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存产品失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存产品失败"}), 500


@api_industry_bp.route("/getPlanCalculateResultTableView", methods=["POST"])
@auth_required
async def get_plan_calculate_result_table_view():
    data = await request.json
    current_user_id = g.current_user["user_id"]
    plan_name = data.get("plan_name")
    # 默认为 "calculate" 以保持向后兼容
    operate_type = data.get("operate_type", "calculate")

    # 如果提供了 user_name，使用它作为 user_id（管理员功能）
    # 否则使用当前用户的 user_id
    user_name = data.get("user_name")
    if user_name:
        user_id = user_name
    else:
        user_id = current_user_id

    try:
        if operate_type == "start":
            # 启动计算任务
            await IndustryManager.start_plan_calculation(user_id, plan_name)
            return jsonify({"status": 200, "message": "计算任务已启动"})

        elif operate_type == "status":
            # 查询计算状态
            status_data = await IndustryManager.get_calculation_status(user_id, plan_name)
            return jsonify({"status": 200, "data": status_data})

        elif operate_type == "result":
            # 获取计算结果
            result_data = await IndustryManager.get_calculation_result(user_id, plan_name)
            return jsonify({"status": 200, "data": result_data})

        else:
            # 向后兼容：直接计算并返回结果（原有行为）
            plan_settings = await IndustryManager.get_plan_settings(user_id, plan_name)
            op = await ConfigFlowOperateCenter.create(user_id, plan_name, plan_settings)
            await IndustryManager.calculate_plan(op)
            node_dict = {
                node['type_id']: node for node in await NIU.get_user_plan_node_with_distance(op.user_name, op.plan_name)
            }
            await MarketManager().update_jita_price()
            data = await IndustryManager.get_plan_tableview_data(op, node_dict)
            return jsonify({"status": 200, "data": data})

    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取计划计算结果表格视图失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取计划计算结果表格视图失败"}), 500


@api_industry_bp.route("/addIndustrypermision", methods=["POST"])
@auth_required
async def add_industrypermision():
    """
    添加工业许可

    为用户添加工业许可（容器权限）。管理员可以为其他用户添加许可。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - user_name (string, optional): 用户名（仅管理员可用）
        - 其他许可配置参数

    Responses:
        200: 添加成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "asset_owner_id": 123456,
            "asset_container_id": 789012,
            ...
        }

    Example Response:
        {
            "status": 200,
            "message": "新增许可成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    # 检查用户是否有admin角色
    user_roles = await permission_manager.get_user_roles(current_user_id)
    # 获取所有角色（直接角色 + 所有父角色）
    all_roles = set(user_roles or [])
    if user_roles:
        for role in user_roles:
            try:
                descendant_roles = await permission_manager.get_all_descendant_roles(role)
                if descendant_roles:
                    all_roles.update(descendant_roles)
            except Exception as e:
                logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

    # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
    is_admin = "admin" in all_roles
    if is_admin and "user_name" in data:
        user_id = data["user_name"]
        logger.info(f"管理员 {current_user_id} 为用户 {user_id} 新增许可")
    else:
        user_id = current_user_id

    try:
        await IndustryManager.add_industrypermision(user_id, data)
        return jsonify({"message": "新增许可成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"新增许可失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "新增许可失败"}), 500


@api_industry_bp.route("/getUserAllContainerPermission", methods=["POST"])
@auth_required
async def get_user_all_container_permission():
    """
    获取用户所有容器许可

    获取指定用户的所有容器许可列表。管理员可以查询其他用户的许可。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - user_name (string, optional): 用户名（仅管理员可用）
        - force_refresh (boolean, optional): 是否强制刷新缓存，默认false

    Responses:
        200: 成功返回许可列表
            - status: 状态码 (200)
            - data: 容器许可列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "force_refresh": false
        }

    Example Response:
        {
            "status": 200,
            "data": [...]
        }
    """
    current_user_id = g.current_user["user_id"]
    data = await request.json
    force_refresh = data.get("force_refresh", False)

    # 检查用户是否有admin角色
    user_roles = await permission_manager.get_user_roles(current_user_id)
    # 获取所有角色（直接角色 + 所有父角色）
    all_roles = set(user_roles or [])
    if user_roles:
        for role in user_roles:
            try:
                descendant_roles = await permission_manager.get_all_descendant_roles(role)
                if descendant_roles:
                    all_roles.update(descendant_roles)
            except Exception as e:
                logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

    # 如果用户有admin角色，允许通过 user_name 参数指定要查询的用户
    is_admin = "admin" in all_roles
    if is_admin and "user_name" in data:
        user_id = data["user_name"]
        logger.info(f"管理员 {current_user_id} 获取用户 {user_id} 的容器许可列表")
    else:
        user_id = current_user_id

    if force_refresh:
        await rdm().r.delete(f'container_permission:{user_id}:all_container_permission')

    try:
        all_container_permission = await IndustryManager.get_user_all_container_permission(user_id)
        return jsonify({"data": all_container_permission, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取用户所有容器许可失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取用户所有容器许可失败"}), 500


@api_industry_bp.route("/getLocationFlagList", methods=["POST"])
@auth_required
async def get_location_flag_list():
    """
    获取位置标志列表

    获取指定容器的可用位置标志列表。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - asset_owner_id (integer, required): 资产所有者ID
        - asset_container_id (integer, required): 资产容器ID

    Responses:
        200: 成功返回位置标志列表
            - status: 状态码 (200)
            - data: 位置标志列表，每个元素包含value和label (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "asset_owner_id": 123456,
            "asset_container_id": 789012
        }

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "value": "CorpSAG1",
                    "label": "公司机库1"
                }
            ]
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]
    asset_owner_id = data["asset_owner_id"]
    asset_container_id = data["asset_container_id"]

    try:
        location_flag_list = await IndustryManager.get_location_flag_list(asset_owner_id, asset_container_id)
        if location_flag_list:
            res_data = [{"value": item, "label": item.replace(
                'CorpSAG', '公司机库')} for item in location_flag_list]
            return jsonify({"data": res_data, "status": 200})
        else:
            return jsonify({"data": [], "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取位置标志列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取位置标志列表失败"}), 500

    return jsonify({"data": location_flag_list, "status": 200})


@api_industry_bp.route("/updateContainerPermissionLocationFlag", methods=["POST"])
@auth_required
async def update_container_permission_location_flag():
    """
    更新容器许可位置标志

    更新指定容器许可的位置标志。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - asset_owner_id (integer, required): 资产所有者ID
        - asset_container_id (integer, required): 资产容器ID
        - location_flag (string, required): 位置标志

    Responses:
        200: 更新成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "asset_owner_id": 123456,
            "asset_container_id": 789012,
            "location_flag": "CorpSAG1"
        }

    Example Response:
        {
            "status": 200,
            "message": "修改位置标志成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]
    try:
        asset_owner_id = data["asset_owner_id"]
        asset_container_id = data["asset_container_id"]
        location_flag = data["location_flag"]
        data = {
            "asset_owner_id": asset_owner_id,
            "asset_container_id": asset_container_id,
            "location_flag": location_flag
        }
        await IndustryManager.update_container_permission_location_flag(current_user_id, data)
        logger.info(
            f"{current_user_id} 修改用户 {current_user_id} 的容器许可位置标志: {asset_owner_id}, {asset_container_id}, {location_flag}")
        return jsonify({"message": "修改位置标志成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"修改位置标志失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "修改位置标志失败"}), 500


@api_industry_bp.route("/deleteIndustrypermision", methods=["POST"])
@auth_required
async def delete_industrypermision():
    """
    删除工业许可

    删除指定的工业许可（容器权限）。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - asset_owner_id (integer, required): 资产所有者ID
        - asset_container_id (integer, required): 资产容器ID

    Responses:
        200: 删除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "asset_owner_id": 123456,
            "asset_container_id": 789012
        }

    Example Response:
        {
            "status": 200,
            "message": "删除许可成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    # 检查用户是否有admin角色
    user_roles = await permission_manager.get_user_roles(current_user_id)
    # 获取所有角色（直接角色 + 所有父角色）
    all_roles = set(user_roles or [])
    if user_roles:
        for role in user_roles:
            try:
                descendant_roles = await permission_manager.get_all_descendant_roles(role)
                if descendant_roles:
                    all_roles.update(descendant_roles)
            except Exception as e:
                logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

    # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
    is_admin = "admin" in all_roles
    if is_admin and "user_name" in data:
        user_id = data["user_name"]
        logger.info(f"管理员 {current_user_id} 删除用户 {user_id} 的许可")
    else:
        user_id = current_user_id

    try:
        await IndustryManager.delete_industrypermision(user_id, data)
        return jsonify({"message": "删除许可成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除许可失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除许可失败"}), 500


@api_industry_bp.route("/updateContainerPermissionTag", methods=["POST"])
@auth_required
async def update_container_permission_tag():
    """
    更新容器许可标签

    更新指定容器许可的标签。管理员可以为其他用户更新标签。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - asset_owner_id (integer, required): 资产所有者ID
        - asset_container_id (integer, required): 资产容器ID
        - tag (string, required): 标签
        - user_name (string, optional): 用户名（仅管理员可用）

    Responses:
        200: 更新成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "asset_owner_id": 123456,
            "asset_container_id": 789012,
            "tag": "标签名称"
        }

    Example Response:
        {
            "status": 200,
            "message": "更新标签成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    # 检查用户是否有admin角色
    user_roles = await permission_manager.get_user_roles(current_user_id)
    # 获取所有角色（直接角色 + 所有父角色）
    all_roles = set(user_roles or [])
    if user_roles:
        for role in user_roles:
            try:
                descendant_roles = await permission_manager.get_all_descendant_roles(role)
                if descendant_roles:
                    all_roles.update(descendant_roles)
            except Exception as e:
                logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

    # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
    is_admin = "admin" in all_roles
    if is_admin and "user_name" in data:
        user_id = data["user_name"]
        logger.info(f"管理员 {current_user_id} 修改用户 {user_id} 的容器许可标签")
    else:
        user_id = current_user_id

    try:
        await IndustryManager.update_container_permission_tag(user_id, data)
        return jsonify({"message": "修改标签成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"修改标签失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "修改标签失败"}), 500


@api_industry_bp.route("/getStructureList", methods=["GET"])
@auth_required
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可拉取真实资产建筑。虚拟建筑可正常使用。")
async def get_structure_list():
    """
    获取建筑列表

    获取当前用户的建筑列表。仅ALPHA订阅者可拉取真实资产建筑。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回建筑列表
            - status: 状态码 (200)
            - data: 建筑列表 (array)
        402: 需要ALPHA订阅
            - status: 状态码 (402)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [...]
        }
    """
    user_id = g.current_user["user_id"]
    try:
        structure_list = await IndustryManager.get_structure_list(user_id)
        return jsonify({"data": structure_list, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取建筑列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取建筑列表失败"}), 500


@api_industry_bp.route("/getGroupSuggestions", methods=["POST"])
@auth_required
async def get_structure_assign_keyword_suggestions():
    """
    获取建筑分配关键字建议

    根据分配类型和查询关键字获取建议列表。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - assign_type (string, required): 分配类型
        - query (string, required): 查询关键字

    Responses:
        200: 成功返回建议列表
            - status: 状态码 (200)
            - data: 建议列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "assign_type": "group",
            "query": "关键字"
        }

    Example Response:
        {
            "status": 200,
            "data": [...]
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        assign_keyword_suggestions = await IndustryManager.get_structure_assign_keyword_suggestions(data["assign_type"], data["query"])
        return jsonify({"data": assign_keyword_suggestions, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取建筑分配关键字建议失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取建筑分配关键字建议失败"}), 500


@api_industry_bp.route("/getTypeList", methods=["GET"])
@auth_required
async def get_type_list():
    """
    获取类型列表

    获取所有可用的类型列表。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回类型列表
            - status: 状态码 (200)
            - data: 类型列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [...]
        }
    """
    user_id = g.current_user["user_id"]

    try:
        type_list = await IndustryManager.get_type_list()
        return jsonify({"data": type_list, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取类型列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取类型列表失败"}), 500


@api_industry_bp.route("/getTypeSuggestionsList", methods=["POST"])
@auth_required
async def get_type_suggestions_list():
    """
    获取类型建议列表

    根据查询关键字获取类型建议列表。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - query (string, required): 查询关键字

    Responses:
        200: 成功返回类型建议列表
            - status: 状态码 (200)
            - data: 类型建议列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "query": "关键字"
        }

    Example Response:
        {
            "status": 200,
            "data": [...]
        }
    """
    data = await request.json

    try:
        type_suggestions_list = await SdeUtils.fuzz_type(data["type_name"], list_len=10)
        type_suggestions_list = [{"value": item, "label": item}
                                 for item in type_suggestions_list]
        return jsonify({"data": type_suggestions_list, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取类型建议列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取类型建议列表失败"}), 500


@api_industry_bp.route("/searchMineralOrIceProduct", methods=["POST"])
@auth_required
async def search_mineral_or_ice_product():
    """
    搜索矿物或冰矿产物

    根据名称查询矿物或冰矿产物类型。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - name (string, required): 物品名称

    Responses:
        200: 成功返回查询结果
            - status: 状态码 (200)
            - data: 包含type_id、type_name、type_name_zh和material_type的对象，如果未找到则为null
            - message: 提示信息（可选）
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "name": "矿物名称"
        }

    Example Response:
        {
            "status": 200,
            "data": {
                "type_id": 123,
                "type_name": "Mineral Name",
                "type_name_zh": "矿物中文名称",
                "material_type": "矿石"
            }
        }
    """
    data = await request.json
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"status": 400, "message": "名称不能为空"}), 400

    try:
        # 根据名称获取 type_id
        type_id = await SdeUtils.get_id_by_name(name)
        if not type_id:
            return jsonify({"data": None, "status": 200, "message": "未找到该物品"}), 200

        # 判断是否为矿物或冰矿产物
        material_type = await get_material_type(type_id)
        if material_type not in ["矿石", "冰矿产物"]:
            return jsonify({"data": None, "status": 200, "message": "该物品不是矿物或冰矿产物"}), 200

        # 获取名称信息
        type_name = await SdeUtils.get_name_by_id(type_id, zh=False)
        type_name_zh = await SdeUtils.get_name_by_id(type_id, zh=True)

        return jsonify({
            "data": {
                "type_id": type_id,
                "type_name": type_name or "",
                "type_name_zh": type_name_zh or "",
                "material_type": material_type
            },
            "status": 200
        }), 200
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"查询矿物/冰矿产物失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "查询矿物/冰矿产物失败"}), 500


@api_industry_bp.route("/createConfigFlowConfig", methods=["POST"])
@auth_required
async def create_config_flow_config():
    """
    创建配置流配置

    创建新的配置流配置。管理员可以为其他用户创建配置。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - config_type (string, required): 配置类型
        - config_value (string, required): 配置值
        - user_name (string, optional): 用户名（仅管理员可用）
        - 其他配置参数

    Responses:
        200: 创建成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "config_type": "type",
            "config_value": "value"
        }

    Example Response:
        {
            "status": 200,
            "message": "创建配置流配置成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    try:
        # 检查管理员权限
        user_roles = await permission_manager.get_user_roles(current_user_id)
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")
        is_admin = "admin" in all_roles
        user_id = current_user_id
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(f"管理员 {current_user_id} 创建用户 {user_id} 的配置流配置: {data}")
        else:
            logger.info(f"创建配置流配置: {data}")

        if "config_type" not in data or "config_value" not in data or not data['config_value']:
            raise KahunaException(
                "config_type 和 config_value 不能为空，且 config_value 不能为空")
        await IndustryManager.create_config_flow_config(user_id, data)
        return jsonify({"message": "创建配置流配置成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except IntegrityError as e:
        logger.error(f"创建配置流配置失败 - 数据库完整性错误: {traceback.format_exc()}")
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        if "duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower():
            return jsonify({"status": 500, "message": "创建配置流配置失败：ID冲突，请稍后重试"}), 500
        return jsonify({"status": 500, "message": f"创建配置流配置失败：{error_msg}"}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"创建配置流配置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建配置流配置失败"}), 500


@api_industry_bp.route("/modifyConfigFlowConfig", methods=["POST"])
@auth_required
async def modify_config_flow_config():
    """
    修改配置流配置

    修改指定的配置流配置。管理员可以为其他用户修改配置。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - config_id (integer, required): 配置ID
        - config_type (string, optional): 配置类型
        - config_value (string, optional): 配置值
        - user_name (string, optional): 用户名（仅管理员可用）
        - 其他配置参数

    Responses:
        200: 修改成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "config_id": 1,
            "config_value": "new_value"
        }

    Example Response:
        {
            "status": 200,
            "message": "修改配置流配置成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    try:
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(current_user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(f"管理员 {current_user_id} 修改用户 {user_id} 的配置流配置: {data}")
        else:
            user_id = current_user_id
            logger.info(f"修改配置流配置: {data}")

        await IndustryManager.modify_config_flow_config(user_id, data, is_admin=is_admin)
        return jsonify({"message": "修改配置流配置成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"修改配置流配置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "修改配置流配置失败"}), 500


@api_industry_bp.route("/fetchRecommendedPresets", methods=["GET"])
@auth_required
async def fetch_recommended_presets():
    """
    获取推荐预设

    获取并创建推荐的配置流预设。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回预设统计
            - status: 状态码 (200)
            - data: 包含created和existing数量的统计对象
            - message: 提示信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {
                "created": 10,
                "existing": 5
            },
            "message": "成功创建 10 个配置，5 个配置已存在"
        }
    """
    user_id = g.current_user["user_id"]
    preset_name = "default_bp_and_material"

    try:
        stats = await IndustryManager.fetch_recommended_presets(user_id, preset_name)
        await IndustryManager.create_default_config_flow_preset(user_id)
        created_count = stats.get("created", 0)
        existing_count = stats.get("existing", 0)

        # 构造中文提示消息
        message = f"成功创建 {created_count} 个配置，{existing_count} 个配置已存在"

        return jsonify({"data": stats, "status": 200, "message": message})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"拉取推荐预设失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "拉取推荐预设失败"}), 500


@api_industry_bp.route("/deleteConfigFlowConfig", methods=["POST"])
@auth_required
async def delete_config_flow_config():
    """
    删除配置流配置

    删除指定的配置流配置。管理员可以为其他用户删除配置。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - config_id (integer, required): 配置ID
        - user_name (string, optional): 用户名（仅管理员可用）

    Responses:
        200: 删除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "config_id": 1
        }

    Example Response:
        {
            "status": 200,
            "message": "删除配置流配置成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    try:
        # 检查管理员权限
        user_roles = await permission_manager.get_user_roles(current_user_id)
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")
        is_admin = "admin" in all_roles
        user_id = current_user_id
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(f"管理员 {current_user_id} 删除用户 {user_id} 的配置流配置: {data}")

        await IndustryManager.delete_config_flow_config(user_id, data)
        return jsonify({"message": "删除配置流配置成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除配置流配置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除配置流配置失败"}), 500


@api_industry_bp.route("/getConfigFlowConfigList", methods=["GET"])
@auth_required
async def get_config_flow_config_list():
    """
    获取配置流配置列表

    获取当前用户的配置流配置列表。管理员可以查询其他用户的配置列表。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Parameters:
        - user_name (query, string, optional): 用户名（仅管理员可用）

    Responses:
        200: 成功返回配置列表
            - status: 状态码 (200)
            - data: 配置列表，按config_type排序 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [...]
        }
    """
    data = await request.json if request.is_json else {}
    current_user_id = g.current_user["user_id"]

    try:
        # 检查管理员权限
        user_roles = await permission_manager.get_user_roles(current_user_id)
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        user_id = current_user_id
        is_admin = "admin" in all_roles
        requested_user_name = None
        if isinstance(data, dict):
            requested_user_name = data.get("user_name")
        if not requested_user_name:
            requested_user_name = request.args.get("user_name")
        if is_admin and requested_user_name:
            user_id = requested_user_name
            logger.info(f"管理员 {current_user_id} 获取用户 {user_id} 的配置流配置列表")

        config_flow_config_list = await IndustryManager.get_config_flow_config_list(user_id)
        config_flow_config_list.sort(key=lambda x: x["config_type"])
        return jsonify({"data": config_flow_config_list, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取配置流配置列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取配置流配置列表失败"}), 500

# 添加配置到计划


@api_industry_bp.route("/addConfigToPlan", methods=["POST"])
@auth_required
async def add_config_to_plan():
    """
    添加配置到计划

    将配置流配置添加到指定计划。管理员可以为其他用户添加配置。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - plan_name (string, required): 计划名称
        - config_id (integer, required): 配置ID
        - user_name (string, optional): 用户名（仅管理员可用）

    Responses:
        200: 添加成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "plan_name": "计划名称",
            "config_id": 1
        }

    Example Response:
        {
            "status": 200,
            "message": "添加配置到计划成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    try:
        # 检查管理员权限
        user_roles = await permission_manager.get_user_roles(current_user_id)
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        is_admin = "admin" in all_roles
        user_id = current_user_id
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 添加配置到用户 {user_id} 的计划 {data.get('plan_name')}")

        await IndustryManager.add_config_to_plan(user_id, data)
        return jsonify({"message": "添加配置到计划成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"添加配置到计划失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加配置到计划失败"}), 500

# 获取计划配置流列表


@api_industry_bp.route("/getConfigFlowList", methods=["POST"])
@auth_required
async def get_config_flow_list():
    """
    获取配置流列表

    获取指定计划的配置流列表。管理员可以查询其他用户的配置流。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - plan_name (string, required): 计划名称
        - user_name (string, optional): 用户名（仅管理员可用）

    Responses:
        200: 成功返回配置流列表
            - status: 状态码 (200)
            - data: 配置流列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "plan_name": "计划名称"
        }

    Example Response:
        {
            "status": 200,
            "data": [...]
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    try:
        # 检查管理员权限
        user_roles = await permission_manager.get_user_roles(current_user_id)
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        is_admin = "admin" in all_roles
        user_id = current_user_id
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 获取用户 {user_id} 的计划配置流: {data['plan_name']}")

        config_flow_list = await IndustryManager.get_config_flow_list(user_id, data["plan_name"])
        return jsonify({"data": config_flow_list, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取配置流列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取配置流列表失败"}), 500

# 保存计划配置流


@api_industry_bp.route("/saveConfigFlowToPlan", methods=["POST"])
@auth_required
async def save_config_flow_to_plan():
    """
    保存配置流到计划

    保存配置流到指定计划。管理员可以为其他用户保存配置流。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - plan_name (string, required): 计划名称
        - config_flow (object, required): 配置流数据
        - user_name (string, optional): 用户名（仅管理员可用）

    Responses:
        200: 保存成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "plan_name": "计划名称",
            "config_flow": {...}
        }

    Example Response:
        {
            "status": 200,
            "message": "保存配置流成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    try:
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(current_user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 保存用户 {user_id} 的计划配置流: {data['plan_name']}")
        else:
            user_id = current_user_id

        await IndustryManager.save_config_flow_to_plan(user_id, data["plan_name"], data)
        return jsonify({"message": "保存配置流成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存配置流失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存配置流失败"}), 500

# 保存配置流预设


@api_industry_bp.route("/saveConfigFlowPreset", methods=["POST"])
@auth_required
async def save_config_flow_preset():
    """
    保存配置流预设

    保存配置流预设。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - preset_name (string, required): 预设名称
        - config_list (array, required): 配置列表

    Responses:
        200: 保存成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "preset_name": "预设名称",
            "config_list": [...]
        }

    Example Response:
        {
            "status": 200,
            "message": "保存预设成功"
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        preset_name = data["preset_name"]
        config_list = data["config_list"]
        await IndustryManager.save_config_flow_preset(user_id, preset_name, config_list)
        return jsonify({"message": "保存预设成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存预设失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存预设失败"}), 500

# 获取用户所有预设


@api_industry_bp.route("/getConfigFlowPresets", methods=["GET"])
@auth_required
async def get_config_flow_presets():
    """
    获取配置流预设列表

    获取当前用户的所有配置流预设列表。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回预设列表
            - status: 状态码 (200)
            - data: 预设列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [...]
        }
    """
    user_id = g.current_user["user_id"]

    try:
        presets = await IndustryManager.get_config_flow_presets(user_id)
        return jsonify({"data": presets, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取预设列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取预设列表失败"}), 500

# 加载预设到计划


@api_industry_bp.route("/loadConfigFlowPreset", methods=["POST"])
@auth_required
async def load_config_flow_preset():
    """
    加载配置流预设到计划

    将指定的配置流预设加载到计划中。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - preset_id (integer, required): 预设ID
        - plan_name (string, required): 计划名称

    Responses:
        200: 加载成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "preset_id": 1,
            "plan_name": "计划名称"
        }

    Example Response:
        {
            "status": 200,
            "message": "加载预设成功"
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        preset_id = data["preset_id"]
        plan_name = data["plan_name"]
        await IndustryManager.load_config_flow_preset(user_id, preset_id, plan_name)
        return jsonify({"message": "加载预设成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"加载预设失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "加载预设失败"}), 500

# 删除预设


@api_industry_bp.route("/deleteConfigFlowPreset", methods=["POST"])
@auth_required
async def delete_config_flow_preset():
    """
    删除配置流预设

    删除指定的配置流预设。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - preset_id (integer, required): 预设ID

    Responses:
        200: 删除成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "preset_id": 1
        }

    Example Response:
        {
            "status": 200,
            "message": "删除预设成功"
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        preset_id = data["preset_id"]
        await IndustryManager.delete_config_flow_preset(user_id, preset_id)
        return jsonify({"message": "删除预设成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除预设失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除预设失败"}), 500

# 更新预设名称


@api_industry_bp.route("/updateConfigFlowPresetName", methods=["POST"])
@auth_required
async def update_config_flow_preset_name():
    """
    更新配置流预设名称

    更新指定配置流预设的名称。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - preset_id (integer, required): 预设ID
        - preset_name (string, required): 新的预设名称

    Responses:
        200: 更新成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "preset_id": 1,
            "preset_name": "新预设名称"
        }

    Example Response:
        {
            "status": 200,
            "message": "更新预设名称成功"
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        preset_id = data["preset_id"]
        preset_name = data["preset_name"]
        await IndustryManager.update_config_flow_preset_name(user_id, preset_id, preset_name)
        return jsonify({"message": "更新预设名称成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"更新预设名称失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "更新预设名称失败"}), 500

# 分享预设（生成分享代码）


@api_industry_bp.route("/shareConfigFlowPreset", methods=["POST"])
@auth_required
async def share_config_flow_preset():
    """
    分享配置流预设

    生成配置流预设的分享代码。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - preset_id (integer, required): 预设ID

    Responses:
        200: 分享成功
            - status: 状态码 (200)
            - share_code: 分享代码 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "preset_id": 1
        }

    Example Response:
        {
            "status": 200,
            "share_code": "abc123"
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        preset_id = data["preset_id"]
        share_code = await IndustryManager.share_config_flow_preset(user_id, preset_id)
        return jsonify({"share_code": share_code, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"分享预设失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "分享预设失败"}), 500

# 载入分享预设


@api_industry_bp.route("/loadSharedConfigFlowPreset", methods=["POST"])
@auth_required
async def load_shared_config_flow_preset():
    """
    载入分享的配置流预设

    通过分享代码载入其他用户分享的配置流预设。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - share_code (string, required): 分享代码

    Responses:
        200: 载入成功
            - status: 状态码 (200)
            - message: 成功消息，包含创建的配置数量 (string)
            - data: 创建的配置列表 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "share_code": "abc123"
        }

    Example Response:
        {
            "status": 200,
            "message": "成功载入分享预设，创建了 5 个配置",
            "data": [...]
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        share_code = data["share_code"]
        created_configs = await IndustryManager.load_shared_config_flow_preset(user_id, share_code)
        return jsonify({"message": f"成功载入分享预设，创建了 {len(created_configs)} 个配置", "data": created_configs, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"载入分享预设失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "载入分享预设失败"}), 500

# 获取预设详情（用于编辑）


@api_industry_bp.route("/getConfigFlowPresetDetail", methods=["GET"])
@auth_required
async def get_config_flow_preset_detail():
    """
    获取配置流预设详情

    获取指定配置流预设的详细信息（用于编辑）。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Parameters:
        - preset_id (query, integer, required): 预设ID

    Responses:
        200: 成功返回预设详情
            - status: 状态码 (200)
            - data: 预设详情 (object)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {...}
        }
    """
    user_id = g.current_user["user_id"]
    preset_id = request.args.get("preset_id", type=int)

    try:
        if not preset_id:
            return jsonify({"status": 400, "message": "preset_id 参数不能为空"}), 400
        detail = await IndustryManager.get_config_flow_preset_detail(user_id, preset_id)
        return jsonify({"data": detail, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取预设详情失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取预设详情失败"}), 500

# 保存预设配置（用于编辑）


@api_industry_bp.route("/saveConfigFlowPresetConfig", methods=["POST"])
@auth_required
async def save_config_flow_preset_config():
    """
    保存配置流预设配置

    保存配置流预设的配置（用于编辑）。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - preset_id (integer, required): 预设ID
        - config_list (array, required): 配置列表

    Responses:
        200: 保存成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "preset_id": 1,
            "config_list": [...]
        }

    Example Response:
        {
            "status": 200,
            "message": "保存预设配置成功"
        }
    """
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        preset_id = data["preset_id"]
        config_list = data["config_list"]
        await IndustryManager.save_config_flow_preset_config(user_id, preset_id, config_list)
        return jsonify({"message": "保存预设配置成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存预设配置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存预设配置失败"}), 500

# # 获取计划设置


@api_industry_bp.route("/modifyPlanSettings", methods=["POST"])
@auth_required
async def modify_plan_settings():
    """
    修改计划设置

    修改指定计划的设置。管理员可以为其他用户修改计划设置。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - plan_name (string, required): 计划名称
        - plan_settings (object, required): 计划设置
        - user_name (string, optional): 用户名（仅管理员可用）

    Responses:
        200: 修改成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "plan_name": "计划名称",
            "plan_settings": {...}
        }

    Example Response:
        {
            "status": 200,
            "message": "修改计划设置成功"
        }
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]

    try:
        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(current_user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = await permission_manager.get_all_descendant_roles(role)
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 修改用户 {user_id} 的计划设置: {data['plan_name']}")
        else:
            user_id = current_user_id

        await IndustryManager.modify_plan_settings(user_id, data["plan_name"], data["plan_settings"])
        return jsonify({"message": "修改计划设置成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"修改计划设置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "修改计划设置失败"}), 500


@api_industry_bp.route("/deletePlan", methods=["POST"])
@auth_required
async def delete_plan():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        plan_name = data.get("plan_name")
        if not plan_name:
            return jsonify({"status": 400, "message": "计划名称不能为空"}), 400

        await IndustryManager.delete_plan(plan_name, user_id)
        return jsonify({"message": "计划删除成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除计划失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除计划失败"}), 500


@api_industry_bp.route("/getItemInfo", methods=["POST"])
@auth_required
async def get_item_info():
    """
    获取物品信息

    获取指定类型ID的物品信息。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - type_id (integer, required): 物品类型ID

    Responses:
        200: 成功返回物品信息
            - status: 状态码 (200)
            - data: 物品信息 (object)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "type_id": 123
        }

    Example Response:
        {
            "status": 200,
            "data": {...}
        }
    """
    data = await request.json

    try:
        item_info = await IndustryManager.get_item_info(data["type_id"])
        return jsonify({"data": item_info, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取物品信息失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取物品信息失败"}), 500


@api_industry_bp.route("/getLaborForceData", methods=["POST"])
@auth_required
async def get_labor_force_data():
    """
    获取劳动力数据

    获取指定计划的劳动力数据。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - plan_name (string, required): 计划名称

    Responses:
        200: 成功返回劳动力数据
            - status: 状态码 (200)
            - data: 劳动力数据 (string或object)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "plan_name": "计划名称"
        }

    Example Response:
        {
            "status": 200,
            "data": "获取劳动力数据成功"
        }
    """
    user_id = g.current_user["user_id"]

    try:
        return jsonify({"data": "获取劳动力数据成功", "status": 200}), 200
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取劳动力数据失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取劳动力数据失败"}), 500


@api_industry_bp.route("/getCompressedAsteroidData", methods=["POST"])
@auth_required
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可获取压缩矿数据。")
async def get_compressed_asteroid_data():
    """
    获取压缩矿数据

    根据矿物需求计算最优的压缩矿采购方案。仅ALPHA订阅者可获取压缩矿数据。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - mineral_data (array, required): 矿物数据列表，每个元素包含type_id、type_name、quantity、real_quantity
        - waste_penalty (number, optional): 浪费惩罚系数，默认0.1
        - shortage_penalty (number, optional): 不足惩罚系数，默认0.5
        - refinement_rate (number, optional): 化矿率，默认0.906
        - purchase_mode (string, optional): 采购模式，默认"扫单"
        - quantity_mode (string, optional): 数量模式，默认"缺失"
        - liquidity_impact (number, optional): 收单流动性溢价系数，默认0.0
        - purchase_time_limit (integer, optional): 采购时间上限（天），默认7
        - shipping_cost_per_volume (number, optional): 运费设置（isk/立方），默认0.0

    Responses:
        200: 成功返回压缩矿数据
            - status: 状态码 (200)
            - data: 包含采购方案、多余矿物、缺失矿物等信息的对象
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        402: 需要ALPHA订阅
            - status: 状态码 (402)
            - message: 错误信息 (string)
        500: 服务器错误或优化失败
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "mineral_data": [
                {
                    "type_id": 34,
                    "type_name": "Tritanium",
                    "quantity": 1000,
                    "real_quantity": 800
                }
            ],
            "waste_penalty": 0.1,
            "shortage_penalty": 0.5
        }

    Example Response:
        {
            "status": 200,
            "data": {
                "purcheses_res": {...},
                "excess_minerals_res": {...},
                "shortage_minerals_res": {...},
                "total_cost": 1000000
            }
        }
    """
    data = await request.json
    mineral_data = data.get('mineral_data', [])
    waste_penalty = data.get('waste_penalty', 0.1)  # 浪费惩罚系数，默认0.1
    shortage_penalty = data.get('shortage_penalty', 0.5)  # 不足惩罚系数，默认0.5
    refinement_rate = data.get('refinement_rate', 0.906)  # 化矿率，默认0.906
    purchase_mode = data.get('purchase_mode', '扫单')  # 采购模式，默认扫单
    quantity_mode = data.get('quantity_mode', '缺失')  # 数量模式，默认缺失
    liquidity_impact = data.get('liquidity_impact', 0.0)  # 收单流动性溢价系数，默认0（不启用）
    purchase_time_limit = data.get('purchase_time_limit', 7)  # 采购时间上限（天），默认7天
    shipping_cost_per_volume = data.get(
        'shipping_cost_per_volume', 0.0)  # 运费设置，单位为isk/立方，默认0
    user_id = g.current_user["user_id"]

    logger.info(f"获取压缩矿数据: {mineral_data}, waste_penalty: {waste_penalty}, shortage_penalty: {shortage_penalty}, refinement_rate: {refinement_rate}, purchase_mode: {purchase_mode}, quantity_mode: {quantity_mode}")
    try:
        # 验证输入数据
        if not isinstance(mineral_data, list):
            logger.error(f"mineral_data 必须是数组: {mineral_data}")
            return jsonify({"status": 400, "message": "mineral_data 必须是数组"}), 400

        # 如果 mineral_data 为空数组，返回空数据标识
        if len(mineral_data) == 0:
            empty_data = {
                "purcheses_res": {},
                "excess_minerals_res": {},
                "shortage_minerals_res": {},
                "mineral_yields": {},
                "total_cost": 0,
                "total_excess_price": 0,
                "mineral_purchases_res": {},
                "total_mineral_cost": 0,
                "is_empty": True  # 标识为空数据
            }
            return jsonify({"data": empty_data, "status": 200}), 200

        # 将 mineral_data 转换为 mineral_requirements 格式
        # mineral_data 格式: [{type_id, type_name, quantity, real_quantity}, ...]
        # mineral_requirements 格式: {mineral_id: required_quantity}
        mineral_requirements = {}
        for mineral in mineral_data:
            mineral_id = mineral.get('type_id')
            # 根据数量模式选择使用 quantity 或 real_quantity
            if quantity_mode == '缺失':
                quantity = mineral.get('real_quantity', 0)
            else:
                quantity = mineral.get('quantity', 0)

            if not mineral_id:
                logger.warning(f"跳过无效的矿物数据: {mineral}")
                continue

            if quantity <= 0:
                logger.warning(f"跳过数量为0或负数的矿物: type_id={mineral_id}")
                continue

            mineral_requirements[mineral_id] = float(quantity)

        # 如果 mineral_requirements 为空，返回空数据标识
        if not mineral_requirements:
            empty_data = {
                "purcheses_res": {},
                "excess_minerals_res": {},
                "shortage_minerals_res": {},
                "mineral_yields": {},
                "total_cost": 0,
                "total_excess_price": 0,
                "mineral_purchases_res": {},
                "total_mineral_cost": 0,
                "is_empty": True  # 标识为空数据
            }
            return jsonify({"data": empty_data, "status": 200}), 200

        logger.info(f"矿物需求: {mineral_requirements}")

        # 创建压缩矿工具实例并初始化数据
        compressed_asteroid_utils = CompressedAsteroidUtils()
        await compressed_asteroid_utils._init_type_material_data()

        # 调用优化求解器
        result = await compressed_asteroid_utils.optimize(
            mineral_requirements=mineral_requirements,
            waste_penalty=waste_penalty,
            shortage_penalty=shortage_penalty,
            refinement_rate=refinement_rate,
            purchase_mode=purchase_mode,
            liquidity_impact=liquidity_impact,
            purchase_time_limit=purchase_time_limit,
            shipping_cost_per_volume=shipping_cost_per_volume,
        )
        if result.get('status') != 'Optimal':
            logger.error(f"优化失败: {result.get('status')}")
            return jsonify({"status": 500, "message": "优化失败，请放宽限制条件。"}), 500

        solution = result.get('solution') or {}
        asteroid_purchases = solution.get('ore_purchases') or {}
        excess_minerals = solution.get('excess_minerals') or {}
        shortage_minerals = solution.get('shortage_minerals') or {}
        ore_price_details = solution.get('ore_price_details') or {}

        purcheses_res = {}
        total_cost = 0.0  # 基准总成本（用于前端展示）
        total_cost_with_liquidity = 0.0  # 含流动性溢价的总成本（仅用于需要时参考）

        for ore_id, quantity in asteroid_purchases.items():
            volume = await SdeUtils.get_volume_by_type_id(ore_id)
            price_detail = ore_price_details.get(
                ore_id, {}) if isinstance(ore_price_details, dict) else {}

            # 溢价前单价（基准价），若不存在则退化为当前单价
            unit_price_final = float(price_detail.get('unit_price', 0) or 0)
            base_unit_price = float(price_detail.get(
                'base_unit_price', unit_price_final) or 0)
            liquidity_premium_rate = float(price_detail.get(
                'liquidity_premium_rate', 0.0) or 0.0)

            # 基准总价用于展示
            total_price_base = base_unit_price * float(quantity or 0)
            # 含溢价总价用于内部参考或后续展示
            total_price_with_liquidity = float(price_detail.get(
                'total_price', unit_price_final * float(quantity or 0)) or 0)

            purcheses_res[ore_id] = {
                "quantity": quantity,
                # 前端主展示的总价使用基准价
                "total_price": total_price_base,
                "total_price_with_liquidity": total_price_with_liquidity,
                "name": await SdeUtils.get_name_by_id(ore_id),
                "name_zh": await SdeUtils.get_cn_name_by_id(ore_id),
                # 前端显示的平均价格使用基准价
                "avrprice": base_unit_price,
                "base_avrprice": base_unit_price,
                "liquidity_premium_rate": liquidity_premium_rate,
                "volume": volume if volume is not None else 0.0,
            }

            total_cost += total_price_base
            total_cost_with_liquidity += total_price_with_liquidity

        # 处理直接购买的矿物
        mineral_purchases_res = {}
        total_mineral_cost = 0
        direct_mineral_purchases = solution.get(
            'direct_mineral_purchases') or {}
        mineral_price_details = solution.get('mineral_price_details') or {}

        for mineral_id, quantity in direct_mineral_purchases.items():
            if isinstance(mineral_price_details, dict) and mineral_id in mineral_price_details:
                price_detail = mineral_price_details.get(mineral_id, {}) or {}
                volume = await SdeUtils.get_volume_by_type_id(mineral_id)
                mineral_purchases_res[mineral_id] = {
                    "quantity": quantity,
                    "total_price": price_detail.get('total_price', 0),
                    "name": await SdeUtils.get_name_by_id(mineral_id),
                    "name_zh": await SdeUtils.get_cn_name_by_id(mineral_id),
                    "avrprice": price_detail.get('unit_price', 0),
                    "volume": volume if volume is not None else 0.0,
                }
                total_mineral_cost += price_detail.get('total_price', 0)

        excess_minerals_res = {}
        total_excess_price = 0
        for mineral_id, quantity in excess_minerals.items():
            excess_minerals_res[mineral_id] = {
                "quantity": quantity,
                "name": await SdeUtils.get_name_by_id(mineral_id),
                "name_zh": await SdeUtils.get_cn_name_by_id(mineral_id),
                "price": await MarketManager().get_jita_buy_price(mineral_id),
            }
            total_excess_price += quantity * await MarketManager().get_jita_buy_price(mineral_id)

        # 处理不足矿物数据
        shortage_minerals_res = {}
        for mineral_id, quantity in shortage_minerals.items():
            if quantity > 0:
                shortage_minerals_res[mineral_id] = {
                    "quantity": quantity,
                    "name": await SdeUtils.get_name_by_id(mineral_id),
                    "name_zh": await SdeUtils.get_cn_name_by_id(mineral_id),
                    "price": await MarketManager().get_jita_buy_price(mineral_id),
                }

        # 计算每种矿石的矿物产出
        mineral_yields = {}
        refinement_rate = getattr(
            compressed_asteroid_utils, "_refinement_rate", refinement_rate)

        # 遍历购买的矿石
        for ore_id, quantity in asteroid_purchases.items():
            if quantity <= 0:
                continue

            # 获取该矿石产出的所有矿物
            type_material_dict = getattr(
                compressed_asteroid_utils, "_type_material_data_dict", None) or {}
            ore_mineral_yields = type_material_dict.get(ore_id, {})
            if not ore_mineral_yields:
                continue

            mineral_yields[ore_id] = {}
            is_ice = compressed_asteroid_utils._is_ice_ore(ore_id)
            for mineral_id, mineral_yield in ore_mineral_yields.items():
                if mineral_yield <= 0:
                    continue
                if is_ice:
                    # 冰矿：mineral_yield 是基于1份的产出
                    contribution = quantity * mineral_yield * refinement_rate
                else:
                    # 标准/卫星矿石：mineral_yield 是基于100份的产出
                    contribution = quantity * \
                        (mineral_yield / 100) * refinement_rate
                yield_quantity = math.floor(contribution)
                quantity_needed = mineral_requirements.get(mineral_id, 0)
                mineral_yields[ore_id][mineral_id] = [
                    yield_quantity, quantity_needed]

        logger.info(f"优化结果状态: {result.get('status')}")

        data = {
            "purcheses_res": purcheses_res,
            "excess_minerals_res": excess_minerals_res,
            "shortage_minerals_res": shortage_minerals_res,
            "mineral_yields": mineral_yields,
            # total_cost 使用基准成本，供前端展示
            "total_cost": total_cost,
            # 额外返回含流动性溢价的总成本，便于后续扩展或对比
            "total_cost_with_liquidity": total_cost_with_liquidity,
            "total_excess_price": total_excess_price,
            "mineral_purchases_res": mineral_purchases_res,
            "total_mineral_cost": total_mineral_cost,
        }
        logger.info(
            f"优化结果: total_cost(base): {total_cost}, "
            f"total_cost_with_liquidity: {total_cost_with_liquidity}, "
            f"total_mineral_cost: {total_mineral_cost}, total_excess_price: {total_excess_price}"
        )
        return jsonify({"data": data, "status": 200}), 200

    except KahunaException as e:
        traceback.print_exc()
        logger.error(f"获取压缩矿数据失败 (KahunaException): {str(e)}")
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取压缩矿数据失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取压缩矿数据失败"}), 500


@api_industry_bp.route("/syncPermissionToPlanConfig", methods=["POST"])
@auth_required
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可同步许可到计划配置。")
async def sync_permission_to_plan_config():
    """
    同步许可到计划配置

    将容器许可同步到计划配置中。管理员可以为其他用户同步许可。仅ALPHA订阅者可同步许可到计划配置。

    Tags:
        - EVE工业管理

    Security:
        - Bearer: []

    Request Body:
        - plan_name (string, required): 计划名称
        - user_name (string, optional): 用户名（仅管理员可用）

    Responses:
        200: 同步成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        402: 需要ALPHA订阅
            - status: 状态码 (402)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "plan_name": "计划名称"
        }

    Example Response:
        {
            "status": 200,
            "message": "同步许可到计划配置成功"
        }
    """
    current_user_id = g.current_user["user_id"]
    data = await request.json

    # 检查用户是否有admin角色
    user_roles = await permission_manager.get_user_roles(current_user_id)
    # 获取所有角色（直接角色 + 所有父角色）
    all_roles = set(user_roles or [])
    if user_roles:
        for role in user_roles:
            try:
                descendant_roles = await permission_manager.get_all_descendant_roles(role)
                if descendant_roles:
                    all_roles.update(descendant_roles)
            except Exception as e:
                logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

    # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
    is_admin = "admin" in all_roles
    if is_admin and "user_name" in data:
        user_id = data["user_name"]
        logger.info(f"管理员 {current_user_id} 同步用户 {user_id} 的许可到计划配置")
    else:
        user_id = current_user_id

    try:
        # 1. 获取当前用户的容器许可列表
        container_permissions = await IndustryManager.get_user_all_container_permission(user_id)

        # 2. 获取当前用户的配置流配置列表，筛选出 LoadAssetConf 类型
        all_configs = await IndustryManager.get_config_flow_config_list(user_id)
        load_asset_configs = [
            config for config in all_configs if config["config_type"] == "LoadAssetConf"]

        # 3. 建立映射关系
        # 访问许可的 (user_id, asset_container_id, asset_owner_id, location_flag) -> 访问许可对象
        permission_key_map = {}
        for perm in container_permissions:
            container_id = perm.get("asset_container_id")
            owner_id = perm.get("asset_owner_id")
            location_flag = perm.get("location_flag")
            if container_id and owner_id:
                key = (user_id, container_id, owner_id, location_flag)
                permission_key_map[key] = perm

        # LoadAssetConf 配置的 (user_id, asset_container_id, asset_owner_id, location_flag) -> 配置对象
        config_key_map = {}
        for config in load_asset_configs:
            config_value = config.get("config_value", {})
            container_id = config_value.get("asset_container_id")
            owner_id = config_value.get("asset_owner_id")
            location_flag = config_value.get("location_flag")
            if container_id and owner_id:
                key = (user_id, container_id, owner_id, location_flag)
                config_key_map[key] = config

        # 4. 找出需要创建的配置（访问许可有但配置没有）
        created_count = 0
        for key, permission in permission_key_map.items():
            if key not in config_key_map:
                # 创建新的 LoadAssetConf 配置
                config_data = {
                    "config_type": "LoadAssetConf",
                    "config_value": permission  # 使用访问许可的完整数据结构
                }
                await IndustryManager.create_config_flow_config(user_id, config_data)
                created_count += 1
                logger.info(
                    f"创建 LoadAssetConf 配置: container_id={permission.get('asset_container_id')}, owner_id={permission.get('asset_owner_id')}")

        # 5. 找出需要更新 tag 的配置（匹配但 tag 不一致）
        updated_count = 0
        for key, permission in permission_key_map.items():
            if key in config_key_map:
                config = config_key_map[key]
                config_value = config.get("config_value", {})
                permission_tag = permission.get("tag")
                config_tag = config_value.get(
                    "tag") or config_value.get("container_tag")

                # 如果 tag 不一致，更新配置
                if permission_tag != config_tag:
                    # 更新 config_value 中的 tag
                    updated_config_value = config_value.copy()
                    updated_config_value["tag"] = permission_tag
                    if "container_tag" in updated_config_value:
                        updated_config_value["container_tag"] = permission_tag

                    # 使用 modifyConfigFlowConfig 更新配置
                    modify_data = {
                        "config_id": config["config_id"],
                        "config_value": updated_config_value
                    }
                    await IndustryManager.modify_config_flow_config(user_id, modify_data, is_admin=is_admin)
                    updated_count += 1
                    logger.info(
                        f"更新 LoadAssetConf 配置 tag: container_id={permission.get('asset_container_id')}, owner_id={permission.get('asset_owner_id')}, old_tag={config_tag}, new_tag={permission_tag}")

        # 6. 找出需要删除的配置（配置有但访问许可没有）
        deleted_count = 0
        for key, config in config_key_map.items():
            if key not in permission_key_map:
                # 删除该配置
                delete_data = {
                    "config_id": config["config_id"]
                }
                await IndustryManager.delete_config_flow_config(user_id, delete_data)
                deleted_count += 1
                config_value = config.get("config_value", {})
                logger.info(
                    f"删除 LoadAssetConf 配置: container_id={config_value.get('asset_container_id')}, owner_id={config_value.get('asset_owner_id')}, config_id={config['config_id']}")

        message = f"同步完成：创建 {created_count} 个配置，更新 {updated_count} 个配置，删除 {deleted_count} 个配置"
        return jsonify({
            "message": message,
            "data": {
                "created": created_count,
                "updated": updated_count,
                "deleted": deleted_count
            },
            "status": 200
        })
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"同步许可到计划配置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "同步许可到计划配置失败"}), 500
