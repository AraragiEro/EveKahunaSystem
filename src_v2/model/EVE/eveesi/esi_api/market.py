import asyncio

from ..esi_req_manager import esi_request
from ..eveutils import get_request_async, OUT_PAGE_ERROR
from src_v2.core.utils import tqdm_manager


# List orders in a structure
# esi-markets.structure_markets.v1
# https://esi.evetech.net/markets/structures/{structure_id}
@esi_request
async def markets_structures(access_token, structure_id: int, page: int=1, test=False, max_retries=3, log=True) -> dict:
    if not isinstance(access_token, str):
        ac_token = await access_token
    else:
        ac_token = access_token
    data, pages = await get_request_async(
        f"https://esi.evetech.net/markets/structures/{structure_id}/",
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
        tasks.append(asyncio.create_task(markets_structures(ac_token, structure_id, p, test, max_retries, log)))
    page_results = await asyncio.gather(*tasks)
    for page_data in page_results:
        data.append(page_data)

    await tqdm_manager.complete_mission(f'markets_structures_{structure_id}')

    return data

# List orders in a region
# https://esi.evetech.net/markets/{region_id}/orders
@esi_request
async def markets_region_orders(region_id: int, type_id: int = None, page: int=1, max_retries=3, log=True):
    params = {"page": page}
    if type_id is not None:
        params["type_id"] = type_id
    data, pages = await get_request_async(
        f"https://esi.evetech.net/markets/{region_id}/orders/", headers={},
       params=params, log=log, max_retries=max_retries, no_retry_code=[OUT_PAGE_ERROR]
    )
    if page != 1:
        await tqdm_manager.update_mission(f'markets_region_orders_{region_id}')
        return data

    await tqdm_manager.add_mission(f'markets_region_orders_{region_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(asyncio.create_task(markets_region_orders(region_id, type_id, p, max_retries, log)))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)

    await tqdm_manager.complete_mission(f'markets_region_orders_{region_id}')
    return data

# List market prices
# https://esi.evetech.net/markets/prices
@esi_request
async def markets_prices(log=True):
    data, _ = await get_request_async(f'https://esi.evetech.net/markets/prices/', log=log)
    return data

# List historical market statistics in a region
# https://esi.evetech.net/markets/{region_id}/history
@esi_request
async def markets_region_history(region_id: int, type_id: int, log=True):
    data, _ = await get_request_async(f"https://esi.evetech.net/markets/{region_id}/history/", headers={},
                       params={"type_id": type_id, "region_id": region_id}, log=log, max_retries=1)
    return data

# List historical orders by a character
# esi-markets.read_character_orders.v1
# https://esi.evetech.net/characters/{character_id}/orders/history
@esi_request
async def characters_character_orders_history(access_token, character_id: int, page: int=1, max_retries=3, log=True):
    if not isinstance(access_token, str):
        ac_token = await access_token
    else:
        ac_token = access_token
    data, pages = await get_request_async(
        f"https://esi.evetech.net/characters/{character_id}/orders/history/",
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
        tasks.append(asyncio.create_task(characters_character_orders_history(ac_token, character_id, p, max_retries, log)))
    page_results = await asyncio.gather(*tasks)
    for data_page in page_results:
        data.append(data_page)
    await tqdm_manager.complete_mission(f'characters_character_orders_history_{character_id}')
    return data

# List open orders from a character
# get
# https://esi.evetech.net/characters/{character_id}/orders
# esi-markets.read_character_orders.v1.
@esi_request
async def characters_character_orders(access_token, character_id: int, log=True):
    ac_token = await access_token
    data, _ = await get_request_async(
        f"https://esi.evetech.net/characters/{character_id}/orders/",
        headers={"Authorization": f"Bearer {ac_token}"},
        log=log
    )
    return data