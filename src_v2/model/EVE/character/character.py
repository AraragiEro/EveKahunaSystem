from typing import Any, Optional

from oauthlib.oauth2 import InvalidClientIdError, InvalidScopeError
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from asyncio import Lock

import traceback

from src_v2.core.database.kahuna_database_utils_v2 import EveAuthedCharacterDBUtils
from src_v2.core.database.model import EveAuthedCharacter as M_EveAuthedCharacter
from ..eveesi.oauth import refresh_token
from ..eveesi import eveesi
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException, get_beijing_utctime


# token 刷新连续失败次数阈值，超过后视为永久失效，不再尝试刷新
MAX_REFRESH_FAILURES = 3


class EveTokenPermanentlyInvalidError(KahunaException):
    """token 已永久失效（连续多次 InvalidGrantError），需要用户重新授权"""
    pass


class Character():
    def __init__(self, character_id: int, character_name: str, owner_user_name: str, birthday: datetime, access_token: str, refresh_token: str, expires_time: datetime, corporation_id: int, director: bool, refresh_failure_count: int = 0, last_refresh_error: Optional[str] = None):
        """
        character_id = Column(Integer, primary_key=True)
            owner_user_name = Column(Text, ForeignKey("user.user_name"))
            character_name = Column(Text, index=True)
            birthday = Column(DateTime)
            access_token = Column(Text)
            refresh_token = Column(Text)
            expires_time = Column(DateTime)
            corporation_id = Column(Integer)
            director = Column(Boolean)
            refresh_failure_count = Column(Integer, default=0)
            last_refresh_error = Column(Text, nullable=True)
        """

        self.character_id = character_id
        self.character_name = character_name
        self.owner_user_name = owner_user_name
        self.birthday = birthday
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.corporation_id = corporation_id
        self.director = director
        self.token_expires_date = expires_time
        self.refresh_failure_count = refresh_failure_count
        self.last_refresh_error = last_refresh_error
        self._refresh_token_lock = Lock()

    async def refresh_character_token(self):
        """刷新 ESI token。

        - 成功：重置 failure_count，清除 last_refresh_error
        - InvalidGrantError（token 已撤销/过期）：递增 failure_count，记录错误
        - 其他错误（网络等）：仅记录错误，不递增计数
        """
        token_state = await EveAuthedCharacterDBUtils.select_character_by_character_id(self.character_id)
        try:
            refresh_res_dict = await refresh_token(token_state.refresh_token)
            logger.info(f"{self.character_name} token refreshed.")
        except InvalidGrantError as e:
            # token 永久失效（用户撤销授权/改密码等），递增失败计数
            new_count = (token_state.refresh_failure_count or 0) + 1
            error_msg = f"InvalidGrantError: {str(e)}"
            token_state.refresh_failure_count = new_count
            token_state.last_refresh_error = error_msg
            await EveAuthedCharacterDBUtils.merge(token_state)
            self.refresh_failure_count = new_count
            self.last_refresh_error = error_msg

            if new_count >= MAX_REFRESH_FAILURES:
                logger.error(
                    f"[{self.character_name}][{self.character_id}] token 已永久失效（连续 {new_count} 次 InvalidGrantError），"
                    f"将停止自动刷新，需要用户重新授权。错误: {str(e)}",
                    exc_info=True
                )
                raise EveTokenPermanentlyInvalidError(
                    f"{self.character_name} 角色token已失效（连续{new_count}次刷新失败），请重新授权"
                )
            else:
                logger.error(
                    f"[{self.character_name}][{self.character_id}] token refresh failed ({new_count}/{MAX_REFRESH_FAILURES}): "
                    f"InvalidGrantError: {str(e)}",
                    exc_info=True
                )
                raise KahunaException(f"{self.character_name} 角色token获取失败，请重新授权")
        except Exception as e:
            # 网络错误等临时故障，记录但不递增 permanent failure 计数
            error_msg = f"{type(e).__name__}: {str(e)}"
            token_state.last_refresh_error = error_msg
            await EveAuthedCharacterDBUtils.merge(token_state)
            self.last_refresh_error = error_msg

            logger.error(f"[{self.character_name}][{self.character_id}] token refresh failed: {type(e).__name__}: {str(e)}", exc_info=True)
            raise KahunaException(f"{self.character_name} 角色token获取失败，请重新授权")

        if refresh_res_dict:
            # 刷新成功，重置失败计数
            token_state.access_token = refresh_res_dict['access_token']
            token_state.refresh_token = refresh_res_dict['refresh_token']
            token_state.expires_time = datetime.fromtimestamp(refresh_res_dict["expires_at"]).astimezone(timezone(timedelta(hours=+8), 'Shanghai')).replace(tzinfo=None)
            token_state.refresh_failure_count = 0
            token_state.last_refresh_error = None

            character_roles = await eveesi.characters_character_roles(token_state.access_token, self.character_id)
            director_status = "Director" in character_roles['roles'] if 'roles' in character_roles else None
            if director_status != token_state.director:
                token_state.director = director_status
            await EveAuthedCharacterDBUtils.merge(token_state)

            self.access_token = token_state.access_token
            self.refresh_token = token_state.refresh_token
            self.token_expires_date = token_state.expires_time
            self.director = token_state.director
            self.refresh_failure_count = 0
            self.last_refresh_error = None

    @classmethod
    def from_db_obj(cls, db_obj: M_EveAuthedCharacter):
        return cls(
            character_id=db_obj.character_id,
            character_name=db_obj.character_name,
            owner_user_name=db_obj.owner_user_name,
            birthday=db_obj.birthday,
            access_token=db_obj.access_token,
            refresh_token=db_obj.refresh_token,
            expires_time=db_obj.expires_time,
            corporation_id=db_obj.corporation_id,
            director=db_obj.director,
            refresh_failure_count=db_obj.refresh_failure_count or 0,
            last_refresh_error=db_obj.last_refresh_error)

    @property
    def token_permanently_failed(self) -> bool:
        """token 是否已永久失效（连续 InvalidGrantError 超过阈值）"""
        return (self.refresh_failure_count or 0) >= MAX_REFRESH_FAILURES

    @property
    async def ac_token(self):
        async with self._refresh_token_lock:
            if self.token_permanently_failed:
                # 已永久失效，不再尝试刷新
                raise EveTokenPermanentlyInvalidError(
                    f"{self.character_name} 角色token已永久失效，请重新授权"
                )
            if not self.token_avaliable:
                await self.refresh_character_token()
        token_statues = await EveAuthedCharacterDBUtils.select_character_by_character_id(self.character_id)
        return token_statues.access_token

    @property
    def token_avaliable(self):
        # 获取当前时间
        current = get_beijing_utctime(datetime.now())

        # 添加15分钟缓冲并移除时区信息
        now = (current + timedelta(minutes=5)).replace(tzinfo=None)

        logger.debug(f"check if {self.token_expires_date} > {now} = {self.token_expires_date > now}")
        return self.token_expires_date > now

    async def refresh_wallet_balance(self):
        wallet_balance = await eveesi.character_character_id_wallet(self.ac_token, self.character_id)
        if wallet_balance is not None:
            self.wallet_balance = wallet_balance
        else:
            logger.error("刷新钱包余额失败")
