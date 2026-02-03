"""
Home API 工具函数模块
用于处理首页概览相关的复杂业务逻辑
"""
import asyncio
import traceback
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.kahuna_database_utils_v2 import (
    EveIndustryPlanConfigFlowConfigDBUtils,
    EveIndustryPlanConfigFlowDBUtils,
    EvePublicCharacterInfoDBUtils,
)
from src_v2.core.database.neo4j_utils import Neo4jAssetUtils as NAU
from src_v2.core.log import logger
from src_v2.core.user.user_manager import UserManager
from src_v2.model.EVE.asset.asset_manager import AssetManager
from src_v2.model.EVE.character.character import Character
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.model.EVE.eveesi import eveesi
from src_v2.model.EVE.industry.blueprint import BPManager as BPM
from src_v2.model.EVE.industry.industry_manager import IndustryManager
from src_v2.model.EVE.market.market_manager import MarketManager
from src_v2.model.EVE.sde import SdeUtils


async def get_wallet_value(user_id: str, character_ids: Optional[List[int]] = None) -> Dict[str, float]:
    """
    获取用户所有角色的钱包价值

    Args:
        user_id: 用户ID
        character_ids: 可选的角色ID列表，如果提供则只获取指定角色的钱包价值

    Returns:
        字典，键为角色名称，值为钱包余额
    """
    wallet_value = {}
    try:
        character_manager = CharacterManager()
        characters = await character_manager.get_user_all_characters(user_id)

        # 如果提供了角色ID列表，进行筛选
        if character_ids:
            characters = [
                char for char in characters if char.character_id in character_ids]

        async def get_wallet_for_character(character_db_obj):
            try:
                character = Character.from_db_obj(character_db_obj)
                wallet_balance = await eveesi.character_character_id_wallet(
                    character.ac_token,
                    character.character_id
                )
                return [wallet_balance, character_db_obj.character_name] if wallet_balance is not None else [0.0, character_db_obj.character_name]
            except Exception as e:
                logger.warning("获取角色 %s 钱包余额失败: %s",
                               character_db_obj.character_name, str(e))
                return [0.0, character_db_obj.character_name]

        wallet_balances = await asyncio.gather(*[
            get_wallet_for_character(char) for char in characters
        ])
        for wallet_balance, character_name in wallet_balances:
            wallet_value[character_name] = wallet_balance
    except Exception:
        logger.error("获取钱包价值失败: %s", traceback.format_exc())

    return wallet_value


async def get_order_value(user_id: str, character_ids: Optional[List[int]] = None) -> Dict[str, float]:
    """
    获取用户所有角色的订单价值

    Args:
        user_id: 用户ID
        character_ids: 可选的角色ID列表，如果提供则只获取指定角色的订单价值

    Returns:
        字典，键为角色名称，值为订单总价值
    """
    order_value = {}
    try:
        character_manager = CharacterManager()
        characters = await character_manager.get_user_all_characters(user_id)

        # 如果提供了角色ID列表，进行筛选
        if character_ids:
            characters = [
                char for char in characters if char.character_id in character_ids]

        async def get_orders_for_character(character_db_obj):
            try:
                character = Character.from_db_obj(character_db_obj)
                orders = await eveesi.characters_character_orders(
                    character.ac_token,
                    character.character_id
                )

                # 计算订单总价值：price * volume_remain
                total_value = 0.0
                if orders:
                    for order in orders:
                        price = order.get('price', 0)
                        volume_remain = order.get('volume_remain', 0)
                        total_value += price * volume_remain

                return [total_value, character_db_obj.character_name]
            except Exception as e:
                logger.warning("获取角色 %s 订单价值失败: %s",
                               character_db_obj.character_name, str(e))
                return [0.0, character_db_obj.character_name]

        order_values = await asyncio.gather(*[
            get_orders_for_character(char) for char in characters
        ])
        for order_total, character_name in order_values:
            order_value[character_name] = order_total
    except Exception:
        logger.error("获取订单价值失败: %s", traceback.format_exc())

    return order_value


async def get_order_details(user_id: str, character_ids: Optional[List[int]] = None) -> List[dict]:
    """
    获取用户所有角色的订单详情

    Args:
        user_id: 用户ID
        character_ids: 可选的角色ID列表，如果提供则只获取指定角色的订单详情

    Returns:
        订单详情列表，每个订单包含：
        - character_name: 角色名称
        - type_name: 物品名称
        - order_type: 订单种类（"收购" 或 "出售"）
        - location_name: 订单地点
        - volume_total: 总数量
        - volume_remain: 剩余数量
        - completion_percent: 完成百分比
        - remaining_value: 剩余订单价值
        - remaining_time_minutes: 剩余时间（分钟）
        - price: 单价
        - region_id: 区域ID
    """
    order_details = []
    try:
        character_manager = CharacterManager()
        characters = await character_manager.get_user_all_characters(user_id)

        # 如果提供了角色ID列表，进行筛选
        if character_ids:
            characters = [
                char for char in characters if char.character_id in character_ids]

        asset_manager = AssetManager()

        async def get_orders_for_character(character_db_obj):
            try:
                character = Character.from_db_obj(character_db_obj)
                orders = await eveesi.characters_character_orders(
                    character.ac_token,
                    character.character_id
                )

                if not orders:
                    return []

                character_orders = []
                for order in orders:
                    type_id = order.get('type_id')
                    location_id = order.get('location_id')
                    is_buy_order = order.get('is_buy_order', False)
                    volume_total = order.get('volume_total', 0)
                    volume_remain = order.get('volume_remain', 0)
                    price = order.get('price', 0)
                    issued = order.get('issued')
                    duration = order.get('duration', 0)
                    region_id = order.get('region_id')

                    # 查询物品名称
                    type_name = await SdeUtils.get_name_by_id(type_id, zh=True)
                    if not type_name:
                        type_name = await SdeUtils.get_name_by_id(type_id, zh=False)
                    if not type_name:
                        type_name = f"Unknown Type {type_id}"

                    # 查询地点名称
                    location_name = f"Location {location_id}"  # 默认值
                    if location_id:
                        # 判断是空间站还是结构（结构ID通常 >= 100000000）
                        if location_id < 100000000:
                            # 空间站
                            try:
                                station_info, _ = await asset_manager.get_station_info(location_id)
                                if station_info and 'name' in station_info:
                                    location_name = station_info['name']
                            except Exception as e:
                                logger.warning(
                                    f"获取空间站 {location_id} 信息失败: {e}")
                                # 尝试直接调用ESI API
                                try:
                                    station_info = await eveesi.universe_stations_station(location_id)
                                    if station_info and 'name' in station_info:
                                        location_name = station_info['name']
                                except Exception:
                                    pass
                        else:
                            # 结构 - 先检查缓存，再使用ESI API获取
                            try:
                                # 先检查Redis缓存
                                structure_info_cache = await rdm().r.hgetall(
                                    f'eveesi:universe_structures_structure:{location_id}')
                                if structure_info_cache and 'name' in structure_info_cache:
                                    location_name = structure_info_cache['name']
                                else:
                                    # 缓存不存在，调用ESI API
                                    structure_info = await eveesi.universe_structures_structure(
                                        character.ac_token, location_id, log=False
                                    )
                                    if structure_info and 'name' in structure_info:
                                        location_name = structure_info['name']
                                        # 保存到缓存（移除position字段，因为它是复杂对象）
                                        structure_info_cache = structure_info.copy()
                                        structure_info_cache.pop(
                                            'position', None)
                                        await rdm().r.hset(
                                            f'eveesi:universe_structures_structure:{location_id}',
                                            mapping=structure_info_cache
                                        )
                            except Exception as e:
                                logger.warning(f"获取结构 {location_id} 信息失败: {e}")

                    # 计算完成百分比
                    completion_percent = 0.0
                    if volume_total > 0:
                        completion_percent = (
                            (volume_total - volume_remain) / volume_total) * 100

                    # 计算剩余订单价值
                    remaining_value = price * volume_remain

                    # 计算订单剩余时间（分钟）
                    remaining_time_minutes = None
                    if issued:
                        try:
                            # issued 可能是字符串或datetime对象
                            if isinstance(issued, str):
                                issued_dt = datetime.fromisoformat(
                                    issued.replace('Z', '+00:00'))
                            else:
                                issued_dt = issued
                            # 转换为本地时区（如果需要）
                            if issued_dt.tzinfo is None:
                                # 假设是UTC时间
                                from datetime import timezone
                                issued_dt = issued_dt.replace(
                                    tzinfo=timezone.utc)
                            # 计算过期时间
                            expiry_dt = issued_dt + timedelta(days=duration)
                            # 计算剩余时间（分钟）
                            # 获取当前UTC时间
                            from datetime import timezone
                            now_utc = datetime.now(timezone.utc)

                            # 统一时区：将过期时间转换为UTC
                            if expiry_dt.tzinfo is None:
                                # 如果过期时间没有时区，假设是UTC
                                expiry_dt = expiry_dt.replace(
                                    tzinfo=timezone.utc)
                            else:
                                # 如果过期时间有时区，转换为UTC
                                expiry_dt = expiry_dt.astimezone(timezone.utc)

                            # 计算时间差
                            time_diff = expiry_dt - now_utc
                            remaining_time_minutes = int(
                                time_diff.total_seconds() / 60)
                            # 如果已经过期，返回0
                            if remaining_time_minutes < 0:
                                remaining_time_minutes = 0
                        except Exception as e:
                            logger.warning(f"计算订单剩余时间失败: {e}")

                    order_detail = {
                        'character_name': character_db_obj.character_name,
                        'type_name': type_name,
                        'order_type': '收购' if is_buy_order else '出售',
                        'location_name': location_name,
                        'volume_total': volume_total,
                        'volume_remain': volume_remain,
                        'completion_percent': round(completion_percent, 2),
                        'remaining_value': remaining_value,
                        'remaining_time_minutes': remaining_time_minutes,
                        'price': price,
                        'region_id': region_id,
                        'order_id': order.get('order_id'),
                        'is_buy_order': is_buy_order
                    }
                    character_orders.append(order_detail)

                return character_orders
            except Exception as e:
                logger.warning("获取角色 %s 订单详情失败: %s",
                               character_db_obj.character_name, str(e))
                return []

        # 并发获取所有角色的订单
        orders_results = await asyncio.gather(*[
            get_orders_for_character(char) for char in characters
        ])

        # 展平结果
        for orders in orders_results:
            order_details.extend(orders)

    except Exception:
        logger.error("获取订单详情失败: %s", traceback.format_exc())

    return order_details


async def get_all_plans_load_asset_confs(user_id: str) -> List[dict]:
    """
    获取用户所有计划的载入库存配置（LoadAssetConf）

    Args:
        user_id: 用户ID

    Returns:
        所有 load_asset_confs 的列表，每个配置包含 asset_container_id, asset_owner_id, location_flag 等信息
    """
    load_asset_confs = []

    try:
        # 获取用户的所有计划
        plans = await IndustryManager.get_plan(user_id)

        # 遍历每个计划，获取配置流
        for plan in plans:
            plan_name = plan.get('plan_name')
            user_name = plan.get('user_name', user_id)

            # 获取计划的配置流
            config_flow = await EveIndustryPlanConfigFlowDBUtils.select_configflow_by_user_name_and_plan_name(
                user_name, plan_name
            )

            if not config_flow or not config_flow.config_list:
                continue

            # 遍历配置流中的每个配置ID
            for config_id in config_flow.config_list:
                config = await EveIndustryPlanConfigFlowConfigDBUtils.select_by_id(config_id)

                if not config:
                    logger.warning(f"配置 {config_id} 不存在")
                    continue

                # 筛选出 LoadAssetConf 类型的配置
                if config.config_type == 'LoadAssetConf':
                    load_asset_confs.append(config.config_value)

    except Exception as e:
        logger.error(f"获取计划载入库存配置失败: {traceback.format_exc()}")

    return load_asset_confs


async def get_corporation_jobs(user_id: str) -> List[dict]:
    """
    获取公司jobs

    Args:
        user_id: 用户ID

    Returns:
        公司jobs列表
    """
    corp_jobs = []

    try:
        # 获取用户的主角色
        main_character_id = await UserManager().get_main_character_id(user_id)
        main_character = await CharacterManager().get_character_by_character_id(main_character_id)

        if not main_character:
            return corp_jobs

        # 获取主角色所在公司的总监角色
        director_character_ids = await CharacterManager().get_director_character_id_of_corporation(
            main_character.corporation_id
        )

        if not director_character_ids:
            return corp_jobs

        # 获取总监角色对象
        for director_character_id in director_character_ids:
            director = await CharacterManager().get_character_by_character_id(director_character_id)
            try:
                await director.ac_token
                break
            except Exception as e:
                logger.warning(f"获取总监角色 {director_character_id} 的token失败: {str(e)}")
                director = None
                continue

        if not director:
            return corp_jobs

        # 获取公司jobs
        corp_jobs_result = await eveesi.corporations_corporation_id_industry_jobs(
            director.ac_token,
            director.corporation_id
        )

        # corp_jobs_result 可能是嵌套列表，需要展平
        if corp_jobs_result:
            for job_list in corp_jobs_result:
                if isinstance(job_list, list):
                    corp_jobs.extend(job_list)
                else:
                    corp_jobs.append(job_list)

    except Exception as e:
        logger.warning(f"获取公司jobs失败: {traceback.format_exc()}")

    return corp_jobs


async def get_character_jobs(user_id: str) -> List[dict]:
    """
    获取所有auth角色的jobs

    Args:
        user_id: 用户ID

    Returns:
        所有角色jobs的列表
    """
    character_jobs = []

    try:
        # 获取用户的所有角色
        characters = await CharacterManager().get_user_all_characters(user_id)

        # 并发获取所有角色的jobs
        async def get_jobs_for_character(character_db_obj):
            try:
                character = Character.from_db_obj(character_db_obj)
                jobs = await eveesi.characters_character_id_industry_jobs(
                    character.ac_token,
                    character.character_id
                )
                return jobs if jobs else []
            except Exception as e:
                logger.warning(
                    f"获取角色 {character_db_obj.character_name} jobs失败: {str(e)}")
                return []

        # 并发获取所有角色的jobs
        jobs_results = await asyncio.gather(*[
            get_jobs_for_character(char) for char in characters
        ])

        # 展平结果
        for jobs in jobs_results:
            character_jobs.extend(jobs)

    except Exception as e:
        logger.warning(f"获取角色jobs失败: {traceback.format_exc()}")

    return character_jobs


async def calculate_running_process_value(user_id: str) -> dict:
    """
    计算运行中流程价值

    Args:
        user_id: 用户ID

    Returns:
        包含公司jobs价值、角色jobs价值和总价值的字典
    """
    try:
        # 获取所有计划的载入库存配置
        load_asset_confs = await get_all_plans_load_asset_confs(user_id)

        # 提取所有 asset_container_id 作为目标库存列表
        target_container_ids = set()
        for conf in load_asset_confs:
            asset_container_id = conf.get('asset_container_id')
            if asset_container_id:
                target_container_ids.add(asset_container_id)

        if not target_container_ids:
            # 如果没有配置的库存，返回0
            return {
                "corp_jobs_value": 0.0,
                "character_jobs_value": 0.0,
                "total_value": 0.0
            }

        # 获取所有jobs
        corp_jobs = await get_corporation_jobs(user_id)
        character_jobs = await get_character_jobs(user_id)

        # 初始化价格管理器
        market_manager = MarketManager()

        # 价格缓存，避免重复查询
        price_cache = {}

        async def get_price(type_id: int) -> float:
            """获取价格，带缓存"""
            if type_id not in price_cache:
                price_cache[type_id] = await market_manager.get_jita_buy_price(type_id)
            return price_cache[type_id]

        # 蓝图产出数量缓存，避免重复查询
        product_quantity_cache = {}

        async def get_product_quantity_per_run(type_id: int) -> int:
            """获取每次运行的产出数量，带缓存"""
            if type_id not in product_quantity_cache:
                product_quantity_cache[type_id] = await BPM.get_bp_product_quantity_typeid(type_id)
            return product_quantity_cache[type_id]

        # 计算公司jobs价值
        corp_jobs_value = 0.0
        for job in corp_jobs:
            output_location_id = job.get('output_location_id')
            if output_location_id not in target_container_ids:
                continue

            product_type_id = job.get('product_type_id')
            if not product_type_id:
                continue

            # 获取运行次数
            runs = job.get('runs', 0)
            if runs <= 0:
                continue

            # 获取每次运行的产出数量（需要查询蓝图）
            product_quantity_per_run = await get_product_quantity_per_run(product_type_id)

            # 计算总产出数量 = runs × 每次运行产出数量
            total_product_quantity = runs * product_quantity_per_run

            # 获取jitabuy价格
            price = await get_price(product_type_id)

            # 计算价值 = 总产出数量 × 价格
            value = total_product_quantity * price
            corp_jobs_value += value

        # 计算角色jobs价值
        character_jobs_value = 0.0
        for job in character_jobs:
            output_location_id = job.get('output_location_id')
            if output_location_id not in target_container_ids:
                continue

            product_type_id = job.get('product_type_id')
            if not product_type_id:
                continue

            # 获取运行次数
            runs = job.get('runs', 0)
            if runs <= 0:
                continue

            # 获取每次运行的产出数量（需要查询蓝图）
            product_quantity_per_run = await get_product_quantity_per_run(product_type_id)

            # 计算总产出数量 = runs × 每次运行产出数量
            total_product_quantity = runs * product_quantity_per_run

            # 获取jitabuy价格
            price = await get_price(product_type_id)

            # 计算价值 = 总产出数量 × 价格
            value = total_product_quantity * price
            character_jobs_value += value

        total_value = corp_jobs_value + character_jobs_value

        return {
            "corp_jobs_value": corp_jobs_value,
            "character_jobs_value": character_jobs_value,
            "total_value": total_value
        }

    except Exception as e:
        logger.error(f"计算运行中流程价值失败: {traceback.format_exc()}")
        return {
            "corp_jobs_value": 0.0,
            "character_jobs_value": 0.0,
            "total_value": 0.0
        }


async def get_all_assets_by_owner_ids(owner_ids: List[int]) -> List[dict]:
    """
    从Neo4j获取指定owner_id列表下的所有资产

    Args:
        owner_ids: 资产所有者ID列表

    Returns:
        资产列表，每个资产包含 type_id, quantity, owner_id 等信息
    """
    if not owner_ids:
        return []

    try:
        from src_v2.core.database.connect_manager import get_neo4j_manager

        query = """
        MATCH (a:Asset)
        WHERE a.owner_id IN $owner_ids
        RETURN a
        """
        async with get_neo4j_manager().get_session() as session:
            result = await session.run(query, {"owner_ids": owner_ids})
            assets = [dict(record["a"]) async for record in result]
            return assets
    except Exception as e:
        logger.error(f"获取资产列表失败: {traceback.format_exc()}")
        return []


async def get_marked_asset_value(
    user_id: str,
    asset_mission_filters: Optional[List[Tuple[str, int]]] = None
) -> float:
    """
    获取标记资产价值（在访问许可内的资产价值总和）

    Args:
        user_id: 用户ID
        asset_mission_filters: 可选的资产拉取任务筛选列表，格式为 [(subject_type, subject_id), ...]
                             如果提供，只计算筛选任务范围内的资产价值

    Returns:
        标记资产总价值
    """
    try:
        # 获取用户所有访问许可
        container_permissions = await IndustryManager.get_user_all_container_permission(user_id)

        if not container_permissions:
            return 0.0

        # 如果提供了筛选条件，只保留 asset_owner_id 在筛选列表中的权限
        if asset_mission_filters:
            # 构建筛选的 owner_id 集合
            filter_owner_ids = set()
            for _subject_type, subject_id in asset_mission_filters:
                filter_owner_ids.add(subject_id)

            # 筛选容器权限
            filtered_permissions = []
            for permission in container_permissions:
                owner_id = permission.get('asset_owner_id')
                owner_type = permission.get('owner_type')
                # 检查 owner_id 和 owner_type 是否匹配筛选条件
                if owner_id in filter_owner_ids:
                    # 进一步检查 owner_type 是否匹配
                    for filter_type, filter_id in asset_mission_filters:
                        if filter_id == owner_id and filter_type == owner_type:
                            filtered_permissions.append(permission)
                            break
            container_permissions = filtered_permissions

        if not container_permissions:
            return 0.0

        # 构建容器-所有者对列表
        container_owner_list = []
        for permission in container_permissions:
            container_id = permission.get('asset_container_id')
            owner_id = permission.get('asset_owner_id')
            location_flag = permission.get('location_flag')
            if container_id and owner_id:
                container_owner_list.append(
                    [container_id, owner_id, location_flag])

        if not container_owner_list:
            return 0.0

        # 获取标记资产
        marked_assets = await NAU.get_asset_in_container_owner_list(container_owner_list)

        if not marked_assets:
            return 0.0

        # 初始化价格管理器
        market_manager = MarketManager()

        # 价格缓存，避免重复查询
        price_cache = {}

        async def get_price(type_id: int) -> float:
            """获取价格，带缓存"""
            if type_id not in price_cache:
                price_cache[type_id] = await market_manager.get_jita_buy_price(type_id)
            return price_cache[type_id]

        # 计算总价值
        total_value = 0.0
        for asset in marked_assets:
            type_id = asset.get('type_id')
            quantity = asset.get('quantity', 0)

            if not type_id or quantity <= 0:
                continue

            price = await get_price(type_id)
            value = quantity * price
            total_value += value

        return total_value

    except Exception as e:
        logger.error(f"获取标记资产价值失败: {traceback.format_exc()}")
        return 0.0


async def get_unmarked_asset_value(
    user_id: str,
    asset_mission_filters: Optional[List[Tuple[str, int]]] = None
) -> float:
    """
    获取非标记资产价值（不在访问许可内的资产价值总和）

    Args:
        user_id: 用户ID
        asset_mission_filters: 可选的资产拉取任务筛选列表，格式为 [(subject_type, subject_id), ...]
                             如果提供，只计算筛选任务范围内的资产价值

    Returns:
        非标记资产总价值
    """
    try:
        # 获取用户所有资产拉取任务
        asset_manager = AssetManager()
        missions = await asset_manager.get_user_asset_pull_mission_list(user_id)

        if not missions:
            return 0.0

        # 如果提供了筛选条件，只使用筛选任务列表中的 subject_id
        if asset_mission_filters:
            # 构建筛选的 (subject_type, subject_id) 集合
            filter_set = set(asset_mission_filters)
            # 筛选任务
            filtered_missions = []
            for mission in missions:
                subject_type = mission.get('subject_type')
                subject_id = mission.get('subject_id')
                if subject_type and subject_id and (subject_type, subject_id) in filter_set:
                    filtered_missions.append(mission)
            missions = filtered_missions

        if not missions:
            return 0.0

        # 提取所有 asset_owner_id (subject_id)
        owner_ids = list(set([mission.get('subject_id')
                         for mission in missions if mission.get('subject_id')]))

        if not owner_ids:
            return 0.0

        # 获取所有资产
        all_assets = await get_all_assets_by_owner_ids(owner_ids)

        if not all_assets:
            return 0.0

        # 获取标记资产（用于排除）
        container_permissions = await IndustryManager.get_user_all_container_permission(user_id)

        marked_asset_keys = set()
        if container_permissions:
            # 构建容器-所有者对列表
            container_owner_list = []
            for permission in container_permissions:
                container_id = permission.get('asset_container_id')
                owner_id = permission.get('asset_owner_id')
                location_flag = permission.get('location_flag')
                if container_id and owner_id:
                    container_owner_list.append(
                        [container_id, owner_id, location_flag])

            if container_owner_list:
                marked_assets = await NAU.get_asset_in_container_owner_list(container_owner_list)
                # 使用 (item_id, owner_id) 作为唯一标识
                for asset in marked_assets:
                    item_id = asset.get('item_id')
                    owner_id = asset.get('owner_id')
                    if item_id and owner_id:
                        marked_asset_keys.add((item_id, owner_id))

        # 筛选出非标记资产
        unmarked_assets = []
        for asset in all_assets:
            item_id = asset.get('item_id')
            owner_id = asset.get('owner_id')
            if item_id and owner_id:
                key = (item_id, owner_id)
                if key not in marked_asset_keys:
                    unmarked_assets.append(asset)

        if not unmarked_assets:
            return 0.0

        # 初始化价格管理器
        market_manager = MarketManager()

        # 价格缓存，避免重复查询
        price_cache = {}

        async def get_price(type_id: int) -> float:
            """获取价格，带缓存"""
            if type_id not in price_cache:
                price_cache[type_id] = await market_manager.get_jita_buy_price(type_id)
            return price_cache[type_id]

        # 计算总价值
        total_value = 0.0
        for asset in unmarked_assets:
            type_id = asset.get('type_id')
            quantity = asset.get('quantity', 0)

            if not type_id or quantity <= 0:
                continue

            price = await get_price(type_id)
            value = quantity * price
            total_value += value

        return total_value

    except Exception as e:
        logger.error(f"获取非标记资产价值失败: {traceback.format_exc()}")
        return 0.0


def process_overview_data_for_history(overview_data: dict) -> dict:
    """
    处理overview数据，对子结构数据（如walletValue、orderValue）进行求和

    Args:
        overview_data: 原始overview数据字典

    Returns:
        处理后的数据字典，所有子结构都已求和为单个数值
    """
    processed = {}

    # 处理walletValue：如果是对象，对values求和；如果是数字，直接使用
    wallet_value = overview_data.get('walletValue', 0)
    if isinstance(wallet_value, dict):
        processed['walletValue'] = sum(wallet_value.values())
    elif isinstance(wallet_value, (int, float)):
        processed['walletValue'] = wallet_value
    else:
        processed['walletValue'] = 0.0

    # 处理orderValue：同上
    order_value = overview_data.get('orderValue', 0)
    if isinstance(order_value, dict):
        processed['orderValue'] = sum(order_value.values())
    elif isinstance(order_value, (int, float)):
        processed['orderValue'] = order_value
    else:
        processed['orderValue'] = 0.0

    # 其他字段直接使用数值
    processed['runningProcessValue'] = float(
        overview_data.get('runningProcessValue', 0.0))
    processed['markedAssetValue'] = float(
        overview_data.get('markedAssetValue', 0.0))
    processed['unmarkedAssetValue'] = float(
        overview_data.get('unmarkedAssetValue', 0.0))

    # 计算总价值
    processed['totalValue'] = (
        processed['walletValue'] +
        processed['orderValue'] +
        processed['runningProcessValue'] +
        processed['markedAssetValue'] +
        processed['unmarkedAssetValue']
    )

    return processed


def get_today_date_beijing() -> 'date':
    """
    获取+8时区的今日日期（仅年月日）

    Returns:
        date对象（仅年月日）
    """
    from src_v2.core.utils import get_beijing_utctime

    beijing_time = get_beijing_utctime(datetime.now())
    return beijing_time.date()


async def get_character_name(character_id: int) -> str:
    """
    获取角色名称，先检查缓存，没有则通过ESI获取

    Args:
        character_id: 角色ID

    Returns:
        角色名称
    """
    try:
        # 1. 先检查本地数据库缓存
        char_info = await EvePublicCharacterInfoDBUtils.select_public_character_info_by_character_id(character_id)
        if char_info and char_info.name:
            return char_info.name

        # 2. 检查已认证角色表
        try:
            char = await CharacterManager().get_character_by_character_id(character_id)
            if char and char.character_name:
                return char.character_name
        except Exception:
            pass

        # 3. 通过ESI API获取
        try:
            char_info_data = await eveesi.characters_character(character_id)
            if char_info_data and 'name' in char_info_data:
                # 保存到缓存（使用CharacterManager的方法）
                char_manager = CharacterManager()
                await char_manager.get_public_character_info_by_character_id(character_id)
                return char_info_data['name']
        except Exception as e:
            logger.warning(f"通过ESI获取角色 {character_id} 信息失败: {e}")

        return f"Unknown Character {character_id}"
    except Exception as e:
        logger.warning(f"获取角色 {character_id} 名称失败: {e}")
        return f"Unknown Character {character_id}"


def calculate_job_progress(start_date: str, end_date: str) -> float:
    """
    计算任务进度百分比

    Args:
        start_date: 开始时间（ISO格式字符串）
        end_date: 结束时间（ISO格式字符串）

    Returns:
        进度百分比（0-100）
    """
    try:
        # 解析时间字符串
        if isinstance(start_date, str):
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start = start_date

        if isinstance(end_date, str):
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = end_date

        # 确保时区信息
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        # 获取当前UTC时间
        now = datetime.now(timezone.utc)

        # 如果还没开始，返回0
        if now <= start:
            return 0.0

        # 如果已经结束，返回100
        if now >= end:
            return 100.0

        # 计算进度
        total_duration = (end - start).total_seconds()
        elapsed = (now - start).total_seconds()
        progress = (elapsed / total_duration) * 100.0

        return min(100.0, max(0.0, progress))
    except Exception as e:
        logger.warning(f"计算任务进度失败: {e}")
        return 0.0


async def get_running_jobs_details(user_id: str) -> dict:
    """
    获取运行中任务详情

    Args:
        user_id: 用户ID

    Returns:
        包含详细信息列表和汇总列表的字典
    """
    try:
        # 获取所有计划的载入库存配置
        load_asset_confs = await get_all_plans_load_asset_confs(user_id)

        # 提取所有 asset_container_id 作为目标库存列表
        target_container_ids = set()
        for conf in load_asset_confs:
            asset_container_id = conf.get('asset_container_id')
            if asset_container_id:
                target_container_ids.add(asset_container_id)

        if not target_container_ids:
            # 如果没有配置的库存，返回空列表
            return {
                "detail_list": [],
                "summary_list": [],
                "character_summary_list": []
            }

        # 获取所有jobs
        corp_jobs = await get_corporation_jobs(user_id)
        character_jobs = await get_character_jobs(user_id)

        # 初始化价格管理器
        market_manager = MarketManager()

        # 价格缓存，避免重复查询
        price_cache = {}

        async def get_price(type_id: int) -> float:
            """获取价格，带缓存"""
            if type_id not in price_cache:
                price_cache[type_id] = await market_manager.get_jita_buy_price(type_id)
            return price_cache[type_id]

        # 蓝图产出数量缓存，避免重复查询
        product_quantity_cache = {}

        async def get_product_quantity_per_run(type_id: int) -> int:
            """获取每次运行的产出数量，带缓存"""
            if type_id not in product_quantity_cache:
                product_quantity_cache[type_id] = await BPM.get_bp_product_quantity_typeid(type_id)
            return product_quantity_cache[type_id]

        # 角色名缓存，避免重复查询
        character_name_cache = {}

        async def get_installer_name(character_id: int) -> str:
            """获取启动角色名，带缓存"""
            if character_id not in character_name_cache:
                character_name_cache[character_id] = await get_character_name(character_id)
            return character_name_cache[character_id]

        # 详细信息列表
        detail_list = []

        # 处理公司jobs
        for job in corp_jobs:
            output_location_id = job.get('output_location_id')
            if output_location_id not in target_container_ids:
                continue

            # 只识别制造（activity_id=1）和反应（activity_id=11）
            activity_id = job.get('activity_id')
            if activity_id not in (1, 9, 11):
                continue

            product_type_id = job.get('product_type_id')
            if not product_type_id:
                continue

            # 获取运行次数
            runs = job.get('runs', 0)
            if runs <= 0:
                continue

            # 获取物品名称
            product_name = await SdeUtils.get_name_by_id(product_type_id, zh=False)
            if not product_name:
                product_name = f"Unknown Type {product_type_id}"
            product_name_zh = await SdeUtils.get_name_by_id(product_type_id, zh=True)
            if not product_name_zh:
                product_name_zh = product_name

            # 获取每次运行的产出数量
            product_quantity_per_run = await get_product_quantity_per_run(product_type_id)

            # 计算总产出数量
            total_quantity = runs * product_quantity_per_run

            # 计算任务进度
            start_date = job.get('start_date')
            end_date = job.get('end_date')
            progress_percent = 0.0
            if start_date and end_date:
                progress_percent = calculate_job_progress(start_date, end_date)

            # 获取cost
            cost = job.get('cost', 0.0) or 0.0

            # 获取启动角色名
            installer_id = job.get('installer_id')
            installer_name = "未知"
            if installer_id:
                installer_name = await get_installer_name(installer_id)

            # 计算生产价值
            price = await get_price(product_type_id)
            value = total_quantity * price

            detail_list.append({
                "job_type": "公司",
                "activity_id": activity_id,
                "activity_type": "制造" if activity_id == 1 else "反应",
                "product_type_id": product_type_id,
                "product_name": product_name,
                "product_name_zh": product_name_zh,
                "runs": runs,
                "product_quantity_per_run": product_quantity_per_run,
                "total_quantity": total_quantity,
                "progress_percent": round(progress_percent, 2),
                "cost": cost,
                "installer_id": installer_id,
                "installer_name": installer_name,
                "value": value,
                "start_date": start_date,
                "end_date": end_date
            })

        # 处理个人jobs
        for job in character_jobs:
            output_location_id = job.get('output_location_id')
            if output_location_id not in target_container_ids:
                continue

            # 只识别制造（activity_id=1）和反应（activity_id=11）
            activity_id = job.get('activity_id')
            if activity_id not in (1, 9, 11):
                continue

            product_type_id = job.get('product_type_id')
            if not product_type_id:
                continue

            # 获取运行次数
            runs = job.get('runs', 0)
            if runs <= 0:
                continue

            # 获取物品名称
            product_name = await SdeUtils.get_name_by_id(product_type_id, zh=False)
            if not product_name:
                product_name = f"Unknown Type {product_type_id}"
            product_name_zh = await SdeUtils.get_name_by_id(product_type_id, zh=True)
            if not product_name_zh:
                product_name_zh = product_name

            # 获取每次运行的产出数量
            product_quantity_per_run = await get_product_quantity_per_run(product_type_id)

            # 计算总产出数量
            total_quantity = runs * product_quantity_per_run

            # 计算任务进度
            start_date = job.get('start_date')
            end_date = job.get('end_date')
            progress_percent = 0.0
            if start_date and end_date:
                progress_percent = calculate_job_progress(start_date, end_date)

            # 获取cost
            cost = job.get('cost', 0.0) or 0.0

            # 获取启动角色名
            installer_id = job.get('installer_id')
            installer_name = "未知"
            if installer_id:
                installer_name = await get_installer_name(installer_id)

            # 计算生产价值
            price = await get_price(product_type_id)
            value = total_quantity * price

            detail_list.append({
                "job_type": "个人",
                "activity_id": activity_id,
                "activity_type": "制造" if activity_id == 1 else "反应",
                "product_type_id": product_type_id,
                "product_name": product_name,
                "product_name_zh": product_name_zh,
                "runs": runs,
                "product_quantity_per_run": product_quantity_per_run,
                "total_quantity": total_quantity,
                "progress_percent": round(progress_percent, 2),
                "cost": cost,
                "installer_id": installer_id,
                "installer_name": installer_name,
                "value": value,
                "start_date": start_date,
                "end_date": end_date
            })

        # 按物品种类分类汇总
        summary_dict = {}
        for detail in detail_list:
            product_type_id = detail["product_type_id"]
            if product_type_id not in summary_dict:
                summary_dict[product_type_id] = {
                    "product_type_id": product_type_id,
                    "product_name": detail["product_name"],
                    "product_name_zh": detail["product_name_zh"],
                    "total_quantity": 0,
                    "total_value": 0.0
                }
            summary_dict[product_type_id]["total_quantity"] += detail["total_quantity"]
            summary_dict[product_type_id]["total_value"] += detail["value"]

        summary_list = list(summary_dict.values())

        # 按角色汇总（角色占用情况）
        character_summary_dict = {}
        for detail in detail_list:
            installer_id = detail.get("installer_id")
            if not installer_id:
                continue

            activity_id = detail.get("activity_id")

            if installer_id not in character_summary_dict:
                installer_name = detail.get("installer_name", "未知")
                character_summary_dict[installer_id] = {
                    "character_id": installer_id,
                    "character_name": installer_name,
                    "manufacturing_running_count": 0,
                    "manufacturing_completed_count": 0,
                    "reaction_running_count": 0,
                    "reaction_completed_count": 0
                }

            # 统计运行中任务数量（分别统计制造和反应）
            progress_percent = detail.get("progress_percent", 0)
            if activity_id == 1:  # 制造
                if progress_percent < 100:
                    character_summary_dict[installer_id]["manufacturing_running_count"] += 1
                else:
                    character_summary_dict[installer_id]["manufacturing_completed_count"] += 1
            elif activity_id == 11 or activity_id == 9:  # 反应
                if progress_percent < 100:
                    character_summary_dict[installer_id]["reaction_running_count"] += 1
                else:
                    character_summary_dict[installer_id]["reaction_completed_count"] += 1

        character_summary_list = list(character_summary_dict.values())

        return {
            "detail_list": detail_list,
            "summary_list": summary_list,
            "character_summary_list": character_summary_list
        }

    except Exception as e:
        logger.error(f"获取运行中任务详情失败: {traceback.format_exc()}")
        return {
            "detail_list": [],
            "summary_list": [],
            "character_summary_list": []
        }
