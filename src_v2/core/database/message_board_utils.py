from datetime import datetime, timedelta
from typing import Optional, Iterable

from sqlalchemy import select, func, desc, or_

from .kahuna_database_utils_v2 import get_postgres_manager
from . import model


class MessageBoardDBUtils:
    """
    留言板相关的数据库工具函数
    """

    @staticmethod
    async def get_latest_message_time(user_name: str) -> Optional[datetime]:
        """
        获取用户最近一次发送 card 或 reply 的时间
        """
        async with get_postgres_manager().get_session() as session:
            # 最近 card
            card_stmt = (
                select(func.max(model.MessageCard.created_at))
                .where(model.MessageCard.author_user_name == user_name)
            )
            # 最近 reply
            reply_stmt = (
                select(func.max(model.MessageReply.created_at))
                .where(model.MessageReply.author_user_name == user_name)
            )

            card_result = await session.execute(card_stmt)
            reply_result = await session.execute(reply_stmt)

            latest_card = card_result.scalar()
            latest_reply = reply_result.scalar()

            if latest_card and latest_reply:
                return latest_card if latest_card >= latest_reply else latest_reply
            return latest_card or latest_reply

    @staticmethod
    async def auto_close_inactive_cards(now: Optional[datetime] = None, days: int = 7) -> int:
        """
        自动关闭超过指定天数未回复的留言卡片

        Returns:
            受影响的行数
        """
        from sqlalchemy import update

        now = now or datetime.utcnow()
        threshold = now - timedelta(days=days)

        async with get_postgres_manager().get_session() as session:
            # last_reply_at 为空时，使用 created_at 作为参考
            effective_last_reply = func.coalesce(model.MessageCard.last_reply_at, model.MessageCard.created_at)

            stmt = (
                update(model.MessageCard)
                .where(model.MessageCard.status != "closed")
                .where(effective_last_reply < threshold)
                .values(
                    status="closed",
                    auto_closed=True,
                    closed_at=now,
                )
            )
            result = await session.execute(stmt)
            # SQLAlchemy 2.x: rowcount 在异步执行结果上可用
            return result.rowcount or 0

    # ============ 第一批问题点2 合规修复新增封装（api_message_board.py 8 处下沉） ============

    @staticmethod
    async def search_cards(
        user_id: str,
        is_admin: bool,
        *,
        status_list=None,
        type_list=None,
        created_from=None,
        created_to=None,
        mine: bool = False,
        participated: bool = False,
        publisher_search: str = "",
        order_by: str = "last_reply_at",
        order: str = "desc",
        show_hidden: bool = False,
        offset: int = 0,
        page_size: int = 20,
    ) -> tuple[list, int]:
        """留言卡片列表查询（含权限过滤/状态/类型/时间/参与/发布人搜索/排序/分页/回复数聚合）。

        对应 api_message_board.py:292 的整个查询块。权限判定由调用方传入 is_admin（归属校验在 API 层）。

        Args:
            user_id: 当前用户ID（用于"我创建的/我回复过的/隐藏可见性"过滤）
            is_admin: 是否管理员
            status_list: 状态筛选列表（如 ["created", "in_progress"]）
            type_list: 类型筛选列表（如 ["bug", "feat", "chat"]）
            created_from: 创建时间起始（ISO 字符串，可空）
            created_to: 创建时间结束（ISO 字符串，可空）
            mine: 是否只显示我创建的
            participated: 是否只显示我回复过的
            publisher_search: 发布人模糊搜索关键字
            order_by: 排序字段（created_at / last_reply_at）
            order: 排序方向（asc / desc）
            show_hidden: 管理员专用，是否只显示隐藏的卡片
            offset: 分页偏移
            page_size: 每页数量

        Returns:
            (cards, total)：cards 为当前页 MessageCard 对象列表（附 reply_count/last_reply 聚合信息），
            total 为过滤后的总数量。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(model.MessageCard)

            # 隐藏状态过滤：如果卡片被隐藏，只有发布者或管理员可见
            if not is_admin:
                if mine:
                    # 如果勾选了"我创建的"，只显示自己创建的留言（包括隐藏和未隐藏的）
                    stmt = stmt.where(
                        model.MessageCard.author_user_name == user_id)
                else:
                    # 默认情况：显示所有未隐藏的卡片，或者自己发布的隐藏卡片
                    stmt = stmt.where(
                        or_(
                            model.MessageCard.is_hidden.is_(False),
                            model.MessageCard.is_hidden.is_(None),
                            model.MessageCard.author_user_name == user_id,
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

            # 预查询每个 card 的回复数（聚合信息附加到对象属性，供 API 序列化）
            if cards:
                card_ids = [c.id for c in cards]
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
                    card.reply_count = reply_info.get("reply_count", 0)
                    card.last_reply_at_from_reply = reply_info.get(
                        "last_reply_at")

            return list(cards), total

    @staticmethod
    async def create_card(
        user_id: str,
        card_type: str,
        status: str,
        title: str,
        content: str,
        now,
    ) -> "model.MessageCard":
        """创建留言卡片并 flush，返回带 id 的对象。

        对应 api_message_board.py:542 的创建逻辑。
        """
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
            return card

    @staticmethod
    async def get_card_by_id(card_id: int) -> Optional["model.MessageCard"]:
        """按 id 查卡片单条。

        对应 api_message_board.py:632/883/1010/1143 的卡片查询。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(model.MessageCard).where(
                model.MessageCard.id == card_id)
            result = await session.execute(stmt)
            return result.scalars().first()

    @staticmethod
    async def get_reply_count(card_id: int) -> int:
        """统计卡片有效回复数（is_deleted=False）。

        对应 api_message_board.py:650 的回复数统计查询。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = (
                select(func.count())
                .where(model.MessageReply.card_id == card_id)
                .where(model.MessageReply.is_deleted == False)  # noqa: E712
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    @staticmethod
    async def get_reply_by_id(reply_id: int) -> Optional["model.MessageReply"]:
        """按 id 查回复单条。

        对应 api_message_board.py:1241 的回复查询（用于隐藏前的权限校验）。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(model.MessageReply).where(
                model.MessageReply.id == reply_id)
            result = await session.execute(stmt)
            return result.scalars().first()

    @staticmethod
    async def search_replies(
        card_id: int,
        is_admin: bool,
        user_id: str,
        offset: int,
        page_size: int,
    ) -> tuple[Optional[list], int]:
        """回复列表查询（含隐藏过滤/分页/总数）。

        对应 api_message_board.py:743 的整个查询块。

        Returns:
            (replies, total)：卡片不存在时返回 (None, 0)；否则返回当前页回复对象列表与总数。
        """
        async with get_postgres_manager().get_session() as session:
            # 确保 card 存在
            card_stmt = select(model.MessageCard.id).where(
                model.MessageCard.id == card_id)
            card_res = await session.execute(card_stmt)
            if not card_res.scalar():
                return None, 0

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

            return list(replies), total

    @staticmethod
    async def create_reply(
        card_id: int,
        author_user_name: str,
        content: str,
        now,
        is_admin: bool,
    ) -> tuple[Optional["model.MessageReply"], Optional[str]]:
        """创建回复并同步更新卡片 last_reply_at/last_reply_user_name/updated_at。

        对应 api_message_board.py:883 的整个创建逻辑。

        Args:
            card_id: 卡片ID
            author_user_name: 回复作者用户名
            content: 回复内容
            now: 当前时间（datetime）
            is_admin: 是否管理员（频率限制判定在 API 层，此处保留签名）

        Returns:
            (reply, error_code)：成功 (reply, None)；卡片不存在 (None, "not_found")；
            卡片已关闭 (None, "CARD_CLOSED")。
        """
        async with get_postgres_manager().get_session() as session:
            # 检查 card
            card_stmt = select(model.MessageCard).where(
                model.MessageCard.id == card_id)
            card_res = await session.execute(card_stmt)
            card = card_res.scalars().first()
            if not card:
                return None, "not_found"
            if card.status == "closed":
                return None, "CARD_CLOSED"

            reply = model.MessageReply(
                card_id=card.id,
                author_user_name=author_user_name,
                content=content,
                created_at=now,
                updated_at=now,
                is_deleted=False,
            )
            session.add(reply)

            # 更新 card 的 last_reply_at / last_reply_user_name / updated_at
            card.last_reply_at = now
            card.last_reply_user_name = author_user_name
            card.updated_at = now
            await session.flush()

            return reply, None

    @staticmethod
    async def update_card_fields(
        card_id: int,
        *,
        new_status=None,
        new_title=None,
        new_content=None,
        new_type=None,
        closed_by=None,
        closed_at=None,
        now,
    ) -> Optional["model.MessageCard"]:
        """按字段更新卡片（仅更新传入的非 None 字段），返回更新后的卡片，不存在返回 None。

        对应 api_message_board.py:1010 的更新逻辑（权限校验在 API 层）。

        Args:
            card_id: 卡片ID
            new_status: 新状态（created / in_progress / closed）
            new_title: 新标题
            new_content: 新内容
            new_type: 新类型（bug / feat / chat）
            closed_by: 关闭人（状态为 closed 时设置）
            closed_at: 关闭时间（状态为 closed 时设置）
            now: 当前时间（datetime）
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(model.MessageCard).where(
                model.MessageCard.id == card_id)
            res = await session.execute(stmt)
            card = res.scalars().first()
            if not card:
                return None

            if new_status is not None:
                card.status = new_status
                if new_status == "closed":
                    card.closed_at = closed_at
                    card.closed_by = closed_by
            if new_title is not None:
                card.title = new_title
            if new_content is not None:
                card.content = new_content
            if new_type is not None:
                card.type = new_type
            card.updated_at = now
            await session.flush()
            return card

    @staticmethod
    async def set_card_hidden(
        card_id: int, now
    ) -> tuple[Optional["model.MessageCard"], bool]:
        """置卡片隐藏（单向不可逆），返回 (card, already_hidden)。

        对应 api_message_board.py:1143 的隐藏逻辑（权限校验在 API 层）。

        Returns:
            (card, already_hidden)：卡片不存在 (None, False)；
            已隐藏 (card, True)（调用方应返回 400「该卡片已被隐藏」）；
            隐藏成功 (card, False)。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(model.MessageCard).where(
                model.MessageCard.id == card_id)
            res = await session.execute(stmt)
            card = res.scalars().first()
            if not card:
                return None, False

            # 单向不可逆：已隐藏的卡片不能再次操作
            if card.is_hidden:
                return card, True

            card.is_hidden = True
            card.updated_at = now
            await session.flush()
            return card, False

    @staticmethod
    async def set_reply_hidden(
        reply_id: int, now
    ) -> tuple[Optional["model.MessageReply"], bool]:
        """置回复隐藏（单向不可逆），返回 (reply, already_hidden)。

        对应 api_message_board.py:1241 的隐藏逻辑（权限校验在 API 层）。

        Returns:
            (reply, already_hidden)：回复不存在 (None, False)；
            已隐藏 (reply, True)（调用方应返回 400「该评论已被隐藏」）；
            隐藏成功 (reply, False)。
        """
        async with get_postgres_manager().get_session() as session:
            stmt = select(model.MessageReply).where(
                model.MessageReply.id == reply_id)
            res = await session.execute(stmt)
            reply = res.scalars().first()
            if not reply:
                return None, False

            # 单向不可逆：已隐藏的评论不能再次操作
            if reply.is_hidden:
                return reply, True

            reply.is_hidden = True
            reply.updated_at = now
            await session.flush()
            return reply, False

