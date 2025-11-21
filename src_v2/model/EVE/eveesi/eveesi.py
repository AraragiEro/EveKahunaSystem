import asyncio

# kahuna logger
from src_v2.core.log import logger
from .esi_req_manager import esi_request

from .esi_api.character import *
from .esi_api.market import *
from .esi_api.corporation import *
from .esi_api.industry import *
from .esi_api.universe import *
from .esi_api.search import *
from .esi_api.assets import *

permission_set = set()

@esi_request
async def verify_token(access_token, log=True):
    data, _, _ = await get_request_async("https://esi.evetech.net/verify/", headers={"Authorization": f"Bearer {access_token}"}, log=log)
    return data
