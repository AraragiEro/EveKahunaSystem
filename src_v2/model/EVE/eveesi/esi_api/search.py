import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import get_request_async, OUT_PAGE_ERROR, parse_token
from src_v2.core.utils import tqdm_manager


# Search on a string
# esi-search.search_structures.v
# https://esi.evetech.net/characters/{character_id}/search
# esi-search.search_structures.v1.
@esi_request
async def search(
    access_token,
    character_id,
    categories: list[str],
    search: str,
    log=True
):
    ac_token = await parse_token(access_token)
    data, _, _ = await get_request_async(
        f"https://esi.evetech.net/characters/{character_id}/search",
        headers={"Authorization": f"Bearer {ac_token}"},
        params={"categories": categories, "search": search},
        log=log)
    return data