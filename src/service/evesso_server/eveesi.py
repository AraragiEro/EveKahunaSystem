from logging import exception

import requests
from cachetools import TTLCache, cached
import traceback
import aiohttp
import asyncio
from typing import Optional, Any
from tqdm.asyncio import tqdm


# kahuna logger
from ..log_server import logger
from .esi_req_manager import esi_request

permission_set = set()

OUT_PAGE_ERROR = 404

class asnyc_tqdm_manager:
    def __init__(self):
        self.mission = {}
        self.mission_count = 0
        self.lock = asyncio.Lock()

    async def add_mission(self, mission_id, len, description=None):
        async with self.lock:
            description = description if description else f"{mission_id}"
            index = self.mission_count
            self.mission_count += 1

            bar = tqdm(total=len, desc=description, position=index, leave=False)

            self.mission[mission_id] = {
                "bar": bar,
                'index': index,
                'count': 0,
                "completed": False,
            }

    async def update_mission(self, mission_id, value=1):
        async with self.lock:
            if mission_id in self.mission:
                self.mission[mission_id]["count"] += 1
                self.mission[mission_id]["bar"].update(1)

    async def complete_mission(self, mission_id):
        if mission_id in self.mission:
            index = self.mission[mission_id]["index"]
            self.mission[mission_id]["completed"] = True
            self.mission[mission_id]["bar"].close()
            del self.mission[mission_id]

            self.mission_count -= 1


tqdm_manager = asnyc_tqdm_manager()

async def get_request_async(
        url, headers=None, params=None, log=True, max_retries=2, timeout=60, no_retry_code = None
) -> Optional[Any]:
    """
    异步发送GET请求，带有重试机制

    Args:
        url: 请求URL
        headers: 请求头
        params: 查询参数
        log: 是否记录日志
        max_retries: 最大重试次数
        timeout: 超时时间（秒）
    """
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    if response.status == 200:
                        try:
                            data = await asyncio.wait_for(response.json(), timeout=timeout)
                            pages = response.headers.get('X-Pages')
                            if pages:
                                pages = int(pages)

                            return data, pages
                        except asyncio.TimeoutError:
                            if log:
                                logger.warning(f"JSON解析超时 (尝试 {attempt + 1}/{max_retries}): {url}")
                            if attempt == max_retries - 1:
                                raise
                            continue
                    elif no_retry_code and response.status in no_retry_code:
                        return [], 0
                    else:
                        response_text = await response.text()
                        if log:
                            logger.warning(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {url}")
                            logger.warning(f'{response.status}:{response_text}')
                        if attempt == max_retries - 1:
                            return None, 0
                        await asyncio.sleep(1 * (attempt + 1))  # 指数退避
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if log:
                logger.error(f"请求异常 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                if log:
                    logger.error(traceback.format_exc())
                return [], 0
            await asyncio.sleep(1 * (attempt + 1))  # 指数退避
        except Exception as e:
            if log:
                logger.error(traceback.format_exc())
            return [], 0

async def verify_token(access_token, log=True):
    data, _ = await get_request_async("https://esi.evetech.net/verify/", headers={"Authorization": f"Bearer {access_token}"}, log=log)
    return data

@esi_request
async def character_character_id_skills(access_token, character_id, log=True):
    ac_token = await access_token
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/characters/{character_id}/skills/",
                       headers={"Authorization": f"Bearer {ac_token}"}, log=log)
    return data

@esi_request
async def character_character_id_wallet(access_token, character_id, log=True):
    ac_token = await access_token
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/characters/{character_id}/wallet/",
                       headers={"Authorization": f"Bearer {ac_token}"}, log=log)
    return data

@esi_request
async def character_character_id_portrait(access_token, character_id, log=True):
    ac_token = await access_token
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/characters/{character_id}/portrait/",
                       headers={"Authorization": f"Bearer {ac_token}"}, log=log)
    return data

@esi_request
async def characters_character_id_blueprints(access_token, character_id: int, page: int=1, max_retries=3, log=True):
    if not isinstance(access_token, str):
        ac_token = await access_token
    else:
        ac_token = access_token
    data, pages = await get_request_async(
        f"https://esi.evetech.net/latest/characters/{character_id}/blueprints/",
        headers={"Authorization": f"Bearer {ac_token}"}, params={"page": page}, log=log, max_retries=max_retries,
        no_retry_code=[OUT_PAGE_ERROR]
    )
    if page != 1:
        await tqdm_manager.update_mission(f'character_character_id_blueprints_{character_id}')
        return data

    await tqdm_manager.add_mission(f'character_character_id_blueprints_{character_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(characters_character_id_blueprints(ac_token, character_id, p, max_retries, log))
        # 使用asyncio.gather同时等待所有任务完成
    page_results = await asyncio.gather(*tasks)
    # 将所有页面的结果合并到data中
    for page_data in page_results:
        data.append(page_data)

    await tqdm_manager.complete_mission(f'character_character_id_blueprints_{character_id}')

    return data

@esi_request
async def industry_systems(log=True):
    data, _ =  await get_request_async(f"https://esi.evetech.net/latest/industry/systems/", log=log)
    return data

@esi_request
async def markets_structures(access_token, structure_id: int, page: int=1, test=False, max_retries=3, log=True) -> dict:
    if not isinstance(access_token, str):
        ac_token = await access_token
    else:
        ac_token = access_token
    data, pages = await get_request_async(
        f"https://esi.evetech.net/latest/markets/structures/{structure_id}/",
        headers={"Authorization": f"Bearer {ac_token}"}, params={"page": page}, log=log, max_retries=max_retries,
        no_retry_code=[OUT_PAGE_ERROR]
    )

    if test or page != 1:
        if page != 1:
            await tqdm_manager.update_mission(f'markets_structures_{structure_id}')
        return data

    await tqdm_manager.add_mission(f'markets_structures_{structure_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(markets_structures(ac_token, structure_id, p, test, max_retries, log))
    page_results = await asyncio.gather(*tasks)
    for page_data in page_results:
        data.append(page_data)

    await tqdm_manager.complete_mission(f'markets_structures_{structure_id}')

    return data

@esi_request
async def markets_region_orders(region_id: int, type_id: int = None, page: int=1, max_retries=3, log=True):
    params = {"page": page}
    if type_id is not None:
        params["type_id"] = type_id
    data, pages = await get_request_async(
        f"https://esi.evetech.net/latest/markets/{region_id}/orders/", headers={},
       params=params, log=log, max_retries=max_retries, no_retry_code=[OUT_PAGE_ERROR]
    )
    if page != 1:
        await tqdm_manager.update_mission(f'markets_region_orders_{region_id}')
        return data

    await tqdm_manager.add_mission(f'markets_region_orders_{region_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(markets_region_orders(region_id, type_id, p, max_retries, log))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)

    await tqdm_manager.complete_mission(f'markets_region_orders_{region_id}')
    return data

@esi_request
async def characters_character_assets(access_token, character_id: int, page: int=1, test=False, max_retries=3, log=True):
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
        return data

    await tqdm_manager.add_mission(f'characters_character_assets_{character_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(characters_character_assets(ac_token, character_id, p, test, max_retries, log))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)
    await tqdm_manager.complete_mission(f'characters_character_assets_{character_id}')

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
    return data

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

@esi_request
async def corporations_corporation_id_roles(access_token, corporation_id: int, log=True):
    ac_token = await access_token
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/corporations/{corporation_id}/roles/",
                       headers={"Authorization": f"Bearer {ac_token}"}, log=log, max_retries=1)
    return data

@esi_request
async def corporations_corporation_id_industry_jobs(
        access_token, corporation_id: int, page: int=1, include_completed: bool = False, max_retries=3, log=True
):
    if not isinstance(access_token, str):
        ac_token = await access_token
    else:
        ac_token = access_token
    data, pages = await get_request_async(
    f"https://esi.evetech.net/latest/corporations/{corporation_id}/industry/jobs/",
        headers={"Authorization": f"Bearer {ac_token}"},
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
        tasks.append(corporations_corporation_id_industry_jobs(ac_token, corporation_id, p, include_completed, max_retries, log))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)
    await tqdm_manager.complete_mission(f'corporations_corporation_id_industry_jobs_{corporation_id}')

    return data

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
        tasks.append(corporations_corporation_id_blueprints(ac_token, corporation_id, p, max_retries, log))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)
    await tqdm_manager.complete_mission(f'corporations_corporation_id_blueprints_{corporation_id}')

    return data

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
                       headers={"Authorization": f"Bearer {ac_token}"}, log=log)
    return data

@esi_request
async def universe_stations_station(station_id, log=True):
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/universe/stations/{station_id}/", log=log)
    return data

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
    ac_token = await access_token
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/characters/{character_id}/industry/jobs/", headers={
        "Authorization": f"Bearer {ac_token}"
    }, params={
        "include_completed": 1 if include_completed else 0
    }, log=log)

    return data

@esi_request
async def markets_prices(log=True):
    data, _ = await get_request_async(f'https://esi.evetech.net/latest/markets/prices/', log=log)
    return data

# /markets/{region_id}/history/
@esi_request
async def markets_region_history(region_id: int, type_id: int, log=True):
    data, _ = await get_request_async(f"https://esi.evetech.net/latest/markets/{region_id}/history/", headers={},
                       params={"type_id": type_id, "region_id": region_id}, log=log, max_retries=1)
    return data

# /characters/{character_id}/orders/
@esi_request
async def characters_character_orders(access_token, character_id: int, log=True):
    ac_token = await access_token
    data, _ = await get_request_async(
        f"https://esi.evetech.net/latest/characters/{character_id}/orders/",
        headers={"Authorization": f"Bearer {ac_token}"},
        log=log
    )
    return data

# /characters/{character_id}/orders/history/
@esi_request
async def characters_character_orders_history(access_token, character_id: int, page: int=1, max_retries=3, log=True):
    if not isinstance(access_token, str):
        ac_token = await access_token
    else:
        ac_token = access_token
    data, pages = await get_request_async(
        f"https://esi.evetech.net/latest/characters/{character_id}/orders/history/",
        headers={"Authorization": f"Bearer {ac_token}"},
        params={"page": page},
        log=log,
        max_retries=max_retries,
        no_retry_code=[OUT_PAGE_ERROR]
    )
    if page != 1:
        await tqdm_manager.update_mission(f'characters_character_orders_history_{character_id}')
        return data

    await tqdm_manager.add_mission(f'characters_character_orders_history_{character_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(characters_character_orders_history(ac_token, character_id, p, max_retries, log))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)
    await tqdm_manager.complete_mission(f'characters_character_orders_history_{character_id}')
    return data

# /characters/{character_id}/portrait/
@esi_request
async def characters_character_portrait(character_id: int, log=True):
    datg, _ = await get_request_async(
        f"https://esi.evetech.net/latest/characters/{character_id}/portrait/",
        log=log
    )
    return datg