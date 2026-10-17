import secrets
import traceback
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any, Dict, List

from quart import Blueprint, jsonify, request, g
from sqlalchemy.exc import IntegrityError

from src_v2.model.EVE.asset.asset_manager import AssetManager
from src_v2.model.EVE.market.market_manager import MarketManager
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveIndustryPlanDBUtils,
    EveIndustryPlanTaskClaimDBUtils,
    UserDBUtils,
    EveAuthedCharacterDBUtils,
    EveCorporationDBUtils,
)
from src_v2.core.user.user_manager import UserManager
from src_v2.backend.auth import auth_required
from src_v2.backend.api import response_helper

api_public_bp = Blueprint("api_public", __name__, url_prefix="/api/public")


# 响应数据模型
@dataclass
class PublicStorageDataResponse:
    """公开资产视图数据响应"""

    status: int
    data: Optional[Dict[str, Any]] = None
    tag: Optional[str] = None
    view_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


@dataclass
class ErrorResponse:
    """错误响应"""

    status: int
    message: str


@api_public_bp.route("/storage/<sid>", methods=["GET"])
# @validate_response(PublicStorageDataResponse)
async def get_public_storage_data(sid: str):
    """
    获取公开的资产视图数据

    根据资产视图SID获取公开的资产视图数据。如果资产视图未公开，将返回403错误。
    对于sell类型的视图，会自动填充价格数据。

    Tags:
        - 公开接口

    Parameters:
        - sid (path, string, required): 资产视图SID

    Responses:
        200: 成功返回资产视图数据
            - status: 状态码 (200)
            - data: 资产视图数据 (object, optional)
            - tag: 资产视图标签 (string, optional)
            - view_type: 视图类型 (string, optional)
            - config: 视图配置 (object, optional)
        403: 资产视图未公开
            - status: 状态码 (403)
            - message: 错误信息 (string)
        404: 资产视图不存在
            - status: 状态码 (404)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {...},
            "tag": "标签",
            "view_type": "sell",
            "config": {...}
        }
    """
    try:
        asset_manager = AssetManager()

        # 获取资产视图对象以获取 view_type 和 config
        asset_view_obj = await asset_manager.get_asset_view_by_sid(sid)
        if not asset_view_obj:
            return response_helper.not_found("资产视图不存在")

        if not asset_view_obj.public:
            return response_helper.forbidden("该资产视图未公开")

        # 获取资产视图数据
        output = await asset_manager.get_asset_view_data(sid)

        # 如果是 sell 视图，填充价格数据
        if asset_view_obj.view_type == "sell":
            await MarketManager().update_jita_price()
            output = await asset_manager.fill_sell_price_data(
                output, asset_view_obj.config
            )

        return jsonify(
            {
                "status": 200,
                "data": output,
                "tag": asset_view_obj.tag,
                "view_type": asset_view_obj.view_type,
                "config": asset_view_obj.config,
            }
        )
    except KahunaException as e:
        traceback.print_exc()
        # 根据错误消息判断返回的状态码
        error_message = str(e)
        if "不存在" in error_message:
            return jsonify({"status": 404, "message": error_message}), 404
        elif "未公开" in error_message:
            return jsonify({"status": 403, "message": error_message}), 403
        else:
            return jsonify({"status": 500, "message": error_message}), 500
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取公开资产视图数据失败: {traceback.format_exc()}")
        return response_helper.server_error("获取公开资产视图数据失败")


# ============ 工作流分享功能API ============


@api_public_bp.route("/workflow/share", methods=["POST"])
@auth_required
async def create_workflow_share():
    """
    创建工作流分享

    每个计划只有一个分享链接，创建新的分享会自动替换旧的。

    Request Body:
        - plan_name (str): 计划名称
        - filter_snapshot (dict): 过滤条件快照

    Returns:
        - status: 状态码
        - share_token: 分享令牌
        - share_url: 完整分享链接
        - message: 提示信息
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]
    plan_name = data.get("plan_name")
    filter_snapshot = data.get("filter_snapshot", {})

    if not plan_name:
        return response_helper.bad_request("缺少计划名称")

    try:
        # 获取计划（验证所有权）
        plan = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(
            current_user_id, plan_name
        )
        if not plan:
            return response_helper.not_found("计划不存在")

        # 生成新的分享令牌（格式：wf_ + 12位随机字符）
        share_token = f"wf_{secrets.token_urlsafe(12)}"

        # 更新计划分享信息（旧token自动被覆盖，链接失效）
        await EveIndustryPlanDBUtils.update_share_info(
            user_name=current_user_id,
            plan_name=plan_name,
            share_data={
                "public": True,  # 默认开启
                "share_token": share_token,
                "filter_snapshot": filter_snapshot,
            },
        )

        # 构建分享链接（前端路由）
        share_url = f"{request.host_url}workflow/{share_token}"

        return jsonify(
            {
                "status": 200,
                "share_token": share_token,
                "share_url": share_url,
                "message": "分享链接已创建（旧的分享链接已失效）",
            }
        )

    except Exception as e:
        logger.error(f"创建工作流分享失败: {e}")
        traceback.print_exc()
        return response_helper.server_error("创建分享失败")


@api_public_bp.route("/workflow/share/toggle", methods=["POST"])
@auth_required
async def toggle_workflow_share():
    """
    切换计划分享公开状态（开启/关闭）

    关闭后分享链接失效，开启后恢复访问（使用当前token）。

    Request Body:
        - plan_name (str): 计划名称

    Returns:
        - status: 状态码
        - public: 当前公开状态
        - message: 提示信息
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]
    plan_name = data.get("plan_name")

    if not plan_name:
        return response_helper.bad_request("缺少计划名称")

    try:
        # 获取计划
        plan = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(
            current_user_id, plan_name
        )
        if not plan:
            return response_helper.not_found("计划不存在")

        # 切换public状态
        new_public_status = not plan.public

        await EveIndustryPlanDBUtils.update_share_info(
            user_name=current_user_id,
            plan_name=plan_name,
            share_data={"public": new_public_status},
        )

        status_text = "开启" if new_public_status else "关闭"
        message = f"分享已{status_text}"
        if new_public_status and plan.share_token:
            share_url = f"{request.host_url}workflow/{plan.share_token}"
            message += f"，链接：{share_url}"

        return response_helper.ok(public=new_public_status, message=message)

    except Exception as e:
        logger.error(f"切换分享状态失败: {e}")
        traceback.print_exc()
        return response_helper.server_error("操作失败")


@api_public_bp.route("/workflow/share/status", methods=["GET"])
@auth_required
async def get_workflow_share_status():
    """
    获取计划分享状态

    Query Parameters:
        - plan_name (str): 计划名称

    Returns:
        - status: 状态码
        - data: 分享状态信息
    """
    plan_name = request.args.get("plan_name")
    current_user_id = g.current_user["user_id"]

    if not plan_name:
        return response_helper.bad_request("缺少计划名称")

    try:
        plan = await EveIndustryPlanDBUtils.select_by_user_name_and_plan_name(
            current_user_id, plan_name
        )
        if not plan:
            return response_helper.not_found("计划不存在")

        return jsonify(
            {
                "status": 200,
                "data": {
                    "public": plan.public,
                    "share_token": plan.share_token,
                    "share_url": f"{request.host_url}workflow/{plan.share_token}"
                    if plan.share_token and plan.public
                    else None,
                    "has_snapshot": bool(plan.filter_snapshot),
                },
            }
        )

    except Exception as e:
        logger.error(f"获取分享状态失败: {e}")
        traceback.print_exc()
        return response_helper.server_error("获取失败")


@api_public_bp.route("/workflow/<token>", methods=["GET"])
async def get_public_workflow(token: str):
    """
    获取公开工作流数据

    免登录访问，根据share_token返回过滤后的工作流数据。

    Parameters:
        - token (path, string, required): 分享令牌

    Returns:
        - status: 状态码
        - data: 工作流数据
    """
    try:
        # 根据token查找计划
        plan = await EveIndustryPlanDBUtils.select_by_share_token(token)
        if not plan:
            return response_helper.not_found("分享链接不存在")

        # 检查公开状态
        if not plan.public:
            return response_helper.forbidden("该分享链接已关闭")

        # 获取计划数据（从缓存读取已计算结果）
        from src_v2.model.EVE.industry.industry_manager import IndustryManager
        from src_v2.core.utils import KahunaException

        try:
            # 尝试从缓存获取计算结果
            result_data = await IndustryManager.get_calculation_result(
                plan.user_name, plan.plan_name
            )
            workflow_data = result_data.get("work_flow", [])
        except KahunaException:
            # 缓存不存在或计算未完成
            return jsonify(
                {
                    "status": 404,
                    "message": "工作流数据尚未计算，请通知计划所有者先进行计算",
                }
            ), 404

        # 应用过滤条件快照
        filter_snapshot = plan.filter_snapshot or {}
        filtered_data = apply_workflow_filters(workflow_data, filter_snapshot)

        return jsonify(
            {
                "status": 200,
                "data": {
                    "plan_name": plan.plan_name,
                    "filter_snapshot": plan.filter_snapshot,
                    "workflow_data": filtered_data,
                },
            }
        )

    except Exception as e:
        logger.error(f"获取公开工作流失败: {e}")
        traceback.print_exc()
        return response_helper.server_error("获取工作流失败")


def apply_workflow_filters(
    workflow_data: List[Dict], filter_snapshot: Dict
) -> List[Dict]:
    """
    应用过滤条件到工作流数据

    与前端过滤逻辑保持一致
    """
    result = workflow_data

    # 1. 蓝图过滤 - 支持三种状态: 'all'(所有), 'no_blueprint'(无蓝图), 'has_blueprint'(有蓝图)
    show_fake = filter_snapshot.get("showFake", "all")
    if show_fake == "no_blueprint":
        # 只显示无蓝图的项目（fake=true）
        result = [
            item for item in result if item.get("bp_object", {}).get("fake", False)
        ]
    elif show_fake == "has_blueprint":
        # 只显示有蓝图的项目（fake=false）
        result = [
            item for item in result if not item.get("bp_object", {}).get("fake", True)
        ]

    # 2. 材料满足过滤 - materialUnavailable为true时只显示有材料的项目
    material_unavailable = filter_snapshot.get("materialUnavailable", False)
    if material_unavailable:
        result = [item for item in result if item.get("avaliable", False)]

    # 3. 工作类型过滤
    active_id_filter = filter_snapshot.get("activeIdFilter", "all")
    if active_id_filter != "all":
        result = [
            item
            for item in result
            if str(item.get("active_id")) == str(active_id_filter)
        ]

    # 4. 产物类型过滤
    class_type_filter = filter_snapshot.get("classTypeFilter", [])
    if class_type_filter:
        result = [
            item for item in result if item.get("class_type") in class_type_filter
        ]

    # 5. 分类过滤
    category_filter = filter_snapshot.get("categoryFilter", [])
    if category_filter:
        result = [
            item for item in result if item.get("category_name") in category_filter
        ]

    # 6. 市场组过滤
    market_group_filter = filter_snapshot.get("marketGroupFilter", [])
    if market_group_filter:
        result = [
            item for item in result
            if any(mg in market_group_filter for mg in (item.get("market_group_list") or []))
        ]

    return result


# ============ 任务接取功能API ============


@api_public_bp.route("/workflow/<token>/claim", methods=["POST"])
@auth_required
async def claim_workflow_task(token: str):
    """
    接取工作流任务（支持部分接取）

    Parameters:
        - token (path, string, required): 分享令牌

    Request Body:
        - workflow_item_key (str): 工作流项唯一标识
        - quantity (int, optional): 接取数量，默认为1

    Returns:
        - status: 状态码
        - message: 提示信息
        - data: 接取信息
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]
    workflow_item_key = data.get("workflow_item_key", "").lower()  # 统一使用小写格式
    quantity = data.get("quantity", 1)
    
    logger.info(f"[DEBUG] 接取任务: user={current_user_id}, key={workflow_item_key}, qty={quantity}")

    if not workflow_item_key:
        return response_helper.bad_request("缺少工作流项标识")

    # 验证数量
    try:
        quantity = int(quantity)
        if quantity < 1:
            return response_helper.bad_request("接取数量必须大于0")
    except (TypeError, ValueError):
        return response_helper.bad_request("接取数量格式错误")

    try:
        # 验证分享链接有效性
        plan = await EveIndustryPlanDBUtils.select_by_share_token(token)
        if not plan or not plan.public:
            return response_helper.forbidden("分享链接无效或已关闭")

        # 获取工作流数据以验证总数量
        from src_v2.model.EVE.industry.industry_manager import IndustryManager
        from src_v2.core.utils import KahunaException

        try:
            result_data = await IndustryManager.get_calculation_result(
                plan.user_name, plan.plan_name
            )
            workflow_data = result_data.get("work_flow", [])
        except KahunaException:
            return response_helper.not_found("工作流数据不存在")

        # 计算线数（按 type_id + runs + fake + avaliable 分组）
        from collections import defaultdict
        line_count_map = defaultdict(int)
        for item in workflow_data:
            fake_val = str(item.get('bp_object', {}).get('fake', False)).lower()
            avaliable_val = str(item.get('avaliable', False)).lower()
            key = f"{int(item['type_id'])}_{int(item['runs'])}_{fake_val}_{avaliable_val}"
            line_count_map[key] += 1

        # 找到对应的工作流项
        target_item = None
        target_line_count = 0
        for item in workflow_data:
            # 使用小写字符串表示布尔值，与前端保持一致
            fake_val = str(item.get('bp_object', {}).get('fake', False)).lower()
            avaliable_val = str(item.get('avaliable', False)).lower()
            item_key = f"{int(item['type_id'])}_{int(item['runs'])}_{fake_val}_{avaliable_val}"
            if item_key == workflow_item_key:
                target_item = item
                target_line_count = line_count_map[item_key]
                break

        if not target_item:
            return response_helper.not_found("工作流项不存在")

        # 获取总线数 (使用 line_count - 分组数量)
        total_lines = target_line_count
        logger.info(f"[DEBUG-CLAIM] target_item: type_id={target_item.get('type_id')}, runs={target_item.get('runs')}, line_count={target_line_count}")
        logger.info(f"[DEBUG-CLAIM] 总线数: total_lines={total_lines} (from line_count)")

        # 获取已接取数量
        total_claimed = (
            await EveIndustryPlanTaskClaimDBUtils.get_total_claimed_quantity(
                token, workflow_item_key
            )
        )

        logger.info(f"[DEBUG-CLAIM] 验证计算: total={total_lines}, claimed={total_claimed}, request_qty={quantity}, sum={total_claimed + quantity}, user={current_user_id}")

        # 检查是否超出（> 表示不能超过，可以等于）
        if total_claimed + quantity > total_lines:
            remaining = total_lines - total_claimed
            logger.info(f"[DEBUG-CLAIM] 新用户接取被拒绝: remaining={remaining}")
            return jsonify(
                {
                    "status": 400,
                    "message": f"超出可接取数量，剩余 {remaining} 线",
                    "data": {
                        "total_lines": total_lines,
                        "claimed_lines": total_claimed,
                        "remaining_lines": remaining,
                    },
                }
            ), 400

        # 使用单一数据库会话进行检查和写入，避免竞态条件（封装模块内完成事务）
        now = datetime.utcnow()
        result, new_quantity = await EveIndustryPlanTaskClaimDBUtils.claim_or_append(
            token, workflow_item_key, current_user_id, quantity, now
        )

        if result == "conflict":
            # 唯一约束冲突且重试后仍未找到当前用户记录（并发竞态）
            logger.error(f"[DEBUG] 冲突但重试未找到当前用户记录，可能是其他用户的记录")
            return jsonify(
                {"status": 409, "message": "接取冲突，请刷新页面后重试"}
            ), 409

        if result == "appended":
            logger.info(f"[DEBUG-CLAIM] 追加成功: user={current_user_id}, add_qty={quantity}, new_qty={new_quantity}")
            return jsonify(
                {
                    "status": 200,
                    "message": f"成功追加接取 {quantity} 线",
                    "data": {
                        "claimed_by": current_user_id,
                        "claimed_quantity": new_quantity,
                        "claimed_at": now.isoformat(),
                    },
                }
            )

        # result == "created"
        logger.info(f"[DEBUG-CLAIM] 创建成功: user={current_user_id}, qty={quantity}")
        return jsonify(
            {
                "status": 200,
                "message": f"成功接取 {quantity} 线",
                "data": {
                    "claimed_by": current_user_id,
                    "claimed_quantity": quantity,
                    "claimed_at": now.isoformat(),
                },
            }
        )

    except IntegrityError as ie:
        # 防御性捕获安全网：理论上不会到达这里，但保留作为安全层
        logger.error(f"[DEBUG] 外层 IntegrityError 安全网触发: {ie}, key={workflow_item_key}, user={current_user_id}")
        return jsonify(
            {"status": 409, "message": "接取冲突，请刷新页面后重试"}
        ), 409

    except Exception as e:
        logger.error(f"接取任务失败: {e}")
        traceback.print_exc()
        return response_helper.server_error("接取失败")


@api_public_bp.route("/workflow/<token>/claim", methods=["DELETE"])
@auth_required
async def cancel_workflow_task_claim(token: str):
    """
    取消任务接取（仅接取人可操作）

    Parameters:
        - token (path, string, required): 分享令牌

    Request Body:
        - workflow_item_key (str): 工作流项唯一标识

    Returns:
        - status: 状态码
        - message: 提示信息
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]
    workflow_item_key = data.get("workflow_item_key", "").lower()  # 统一使用小写格式

    if not workflow_item_key:
        return response_helper.bad_request("缺少工作流项标识")

    try:
        # 查询当前用户的接取记录并删除（封装模块内实现，校验归属）
        deleted = await EveIndustryPlanTaskClaimDBUtils.cancel_claim_by_user(
            token, workflow_item_key, current_user_id
        )
        if not deleted:
            return response_helper.not_found("未找到您的接取记录")

        return response_helper.ok(message="已取消接取")

    except Exception as e:
        logger.error(f"取消接取失败: {e}")
        traceback.print_exc()
        return response_helper.server_error("操作失败")


@api_public_bp.route("/workflow/<token>/claims", methods=["GET"])
async def get_workflow_claims(token: str):
    """
    获取工作流的所有接取记录（包含数量信息）

    公开访问，无需登录。

    Parameters:
        - token (path, string, required): 分享令牌

    Returns:
        - status: 状态码
        - data: 接取记录列表，包含每个任务的接取详情
    """
    try:
        # 验证分享链接有效性
        plan = await EveIndustryPlanDBUtils.select_by_share_token(token)
        if not plan or not plan.public:
            return response_helper.forbidden("分享链接无效")

        # 获取工作流数据以计算总线数
        from src_v2.model.EVE.industry.industry_manager import IndustryManager
        from src_v2.core.utils import KahunaException

        workflow_items = {}
        try:
            result_data = await IndustryManager.get_calculation_result(
                plan.user_name, plan.plan_name
            )
            workflow_data = result_data.get("work_flow", [])
            # 计算线数（按 type_id + runs + fake + avaliable 分组）
            from collections import defaultdict
            line_count_map = defaultdict(int)
            for item in workflow_data:
                fake_val = str(item.get('bp_object', {}).get('fake', False)).lower()
                avaliable_val = str(item.get('avaliable', False)).lower()
                key = f"{int(item['type_id'])}_{int(item['runs'])}_{fake_val}_{avaliable_val}"
                line_count_map[key] += 1
            # 构建 workflow_item_key -> line_count (总线数) 映射
            for item in workflow_data:
                fake_val = str(item.get('bp_object', {}).get('fake', False)).lower()
                avaliable_val = str(item.get('avaliable', False)).lower()
                item_key = f"{int(item['type_id'])}_{int(item['runs'])}_{fake_val}_{avaliable_val}"
                workflow_items[item_key] = line_count_map[item_key]
        except KahunaException:
            pass  # 工作流数据不存在时继续返回接取记录

        # 查询所有接取记录
        claims = await EveIndustryPlanTaskClaimDBUtils.select_by_plan_token(token)

        # 按工作流项分组统计（key统一使用小写格式）
        item_claims = {}
        for claim in claims:
            # 将数据库中的key转为小写，确保一致性
            key = claim.workflow_item_key.lower() if claim.workflow_item_key else ""
            if key not in item_claims:
                item_claims[key] = {
                    "total_lines": workflow_items.get(key, 1),
                    "claimed_lines": 0,
                    "claims": [],
                }
            item_claims[key]["claimed_lines"] += claim.claimed_quantity or 0
            item_claims[key]["claims"].append(
                {
                    "claimed_by": claim.claimed_by,
                    "claimed_quantity": claim.claimed_quantity,
                    "claimed_at": claim.claimed_at.isoformat()
                    if claim.claimed_at
                    else None,
                    "status": claim.status,
                }
            )

        # 计算剩余数量
        for key in item_claims:
            item_claims[key]["remaining_lines"] = (
                item_claims[key]["total_lines"] - item_claims[key]["claimed_lines"]
            )

        return response_helper.ok(item_claims)

    except Exception as e:
        logger.error(f"获取接取记录失败: {e}")
        traceback.print_exc()
        return response_helper.server_error("获取失败")

# ============ 任务接取管理功能API（需要所有者或管理员权限） ============


async def check_claim_manage_permission(token: str, current_user_id: str):
    """
    检查用户是否有权限管理接取记录

    只有计划所有者或管理员可以管理接取。

    Args:
        token: 分享令牌
        current_user_id: 当前用户ID

    Returns:
        (是否有权限, 计划对象)
    """
    plan = await EveIndustryPlanDBUtils.select_by_share_token(token)
    if not plan:
        return False, None

    # 检查是否是计划所有者
    if plan.user_name == current_user_id:
        return True, plan

    # 检查是否是管理员
    user = await UserManager().get_user(current_user_id)
    if user:
        roles = await user.roles
        if 'admin' in roles:
            return True, plan

    return False, plan


@api_public_bp.route("/workflow/<token>/claim/manage/delete", methods=["POST"])
@auth_required
async def delete_workflow_claim_admin(token: str):
    """
    管理员删除接取记录

    允许计划所有者或管理员删除任何接取记录。

    Parameters:
        - token (path, string, required): 分享令牌

    Request Body:
        - workflow_item_key (str): 工作流项唯一标识

    Returns:
        - status: 状态码
        - message: 提示信息
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]
    workflow_item_key = data.get("workflow_item_key", "").lower()  # 统一使用小写格式

    if not workflow_item_key:
        return response_helper.bad_request("缺少工作流项标识")

    try:
        # 检查权限
        has_permission, plan = await check_claim_manage_permission(token, current_user_id)
        if not plan:
            return response_helper.not_found("分享链接不存在")

        if not has_permission:
            return response_helper.forbidden("无权管理此计划的接取记录")

        # 查询接取记录
        claim = await EveIndustryPlanTaskClaimDBUtils.select_by_plan_token_and_item_key(
            token, workflow_item_key
        )

        if not claim:
            return response_helper.not_found("接取记录不存在")

        # 删除接取记录
        await EveIndustryPlanTaskClaimDBUtils.delete_by_plan_token_and_item_key(
            token, workflow_item_key
        )

        return jsonify({
            "status": 200,
            "message": "接取记录已删除",
            "data": {
                "workflow_item_key": workflow_item_key,
                "claimed_by": claim.claimed_by
            }
        })

    except Exception as e:
        logger.error(f"删除接取记录失败: {e}")
        traceback.print_exc()
        return response_helper.server_error("删除失败")


@api_public_bp.route("/workflow/<token>/claim/manage/transfer", methods=["POST"])
@auth_required
async def transfer_workflow_claim_admin(token: str):
    """
    管理员转移接取记录给其他用户

    允许计划所有者或管理员将接取记录转移给另一个用户。

    Parameters:
        - token (path, string, required): 分享令牌

    Request Body:
        - workflow_item_key (str): 工作流项唯一标识
        - new_claimed_by (str): 新接取人用户名

    Returns:
        - status: 状态码
        - message: 提示信息
    """
    data = await request.json
    current_user_id = g.current_user["user_id"]
    workflow_item_key = data.get("workflow_item_key", "").lower()  # 统一使用小写格式
    new_claimed_by = data.get("new_claimed_by")

    if not workflow_item_key:
        return response_helper.bad_request("缺少工作流项标识")

    if not new_claimed_by:
        return response_helper.bad_request("请输入新接取人用户名")

    try:
        # 检查权限
        has_permission, plan = await check_claim_manage_permission(token, current_user_id)
        if not plan:
            return response_helper.not_found("分享链接不存在")

        if not has_permission:
            return response_helper.forbidden("无权管理此计划的接取记录")

        # 验证新用户是否存在
        new_user = await UserManager().get_user(new_claimed_by)
        if not new_user:
            return response_helper.not_found("新接取人用户不存在")

        # 查询现有接取记录
        existing_claim = await EveIndustryPlanTaskClaimDBUtils.select_by_plan_token_and_item_key(
            token, workflow_item_key
        )

        if not existing_claim:
            return response_helper.not_found("接取记录不存在")

        old_claimed_by = existing_claim.claimed_by

        # 更新接取记录（封装模块内使用 update 语句原子更新，避免 detached 对象跨会话修改失效）
        affected = await EveIndustryPlanTaskClaimDBUtils.transfer_claim(
            token, workflow_item_key, new_claimed_by, datetime.utcnow()
        )
        if not affected:
            return response_helper.not_found("接取记录不存在")

        return jsonify({
            "status": 200,
            "message": "接取记录已转移",
            "data": {
                "workflow_item_key": workflow_item_key,
                "old_claimed_by": old_claimed_by,
                "new_claimed_by": new_claimed_by
            }
        })

    except Exception as e:
        logger.error(f"转移接取记录失败: {e}")
        traceback.print_exc()
        return response_helper.server_error("转移失败")


# ==================== Landing Page 统计数据 ====================

@api_public_bp.route("/landing/stats", methods=["GET"])
async def landing_stats():
    """
    公开接口：返回落地页需要的统计数据
    无需认证
    """
    try:
        # 注册用户数
        user_count = await UserDBUtils.count_all()

        # 去重公司ID
        corp_ids = await EveAuthedCharacterDBUtils.get_distinct_corporation_ids()

        # 批量查询公司信息
        corp_list = await EveCorporationDBUtils.select_corporations_by_ids(corp_ids)

        corporations = []
        for corp in corp_list:
            corporations.append({
                "id": corp.corporation_id,
                "name": corp.name,
                "ticker": corp.ticker,
                "member_count": corp.member_count or 0,
                "icon_url": f"https://images.evetech.net/corporations/{corp.corporation_id}/logo"
            })

        return jsonify({
            "status": 200,
            "data": {
                "user_count": user_count,
                "corp_count": len(corporations),
                "corporations": sorted(corporations, key=lambda x: x["member_count"], reverse=True)
            }
        })

    except Exception as e:
        logger.error(f"获取落地页统计数据失败: {e}")
        traceback.print_exc()
        # 失败时返回空数据，不阻塞页面
        return jsonify({
            "status": 200,
            "data": {
                "user_count": 0,
                "corp_count": 0,
                "corporations": []
            }
        })
