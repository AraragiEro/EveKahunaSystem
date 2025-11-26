import datetime, jwt
import re
import traceback
import asyncio
import json

from quart import Quart, request, jsonify, g, Blueprint, redirect
from quart import current_app as app
from src_v2.backend.auth import auth_required, verify_token
from src_v2.backend.api.permission_required import role_required
from src_v2.core.database.connect_manager import redis_manager
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy.exc import IntegrityError

from src_v2.core.user.user_manager import UserManager
from src_v2.core.log import logger

from src_v2.model.EVE.industry.industry_manager import IndustryManager
from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU
from src_v2.core.utils import KahunaException
from src_v2.model.EVE.industry.plan_configflow_operate import ConfigFlowOperateCenter
from src_v2.model.EVE.sde.utils import SdeUtils

api_industry_bp = Blueprint('api_industry', __name__, url_prefix='/api/EVE/industry')

@api_industry_bp.route("/getMarketTree", methods=["POST"])
@auth_required
async def get_market_tree():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        market_tree = await IndustryManager.get_market_tree(data["node"])
        logger.info(f"获取 市场节点 {data['node']} 的子节点 {len(market_tree)} 个")
        return jsonify({"data": market_tree, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取市场树失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取市场树失败"}), 500

@api_industry_bp.route("/createPlan", methods=["POST"])
@auth_required
async def create_plan():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        plan_name = data["name"]
        data.pop("name")
        await IndustryManager().create_plan(user_id, plan_name, data)
        return jsonify({"message": "计划创建成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"创建计划失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建计划失败"}), 500

@api_industry_bp.route("/getPlanTableData", methods=["POST"])
@auth_required
async def get_plan_table_data():
    data = await request.json
    user_id = g.current_user["user_id"]
    logger.info(f"获取计划表格数据: {user_id}")

    try:
        plan_table_data = await IndustryManager.get_plan(user_id)
        logger.info(f"获取计划表格数据: {plan_table_data} ")
        return jsonify({"data": plan_table_data, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取计划表格数据失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取计划表格数据失败"}), 500

@api_industry_bp.route("/addPlanProduct", methods=["POST"])
@auth_required
async def add_plan_product():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.add_plan_product(user_id, data["plan_name"], data["type_id"], data["quantity"])
        return jsonify({"message": "产品添加成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"添加产品失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加产品失败"}), 500

@api_industry_bp.route("/savePlanProducts", methods=["POST"])
@auth_required
async def save_plan_products():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.save_plan_products(user_id, data["plan_name"], data["products"])
        return jsonify({"message": "产品保存成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"保存产品失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存产品失败"}), 500

async def _calculate_plan_async(user_id: str, plan_name: str):
    """异步计算计划的后台任务"""
    status_key = f"plan_calculate_status:{user_id}:{plan_name}"
    total_progress_key = f"plan_calculate_total_progress:{user_id}:{plan_name}"
    current_progress_key = f"plan_calculate_current_progress:{user_id}:{plan_name}"
    result_key = f"plan_calculate_result:{user_id}:{plan_name}"
    
    try:
        # 设置状态为运行中
        await redis_manager.redis.set(status_key, "running")
        await redis_manager.redis.expire(status_key, 3600)  # 1小时过期
        
        # 执行计算
        op = await ConfigFlowOperateCenter.create(user_id, plan_name)
        op.total_progress_key = total_progress_key
        op.current_progress_key = current_progress_key
        result_data = await IndustryManager.calculate_plan(op)
        
        
        # 计算完成，设置状态为已完成
        await redis_manager.redis.set(result_key, json.dumps(result_data))
        await redis_manager.redis.expire(result_key, 3600)
        await redis_manager.redis.set(status_key, "completed")
        await redis_manager.redis.expire(status_key, 3600)
        
        
        logger.info(f"计划 {plan_name} 计算完成")
    except KahunaException as e:
        # 计算失败，设置状态为失败
        traceback.print_exc()
        error_msg = str(e)
        await redis_manager.redis.set(status_key, f"failed:{error_msg}")
        await redis_manager.redis.expire(status_key, 3600)
        logger.error(f"计划 {plan_name} 计算失败: {error_msg}")
    except Exception as e:
        # 计算失败，设置状态为失败
        traceback.print_exc()
        error_msg = f"计算过程发生错误: {str(e)}"
        await redis_manager.redis.set(status_key, f"failed:{error_msg}")
        await redis_manager.redis.expire(status_key, 3600)
        logger.error(f"计划 {plan_name} 计算失败: {traceback.format_exc()}")

@api_industry_bp.route("/getPlanCalculateResultTableView", methods=["POST"])
@auth_required
async def get_plan_calculate_result_table_view():
    data = await request.json
    user_id = g.current_user["user_id"]
    plan_name = data.get("plan_name")
    operate_type = data.get("operate_type", "calculate")  # 默认为 "calculate" 以保持向后兼容
    
    status_key = f"plan_calculate_status:{user_id}:{plan_name}"
    total_progress_key = f"plan_calculate_total_progress:{user_id}:{plan_name}"
    current_progress_key = f"plan_calculate_current_progress:{user_id}:{plan_name}"
    result_key = f"plan_calculate_result:{user_id}:{plan_name}"
    
    try:
        if operate_type == "start":
            # 启动计算任务
            # 检查是否已有正在进行的计算
            current_status = await redis_manager.redis.get(status_key)
            if current_status:
                if current_status == "pending" or current_status == "running":
                    return jsonify({"status": 400, "message": "计算任务已在运行中"}), 400
                elif current_status.startswith("failed:"):
                    # 如果之前失败，允许重新启动
                    pass
                elif current_status == "completed":
                    # 如果已完成，允许重新计算
                    pass
            
            # 设置状态为待处理
            await redis_manager.redis.set(status_key, "pending")
            await redis_manager.redis.expire(status_key, 3600)
            
            # 启动异步计算任务
            asyncio.create_task(_calculate_plan_async(user_id, plan_name))
            
            return jsonify({"status": 200, "message": "计算任务已启动"})
            
        elif operate_type == "status":
            # 查询计算状态
            status = await redis_manager.redis.get(status_key)
            total_progress = await redis_manager.redis.get(total_progress_key)
            # current_progress 是使用 hset 存储的 hash，使用 hgetall 获取所有字段
            current_progress_hash = await redis_manager.redis.hgetall(current_progress_key)  # type: ignore
            
            if not status:
                return jsonify({"status": 200, "data": {"status": "idle", "total_progress": None, "current_step": None, "is_indeterminate": 1}})
            
            # 解析状态
            if status.startswith("failed:"):
                error_msg = status[7:]  # 去掉 "failed:" 前缀
                return jsonify({"status": 200, "data": {"status": "failed", "error": error_msg, "total_progress": None, "current_step": None, "is_indeterminate": 1}})
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
                
                return jsonify({
                    "status": 200, 
                    "data": {
                        "status": status, 
                        "total_progress": total_progress_value,
                        "current_step": current_step_data,
                        "is_indeterminate": current_progress_hash.get("is_indeterminate", "0") == "1"
                    }
                })
                
        elif operate_type == "result":
            # 获取计算结果
            # 检查状态是否为已完成
            status = await redis_manager.redis.get(status_key)
            if not status or status != "completed":
                return jsonify({"status": 400, "message": "计算尚未完成"}), 400
            
            # 从Redis获取计算结果
            result_data_str = await redis_manager.redis.get(result_key)
            if result_data_str:
                try:
                    result_data = json.loads(result_data_str)
                except (json.JSONDecodeError, TypeError):
                    # 如果Redis中没有结果，回退到从数据库获取
                    op = await ConfigFlowOperateCenter.create(user_id, plan_name)
                    result_data = await IndustryManager.get_plan_tableview_data(op)
            else:
                # 如果Redis中没有结果，从数据库获取
                op = await ConfigFlowOperateCenter.create(user_id, plan_name)
                result_data = await IndustryManager.get_plan_tableview_data(op)
            
            return jsonify({"status": 200, "data": result_data})
            
        else:
            # 向后兼容：直接计算并返回结果（原有行为）
            op = await ConfigFlowOperateCenter.create(user_id, plan_name)
            await IndustryManager.calculate_plan(op)
            data = await IndustryManager.get_plan_tableview_data(op)
            return jsonify({"status": 200, "data": data})
            
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取计划计算结果表格视图失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取计划计算结果表格视图失败"}), 500

@api_industry_bp.route("/addIndustrypermision", methods=["POST"])
@auth_required
async def add_industrypermision():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.add_industrypermision(user_id,data)
        return jsonify({"message": "新增许可成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"新增许可失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "新增许可失败"}), 500

@api_industry_bp.route("/getUserAllContainerPermission", methods=["POST"])
@auth_required
async def get_user_all_container_permission():
    user_id = g.current_user["user_id"]
    data = await request.json
    force_refresh = data.get("force_refresh", False)
    if force_refresh:
        await redis_manager.redis.delete(f'container_permission:{user_id}:all_container_permission')

    try:
        all_container_permission = await IndustryManager.get_user_all_container_permission(user_id)
        return jsonify({"data": all_container_permission, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取用户所有容器许可失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取用户所有容器许可失败"}), 500

@api_industry_bp.route("/deleteIndustrypermision", methods=["POST"])
@auth_required
async def delete_industrypermision():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.delete_industrypermision(user_id, data)
        return jsonify({"message": "删除许可成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"删除许可失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除许可失败"}), 500

@api_industry_bp.route("/getStructureList", methods=["GET"])
@auth_required
@role_required(["vip_alpha"], 402, "仅ALPHA订阅者可拉取真实资产建筑。虚拟建筑可正常使用。")
async def get_structure_list():
    user_id = g.current_user["user_id"]
    try:
        structure_list = await IndustryManager.get_structure_list(user_id)
        return jsonify({"data": structure_list, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取建筑列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取建筑列表失败"}), 500
        
@api_industry_bp.route("/getGroupSuggestions", methods=["POST"])
@auth_required
async def get_structure_assign_keyword_suggestions():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        assign_keyword_suggestions = await IndustryManager.get_structure_assign_keyword_suggestions(data["assign_type"], data["query"])
        return jsonify({"data": assign_keyword_suggestions, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取建筑分配关键字建议失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取建筑分配关键字建议失败"}), 500

@api_industry_bp.route("/getTypeList", methods=["GET"])
@auth_required
async def get_type_list():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        type_list = await IndustryManager.get_type_list()
        return jsonify({"data": type_list, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取类型列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取类型列表失败"}), 500

@api_industry_bp.route("/getTypeSuggestionsList", methods=["POST"])
@auth_required
async def get_type_suggestions_list():
    data = await request.json
    
    try:
        type_suggestions_list = await SdeUtils.fuzz_type(data["type_name"], list_len=10)
        type_suggestions_list = [{"value": item, "label": item} for item in type_suggestions_list]
        return jsonify({"data": type_suggestions_list, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取类型建议列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取类型建议列表失败"}), 500

@api_industry_bp.route("/createConfigFlowConfig", methods=["POST"])
@auth_required
async def create_config_flow_config():
    data = await request.json
    user_id = g.current_user["user_id"]
    
    logger.info(f"创建配置流配置: {data}")
    try:
        await IndustryManager.create_config_flow_config(user_id, data)
        return jsonify({"message": "创建配置流配置成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except IntegrityError as e:
        logger.error(f"创建配置流配置失败 - 数据库完整性错误: {traceback.format_exc()}")
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        if "duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower():
            return jsonify({"status": 500, "message": "创建配置流配置失败：ID冲突，请稍后重试"}), 500
        return jsonify({"status": 500, "message": f"创建配置流配置失败：{error_msg}"}), 500
    except Exception as e:
        logger.error(f"创建配置流配置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建配置流配置失败"}), 500

@api_industry_bp.route("/modifyConfigFlowConfig", methods=["POST"])
@auth_required
async def modify_config_flow_config():
    data = await request.json
    user_id = g.current_user["user_id"]
    
    logger.info(f"修改配置流配置: {data}")
    try:
        await IndustryManager.modify_config_flow_config(user_id, data)
        return jsonify({"message": "修改配置流配置成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"修改配置流配置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "修改配置流配置失败"}), 500

@api_industry_bp.route("/fetchRecommendedPresets", methods=["GET"])
@auth_required
async def fetch_recommended_presets():
    data = await request.json
    user_id = g.current_user["user_id"]
    preset_name = "default_bp_and_material"

    try:
        recommended_presets = await IndustryManager.fetch_recommended_presets(user_id, preset_name)
        return jsonify({"data": recommended_presets, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"拉取推荐预设失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "拉取推荐预设失败"}), 500

@api_industry_bp.route("/deleteConfigFlowConfig", methods=["POST"])
@auth_required
async def delete_config_flow_config():
    data = await request.json
    user_id = g.current_user["user_id"]
    
    try:
        await IndustryManager.delete_config_flow_config(user_id, data)
        return jsonify({"message": "删除配置流配置成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"删除配置流配置失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除配置流配置失败"}), 500

@api_industry_bp.route("/getConfigFlowConfigList", methods=["GET"])
@auth_required
async def get_config_flow_config_list():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        config_flow_config_list = await IndustryManager.get_config_flow_config_list(user_id)
        config_flow_config_list.sort(key=lambda x: x["config_type"])
        return jsonify({"data": config_flow_config_list, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取配置流配置列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取配置流配置列表失败"}), 500

# 添加配置到计划
@api_industry_bp.route("/addConfigToPlan", methods=["POST"])
@auth_required
async def add_config_to_plan():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.add_config_to_plan(user_id, data)
        return jsonify({"message": "添加配置到计划成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"添加配置到计划失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "添加配置到计划失败"}), 500

# 获取计划配置流列表
@api_industry_bp.route("/getConfigFlowList", methods=["POST"])
@auth_required
async def get_config_flow_list():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        config_flow_list = await IndustryManager.get_config_flow_list(user_id, data["plan_name"])
        return jsonify({"data": config_flow_list, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取配置流列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取配置流列表失败"}), 500

# 保存计划配置流
@api_industry_bp.route("/saveConfigFlowToPlan", methods=["POST"])
@auth_required
async def save_config_flow_to_plan():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.save_config_flow_to_plan(user_id, data["plan_name"], data)
        return jsonify({"message": "保存配置流成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"保存配置流失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存配置流失败"}), 500

# 保存配置流预设
@api_industry_bp.route("/saveConfigFlowPreset", methods=["POST"])
@auth_required
async def save_config_flow_preset():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        preset_name = data["preset_name"]
        config_list = data["config_list"]
        await IndustryManager.save_config_flow_preset(user_id, preset_name, config_list)
        return jsonify({"message": "保存预设成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"保存预设失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "保存预设失败"}), 500

# 获取用户所有预设
@api_industry_bp.route("/getConfigFlowPresets", methods=["GET"])
@auth_required
async def get_config_flow_presets():
    user_id = g.current_user["user_id"]

    try:
        presets = await IndustryManager.get_config_flow_presets(user_id)
        return jsonify({"data": presets, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取预设列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取预设列表失败"}), 500

# 加载预设到计划
@api_industry_bp.route("/loadConfigFlowPreset", methods=["POST"])
@auth_required
async def load_config_flow_preset():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        preset_id = data["preset_id"]
        plan_name = data["plan_name"]
        await IndustryManager.load_config_flow_preset(user_id, preset_id, plan_name)
        return jsonify({"message": "加载预设成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"加载预设失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "加载预设失败"}), 500

# # 获取计划设置
@api_industry_bp.route("/modifyPlanSettings", methods=["POST"])
@auth_required
async def modify_plan_settings():
    data = await request.json
    user_id = g.current_user["user_id"]

    try:
        await IndustryManager.modify_plan_settings(user_id, data["plan_name"], data["plan_settings"])
        return jsonify({"message": "修改计划设置成功", "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"删除计划失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "删除计划失败"}), 500

@api_industry_bp.route("/getItemInfo", methods=["POST"])
@auth_required
async def get_item_info():
    data = await request.json

    try:
        item_info = await IndustryManager.get_item_info(data["type_id"])
        return jsonify({"data": item_info, "status": 200})
    except KahunaException as e:
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception as e:
        logger.error(f"获取物品信息失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取物品信息失败"}), 500

@api_industry_bp.route("/getLaborForceData", methods=["POST"])
@auth_required
async def get_labor_force_data():
    user_id = g.current_user["user_id"]

    try:
        return jsonify({"data": "获取劳动力数据成功", "status": 200}), 200
    except KahunaException as e:
        return jsonify({"message": str(e), "status": 500}), 500
    except Exception as e:
        logger.error(f"获取劳动力数据失败: {traceback.format_exc()}")
        return jsonify({"message": "获取劳动力数据失败", "status": 500}), 500