import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from quart import Blueprint, g, jsonify, request

from src_v2.backend.api.permission_required import role_required
from src_v2.backend.auth import auth_required
from src_v2.core.database.message_board_utils import MessageBoardDBUtils
from src_v2.core.log import logger
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.utils import KahunaException
from src_v2.backend.api import response_helper

api_message_board_bp = Blueprint(
    "api_message_board", __name__, url_prefix="/api/message-board")


# 请求数据模型
@dataclass
class CreateCardRequest:
    """创建留言卡片请求"""
    type: str  # bug, feat, chat
    title: str
    content: str


@dataclass
class CreateReplyRequest:
    """创建回复请求"""
    content: str


@dataclass
class UpdateCardRequest:
    """更新卡片请求"""
    status: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    type: Optional[str] = None


# 响应数据模型
@dataclass
class UserBrief:
    """用户摘要"""
    id: str
    name: str
    avatarUrl: Optional[str] = None


@dataclass
class CardItem:
    """卡片项"""
    id: int
    title: str
    type: str
    status: str
    author: UserBrief
    created_at: Optional[str] = None
    last_reply_at: Optional[str] = None
    reply_count: int = 0
    auto_closed: bool = False
    is_hidden: bool = False
    content_snippet: Optional[str] = None


@dataclass
class PaginationInfo:
    """分页信息"""
    page: int
    page_size: int
    total: int
    has_next: bool


@dataclass
class CardListResponse:
    """卡片列表响应"""
    status: int
    data: Dict[str, Any]  # items: List[CardItem], pagination: PaginationInfo


@dataclass
class CardDetail:
    """卡片详情"""
    id: int
    title: str
    type: str
    status: str
    content: str
    author: UserBrief
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_reply_at: Optional[str] = None
    reply_count: int = 0
    auto_closed: bool = False
    closed_at: Optional[str] = None
    is_hidden: bool = False


@dataclass
class CardDetailResponse:
    """卡片详情响应"""
    status: int
    data: CardDetail


@dataclass
class ReplyItem:
    """回复项"""
    id: int
    author: UserBrief
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_hidden: bool = False


@dataclass
class ReplyListResponse:
    """回复列表响应"""
    status: int
    data: Dict[str, Any]  # items: List[ReplyItem], pagination: PaginationInfo


@dataclass
class MessageResponse:
    """消息响应"""
    status: int
    message: str


@dataclass
class ErrorResponse:
    """错误响应"""
    status: int
    message: str
    code: Optional[str] = None


async def _get_all_roles(user_id: str) -> set[str]:
    """获取用户的所有角色（直接 + 继承）"""
    user_roles = await permission_manager.get_user_roles(user_id)
    all_roles: set[str] = set(user_roles or [])
    if user_roles:
        for role in user_roles:
            try:
                descendant_roles = await permission_manager.get_all_descendant_roles(role)
                if descendant_roles:
                    all_roles.update(descendant_roles)
            except Exception as e:
                logger.warning(f"获取角色 {role} 的父角色失败: {str(e)}")
    return all_roles


async def _is_admin(user_id: str) -> bool:
    all_roles = await _get_all_roles(user_id)
    return "admin" in all_roles


async def _check_rate_limit(user_name: str, is_admin: bool) -> Optional[str]:
    """
    非管理员用户 1 分钟仅允许发送一条（card 或 reply）
    返回错误消息字符串表示受限；返回 None 表示通过
    """
    if is_admin:
        return None

    latest_time = await MessageBoardDBUtils.get_latest_message_time(user_name)
    if not latest_time:
        return None

    now = datetime.utcnow()
    if now - latest_time < timedelta(minutes=1):
        # 距离上次发送不足 1 分钟
        return "非管理员用户每分钟仅允许发送一条留言或回复"
    return None


def _serialize_user_brief(user_name: str) -> dict:
    """
    简单的用户摘要，当前系统以 user_name 为主键，
    可以预留 avatar 等字段方便前端展示
    """
    return {
        "id": user_name,
        "name": user_name,
        "avatarUrl": None,
    }


@api_message_board_bp.route("/cards", methods=["GET"])
@auth_required
# @validate_response(CardListResponse)
async def list_cards():
    """
    获取留言卡片列表（筛选 + 排序 + 分页）
    
    获取留言卡片列表，支持多种筛选条件、排序和分页。普通用户只能看到未隐藏的卡片和自己创建的隐藏卡片，管理员可以看到所有卡片。

    Tags:
        - 留言板

    Security:
        - Bearer: []

    Parameters:
        - page (query, integer, optional): 页码，默认1
        - page_size (query, integer, optional): 每页数量，默认20，最大50
        - status (query, array, optional): 状态筛选，可选值: created, in_progress, closed，默认["created", "in_progress"]
        - type (query, array, optional): 类型筛选，可选值: bug, feat, chat
        - created_from (query, string, optional): 创建时间起始，ISO格式
        - created_to (query, string, optional): 创建时间结束，ISO格式
        - mine (query, boolean, optional): 是否只显示我创建的，默认false
        - participated (query, boolean, optional): 是否只显示我回复过的，默认false
        - publisher_search (query, string, optional): 发布人搜索关键字
        - order_by (query, string, optional): 排序字段，可选值: created_at, last_reply_at，默认last_reply_at
        - order (query, string, optional): 排序方向，可选值: asc, desc，默认desc
        - show_hidden (query, boolean, optional): 管理员专用，是否只显示隐藏的卡片，默认false

    Responses:
        200: 成功返回卡片列表
            - status: 状态码 (200)
            - data: 包含items（卡片列表）和pagination（分页信息）的对象
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {
                "items": [
                    {
                        "id": 1,
                        "title": "标题",
                        "type": "bug",
                        "status": "in_progress",
                        "author": {"id": "user1", "name": "user1", "avatarUrl": null},
                        "created_at": "2024-01-01T00:00:00",
                        "last_reply_at": "2024-01-01T01:00:00",
                        "reply_count": 5,
                        "auto_closed": false,
                        "is_hidden": false,
                        "content_snippet": "内容摘要..."
                    }
                ],
                "pagination": {
                    "page": 1,
                    "page_size": 20,
                    "total": 100,
                    "has_next": true
                }
            }
        }
    """
    try:
        user_id = g.current_user["user_id"]

        # 分页参数
        page = int(request.args.get("page", 1))
        page_size = min(int(request.args.get("page_size", 20)), 50)
        offset = (page - 1) * page_size

        # 状态过滤，默认排除 closed
        # 兼容 axios 默认数组序列化（status[]=...），优先读取 status，其次 status[]
        status_list = request.args.getlist(
            "status") or request.args.getlist("status[]")
        if not status_list:
            status_list = ["created", "in_progress"]

        # 类型过滤，兼容 axios 的 type[]=... 数组写法
        type_list = request.args.getlist(
            "type") or request.args.getlist("type[]")
        created_from = request.args.get("created_from")
        created_to = request.args.get("created_to")
        mine = request.args.get("mine", "false").lower() == "true"
        participated = request.args.get(
            "participated", "false").lower() == "true"
        publisher_search = request.args.get("publisher_search", "").strip()
        order_by = request.args.get("order_by", "last_reply_at")
        order = request.args.get("order", "desc")
        # 管理员筛选隐藏卡片
        show_hidden = request.args.get(
            "show_hidden", "false").lower() == "true"

        is_admin = await _is_admin(user_id)

        # 查询留言卡片列表（封装模块内实现筛选/排序/分页/回复数聚合）
        cards, total = await MessageBoardDBUtils.search_cards(
            user_id,
            is_admin,
            status_list=status_list,
            type_list=type_list,
            created_from=created_from,
            created_to=created_to,
            mine=mine,
            participated=participated,
            publisher_search=publisher_search,
            order_by=order_by,
            order=order,
            show_hidden=show_hidden,
            offset=offset,
            page_size=page_size,
        )

        items = []
        if cards:
            for card in cards:
                # 封装内已附加 reply_count / last_reply_at_from_reply 聚合信息
                reply_count = getattr(card, "reply_count", 0)
                last_reply_at = card.last_reply_at or getattr(
                    card, "last_reply_at_from_reply", None) or card.created_at
                # 为前端卡片提供内容摘要，避免一次性返回完整 content
                content_snippet = None
                if card.content:
                    # 这里简单按字符数截断，前端仍可再次做精细截断
                    content_snippet = card.content[:200]

                items.append(
                    {
                        "id": card.id,
                        "title": card.title,
                        "type": card.type,
                        "status": card.status,
                        "author": _serialize_user_brief(card.author_user_name),
                        "created_at": (card.created_at.isoformat() if card.created_at else None),
                        "last_reply_at": (last_reply_at.isoformat() if last_reply_at else None),
                        "reply_count": reply_count,
                        "auto_closed": bool(card.auto_closed),
                        "is_hidden": bool(card.is_hidden) if card.is_hidden is not None else False,
                        "content_snippet": content_snippet,
                    }
                )

        return jsonify(
            {
                "status": 200,
                "data": {
                    "items": items,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": total,
                        "has_next": offset + page_size < total,
                    },
                },
            }
        )
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception:
        traceback.print_exc()
        logger.error(f"获取留言卡片列表失败: {traceback.format_exc()}")
        return response_helper.server_error("获取留言卡片列表失败")


@api_message_board_bp.route("/cards", methods=["POST"])
@auth_required
# @validate_request(CreateCardRequest)
# @validate_response(CardDetailResponse)
async def create_card():
    """
    创建留言卡片
    
    创建新的留言卡片。非管理员用户每分钟仅允许发送一条留言或回复。chat类型的卡片初始状态为in_progress，其他类型为created。

    Tags:
        - 留言板

    Security:
        - Bearer: []

    Request Body:
        - type (string, required): 卡片类型，可选值: bug, feat, chat
        - title (string, required): 标题
        - content (string, required): 内容

    Responses:
        200: 创建成功
            - status: 状态码 (200)
            - data: 创建的卡片详情
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        429: 频率限制
            - status: 状态码 (429)
            - message: 错误信息 (string)
            - code: "RATE_LIMIT"
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "type": "bug",
            "title": "发现一个bug",
            "content": "详细描述..."
        }

    Example Response:
        {
            "status": 200,
            "data": {
                "id": 1,
                "title": "发现一个bug",
                "type": "bug",
                "status": "created",
                "content": "详细描述...",
                "author": {"id": "user1", "name": "user1", "avatarUrl": null},
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
                "last_reply_at": "2024-01-01T00:00:00",
                "reply_count": 0,
                "auto_closed": false,
                "closed_at": null,
                "is_hidden": false
            }
        }
    """
    try:
        user_id = g.current_user["user_id"]
        data = await request.get_json()
        card_type = (data.get("type") or "").strip()
        title = (data.get("title") or "").strip()
        content = (data.get("content") or "").strip()

        if card_type not in ("bug", "feat", "chat"):
            return response_helper.bad_request("type 必须为 bug/feat/chat")
        if not title:
            return response_helper.bad_request("标题不能为空")
        if not content:
            return response_helper.bad_request("内容不能为空")

        is_admin = await _is_admin(user_id)
        # 频率限制
        err = await _check_rate_limit(user_id, is_admin)
        if err:
            return response_helper.fail(err, 429, code="RATE_LIMIT")

        now = datetime.utcnow()
        status = "in_progress" if card_type == "chat" else "created"

        # 创建留言卡片（封装模块内实现，flush 后返回带 id 的对象）
        card = await MessageBoardDBUtils.create_card(
            user_id, card_type, status, title, content, now
        )

        result = {
            "id": card.id,
            "title": card.title,
            "type": card.type,
            "status": card.status,
            "author": _serialize_user_brief(card.author_user_name),
            "created_at": now.isoformat(),
            "last_reply_at": now.isoformat(),
            "reply_count": 0,
            "auto_closed": False,
            "content_snippet": card.content[:200] if card.content else None,
        }

        return {"status": 200, "data": result}
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception:
        traceback.print_exc()
        logger.error(f"创建留言卡片失败: {traceback.format_exc()}")
        return response_helper.server_error("创建留言卡片失败")


@api_message_board_bp.route("/cards/<int:card_id>", methods=["GET"])
@auth_required
# @validate_response(CardDetailResponse)
async def get_card_detail(card_id: int):
    """
    获取单个 card 详情（不含回复列表）
    
    获取指定卡片的详细信息。如果卡片被隐藏且当前用户不是发布者也不是管理员，将返回404。

    Tags:
        - 留言板

    Security:
        - Bearer: []

    Parameters:
        - card_id (path, integer, required): 卡片ID

    Responses:
        200: 成功返回卡片详情
            - status: 状态码 (200)
            - data: 卡片详情对象
        404: 卡片不存在或无权访问
            - status: 状态码 (404)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {
                "id": 1,
                "title": "标题",
                "type": "bug",
                "status": "in_progress",
                "content": "完整内容...",
                "author": {"id": "user1", "name": "user1", "avatarUrl": null},
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T01:00:00",
                "last_reply_at": "2024-01-01T01:00:00",
                "reply_count": 5,
                "auto_closed": false,
                "closed_at": null,
                "is_hidden": false
            }
        }
    """
    try:
        user_id = g.current_user["user_id"]
        is_admin = await _is_admin(user_id)

        # 查询卡片（封装模块内实现）
        card = await MessageBoardDBUtils.get_card_by_id(card_id)
        if not card:
            return response_helper.not_found("留言卡片不存在")

        # 检查隐藏权限：如果卡片被隐藏且当前用户不是发布者也不是管理员，返回404
        if card.is_hidden and not is_admin and card.author_user_name != user_id:
            return response_helper.not_found("留言卡片不存在")

        # 统计回复数（封装模块内实现）
        reply_count = await MessageBoardDBUtils.get_reply_count(card_id)

        last_reply_at = card.last_reply_at or card.created_at

        data = {
            "id": card.id,
            "title": card.title,
            "type": card.type,
            "status": card.status,
            "content": card.content,
            "author": _serialize_user_brief(card.author_user_name),
            "created_at": (card.created_at.isoformat() if card.created_at else None),
            "updated_at": (card.updated_at.isoformat() if card.updated_at else None),
            "last_reply_at": (last_reply_at.isoformat() if last_reply_at else None),
            "reply_count": reply_count,
            "auto_closed": bool(card.auto_closed),
            "closed_at": (card.closed_at.isoformat() if card.closed_at else None),
            "is_hidden": bool(card.is_hidden) if card.is_hidden is not None else False,
        }

        return {"status": 200, "data": data}
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception:
        traceback.print_exc()
        logger.error(f"获取留言卡片详情失败: {traceback.format_exc()}")
        return response_helper.server_error("获取留言卡片详情失败")


@api_message_board_bp.route("/cards/<int:card_id>/replies", methods=["GET"])
@auth_required
# @validate_response(ReplyListResponse)
async def list_replies(card_id: int):
    """
    获取 card 回复列表（分页）
    
    获取指定卡片的回复列表，支持分页。普通用户看不到他人隐藏的回复，管理员可以看到所有回复。

    Tags:
        - 留言板

    Security:
        - Bearer: []

    Parameters:
        - card_id (path, integer, required): 卡片ID
        - page (query, integer, optional): 页码，默认1
        - page_size (query, integer, optional): 每页数量，默认20，最大50

    Responses:
        200: 成功返回回复列表
            - status: 状态码 (200)
            - data: 包含items（回复列表）和pagination（分页信息）的对象
        404: 卡片不存在
            - status: 状态码 (404)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {
                "items": [
                    {
                        "id": 1,
                        "author": {"id": "user1", "name": "user1", "avatarUrl": null},
                        "content": "回复内容",
                        "created_at": "2024-01-01T00:00:00",
                        "updated_at": "2024-01-01T00:00:00",
                        "is_hidden": false
                    }
                ],
                "pagination": {
                    "page": 1,
                    "page_size": 20,
                    "total": 50,
                    "has_next": true
                }
            }
        }
    """
    try:
        user_id = g.current_user["user_id"]
        is_admin = await _is_admin(user_id)

        page = int(request.args.get("page", 1))
        page_size = min(int(request.args.get("page_size", 20)), 50)
        offset = (page - 1) * page_size

        # 查询回复列表（封装模块内实现：卡片存在性校验 + 隐藏过滤 + 分页 + 总数）
        replies, total = await MessageBoardDBUtils.search_replies(
            card_id, is_admin, user_id, offset, page_size
        )
        if replies is None:
            return response_helper.not_found("留言卡片不存在")

        items = []
        for r in replies:
            is_hidden = bool(
                r.is_hidden) if r.is_hidden is not None else False
            items.append(
                {
                    "id": r.id,
                    "author": _serialize_user_brief(r.author_user_name),
                    "content": r.content,
                    "created_at": (r.created_at.isoformat() if r.created_at else None),
                    "updated_at": (r.updated_at.isoformat() if r.updated_at else None),
                    "is_hidden": is_hidden,
                }
            )

        return jsonify(
            {
                "status": 200,
                "data": {
                    "items": items,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": total,
                        "has_next": offset + page_size < total,
                    },
                },
            }
        )
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception:
        traceback.print_exc()
        logger.error(f"获取留言回复列表失败: {traceback.format_exc()}")
        return response_helper.server_error("获取留言回复列表失败")


@api_message_board_bp.route("/cards/<int:card_id>/replies", methods=["POST"])
@auth_required
# @validate_request(CreateReplyRequest)
# @validate_response(CardDetailResponse)
async def create_reply(card_id: int):
    """
    创建回复
    
    为指定卡片创建回复。非管理员用户每分钟仅允许发送一条留言或回复。已关闭的卡片无法继续回复。

    Tags:
        - 留言板

    Security:
        - Bearer: []

    Parameters:
        - card_id (path, integer, required): 卡片ID

    Request Body:
        - content (string, required): 回复内容

    Responses:
        200: 创建成功
            - status: 状态码 (200)
            - data: 创建的回复信息
        400: 请求参数错误或卡片已关闭
            - status: 状态码 (400)
            - message: 错误信息 (string)
            - code: "CARD_CLOSED" (如果卡片已关闭)
        404: 卡片不存在
            - status: 状态码 (404)
            - message: 错误信息 (string)
        429: 频率限制
            - status: 状态码 (429)
            - message: 错误信息 (string)
            - code: "RATE_LIMIT"
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "content": "这是回复内容"
        }

    Example Response:
        {
            "status": 200,
            "data": {
                "id": 1,
                "author": {"id": "user1", "name": "user1", "avatarUrl": null},
                "content": "这是回复内容",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }
    """
    try:
        user_id = g.current_user["user_id"]
        data = await request.get_json()
        content = (data.get("content") or "").strip()

        if not content:
            return response_helper.bad_request("回复内容不能为空")

        is_admin = await _is_admin(user_id)

        # 检查 card（封装模块内实现）
        card = await MessageBoardDBUtils.get_card_by_id(card_id)
        if not card:
            return response_helper.not_found("留言卡片不存在")
        if card.status == "closed":
            return response_helper.fail("该留言已关闭，无法继续回复", 400, code="CARD_CLOSED")

        # 频率限制
        err = await _check_rate_limit(user_id, is_admin)
        if err:
            return response_helper.fail(err, 429, code="RATE_LIMIT")

        now = datetime.utcnow()
        # 创建回复并同步更新卡片（封装模块内实现，单会话事务）
        reply, error_code = await MessageBoardDBUtils.create_reply(
            card_id, user_id, content, now, is_admin
        )
        if error_code == "not_found":
            return response_helper.not_found("留言卡片不存在")
        if error_code == "CARD_CLOSED":
            return response_helper.fail("该留言已关闭，无法继续回复", 400, code="CARD_CLOSED")

        data_resp = {
            "id": reply.id,
            "author": _serialize_user_brief(reply.author_user_name),
            "content": reply.content,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        return {"status": 200, "data": data_resp}
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception:
        traceback.print_exc()
        logger.error(f"创建留言回复失败: {traceback.format_exc()}")
        return response_helper.server_error("创建留言回复失败")


@api_message_board_bp.route("/cards/<int:card_id>", methods=["PATCH"])
@auth_required
# @validate_request(UpdateCardRequest)
# @validate_response(CardDetailResponse)
async def update_card(card_id: int):
    """
    更新 card 状态 / 标题 / 内容 / 类型
    
    更新卡片的状态、标题、内容或类型。非管理员只能关闭自己创建的卡片或修改自己卡片的类型；管理员可以任意修改。

    Tags:
        - 留言板

    Security:
        - Bearer: []

    Parameters:
        - card_id (path, integer, required): 卡片ID

    Request Body:
        - status (string, optional): 新状态，可选值: created, in_progress, closed
        - title (string, optional): 新标题（仅管理员）
        - content (string, optional): 新内容（仅管理员）
        - type (string, optional): 新类型，可选值: bug, feat, chat

    Responses:
        200: 更新成功
            - status: 状态码 (200)
            - data: 更新后的卡片详情
        400: 请求参数错误
            - status: 状态码 (400)
            - message: 错误信息 (string)
        403: 无权限修改
            - status: 状态码 (403)
            - message: 错误信息 (string)
        404: 卡片不存在
            - status: 状态码 (404)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Request:
        {
            "status": "closed"
        }

    Example Response:
        {
            "status": 200,
            "data": {
                "id": 1,
                "title": "标题",
                "type": "bug",
                "status": "closed",
                "content": "内容",
                "author": {"id": "user1", "name": "user1", "avatarUrl": null},
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T02:00:00",
                "last_reply_at": "2024-01-01T01:00:00",
                "auto_closed": false,
                "closed_at": "2024-01-01T02:00:00"
            }
        }
    """
    try:
        user_id = g.current_user["user_id"]
        data = await request.get_json()

        new_status = data.get("status")
        new_title = data.get("title")
        new_content = data.get("content")
        new_type = data.get("type")

        is_admin = await _is_admin(user_id)

        # 查询卡片用于权限校验（封装模块内实现）
        card = await MessageBoardDBUtils.get_card_by_id(card_id)
        if not card:
            return response_helper.not_found("留言卡片不存在")

        now = datetime.utcnow()

        # 权限校验与字段决定（纯逻辑，最终写入由封装模块完成）
        final_status = None
        final_title = None
        final_content = None
        final_type = None
        final_closed_by = None
        final_closed_at = None

        if not is_admin:
            # 允许作者关闭自己的卡片
            if new_status and new_status == "closed":
                if card.author_user_name != user_id:
                    return response_helper.forbidden("只能关闭自己创建的卡片")
                final_status = "closed"
                final_closed_at = now
                final_closed_by = user_id
            # 允许作者修改自己卡片的类型
            elif new_type is not None:
                if card.author_user_name != user_id:
                    return response_helper.forbidden("只能修改自己创建的卡片")
                if new_type not in ("bug", "feat", "chat"):
                    return response_helper.bad_request("非法类型值")
                final_type = new_type
            else:
                return response_helper.forbidden("无权限修改状态或内容")
        else:
            # 管理员可以更新状态与内容
            if new_status:
                if new_status not in ("created", "in_progress", "closed"):
                    return response_helper.bad_request("非法状态值")
                final_status = new_status
                if new_status == "closed":
                    final_closed_at = now
                    final_closed_by = user_id
            if new_title is not None:
                final_title = new_title
            if new_content is not None:
                final_content = new_content
            if new_type is not None:
                if new_type not in ("bug", "feat", "chat"):
                    return response_helper.bad_request("非法类型值")
                final_type = new_type

        # 按字段更新卡片（封装模块内实现）
        card = await MessageBoardDBUtils.update_card_fields(
            card_id,
            new_status=final_status,
            new_title=final_title,
            new_content=final_content,
            new_type=final_type,
            closed_by=final_closed_by,
            closed_at=final_closed_at,
            now=now,
        )

        last_reply_at = card.last_reply_at or card.created_at
        data_resp = {
            "id": card.id,
            "title": card.title,
            "type": card.type,
            "status": card.status,
            "content": card.content,
            "author": _serialize_user_brief(card.author_user_name),
            "created_at": (card.created_at.isoformat() if card.created_at else None),
            "updated_at": (card.updated_at.isoformat() if card.updated_at else None),
            "last_reply_at": (last_reply_at.isoformat() if last_reply_at else None),
            "auto_closed": bool(card.auto_closed),
            "closed_at": (card.closed_at.isoformat() if card.closed_at else None),
        }

        return {"status": 200, "data": data_resp}
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception:
        traceback.print_exc()
        logger.error(f"更新留言卡片失败: {traceback.format_exc()}")
        return response_helper.server_error("更新留言卡片失败")


@api_message_board_bp.route("/cards/<int:card_id>/hide", methods=["PATCH"])
@auth_required
# @validate_response(CardDetailResponse)
async def toggle_card_hidden(card_id: int):
    """
    隐藏卡片（作者或管理员），单向不可逆
    
    隐藏指定的留言卡片。只有卡片的作者或管理员可以隐藏卡片。隐藏操作是单向不可逆的。

    Tags:
        - 留言板

    Security:
        - Bearer: []

    Parameters:
        - card_id (path, integer, required): 卡片ID

    Responses:
        200: 隐藏成功
            - status: 状态码 (200)
            - data: 更新后的卡片详情
        400: 卡片已被隐藏
            - status: 状态码 (400)
            - message: 错误信息 (string)
        403: 无权限隐藏
            - status: 状态码 (403)
            - message: 错误信息 (string)
        404: 卡片不存在
            - status: 状态码 (404)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {
                "id": 1,
                "title": "标题",
                "type": "bug",
                "status": "in_progress",
                "content": "内容",
                "author": {"id": "user1", "name": "user1", "avatarUrl": null},
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T02:00:00",
                "last_reply_at": "2024-01-01T01:00:00",
                "auto_closed": false,
                "closed_at": null,
                "is_hidden": true
            }
        }
    """
    try:
        user_id = g.current_user["user_id"]
        is_admin = await _is_admin(user_id)

        # 查询卡片用于权限校验（封装模块内实现）
        card = await MessageBoardDBUtils.get_card_by_id(card_id)
        if not card:
            return response_helper.not_found("留言卡片不存在")

        # 权限校验：只有作者或管理员可以隐藏
        if not is_admin and card.author_user_name != user_id:
            return response_helper.forbidden("只能隐藏自己创建的卡片")

        # 单向不可逆：已隐藏的卡片不能再次操作（封装内处理并返回状态）
        card, already_hidden = await MessageBoardDBUtils.set_card_hidden(
            card_id, datetime.utcnow()
        )
        if already_hidden:
            return response_helper.bad_request("该卡片已被隐藏，无法重复隐藏")

        last_reply_at = card.last_reply_at or card.created_at
        data_resp = {
            "id": card.id,
            "title": card.title,
            "type": card.type,
            "status": card.status,
            "content": card.content,
            "author": _serialize_user_brief(card.author_user_name),
            "created_at": (card.created_at.isoformat() if card.created_at else None),
            "updated_at": (card.updated_at.isoformat() if card.updated_at else None),
            "last_reply_at": (last_reply_at.isoformat() if last_reply_at else None),
            "auto_closed": bool(card.auto_closed),
            "closed_at": (card.closed_at.isoformat() if card.closed_at else None),
            "is_hidden": bool(card.is_hidden),
        }

        return {"status": 200, "data": data_resp}
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception:
        traceback.print_exc()
        logger.error(f"更新卡片隐藏状态失败: {traceback.format_exc()}")
        return response_helper.server_error("更新卡片隐藏状态失败")


@api_message_board_bp.route("/replies/<int:reply_id>/hide", methods=["PATCH"])
@auth_required
# @validate_response(CardDetailResponse)
async def toggle_reply_hidden(reply_id: int):
    """
    隐藏评论（作者或管理员），单向不可逆
    
    隐藏指定的回复评论。只有回复的作者或管理员可以隐藏回复。隐藏操作是单向不可逆的。

    Tags:
        - 留言板

    Security:
        - Bearer: []

    Parameters:
        - reply_id (path, integer, required): 回复ID

    Responses:
        200: 隐藏成功
            - status: 状态码 (200)
            - data: 更新后的回复信息
        400: 回复已被隐藏
            - status: 状态码 (400)
            - message: 错误信息 (string)
        403: 无权限隐藏
            - status: 状态码 (403)
            - message: 错误信息 (string)
        404: 回复不存在
            - status: 状态码 (404)
            - message: 错误信息 (string)
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {
                "id": 1,
                "author": {"id": "user1", "name": "user1", "avatarUrl": null},
                "content": "回复内容",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T02:00:00",
                "is_hidden": true
            }
        }
    """
    try:
        user_id = g.current_user["user_id"]
        is_admin = await _is_admin(user_id)

        # 查询回复用于权限校验（封装模块内实现）
        reply = await MessageBoardDBUtils.get_reply_by_id(reply_id)
        if not reply:
            return response_helper.not_found("回复不存在")

        # 权限校验：只有作者或管理员可以隐藏
        if not is_admin and reply.author_user_name != user_id:
            return response_helper.forbidden("只能隐藏自己发布的评论")

        # 单向不可逆：已隐藏的评论不能再次操作（封装内处理并返回状态）
        reply, already_hidden = await MessageBoardDBUtils.set_reply_hidden(
            reply_id, datetime.utcnow()
        )
        if already_hidden:
            return response_helper.bad_request("该评论已被隐藏，无法重复隐藏")

        data_resp = {
            "id": reply.id,
            "author": _serialize_user_brief(reply.author_user_name),
            "content": reply.content,
            "created_at": (reply.created_at.isoformat() if reply.created_at else None),
            "updated_at": (reply.updated_at.isoformat() if reply.updated_at else None),
            "is_hidden": bool(reply.is_hidden),
        }

        return {"status": 200, "data": data_resp}
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception:
        traceback.print_exc()
        logger.error(f"更新回复隐藏状态失败: {traceback.format_exc()}")
        return response_helper.server_error("更新回复隐藏状态失败")


@api_message_board_bp.route("/admin/auto-close", methods=["POST"])
@auth_required
@role_required(["admin"])
# @validate_response(CardDetailResponse)
async def auto_close_cards():
    """
    管理端触发：自动关闭超过 7 天无回复的 card
    
    自动关闭超过7天无回复的留言卡片。该接口可由定时任务或运维脚本调用。仅管理员可访问。

    Tags:
        - 留言板管理

    Security:
        - Bearer: []

    Responses:
        200: 执行成功
            - status: 状态码 (200)
            - data: 包含affected字段的对象，表示关闭的卡片数量
        500: 服务器错误
            - status: 状态码 (500)
            - message: 错误信息 (string)

    Example Response:
        {
            "status": 200,
            "data": {
                "affected": 5
            }
        }
    """
    try:
        affected = await MessageBoardDBUtils.auto_close_inactive_cards()
        return {"status": 200, "data": {"affected": affected}}
    except KahunaException as e:
        traceback.print_exc()
        return response_helper.fail(str(e), 500)
    except Exception:
        traceback.print_exc()
        logger.error(f"自动关闭留言卡片失败: {traceback.format_exc()}")
        return response_helper.server_error("自动关闭留言卡片失败")
