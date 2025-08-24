from gzip import FTEXT
from typing import Any, Coroutine
from datetime import datetime, timedelta

from ..evesso_server import eveesi
from ..log_server import logger
from ..character_server.character_manager import Character, CharacterManager
from ..user_server.user_manager import User, UserManager
from ..evesso_server.eveutils import parse_iso_datetime
from ..sde_service import SdeUtils
from ..market_server.marker import FRT_4H_STRUCTURE_ID, JITA_TRADE_HUB_STRUCTURE_ID, MarketHistory, REGION_VALE_ID, REGION_FORGE_ID
from ..market_server.market_manager import MarketManager
from ..industry_server.structure import StructureManager
from ...utils import get_beijing_utctime
from ..database_server.sqlalchemy.kahuna_database_utils import (
    OrderHistoryDBUtils, OrderHistory,
    RefreshDataDBUtils
)

class OrderManager:
    def __init__(self):
        pass

    async def get_character_orders(self, character: Character):
        results = await eveesi.characters_character_orders(character.ac_token, character.character_id)
        if not results:
            return []
        for res in results:
            if 'is_buy_order' not in res:
                res.update({
                    'escrow': 0.0,
                    'is_buy_order': False,
                    'min_volume': 0
                })
            res.update({
                'owner_id': character.character_id,
                "issued": get_beijing_utctime(parse_iso_datetime(res['issued']))
            })
        return results

    async def get_order_of_user(self, user: User) -> list:
        character_list = CharacterManager.get_all_characters_of_user(user.user_qq)
        orders = []
        for character in character_list:
            orders.extend(await self.get_character_orders(character))
        return orders

    async def refresh_character_order_history(self, character: Character):
        logger.info(f"开始刷新角色 {character.character_name} 的订单历史")
        results = await eveesi.characters_character_orders_history(
            character.ac_token,
            character.character_id
        )
        for result in results:
            for data in result:
                data.update({
                    'owner_id': character.character_id,
                    "issued": get_beijing_utctime(parse_iso_datetime(data['issued']))
                })
                if 'is_buy_order' not in data:
                    data.update({
                        'escrow': 0.0,
                        'is_buy_order': False,
                        'min_volume': 0
                    })
            if result:
                await OrderHistoryDBUtils.insert_many_ignore_conflict(result)

        logger.info(f'{character.character_name} 刷新订单 {len(results)} 页')

    async def refresh_order_history_of_user(self, user: User, force=False):
        if not force and not await RefreshDataDBUtils.out_of_day_interval(f'order_history_{user.user_qq}', 1):
            return
        logger.info(f"开始刷新 {user.user_qq} 的订单历史")
        character_list = CharacterManager.get_all_characters_of_user(user.user_qq)
        for character in character_list:
            await self.refresh_character_order_history(character)

        await RefreshDataDBUtils.update_refresh_date(f'order_history_{user.user_qq}')

    async def refresh_all_order(self, force=False):
        logger.info("开始刷新订单历史")
        user_list = UserManager.get_users_list()
        for user in user_list:
            await self.refresh_order_history_of_user(user, force=force)

    async def get_month_order_history_of_user(self, user: User):
        month_ago = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=32)
        character_list = CharacterManager.get_all_characters_of_user(user.user_qq)

        res = await OrderHistoryDBUtils.select_order_history_by_owner_id_list(
            [character.character_id for character in character_list]
        )
        res = [order for order in res if order.issued >= month_ago]
        return res

    async def filt_order_of_location_id(self, order_data: list[dict], location_id: int, is_buy_order=False, alias_location_list: list = []) -> list[Any] | None:
        if location_id not in {FRT_4H_STRUCTURE_ID, JITA_TRADE_HUB_STRUCTURE_ID}:
            logger.error("暂不支持除联盟市场和jita市场的订单统计")
            return []
        if location_id == FRT_4H_STRUCTURE_ID:
            market = MarketManager.get_market_by_type('frt')
        else:
            market = MarketManager.get_market_by_type('jita')

        structure = await StructureManager.get_structure(location_id)
        if structure:
            structure_name = structure.name
        else:
            structure_name = 'unknown structure'

        filt_order = [{
            'type_id': order['type_id'],
            'name': SdeUtils.get_name_by_id(order['type_id']),
            'icon': '',
            'structure_name': structure_name,
            'volume_total': order['volume_total'],
            'volume_remain': order['volume_remain'],
            'price': order['price'],
            'min_price': (await market.get_type_order_rouge(order['type_id']))[1],
            'max_price': (await market.get_type_order_rouge(order['type_id']))[0],
            'issued': order['issued'],
            'duration': order['duration']
        } for order in order_data if order['is_buy_order'] is is_buy_order and (order['location_id'] == location_id or order['location_id'] in alias_location_list)]
        filt_order.sort(key=lambda x: x['type_id'], reverse=False)

        if is_buy_order:
            res = filt_order
        else:
            res = {}
            for order in filt_order:
                if order['type_id'] not in res:
                    res[order['type_id']] = order
                    continue
                if order['price'] < res[order['type_id']]['price']:
                    res[order['type_id']] = order
            res = [order for order in res.values()]
            res.sort(key=lambda x: x['type_id'], reverse=False)
        return res

    async def analyse_month_order_statistic(self, order_data: list, month_prder_history: list[OrderHistory]):
        """
        需要计算的有：
            出单求和
            出单分类
                按照出售建筑分类
                按照物品种类分类
                每种物品占各自的月流水占比

            收单求和
        """
        sell_total = 0
        sell_type_data = {}
        sell_structure_data = {}
        sell_group_data = {}

        frt_market = MarketManager.get_market_by_type('frt')
        jiata_market = MarketManager.get_market_by_type('jita')

        order_type_id = list({order.type_id for order in month_prder_history})
        await MarketHistory.get_type_region_history_data_batch(order_type_id, REGION_VALE_ID)
        await MarketHistory.get_type_region_history_data_batch(order_type_id, REGION_FORGE_ID)
        for h_order_data in month_prder_history:
            if h_order_data.is_buy_order:
                continue
            structure = await StructureManager.get_structure(h_order_data.location_id)
            if not structure:
                continue
            group_name = SdeUtils.get_groupname_by_id(h_order_data.type_id, zh=True)
            sell_profit = h_order_data.price * (h_order_data.volume_total - h_order_data.volume_remain)
            history_detel = await MarketHistory.get_type_history_detale(h_order_data.type_id)
            if h_order_data.location_id == FRT_4H_STRUCTURE_ID:
                history_data = history_detel[0]
            else:
                history_data = history_detel[1]

            # 总价统计
            sell_total += sell_profit
            # 物品分类
            if h_order_data.type_id not in sell_type_data:
                sell_type_data[h_order_data.type_id] = {
                    'type_id': h_order_data.type_id,
                    'name': SdeUtils.get_name_by_id(h_order_data.type_id),
                    'icon': '',
                    'sell_volume': 0,
                    'sell_profit': 0,
                    'market_total_month_flow': history_data['monthflow']
                }
            sell_type_data[h_order_data.type_id]['sell_volume'] += h_order_data.volume_total - h_order_data.volume_remain
            sell_type_data[h_order_data.type_id]['sell_profit'] += sell_profit
            # 建筑分类
            if structure.name not in sell_structure_data:
                sell_structure_data[structure.name] = 0
            sell_structure_data[structure.name] += sell_profit
            # group 分类
            if group_name not in sell_group_data:
                sell_group_data[group_name] = 0
            sell_group_data[group_name] += sell_profit

        order_type_id = list({order['type_id'] for order in order_data})
        await MarketHistory.get_type_region_history_data_batch(order_type_id, REGION_VALE_ID)
        await MarketHistory.get_type_region_history_data_batch(order_type_id, REGION_FORGE_ID)
        for order in order_data:
            if order['is_buy_order']:
                continue
            structure = await StructureManager.get_structure(order['location_id'])
            if not structure:
                continue
            if order['volume_total'] == order['volume_remain']:
                continue
            group_name = SdeUtils.get_groupname_by_id(order['type_id'], zh=True)
            history_detel = await MarketHistory.get_type_history_detale(h_order_data.type_id)
            sell_profit = order['price'] * (order['volume_total'] - order['volume_remain'])
            if h_order_data.location_id == FRT_4H_STRUCTURE_ID:
                history_data = history_detel[0]
            else:
                history_data = history_detel[1]


            # 总价统计
            sell_total += sell_profit
            # 物品分类
            if order['type_id'] not in sell_type_data:
                sell_type_data[order['type_id']] = {
                    'type_id': order['type_id'],
                    'name': SdeUtils.get_name_by_id(order['type_id']),
                    'icon': '',
                    'sell_volume': 0,
                    'sell_profit': 0,
                    'market_total_month_flow': history_data['monthflow']
                }
            sell_type_data[order['type_id']]['sell_volume'] += order['volume_total'] - order['volume_remain']
            sell_type_data[order['type_id']]['sell_profit'] += sell_profit
            # 建筑分类
            if structure.name not in sell_structure_data:
                sell_structure_data[structure.name] = 0
            sell_structure_data[structure.name] += sell_profit
            # group分类
            if group_name not in sell_group_data:
                sell_group_data[group_name] = 0
            sell_group_data[group_name] += sell_profit

        return {
            'sell_total': sell_total,
            'sell_type_data': sell_type_data,
            'sell_structure_data': sell_structure_data,
            'sell_group_data': sell_group_data
        }

order_manager = OrderManager()