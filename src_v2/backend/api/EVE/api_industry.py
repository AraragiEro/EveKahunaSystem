import datetime, jwt
import traceback

from quart import Quart, request, jsonify, g, Blueprint, redirect
from quart import current_app as app
from src_v2.backend.auth import auth_required, verify_token
from src_v2.core.database.connect_manager import redis_manager
from werkzeug.security import check_password_hash, generate_password_hash

from src_v2.core.user.user_manager import UserManager
from src.service.log_server import logger

from src_v2.model.EVE.industry.industry_manager import IndustryManager
from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU
from src_v2.core.utils import KahunaException
from src_v2.model.EVE.industry.plan_configflow_operate import ConfigFlowOperateCenter

api_industry_bp = Blueprint('api_industry', __name__, url_prefix='/api/EVE/industry')

@api_industry_bp.route("/getMarketTree", methods=["POST"])
@auth_required
async def get_market_tree():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        market_tree = await IndustryManager.get_market_tree(data["node"])
        logger.info(f"获取 市场节点 {data['node']} 的子节点 {len(market_tree)} 个")
        return jsonify({"data": market_tree})
    except:
        logger.error(f"获取市场树失败: {traceback.format_exc()}")
        return jsonify({"error": "获取市场树失败"}), 500

@api_industry_bp.route("/createPlan", methods=["POST"])
@auth_required
async def create_plan():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        plan_name = data["name"]
        data.pop("name")
        await IndustryManager().create_plan(user_id, plan_name, data)
        return jsonify({"data": "计划创建成功"})
    except:
        logger.error(f"创建计划失败: {traceback.format_exc()}")
        return jsonify({"error": "创建计划失败"}), 500

@api_industry_bp.route("/getPlanTableData", methods=["POST"])
@auth_required
async def get_plan_table_data():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        plan_table_data = await IndustryManager.get_plan(user_id)
        return jsonify({"data": plan_table_data})
    except:
        logger.error(f"获取计划表格数据失败: {traceback.format_exc()}")
        return jsonify({"error": "获取计划表格数据失败"}), 500

@api_industry_bp.route("/addPlanProduct", methods=["POST"])
@auth_required
async def add_plan_product():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.add_plan_product(user_id, data["plan_name"], data["type_id"], data["quantity"])
        return jsonify({"data": "产品添加成功"})
    except:
        logger.error(f"添加产品失败: {traceback.format_exc()}")
        return jsonify({"error": "添加产品失败"}), 500

@api_industry_bp.route("/savePlanProducts", methods=["POST"])
@auth_required
async def save_plan_products():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.save_plan_products(user_id, data["plan_name"], data["products"])
        return jsonify({"data": "产品保存成功"})
    except:
        logger.error(f"保存产品失败: {traceback.format_exc()}")
        return jsonify({"error": "保存产品失败"}), 500

@api_industry_bp.route("/getPlanCalculateResultTableView", methods=["POST"])
@auth_required
async def get_plan_calculate_result_table_view():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        op = await ConfigFlowOperateCenter.create(user_id, data["plan_name"])
        await IndustryManager.calculate_plan(op)
        data = await IndustryManager.get_plan_tableview_data(op)
        return jsonify({"status": 200, "data": data})
    except KahunaException as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"获取计划计算结果表格视图失败: {traceback.format_exc()}")
        return jsonify({"message": "获取计划计算结果表格视图失败"}), 500

@api_industry_bp.route("/addIndustrypermision", methods=["POST"])
@auth_required
async def add_industrypermision():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.add_industrypermision(user_id,data)
        return jsonify({"message": "新增许可成功", "status": 200})
    except:
        logger.error(f"新增许可失败: {traceback.format_exc()}")
        return jsonify({"message": "新增许可失败", "status": 500}), 500

@api_industry_bp.route("/getUserAllContainerPermission", methods=["GET"])
@auth_required
async def get_user_all_container_permission():
    user_id = g.current_user["user_id"]

    try:
        all_container_permission = await IndustryManager.get_user_all_container_permission(user_id)
        return jsonify({"data": all_container_permission, "status": 200})
    except:
        logger.error(f"获取用户所有容器许可失败: {traceback.format_exc()}")
        return jsonify({"message": "获取用户所有容器许可失败", "status": 500}), 500

@api_industry_bp.route("/deleteIndustrypermision", methods=["POST"])
@auth_required
async def delete_industrypermision():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.delete_industrypermision(user_id, data)
        return jsonify({"message": "删除许可成功", "status": 200})
    except:
        logger.error(f"删除许可失败: {traceback.format_exc()}")
        return jsonify({"message": "删除许可失败", "status": 500}), 500

@api_industry_bp.route("/getStructureList", methods=["GET"])
@auth_required
async def get_structure_list():
    try:
        structure_list = await IndustryManager.get_structure_list()
        return jsonify({"data": structure_list, "status": 200})
    except:
        logger.error(f"获取建筑列表失败: {traceback.format_exc()}")
        return jsonify({"message": "获取建筑列表失败", "status": 500}), 500
        
@api_industry_bp.route("/getGroupSuggestions", methods=["POST"])
@auth_required
async def get_structure_assign_keyword_suggestions():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        assign_keyword_suggestions = await IndustryManager.get_structure_assign_keyword_suggestions(data["assign_type"])
        return jsonify({"data": assign_keyword_suggestions, "status": 200})
    except:
        logger.error(f"获取建筑分配关键字建议失败: {traceback.format_exc()}")
        return jsonify({"message": "获取建筑分配关键字建议失败", "status": 500}), 500

@api_industry_bp.route("/getTypeList", methods=["GET"])
@auth_required
async def get_type_list():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        type_list = await IndustryManager.get_type_list()
        return jsonify({"data": type_list, "status": 200})
    except:
        logger.error(f"获取类型列表失败: {traceback.format_exc()}")
        return jsonify({"error": "获取类型列表失败", "status": 500}), 500

@api_industry_bp.route("/createConfigFlowConfig", methods=["POST"])
@auth_required
async def create_config_flow_config():
    data = await request.json
    user_id = g.current_user["user_id"]
    
    logger.info(f"创建配置流配置: {data}")
    try:
        await IndustryManager.create_config_flow_config(user_id, data)
        return jsonify({"message": "创建配置流配置成功", "status": 200})
    except:
        logger.error(f"创建配置流配置失败: {traceback.format_exc()}")
        return jsonify({"message": "创建配置流配置失败", "status": 500}), 500

@api_industry_bp.route("/getConfigFlowConfigList", methods=["GET"])
@auth_required
async def get_config_flow_config_list():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        config_flow_config_list = await IndustryManager.get_config_flow_config_list(user_id)
        return jsonify({"data": config_flow_config_list, "status": 200})
    except:
        logger.error(f"获取配置流配置列表失败: {traceback.format_exc()}")
        return jsonify({"message": "获取配置流配置列表失败", "status": 500}), 500

# 添加配置到计划
@api_industry_bp.route("/addConfigToPlan", methods=["POST"])
@auth_required
async def add_config_to_plan():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.add_config_to_plan(user_id, data)
        return jsonify({"message": "添加配置到计划成功", "status": 200})
    except:
        logger.error(f"添加配置到计划失败: {traceback.format_exc()}")
        return jsonify({"message": "添加配置到计划失败", "status": 500}), 500

# 获取计划配置流列表
@api_industry_bp.route("/getConfigFlowList", methods=["POST"])
@auth_required
async def get_config_flow_list():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        config_flow_list = await IndustryManager.get_config_flow_list(user_id, data["plan_name"])
        return jsonify({"data": config_flow_list, "status": 200})
    except:
        logger.error(f"获取配置流列表失败: {traceback.format_exc()}")
        return jsonify({"message": "获取配置流列表失败", "status": 500}), 500

# 保存计划配置流
@api_industry_bp.route("/saveConfigFlowToPlan", methods=["POST"])
@auth_required
async def save_config_flow_to_plan():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.save_config_flow_to_plan(user_id, data["plan_name"], data)
        return jsonify({"message": "保存配置流成功", "status": 200})
    except:
        logger.error(f"保存配置流失败: {traceback.format_exc()}")
        return jsonify({"message": "保存配置流失败", "status": 500}), 500

# # 获取计划设置
@api_industry_bp.route("/modifyPlanSettings", methods=["POST"])
@auth_required
async def modify_plan_settings():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.modify_plan_settings(user_id, data["plan_name"], data["plan_settings"])
        return jsonify({"message": "修改计划设置成功", "status": 200})
    except:
        logger.error(f"修改计划设置失败: {traceback.format_exc()}")
        return jsonify({"message": "修改计划设置失败", "status": 500}), 500

@api_industry_bp.route("/getItemInfo", methods=["POST"])
@auth_required
async def get_item_info():
    data = await request.json

    try:
        item_info = await IndustryManager.get_item_info(data["type_id"])
        return jsonify({"data": item_info, "status": 200})
    except:
        logger.error(f"获取物品信息失败: {traceback.format_exc()}")
        return jsonify({"message": "获取物品信息失败", "status": 500}), 500