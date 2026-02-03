import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from quart import Blueprint, g, jsonify, request
from sqlalchemy import and_, desc, func, or_, select

from src_v2.backend.api.permission_required import role_required
from src_v2.backend.auth import auth_required
from src_v2.core.database import model
from src_v2.core.database.kahuna_database_utils_v2 import get_postgres_manager
from src_v2.core.database.message_board_utils import MessageBoardDBUtils
from src_v2.core.log import logger
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.utils import KahunaException

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

        async with get_postgres_manager().get_session() as session:
            is_admin = await _is_admin(user_id)

            stmt = select(model.MessageCard)

            # 隐藏状态过滤：如果卡片被隐藏，只有发布者或管理员可见
            if not is_admin:
                if mine:
                    # 如果勾选了"我创建的"，只显示自己创建的留言（包括隐藏和未隐藏的）
                    stmt = stmt.where(
                        model.MessageCard.author_user_name == user_id)
                else:
                    # 默认情况：显示所有未隐藏的卡片，或者自己发布的隐藏卡片
                    # 即：所有人的未隐藏留言 + 属于自己的已隐藏留言
                    # 注意：使用 is_(False) 和 is_(None) 来正确处理 NULL 值
                    stmt = stmt.where(
                        or_(
                            model.MessageCard.is_hidden.is_(False),
                            model.MessageCard.is_hidden.is_(None),
                            model.MessageCard.author_user_name == user_id
                        )
                    )
            else:
                # 管理员：如果 show_hidden=true，只显示隐藏的卡片；否则显示所有卡片
                if show_hidden:
                    stmt = stmt.where(model.MessageCard.is_hidden == True)  # noqa: E712
                # 如果 show_hidden=false，不添加过滤条件，显示所有卡片
                # 如果勾选了"我创建的"，添加作者过滤
                if mine:
                    stmt = stmt.where(
                        model.MessageCard.author_user_name == user_id)

            # 状态
            if status_list:
                stmt = stmt.where(model.MessageCard.status.in_(status_list))

            # 类型
            if type_list:
                stmt = stmt.where(model.MessageCard.type.in_(type_list))

            # 创建时间范围
            if created_from:
                try:
                    dt_from = datetime.fromisoformat(created_from)
                    stmt = stmt.where(model.MessageCard.created_at >= dt_from)
                except ValueError:
                    pass
            if created_to:
                try:
                    dt_to = datetime.fromisoformat(created_to)
                    stmt = stmt.where(model.MessageCard.created_at <= dt_to)
                except ValueError:
                    pass

            # 我回复过的
            if participated:
                # 通过回复表 join
                reply_subq = (
                    select(model.MessageReply.card_id)
                    .where(model.MessageReply.author_user_name == user_id)
                    .distinct()
                )
                stmt = stmt.where(model.MessageCard.id.in_(reply_subq))

            # 发布人搜索（这里用 user_name 模糊匹配）
            if publisher_search:
                like_pattern = f"%{publisher_search}%"
                stmt = stmt.where(
                    model.MessageCard.author_user_name.ilike(like_pattern))

            # 排序
            if order_by == "created_at":
                order_column = model.MessageCard.created_at
            else:
                # 默认按 last_reply_at 排序，空值时可退化为 created_at
                order_column = func.coalesce(
                    model.MessageCard.last_reply_at, model.MessageCard.created_at)
            order_fn = desc if order.lower() == "desc" else lambda c: c
            stmt = stmt.order_by(order_fn(order_column))

            # 统计总数
            count_stmt = select(func.count()).select_from(stmt.subquery())
            count_result = await session.execute(count_stmt)
            total = count_result.scalar() or 0

            # 分页
            stmt = stmt.offset(offset).limit(page_size)
            result = await session.execute(stmt)
            cards = result.scalars().all()

            items = []
            if cards:
                # 预查询每个 card 的回复数与最后回复人
                card_ids = [c.id for c in cards]
                # 回复数
                count_reply_stmt = (
                    select(
                        model.MessageReply.card_id,
                        func.count().label("reply_count"),
                        func.max(model.MessageReply.created_at).label(
                            "last_reply_at"),
                    )
                    .where(model.MessageReply.card_id.in_(card_ids))
                    .where(model.MessageReply.is_deleted == False)  # noqa: E712
                    .group_by(model.MessageReply.card_id)
                )
                reply_count_result = await session.execute(count_reply_stmt)
                reply_map = {
                    row.card_id: {
                        "reply_count": row.reply_count,
                        "last_reply_at": row.last_reply_at,
                    }
                    for row in reply_count_result
                }

                for card in cards:
                    reply_info = reply_map.get(card.id, {})
                    last_reply_at = card.last_reply_at or reply_info.get(
                        "last_reply_at") or card.created_at
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
                            "reply_count": reply_info.get("reply_count", 0),
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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception:
        traceback.print_exc()
        logger.error(f"获取留言卡片列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取留言卡片列表失败"}), 500


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
            return jsonify({"status": 400, "message": "type 必须为 bug/feat/chat"}), 400
        if not title:
            return jsonify({"status": 400, "message": "标题不能为空"}), 400
        if not content:
            return jsonify({"status": 400, "message": "内容不能为空"}), 400

        is_admin = await _is_admin(user_id)
        # 频率限制
        err = await _check_rate_limit(user_id, is_admin)
        if err:
            return jsonify({"status": 429, "message": err, "code": "RATE_LIMIT"}), 429

        now = datetime.utcnow()
        status = "in_progress" if card_type == "chat" else "created"

        async with get_postgres_manager().get_session() as session:
            card = model.MessageCard(
                author_user_name=user_id,
                type=card_type,
                status=status,
                title=title,
                content=content,
                created_at=now,
                updated_at=now,
                last_reply_at=now,
            )
            session.add(card)
            await session.flush()

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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception:
        traceback.print_exc()
        logger.error(f"创建留言卡片失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建留言卡片失败"}), 500


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

        async with get_postgres_manager().get_session() as session:
            stmt = select(model.MessageCard).where(
                model.MessageCard.id == card_id)
            result = await session.execute(stmt)
            card = result.scalars().first()
            if not card:
                return jsonify({"status": 404, "message": "留言卡片不存在"}), 404

            # 检查隐藏权限：如果卡片被隐藏且当前用户不是发布者也不是管理员，返回404
            if card.is_hidden and not is_admin and card.author_user_name != user_id:
                return jsonify({"status": 404, "message": "留言卡片不存在"}), 404

            # 统计回复数
            reply_count_stmt = (
                select(func.count())
                .where(model.MessageReply.card_id == card.id)
                .where(model.MessageReply.is_deleted == False)  # noqa: E712
            )
            reply_count_res = await session.execute(reply_count_stmt)
            reply_count = reply_count_res.scalar() or 0

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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception:
        traceback.print_exc()
        logger.error(f"获取留言卡片详情失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取留言卡片详情失败"}), 500


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

        async with get_postgres_manager().get_session() as session:
            # 确保 card 存在
            card_stmt = select(model.MessageCard.id).where(
                model.MessageCard.id == card_id)
            card_res = await session.execute(card_stmt)
            if not card_res.scalar():
                return jsonify({"status": 404, "message": "留言卡片不存在"}), 404

            base_stmt = (
                select(model.MessageReply)
                .where(model.MessageReply.card_id == card_id)
                .where(model.MessageReply.is_deleted == False)  # noqa: E712
            )

            # 隐藏回复过滤：普通用户看不到他人隐藏的回复
            if not is_admin:
                base_stmt = base_stmt.where(
                    or_(
                        model.MessageReply.is_hidden.is_(False),
                        model.MessageReply.is_hidden.is_(None),
                        model.MessageReply.author_user_name == user_id,
                    )
                )

            # 统计总数
            count_stmt = select(func.count()).select_from(base_stmt.subquery())
            count_res = await session.execute(count_stmt)
            total = count_res.scalar() or 0

            stmt = base_stmt.order_by(model.MessageReply.created_at.asc()).offset(
                offset).limit(page_size)
            result = await session.execute(stmt)
            replies = result.scalars().all()

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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception:
        traceback.print_exc()
        logger.error(f"获取留言回复列表失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "获取留言回复列表失败"}), 500


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
            return jsonify({"status": 400, "message": "回复内容不能为空"}), 400

        is_admin = await _is_admin(user_id)

        async with get_postgres_manager().get_session() as session:
            # 检查 card
            card_stmt = select(model.MessageCard).where(
                model.MessageCard.id == card_id)
            card_res = await session.execute(card_stmt)
            card = card_res.scalars().first()
            if not card:
                return jsonify({"status": 404, "message": "留言卡片不存在"}), 404
            if card.status == "closed":
                return jsonify({"status": 400, "message": "该留言已关闭，无法继续回复", "code": "CARD_CLOSED"}), 400

            # 频率限制
            err = await _check_rate_limit(user_id, is_admin)
            if err:
                return jsonify({"status": 429, "message": err, "code": "RATE_LIMIT"}), 429

            now = datetime.utcnow()
            reply = model.MessageReply(
                card_id=card.id,
                author_user_name=user_id,
                content=content,
                created_at=now,
                updated_at=now,
                is_deleted=False,
            )
            session.add(reply)

            # 更新 card 的 last_reply_at / last_reply_user_name / updated_at
            card.last_reply_at = now
            card.last_reply_user_name = user_id
            card.updated_at = now
            await session.flush()

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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception:
        traceback.print_exc()
        logger.error(f"创建留言回复失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "创建留言回复失败"}), 500


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

        async with get_postgres_manager().get_session() as session:
            stmt = select(model.MessageCard).where(
                model.MessageCard.id == card_id)
            res = await session.execute(stmt)
            card = res.scalars().first()
            if not card:
                return jsonify({"status": 404, "message": "留言卡片不存在"}), 404

            now = datetime.utcnow()

            if not is_admin:
                # 允许作者关闭自己的卡片
                if new_status and new_status == "closed":
                    if card.author_user_name != user_id:
                        return jsonify({"status": 403, "message": "只能关闭自己创建的卡片"}), 403
                    card.status = "closed"
                    card.closed_at = now
                    card.closed_by = user_id
                    card.updated_at = now
                # 允许作者修改自己卡片的类型
                elif new_type is not None:
                    if card.author_user_name != user_id:
                        return jsonify({"status": 403, "message": "只能修改自己创建的卡片"}), 403
                    if new_type not in ("bug", "feat", "chat"):
                        return jsonify({"status": 400, "message": "非法类型值"}), 400
                    card.type = new_type
                    card.updated_at = now
                else:
                    return jsonify({"status": 403, "message": "无权限修改状态或内容"}), 403
            else:
                # 管理员可以更新状态与内容
                if new_status:
                    if new_status not in ("created", "in_progress", "closed"):
                        return jsonify({"status": 400, "message": "非法状态值"}), 400
                    card.status = new_status
                    if new_status == "closed":
                        card.closed_at = now
                        card.closed_by = user_id
                if new_title is not None:
                    card.title = new_title
                if new_content is not None:
                    card.content = new_content
                if new_type is not None:
                    if new_type not in ("bug", "feat", "chat"):
                        return jsonify({"status": 400, "message": "非法类型值"}), 400
                    card.type = new_type
                card.updated_at = now

            await session.flush()

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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception:
        traceback.print_exc()
        logger.error(f"更新留言卡片失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "更新留言卡片失败"}), 500


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

        async with get_postgres_manager().get_session() as session:
            stmt = select(model.MessageCard).where(
                model.MessageCard.id == card_id)
            res = await session.execute(stmt)
            card = res.scalars().first()
            if not card:
                return jsonify({"status": 404, "message": "留言卡片不存在"}), 404

            # 权限校验：只有作者或管理员可以隐藏
            if not is_admin and card.author_user_name != user_id:
                return jsonify({"status": 403, "message": "只能隐藏自己创建的卡片"}), 403

            # 单向不可逆：已隐藏的卡片不能再次操作
            if card.is_hidden:
                return jsonify({"status": 400, "message": "该卡片已被隐藏，无法重复隐藏"}), 400

            card.is_hidden = True
            card.updated_at = datetime.utcnow()
            await session.flush()

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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception:
        traceback.print_exc()
        logger.error(f"更新卡片隐藏状态失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "更新卡片隐藏状态失败"}), 500


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

        async with get_postgres_manager().get_session() as session:
            stmt = select(model.MessageReply).where(
                model.MessageReply.id == reply_id)
            res = await session.execute(stmt)
            reply = res.scalars().first()
            if not reply:
                return jsonify({"status": 404, "message": "回复不存在"}), 404

            # 权限校验：只有作者或管理员可以隐藏
            if not is_admin and reply.author_user_name != user_id:
                return jsonify({"status": 403, "message": "只能隐藏自己发布的评论"}), 403

            # 单向不可逆：已隐藏的评论不能再次操作
            if reply.is_hidden:
                return jsonify({"status": 400, "message": "该评论已被隐藏，无法重复隐藏"}), 400

            reply.is_hidden = True
            reply.updated_at = datetime.utcnow()
            await session.flush()

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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception:
        traceback.print_exc()
        logger.error(f"更新回复隐藏状态失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "更新回复隐藏状态失败"}), 500


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
        return jsonify({"status": 500, "message": str(e)}), 500
    except Exception:
        traceback.print_exc()
        logger.error(f"自动关闭留言卡片失败: {traceback.format_exc()}")
        return jsonify({"status": 500, "message": "自动关闭留言卡片失败"}), 500
