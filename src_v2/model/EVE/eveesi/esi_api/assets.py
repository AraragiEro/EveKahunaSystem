import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import get_request_async, OUT_PAGE_ERROR
from src_v2.core.utils import tqdm_manager

from src_v2.core.database.connect_manager import redis_manager as rdm

# Get corporation asset locations
# esi-assets.read_corporation_assets.v1
# https://esi.evetech.net/corporations/{corporation_id}/assets/locations
@esi_request
async def corporations_corporation_assets(access_token, corporation_id: int, page: int=1, test=False, max_retries=3, log=True, **kwargs):
    """
    # is_blueprint_copy - Boolean
    # is_singleton - Boolean
    # item_id - Integer
    # location_flag - String
    # location_id - Integer
    # location_type - String
    # quantity - Integer
    # type_id - Integer
    """
    status_key = kwargs.get('status_key', None)
    if not isinstance(access_token, str):
        ac_token = await access_token
    else:
        ac_token = access_token
    data, pages = await get_request_async(
        f"https://esi.evetech.net/latest/corporations/{corporation_id}/assets/",
        headers={"Authorization": f"Bearer {ac_token}"}, params={"page": page}, log=log, max_retries=max_retries,
        no_retry_code=[OUT_PAGE_ERROR]
    )

    if test or page != 1:
        if page != 1:
            await tqdm_manager.update_mission(f'corporations_corporation_assets_{corporation_id}')
            if status_key:
                total_page = await rdm.r.hget(status_key, "total_page")
                await rdm.r.hset(status_key, "step_progress", page / int(total_page or 0))
        return data

    await tqdm_manager.add_mission(f'corporations_corporation_assets_{corporation_id}', pages)
    if status_key:
        await rdm.r.hset(status_key, "total_page", pages)
        await rdm.r.hset(status_key, "step_progress", 0)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(asyncio.create_task(corporations_corporation_assets(ac_token, corporation_id, p, test, max_retries, log, status_key=status_key)))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)
    await tqdm_manager.complete_mission(f'corporations_corporation_assets_{corporation_id}')

    return data

# Get character assets
# get
# https://esi.evetech.net/characters/{character_id}/assets
# esi-assets.read_assets.v1.
@esi_request
async def characters_character_assets(access_token, character_id: int, page: int=1, test=False, max_retries=3, log=True, **kwargs):
    status_key = kwargs.get('status_key', None)
    if not isinstance(access_token, str):
        ac_token = await access_token
    else:
        ac_token = access_token
    data, pages = await get_request_async(
        f"https://esi.evetech.net/latest/characters/{character_id}/assets/",
        headers={"Authorization": f"Bearer {ac_token}"}, params={"page": page}, log=log, max_retries=max_retries,
        no_retry_code=[OUT_PAGE_ERROR]
    )

    if test or page != 1:
        if page != 1:
            await tqdm_manager.update_mission(f'characters_character_assets_{character_id}')
            if status_key:
                total_page = await rdm.r.hget(status_key, "total_page")
                await rdm.r.hset(status_key, "step_progress", page / int(total_page or 0))
        return data

    if status_key:
        await rdm.r.hset(status_key, "total_page", pages)
        await rdm.r.hset(status_key, "step_progress", 0)
    await tqdm_manager.add_mission(f'characters_character_assets_{character_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(asyncio.create_task(characters_character_assets(ac_token, character_id, p, test, max_retries, log, status_key=status_key)))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)
    await tqdm_manager.complete_mission(f'characters_character_assets_{character_id}')

    return data