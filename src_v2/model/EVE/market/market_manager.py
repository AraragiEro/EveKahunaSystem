
import asyncio
from datetime import datetime

# from .marker import Market
from src_v2.core.database.connect_manager import redis_manager as rdm
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.config.config import config, update_config
#import Exception
from src_v2.core.utils import KahunaException, SingletonMeta

from src_v2.model.EVE.eveesi import eveesi

# kahuna logger
from src_v2.core.log import logger

REGION_FORGE_ID = 10000002
REGION_VALE_ID = 10000003
REGION_PLEX_ID = 19000001
JITA_TRADE_HUB_STRUCTURE_ID = 60003760
PLEX_ID = 44992
FRT_4H_STRUCTURE_ID = 1035466617946
S33RB_O_STRUCTURE_ID = 1045441547980
B_9C24_KEEPSTAR_ID = 1046831245129
PIMI_STRUCTURE_LIST = [1042508032148, 1042499803831, 1044752365771]

class MarketManager(metaclass=SingletonMeta):
    def __init__(self):
        self.update_jita_price_lock = asyncio.Lock()

    async def _batch_insert_redis(self, batch: list):
        """批量插入Redis的辅助方法"""
        for type_id, price_data in batch:
            await rdm.r.hset(f"market:price:jita:{type_id}", mapping=price_data)

    async def update_jita_price(self):
        async with self.update_jita_price_lock:
            update_flag = await rdm.r.get(f"market:update_flag:jita")
            if update_flag:
                return

        type_price_cache = {}
        jita_order = await eveesi.markets_region_orders(REGION_FORGE_ID)
        for order_list in jita_order:
            for order in order_list:
                if order["location_id"] != JITA_TRADE_HUB_STRUCTURE_ID:
                    continue
                    
                if order["type_id"] not in type_price_cache:
                    type_price_cache[order["type_id"]] = {
                        "max_buy": 0,
                        "min_sell": 1000000000000000000000,
                    }
                else:
                    if order["is_buy_order"]:
                        type_price_cache[order["type_id"]]["max_buy"] = max(type_price_cache[order["type_id"]]["max_buy"], order["price"])
                    else:
                        type_price_cache[order["type_id"]]["min_sell"] = min(type_price_cache[order["type_id"]]["min_sell"], order["price"])


        
        # 分批处理并并发插入Redis
        batch_size = 100  # 每批处理100个type_id
        items = list(type_price_cache.items())
        tasks = []
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            task = asyncio.create_task(self._batch_insert_redis(batch))
            tasks.append(task)
        
        # 等待所有批次完成
        await asyncio.gather(*tasks)

        await rdm.r.set(f"market:update_flag:jita", "1", ex=60 *60)


# class MarketManagerOld():
#     init_status = False
#     market_dict = dict()
#     monitor_process = None
#     refresh_signal_flag = False
#     last_refresh_time = None

#     @classmethod
#     def init(cls):
#         cls.init_market()

#     @classmethod
#     def init_market(cls):
#         if not cls.init_status:
#             cls.market_dict["jita"] = Market("jita")
#             cls.market_dict["frt"] = Market("frt")
#             cls.market_dict['plex'] = Market("plex")
#             cls.market_dict['B-9'] = Market("B-9")

#             try:
#                 ac_character_id = int(config['EVE']['MARKET_AC_CHARACTER_ID'])
#                 cls.market_dict["frt"].access_character = CharacterManager.get_character_by_id(ac_character_id)
#                 cls.market_dict["B-9"].access_character = CharacterManager.get_character_by_id(ac_character_id)
#             except:
#                 logger.error(f"market access character init error")
#                 return


#         cls.init_status = True
#         logger.info(f"初始化市场. {id(cls)}")

#     @classmethod
#     async def set_ac_character(cls, ac_character_id: int):
#         frt_market = Market("frt")
#         frt_market.access_character = CharacterManager.get_character_by_id(ac_character_id)
#         if not await frt_market.check_structure_access():
#             raise KahunaException("获取市场数据失败，检查角色名或权限。")
#         update_config("EVE", "MARKET_AC_CHARACTER_ID", ac_character_id)

#     @classmethod
#     async def copy_to_cache(cls):
#         await MarketOrderCacheDBUtils.copy_base_to_cache()

#     # 监视器，定时刷新
#     @classmethod
#     async def refresh_market(cls, force=False):
#         if not force and not await RefreshDataDBUtils.out_of_min_interval('market_order', 20):
#             return await cls.get_markets_detal()

#         logger.info("开始刷新市场数据。")
#         for market in cls.market_dict.values():
#             await market.get_market_order()
#         await cls.copy_to_cache()

#         log = await cls.get_markets_detal()
#         logger.info(log)
#         await RefreshDataDBUtils.update_refresh_date('market_order')
#         return log

#     @classmethod
#     def get_market_by_type(cls, type: str) -> Market | None:
#         return cls.market_dict.get(type, None)

#     @classmethod
#     async def get_markets_detal(cls) -> str:
#         res = {}
#         for market in cls.market_dict.values():
#             res[market.market_type] = await market.get_market_detail()
#         refresh_log = ""
#         for market, date in res.items():
#             refresh_log += (f"{market}:\n"
#                             f"  总订单数量：{date[0]} (收单：{date[1]}, 出单：{date[2]}, 物品：{date[3]})\n")
#         return refresh_log

