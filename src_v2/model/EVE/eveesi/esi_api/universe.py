import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import FORBIDDEN_ERROR, get_request_async, OUT_PAGE_ERROR, FORBIDDEN_ERROR
from src_v2.core.utils import tqdm_manager
from src_v2.core.log import logger

# Get structure information
# get
# https://esi.evetech.net/universe/structures/{structure_id}
# esi-universe.read_structures.v1
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
    if structure_id < 10000000:
        logger.warning(f"建筑id不会小于10000000，{structure_id} 可能为空间站id")
        return None
    if not isinstance(access_token, str):
        ac_token = await access_token
    else:
        ac_token = access_token
    data, _, _ = await get_request_async(f"https://esi.evetech.net/universe/structures/{structure_id}/",
                       headers={"Authorization": f"Bearer {ac_token}"}, log=log, no_retry_code=[FORBIDDEN_ERROR])
    return data

# Get station information
# get
# https://esi.evetech.net/universe/stations/{station_id}
@esi_request
async def universe_stations_station(station_id, log=True):
    data, _, _ = await get_request_async(f"https://esi.evetech.net/latest/universe/stations/{station_id}/", log=log)
    return data