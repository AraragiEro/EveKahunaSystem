from astrbot.core.star.filter.custom_filter import CustomFilter
from astrbot.api.event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig

from .src.service.user_server.user_manager import UserManager
from datetime import datetime
from .src_v2.core.log import logger
from .src.utils import KahunaException

# import Exception
from .src.utils import (
    get_debug_qq
)

def get_user(event: AstrMessageEvent):
    if get_debug_qq():
        user_qq = get_debug_qq()
    else:
        user_qq = int(event.get_sender_id())

    return user_qq

class MemberFilter(CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        user_qq = get_user(event)
        if UserManager.user_exists(user_qq):
            return True
        else:
            logger.error(f"member filter error: user {user_qq} not exists")
            return False

class VipMemberFilter(CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        user_qq = get_user(event)
        if not UserManager.user_exists(user_qq):
            logger.error(f"vip member filter error: user {user_qq} not exists")
            return False
        user = UserManager().get_user(user_qq)
        if user.expire_date > datetime.now():
            logger.debug(f"vip member filter success: user {user_qq} is vip member")
            return True
        else:
            logger.debug(f"vip member filter error: user {user_qq} is not vip member")
            return False

class AdminFilter(CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return event.is_admin()
