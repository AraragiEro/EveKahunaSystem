import asyncio
import datetime
import json
import math
import re
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import jwt

from src_v2.core.utils.datetime_utils import parse_naive_utc_datetime

from quart import Blueprint, Quart
from quart import current_app as app
from quart import g, jsonify, redirect, request
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from src_v2.backend.api.permission_required import role_required
from src_v2.backend.auth import auth_required, is_admin_user, verify_jwt_token
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveIndustryCalculateHistoryDBUtils,
    EveIndustryPlanTaskImplementationDBUtils,
)
from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU
from src_v2.core.log import logger
from src_v2.model.EVE.market.price_trend import build_price_trends
from src_v2.model.EVE.eve_constants import REGION_FORGE_ID
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.user.user_manager import UserManager
from src_v2.core.utils import KahunaException
from src_v2.model.EVE.industry.blueprint import BPManager as BPM
from src_v2.model.EVE.industry.industry_utils import (
    add_config_to_plan as _add_config_to_plan_impl,
    add_industrypermision as _add_industrypermision_impl,
    create_config_flow_config as _create_config_flow_config_impl,
    create_default_config_flow_preset,
    delete_config_flow_config as _delete_config_flow_config_impl,
    delete_config_flow_preset as _delete_config_flow_preset_impl,
    delete_config_from_plan,
    delete_industrypermision as _delete_industrypermision_impl,
    fetch_recommended_presets as _fetch_recommended_presets_impl,
    get_config_flow_config_list as _get_config_flow_config_list_impl,
    get_config_flow_list as _get_config_flow_list_impl,
    get_config_flow_preset_detail as _get_config_flow_preset_detail_impl,
    get_config_flow_presets as _get_config_flow_presets_impl,
    get_item_info as _get_item_info_impl,
    get_plan_tableview_data as _get_plan_tableview_data_impl,
    get_type_list as _get_type_list_impl,
    load_config_flow_preset as _load_config_flow_preset_impl,
    load_shared_config_flow_preset as _load_shared_config_flow_preset_impl,
    modify_config_flow_config as modify_config_flow,
    save_config_flow_preset as _save_config_flow_preset_impl,
    save_config_flow_preset_config as _save_config_flow_preset_config_impl,
    save_config_flow_to_plan as _save_config_flow_to_plan_impl,
    share_config_flow_preset as _share_config_flow_preset_impl,
    update_config_flow_preset_name as _update_config_flow_preset_name_impl,
    update_container_permission_location_flag as _update_container_permission_location_flag_impl,
    update_container_permission_tag as _update_container_permission_tag_impl,
    get_location_flag_list as _get_location_flag_list_impl,
    get_user_all_container_permission as _get_user_all_container_permission_impl,
    get_structure_assign_keyword_suggestions as _get_structure_assign_keyword_suggestions_impl,
    get_structure_list as _get_structure_list_impl,
)

from src_v2.model.EVE.industry.industry_manager import IndustryManager
from src_v2.model.EVE.industry.industry_utils.compressedAsteroid import (
    CompressedAsteroidUtils,
)
from src_v2.model.EVE.industry.industry_utils.market_tree import (
    get_market_tree as _get_market_tree_impl,
)
from src_v2.model.EVE.industry.industry_utils.material_utils import get_material_type
from src_v2.model.EVE.industry.industry_utils.bp_requirement_analyzer import (
    analyze_blueprint_requirements,
)
from src_v2.model.EVE.industry.plan_configflow_operate import ConfigFlowOperateCenter
from src_v2.model.EVE.market.market_manager import MarketManager
from src_v2.model.EVE.sde.utils import SdeUtils
from src_v2.backend.api import response_helper

api_industry_bp = Blueprint("api_industry", __name__, url_prefix="/api/EVE/industry")


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
        market_tree = await _get_market_tree_impl(data["node"])
        logger.info(f"获取 市场节点 {data['node']} 的子节点 {len(market_tree)} 个")
        return jsonify({"data": market_tree, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取市场树失败: {traceback.format_exc()}")
        return response_helper.server_error("获取市场树失败")


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
    keyword = data.get("keyword", "").strip()

    try:
        if not keyword:
            return response_helper.bad_request("搜索关键字不能为空")

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
                        primary_results.append(
                            {"type_id": type_id, "type_name_zh": type_name_zh}
                        )

        if not primary_results:
            return response_helper.ok(data=[], count=0)

        # 步骤4: 从neo4j查询Type节点（封装模块内实现）
        type_ids = [item["type_id"] for item in primary_results]
        type_nodes = await NIU.get_type_nodes_by_type_ids(type_ids)

        # 创建type_id到type_name_zh的映射
        type_id_to_name_zh = {
            item["type_id"]: item["type_name_zh"] for item in primary_results
        }

        # 步骤5: 处理查询结果，先存储到字典中
        type_id_to_node = {}
        for node_obj in type_nodes:
            node_dict = dict(node_obj)
            type_id = node_dict.get("type_id")
            if type_id:
                # 按照market_tree.py:57-65的处理方式
                node_dict["hasChildren"] = False
                node_dict["row_id"] = type_id
                node_dict["name"] = node_dict.get(
                    "type_name_zh"
                ) or node_dict.get("type_name", "")
                # 如果neo4j中没有type_name_zh，使用我们之前获取的
                if (
                    not node_dict.get("type_name_zh")
                    and type_id in type_id_to_name_zh
                ):
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
            f"用户 {user_id} 搜索关键词 '{keyword}'，找到 {len(market_nodes)} 个可生产的市场类型"
        )
        return jsonify(
            {"status": 200, "data": market_nodes, "count": len(market_nodes)}
        )
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"搜索市场类型失败: {traceback.format_exc()}")
        return response_helper.server_error("搜索市场类型失败")


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
        plan_name = data.get("name", "")
        if not plan_name or not plan_name.strip():
            return response_helper.bad_request("计划名称不能为空")
        data.pop("name")
        await IndustryManager().create_plan(user_id, plan_name, data)
        return jsonify({"message": "计划创建成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"创建计划失败: {traceback.format_exc()}")
        return response_helper.server_error("创建计划失败")


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

        plan_count = len(plan_table_data) if isinstance(plan_table_data, list) else 0
        logger.info(f"获取计划表格数据完成: user={user_id}, 计划条目数={plan_count}")
        logger.debug(f"获取计划表格数据明细: {plan_table_data}")
        return jsonify({"data": plan_table_data, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取计划表格数据失败: {traceback.format_exc()}")
        return response_helper.server_error("获取计划表格数据失败")


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
                    descendant_roles = (
                        await permission_manager.get_all_descendant_roles(role)
                    )
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 添加用户 {user_id} 的计划产品: {data['plan_name']}"
            )
        else:
            user_id = current_user_id

        await IndustryManager.add_plan_product(
            user_id, data["plan_name"], data["type_id"], data["quantity"]
        )
        return jsonify({"message": "产品添加成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        logger.error(f"添加产品失败: {traceback.format_exc()}")
        return response_helper.server_error("添加产品失败")


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
                    descendant_roles = (
                        await permission_manager.get_all_descendant_roles(role)
                    )
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 保存用户 {user_id} 的计划产品: {data['plan_name']}"
            )
        else:
            user_id = current_user_id

        await IndustryManager.save_plan_products(
            user_id, data["plan_name"], data["products"]
        )
        return jsonify({"message": "产品保存成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存产品失败: {traceback.format_exc()}")
        return response_helper.server_error("保存产品失败")


@api_industry_bp.route("/getPlanCalculateResultTableView", methods=["POST"])
@auth_required
async def get_plan_calculate_result_table_view():
    data = await request.json
    current_user_id = g.current_user["user_id"]
    plan_name = data.get("plan_name")
    # 默认为 "calculate" 以保持向后兼容
    operate_type = data.get("operate_type", "calculate")

    # 身份一律取当前登录用户；请求体里的 user_name 只有管理员可用于代查他人计划
    # （安全审计 #3：不能让请求参数直接替换身份，否则任何登录用户都能读他人计划）
    target_user_name = data.get("user_name")
    user_id = current_user_id
    if target_user_name and target_user_name != current_user_id:
        if not await is_admin_user(current_user_id):
            logger.warning(
                f"用户 {current_user_id} 尝试访问用户 {target_user_name} 的工业计划 {plan_name}，已拒绝"
            )
            return response_helper.forbidden("无权查看他人的工业计划")
        user_id = target_user_name
        logger.info(
            f"管理员 {current_user_id} 代查用户 {user_id} 的计划: {plan_name}"
        )

    try:
        if operate_type == "start":
            # 启动计算任务
            await IndustryManager.start_plan_calculation(user_id, plan_name)
            return response_helper.ok(message="计算任务已启动")

        elif operate_type == "status":
            # 查询计算状态
            status_data = await IndustryManager.get_calculation_status(
                user_id, plan_name
            )
            return response_helper.ok(status_data)

        elif operate_type == "result":
            # 获取计算结果
            result_data = await IndustryManager.get_calculation_result(
                user_id, plan_name
            )

            # 获取最新的计算历史记录ID作为 calculation_id
            try:
                # 查询最近一次计算历史（封装模块内实现）
                latest_history = await EveIndustryCalculateHistoryDBUtils.get_latest_by_user_and_plan(
                    user_id, plan_name
                )
                if latest_history:
                    result_data["calculation_id"] = latest_history.id
                else:
                    # 如果没有历史记录，使用当前时间戳作为 fallback
                    result_data["calculation_id"] = int(
                        datetime.datetime.utcnow().timestamp() * 1000
                    )
            except Exception as e:
                logger.warning(f"获取计算历史记录ID失败: {e}")
                # fallback: 使用当前时间戳
                result_data["calculation_id"] = int(
                    datetime.datetime.utcnow().timestamp() * 1000
                )

            return response_helper.ok(result_data)

        else:
            # 向后兼容：直接计算并返回结果（原有行为）
            plan_settings = await IndustryManager.get_plan_settings(user_id, plan_name)
            op = await ConfigFlowOperateCenter.create(user_id, plan_name, plan_settings)
            await IndustryManager.calculate_plan(op)
            node_dict = {
                node["type_id"]: node
                for node in await NIU.get_user_plan_node_with_distance(
                    op.user_name, op.plan_name
                )
            }
            await MarketManager().update_jita_price()
            data = await _get_plan_tableview_data_impl(op, node_dict)
            return response_helper.ok(data)

    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取计划计算结果表格视图失败: {traceback.format_exc()}")
        return response_helper.server_error("获取计划计算结果表格视图失败")


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
                descendant_roles = await permission_manager.get_all_descendant_roles(
                    role
                )
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
        await _add_industrypermision_impl(user_id, data)
        return jsonify({"message": "新增许可成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"新增许可失败: {traceback.format_exc()}")
        return response_helper.server_error("新增许可失败")


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
                descendant_roles = await permission_manager.get_all_descendant_roles(
                    role
                )
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
        await rdm().r.delete(f"container_permission:{user_id}:all_container_permission")

    try:
        all_container_permission = (
            await _get_user_all_container_permission_impl(user_id)
        )
        return jsonify({"data": all_container_permission, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取用户所有容器许可失败: {traceback.format_exc()}")
        return response_helper.server_error("获取用户所有容器许可失败")


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
        location_flag_list = await _get_location_flag_list_impl(
            asset_owner_id, asset_container_id
        )
        if location_flag_list:
            res_data = [
                {"value": item, "label": item.replace("CorpSAG", "公司机库")}
                for item in location_flag_list
            ]
            return jsonify({"data": res_data, "status": 200})
        else:
            return jsonify({"data": [], "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取位置标志列表失败: {traceback.format_exc()}")
        return response_helper.server_error("获取位置标志列表失败")

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
            "location_flag": location_flag,
        }
        await _update_container_permission_location_flag_impl(
            current_user_id, data
        )
        logger.info(
            f"{current_user_id} 修改用户 {current_user_id} 的容器许可位置标志: {asset_owner_id}, {asset_container_id}, {location_flag}"
        )
        return jsonify({"message": "修改位置标志成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"修改位置标志失败: {traceback.format_exc()}")
        return response_helper.server_error("修改位置标志失败")


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
                descendant_roles = await permission_manager.get_all_descendant_roles(
                    role
                )
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
        await _delete_industrypermision_impl(user_id, data)
        return jsonify({"message": "删除许可成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除许可失败: {traceback.format_exc()}")
        return response_helper.server_error("删除许可失败")


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
                descendant_roles = await permission_manager.get_all_descendant_roles(
                    role
                )
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
        await _update_container_permission_tag_impl(user_id, data)
        return jsonify({"message": "修改标签成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"修改标签失败: {traceback.format_exc()}")
        return response_helper.server_error("修改标签失败")


@api_industry_bp.route("/getStructureList", methods=["GET"])
@auth_required
@role_required(
    ["vip_alpha"], 402, "仅ALPHA订阅者可拉取真实资产建筑。虚拟建筑可正常使用。"
)
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
        structure_list = await _get_structure_list_impl(user_id)
        return jsonify({"data": structure_list, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取建筑列表失败: {traceback.format_exc()}")
        return response_helper.server_error("获取建筑列表失败")


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
        assign_keyword_suggestions = (
            await _get_structure_assign_keyword_suggestions_impl(
                data["assign_type"], data["query"]
            )
        )
        return jsonify({"data": assign_keyword_suggestions, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取建筑分配关键字建议失败: {traceback.format_exc()}")
        return response_helper.server_error("获取建筑分配关键字建议失败")


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
        type_list = await _get_type_list_impl()
        return jsonify({"data": type_list, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取类型列表失败: {traceback.format_exc()}")
        return response_helper.server_error("获取类型列表失败")


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
        type_suggestions_list = [
            {"value": item, "label": item} for item in type_suggestions_list
        ]
        return jsonify({"data": type_suggestions_list, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取类型建议列表失败: {traceback.format_exc()}")
        return response_helper.server_error("获取类型建议列表失败")


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
        return response_helper.bad_request("名称不能为空")

    try:
        # 根据名称获取 type_id
        type_id = await SdeUtils.get_id_by_name(name)
        if not type_id:
            return jsonify(
                {"data": None, "status": 200, "message": "未找到该物品"}
            ), 200

        # 判断是否为矿物或冰矿产物
        material_type = await get_material_type(type_id)
        if material_type not in ["矿物", "冰矿产物"]:
            return jsonify(
                {"data": None, "status": 200, "message": "该物品不是矿物或冰矿产物"}
            ), 200

        # 获取名称信息
        type_name = await SdeUtils.get_name_by_id(type_id, zh=False)
        type_name_zh = await SdeUtils.get_name_by_id(type_id, zh=True)

        return jsonify(
            {
                "data": {
                    "type_id": type_id,
                    "type_name": type_name or "",
                    "type_name_zh": type_name_zh or "",
                    "material_type": material_type,
                },
                "status": 200,
            }
        ), 200
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"查询矿物/冰矿产物失败: {traceback.format_exc()}")
        return response_helper.server_error("查询矿物/冰矿产物失败")


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
                    descendant_roles = (
                        await permission_manager.get_all_descendant_roles(role)
                    )
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")
        is_admin = "admin" in all_roles
        user_id = current_user_id
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 创建用户 {user_id} 的配置流配置: {data}"
            )
        else:
            logger.info(f"创建配置流配置: {data}")

        if (
            "config_type" not in data
            or "config_value" not in data
            or not data["config_value"]
        ):
            raise KahunaException(
                "config_type 和 config_value 不能为空，且 config_value 不能为空"
            )
        await _create_config_flow_config_impl(user_id, data)
        return jsonify({"message": "创建配置流配置成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except IntegrityError as e:
        logger.error(f"创建配置流配置失败 - 数据库完整性错误: {traceback.format_exc()}")
        error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
        if (
            "duplicate key" in error_msg.lower()
            or "unique constraint" in error_msg.lower()
        ):
            return jsonify(
                {"status": 500, "message": "创建配置流配置失败：ID冲突，请稍后重试"}
            ), 500
        return jsonify(
            {"status": 500, "message": f"创建配置流配置失败：{error_msg}"}
        ), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"创建配置流配置失败: {traceback.format_exc()}")
        return response_helper.server_error("创建配置流配置失败")


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
                    descendant_roles = (
                        await permission_manager.get_all_descendant_roles(role)
                    )
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 修改用户 {user_id} 的配置流配置: {data}"
            )
        else:
            user_id = current_user_id
            logger.info(f"修改配置流配置: {data}")

        await modify_config_flow(
            user_id, data, is_admin=is_admin
        )
        return jsonify({"message": "修改配置流配置成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"修改配置流配置失败: {traceback.format_exc()}")
        return response_helper.server_error("修改配置流配置失败")


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
        stats = await _fetch_recommended_presets_impl(user_id, preset_name)
        await create_default_config_flow_preset(user_id)
        created_count = stats.get("created", 0)
        existing_count = stats.get("existing", 0)

        # 构造中文提示消息
        message = f"成功创建 {created_count} 个配置，{existing_count} 个配置已存在"

        return jsonify({"data": stats, "status": 200, "message": message})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"拉取推荐预设失败: {traceback.format_exc()}")
        return response_helper.server_error("拉取推荐预设失败")


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
                    descendant_roles = (
                        await permission_manager.get_all_descendant_roles(role)
                    )
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")
        is_admin = "admin" in all_roles
        user_id = current_user_id
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 删除用户 {user_id} 的配置流配置: {data}"
            )

        await _delete_config_flow_config_impl(user_id, data)
        return jsonify({"message": "删除配置流配置成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除配置流配置失败: {traceback.format_exc()}")
        return response_helper.server_error("删除配置流配置失败")


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
                    descendant_roles = (
                        await permission_manager.get_all_descendant_roles(role)
                    )
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

        config_flow_config_list = await _get_config_flow_config_list_impl(
            user_id
        )
        config_flow_config_list.sort(key=lambda x: x["config_type"])
        return jsonify({"data": config_flow_config_list, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取配置流配置列表失败: {traceback.format_exc()}")
        return response_helper.server_error("获取配置流配置列表失败")


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
                    descendant_roles = (
                        await permission_manager.get_all_descendant_roles(role)
                    )
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        is_admin = "admin" in all_roles
        user_id = current_user_id
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 添加配置到用户 {user_id} 的计划 {data.get('plan_name')}"
            )

        await _add_config_to_plan_impl(user_id, data)
        return jsonify({"message": "添加配置到计划成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"添加配置到计划失败: {traceback.format_exc()}")
        return response_helper.server_error("添加配置到计划失败")


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
                    descendant_roles = (
                        await permission_manager.get_all_descendant_roles(role)
                    )
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        is_admin = "admin" in all_roles
        user_id = current_user_id
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 获取用户 {user_id} 的计划配置流: {data['plan_name']}"
            )

        config_flow_list = await _get_config_flow_list_impl(
            user_id, data["plan_name"]
        )
        logger.info(
            f"获取计划配置流完成: operator={current_user_id}, target={user_id}, "
            f"plan_name={data['plan_name']}, 配置条目数={len(config_flow_list)}"
        )
        logger.debug(f"获取计划配置流明细: {config_flow_list}")
        return jsonify({"data": config_flow_list, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取配置流列表失败: {traceback.format_exc()}")
        return response_helper.server_error("获取配置流列表失败")


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
    try:
        data = await request.get_json()
        current_user = getattr(g, "current_user", {}) or {}
        current_user_id = current_user.get("user_id")

        logger.info(
            f"[saveConfigFlowToPlan] 请求进入 current_user_id={current_user_id}, "
            f"has_data={data is not None}, keys={list(data.keys()) if isinstance(data, dict) else 'not_dict'}"
        )

        if not isinstance(data, dict):
            logger.warning("[saveConfigFlowToPlan] 请求体不是JSON对象")
            return response_helper.bad_request("请求体必须是JSON对象")
        if not current_user_id:
            logger.warning(
                "[saveConfigFlowToPlan] 当前用户信息缺失，token可能无user_id"
            )
            return response_helper.unauthorized("用户认证信息无效")
        if "plan_name" not in data:
            logger.warning("[saveConfigFlowToPlan] 缺少必填参数 plan_name")
            return response_helper.bad_request("缺少参数 plan_name")
        if "config_list" not in data or not isinstance(data["config_list"], list):
            logger.warning("[saveConfigFlowToPlan] 缺少或非法参数 config_list")
            return jsonify(
                {"status": 400, "message": "缺少参数 config_list 或类型错误"}
            ), 400

        # 检查用户是否有admin角色
        user_roles = await permission_manager.get_user_roles(current_user_id)
        # 获取所有角色（直接角色 + 所有父角色）
        all_roles = set(user_roles or [])
        if user_roles:
            for role in user_roles:
                try:
                    descendant_roles = (
                        await permission_manager.get_all_descendant_roles(role)
                    )
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 保存用户 {user_id} 的计划配置流: {data['plan_name']}"
            )
        else:
            user_id = current_user_id

        await _save_config_flow_to_plan_impl(user_id, data["plan_name"], data)
        logger.info(
            f"[saveConfigFlowToPlan] 保存成功 operator={current_user_id}, target={user_id}, "
            f"plan_name={data['plan_name']}, config_count={len(data['config_list'])}"
        )
        return jsonify({"message": "保存配置流成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        logger.error(f"[saveConfigFlowToPlan] 业务异常: {str(e)}", exc_info=True)
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"[saveConfigFlowToPlan] 未知异常: {str(e)}", exc_info=True)
        return response_helper.server_error("保存配置流失败")


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
        await _save_config_flow_preset_impl(user_id, preset_name, config_list)
        return jsonify({"message": "保存预设成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存预设失败: {traceback.format_exc()}")
        return response_helper.server_error("保存预设失败")


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
        presets = await _get_config_flow_presets_impl(user_id)
        return jsonify({"data": presets, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取预设列表失败: {traceback.format_exc()}")
        return response_helper.server_error("获取预设列表失败")


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
        await _load_config_flow_preset_impl(user_id, preset_id, plan_name)
        return jsonify({"message": "加载预设成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"加载预设失败: {traceback.format_exc()}")
        return response_helper.server_error("加载预设失败")


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
        await _delete_config_flow_preset_impl(user_id, preset_id)
        return jsonify({"message": "删除预设成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除预设失败: {traceback.format_exc()}")
        return response_helper.server_error("删除预设失败")


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
        await _update_config_flow_preset_name_impl(
            user_id, preset_id, preset_name
        )
        return jsonify({"message": "更新预设名称成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"更新预设名称失败: {traceback.format_exc()}")
        return response_helper.server_error("更新预设名称失败")


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
        share_code = await _share_config_flow_preset_impl(user_id, preset_id)
        return jsonify({"share_code": share_code, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"分享预设失败: {traceback.format_exc()}")
        return response_helper.server_error("分享预设失败")


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
        created_configs = await _load_shared_config_flow_preset_impl(
            user_id, share_code
        )
        return jsonify(
            {
                "message": f"成功载入分享预设，创建了 {len(created_configs)} 个配置",
                "data": created_configs,
                "status": 200,
            }
        )
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"载入分享预设失败: {traceback.format_exc()}")
        return response_helper.server_error("载入分享预设失败")


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
            return response_helper.bad_request("preset_id 参数不能为空")
        detail = await _get_config_flow_preset_detail_impl(user_id, preset_id)
        return jsonify({"data": detail, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取预设详情失败: {traceback.format_exc()}")
        return response_helper.server_error("获取预设详情失败")


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
        await _save_config_flow_preset_config_impl(
            user_id, preset_id, config_list
        )
        return jsonify({"message": "保存预设配置成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"保存预设配置失败: {traceback.format_exc()}")
        return response_helper.server_error("保存预设配置失败")


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
                    descendant_roles = (
                        await permission_manager.get_all_descendant_roles(role)
                    )
                    if descendant_roles:
                        all_roles.update(descendant_roles)
                except Exception as e:
                    logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")

        # 如果用户有admin角色，允许通过 user_name 参数指定要操作的用户
        is_admin = "admin" in all_roles
        if is_admin and "user_name" in data:
            user_id = data["user_name"]
            logger.info(
                f"管理员 {current_user_id} 修改用户 {user_id} 的计划设置: {data['plan_name']}"
            )
        else:
            user_id = current_user_id

        await IndustryManager.modify_plan_settings(
            user_id, data["plan_name"], data["plan_settings"]
        )
        return jsonify({"message": "修改计划设置成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"修改计划设置失败: {traceback.format_exc()}")
        return response_helper.server_error("修改计划设置失败")


@api_industry_bp.route("/deletePlan", methods=["POST"])
@auth_required
async def delete_plan():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        plan_name = data.get("plan_name")
        if plan_name is None:
            return response_helper.bad_request("计划名称不能为空")

        await IndustryManager.delete_plan(plan_name, user_id)
        return jsonify({"message": "计划删除成功", "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"删除计划失败: {traceback.format_exc()}")
        return response_helper.server_error("删除计划失败")


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
        item_info = await _get_item_info_impl(data["type_id"])
        return jsonify({"data": item_info, "status": 200})
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取物品信息失败: {traceback.format_exc()}")
        return response_helper.server_error("获取物品信息失败")


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
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取劳动力数据失败: {traceback.format_exc()}")
        return response_helper.server_error("获取劳动力数据失败")


@api_industry_bp.route("/getMarket4HPrices", methods=["POST"])
@auth_required
async def get_market_4h_prices():
    """
    批量获取 JITA 与 4-H（FRT）市场的卖单/买单价格（读取 Redis 快照）。

    Request Body:
        - type_ids (int[], required): 物品类型ID（最多 500 个）

    Responses:
        200: { status: 200, data: { "<type_id>": { jita_sell, jita_buy, frt_sell, frt_buy } } }
    """
    try:
        body = await request.get_json() or {}
        raw = body.get("type_ids") or []
        try:
            type_ids = [int(t) for t in raw if str(t).lstrip("-").isdigit()]
        except Exception:
            type_ids = []
        type_ids = list(dict.fromkeys(type_ids))[:500]
        if not type_ids:
            return response_helper.bad_request("type_ids 不能为空")

        def _f(v):
            try:
                return round(float(v), 2)
            except Exception:
                return 0.0

        data = {}
        for tid in type_ids:
            jita = await rdm().r.hgetall(f"market_price:jita:{tid}")
            frt = await rdm().r.hgetall(f"market_price:frt:{tid}")
            data[str(tid)] = {
                "jita_sell": _f((jita or {}).get("min_sell")),
                "jita_buy": _f((jita or {}).get("max_buy")),
                "frt_sell": _f((frt or {}).get("min_sell")),
                "frt_buy": _f((frt or {}).get("max_buy")),
            }
        return jsonify({"status": 200, "data": data})
    except Exception:
        traceback.print_exc()
        logger.error(f"获取 4H 价格失败: {traceback.format_exc()}")
        return response_helper.server_error("获取 4H 价格失败")

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
        - market_supply_ratio (number, optional): 市场供给比例（仅扫单模式），默认1.0。将市场挂单量乘以此系数作为购买上限，取值范围0.0～1.0
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
    mineral_data = data.get("mineral_data", [])
    waste_penalty = data.get("waste_penalty", 0.1)  # 浪费惩罚系数，默认0.1
    shortage_penalty = data.get("shortage_penalty", 0.5)  # 不足惩罚系数，默认0.5
    refinement_rate = data.get("refinement_rate", 0.906)  # 化矿率，默认0.906
    purchase_mode = data.get("purchase_mode", "扫单")  # 采购模式，默认扫单
    quantity_mode = data.get("quantity_mode", "缺失")  # 数量模式，默认缺失
    liquidity_impact = data.get(
        "liquidity_impact", 0.0
    )  # 收单流动性溢价系数，默认0（不启用）
    purchase_time_limit = data.get(
        "purchase_time_limit", 7
    )  # 采购时间上限（天），默认7天
    market_supply_ratio = data.get(
        "market_supply_ratio", 1.0
    )  # 市场供给比例，默认1.0（100%），仅扫单模式生效
    shipping_cost_per_volume = data.get(
        "shipping_cost_per_volume", 0.0
    )  # 运费设置，单位为isk/立方，默认0
    allow_direct_mineral_purchase = data.get(
        "allow_direct_mineral_purchase", True
    )  # 是否允许直接购买矿物，默认允许
    output_value_reward_rate = data.get(
        "output_value_reward_rate", 0.0
    )  # 产出价值奖励系数，默认0.0
    blacklist = data.get("blacklist", [])  # 矿石黑名单 type_id 列表
    user_id = g.current_user["user_id"]

    logger.info(
        f"获取压缩矿数据: {mineral_data}, waste_penalty: {waste_penalty}, shortage_penalty: {shortage_penalty}, refinement_rate: {refinement_rate}, purchase_mode: {purchase_mode}, quantity_mode: {quantity_mode}"
    )
    try:
        # 验证输入数据
        if not isinstance(mineral_data, list):
            logger.error(f"mineral_data 必须是数组: {mineral_data}")
            return response_helper.bad_request("mineral_data 必须是数组")

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
                "is_empty": True,  # 标识为空数据
            }
            return jsonify({"data": empty_data, "status": 200}), 200

        # 将 mineral_data 转换为 mineral_requirements 格式
        # mineral_data 格式: [{type_id, type_name, quantity, real_quantity}, ...]
        # mineral_requirements 格式: {mineral_id: required_quantity}
        mineral_requirements = {}
        for mineral in mineral_data:
            mineral_id = mineral.get("type_id")
            # 根据数量模式选择使用 quantity 或 real_quantity
            if quantity_mode == "缺失":
                quantity = mineral.get("real_quantity", 0)
            else:
                quantity = mineral.get("quantity", 0)

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
                "is_empty": True,  # 标识为空数据
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
            refinement_rate=refinement_rate,
            purchase_mode=purchase_mode,
            liquidity_impact=liquidity_impact,
            purchase_time_limit=purchase_time_limit,
            market_supply_ratio=market_supply_ratio,
            shipping_cost_per_volume=shipping_cost_per_volume,
            allow_direct_mineral_purchase=allow_direct_mineral_purchase,
            output_value_reward_rate=output_value_reward_rate,
            blacklist=blacklist,
        )
        if result.get("status") != "Optimal":
            logger.error(f"优化失败: {result.get('status')}")
            return jsonify(
                {"status": 500, "message": "优化失败，请放宽限制条件。"}
            ), 500

        solution = result.get("solution") or {}
        asteroid_purchases = solution.get("ore_purchases") or {}
        excess_minerals = solution.get("excess_minerals") or {}
        shortage_minerals = solution.get("shortage_minerals") or {}
        ore_price_details = solution.get("ore_price_details") or {}

        purcheses_res = {}
        total_cost = 0.0  # 基准总成本（用于前端展示）
        total_cost_with_liquidity = 0.0  # 含流动性溢价的总成本（仅用于需要时参考）

        for ore_id, quantity in asteroid_purchases.items():
            volume = await SdeUtils.get_volume_by_type_id(ore_id)
            price_detail = (
                ore_price_details.get(ore_id, {})
                if isinstance(ore_price_details, dict)
                else {}
            )

            # 溢价前单价（基准价），若不存在则退化为当前单价
            unit_price_final = float(price_detail.get("unit_price", 0) or 0)
            base_unit_price = float(
                price_detail.get("base_unit_price", unit_price_final) or 0
            )
            liquidity_premium_rate = float(
                price_detail.get("liquidity_premium_rate", 0.0) or 0.0
            )

            # 基准总价用于展示
            total_price_base = base_unit_price * float(quantity or 0)
            # 含溢价总价用于内部参考或后续展示
            total_price_with_liquidity = float(
                price_detail.get("total_price", unit_price_final * float(quantity or 0))
                or 0
            )

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
        direct_mineral_purchases = solution.get("direct_mineral_purchases") or {}
        mineral_price_details = solution.get("mineral_price_details") or {}

        for mineral_id, quantity in direct_mineral_purchases.items():
            if (
                isinstance(mineral_price_details, dict)
                and mineral_id in mineral_price_details
            ):
                price_detail = mineral_price_details.get(mineral_id, {}) or {}
                volume = await SdeUtils.get_volume_by_type_id(mineral_id)
                mineral_purchases_res[mineral_id] = {
                    "quantity": quantity,
                    "total_price": price_detail.get("total_price", 0),
                    "name": await SdeUtils.get_name_by_id(mineral_id),
                    "name_zh": await SdeUtils.get_cn_name_by_id(mineral_id),
                    "avrprice": price_detail.get("unit_price", 0),
                    "volume": volume if volume is not None else 0.0,
                }
                total_mineral_cost += price_detail.get("total_price", 0)

        excess_minerals_res = {}
        total_excess_price = 0
        for mineral_id, quantity in excess_minerals.items():
            excess_minerals_res[mineral_id] = {
                "quantity": quantity,
                "name": await SdeUtils.get_name_by_id(mineral_id),
                "name_zh": await SdeUtils.get_cn_name_by_id(mineral_id),
                "price": await MarketManager().get_jita_buy_price(mineral_id),
            }
            total_excess_price += quantity * await MarketManager().get_jita_buy_price(
                mineral_id
            )

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
            compressed_asteroid_utils, "_refinement_rate", refinement_rate
        )

        # 遍历购买的矿石
        for ore_id, quantity in asteroid_purchases.items():
            if quantity <= 0:
                continue

            # 获取该矿石产出的所有矿物
            type_material_dict = (
                getattr(compressed_asteroid_utils, "_type_material_data_dict", None)
                or {}
            )
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
                    contribution = quantity * (mineral_yield / 100) * refinement_rate
                yield_quantity = math.floor(contribution)
                quantity_needed = mineral_requirements.get(mineral_id, 0)
                mineral_yields[ore_id][mineral_id] = [yield_quantity, quantity_needed]

        logger.info(f"优化结果状态: {result.get('status')}")

        # 价格趋势：求解涉及的矿石与矿物一起下发，前端无需二次请求
        try:
            trend_ids: list[int] = []
            for ore_id in purcheses_res.keys():
                try:
                    trend_ids.append(int(ore_id))
                except Exception:
                    pass
            trend_ids += [int(m) for m in set(list(excess_minerals_res.keys()) + list(shortage_minerals_res.keys()) + list(mineral_purchases_res.keys())) if str(m).isdigit()]
            trend_ids = list(dict.fromkeys(trend_ids))
            price_trends, trend_meta = await build_price_trends(
                trend_ids, REGION_FORGE_ID, 30
            )
            logger.info(
                f"求解价格趋势: 请求={len(trend_ids)} 命中={len(price_trends)} 缺失={len(trend_meta.get('missing', []))}"
            )
        except Exception:
            logger.error(f"求解价格趋势失败: {traceback.format_exc()}")
            price_trends, trend_meta = {}, {"missing": [], "collecting": 0, "as_of": ""}

        data = {
            "price_trends": price_trends,
            "price_trends_meta": trend_meta,
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
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取压缩矿数据失败: {traceback.format_exc()}")
        return response_helper.server_error("获取压缩矿数据失败")


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
                descendant_roles = await permission_manager.get_all_descendant_roles(
                    role
                )
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
        container_permissions = await _get_user_all_container_permission_impl(
            user_id
        )

        # 2. 获取当前用户的配置流配置列表，筛选出 LoadAssetConf 类型
        all_configs = await _get_config_flow_config_list_impl(user_id)
        load_asset_configs = [
            config for config in all_configs if config["config_type"] == "LoadAssetConf"
        ]

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
                    "config_value": permission,  # 使用访问许可的完整数据结构
                }
                await _create_config_flow_config_impl(user_id, config_data)
                created_count += 1
                logger.info(
                    f"创建 LoadAssetConf 配置: container_id={permission.get('asset_container_id')}, owner_id={permission.get('asset_owner_id')}"
                )

        # 5. 找出需要更新 tag 的配置（匹配但 tag 不一致）
        updated_count = 0
        for key, permission in permission_key_map.items():
            if key in config_key_map:
                config = config_key_map[key]
                config_value = config.get("config_value", {})
                permission_tag = permission.get("tag")
                config_tag = config_value.get("tag") or config_value.get(
                    "container_tag"
                )

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
                        "config_value": updated_config_value,
                    }
                    await modify_config_flow(
                        user_id, modify_data, is_admin=is_admin
                    )
                    updated_count += 1
                    logger.info(
                        f"更新 LoadAssetConf 配置 tag: container_id={permission.get('asset_container_id')}, owner_id={permission.get('asset_owner_id')}, old_tag={config_tag}, new_tag={permission_tag}"
                    )

        # 6. 找出需要删除的配置（配置有但访问许可没有）
        deleted_count = 0
        for key, config in config_key_map.items():
            if key not in permission_key_map:
                # 删除该配置
                delete_data = {"config_id": config["config_id"]}
                await _delete_config_flow_config_impl(user_id, delete_data)
                deleted_count += 1
                config_value = config.get("config_value", {})
                logger.info(
                    f"删除 LoadAssetConf 配置: container_id={config_value.get('asset_container_id')}, owner_id={config_value.get('asset_owner_id')}, config_id={config['config_id']}"
                )

        message = f"同步完成：创建 {created_count} 个配置，更新 {updated_count} 个配置，删除 {deleted_count} 个配置"
        return jsonify(
            {
                "message": message,
                "data": {
                    "created": created_count,
                    "updated": updated_count,
                    "deleted": deleted_count,
                },
                "status": 200,
            }
        )
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"同步许可到计划配置失败: {traceback.format_exc()}")
        return response_helper.server_error("同步许可到计划配置失败")


# ============ 工作流实施标记功能 ============


@api_industry_bp.route("/plan/<plan_name>/workflow/implementations", methods=["GET"])
@auth_required
async def get_workflow_implementations(plan_name: str):
    """
    获取工作流实施标记状态

    获取指定计划和计算周期的实施标记状态。

    Tags:
        - EVE工业管理 - 工作流实施标记

    Security:
        - Bearer: []

    Parameters:
        - plan_name (path): 计划名称
        - calculation_id (query): 计算周期ID

    Responses:
        200: 成功返回实施状态列表
            - status: 状态码 (200)
            - data: 实施状态数据
                - calculation_id: 计算周期ID
                - items: 实施标记项列表
                - last_modified: 最后修改时间
        404: 计划不存在
        500: 服务器错误
    """
    current_user_id = g.current_user["user_id"]
    calculation_id = request.args.get("calculation_id", type=int)

    if not calculation_id:
        return response_helper.bad_request("缺少 calculation_id 参数")

    try:
        # 查询该计划的所有实施标记（封装模块内实现）
        implementations = await EveIndustryPlanTaskImplementationDBUtils.select_by_user_plan_calculation(
            current_user_id, plan_name, calculation_id
        )

        items = []
        last_modified = None

        for impl in implementations:
            items.append(
                {
                    "workflow_item_key": impl.workflow_item_key,
                    "implemented": impl.implemented,
                    "runs_implemented": impl.runs_implemented,
                    "modified_at": impl.modified_at.isoformat() + "Z"
                    if impl.modified_at
                    else None,
                }
            )
            if impl.modified_at:
                if last_modified is None or impl.modified_at > last_modified:
                    last_modified = impl.modified_at

        return jsonify(
            {
                "status": 200,
                "data": {
                    "calculation_id": calculation_id,
                    "items": items,
                    "last_modified": last_modified.isoformat()
                    if last_modified
                    else None,
                },
            }
        )

    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取工作流实施标记失败: {traceback.format_exc()}")
        return response_helper.server_error("获取工作流实施标记失败")


@api_industry_bp.route(
    "/plan/<plan_name>/workflow/implementations/sync", methods=["POST"]
)
@auth_required
async def sync_workflow_implementations(plan_name: str):
    """
    同步工作流实施标记

    批量同步客户端的实施标记到服务器，处理冲突。

    Tags:
        - EVE工业管理 - 工作流实施标记

    Security:
        - Bearer: []

    Parameters:
        - plan_name (path): 计划名称

    Request Body:
        - calculation_id (integer, required): 计算周期ID
        - items (array, required): 实施标记项列表
            - workflow_item_key (string): 工作流项唯一标识
            - implemented (boolean): 是否已实施
            - runs_implemented (integer): 已实施的运行次数（可选）
            - modified_at (string): 修改时间（ISO格式）
        - deleted_keys (array, optional): 待删除的项key列表

    Responses:
        200: 同步成功
            - status: 状态码 (200)
            - server_time: 服务器时间
            - conflicts: 冲突列表（如果有）
            - server_only_items: 服务器独有的项（需要合并到本地）
        500: 服务器错误
    """
    current_user_id = g.current_user["user_id"]
    data = await request.json

    calculation_id = data.get("calculation_id")
    client_items = data.get("items", [])
    deleted_keys = data.get("deleted_keys", [])

    if not calculation_id:
        return response_helper.bad_request("缺少 calculation_id 参数")

    try:
        # 事务性同步实施标记（封装模块内完成查询/新增/更新/删除/冲突检测，单会话原子提交）
        conflicts, server_only_items = await EveIndustryPlanTaskImplementationDBUtils.sync_implementations(
            current_user_id,
            plan_name,
            calculation_id,
            client_items,
            deleted_keys,
            parse_naive_utc_datetime,
        )

        return jsonify(
            {
                "status": 200,
                "server_time": datetime.datetime.utcnow().isoformat(),
                "conflicts": conflicts,
                "server_only_items": server_only_items,
            }
        )

    except Exception as e:
        traceback.print_exc()
        logger.error(f"同步工作流实施标记失败: {traceback.format_exc()}")
        return response_helper.server_error("同步工作流实施标记失败")


@api_industry_bp.post("/getBpRequirementViewData")
@auth_required
async def get_bp_requirement_view_data():
    """获取蓝图需求视图数据。

    从 Redis 缓存的 work_flow 中筛选 bp_object.fake 条目，
    聚合展示缺失蓝图汇总、BPC 拷贝需求和 T2→T1 发明源。

    Request Body:
        - plan_name (string, required): 计划名称
        - user_name (string, optional): 管理员查看他人计划时指定

    Responses:
        200: 成功
            - status: 200
            - data.cache_hit: bool
            - data.missing_blueprint_sheet_count: int
            - data.missing_workflow_runs_count: int
            - data.missing_blueprint_workflow: array
        400: plan_name 为空
        403: 普通用户尝试查看他人计划
        500: 服务器错误
    """
    try:
        data = await request.get_json()
        plan_name = data.get("plan_name", "").strip()
        if not plan_name:
            return jsonify({"status": 400, "message": "plan_name 不能为空"}), 400

        # 身份一律取当前登录用户；请求体里的 user_name 只有管理员可用于代查他人计划
        # （安全审计 #18：Quart 的 request 没有 user_name 属性会直接抛 AttributeError，
        #   且不能让请求参数直接替换身份，否则任何登录用户都能读他人的缓存结果）
        current_user_name = g.current_user["user_id"]

        target_user_name = data.get("user_name")
        user_name = current_user_name
        if target_user_name and target_user_name != current_user_name:
            if not await is_admin_user(current_user_name):
                logger.warning(
                    f"用户 {current_user_name} 尝试查看用户 {target_user_name} 的蓝图需求视图 {plan_name}，已拒绝"
                )
                return response_helper.forbidden("无权查看他人的工业计划")
            user_name = target_user_name
            logger.info(
                f"管理员 {current_user_name} 代查用户 {user_name} 的蓝图需求视图: {plan_name}"
            )

        status_key = f"plan_calculate_status:{user_name}:{plan_name}"
        result_key = f"plan_calculate_result:{user_name}:{plan_name}"

        status_value = await rdm().r.get(status_key)
        if isinstance(status_value, bytes):
            status_value = status_value.decode("utf-8", errors="ignore")

        if status_value != "completed":
            return jsonify(
                {
                    "status": 200,
                    "data": [],
                    "cache_hit": False,
                    "message": "计划计算缓存不存在或未完成",
                }
            )

        result_data_str = await rdm().r.get(result_key)
        if not result_data_str:
            return jsonify(
                {
                    "status": 200,
                    "data": [],
                    "cache_hit": False,
                    "message": "计划计算缓存不存在或未完成",
                }
            )

        import json

        result_data = (
            json.loads(result_data_str)
            if isinstance(result_data_str, str)
            else result_data_str
        )

        work_flow = (
            result_data.get("work_flow", [])
            if isinstance(result_data, dict)
            else []
        )
        if not isinstance(work_flow, list):
            work_flow = []

        missing_blueprint_workflow = await analyze_blueprint_requirements(work_flow)

        missing_sheet_count = len(missing_blueprint_workflow)
        missing_runs_count = sum(
            node.get("runs_total", 0) for node in missing_blueprint_workflow
        )

        return jsonify(
            {
                "status": 200,
                "data": {
                    "user_name": user_name,
                    "plan_name": plan_name,
                    "cache_hit": True,
                    "missing_blueprint_sheet_count": missing_sheet_count,
                    "missing_workflow_runs_count": missing_runs_count,
                    "missing_blueprint_workflow": missing_blueprint_workflow,
                },
            }
        )
    except Exception:
        import traceback

        logger.error(f"获取蓝图需求视图数据失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取蓝图需求视图数据失败"})
