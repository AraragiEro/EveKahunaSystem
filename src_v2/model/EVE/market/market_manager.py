
import asyncio
from datetime import datetime, timedelta, timezone

# from .marker import Market
from src_v2.core.database.connect_manager import get_redis_manager
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.core.config.config import config, update_config
#import Exception
from src_v2.core.utils import KahunaException, SingletonMeta, tqdm_manager

from src_v2.model.EVE.eveesi import eveesi
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveMarketRegionHistoryStatisticDBUtils,
    EveMarketRegionOrdersDBUtils,
)
from src_v2.core.database import model

# kahuna logger
from src_v2.core.log import logger

REGION_FORGE_ID = 10000002
REGION_VALE_ID = 10000003
REGION_PLEX_ID = 19000001
JITA_TRADE_HUB_STRUCTURE_ID = 60003760
JITA_SYSTEM_ID = 30000142
PERIMETER_SYSTEM_ID = 30000144
PLEX_ID = 44992
FRT_4H_STRUCTURE_ID = 1035466617946
S33RB_O_STRUCTURE_ID = 1045441547980
B_9C24_KEEPSTAR_ID = 1046831245129
PIMI_STRUCTURE_LIST = [1042508032148, 1042499803831, 1044752365771]

class MarketManager(metaclass=SingletonMeta):
    def __init__(self):
        self.update_jita_price_lock = asyncio.Lock()
        self.update_frt_price_lock = asyncio.Lock()

    async def _save_orders_to_database(self, region_id: int, orders: list[dict]):
        """
        将指定 region 的订单原始数据写入 PostgreSQL。
        写入前会删除该 region 的所有历史订单。

        :param region_id: 区域 ID
        :param orders: 订单列表，元素示例：
            {
                "duration": 90,
                "is_buy_order": false,
                "issued": "2025-10-08T09:58:38Z",
                "location_id": 60003760,
                "min_volume": 1,
                "order_id": 7157579777,
                "price": 34000000,
                "range": "region",
                "system_id": 30000142,
                "type_id": 89953,
                "volume_remain": 1,
                "volume_total": 1
            }
        """
        if not orders:
            return

        try:
            # 先删除该 region 的历史订单
            await EveMarketRegionOrdersDBUtils.delete_by_region_id(region_id)

            now = datetime.utcnow()
            rows: list[dict] = []
            for order in orders:
                try:
                    issued_raw = order.get("issued")
                    issued_dt = None
                    if isinstance(issued_raw, str):
                        # 处理带 Z 的 ISO 字符串
                        issued_str = issued_raw.replace("Z", "+00:00")
                        issued_dt = datetime.fromisoformat(issued_str)
                        # 如果是 offset-aware，转换为 UTC 后移除时区信息
                        if issued_dt.tzinfo is not None:
                            issued_dt = issued_dt.astimezone(timezone.utc).replace(tzinfo=None)
                    elif isinstance(issued_raw, datetime):
                        issued_dt = issued_raw
                        # 如果是 offset-aware，转换为 UTC 后移除时区信息
                        if issued_dt.tzinfo is not None:
                            issued_dt = issued_dt.astimezone(timezone.utc).replace(tzinfo=None)

                    row = {
                        "order_id": order["order_id"],
                        "type_id": order["type_id"],
                        "region_id": region_id,
                        "system_id": order.get("system_id"),
                        "location_id": order.get("location_id"),
                        "price": order["price"],
                        "volume_total": order["volume_total"],
                        "volume_remain": order["volume_remain"],
                        "min_volume": order["min_volume"],
                        "is_buy_order": order["is_buy_order"],
                        "duration": order["duration"],
                        "issued": issued_dt,
                        "range": order.get("range"),
                        "created_at": now,
                        "updated_at": now,
                    }
                except Exception as e:
                    logger.error(f"转换订单数据失败 region_id={region_id}, order_id={order.get('order_id')}: {e}", exc_info=True)
                    raise

                rows.append(row)
            
            await tqdm_manager.add_mission(f"save_orders_to_database_{region_id}", len(rows))
            if rows:
                # 分批插入，避免超过 PostgreSQL 参数限制（32767个参数）
                # 每个订单有15个字段，所以每批最多 2000 条订单（2000 * 15 = 30000 < 32767）
                batch_size = 2000
                total_rows = len(rows)
                semaphore = asyncio.Semaphore(2)

                async def _insert_batch_with_semaphore(batch: list):
                    async with semaphore:
                        await EveMarketRegionOrdersDBUtils.insert_many(batch)
                        logger.debug(f"成功插入订单批次 region_id={region_id}, 批次 {i//batch_size + 1}/{(total_rows + batch_size - 1)//batch_size}, 数量={len(batch)}")
                        await tqdm_manager.update_mission(f"save_orders_to_database_{region_id}", len(batch))

                tasks = []
                for i in range(0, total_rows, batch_size):
                    batch = rows[i:i + batch_size]
                    task = asyncio.create_task(_insert_batch_with_semaphore(batch))
                    tasks.append(task)
                await asyncio.gather(*tasks)
            await tqdm_manager.complete_mission(f"save_orders_to_database_{region_id}")
        except Exception as e:
            # 写库失败不影响后续 Redis 逻辑
            logger.error(
                f"写入区域市场订单数据失败 region_id={region_id}: {e}",
                exc_info=True,
            )

    async def _batch_insert_redis(self, market_zone: str, batch: list):
        """批量插入Redis的辅助方法"""
        for type_id, price_data in batch:
            await get_redis_manager().r.hset(f"market_price:{market_zone}:{type_id}", mapping=price_data)

    async def update_market_price(self, market_zone: str, main_character_id: int = None):
        if market_zone == "jita":
            await self.update_jita_price()
        elif market_zone == "frt":
            await self.update_frt_price(main_character_id=main_character_id)
        # elif market_zone == "B-9":
        #     await self.update_b9_price()
        else:
            raise KahunaException(f"不支持的市场区域: {market_zone}")

    async def update_frt_price(self, main_character_id: int = None):
        # 检查角色授权
        if not main_character_id:
            raise KahunaException("拉取区域市场需要绑定主角色")
        character = await CharacterManager().get_character_by_character_id(main_character_id)
        if not character:
            raise KahunaException("主角色不存在")
        if not await character.ac_token:
            raise KahunaException("主角色没有授权")

        async with self.update_frt_price_lock:
            update_flag = await get_redis_manager().r.get(f"market_update_flag:frt")
            if update_flag:
                return

        type_price_cache = {}
        frt_order = await eveesi.markets_structures(character.ac_token, FRT_4H_STRUCTURE_ID)

        # 扁平化订单列表，便于写库
        flat_frt_orders: list[dict] = []
        for order_list in frt_order:
            for order in order_list:
                flat_frt_orders.append(order)

                if order["type_id"] not in type_price_cache:
                    type_price_cache[order["type_id"]] = {
                        "max_buy": 0,
                        "min_sell": 1000000000000000000000,
                    }
                else:
                    if order["is_buy_order"]:
                        type_price_cache[order["type_id"]]["max_buy"] = max(
                            type_price_cache[order["type_id"]]["max_buy"], order["price"]
                        )
                    else:
                        type_price_cache[order["type_id"]]["min_sell"] = min(
                            type_price_cache[order["type_id"]]["min_sell"], order["price"]
                        )

        # 保存原始订单到 Postgre
        await self._save_orders_to_database(REGION_VALE_ID, flat_frt_orders)
        
        # 分批处理并并发插入Redis
        batch_size = 100  # 每批处理100个type_id
        items = list(type_price_cache.items())
        tasks = []
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            task = asyncio.create_task(self._batch_insert_redis("frt", batch))
            tasks.append(task)
        
        # 等待所有批次完成
        await asyncio.gather(*tasks)
        
        await get_redis_manager().r.set(f"market_update_flag:frt", "1", ex=60*60*1)

    async def update_jita_price(self, rdm=None):
        if rdm:
            rdm = rdm
        else:
            rdm = get_redis_manager()
        async with self.update_jita_price_lock:
            update_flag = await rdm.r.get(f"market_update_flag:jita")
            if update_flag:
                return

        type_price_cache = {}
        jita_order = await eveesi.markets_region_orders(REGION_FORGE_ID)

        # 仅保留 Jita 交易中心的订单，并构造用于写库的列表
        flat_jita_orders: list[dict] = []
        for order_list in jita_order:
            for order in order_list:
                if not order['is_buy_order'] and order["location_id"] != JITA_TRADE_HUB_STRUCTURE_ID:
                    continue
                elif order['is_buy_order'] and order["system_id"] not in [JITA_SYSTEM_ID, PERIMETER_SYSTEM_ID]:
                    continue

                flat_jita_orders.append(order)

                if order["type_id"] not in type_price_cache:
                    type_price_cache[order["type_id"]] = {
                        "max_buy": 0,
                        "min_sell": 1000000000000,
                    }
                else:
                    if order["is_buy_order"]:
                        type_price_cache[order["type_id"]]["max_buy"] = max(
                            type_price_cache[order["type_id"]]["max_buy"], order["price"]
                        )
                    else:
                        type_price_cache[order["type_id"]]["min_sell"] = min(
                            type_price_cache[order["type_id"]]["min_sell"], order["price"]
                        )

        # 保存原始订单到 Postgre
        await self._save_orders_to_database(REGION_FORGE_ID, flat_jita_orders)
        
        # 分批处理并并发插入Redis
        batch_size = 100  # 每批处理100个type_id
        items = list(type_price_cache.items())
        tasks = []
        
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            task = asyncio.create_task(self._batch_insert_redis("jita", batch))
            tasks.append(task)
        
        # 等待所有批次完成
        await asyncio.gather(*tasks)

        await get_redis_manager().r.set(f"market_update_flag:jita", "1", ex=60*60*2)

    async def update_type_id_market_region_history(self, type_id: int, region_id: int):
        """
        使用 ESI API 获取指定 type_id 在指定 region 的历史市场统计数据并入库。

        数据写入到 Postgre 表 `eve_market_region_history_statistic`，
        以 (type_id, region_id, date) 作为唯一键做插入/更新。
        """
        try:
            # 调用 ESI 接口获取历史数据
            history_list = await eveesi.markets_region_history(
                region_id, type_id, log=False
            )
        except Exception as e:
            logger.error(
                f"获取市场历史数据失败 type_id={type_id}, region_id={region_id}: {e}",
                exc_info=True,
            )
            return

        if not history_list:
            return

        rows: list[dict] = []
        for item in history_list:
            # 复制一份，避免直接修改原始数据
            row = dict(item)
            row["type_id"] = type_id
            row["region_id"] = region_id

            # 将字符串日期转换为 date 对象（格式示例："2024-11-01"）
            date_str = row.get("date")
            if isinstance(date_str, str):
                try:
                    row["date"] = datetime.strptime(date_str, "%Y-%m-%d").date()
                except Exception:
                    # 如果解析失败，记录日志并跳过该条记录
                    logger.warning(
                        f"解析历史数据日期失败 type_id={type_id}, region_id={region_id}, date={date_str}"
                    )
                    continue

            rows.append(row)

        if not rows:
            return

        try:
            # 基于 (type_id, region_id, date) 做 upsert
            await EveMarketRegionHistoryStatisticDBUtils.insert_many_or_update(rows)
        except Exception as e:
            logger.error(
                f"写入市场历史统计数据失败 type_id={type_id}, region_id={region_id}: {e}",
                exc_info=True,
            )

    async def update_type_id_list_market_region_history(
        self, type_id_list: list, region_id: int
    ):
        """
        批量更新多个 type_id 在指定 region 的市场历史统计数据。

        使用异步“线程池”/任务池方式并发执行，最大并发数 20。
        """
        if not type_id_list:
            return

        semaphore = asyncio.Semaphore(20)
        await tqdm_manager.add_mission(f"update_type_id_list_market_region_history_{region_id}", len(type_id_list))
        async def _worker(tid: int):
            async with semaphore:
                try:
                    await self.update_type_id_market_region_history(tid, region_id)
                except Exception as e:
                    logger.error(
                        f"批量更新市场历史数据单项失败 type_id={tid}, region_id={region_id}: {e}",
                        exc_info=True,
                    )
                await tqdm_manager.update_mission(f"update_type_id_list_market_region_history_{region_id}", 1)
        tasks = [asyncio.create_task(_worker(tid)) for tid in type_id_list]
        await asyncio.gather(*tasks)
        await tqdm_manager.complete_mission(f"update_type_id_list_market_region_history_{region_id}")

    async def update_type_id_history_detale(self, region_id: int, type_id: int):
        """
        计算指定 type_id 在指定 region 的市场历史统计数据。
        
        计算过去7天和30天的均价（加权平均，基于volume）和总交易量。
        排除最近2天的数据（最近2天没有数据）。
        
        过去7天：过去2日到过去9日
        过去30天：过去2日到过去32日
        
        结果保存到Redis：
        - market_region_history:{region_id}:{type_id}:7DAverPrice
        - market_region_history:{region_id}:{type_id}:7DTotalVolume
        - market_region_history:{region_id}:{type_id}:30DAverPrice
        - market_region_history:{region_id}:{type_id}:30DTotalVolume
        """
        try:
            # 获取当前时间（+8时区）
            tz = timezone(timedelta(hours=8))
            now = datetime.now(tz)
            
            # 计算日期范围
            # 过去2日到过去9日（7天数据）
            end_date_7d = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            start_date_7d = (now - timedelta(days=9)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # 过去2日到过去32日（30天数据）
            end_date_30d = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            start_date_30d = (now - timedelta(days=32)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # 移除时区信息，因为数据库字段是 TIMESTAMP WITHOUT TIME ZONE
            end_date_7d = end_date_7d.replace(tzinfo=None)
            start_date_7d = start_date_7d.replace(tzinfo=None)
            end_date_30d = end_date_30d.replace(tzinfo=None)
            start_date_30d = start_date_30d.replace(tzinfo=None)
            
            # 查询数据库
            records_7d = await EveMarketRegionHistoryStatisticDBUtils.get_records_by_date_range(
                type_id=type_id,
                region_id=region_id,
                start_date=start_date_7d,
                end_date=end_date_7d,
            )
            
            records_30d = await EveMarketRegionHistoryStatisticDBUtils.get_records_by_date_range(
                type_id=type_id,
                region_id=region_id,
                start_date=start_date_30d,
                end_date=end_date_30d,
            )
            
            # 计算7天统计
            total_volume_7d = 0
            weighted_sum_7d = 0.0
            for record in records_7d:
                total_volume_7d += record.volume
                weighted_sum_7d += record.average * record.volume
            
            # 计算30天统计
            total_volume_30d = 0
            weighted_sum_30d = 0.0
            for record in records_30d:
                total_volume_30d += record.volume
                weighted_sum_30d += record.average * record.volume
            
            # 计算加权平均价格
            avg_price_7d = weighted_sum_7d / total_volume_7d if total_volume_7d > 0 else 0.0
            avg_price_30d = weighted_sum_30d / total_volume_30d if total_volume_30d > 0 else 0.0
            
            # 保存到Redis
            redis_key_base = f"market_region_history:{region_id}:{type_id}"
            await get_redis_manager().r.set(f"{redis_key_base}:7DAverPrice", str(avg_price_7d))
            await get_redis_manager().r.set(f"{redis_key_base}:7DTotalVolume", str(total_volume_7d))
            await get_redis_manager().r.set(f"{redis_key_base}:30DAverPrice", str(avg_price_30d))
            await get_redis_manager().r.set(f"{redis_key_base}:30DTotalVolume", str(total_volume_30d))
            
        except Exception as e:
            logger.error(
                f"计算市场历史统计数据失败 type_id={type_id}, region_id={region_id}: {e}",
                exc_info=True,
            )

    async def get_type_id_history_detail(self, region_id: int, type_id: int) -> dict:
        """
        从 Redis 读取指定 type_id 在指定 region 的市场历史统计数据。
        
        :param region_id: 区域ID
        :param type_id: 物品类型ID
        :return: 包含历史统计数据的字典，如果数据不存在则返回默认值
        """
        redis_key_base = f"market_region_history:{region_id}:{type_id}"
        
        # 从 Redis 读取数据，如果为 None 则使用默认值 0.0
        avg_price_7d_str = await get_redis_manager().r.get(f"{redis_key_base}:7DAverPrice")
        avg_price_30d_str = await get_redis_manager().r.get(f"{redis_key_base}:30DAverPrice")
        total_volume_7d_str = await get_redis_manager().r.get(f"{redis_key_base}:7DTotalVolume")
        total_volume_30d_str = await get_redis_manager().r.get(f"{redis_key_base}:30DTotalVolume")
        
        try:
            avg_price_7d = float(avg_price_7d_str) if avg_price_7d_str is not None else 0.0
        except (ValueError, TypeError):
            avg_price_7d = 0.0
            
        try:
            avg_price_30d = float(avg_price_30d_str) if avg_price_30d_str is not None else 0.0
        except (ValueError, TypeError):
            avg_price_30d = 0.0
            
        try:
            total_volume_7d = float(total_volume_7d_str) if total_volume_7d_str is not None else 0.0
        except (ValueError, TypeError):
            total_volume_7d = 0.0
            
        try:
            total_volume_30d = float(total_volume_30d_str) if total_volume_30d_str is not None else 0.0
        except (ValueError, TypeError):
            total_volume_30d = 0.0
        
        return {
            'avg_price_7d': avg_price_7d,
            'avg_price_30d': avg_price_30d,
            'total_volume_7d': total_volume_7d,
            'total_volume_30d': total_volume_30d
        }

    async def update_type_id_list_history_detale(self, region_id: int, type_id_list: list, force: bool = False):
        """
        批量计算多个 type_id 在指定 region 的市场历史统计数据。
        
        先检查Redis标志 market_region_history_detail_update:flag:{region_id}，
        如果存在则跳过。所有计算完成后，设置Redis标志，过期时间为次日凌晨2点（+8时区）。
        """
        if not type_id_list:
            return
        
        # 检查Redis标志
        flag_key = f"market_region_history_detail_update:flag:{region_id}"
        update_flag = await get_redis_manager().r.get(flag_key)
        if update_flag and not force:
            logger.debug(f"检测到市场历史统计更新标志已存在 region_id={region_id}，跳过本次执行")
            return
        
        try:
            # 批量处理，使用异步并发
            semaphore = asyncio.Semaphore(20)
            await tqdm_manager.add_mission(f"update_type_id_list_history_detale_{region_id}", len(type_id_list))
            
            async def _worker(tid: int):
                async with semaphore:
                    try:
                        await self.update_type_id_history_detale(region_id, tid)
                    except Exception as e:
                        logger.error(
                            f"批量计算市场历史统计数据单项失败 type_id={tid}, region_id={region_id}: {e}",
                            exc_info=True,
                        )
                    await tqdm_manager.update_mission(f"update_type_id_list_history_detale_{region_id}", 1)
            
            tasks = [asyncio.create_task(_worker(tid)) for tid in type_id_list]
            await asyncio.gather(*tasks)
            await tqdm_manager.complete_mission(f"update_type_id_list_history_detale_{region_id}")
            
            # 计算过期时间（次日凌晨2点，+8时区）
            tz = timezone(timedelta(hours=8))
            now = datetime.now(tz)
            tomorrow = now + timedelta(days=1)
            tomorrow_target = tomorrow.replace(hour=2, minute=0, second=0, microsecond=0)
            delta = tomorrow_target - now
            expire_seconds = int(delta.total_seconds())
            
            # 设置Redis标志
            await get_redis_manager().r.set(flag_key, "1", ex=expire_seconds)
            logger.info(f"市场历史统计计算完成 region_id={region_id}，已设置Redis标志，过期时间: {expire_seconds} 秒后（次日凌晨2点）")
            
        except Exception as e:
            logger.error(
                f"批量计算市场历史统计数据失败 region_id={region_id}: {e}",
                exc_info=True,
            )
            # 即使失败也设置一个较短的过期时间，避免一直重试
            try:
                await get_redis_manager().r.set(flag_key, "1", ex=3600)  # 1小时后过期
            except Exception as redis_error:
                logger.error(f"设置Redis标志失败: {redis_error}", exc_info=True)

    async def get_jita_buy_price(self, type_id: int) -> float:
        price = await get_redis_manager().r.hget(f"market_price:jita:{type_id}", "max_buy")
        if not price:
            return 0
        return float(price)

    async def get_jita_sell_price(self, type_id: int) -> float:
        price = await get_redis_manager().r.hget(f"market_price:jita:{type_id}", "min_sell")
        if not price:
            return 0
        return float(price)