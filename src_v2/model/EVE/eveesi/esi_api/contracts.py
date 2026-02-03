
import asyncio

from src_v2.core.utils import tqdm_manager

from ..esi_req_manager import esi_request
from ..eveutils import OUT_PAGE_ERROR, get_request_async, parse_token


# Get contracts
# esi-contracts.read_character_contracts.v1
# https://esi.evetech.net/characters/{character_id}/contracts
# This route is part of the rate limit group char-contract. This group is limited to 600 tokens per 15 minutes.
@esi_request(limit=0.3)
async def characters_character_contracts(access_token, character_id: int, page: int = 1, max_retries=3, log=True):
    access_token = await parse_token(access_token)
    data, pages, _ = await get_request_async(
        f"https://esi.evetech.net/latest/characters/{character_id}/contracts/",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"page": page},
        log=log,
        max_retries=max_retries,
        no_retry_code=[OUT_PAGE_ERROR]
    )
    if page != 1:
        await tqdm_manager.update_mission(f'characters_character_contracts_{character_id}')
        return data

    await tqdm_manager.add_mission(f'characters_character_contracts_{character_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(asyncio.create_task(characters_character_contracts(
            access_token, character_id, p, max_retries, log)))
    page_results = await asyncio.gather(*tasks)
    for page_data in page_results:
        data.append(page_data)

    await tqdm_manager.complete_mission(f'characters_character_contracts_{character_id}')
    return data


# Get corporation contracts
# esi-contracts.read_corporation_contracts.v1
# https://esi.evetech.net/corporations/{corporation_id}/contracts
# This route is part of the rate limit group corp-contract. This group is limited to 600 tokens per 15 minutes.
@esi_request(limit=0.3)
async def corporations_corporation_contracts(access_token, corporation_id: int, page: int = 1, max_retries=3, log=True):
    access_token = await parse_token(access_token)
    data, pages, _ = await get_request_async(
        f"https://esi.evetech.net/latest/corporations/{corporation_id}/contracts/",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"page": page},
        log=log,
        max_retries=max_retries,
        no_retry_code=[OUT_PAGE_ERROR]
    )
    if page != 1:
        await tqdm_manager.update_mission(f'corporations_corporation_contracts_{corporation_id}')
        return data

    await tqdm_manager.add_mission(f'corporations_corporation_contracts_{corporation_id}', pages)
    tasks = []
    data = [data]
    for p in range(2, pages + 1):
        tasks.append(asyncio.create_task(corporations_corporation_contracts(
            access_token, corporation_id, p, max_retries, log)))
    page_results = await asyncio.gather(*tasks)
    for page_data in page_results:
        data.append(page_data)

    await tqdm_manager.complete_mission(f'corporations_corporation_contracts_{corporation_id}')
    return data


# Get corporation contract items
# esi-contracts.read_corporation_contracts.v1
# https://esi.evetech.net/corporations/{corporation_id}/contracts/{contract_id}/items
# This route is part of the rate limit group corp-contract. This group is limited to 600 tokens per 15 minutes.
@esi_request(limit=0.3)
async def corporations_corporation_contracts_contract_id_items(access_token, corporation_id: int, contract_id: int, max_retries=3, log=True):
    access_token = await parse_token(access_token)
    data, _, _ = await get_request_async(
        f"https://esi.evetech.net/latest/corporations/{corporation_id}/contracts/{contract_id}/items/",
        headers={"Authorization": f"Bearer {access_token}"},
        log=log,
        max_retries=max_retries
    )
    return data
