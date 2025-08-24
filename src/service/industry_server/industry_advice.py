import asyncio
import json
from pickle import BINPUT
from pydoc import classify_class_attrs
import pulp
from datetime import datetime, timedelta
from multiprocessing import Lock

from .industry_analyse import IndustryAnalyser
from .order import order_manager
from .structure import StructureManager
from .running_job import RunningJobOwner
from ..sde_service.utils import SdeUtils
from ..user_server.user_manager import UserManager
from ..user_server.user import User
from ...utils import KahunaException, get_beijing_utctime
from ..market_server.marker import MarketHistory, REGION_FORGE_ID
from ..market_server.market_manager import MarketManager
from ..asset_server.asset_manager import AssetManager
from ..character_server.character_manager import CharacterManager
# from ..database_server.utils import UserAssetStatisticsUtils
from ..database_server.sqlalchemy.kahuna_database_utils import (
    RefreshDataDBUtils,
    UserAssetStatisticsDBUtils
)
from .blueprint import BPManager
from ..config_server.config import config, reload_config
from ..log_server import logger


class IndustryAdvice:
    personal_asset_statistics_lock = False

    @classmethod
    async def advice_report(cls, user: User, plan_name: str, product_list: list):
        jita_mk = MarketManager.get_market_by_type('jita')
        vale_mk = MarketManager.get_market_by_type('frt')

        input_list = product_list
        t2_ship_id_list = [SdeUtils.get_id_by_name(name) for name in input_list]
        t2_plan = [[ship, 1] for ship in input_list]

        t2_cost_data = IndustryAnalyser.get_cost_data(user, plan_name, t2_plan)
        t2_cost_data = [[name] + value for name, value in t2_cost_data.items()]
        t2ship_data = []
        t2ship_dict = {}
        for data in t2_cost_data:
            tid = SdeUtils.get_id_by_name(data[0])
            vale_mk_his_data, forge_mk_his_data = await MarketHistory.get_type_history_detale(tid)
            frt_buy, frt_sell = await vale_mk.get_type_order_rouge(tid)
            jita_buy, jita_sell = await jita_mk.get_type_order_rouge(tid)

            market_data = [
                tid,        # id
                data[0],    # name
                SdeUtils.get_cn_name_by_id(tid), # cn_name
                frt_sell * 0.956 - data[3] * 1.01,  # 利润
                (frt_sell * 0.956 - data[3] * 1.01) / data[3],  # 利润率
                vale_mk_his_data['monthflow'] * ((frt_sell * 0.956 - data[3] * 1.01) / data[3]), # 月利润空间
                data[3],    # cost
                frt_sell,   # 4h出单
                jita_buy,   # 吉他收单
                jita_sell,  # 吉他出单
                vale_mk_his_data['monthflow'],  # 月流水
                vale_mk_his_data['month_volume'], # 月销量
                SdeUtils.get_metaname_by_typeid(tid)    # 元组信息
            ]

            market_data_dict = {
                'id': tid,
                'name': data[0],
                'cn_name': SdeUtils.get_cn_name_by_id(tid),
                'profit': (frt_sell * 0.956 - data[3] * 1.01),
                'profit_rate': (frt_sell * 0.956 - data[3] * 1.01) / data[3],
                'month_profit': vale_mk_his_data['monthflow'] * ((frt_sell * 0.956 - data[3] * 1.01) / data[3]),
                'cost': data[3],
                'frt_sell': frt_sell,
                'jita_buy': jita_buy,
                'jita_sell': jita_sell,
                'month_flow': vale_mk_his_data['monthflow'],
                'month_volume': vale_mk_his_data['month_volume'],
                'meta': SdeUtils.get_metaname_by_typeid(tid)
            }

            t2ship_data.append(market_data)
            t2ship_dict[tid] = market_data_dict

        t2ship_data.sort(key=lambda x: x[5], reverse=True)
        return t2ship_dict

    @classmethod
    async def material_ref_advice(
            cls, material_list: list,
            material_flag: str = 'buy',
            compress_flag: str = 'buy'
    ):
        """
        三钛：34
        胶水：35
        类银：36
        同位：37
        小超：38
        石英：39
        大超：40
        摩尔：11399
        """
        jita_market = MarketManager.get_market_by_type('jita')
        # 产出效率系数
        efficiency_rate = 0.906  # 90.6%
        transport_cost = 500
        ref_target = {
            34, 35, 36, 37, 38, 39, 40, 11399,
            16272, 16273, 16274, 16275, 17887, 17888, 17889,
        }
        one_ref_target = {
            34, 35, 36, 37, 38, 39, 40, 11399,
            16272, 16273, 16274, 16275, 17887, 17888, 17889,
            28433, 28434, 28435, 28436, 28437, 28438, 28439, 28440, 28441, 28442, 28443, 28444,
        }
        # ref_source_dict 中的值表示每100单位材料的产出
        ref_source_dict = {
            28433: {16272: 69, 16273: 35, 16275: 1, 17887: 414},
            28434: {16272: 69, 16273: 35, 16275: 1, 16274: 414},
            28435: {16272: 691, 16273: 1381, 16275: 69},
            # 28436: {16272: 104, 16273: 55, 16275: 1, 16274: 483},
            28437: {16272: 345, 16273: 691, 16275: 104},
            28438: {16272: 69, 16273: 35, 16275: 1, 17889: 414},
            28439: {16272: 1381, 16273: 691, 16275: 35},
            28440: {16272: 173, 16273: 691, 16275: 173},
            # 28441: {16272: 104, 16273: 55, 16275: 1, 17888: 483},
            # 28442: {16272: 104, 16273: 55, 16275: 1, 17889: 483},
            # 28443: {16272: 104, 16273: 55, 16275: 1, 17887: 483},
            28444: {16272: 69, 16273: 35, 16275: 1, 17888: 414},
            62520: {34: 150, 35: 90},
            62528: {34: 175, 36: 70},
            # 62536: {36: 60, 37: 120},
            62552: {37: 800, 35: 2000, 36: 1500},
            62524: {35: 90, 36: 30},
            62516: {34: 400},
            62586: {11399: 140},
            62560: {35: 800, 36: 2000, 38: 800},
            62564: {35: 3200, 36: 1200, 39: 160},
            62568: {35: 3200, 36: 1200, 40: 120},
            34: {34: 1}, 35: {35: 1}, 36: {36: 1}, 37: {37: 1}, 38: {38: 1}, 39: {39: 1}, 40: {40: 1}, 11399: {11399: 1},
            16272: {16272: 1}, 16273: {16273: 1}, 16274: {16274: 1}, 16275: {16275: 1}, 17887: {17887: 1}, 17888: {17888: 1}, 17889: {17889: 1}
        }
        target_price_index = 0 if material_flag == 'buy' else 1
        target_price = {
            target: (await jita_market.get_type_order_rouge(target))[target_price_index] for target in ref_target
        }
        source_price_index = 0 if compress_flag == 'buy' else 1
        source_price = {
            source: (await jita_market.get_type_order_rouge(source))[source_price_index] for source in ref_source_dict.keys()
        }
        for source, price in source_price.items():
            if price == 0:
                source_price[source] = 100000000000000
        source_transport_cost = {
            source: SdeUtils.get_volume_by_type_id(source) * transport_cost for source in ref_source_dict.keys()
        }

        # 预先计算考虑效率系数的产出
        effective_ref_source_dict = {}
        for m, products in ref_source_dict.items():
            effective_ref_source_dict[m] = {}
            for p, amount in products.items():
                # 预先计算单位产出 * 效率系数
                effective_ref_source_dict[m][p] = amount * (efficiency_rate if m not in ref_target else 1)

        need = {data[0]: data[1] for data in material_list if data[0] in ref_target}

        # 创建问题实例
        prob = pulp.LpProblem("MinimizeWaste", pulp.LpMinimize)

        # 定义决策变量（每种生产材料使用的数量，单位为100）
        materials = list(ref_source_dict.keys())
        material_units = pulp.LpVariable.dicts("Units", materials, lowBound=0, cat='Integer')

        # 创建辅助变量来表示每种产品的冗余量
        waste_vars = pulp.LpVariable.dicts("Waste",
                                           [(m, p) for m in materials for p in need.keys()],
                                           lowBound=0)

        # 目标1：原材料总成本
        material_cost = pulp.lpSum(
            [material_units[m] * (100 if m not in one_ref_target else 1) * (source_price[m] + source_transport_cost[m]) for m in materials]
        )

        # 目标2：总产出价值 - 原材料总成本
        product_value = pulp.lpSum([
            pulp.lpSum([
                material_units[m] * effective_ref_source_dict[m].get(p, 0) * target_price[p]
                for m in materials if p in ref_source_dict[m]
            ])
            for p in need.keys()
        ])

        # 设置权重
        reload_config()
        material_weight = float(config['EVE']['REF_MATER_WEIGHT'])  # 原材料成本权重
        profit_weight = float(config['EVE']['REF_PROFIT_WEIGHT'])  # 利润权重 (负号表示我们要最大化这部分)

        # 多目标优化：最小化原材料成本同时最大化利润
        prob += material_weight * material_cost - profit_weight * (product_value - material_cost)

        # 添加约束：waste_vars[m, p] 必须大于等于冗余量
        for m in materials:
            for p in need.keys():
                if p in ref_source_dict[m]:
                    # 使用预先计算的有效产出率
                    prob += waste_vars[m, p] >= material_units[m] * effective_ref_source_dict[m][p] - need[p]
                else:
                    prob += waste_vars[m, p] == 0

        # 定义约束条件：每种最终产品的实际产出量必须满足需求
        for product in need.keys():
            # 使用预先计算的有效产出率
            effective_production = pulp.lpSum([
                material_units[m] * effective_ref_source_dict[m].get(product, 0)
                for m in materials if product in ref_source_dict[m]
            ])
            prob += effective_production >= need[product]

        # 求解问题
        prob.solve(pulp.PULP_CBC_CMD(msg=False))
        res = {
            'need': {},
            'product': {},
            'connect': {}
        }

        # 检查求解状态
        if pulp.LpStatus[prob.status] != 'Optimal':
            raise KahunaException(f"未找到最优解，状态：{pulp.LpStatus[prob.status]}")

        # 输出结果
        # print(f"优化状态: {pulp.LpStatus[prob.status]}")

        need_d = res['need']
        product_d = res['product']
        connect_d = res['connect']
        # 构建结果列表
        result_list = []
        for m in materials:
            m_value = int(material_units[m].value()) * (100 if m not in one_ref_target else 1)
            if m_value > 0:
                result_list.append((m, m_value))

        # 打印详细信息
        # print("\n需要的生产材料数量:")
        total_resource_price = 0
        total_transport_cost = 0
        for m in materials:
            if material_units[m].value() > 0:
                need_d[m] = {
                    'name': SdeUtils.get_name_by_id(m),
                    'need': int(material_units[m].value()) * (100 if m not in one_ref_target else 1),
                    'price': source_price[m] * int(material_units[m].value()) * (100 if m not in one_ref_target else 1),
                }
                total_resource_price += need_d[m]['price']
                total_transport_cost += int(material_units[m].value()) * source_transport_cost[m]
        res['total_resource_price'] = total_resource_price
        res['total_transport_cost'] = total_transport_cost
        res['total_cost'] = total_transport_cost + total_resource_price
        # print("\n理论产出与实际产出对比:")
        theoretical_production = {p: 0 for p in need.keys()}
        actual_production = {p: 0 for p in need.keys()}

        for m in materials:
            connect_d[m] = {'name': SdeUtils.get_name_by_id(m), 'product': {}}
            if material_units[m].value() > 0:
                for p in need.keys():
                    if p in ref_source_dict[m]:
                        # 理论产出
                        theo_output = material_units[m].value() * ref_source_dict[m][p]
                        theoretical_production[p] += theo_output

                        # 实际产出（应用效率系数并向下取整）
                        actual_output = int(theo_output * (efficiency_rate if m not in ref_target else 1))
                        actual_production[p] += actual_output
                        connect_d[m]['product'][p] = {'name': SdeUtils.get_name_by_id(p), 'product_value': actual_output}

        # print("产品\t需求\t理论产出\t实际产出\t冗余")
        total_real_waste_price = 0
        total_product_price = 0
        for p in need.keys():
            real_waste = max(0, actual_production[p] - need[p])
            total_real_waste_price += target_price[p] * real_waste
            total_product_price += target_price[p] * actual_production[p]
            product_d[p] = {
                'name': SdeUtils.get_name_by_id(p),
                'need': need[p],
                'actual_production': actual_production[p],
                'waste_unit': real_waste,
                'waste_price': target_price[p] * real_waste
            }
        res['total_real_waste_price'] = total_real_waste_price
        res['total_product_price'] = total_product_price

        return res

    @classmethod
    async def personal_asset_statistics(cls, user_qq: int):
        # 获取资产
        container_list = AssetManager.get_user_container(user_qq)
        target_container = set(container for container in container_list)

        asset_dict = {}
        structure_asset_dict = {}

        for container in target_container:
            result = await AssetManager.get_asset_in_container_list([container.asset_location_id])
            if container.structure_id not in structure_asset_dict:
                structure_asset_dict[container.structure_id] = {}
            for asset in result:
                if asset.type_id not in asset_dict:
                    asset_dict[asset.type_id] = 0
                asset_dict[asset.type_id] += asset.quantity

                if asset.type_id not in structure_asset_dict[container.structure_id]:
                    structure_asset_dict[container.structure_id][asset.type_id] = 0
                structure_asset_dict[container.structure_id][asset.type_id] += asset.quantity

        # 获取运行中任务
        user = UserManager.get_user(user_qq)
        user_character = [c.character_id for c in CharacterManager.get_user_all_characters(user.user_qq)]
        alias_character = [cid for cid in user.user_data.alias.keys()]
        result = await RunningJobOwner.get_job_with_starter(user_character + alias_character)

        job_dict = {}
        for job in result:
            if job.output_location_id in set(container.asset_location_id for container in target_container):
                product_count = BPManager.get_bp_product_quantity_typeid(job.product_type_id)
                if job.product_type_id not in job_dict:
                    job_dict[job.product_type_id] = 0
                job_dict[job.product_type_id] += job.runs * product_count

                if job.product_type_id not in asset_dict:
                    asset_dict[job.product_type_id] = 0
                asset_dict[job.product_type_id] += job.runs * product_count

                structure_id = (await StructureManager.get_structure_id_from_location_id(job.output_location_id))[0]
                if structure_id not in structure_asset_dict:
                    structure_asset_dict[structure_id] = {}
                if job.product_type_id not in structure_asset_dict[structure_id]:
                    structure_asset_dict[structure_id][job.product_type_id] = 0
                structure_asset_dict[structure_id][job.product_type_id] += job.runs * product_count

        # 整理数据
        res = {
            'classify_asset': {},
            'structure_asset': {},
            'wallet': 0,
            'total': 0,
            'order': 0
        }

        # TODO 获取珍贵物品
        # 暂时pass

        # 获取订单数据
        user = UserManager.get_user(user_qq)
        order_data = await order_manager.get_order_of_user(user)
        order_total = 0
        for order in order_data:
            order_total += order['price'] * order['volume_remain']
        res['order'] += order_total
        res['total'] += order_total

        # 获取价格
        jita_market = MarketManager.get_market_by_type('jita')
        price_dict = {
            tid: (await jita_market.get_type_order_rouge(tid))[0] for tid in asset_dict.keys()
        }

        # 按照物品种类
        classify_asset = {'矿石': 0, '冰矿产物': 0, '组件': 0, '燃料块': 0, '元素': 0, '气云': 0, '行星工业': 0, '产品': 0, '杂货': 0}
        # 关键原材料数量统计
        key_material = {'元素': {}, '矿物': {}, '燃料块': {}, 'RAM': {}, '数据核心': {}, '解码器': {}, '行星工业': {}}
        for tid, quantity in asset_dict.items():
            group = SdeUtils.get_groupname_by_id(tid)
            category = SdeUtils.get_category_by_id(tid)
            market_list = SdeUtils.get_market_group_list(tid)
            # 根据 group 或 category 进行判断和分类
            if group == "Mineral":
                classify_asset["矿石"] += quantity * price_dict.get(tid, 0)
                if tid not in key_material['矿物']:
                    key_material['矿物'][tid] = quantity

            elif group == "Ice Product":
                classify_asset['冰矿产物'] += quantity * price_dict.get(tid, 0)

            elif (
                'Advanced Components' in market_list or
                'Capital Components' in market_list
            ):
                classify_asset['组件'] += quantity * price_dict.get(tid, 0)

            elif group == "Fuel Block":
                classify_asset['燃料块'] += quantity * price_dict.get(tid, 0)
                if tid not in key_material['燃料块']:
                    key_material['燃料块'][tid] = quantity

            elif (
                group == "Moon Materials" or
                "Processed Moon Materials" in market_list or
                "Advanced Moon Materials" in market_list
            ):
                classify_asset['元素'] += quantity * price_dict.get(tid, 0)
                if group == "Moon Materials":
                    if tid not in key_material['元素']:
                        key_material['元素'][tid] = quantity

            elif (
                group == "Harvestable Cloud" or
                "Reaction Materials" in market_list
            ):
                classify_asset['气云'] += quantity * price_dict.get(tid, 0)

            elif category == "Planetary Commodities":
                classify_asset['行星工业'] += quantity * price_dict.get(tid, 0)
                if tid not in key_material['行星工业']:
                    key_material['行星工业'][tid] = quantity

            elif category in ['Ship', 'Drone', 'Fighter', 'Module', 'Charge']:
                classify_asset['产品'] += quantity * price_dict.get(tid, 0)

            elif 'R.A.M.' in market_list:
                key_material['RAM'][tid] = quantity

            elif group == 'Datacores':
                key_material['数据核心'][tid] = quantity

            elif category == 'Decryptors':
                key_material['解码器'][tid] = quantity

            else:
                classify_asset["杂货"] += quantity * price_dict.get(tid, 0)

        res['classify_asset'] = classify_asset
        res['key_material'] = key_material
        res['job_running'] = sum([price_dict.get(tid) * value for tid, value in job_dict.items() if tid in price_dict])
        res['total'] += sum(classify_asset.values())

        structure_asset = {}
        count = 1
        main_character_id = UserManager.get_main_character_id(user_qq)
        main_character = CharacterManager.get_character_by_id(main_character_id)
        for structure_id, data in structure_asset_dict.items():
            structure = await StructureManager.get_structure(structure_id, ac_token=main_character.ac_token)
            if structure:
                structure_name = structure.name
            else:
                structure_name = f'unknow_structure_{count}'
                count += 1
            if structure_name not in structure_asset:
                structure_asset[structure_name] = 0
            for tid, quantity in data.items():
                structure_asset[structure_name] += quantity * price_dict.get(tid, 0)
        res['structure_asset'] = structure_asset

        # 钱包余额
        character_list = CharacterManager.get_user_all_characters(user.user_qq)
        for character in character_list:
            res['wallet'] += await character.wallet_balance
            res['total'] += await character.wallet_balance

        upadte_date = get_beijing_utctime(datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
        await UserAssetStatisticsDBUtils.update(user_qq, upadte_date, json.dumps(res))

        # 拉取历史信息
        history_data = {
            data.date.strftime("%Y-%m-%d"): {
                'date': data.date.strftime("%Y-%m-%d"),
                'data': json.loads(data.asset_statistics)
            }
            for data in await UserAssetStatisticsDBUtils.get_user_asset_statistics(user_qq)
        }
        # 补充新加的元素
        for data in history_data.values():
            if 'classify_asset' not in data['data']:
                data['data']['classify_asset'] = {}
            if 'structure_asset' not in data['data']:
                data['data']['structure_asset'] = {}
            if 'job_running' not in data['data']:
                data['data']['job_running'] = 0
            if 'total' not in data['data']:
                data['data']['total'] = 0
            if 'order' not in data['data']:
                data['data']['order'] = 0

        output = {
            'today': res,
            'history': history_data
        }

        return output

    @classmethod
    async def perisonal_inventory_statistics(cls, user_qq: int):
        market = MarketManager.get_market_by_type('jita')

        # TODO 获取资产
        container_list = AssetManager.get_user_container(user_qq)
        target_container = set(container for container in container_list)
        asset_dict = {}

        for container in target_container:
            result = await AssetManager.get_asset_in_container_list([container.asset_location_id])
            for asset in result:
                if asset.type_id not in asset_dict:
                    asset_dict[asset.type_id] = 0
                asset_dict[asset.type_id] += asset.quantity

        async def get_m_dict(tid):
            return {
                'id': tid,
                'quantity': asset_dict.get(tid, 0),
                'name': SdeUtils.get_name_by_id(tid),
                'cn_name': SdeUtils.get_cn_name_by_id(tid),
                "value": (await market.get_type_order_rouge(tid))[0] * asset_dict.get(tid, 0)
            }

        res = {}
        # 元素
        res['moon_material'] = {}
        moon_material_list = list(range(16633, 16654))
        moon_material_list.remove(16645)
        for tid in moon_material_list:
            res['moon_material'][tid] = await get_m_dict(tid)

        # 矿物
        res['material'] = {}
        material_list = list(range(34, 41)) + [11399]
        for tid in material_list:
            res['material'][tid] = await get_m_dict(tid)

        # 燃料块
        res['fuel_block'] = {}
        fuel_block_list = [4051, 4247, 4312, 4246]
        for tid in fuel_block_list:
            res['fuel_block'][tid] = await get_m_dict(tid)

        # RAM
        res['ram'] = {}
        ram_list = [11475, 11476, 11478, 11481, 11482, 11483, 11484, 11485, 11486, 11859, 11870, 11872, 11873, 11887, 11889, 11890, 11891]
        for tid in ram_list:
            res['ram'][tid] = await get_m_dict(tid)

        # 数据核心
        res['datacores'] = {}
        datacore_list = [11496, 20114, 20115, 20171, 20172, 20410, 20411, 20412, 20413, 20414, 20415, 20416, 20417, 20418, 20419, 20420, 20421, 20423, 20424, 20425, 25887, 52309, 81051]
        for tid in datacore_list:
            res['datacores'][tid] = await get_m_dict(tid)

        # 解码器
        res['decryptors'] = {}
        decryptors_list = list(range(34201, 34209))
        for tid in decryptors_list:
            res['decryptors'][tid] = await get_m_dict(tid)

        # 行星工业
        res['planet_industry'] = {}
        for tid, quantity in asset_dict.items():
            category = SdeUtils.get_category_by_id(tid)
            if category == "Planetary Commodities":
                if tid not in res['planet_industry']:
                    res['planet_industry'][tid] = await get_m_dict(tid)

        return res

    @classmethod
    async def refresh_all_asset_statistics(cls):
        if not await RefreshDataDBUtils.out_of_hour_interval('asset_statistics', 4):
            return
        if not cls.personal_asset_statistics_lock:
            try:
                cls.personal_asset_statistics_lock = True
                logger.info('开始刷新资产统计')
                for user_qq in UserManager.user_dict.keys():
                    logger.info(f'刷新{user_qq}的资产')
                    await cls.personal_asset_statistics(user_qq)
                await RefreshDataDBUtils.update_refresh_date('asset_statistics')
                logger.info('刷新资产统计完成')
            finally:
                cls.personal_asset_statistics_lock = False

    @classmethod
    async def moon_material_state(cls, moon_class: int):
        R4 = list(range(16633, 16637))
        R8 = list(range(16637, 16641))
        R16 = list(range(16641, 16645))
        R32 = list(range(16646, 16650))
        R64 = list(range(16650, 16654))
        if moon_class == 4:
            moon_dict = {'R4': R4}
            moon_list = R4
        elif moon_class == 8:
            moon_dict = {'R8': R8}
            moon_list = R8
        elif moon_class == 16:
            moon_dict = {'R16': R16}
            moon_list = R16
        elif moon_class == 32:
            moon_dict = {'R32': R32}
            moon_list = R32
        elif moon_class == 64:
            moon_dict = {'R64': R64}
            moon_list = R64
        else:
            moon_dict = {
                'R4': R4,
                'R8': R8,
                'R16': R16,
                'R32': R32,
                'R64': R64,
            }
            moon_list = R4 + R8 + R16 + R32 + R64
        await MarketHistory.get_type_region_history_data_batch(moon_list, REGION_FORGE_ID)

        # 生成从60天前到昨天的日期列表
        today = get_beijing_utctime(datetime.now())
        date_list = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(2, 60)]
        date_list.reverse()  # 将列表按照日期从早到晚排序

        res_data = {}
        type_dict = {}
        market = MarketManager.get_market_by_type('jita')
        for moon, tid_list in moon_dict.items():
            if moon not in res_data:
                res_data[moon] = {tid: {} for tid in tid_list}
            for tid in tid_list:
                history_data = await MarketHistory.get_type_region_history_data(tid, REGION_FORGE_ID)
                two_month_ago = get_beijing_utctime(datetime.now()) - timedelta(days=60)
                two_month_history = [data for data in history_data if datetime.fromisoformat(data[0]) >= two_month_ago]
                two_month_history = {
                    data[0]: {
                        'date': data[0],
                        'lowest_price': data[3],
                        'highest_price': data[2],
                        'average_price': data[1],
                        'volume': data[4]
                    } for data in two_month_history
                }
                history_detal = (await MarketHistory.get_type_history_detale(tid))[1]
                res_data[moon][tid].update({
                    'type_id': tid,
                    'name': SdeUtils.get_name_by_id(tid),
                    'cn_name': SdeUtils.get_cn_name_by_id(tid),
                    'sell_price': (await market.get_type_order_rouge(tid))[1],
                    'buy_price': (await market.get_type_order_rouge(tid))[0],
                    'two_month_history': two_month_history,
                    'month_highset_aver': history_detal['month_highset_aver'],
                    'month_lowest_aver': history_detal['month_lowest_aver'],
                })
                type_dict[tid] = res_data[moon][tid]

        market_index_history = {}
        for date in date_list:
            flow = 0
            volumes = 0
            for tid, data in type_dict.items():
                if date in data['two_month_history']:
                    flow += data['two_month_history'][date]['average_price'] * data['two_month_history'][date]['volume']
                    volumes += data['two_month_history'][date]['volume']
            market_index_history[date] = flow / volumes if volumes !=0 else 0

        return res_data, market_index_history