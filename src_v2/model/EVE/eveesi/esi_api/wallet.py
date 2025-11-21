import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import get_request_async, OUT_PAGE_ERROR, parse_token
from src_v2.core.utils import tqdm_manager

# Get a character's wallet balance
# get
# https://esi.evetech.net/characters/{character_id}/wallet
# esi-wallet.read_character_wallet.v1
@esi_request
async def character_character_id_wallet(access_token, character_id, log=True):
    ac_token = await access_token
    data, _, _ = await get_request_async(f"https://esi.evetech.net/latest/characters/{character_id}/wallet/",
                       headers={"Authorization": f"Bearer {ac_token}"}, log=log)
    return data