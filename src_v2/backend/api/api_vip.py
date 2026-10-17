import traceback
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from quart import request, jsonify, g, Blueprint

from src_v2.backend.auth import auth_required
from src_v2.backend.api.permission_required import permission_required, role_required
from src_v2.core.log import logger
from src_v2.core.permission.grant_guard import (
    GrantDenied,
    assert_admin_operator,
    audit_grant,
)
from src_v2.core.utils import KahunaException
from src_v2.core.database.kahuna_database_utils_v2 import VipStateDBUtils, UserDBUtils
from src_v2.backend.api import response_helper
from datetime import datetime

api_vip_bp = Blueprint('api_vip', __name__, url_prefix='/api/vip')


# 请求数据模型
@dataclass
class UpdateVipStateRequest:
    """更新VIP状态请求"""
    vipLevel: Optional[str] = None
    vipEndDate: Optional[str] = None


# 响应数据模型
@dataclass
class VipStateItem:
    """VIP状态项"""
    userName: str
    vipLevel: str
    vipEndDate: str


@dataclass
class VipStatesResponse:
    """VIP状态列表响应"""
    status: int
    data: List[VipStateItem]


@dataclass
class MessageResponse:
    """消息响应"""
    status: int
    message: str


@dataclass
class UserSearchResponse:
    """用户搜索响应"""
    status: int
    data: List[Dict[str, str]]


@dataclass
class ErrorResponse:
    """错误响应"""
    status: int
    message: str


@api_vip_bp.route("", methods=["GET"])
@auth_required
@permission_required(["admin:read"])
# @validate_response(VipStatesResponse)
async def get_all_vip_states():
    """
    获取所有VIP状态列表
    
    获取系统中所有用户的VIP状态信息，包括VIP等级和到期日期。

    Tags:
        - VIP管理

    Security:
        - Bearer: []

    Responses:
        200: 成功返回VIP状态列表
            - status: 状态码 (200)
            - data: VIP状态列表，每个元素包含用户名、VIP等级、到期日期 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "userName": "user1",
                    "vipLevel": "vip_alpha",
                    "vipEndDate": "2024-12-31T23:59:59"
                }
            ]
        }
    """
    try:
        vip_states = []
        async with await VipStateDBUtils.select_all_vip_states() as iterator:
            async for vip_state in iterator:
                # 格式化日期
                vip_end_date_str = ''
                if vip_state.vip_end_date:
                    if hasattr(vip_state.vip_end_date, 'isoformat'):
                        vip_end_date_str = vip_state.vip_end_date.isoformat()
                    else:
                        vip_end_date_str = str(vip_state.vip_end_date)
                
                vip_states.append({
                    "userName": vip_state.user_name or '',
                    "vipLevel": vip_state.vip_level or '',
                    "vipEndDate": vip_end_date_str
                })
        
        return {"status": 200, "data": vip_states}
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取VIP状态列表失败: {traceback.format_exc()}")
        return response_helper.server_error("获取VIP状态列表失败")


@api_vip_bp.route("/<user_name>", methods=["PUT"])
@auth_required
@role_required(["admin"])
# @validate_request(UpdateVipStateRequest)
# @validate_response(MessageResponse)
async def update_vip_state(user_name: str):
    """
    更新指定用户的VIP状态
    
    更新指定用户的VIP等级和到期日期。VIP等级必须是 vip_alpha 或 vip_omega。

    安全说明：VIP 等级在 role_required 中被当作角色使用（可解锁企业版/资产/工业
    等全部付费接口），因此本端点要求操作者具备 admin 角色，而不是仅 admin:write。

    Tags:
        - VIP管理

    Security:
        - Bearer: []

    Parameters:
        - user_name (path, string, required): 用户名

    Request Body:
        - vipLevel (string, optional): VIP等级，可选值: vip_alpha, vip_omega
        - vipEndDate (string, optional): VIP到期日期，ISO格式日期字符串

    Responses:
        200: 更新成功
            - status: 状态码 (200)
            - message: 成功消息 (string)
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "vipLevel": "vip_alpha",
            "vipEndDate": "2024-12-31T23:59:59"
        }

    Example Response:
        {
            "status": 200,
            "message": "更新成功"
        }
    """
    try:
        operator_id = g.current_user["user_id"]

        # 纵深防御：装饰器已要求 admin 角色，这里再用 is_admin_user 显式复核一次
        # （is_admin_user 只认角色、不认 VIP 等级，避免"发 VIP 自解锁"的绕过）
        try:
            await assert_admin_operator(operator_id)
        except GrantDenied as e:
            logger.warning(
                f"拒绝越权修改 VIP: operator={operator_id} target={user_name} reason={e}"
            )
            return response_helper.forbidden(str(e))

        data = await request.get_json()
        vip_level = data.get('vipLevel')
        vip_end_date_str = data.get('vipEndDate')
        
        # 验证VIP等级
        if vip_level is not None and vip_level not in ['vip_alpha', 'vip_omega']:
            return response_helper.bad_request("VIP等级必须是 vip_alpha 或 vip_omega")
        
        # 解析日期时间
        vip_end_date = None
        if vip_end_date_str:
            try:
                # 处理ISO格式日期字符串，支持带Z和不带时区的情况
                date_str = vip_end_date_str.replace('Z', '+00:00')
                # 如果字符串中没有时区信息，尝试直接解析
                if '+' not in date_str and date_str[-1] != 'Z' and 'T' in date_str:
                    vip_end_date = datetime.fromisoformat(date_str)
                elif '+' in date_str or date_str.endswith('+00:00'):
                    vip_end_date = datetime.fromisoformat(date_str)
                else:
                    # 尝试其他格式
                    vip_end_date = datetime.fromisoformat(date_str)
            except (ValueError, AttributeError) as e:
                logger.error(f"日期解析失败: {vip_end_date_str}, 错误: {e}")
                return response_helper.bad_request(f"日期时间格式错误: {str(e)}")
        
        # 检查用户是否存在
        existing_user = await UserDBUtils.select_user_by_user_name(user_name)
        if not existing_user:
            return response_helper.not_found(f"用户 {user_name} 不存在，请先注册")
        
        # 更新VIP状态
        await VipStateDBUtils.update_vip_state(
            user_name=user_name,
            vip_level=vip_level,
            vip_end_date=vip_end_date
        )

        audit_grant(
            operator_id,
            "update-vip",
            user_name,
            f"level={vip_level or ''} end={vip_end_date_str or ''}",
        )

        # VIP 等级决定 role_required 的可见范围，变更后撤销该用户 refresh token
        # （refresh_token_store 由并行子任务提供，懒导入 + 保护，缺失时安全降级）
        try:
            from src_v2.core.user.refresh_token_store import revoke_all_for_user
            await revoke_all_for_user(user_name)
        except Exception as exc:
            logger.warning(f"撤销用户 {user_name} 的 refresh token 失败: {exc}")

        return {"status": 200, "message": "更新成功"}
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"更新VIP状态失败: {traceback.format_exc()}")
        return response_helper.server_error("更新VIP状态失败")


@api_vip_bp.route("/search-users", methods=["GET"])
@auth_required
@permission_required(["admin:read"])
# @validate_response(UserSearchResponse)
async def search_users():
    """
    搜索用户（用于自动补全）
    
    根据查询关键字搜索用户名，用于前端自动补全功能。支持模糊匹配。

    Tags:
        - VIP管理

    Security:
        - Bearer: []

    Parameters:
        - query (query, string, optional): 搜索关键字，为空时返回空列表
        - limit (query, integer, optional): 返回结果数量限制，默认20

    Responses:
        200: 成功返回用户列表
            - status: 状态码 (200)
            - data: 用户列表，每个元素包含用户名 (array)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": [
                {
                    "userName": "user1"
                },
                {
                    "userName": "user2"
                }
            ]
        }
    """
    try:
        query = request.args.get('query', '').strip()
        limit = int(request.args.get('limit', 20))
        
        if not query:
            return {"status": 200, "data": []}
        
        # 使用 LIKE 进行模糊搜索（封装模块内实现）
        matched_users = await UserDBUtils.search_users_by_keyword(query, limit)
        users = [{"userName": user.user_name} for user in matched_users]

        return {"status": 200, "data": users}
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"搜索用户失败: {traceback.format_exc()}")
        return response_helper.server_error("搜索用户失败")

