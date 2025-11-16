import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import get_request_async, OUT_PAGE_ERROR
from src_v2.core.utils import tqdm_manager




# Get corporation information
# https://esi.evetech.net/corporations/{corporation_id}
@esi_request
async def corporations_corporation_id(corporation_id: int, log=True):
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/corporations/{corporation_id}/",
                       log=log, max_retries=1)
    return data

# Get corporation icon
# https://esi.evetech.net/corporations/{corporation_id}/icons
@esi_request
async def corporations_corporation_id_icons(corporation_id: int, log=True):
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/corporations/{corporation_id}/icons/",
                       log=log, max_retries=1)
    return data

# Get corporation blueprints
# get
# https://esi.evetech.net/corporations/{corporation_id}/blueprints
# esi-corporations.read_blueprints.v1
# This route is part of the rate limit group corp-industry. This group is limited to 600 tokens per 15 minutes.
@esi_request
async def corporations_corporation_id_blueprints(access_token, corporation_id: int, page: int=1, max_retries=3, log=True):
    if not isinstance(access_token, str):
        ac_token = await access_token
    else:
        ac_token = access_token
    data, pages = await get_request_async(
        f"https://esi.evetech.net/latest/corporations/{corporation_id}/blueprints/",
        headers={"Authorization": f"Bearer {ac_token}"}, params={"page": page}, log=log, max_retries=max_retries,
        no_retry_code=[OUT_PAGE_ERROR]
    )
    if page != 1:
        await tqdm_manager.update_mission(f'corporations_corporation_id_blueprints_{corporation_id}')
        return data

    await tqdm_manager.add_mission(f'corporations_corporation_id_blueprints_{corporation_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(asyncio.create_task(corporations_corporation_id_blueprints(ac_token, corporation_id, p, max_retries, log)))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)
    await tqdm_manager.complete_mission(f'corporations_corporation_id_blueprints_{corporation_id}')

    return data

# Get corporation members
# esi-corporations.read_corporation_membership.v1
# https://esi.evetech.net/corporations/{corporation_id}/members
# esi-corporations.read_corporation_membership.v1
@esi_request
async def corporations_corporation_id_members(access_token, corporation_id: int, log=True):
    ac_token = await access_token
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/corporations/{corporation_id}/members/",
                       headers={"Authorization": f"Bearer {ac_token}"}, log=log, max_retries=1)
    return data
