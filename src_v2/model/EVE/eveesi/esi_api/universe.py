import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import FORBIDDEN_ERROR, get_request_async, OUT_PAGE_ERROR, FORBIDDEN_ERROR
from src_v2.core.utils import tqdm_manager


@esi_request
async def universe_structures_structure(access_token, structure_id: int, log=True):
    """
    name*	string
    owner_id    int32
    position
        x
        y
        z
    solar_system_id
    type_id
    """
    if not isinstance(access_token, str):
        ac_token = await access_token
    else:
        ac_token = access_token
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/universe/structures/{structure_id}/",
                       headers={"Authorization": f"Bearer {ac_token}"}, log=log, no_retry_code=[FORBIDDEN_ERROR])
    return data

@esi_request
async def universe_stations_station(station_id, log=True):
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/universe/stations/{station_id}/", log=log)
    return data