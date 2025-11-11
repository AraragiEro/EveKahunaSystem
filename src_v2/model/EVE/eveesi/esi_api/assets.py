import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import get_request_async, OUT_PAGE_ERROR
from src_v2.core.utils import tqdm_manager


# Get corporation asset locations
# esi-assets.read_corporation_assets.v1
# https://esi.evetech.net/corporations/{corporation_id}/assets/locations
@esi_request
async def corporations_corporation_assets(access_token, corporation_id: int, page: int=1, test=False, max_retries=3, log=True):
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
        return data

    await tqdm_manager.add_mission(f'corporations_corporation_assets_{corporation_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(corporations_corporation_assets(ac_token, corporation_id, p, test, max_retries, log))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)
    await tqdm_manager.complete_mission(f'corporations_corporation_assets_{corporation_id}')

    return data
