from datetime import datetime, timedelta
from typing import Optional, Iterable

from sqlalchemy import select, func, desc

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

