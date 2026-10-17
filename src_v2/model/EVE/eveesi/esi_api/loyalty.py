from ..esi_req_manager import esi_request
from ..eveutils import get_request_async


# List loyalty store offers for a corporation
# https://esi.evetech.net/loyalty/stores/{corporation_id}/offers
# This is a public endpoint, no auth required.
# Route expires daily at 11:05 (UTC).
@esi_request
async def loyalty_stores_corporation_id_offers(corporation_id: int, log=True):
    """
    获取指定军团忠诚点商店的兑换列表。

    Args:
        corporation_id: NPC军团ID
        log: 是否记录日志

    Returns:
        list[dict]: 兑换物品列表，每项包含:
            - offer_id (int): 兑换项ID
            - type_id (int): 可兑换物品的typeID
            - quantity (int): 每次兑换获得的数量
            - lp_cost (int): 忠诚点消耗
            - isk_cost (int): ISK消耗
            - ak_cost (int, optional): 分析信用点消耗(仅部分势力)
            - required_items (list[dict]): 需要的物品清单
                - type_id (int): 所需物品typeID
                - quantity (int): 所需数量

    Raises:
        HTTP 404: 该军团没有LP商店
    """
    data, *_ = await get_request_async(
        f"https://esi.evetech.net/latest/loyalty/stores/{corporation_id}/offers/",
        log=log, max_retries=1
    )
    return data
