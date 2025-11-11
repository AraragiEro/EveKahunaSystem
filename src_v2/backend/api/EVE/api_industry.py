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
        await IndustryManager.calculate_plan(user_id, data["plan_name"])
        data = await IndustryManager.get_plan_tableview_data(data["plan_name"], user_id)
        return jsonify({"status": 200, "data": data})
    except KahunaException as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"获取计划计算结果表格视图失败: {traceback.format_exc()}")
        return jsonify({"error": "获取计划计算结果表格视图失败"}), 500