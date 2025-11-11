from functools import wraps
from peewee import DoesNotExist
from typing import Callable, Optional
from cachetools import LRUCache
import asyncio

from ..sde import SdeUtils
from ..sde.database import IndustryActivityMaterials, IndustryActivityProducts, IndustryBlueprints, InvTypes, IndustryActivities
from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU
from src_v2.core.database.connect_manager import neo4j_manager
from src_v2.core.utils import tqdm_manager

# 限制并发任务数量的信号量，防止连接池耗尽
# 设置为 50，确保不超过连接池大小（200）的合理比例

def async_lru_cache(maxsize: int = 128):
    """
    异步LRU缓存装饰器
    用于缓存异步函数的返回值
    """
    def decorator(func: Callable) -> Callable:
        cache = LRUCache(maxsize=maxsize)
        lock = asyncio.Lock()
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 创建缓存键，排除 cls 参数（类方法）
            key = (args[1:] if args else (), tuple(sorted(kwargs.items())))
            
            # 先尝试无锁读取（快速路径）
            if key in cache:
                return cache[key]
            
            # 如果缓存未命中，加锁执行函数并缓存结果
            async with lock:
                # 双重检查，可能在等待锁时其他协程已经缓存了结果
                if key in cache:
                    return cache[key]
                
                # 执行函数并缓存结果
                result = await func(*args, **kwargs)
                cache[key] = result
                return result
        
        # 添加缓存清理方法
        setattr(wrapper, 'cache_clear', cache.clear)
        setattr(wrapper, 'cache_info', lambda: {
            'hits': getattr(cache, 'hits', 0),
            'misses': getattr(cache, 'misses', 0),
            'maxsize': maxsize,
            'currsize': len(cache)
        })
        
        return wrapper
    return decorator


class BPManager:
    ACTIVITY_ID_MAP = {
        1: "Manufacturing",
        3: "Researching Time Efficiency",
        4: "Researching Material Efficiency",
        5: "Copying",
        8: "Invention",
        11: "Reactions",
    }

    @classmethod
    @async_lru_cache(maxsize=1000)
    async def get_bp_materials(cls, type_id: int) -> dict:
        material_search = (
            IndustryActivityMaterials
                .select(IndustryActivityMaterials.materialTypeID, IndustryActivityMaterials.quantity)
                .join(IndustryActivityProducts,
                      on=(IndustryActivityMaterials.blueprintTypeID==IndustryActivityProducts.blueprintTypeID))
                .where((IndustryActivityProducts.productTypeID==type_id) &
                       (IndustryActivityProducts.blueprintTypeID != 45732) &
                       ((IndustryActivityMaterials.activityID == 1) | (IndustryActivityMaterials.activityID == 11)))
        )
        return {material.materialTypeID: material.quantity for material in material_search}

    @classmethod
    @async_lru_cache(maxsize=1000)
    async def get_bp_product_quantity_typeid(cls, type_id: int) -> int:
        try:
            #45732是一个测试用数据，会导致误判，需要特殊处理
            product_quantity = IndustryActivityProducts.select(IndustryActivityProducts.quantity).where(
                (IndustryActivityProducts.productTypeID == type_id) &
                (IndustryActivityProducts.blueprintTypeID != 45732)
            ).get().quantity
        except DoesNotExist:
            product_quantity = 1  # 或者你想要的默认值

        return product_quantity

    # @classmethod
    # def get_formula_id_by_prod_typeid(cls, type_id: int, unrefined: bool = False) -> int:
    #     ressults = (IndustryActivityProducts
    #              .select(IndustryActivityProducts.blueprintTypeID, IndustryActivityProducts.quantity)
    #              .where(IndustryActivityProducts.productTypeID == type_id))
    #
    #     for res in ressults:
    #         if unrefined and res.quantity == 1:
    #             return res.blueprintTypeID
    #         elif not unrefined and res.quantity > 1:
    #             return res.blueprintTypeID
    #
    # @classmethod
    # def get_manubp_id_by_prod_typeid(cls, type_id: int) -> int:
    #     return (IndustryActivityProducts
    #              .select(IndustryActivityProducts.blueprintTypeID)
    #              .where(IndustryActivityProducts.productTypeID == type_id)).scalar()

    @classmethod
    @async_lru_cache(maxsize=100)
    async def get_bp_id_by_prod_typeid(cls, type_id: int) -> int:
        return (
            IndustryActivityProducts
                 .select(IndustryActivityProducts.blueprintTypeID)
                 .where((IndustryActivityProducts.productTypeID == type_id) &
                        (IndustryActivityProducts.blueprintTypeID != 45732)).scalar()
        )

    @classmethod
    @async_lru_cache(maxsize=100)
    async def get_bp_id_by_pbpname(cls, bp_name) -> Optional[int]:
        bp_maybe_type_id = SdeUtils.get_id_by_name(bp_name)
        if not bp_maybe_type_id:
            return None
        bp_id = (IndustryActivityProducts
                 .select(IndustryActivityProducts.blueprintTypeID)
                 .where(IndustryActivityProducts.blueprintTypeID == bp_maybe_type_id)
                 .scalar())
        if bp_id:
            return bp_id
        return None

    @classmethod
    @async_lru_cache(maxsize=1000)
    async def check_product_id_existence(cls, product_type_id: int) -> bool:
        return IndustryActivityProducts.select().where(IndustryActivityProducts.productTypeID == product_type_id).exists()

    @classmethod
    @async_lru_cache(maxsize=1000)
    async def get_production_time(cls, product_id: int) -> int:
        """
        获取指定产品的制造活动时间（秒）
        参数：
            product_id (int): 产品ID
        返回：
            int: 制造活动时间，单位秒。如果未找到返回0
        """
        details = await cls.get_blueprint_details(product_id)
        if details is None:
            return 0
            
        for activity in details['activities']:
            if activity['activityID'] == 1 or activity['activityID'] == 11:  # 制造活动
                return activity['time']
        return 0

    @classmethod
    @async_lru_cache(maxsize=1000)
    async def get_activity_time_by_typeid(cls, product_id: int) -> int:
        """
        获取指定产品的制造活动时间（秒）
        参数：
            product_id (int): 产品ID
        返回：
            int: 制造活动时间，单位秒。如果未找到返回0
        """
        details = await cls.get_blueprint_details(product_id)
        if details is None:
            return 0

        for activity in details['activities']:
            if activity['activityID'] == 1 or activity['activityID'] == 11:  # 制造活动
                return activity['activityID']
        return 0

    @classmethod
    @async_lru_cache(maxsize=1000)
    async def get_chunk_runs(cls, product_id: int) -> int:
        """
        计算单个蓝图每日可完成的制造流程数
        参数：
            product_id (int): 产品ID
        返回：
            int: 每日可完成的制造流程数
        """
        production_time = await cls.get_production_time(product_id)
        if production_time <= 0:
            return 0
        return max(1, 86400 // production_time)  # 86400秒 = 1天

    @classmethod
    @async_lru_cache(maxsize=500)
    async def get_activity_id_by_product_typeid(cls, product_typeid: int) -> int:
        return IndustryActivityProducts.select(
            IndustryActivityProducts.activityID
        ).where(
            (IndustryActivityProducts.productTypeID == product_typeid) &
            (IndustryActivityProducts.blueprintTypeID != 45732)
        ).scalar()

    @classmethod
    @async_lru_cache(maxsize=1000)
    async def get_blueprint_details(cls, product_id: int) -> Optional[dict]:
        """
        根据产品ID返回蓝图的详细信息字典。
        参数：
            product_id (int): 产品的ID
        返回：
            dict: 包含蓝图详细信息的字典，包括基本属性、材料和活动时间
        """
        
        blueprint_details = {
            'product_info': {},
            'materials': [],
            'activities': []
        }
        
        try:
            # 获取产品基本信息
            product = InvTypes.get(InvTypes.typeID == product_id)
            blueprint_details['product_info'] = {
                'typeID': product.typeID,
                'typeName': product.typeName,
                'description': product.description,
                'mass': product.mass,
                'volume': product.volume,
                'basePrice': product.basePrice
            }
            
            # 获取所有与该产品相关的蓝图活动材料
            materials = IndustryActivityMaterials.select(
                    IndustryActivityMaterials.materialTypeID,
                    IndustryActivityMaterials.quantity  # 
                ).join(
                IndustryActivityProducts,
                on=(IndustryActivityMaterials.blueprintTypeID == 
                    IndustryActivityProducts.blueprintTypeID)
            ).where((IndustryActivityProducts.productTypeID == product_id) &
                    (IndustryActivityProducts.blueprintTypeID != 45732) &
                    ((IndustryActivityMaterials.activityID == 1) | (IndustryActivityMaterials.activityID == 11)))
            
            for material in materials:
                blueprint_details['materials'].append({
                    'material_typeID': material.materialTypeID,
                    'quantity': material.quantity
                })
            
            # 获取所有与该产品相关的蓝图活动信息
            # 首先通过 IndustryActivityProducts 获取 blueprintTypeID
            blueprint_type_id = IndustryActivityProducts.select(
                IndustryActivityProducts.blueprintTypeID
            ).where(
                (IndustryActivityProducts.productTypeID == product_id) &
                (IndustryActivityProducts.blueprintTypeID != 45732)
            ).get().blueprintTypeID
            
            # 然后使用 blueprintTypeID 查询 IndustryActivities
            activities = IndustryActivities.select(
                IndustryActivities.activityID,
                IndustryActivities.time
            ).where(
                (IndustryActivities.blueprintTypeID == blueprint_type_id) &
                (IndustryActivities.blueprintTypeID != 45732)
            )
            
            for activity in activities:
                blueprint_details['activities'].append({
                    'activityID': activity.activityID,
                    'time': activity.time
                })

        except DoesNotExist as e:
            return None
        
        return blueprint_details

    @classmethod
    async def get_typeid_by_bpid(cls, blueprint_id: int):
        return (IndustryActivityProducts.select(IndustryActivityProducts.productTypeID)
                                  .where(IndustryActivityProducts.blueprintTypeID == blueprint_id).scalar())

    @classmethod
    @async_lru_cache(maxsize=1000)
    async def get_productionmax_by_bpid(cls, blueprint_id: int):
        product_id = cls.get_typeid_by_bpid(blueprint_id)
        meta = SdeUtils.get_metaname_by_typeid(product_id)
        cate = SdeUtils.get_category_by_id(product_id)
        if meta == 'Faction' and cate == 'Ship':
            return 1
        return (IndustryBlueprints.select(IndustryBlueprints.maxProductionLimit)
                                  .where(IndustryBlueprints.blueprintTypeID == blueprint_id).scalar())

    @classmethod
    async def get_all_product_typeids(cls):
        return [p.productTypeID for p in IndustryActivityProducts.select(IndustryActivityProducts.productTypeID)]

    @classmethod
    async def init_bp_data_to_neo4j(cls):
        product_typeids = await cls.get_all_product_typeids()

        # 使用信号量限制并发任务数量，防止连接池耗尽
        async def process_with_semaphore(product_typeid):
            return await cls.fill_bp_node_and_link_child(product_typeid, finished_set, root=True)

        finished_set = set()
        await tqdm_manager.add_mission("init_bp_data_to_neo4j", len(product_typeids))
        tasks = [
            asyncio.create_task(process_with_semaphore(product_typeid)) for product_typeid in product_typeids
        ]
        await asyncio.gather(*tasks)

    @classmethod
    async def fill_bp_node_and_link_child(cls, product_typeid: int, finished_set: set, root=False):
        # 提前检查是否已完成，避免不必要的并发操作
        if f"fill_{product_typeid}" in finished_set:
            return
        
        type_id = product_typeid
        type_name = SdeUtils.get_name_by_id(type_id)
        group_name = SdeUtils.get_groupname_by_id(type_id)
        category = SdeUtils.get_category_by_id(type_id)
        meta = SdeUtils.get_metaname_by_typeid(type_id)
        market_list = SdeUtils.get_market_group_list(type_id)
        activity_id = await cls.get_activity_id_by_product_typeid(type_id)
        bp_type_id = await cls.get_bp_id_by_prod_typeid(type_id)

        async with neo4j_manager.semaphore:
            # 再次检查，防止在等待信号量期间其他任务已完成
            if f"fill_{product_typeid}" in finished_set:
                return
            finished_set.add(f"fill_{product_typeid}")
            await NIU.merge_node(
                "Blueprint",
                {"type_id": type_id},
                {
                    "type_id": type_id,
                    "type_name": type_name,
                    "group_name": group_name,
                    "category": category,
                    "meta": meta,
                    "market_list": market_list,
                    "bp_type_id": bp_type_id
                }
            )

        product_quantity = await cls.get_bp_product_quantity_typeid(type_id)
        childs = await cls.get_bp_materials(type_id)
        if not childs:
            return

        # 使用信号量限制并发任务数量
        async def link_with_semaphore(material_type_id, quantity):
            # 提前检查是否已完成
            if f"{type_id}_{material_type_id}" in finished_set:
                return
            async with neo4j_manager.semaphore:
                # 再次检查，防止在等待信号量期间其他任务已完成
                if f"{type_id}_{material_type_id}" in finished_set:
                    return
                finished_set.add(f"{type_id}_{material_type_id}")
                return await NIU.link_node(
                    "Blueprint",
                    {"type_id": type_id}, {"type_id": type_id},
                    "BP_DEPEND_ON",
                    {"product": type_id, "material": material_type_id},
                    {"product": type_id, "material": material_type_id,
                    "material_num": quantity, "product_num": product_quantity,
                    "activity_id": activity_id, "activity_type": cls.ACTIVITY_ID_MAP[activity_id]},
                    "Blueprint",
                    {"type_id": material_type_id},
                    {"type_id": material_type_id}
                )
        
        tasks = [
            asyncio.create_task(link_with_semaphore(material_type_id, quantity)) 
            for material_type_id, quantity in childs.items() if f"{type_id}_{material_type_id}" not in finished_set
        ]
        await asyncio.gather(*tasks)

        # 递归调用时也使用信号量限制并发
        async def fill_with_semaphore(material_type_id):
            return await cls.fill_bp_node_and_link_child(material_type_id, finished_set)
        
        tasks = [
            asyncio.create_task(fill_with_semaphore(material_type_id)) for material_type_id in childs if f"fill_{material_type_id}" not in finished_set
        ]
        await asyncio.gather(*tasks)

        if root:
            await tqdm_manager.update_mission("init_bp_data_to_neo4j", 1)

    