import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import get_request_async, OUT_PAGE_ERROR
from src_v2.core.utils import tqdm_manager


@esi_request
async def industry_systems(log=True):
    data, _ =  await get_request_async(f"https://esi.evetech.net/latest/industry/systems/", log=log)
    return data

