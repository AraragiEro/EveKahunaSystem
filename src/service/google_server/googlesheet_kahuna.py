from tqdm import tqdm
from typing import Dict, List
import math
import asyncio
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# from ..database_server.utils import database_utils as dbutils
from .google_sheet_api import google_sheet_api
from ..sde_service import SdeUtils
from ..market_server.market_manager import MarketManager
from ..market_server.marker import MarketHistory
from ..industry_server.third_provider import provider_manager as pm
from ..config_server.config import config
from ..log_server import logger
# from ..database_server.utils import RefreshDateUtils
from ..database_server.sqlalchemy.kahuna_database_utils import MarketOrderCacheDBUtils, RefreshDataDBUtils
from ...utils import get_beijing_utctime


REGION_FORGE_ID = 10000002
REGION_VALE_ID = 10000003
JITA_TRADE_HUB_STRUCTURE_ID = 60003760
FRT_4H_STRUCTURE_ID = 1035466617946
B_9C24_KEEPSTAR_ID = 1046831245129

class KahunaGoogleSheetManager:
    def __init__(self):
        self.refresh_running = asyncio.Lock()
        self.sheet_api_test = False

    def test_google_sheet_api(self):
        try:
            spreadsheet_id = config['GOOGLE']['MARKET_MONITOR_SPREADSHEET_ID']
            server = google_sheet_api.server
            server.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    'data': [
                        {
                            'majorDimension': 'ROWS',
                            'range': '欢迎！先看这里!A18',
                            'values': [['链接测试', get_beijing_utctime(datetime.now()).strftime('%Y-%m-%d %H:%M:%S')]]
                        }
                    ],
                    'valueInputOption': 'USER_ENTERED'
                }
            ).execute()

            self.sheet_api_test = True
        except Exception as e:
            logger.error(e)
            raise e
        finally:
            pass

    def write_data_to_monitor(self, spreadsheet_id, data):
        server = google_sheet_api.server

        try:
            server.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range='市场'
            ).execute()
        except Exception as e:
            logger.error("清空 google sheet 市场 失败")
            raise

        try:
            server.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=data
            ).execute()
        except Exception as e:
            logger.error('写入 googlesheet 市场 失败')
            raise

    """
    表1： 市场
    """
    async def output_4h_market_data(self):
        frt_4h_order = await MarketOrderCacheDBUtils.select_order_by_location_id(FRT_4H_STRUCTURE_ID)
        jita_market = MarketManager.get_market_by_type('jita')
        pl_asset = await pm.get_all_assets()

        important_list = SdeUtils.get_important_type_id_in_market()
        order_cache = list(frt_4h_order)
        data1 = {}
        await MarketHistory.get_type_region_history_data_batch(important_list, REGION_FORGE_ID)
        await MarketHistory.get_type_region_history_data_batch(important_list, REGION_VALE_ID)
        important_not_have_order_set = set(important_list) - set([order.type_id for order in frt_4h_order])
        important_not_have_order_list = list(important_not_have_order_set)
        with tqdm(total=len(order_cache), desc="处理联盟历史订单", unit="order", ascii='=-') as pbar:
            for order in order_cache:
                pbar.update()
                if int(order.is_buy_order) == 1:
                    continue
                if int(order.type_id) not in important_list:
                    continue
                if order.type_id not in data1:
                    data1[order.type_id] = {
                        'type_id': int(order.type_id),
                        'volume_remain': int(order.volume_remain),
                        '4h_max_price': float(order.price),
                        '4h_min_price': float(order.price),
                        'jita_price': await jita_market.get_type_order_rouge(int(order.type_id)),
                        'type_market_history': (await MarketHistory.get_type_history_detale(int(order.type_id)))[0]
                    }
                    continue

                data1[order.type_id]['volume_remain'] += int(order.volume_remain)
                data1[order.type_id]['4h_max_price'] = max(data1[order.type_id]['4h_max_price'], float(order.price))
                data1[order.type_id]['4h_min_price'] = min(data1[order.type_id]['4h_min_price'], float(order.price))

        with tqdm(total=len(important_not_have_order_list), desc="处理无订单但有流水的物品", unit="order", ascii='=-') as pbar:
            for tid in important_not_have_order_list:
                pbar.update()
                if tid in data1:
                    continue
                data1[tid] = {
                    'type_id': tid,
                    'volume_remain': 0,
                    '4h_max_price': 0,
                    '4h_min_price': 0,
                    'jita_price': await jita_market.get_type_order_rouge(tid),
                    'type_market_history': (await MarketHistory.get_type_history_detale(tid))[0]
                }

        head = [
            'typeID',
            'name',
            '物品名',
            '卖单数量',
            '卖单余量时间',
            '周月日均销量变化',
            '4H最低价',
            '4H最高价',
            'jitasell',
            '溢价倍率',
            'jita溢价指数',
            '7天交易量',
            '7天均价',
            '7天流水',
            '30天交易量',
            '30天均价',
            '30天流水',
            '年交易量',
            '年均价',
            '年流水',
            '缺货指数',
            '赚钱指数',
            '坏比指数',
            '建制标',
            '低价因数',
            '销量因数',
            'PL库存',
            'catagory',
            'metaGroup',
            'jitabuy',
            'group_name'
        ]

        data2 = [
            self.get_data_row(tid, data, pl_asset) for tid, data in data1.items()
        ]

        return [head] + data2

    def get_data_row(self, tid: int, data: Dict, pl_asset):
        sell_volume_remain_time = data['volume_remain'] / data['type_market_history']['month_volume'] * 365 if data['type_market_history']['month_volume'] != 0 else 0
        week_month_volume_change = (data['type_market_history']['week_volume'] / 7 - data['type_market_history']['month_volume'] / 30) / (data['type_market_history']['month_volume'] / 30) \
                                    if data['type_market_history']['month_volume'] != 0 else 0
        premiu_ratio = (data['4h_min_price'] - data['jita_price'][1]) / data['jita_price'][1] if data['jita_price'][1] !=0 else 0
        low_price_index = 1 / max(1, min(100, -0.001 * data['jita_price'][1] + 101))
        sell_volume_index = 1 / max(1, min(2, -0.0000000025 * data['type_market_history']['month_volume'] + 2.25))

        pl_asset_quantity = pl_asset.get('PL', 0)
        if pl_asset_quantity:
            pl_asset_quantity = pl_asset.get(tid, 0)
        def calculate_formula(q2, f2, j2, i2):
            """赚钱指数: Q2 * EXP(-ABS(F2)) * (1 / (1 + EXP(-(J2/I2))))"""
            if i2 == 0:
                i2 = data['type_market_history']['month_volume'] / 30 * 7
            if i2 == 0:
                return 0

            return q2 * math.exp(-abs(f2)) * (1 / (1 + math.exp(-(j2 / i2))))

        res = [
                tid,
                SdeUtils.get_name_by_id(tid),
                SdeUtils.get_cn_name_by_id(tid),
                data['volume_remain'],
                sell_volume_remain_time,
                week_month_volume_change,
                data['4h_min_price'],
                data['4h_max_price'],
                data['jita_price'][1],
                premiu_ratio,  #溢价倍率
                min(low_price_index, sell_volume_index) * premiu_ratio,  #jita溢价指数
                data['type_market_history']['week_volume'],
                (data['type_market_history']['week_highset_aver'] + data['type_market_history']['week_lowest_aver']) / 2,
                data['type_market_history']['weekflow'],
                data['type_market_history']['month_volume'],
                (data['type_market_history']['month_highset_aver'] + data['type_market_history']['month_lowest_aver']) / 2,
                data['type_market_history']['monthflow'],
                data['type_market_history']['year_volume'],
                (data['type_market_history']['year_highset_aver'] + data['type_market_history']['year_lowest_aver']) / 2,
                data['type_market_history']['yearflow'],
                7 - sell_volume_remain_time,
                calculate_formula(data['type_market_history']['monthflow'], week_month_volume_change, premiu_ratio, data['jita_price'][1]),
                (data['4h_min_price'] + data['4h_max_price']) / 2 / data['jita_price'][1] if data['jita_price'][1] != 0 else 0 ,
                '', # 建制标记
                low_price_index,
                sell_volume_index,
                pl_asset_quantity,
                SdeUtils.get_category_by_id(tid),
                '' if not SdeUtils.get_metaname_by_typeid(tid) else SdeUtils.get_metaname_by_typeid(tid),
                data['jita_price'][0],
                SdeUtils.get_groupname_by_id(tid)
            ]

        return res

    async def output_B_9_order(self):
        header = ['id', 'is_buy_order', 'issued', 'volume_remain', 'type_id', 'price']

        b_9_order = await MarketOrderCacheDBUtils.select_order_by_location_id(B_9C24_KEEPSTAR_ID)
        b_9_order = list(b_9_order)
        res = [header]
        for data in b_9_order:
            if int(data.is_buy_order) == 1:
                continue
            res.append([
                data.id,
                int(data.is_buy_order),
                data.issued,
                data.volume_remain,
                data.type_id,
                data.price,
            ])
        return res

    async def refresh_market_monitor(self):
        start = datetime.now()

        try:
            # 在事件循环中运行异步函数
            # 4H市场订单详细数据
            res = await self.output_4h_market_data()

            # B-9订单粗略数据
            B_9_order_data = await self.output_B_9_order()

            spreadsheet_id = config['GOOGLE']['MARKET_MONITOR_SPREADSHEET_ID']

            data = {
                'data': [
                    {
                        'majorDimension': 'ROWS',
                        'range': '市场',
                        'values': res
                    },
                    {
                        'majorDimension': 'ROWS',
                        'range': '欢迎！先看这里!A17',
                        'values': [['最后更新:', get_beijing_utctime(datetime.now()).strftime('%Y-%m-%d %H:%M:%S')]]
                    },
                    {
                        'majorDimension': 'ROWS',
                        'range': 'B-9订单数据',
                        'values': B_9_order_data
                    },
                ],
                'valueInputOption': 'USER_ENTERED'
            }
            self.write_data_to_monitor(spreadsheet_id, data)

            logger.info(f'向市场监视器插入 {len(res)}行, {len(res) * len(res[0])}行数据. 耗时{datetime.now() - start}')
        except Exception as e:
            logger.error(e)
            raise e

    async def refresh_market_monitor_process(self, force=False):
        if self.refresh_running.locked():
            return
        async with self.refresh_running:
            if not self.sheet_api_test:
                self.test_google_sheet_api()
                if not self.sheet_api_test:
                    logger.error('google_sheet_api test not pass.')
                    return

            if not force and not await RefreshDataDBUtils.out_of_hour_interval('market_monitor', 2):
                return
            if not config.has_option('GOOGLE', 'MARKET_MONITOR_SPREADSHEET_ID'):
                logger.info(f'未设置市场监视器googleid.')
                return

            await self.refresh_market_monitor()

            await RefreshDataDBUtils.update_refresh_date('market_monitor')

kahuna_google_market_monitor = KahunaGoogleSheetManager()