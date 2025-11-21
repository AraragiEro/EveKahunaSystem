import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import get_request_async, OUT_PAGE_ERROR, parse_token
from src_v2.core.utils import tqdm_manager


@esi_request
async def industry_systems(log=True):
    data, _, _ =  await get_request_async(f"https://esi.evetech.net/latest/industry/systems/", log=log)
    return data


# List corporation industry jobs
# GET
# esi-industry.read_corporation_jobs.v1
# https://esi.evetech.net/corporations/{corporation_id}/industry/jobs
# This route is part of the rate limit group corp-industry. This group is limited to 600 tokens per 15 minutes.
@esi_request
async def corporations_corporation_id_industry_jobs(
        access_token, corporation_id: int, page: int=1, include_completed: bool = False, max_retries=3, log=True
):
    access_token = await parse_token(access_token)
    data, pages, _ = await get_request_async(
        f"https://esi.evetech.net/corporations/{corporation_id}/industry/jobs/",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "page": page,
                "include_completed": 1 if include_completed else 0
            }, log=log, max_retries=max_retries,
            no_retry_code=[OUT_PAGE_ERROR]
        )
    if page != 1:
        await tqdm_manager.update_mission(f'corporations_corporation_id_industry_jobs_{corporation_id}')
        return data

    await tqdm_manager.add_mission(f'corporations_corporation_id_industry_jobs_{corporation_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(asyncio.create_task(corporations_corporation_id_industry_jobs(access_token, corporation_id, p, include_completed, max_retries, log)))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)
    await tqdm_manager.complete_mission(f'corporations_corporation_id_industry_jobs_{corporation_id}')

    return data

# List character industry jobs
# get
# https://esi.evetech.net/characters/{character_id}/industry/jobs
# esi-industry.read_character_jobs.v1
@esi_request
async def characters_character_id_industry_jobs(access_token, character_id: int, include_completed: bool = False, log=True):
    """
    List character industry jobs
    Args:
        access_token: Access token
        character_id: An EVE character ID
        datasource: The server name you would like data from
        include_completed: Whether to retrieve completed character industry jobs
    Returns:
        Industry jobs placed by a character
    """
    data, _, _ = await get_request_async(f"https://esi.evetech.net/characters/{character_id}/industry/jobs/", headers={
        "Authorization": f"Bearer {await parse_token(access_token)}"
    }, params={
        "include_completed": 1 if include_completed else 0
    }, log=log)

    return data