from typing import Any

from oauthlib.oauth2 import InvalidClientIdError, InvalidScopeError
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from asyncio import Lock

import traceback

from ..database_server.sqlalchemy.kahuna_database_utils import CharacterDBUtils
from ..evesso_server.oauth import refresh_token
from ..evesso_server import eveesi
from ..log_server import logger
from ...utils import KahunaException, get_beijing_utctime


class Character(BaseModel):
    character_id: int
    character_name: str
    QQ: int
    create_date: datetime
    token: str
    refresh_token: str
    expires_date: datetime
    corp_id: int
    director: bool = False
    _wallet_balance: float = 0.0

    def model_post_init(self, __context: Any) -> None:
        self._refresh_token_lock = Lock()

    @staticmethod
    async def get_all_characters():
        return await CharacterDBUtils.select_all()

    async def get_from_db(self):
        return await CharacterDBUtils.select_character_by_character_id(self.character_id)

    async def insert_to_db(self):
        obj = await self.get_from_db()
        if not obj:
            obj = CharacterDBUtils.get_obj()

        obj.character_id = self.character_id
        obj.character_name = self.character_name
        obj.QQ = self.QQ
        obj.create_date = self.create_date
        obj.token = self.token
        obj.refresh_token = self.refresh_token
        obj.expires_date = self.expires_date
        obj.corp_id = self.corp_id
        obj.director = self.director

        await CharacterDBUtils.save_obj(obj)

    async def refresh_character_token(self):
        try:
            refresh_res_dict = refresh_token(self.refresh_token)
            logger.info(f"{self.character_name} token refreshed.")
        except (InvalidClientIdError, InvalidScopeError) as e:
            logger.error(f"Caught an exception: {type(e).__name__}, message: {str(e)}")
            raise KahunaException(f"QQ:{self.QQ}: {self.character_name} failed to refresh token")
        if refresh_res_dict:
            self.token = refresh_res_dict['access_token']
            self.refresh_token = refresh_res_dict['refresh_token']
            self.expires_date = datetime.fromtimestamp(refresh_res_dict['expires_at'])
            self.expires_date = self.expires_date.astimezone(timezone(timedelta(hours=+8), 'Shanghai'))

        await self.insert_to_db()

    @property
    async def ac_token(self):
        async with self._refresh_token_lock:
            if not self.token_avaliable:
                await self.refresh_character_token()
        return self.token

    @property
    async def wallet_balance(self):
        if self._wallet_balance == 0.0:
            await self.refresh_wallet_balance()
        return self._wallet_balance
    @wallet_balance.setter
    def wallet_balance(self, value):
        self._wallet_balance = value

    @property
    def token_avaliable(self):
        expire_time = self.expires_date.replace(tzinfo=None)
        # 获取当前时间
        current = get_beijing_utctime(datetime.now())

        # 添加15分钟缓冲并移除时区信息
        now = (current + timedelta(minutes=5)).replace(tzinfo=None)

        logger.debug(f"check if {expire_time} > {now} = {expire_time > now}")
        return expire_time > now

    async def refresh_wallet_balance(self):
        wallet_balance = await eveesi.character_character_id_wallet(self.ac_token, self.character_id)
        if wallet_balance is not None:
            self.wallet_balance = wallet_balance
        else:
            logger.error("刷新钱包余额失败")

    @property
    async def info(self):
        return f"角色:{self.character_name}\n"\
                f"所属用户:{self.QQ}\n"\
                f"角色id:{self.character_id}\n"\
                f"钱包:{await self.wallet_balance:,.2f\n}" \
                f"token过期时间:{self.expires_date}\n"

