import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import get_request_async, OUT_PAGE_ERROR, parse_token
from src_v2.core.utils import tqdm_manager

# Get character skills
# get
# https://esi.evetech.net/characters/{character_id}/skills
# esi-skills.read_skills.v1
@esi_request
async def character_character_id_skills(access_token, character_id, log=True):
    ac_token = await access_token
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/characters/{character_id}/skills/",
                       headers={"Authorization": f"Bearer {ac_token}"}, log=log)
    return data