from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import traceback
import time
from peewee import fn
import asyncio
from cachetools import TTLCache, cached
from datetime import datetime, timedelta

from ..evesso_server.eveesi import markets_region_orders
from ..evesso_server.eveesi import markets_structures
from ..evesso_server import eveesi
from ..database_server.sqlalchemy.kahuna_database_utils import (
    MarkerOrderDBUtils, MarketOrderCacheDBUtils,
    RefreshDataDBUtils,
    MarketHistoryDBUtils
)

# kahuna logger
from ..log_server import logger

REGION_FORGE_ID = 10000002
REGION_VALE_ID = 10000003
REGION_PLEX_ID = 19000001
JITA_TRADE_HUB_STRUCTURE_ID = 60003760
PLEX_ID = 44992
FRT_4H_STRUCTURE_ID = 1035466617946
S33RB_O_STRUCTURE_ID = 1045441547980
PIMI_STRUCTURE_LIST = [1042508032148, 1042499803831, 1044752365771]

class RateLimiter:
    """令牌桶算法实现的频率限制器"""

    def __init__(self, rate_per_minute):
        self.rate_per_second = rate_per_minute / 60.0
        self.max_tokens = rate_per_minute  # 最大令牌数量
        self.tokens = self.max_tokens  # 当前令牌数量
        self.updated_at = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """获取一个令牌，如果没有令牌则等待"""
        async with self.lock:
            # 先更新当前令牌数量
            current = time.time()
            time_passed = current - self.updated_at
            self.updated_at = current

            # 根据时间流逝增加令牌
            self.tokens = min(self.max_tokens, self.tokens + time_passed * self.rate_per_second)

            # 如果没有足够的令牌，需要等待
            if self.tokens < 1:
                # 计算需要等待的时间
                wait_time = (1 - self.tokens) / self.rate_per_second
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class Market:
    market_type = "jita"
    access_character = None

    def __init__(self, market_type="jita"):
        self.market_type = market_type
        if market_type == "frt":
            self.location_id = FRT_4H_STRUCTURE_ID
        else:
            self.location_id = JITA_TRADE_HUB_STRUCTURE_ID

    def set_access_character(self, access_character):
        self.access_character = access_character

    async def get_market_order(self):
        if self.market_type == "jita":
            await self.get_jita_order()
            await self.get_plex_order()
        if self.market_type == "frt":
            await self.get_frt_order()

    async def check_structure_access(self):
        res = await eveesi.markets_structures(self.access_character.ac_token, FRT_4H_STRUCTURE_ID, test=True, log=True)
        if not res:
            return False
        return True

    async def get_frt_order(self):
        if not self.access_character:
            return
        results = await eveesi.markets_structures(self.access_character.ac_token, FRT_4H_STRUCTURE_ID)

        await MarkerOrderDBUtils.delete_order_by_location_id(FRT_4H_STRUCTURE_ID)
        with tqdm(total=len(results), desc=f"写入{MarkerOrderDBUtils.cls_model.__tablename__}数据", unit="page", ascii='=-') as pbar:
            for i, result in enumerate(results):
                await MarkerOrderDBUtils.insert_many(result)
                pbar.update()

    async def get_jita_order(self):
        # with db.atomic() as txn:
        logger.info("请求市场。")
        results = await eveesi.markets_region_orders(REGION_FORGE_ID)

        await MarkerOrderDBUtils.delete_order_by_location_id(JITA_TRADE_HUB_STRUCTURE_ID)
        with tqdm(total=len(results), desc="写入数据库", unit="page", ascii='=-') as pbar:
            for i, result in enumerate(results):
                try:
                    result = [order for order in result if order["location_id"] == JITA_TRADE_HUB_STRUCTURE_ID]
                    await MarkerOrderDBUtils.insert_many(result)
                    pbar.update()
                except Exception as e:
                    # 详细记录错误信息
                    error_msg = [
                        f"处理页面 {i + 1}/{len(results)} 时出错:",
                        f"错误类型: {type(e).__name__}",
                        f"错误信息: {str(e)}",
                        "异常堆栈:"
                    ]
                    error_msg.append(traceback.format_exc())

                    # 检查是否有内部异常
                    inner_exc = e.__cause__ or e.__context__
                    if inner_exc:
                        error_msg.append("内部异常链:")
                        current = inner_exc
                        depth = 1
                        while current:
                            error_msg.append(f"内部异常 {depth}: {type(current).__name__}: {current}")
                            inner_trace = traceback.format_tb(current.__traceback__)
                            error_msg.append(f"内部异常 {depth} 堆栈: {''.join(inner_trace)}")
                            current = current.__cause__ or current.__context__
                            depth += 1
                            if depth > 5:  # 防止过深的递归
                                error_msg.append("异常嵌套过深，停止追踪")
                                break

                    logger.error("\n".join(error_msg))

                    # 更新进度条但显示错误
                    pbar.update()

    async def get_plex_order(self):
        logger.info("请求plex市场。")
        results = await eveesi.markets_region_orders(REGION_PLEX_ID)

        await MarkerOrderDBUtils.delete_order_by_type_id(PLEX_ID)
        with tqdm(total=len(results), desc="写入数据库", unit="page", ascii='=-') as pbar:
            for i, result in enumerate(results):
                try:
                    await MarkerOrderDBUtils.insert_many(result)
                    pbar.update()
                except Exception as e:
                    # 详细记录错误信息
                    error_msg = [
                        f"处理页面 {i + 1}/{len(results)} 时出错:",
                        f"错误类型: {type(e).__name__}",
                        f"错误信息: {str(e)}",
                        "异常堆栈:"
                    ]
                    error_msg.append(traceback.format_exc())

                    # 检查是否有内部异常
                    inner_exc = e.__cause__ or e.__context__
                    if inner_exc:
                        error_msg.append("内部异常链:")
                        current = inner_exc
                        depth = 1
                        while current:
                            error_msg.append(f"内部异常 {depth}: {type(current).__name__}: {current}")
                            inner_trace = traceback.format_tb(current.__traceback__)
                            error_msg.append(f"内部异常 {depth} 堆栈: {''.join(inner_trace)}")
                            current = current.__cause__ or current.__context__
                            depth += 1
                            if depth > 5:  # 防止过深的递归
                                error_msg.append("异常嵌套过深，停止追踪")
                                break

                    logger.error("\n".join(error_msg))

                    # 更新进度条但显示错误
                    pbar.update()

    async def get_market_detail(self) -> tuple[int, int, int, int]:
        if self.market_type == "jita":
            target_location = JITA_TRADE_HUB_STRUCTURE_ID
        else:
            target_location = FRT_4H_STRUCTURE_ID

        # 统计总数据数量，并按照is_buy_order进行求和统计
        total_count = await MarketOrderCacheDBUtils.select_order_count_by_location_id(target_location)
        buy_count = await MarketOrderCacheDBUtils.select_buy_order_count_by_location_id(target_location)
        sell_count = await MarketOrderCacheDBUtils.select_sell_order_count_by_location_id(target_location)

        # 统计不同的类型数量
        distinct_type_count = await MarketOrderCacheDBUtils.select_distinct_type_count_by_location_id(target_location)

        return total_count, buy_count, sell_count, distinct_type_count

    order_rouge_cache = TTLCache(maxsize=500, ttl=10 * 60)
    async def get_type_order_rouge(self, type_id: int) -> tuple[float, float]:
        if type_id in Market.order_rouge_cache:
            return Market.order_rouge_cache[type_id]
        if self.market_type == "jita":
            target_location = JITA_TRADE_HUB_STRUCTURE_ID
        else:
            target_location = FRT_4H_STRUCTURE_ID
        
        target_id , target_location = type_id, target_location  # replace with actual values

        # plex统一大市场，不需要进行位置筛选
        if type_id == 44992:
            target_location = None
        # 获取 is_buy_order=1 的最高价格
        max_price_buy = await MarketOrderCacheDBUtils.select_max_buy_by_type_id_and_location_id(target_id, target_location)
        
        # 获取 is_buy_order=0 的最低价格
        min_price_sell = await MarketOrderCacheDBUtils.select_min_sell_by_type_id_and_location_id(target_id, target_location)

        if not max_price_buy:
            max_price_buy = 0
        if not min_price_sell:
            min_price_sell = 0
        res = [float(max_price_buy), float(min_price_sell)]
        Market.order_rouge_cache[type_id] = res
        return res

    async def get_latest_order_by_type_id(self, type_id: int) -> tuple[list, list]:
        if self.market_type == "jita":
            target_location = JITA_TRADE_HUB_STRUCTURE_ID
        else:
            target_location = FRT_4H_STRUCTURE_ID

        if type_id == PLEX_ID:
            buy_order = await MarketOrderCacheDBUtils.select_5_buy_order_by_type_id(type_id)
            sell_order = await MarketOrderCacheDBUtils.select_5_sell_order_by_type_id(type_id)
        else:
            buy_order = await MarketOrderCacheDBUtils.select_5_buy_order_by_type_id_and_location_id(type_id, target_location)
            sell_order = await MarketOrderCacheDBUtils.select_5_sell_order_by_type_id_and_location_id(type_id, target_location)

        res = {
            'sell_order': {
                order.id: {
                    'price': order.price,
                    'volume_remain': order.volume_remain
                } for order in sell_order
            },
            'buy_order': {
                order.id: {
                    'price': order.price,
                    'volume_remain': order.volume_remain
                } for order in buy_order
            }
        }
        return res

class MarketHistory:
    @classmethod
    async def refresh_vale_market_history(cls, type_id_list: list):
        await cls.refresh_market_history(type_id_list, REGION_VALE_ID)

    @classmethod
    async def refresh_forge_market_history(cls, type_id_list: list):
        await cls.refresh_market_history(type_id_list, REGION_FORGE_ID)

    @classmethod
    async def refresh_market_history(cls, type_id_list: list, region_id: int):
        logger.info(f'刷新历史订单信息。id长度{len(type_id_list)}, region_id:{region_id}')
        # 创建频率限制器
        rate_limiter = RateLimiter(290)

        # 控制总体并发数
        max_concurrent = 100
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_limit(type_id):
            async with semaphore:
                await rate_limiter.acquire()
                try:
                    return await cls.refresh_type_history_in_region(type_id, region_id)
                except Exception as e:
                    logger.error(f"处理 type_id {type_id} 时出错: {e}")
                    return None

        with tqdm(total=len(type_id_list), desc="刷新历史订单", unit="item", ascii='=-') as pbar:
            # 创建所有任务但控制并发
            tasks = [process_with_limit(type_id) for type_id in type_id_list]
            # 使用as_completed可以让进度条更平滑地更新
            for future in asyncio.as_completed(tasks):
                await future
                pbar.update(1)

    @classmethod
    async def refresh_type_history_in_region(cls, type_id: int, region_id: int):
        result = await eveesi.markets_region_history(region_id, type_id, log=False)
        if not result:
            return
        [res.update({"type_id": type_id, 'region_id': region_id}) for res in result]

        await MarketHistoryDBUtils.insert_many_ignore_conflict(result)
        await RefreshDataDBUtils.update_refresh_date(cls.get_history_refreshdate_id(type_id, region_id), log=False)

    @classmethod
    def get_history_refreshdate_id(cls, type_id: int, region_id: int) -> str:
        history_id =f'markey_history_{type_id}_{region_id}'
        return history_id

    type_region_histpry_data_cache = TTLCache(maxsize=500, ttl=10 * 60 * 60)
    @classmethod
    async def get_type_region_history_data(cls, type_id: int, region_id: int) -> list:
        if (type_id, region_id) in cls.type_region_histpry_data_cache:
            return cls.type_region_histpry_data_cache[(type_id, region_id)]
        region_year_data = await MarketHistoryDBUtils.select_order_history_by_type_id_and_region_id(type_id, region_id)
        region_year_data_list = [[res.date, res.average, res.highest, res.lowest, res.volume] for res in region_year_data]

        cls.type_region_histpry_data_cache[(type_id, region_id)] = region_year_data_list
        return region_year_data_list

    @classmethod
    async def get_type_region_history_data_batch(cls, type_id_list: list, region_id: int) -> dict:
        need_refresh_list = [
            tid for tid in type_id_list if await RefreshDataDBUtils.out_of_day_interval(
                cls.get_history_refreshdate_id(tid, region_id), 1
            )
        ]
        if need_refresh_list:
            await cls.refresh_market_history(need_refresh_list, region_id)

        type_region_history_data = {
            tid: await cls.get_type_region_history_data(tid, region_id) for tid in type_id_list
        }

        return type_region_history_data

    type_history_detale_cache = TTLCache(maxsize=500, ttl=10 * 60 * 60)
    @classmethod
    async def get_type_history_detale(cls, type_id: int):
        if type_id in cls.type_history_detale_cache:
            return cls.type_history_detale_cache[type_id]
        # mkhist = model.MarketHistory
        week_ago = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=9)
        month_ago = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=32)
        year_ago = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=366)

        vale_week_data = await MarketHistoryDBUtils.select_order_history_before_date_by_type_id_and_region_id(week_ago, type_id, REGION_VALE_ID)
        vale_month_data = await MarketHistoryDBUtils.select_order_history_before_date_by_type_id_and_region_id(month_ago, type_id, REGION_VALE_ID)
        vale_year_data = await MarketHistoryDBUtils.select_order_history_before_date_by_type_id_and_region_id(year_ago, type_id, REGION_VALE_ID)
        vale_week_data_list = [[res.average, res.highest, res.lowest, res.order_count, res.volume] for res in vale_week_data]
        vale_month_data_list = [[res.average, res.highest, res.lowest, res.order_count, res.volume] for res in vale_month_data]
        vale_year_data_list = [[res.average, res.highest, res.lowest, res.order_count, res.volume] for res in vale_year_data]

        forge_week_data = await MarketHistoryDBUtils.select_order_history_before_date_by_type_id_and_region_id(week_ago, type_id, REGION_FORGE_ID)
        forge_month_data = await MarketHistoryDBUtils.select_order_history_before_date_by_type_id_and_region_id(month_ago, type_id, REGION_FORGE_ID)
        forge_year_data = await MarketHistoryDBUtils.select_order_history_before_date_by_type_id_and_region_id(year_ago, type_id, REGION_FORGE_ID)
        forge_week_data_list = [[res.average, res.highest, res.lowest, res.order_count, res.volume] for res in forge_week_data]
        forge_month_data_list = [[res.average, res.highest, res.lowest, res.order_count, res.volume] for res in forge_month_data]
        forge_year_data_list = [[res.average, res.highest, res.lowest, res.order_count, res.volume] for res in forge_year_data]

        vale_res ={}
        forge_res = {}

        count = 0
        flow = 0
        highest_average = 0
        lowest_average = 0
        total_volume = 0
        for data in vale_week_data_list:
            flow += data[0] * data[4]
            count += 1
            total_volume += data[4]
            highest_average += data[1]
            lowest_average += data[2]
        vale_res.update({
            'weekflow': flow,
            'week_highset_aver': highest_average / count if count else 0,
            'week_lowest_aver': lowest_average / count if count else 0,
            'week_volume': total_volume
        })

        count = 0
        flow = 0
        highest_average = 0
        lowest_average = 0
        total_volume = 0
        for data in vale_month_data_list:
            flow += data[0] * data[4]
            count += 1
            total_volume += data[4]
            highest_average += data[1]
            lowest_average += data[2]
        vale_res.update({
            'monthflow': flow,
            'month_highset_aver': highest_average / count if count else 0,
            'month_lowest_aver': lowest_average / count if count else 0,
            'month_volume': total_volume
        })

        count = 0
        flow = 0
        highest_average = 0
        lowest_average = 0
        total_volume = 0
        for data in vale_year_data_list:
            flow += data[0] * data[4]
            count += 1
            total_volume += data[4]
            highest_average += data[1]
            lowest_average += data[2]
        vale_res.update({
            'yearflow': flow,
            'year_highset_aver': highest_average / count if count else 0,
            'year_lowest_aver': lowest_average / count if count else 0,
            'year_volume': total_volume
        })

        count = 0
        flow = 0
        highest_average = 0
        lowest_average = 0
        total_volume = 0
        for data in forge_week_data_list:
            flow += data[0] * data[4]
            count += 1
            total_volume += data[4]
            highest_average += data[1]
            lowest_average += data[2]
        forge_res.update({
            'weekflow': flow,
            'week_highset_aver': highest_average / count if count else 0,
            'week_lowest_aver': lowest_average / count if count else 0,
            'week_volume': total_volume
        })

        count = 0
        flow = 0
        highest_average = 0
        lowest_average = 0
        total_volume = 0
        for data in forge_month_data_list:
            flow += data[0] * data[4]
            count += 1
            total_volume += data[4]
            highest_average += data[1]
            lowest_average += data[2]
        forge_res.update({
            'monthflow': flow,
            'month_highset_aver': highest_average / count if count else 0,
            'month_lowest_aver': lowest_average / count if count else 0,
            'month_volume': total_volume
        })

        count = 0
        flow = 0
        highest_average = 0
        lowest_average = 0
        total_volume = 0
        for data in forge_year_data_list:
            flow += data[0] * data[4]
            count += 1
            total_volume += data[4]
            highest_average += data[1]
            lowest_average += data[2]
        forge_res.update({
            'yearflow': flow,
            'year_highset_aver': highest_average / count if count else 0,
            'year_lowest_aver': lowest_average / count if count else 0,
            'year_volume': total_volume
        })

        res = [vale_res, forge_res]
        cls.type_history_detale_cache[type_id] = res
        return res


