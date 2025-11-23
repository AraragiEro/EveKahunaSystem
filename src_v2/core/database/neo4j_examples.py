"""
Neo4j 数据模型使用示例

本文件展示了如何使用 Neo4j 数据模型进行 CRUD 操作
"""

# ==================== 1. 模型定义使用示例 ====================

from src_v2.core.database.neo4j_models import Asset, Location, Character, Blueprint, Material, Product

# 创建 Asset 节点实例
asset = Asset(
    item_id=123456789,
    type_id=12345,
    quantity=100,
    is_blueprint_copy=False,
    is_singleton=False,
    location_flag="Hangar",
    owner_id=987654321,
    owner_type="character"
)

# 转换为字典（用于 Neo4j 操作）
asset_dict = asset.to_dict()

# ==================== 2. CRUD 操作示例 ====================

from src_v2.core.database.neo4j_utils import Neo4jAssetUtils, Neo4jIndustryUtils

# 创建资产节点
async def example_create_asset():
    asset = Asset(
        item_id=123456789,
        type_id=12345,
        quantity=100,
        location_flag="Hangar"
    )
    
    # 创建资产并建立关系
    success = await Neo4jAssetUtils.create_asset_with_relationships(
        asset=asset,
        location_id=60003760,
        owner_id=987654321,
        owner_type="character"
    )
    return success


# 批量创建资产
async def example_batch_create_assets():
    assets = [
        Asset(item_id=1001, type_id=12345, quantity=10),
        Asset(item_id=1002, type_id=12346, quantity=20),
    ]
    
    location_ids = [60003760, 60003760]
    owner_ids = [987654321, 987654321]
    owner_types = ["character", "character"]
    
    await Neo4jAssetUtils.batch_create_assets(
        assets, location_ids, owner_ids, owner_types
    )


# 查询资产层级结构
async def example_get_asset_hierarchy():
    hierarchy = await Neo4jAssetUtils.get_asset_hierarchy(
        owner_id=987654321,
        owner_type="character",
        max_depth=5
    )
    return hierarchy


# ==================== 3. 工业制造操作示例 ====================

# 创建蓝图-材料关系
async def example_create_blueprint_material():
    success = await Neo4jIndustryUtils.create_blueprint_material_relationship(
        blueprint_type_id=12345,
        material_type_id=67890,
        quantity=5,
        activity_id=1  # 1=制造活动
    )
    return success


# 创建蓝图-产品关系
async def example_create_blueprint_product():
    success = await Neo4jIndustryUtils.create_blueprint_product_relationship(
        blueprint_type_id=12345,
        product_type_id=11111,
        quantity=1,
        activity_id=1,
        probability=1.0
    )
    return success


# 获取制造链
async def example_get_manufacturing_chain():
    chain = await Neo4jIndustryUtils.get_manufacturing_chain(
        product_type_id=11111,
        max_depth=10
    )
    return chain


# 获取蓝图依赖树（ECharts 格式）
async def example_get_blueprint_tree():
    tree_data = await Neo4jIndustryUtils.get_blueprint_tree(
        blueprint_type_id=12345,
        max_depth=10
    )
    # tree_data 格式：
    # {
    #     "nodes": [...],
    #     "links": [...],
    #     "categories": [...]
    # }
    return tree_data


# ==================== 4. 数据库初始化示例 ====================

from src_v2.core.database.connect_manager import neo4j_manager

async def example_init_neo4j():
    # 初始化连接（会自动创建索引和约束）
    await neo4j_manager.init()
    
    # 使用完成后关闭连接
    await neo4j_manager.close()


