import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import get_request_async, OUT_PAGE_ERROR, parse_token
from src_v2.core.utils import tqdm_manager







@esi_request
async def character_character_id_portrait(access_token, character_id, log=True):
    ac_token = await access_token
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/characters/{character_id}/portrait/",
                       headers={"Authorization": f"Bearer {ac_token}"}, log=log)
    return data

# Get blueprints
# get
# https://esi.evetech.net/characters/{character_id}/blueprints
# esi-characters.read_blueprints.v1
@esi_request
async def characters_character_id_blueprints(access_token, character_id: int, page: int=1, max_retries=3, log=True):
    access_token = await parse_token(access_token)
    data, pages = await get_request_async(
        f"https://esi.evetech.net/latest/characters/{character_id}/blueprints/",
        headers={"Authorization": f"Bearer {access_token}"}, params={"page": page}, log=log, max_retries=max_retries,
        no_retry_code=[OUT_PAGE_ERROR]
    )
    if page != 1:
        await tqdm_manager.update_mission(f'character_character_id_blueprints_{character_id}')
        return data

    await tqdm_manager.add_mission(f'character_character_id_blueprints_{character_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(asyncio.create_task(characters_character_id_blueprints(access_token, character_id, p, max_retries, log)))
        # 使用asyncio.gather同时等待所有任务完成
    page_results = await asyncio.gather(*tasks)
    # 将所有页面的结果合并到data中
    for page_data in page_results:
        data.append(page_data)

    await tqdm_manager.complete_mission(f'character_character_id_blueprints_{character_id}')

    return data



@esi_request
async def characters_character(character_id, log=True):
    """
# alliance_id - Integer
# birthday -  String (date-time)
# bloodline_id - Integer
# corporation_id - Integer
# description - String
# faction_id - Integer
# gender - String
# name - String
# race_id - Integer
# security_status - Float (min: -10, max: 10)
# title - String
    """
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/characters/{character_id}/", log=log)
    data["character_id"] = character_id
    return data



# Get character portraits
# https://esi.evetech.net/characters/{character_id}/portrait
@esi_request
async def characters_character_portrait(character_id: int, log=True):
    datg, _ = await get_request_async(
        f"https://esi.evetech.net/latest/characters/{character_id}/portrait/",
        log=log
    )
    return datg

# Get character corporation roles
# esi-characters.read_corporation_roles.v1
# https://esi.evetech.net/characters/{character_id}/roles
@esi_request
async def characters_character_roles(access_token, character_id: int, log=True):
    ac_token = await parse_token(access_token)
    data, _ = await get_request_async(
        f"https://esi.evetech.net/latest/characters/{character_id}/roles/",
        headers={"Authorization": f"Bearer {ac_token}"},
        log=log
    )
    return data