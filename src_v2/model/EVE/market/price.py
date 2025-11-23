from ..sde import SdeUtils
from ..market_server.market_manager import MarketManager

from ...utils import KahunaException

class PriceService:
    @staticmethod
    async def get_price_rouge(item_str: str, market_str: str):
        # 可能的模糊匹配

        if market_str == "jita" or market_str == "frt":
            market = MarketManager.market_dict[market_str]
        else:
            raise KahunaException("market_server not define.")

        # 模糊匹配以及特殊处理
        # 先处理map
        if item_str in SdeUtils.item_map_dict:
            item_str = SdeUtils.item_map_dict[item_str]
        # 找不到id时获取模糊匹配结果并返回给用户
        if (type_id := await SdeUtils.get_id_by_name(item_str)) is None:
            fuzz_list = await SdeUtils.fuzz_type(item_str)
            # 进行忽略大小写的匹配
            for item in fuzz_list:
                if SdeUtils.maybe_chinese(item_str):
                    if len(item_str) == len(item) or item_str in item:
                        type_id = await SdeUtils.get_id_by_name(item)
                        break
                else:
                    if item_str.lower() == item.lower():
                        type_id = await SdeUtils.get_id_by_name(item)
                        break
            if type_id is None:
                return None, None, None, None, fuzz_list
        if type_id:
            if type_id == 44992:
                market = MarketManager.market_dict['plex']
            max_buy, min_sell = await market.get_type_order_rouge(type_id)

            # 整理信息
            mid_price = round((max_buy + min_sell) / 2, 2)

            return type_id, max_buy, mid_price, min_sell, None

    @staticmethod
    async def get_latest_order(item_id: int, market_str: str):
        if market_str == "jita" or market_str == "frt":
            market = MarketManager.market_dict[market_str]
        else:
            raise KahunaException("market_server not define.")

        return await market.get_latest_order_by_type_id(item_id)

    @staticmethod
    async def get_item_special_scheme(item_str):
        pass


