from typing import Any

from oauthlib.oauth2 import InvalidClientIdError, InvalidScopeError
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from asyncio import Lock

import traceback

from src_v2.core.database.kahuna_database_utils_v2 import EveAuthedCharacterDBUtils
from src_v2.core.database.model import EveAuthedCharacter as M_EveAuthedCharacter
from src_v2.core.database.connect_manager import redis_manager
from ..eveesi.oauth import refresh_token
from ..eveesi import eveesi
from ..eveesi.eveutils import parse_iso_datetime
from src_v2.core.log import logger
from src_v2.core.utils import KahunaException, get_beijing_utctime


class Character():
    def __init__(self, character_id: int, character_name: str, owner_user_name: str, birthday: datetime, access_token: str, refresh_token: str, expires_time: datetime, corporation_id: int, director: bool):
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
        self._refresh_token_lock = Lock()

    async def refresh_character_token(self):
        token_state = await EveAuthedCharacterDBUtils.select_character_by_character_id(self.character_id)
        try:
            refresh_res_dict = refresh_token(token_state.refresh_token)
            logger.info(f"{self.character_name} token refreshed.")
        except (InvalidClientIdError, InvalidScopeError) as e:
            logger.error(f"Caught an exception: {type(e).__name__}, message: {str(e)}")
            raise KahunaException(f"{self.character_name} 角色token获取失败，请重新授权")
        if refresh_res_dict:
            token_state.access_token = refresh_res_dict['access_token']
            token_state.refresh_token = refresh_res_dict['refresh_token']
            token_state.expires_time = datetime.fromtimestamp(refresh_res_dict["expires_at"]).astimezone(timezone(timedelta(hours=+8), 'Shanghai')).replace(tzinfo=None)
            
            character_roles = await eveesi.characters_character_roles(token_state.access_token, self.character_id)
            director_status = "Director" in character_roles['roles'] if 'roles' in character_roles else None
            if director_status != token_state.director:
                token_state.director = director_status
            await EveAuthedCharacterDBUtils.merge(token_state)

            self.access_token = token_state.access_token
            self.refresh_token = token_state.refresh_token
            self.token_expires_date = token_state.expires_time
            self.director = token_state.director

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
            director=db_obj.director)

    @property
    async def ac_token(self):
        async with self._refresh_token_lock:
            if not self.token_avaliable:
                await self.refresh_character_token()
        token_statues = await EveAuthedCharacterDBUtils.select_character_by_character_id(self.character_id)
        return token_statues.access_token

    # @property
    # async def wallet_balance(self):
    #     if self._wallet_balance == 0.0:
    #         await self.refresh_wallet_balance()
    #     return self._wallet_balance

    # @wallet_balance.setter
    # def wallet_balance(self, value):
    #     self._wallet_balance = value

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

    # @property
    # async def info(self):
    #     return f"角色:{self.character_name}\n"\
    #             f"所属用户:{self.QQ}\n"\
    #             f"角色id:{self.character_id}\n"\
    #             f"钱包:{await self.wallet_balance:,.2f\n}" \
    #             f"token过期时间:{self.token_expires_date}\n"

