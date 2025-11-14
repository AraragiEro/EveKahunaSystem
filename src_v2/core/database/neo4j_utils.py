"""
Neo4j CRUD 操作工具类
"""
import asyncio
import stat
from typing import Optional, List, Dict, Any, TYPE_CHECKING, Tuple
from datetime import datetime
from neo4j.exceptions import TransientError
from .neo4j_models import NodeModel, RelationshipType
from .connect_manager import neo4j_manager
from ..log import logger

if TYPE_CHECKING:
    from .neo4j_models import Asset


class Neo4jAssetUtils:
    """Asset 相关的 CRUD 操作"""
    @staticmethod
    async def get_asset_hierarchy(owner_id: int, owner_type: str, max_depth: int = 5) -> List[Dict]:
        """获取资产层级结构"""
        async with neo4j_manager.get_session() as session:
            owner_label = "Character" if owner_type == "character" else "Corporation"
            owner_prop = "character_id" if owner_type == "character" else "corporation_id"
            
            query = f"""
            MATCH path = (owner:{owner_label} {{{owner_prop}: $owner_id}})
                  <-[:OWNED_BY]-(asset:Asset)
                  -[:LOCATED_IN*0..{max_depth}]->(loc:Location)
            RETURN path
            ORDER BY length(path) DESC
            LIMIT 100
            """
            
            result = await session.run(query, {"owner_id": owner_id})
            paths = []
            async for record in result:
                paths.append(record["path"])
            return paths
    
    @staticmethod
    async def batch_create_assets(assets: List[Dict[str, Any]]):
        """批量创建资产节点并建立位置关系
        
        Args:
            assets: 资产数据列表，每个元素是一个包含资产属性的字典
            owner_id: 所有者ID
            
        功能：
            1. 创建asset节点，填充dict的数据
            2. 创建当前asset节点到item_id==location_id的asset节点的LOCATED_IN边
            3. 若目标节点不存在则新建一个填充item_id=location_id和owner_id的节点
            
        Returns:
            创建的资产节点数量
        """
        if not assets:
            return 0
        
        async with neo4j_manager.get_transaction() as tx:
            # 第一步：创建所有asset节点
            create_query = """
            UNWIND $assets AS asset_data
            // 创建或更新当前asset节点（使用owner_id和item_id作为唯一键）
            MERGE (a:Asset {owner_id: asset_data.owner_id, item_id: asset_data.item_id})
            // 设置所有属性
            SET a.owner_type = asset_data.owner_type,
                a.is_blueprint_copy = COALESCE(asset_data.is_blueprint_copy, false),
                a.is_singleton = COALESCE(asset_data.is_singleton, false),
                a.location_flag = asset_data.location_flag,
                a.location_id = asset_data.location_id,
                a.location_type = asset_data.location_type,
                a.quantity = asset_data.quantity,
                a.type_id = asset_data.type_id,
                a.type_name = asset_data.type_name
            RETURN count(a) AS created_count
            """
            
            result = await tx.run(create_query, {
                "assets": assets
            })
            record = await result.single()
            created_count = record["created_count"] if record else 0
            
            # 第二步：为有location_id的资产创建LOCATED_IN关系
            relationship_query = """
            UNWIND $assets AS asset_data
            // 只处理有location_id的资产
            WITH asset_data
            WHERE asset_data.location_id IS NOT NULL
            // 找到源节点
            MATCH (a:Asset {owner_id: asset_data.owner_id, item_id: asset_data.item_id})
            // MERGE目标节点（如果不存在则创建，只填充item_id和owner_id）
            MERGE (target:Asset {owner_id: asset_data.owner_id, item_id: asset_data.location_id})
            // 创建LOCATED_IN关系
            MERGE (a)-[:LOCATED_IN]->(target)
            RETURN count(a) AS relationship_count
            """
            
            result = await tx.run(relationship_query, {
                "assets": assets
            })
            
            return created_count

    @staticmethod
    async def merge_asset_to_structure_if_exists(asset_dict: Dict, structure_dict: Dict):
        """插入asset，如果找到structure则插入asset->structure的关系
        
        Args:
            asset_dict: 资产数据字典
            structure_dict: 结构数据字典，必须包含 structure_id
            
        Returns:
            bool: 是否成功创建了asset->structure的关系
        """
        async with neo4j_manager.get_transaction() as tx:
            query = """
            // 1. 插入或更新 Asset 节点
            MERGE (a:Asset {owner_id: $owner_id, item_id: $item_id})
            SET a.is_blueprint_copy = COALESCE($is_blueprint_copy, a.is_blueprint_copy, false),
                a.is_singleton = COALESCE($is_singleton, a.is_singleton, false),
                a.location_flag = COALESCE($location_flag, a.location_flag),
                a.location_id = COALESCE($location_id, a.location_id),
                a.location_type = COALESCE($location_type, a.location_type),
                a.quantity = COALESCE($quantity, a.quantity),
                a.type_id = COALESCE($type_id, a.type_id),
                a.type_name = COALESCE($type_name, a.type_name)
            // 2. 查找是否存在 Structure 节点，如果存在则创建关系
            WITH a
            OPTIONAL MATCH (s:Structure {structure_id: $structure_id})
            WITH a, s
            // 3. 如果找到 Structure，则创建关系
            FOREACH (x IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END |
                MERGE (a)-[:LOCATED_IN]->(s)
            )
            // 4. 返回是否创建了关系
            RETURN s IS NOT NULL AS relationship_created
            """
            result = await tx.run(query, {
                "owner_id": asset_dict.get("owner_id"),
                "item_id": asset_dict.get("item_id"),
                "is_blueprint_copy": asset_dict.get("is_blueprint_copy"),
                "is_singleton": asset_dict.get("is_singleton"),
                "location_flag": asset_dict.get("location_flag"),
                "location_id": asset_dict.get("location_id"),
                "location_type": asset_dict.get("location_type"),
                "quantity": asset_dict.get("quantity"),
                "type_id": asset_dict.get("type_id"),
                "type_name": asset_dict.get("type_name"),
                "structure_id": structure_dict.get("structure_id")
            })
            record = await result.single()
            # 如果找到 structure 并创建了关系，返回 True；否则返回 False
            return record["relationship_created"] if record else False

    @staticmethod
    async def merge_asset_to_structure_to_solar_system(asset_dict: Dict, structure_dict: Dict, solar_system_dict: Dict):
        async with neo4j_manager.get_transaction() as tx:
            query = """
            // 以 item_id 搜索 Asset 节点
            OPTIONAL MATCH (asset:Asset {owner_id: $owner_id, item_id: $item_id})
            // 如果找到 Asset 节点，删除 Asset label，添加 Structure label
            FOREACH (x IN CASE WHEN asset IS NOT NULL THEN [1] ELSE [] END |
                REMOVE asset:Asset
            )
            FOREACH (x IN CASE WHEN asset IS NOT NULL THEN [1] ELSE [] END |
                SET asset:Structure,
                    asset.structure_id = $structure_id,
                    asset.structure_name = $structure_name,
                    asset.structure_type = $structure_type,
                    asset.system_id = $system_id,
                    asset.system_name = $system_name,
                    asset.region_id = $region_id,
                    asset.region_name = $region_name
            )
            WITH asset AS node
            // 如果 Asset 节点不存在，创建新的 Structure 节点
            MERGE (new_node:Structure {structure_id: $structure_id})
            ON CREATE SET new_node.structure_id = $structure_id,
                new_node.structure_name = $structure_name,
                new_node.structure_type = $structure_type
            WITH COALESCE(node, new_node) AS a
            // 连接到 SolarSystem
            MERGE (s:SolarSystem {system_id: $system_id})
            SET s.system_name = $system_name,
                s.region_id = $region_id,
                s.region_name = $region_name
            MERGE (a)-[:LOCATED_IN]->(s)
            RETURN a
            """
            result = await tx.run(query, {
                'owner_id': asset_dict.get("owner_id"),
                'item_id': asset_dict.get("item_id"),
                'structure_id': structure_dict.get("structure_id"),
                'structure_name': structure_dict.get("structure_name"),
                'structure_type': structure_dict.get("structure_type"),
                'system_id': solar_system_dict.get("system_id"),
                'system_name': solar_system_dict.get("system_name"),
                'region_id': solar_system_dict.get("region_id"),
                'region_name': solar_system_dict.get("region_name")
            })
            record = await result.single()
            return record is not None

    @staticmethod
    async def merge_asset_to_station(asset_dict: Dict, station_dict: Dict):
        async with neo4j_manager.get_transaction() as tx:
            query = """
            MERGE (a:Asset {owner_id: $owner_id, item_id: $item_id})
            SET a.is_blueprint_copy = $is_blueprint_copy,
                a.is_singleton = $is_singleton,
                a.location_flag = $location_flag,
                a.location_id = $location_id,
                a.location_type = $location_type,
                a.quantity = $quantity,
                a.type_id = $type_id,
                a.type_name = $type_name
            MERGE (s:Station {station_id: $station_id})
            SET s.station_name = $station_name,
                s.system_id = $system_id,
                s.system_name = $system_name
            MERGE (a)-[:LOCATED_IN]->(s)
            RETURN a
            """
            result = await tx.run(query, {
                "owner_id": asset_dict.get("owner_id"),
                "item_id": asset_dict.get("item_id"),
                "is_blueprint_copy": asset_dict.get("is_blueprint_copy", False),
                "is_singleton": asset_dict.get("is_singleton", False),
                "location_flag": asset_dict.get("location_flag"),
                "location_id": asset_dict.get("location_id"),
                "location_type": asset_dict.get("location_type"),
                "quantity": asset_dict.get("quantity"),
                "type_id": asset_dict.get("type_id"),
                "type_name": asset_dict.get("type_name"),
                "station_id": station_dict.get("station_id"),
                "station_name": station_dict.get("station_name"),
                "system_id": station_dict.get("system_id"),
                "system_name": station_dict.get("system_name")
            })
            record = await result.single()
            return record is not None

    @staticmethod
    async def merge_station_to_system(station_dict: Dict, system_dict: Dict):
        async with neo4j_manager.get_transaction() as tx:
            query = """
            MERGE (s:Station {station_id: $station_id})
            SET s.station_name = $station_name,
                s.system_id = $system_id,
                s.system_name = $system_name
            MERGE (g:SolarSystem {system_id: $system_id})
            SET g.system_name = $system_name,
                g.region_id = $region_id,
                g.region_name = $region_name
            MERGE (s)-[:LOCATED_IN]->(g)
            RETURN s
            """
            result = await tx.run(query, {
                "station_id": station_dict.get("station_id"),
                "station_name": station_dict.get("station_name"),
                "system_id": system_dict.get("system_id"),
                "system_name": system_dict.get("system_name"),
                "region_id": system_dict.get("region_id"),
                "region_name": system_dict.get("region_name")
            })
            record = await result.single()
            return record is not None

    @staticmethod
    async def get_forbidden_structure_node_list(owner_id: int) -> List[Dict]:
        """查找没有出边的 Structure 节点（通常是位置信息不完整的结构）
        
        Args:
            owner_id: 所有者ID
            
        Returns:
            没有出边关系的 Structure 节点列表（字典格式）
        """
        async with neo4j_manager.get_session() as session:
            query = """
            MATCH (a:Asset {owner_id: $owner_id})
            WHERE NOT EXISTS { (a)-[]->() }
            RETURN a
            """
            result = await session.run(query, {"owner_id": owner_id})
            nodes = []
            async for record in result:
                node = record["a"]
                # 将 Neo4j Node 对象转换为字典
                node_dict = dict(node)
                nodes.append(node_dict)
            return nodes
            
    @staticmethod
    async def delete_assets_by_owner_id(owner_id: int):
        async with neo4j_manager.get_transaction() as tx:
            query = """
            MATCH (a:Asset {owner_id: $owner_id})
            DETACH DELETE a
            """
            await tx.run(query, {"owner_id": owner_id})
    
    @staticmethod
    async def search_container_by_item_name(owner_ids: List[int], type_id: int):
        async with neo4j_manager.get_session() as session:
            query = """
            match path = (a:Asset)-[r:LOCATED_IN*0..20]->(b:SolarSystem)
            where a.owner_id IN $owner_ids and a.type_id = $type_id
            return a, nodes(path) as path_nodes, b
            """
            result = await session.run(query, {"owner_ids": owner_ids, "type_id": type_id})
            result_list = []
            async for record in result:
                if record and record["path_nodes"]:
                    # 将路径节点列表转换为字典列表
                    path_nodes = []
                    for node in record["path_nodes"]:
                        node_dict = dict(node)
                        node_dict['labels'] = list(node.labels)
                        path_nodes.append(node_dict)
                    result_list.append(path_nodes)
            return result_list

    @staticmethod
    async def get_structure_asset_nodes(owner_id: int) -> List[Dict]:
        query = """
        match (a:Asset {owner_id: $owner_id})-[]->(b:SolarSystem) return a,b
        """
        async with neo4j_manager.get_session() as session:
            result = await session.run(query, {"owner_id": owner_id})
            nodes = []
            async for record in result:
                nodes.append(dict(record["a"]))
            return nodes

    @staticmethod
    async def change_asset_to_structure(asset_dict: Dict, structure_dict: Dict):
        query = """
        match (a:Asset {item_id: $item_id,owner_id: $owner_id})
        REMOVE a:Asset
        SET a:Structure
        SET a.structure_id = $structure_id,
            a.structure_name = $structure_name,
            a.structure_type = $structure_type,
            a.system_id = $system_id,
            a.system_name = $system_name,
            a.region_id = $region_id,
            a.region_name = $region_name
        return a
        """
        async with neo4j_manager.get_transaction() as tx:
            result = await tx.run(
                query,
                {
                    "item_id": asset_dict.get("item_id"),
                    "owner_id": asset_dict.get("owner_id"),
                    "structure_id": structure_dict.get("structure_id"),
                    "structure_name": structure_dict.get("structure_name"),
                    "structure_type": structure_dict.get("structure_type"),
                    "system_id": structure_dict.get("system_id"),
                    "system_name": structure_dict.get("system_name"),
                    "region_id": structure_dict.get("region_id"),
                    "region_name": structure_dict.get("region_name")
                })
            record = await result.single()
            return record is not None

    @staticmethod
    async def get_structure_nodes() -> List[Dict]:
        query = """
        match (a:Structure) return a
        """
        async with neo4j_manager.get_session() as session:
            result = await session.run(query)
            nodes = []
            async for record in result:
                nodes.append(dict(record["a"]))
            return nodes

    @staticmethod
    async def get_asset_by_type_id_in_container_list(type_id: int, container_list: List[int]) -> List[Dict]:
        query = """
        match (a:Asset {type_id: $type_id}) where a.location_id in $container_list return a
        """
        async with neo4j_manager.get_session() as session:
            result = await session.run(query, {"type_id": type_id, "container_list": container_list})
            assets = []
            async for record in result:
                assets.append(dict(record["a"]))
            return assets

    @staticmethod
    async def get_asset_in_container_list(container_list: List[int]) -> List[Dict]:
        query = """
        match (a:Asset) where a.location_id in $container_list return a
        """
        async with neo4j_manager.get_session() as session:
            result = await session.run(query, {"container_list": container_list})
            assets = []
            async for record in result:
                assets.append(dict(record["a"]))
            return assets

class Neo4jIndustryUtils:
    """工业制造相关的 CRUD 操作"""
    @staticmethod
    async def delete_tree(root_label: str, root_index: Dict[str, Any], relation_label: str) -> int:
        """根据根节点属性和边属性删除整棵树
        
        Args:
            root_label: 根节点的标签（如 "Asset", "Structure"）
            root_index: 根节点的属性字典，用于匹配根节点（如 {"owner_id": 123, "item_id": 456}）
            relation_label: 关系的标签（如 "LOCATED_IN", "CONTAINS"）
            
        Returns:
            int: 删除的节点数量
            
        功能说明：
            1. 根据 root_label 和 root_index 找到根节点
            2. 找到所有通过 relation_label 关系连接的子树节点（包括根节点）
            3. 删除整棵树及其所有关系
            
        示例：
            # 删除以 owner_id=123, item_id=456 的 Asset 为根，通过 LOCATED_IN 关系连接的整棵树
            await Neo4jIndustryUtils.delete_tree(
                "Asset", 
                {"owner_id": 123, "item_id": 456}, 
                "LOCATED_IN"
            )
        """
        if not root_index:
            logger.warning("root_index 不能为空")
            return 0
        
        async with neo4j_manager.get_transaction() as tx:
            # 构建根节点的匹配条件
            root_conditions = []
            params = {}
            for key, value in root_index.items():
                root_conditions.append(f"root.{key} = ${key}")
                params[key] = value
            
            root_where = " AND ".join(root_conditions)
            
            # 构建查询：找到根节点及其所有通过指定关系连接的子树节点
            query = f"""
            MATCH (root:{root_label})
            WHERE {root_where}
            // 找到所有通过指定关系连接的子树节点（*1.. 表示至少1步，不包括根节点本身）
            OPTIONAL MATCH path = (root)-[:{relation_label}*1..]->(node)
            // 收集所有需要删除的节点（包括根节点），过滤掉 null
            WITH collect(DISTINCT node) AS nodes, root
            WITH [n IN nodes WHERE n IS NOT NULL] + [root] AS all_nodes
            UNWIND all_nodes AS n
            // 删除节点及其所有关系
            DETACH DELETE n
            RETURN count(n) AS deleted_count
            """
            
            result = await tx.run(query, params)
            record = await result.single()
            deleted_count = record["deleted_count"] if record else 0
            
            logger.info(
                f"删除树完成: root_label={root_label}, root_index={root_index}, "
                f"relation_label={relation_label}, deleted_count={deleted_count}"
            )
            
            return deleted_count

    @staticmethod
    async def merge_node(node_label: str, node_index: Dict[str, Any], node_properties: Dict[str, Any], max_retries: int = 50) -> bool:
        """通用的新建或更新节点函数
        
        Args:
            node_label: 节点的标签（如 "Asset", "Structure", "Station"）
            node_index: 用于匹配节点的属性字典，作为 MERGE 的唯一键（如 {"owner_id": 123, "item_id": 456}）
            node_properties: 要设置的所有属性字典（包括 node_index 中的属性）
            max_retries: 最大重试次数（用于处理死锁错误，默认50次）
            
        Returns:
            bool: 是否成功创建或更新了节点
            
        功能说明：
            1. 根据 node_label 和 node_index 查找节点，如果不存在则创建
            2. 如果节点是新创建的，使用 ON CREATE SET 设置所有属性
            3. 如果节点已存在，使用 ON MATCH SET 更新所有属性
            4. 自动处理死锁错误，使用指数退避策略重试
            
        示例：
            # 创建或更新一个 Asset 节点
            await Neo4jIndustryUtils.merge_node(
                "Asset",
                {"owner_id": 123, "item_id": 456},  # 唯一键
                {
                    "owner_id": 123,
                    "item_id": 456,
                    "owner_type": "character",
                    "type_id": 12345,
                    "quantity": 100
                }  # 所有属性
            )
        """
        if not node_index:
            logger.warning("node_index 不能为空")
            return False
        
        if not node_properties:
            logger.warning("node_properties 不能为空")
            return False
        
        # 重试逻辑：处理死锁错误
        for attempt in range(max_retries):
            try:
                async with neo4j_manager.get_transaction() as tx:
                    # 构建 MERGE 的匹配条件
                    merge_conditions = []
                    params = {}
                    for key, value in node_index.items():
                        merge_conditions.append(f"{key}: ${key}_index")
                        params[f"{key}_index"] = value
                    
                    merge_where = ", ".join(merge_conditions)
                    
                    # 构建 ON CREATE SET 和 ON MATCH SET 的属性设置
                    create_props = []
                    match_props = []
                    
                    for key, value in node_properties.items():
                        param_key = f"prop_{key}"
                        params[param_key] = value
                        
                        # 使用 COALESCE 处理 null 值：新建时使用新值，更新时如果新值为 null 则保留旧值
                        create_props.append(f"n.{key} = ${param_key}")
                        match_props.append(f"n.{key} = COALESCE(${param_key}, n.{key})")
                    
                    create_set = ", ".join(create_props)
                    match_set = ", ".join(match_props)
                    
                    # 构建查询
                    query = f"""
                    MERGE (n:{node_label} {{{merge_where}}})
                    ON CREATE SET {create_set}
                    ON MATCH SET {match_set}
                    RETURN n
                    """
                    
                    result = await tx.run(query, params)
                    record = await result.single()
                    
                    if record:
                        logger.debug(
                            f"节点合并成功: node_label={node_label}, node_index={node_index}"
                        )
                        return True
                    else:
                        logger.warning(
                            f"节点合并失败: node_label={node_label}, node_index={node_index}"
                        )
                        return False
            except TransientError as e:
                # 检查是否是死锁错误
                error_code = getattr(e, 'code', '') or ''
                is_deadlock = (
                    'DeadlockDetected' in str(e) or 
                    'Neo.TransientError.Transaction.DeadlockDetected' in error_code or
                    error_code == 'Neo.TransientError.Transaction.DeadlockDetected'
                )
                if is_deadlock:
                    if attempt < max_retries - 1:
                        # 指数退避：等待时间 = 0.1 * (2^attempt) 秒，最大2秒
                        wait_time = min(0.1 * (2 ** attempt), 2.0)
                        logger.debug(
                            f"检测到死锁错误，正在重试 ({attempt + 1}/{max_retries}): "
                            f"{node_label}{node_index}，等待 {wait_time:.2f} 秒后重试"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            f"节点合并失败（死锁错误，已重试 {max_retries} 次）: "
                            f"{node_label}{node_index}"
                        )
                        raise
                else:
                    # 其他类型的 TransientError，直接抛出
                    raise
            except Exception as e:
                # 非死锁错误，直接抛出
                logger.error(
                    f"节点合并时发生未预期的错误: {node_label}{node_index}, 错误: {str(e)}"
                )
                raise
        
        # 理论上不应该到达这里（所有重试都失败会抛出异常）
        # 但为了满足类型检查，添加此返回
        logger.error(
            f"节点合并失败（重试次数耗尽）: {node_label}{node_index}"
        )
        return False

    @staticmethod
    async def link_node(
        node_label: str,
        node_index: Dict[str, Any],
        node_properties: Dict[str, Any],
        relation_label: str,
        relation_index: Dict[str, Any],
        relation_properties: Dict[str, Any],
        target_node_label: str,
        target_node_index: Dict[str, Any],
        target_node_properties: Dict[str, Any],
        max_retries: int = 50
    ) -> bool:
        """使用指定关系连接两个节点，并设置节点和关系的属性
        
        Args:
            node_label: 源节点的标签（如 "Asset", "Structure", "Station"）
            node_index: 用于匹配源节点的属性字典，作为 MERGE 的唯一键（如 {"owner_id": 123, "item_id": 456}）
            node_properties: 源节点的属性字典，用于设置节点的所有属性
            relation_label: 关系的标签（如 "LOCATED_IN", "CONTAINS", "OWNED_BY"）
            relation_index: 关系的索引属性字典，用于在 MERGE 中匹配已存在的关系（可选）
                - 如果提供，MERGE 会在关系模式中包含这些属性进行匹配
                - 只有当所有 relation_index 属性都匹配时才会匹配到现有关系，否则创建新关系
                - 这允许在两个节点之间创建多条相同类型但不同属性的关系
                - 如果为空，则只匹配关系类型，两个节点之间只能有一条相同类型的关系
            relation_properties: 关系的属性字典，用于设置关系的所有属性（可选）
            target_node_label: 目标节点的标签（如 "Asset", "Structure", "Station"）
            target_node_index: 用于匹配目标节点的属性字典，作为 MERGE 的唯一键（如 {"owner_id": 123, "item_id": 456}）
            target_node_properties: 目标节点的属性字典，用于设置节点的所有属性
            max_retries: 最大重试次数（用于处理死锁错误，默认50次）
            
        Returns:
            bool: 是否成功创建了关系
            
        功能说明：
            1. 根据 node_label 和 node_index 找到或创建源节点，并设置 node_properties
            2. 根据 target_node_label 和 target_node_index 找到或创建目标节点，并设置 target_node_properties
            3. 使用 MERGE 创建源节点到目标节点的关系，并设置 relation_properties
                - 如果提供了 relation_index，MERGE 会在关系模式中包含这些属性进行匹配
                - 只有当所有 relation_index 属性都匹配时才会匹配到现有关系，否则创建新关系
            4. 如果关系已存在，则更新关系的属性
            5. 自动处理死锁错误，使用指数退避策略重试
            
        示例：
            # 连接两个 Asset 节点，创建 LOCATED_IN 关系（不提供 relation_index，两个节点之间只能有一条关系）
            await Neo4jIndustryUtils.link_node(
                "Asset",
                {"owner_id": 123, "item_id": 456},  # 源节点索引
                {"owner_id": 123, "item_id": 456, "type_id": 12345, "quantity": 100},  # 源节点属性
                "LOCATED_IN",
                {},  # 关系索引为空，只匹配关系类型
                {"distance": 1000},  # 关系属性（可选）
                "Asset",
                {"owner_id": 123, "item_id": 789},  # 目标节点索引
                {"owner_id": 123, "item_id": 789, "type_id": 67890, "quantity": 50}  # 目标节点属性
            )
            
            # 创建 PLAN_BP_DEPEND_ON 关系（提供 relation_index，允许创建多条不同属性的关系）
            await Neo4jIndustryUtils.link_node(
                "PlanBlueprint",
                {"user_name": "user1", "plan_name": "plan1", "type_id": 12345},  # 源节点索引
                {"user_name": "user1", "plan_name": "plan1", "type_id": 12345},  # 源节点属性
                "PLAN_BP_DEPEND_ON",
                {"user_name": "user1", "plan_name": "plan1", "index_id": 1, "product": 12345, "material": 67890},  # 关系索引
                {"user_name": "user1", "plan_name": "plan1", "index_id": 1, "product": 12345, "material": 67890, "material_num": 10},  # 关系属性
                "PlanBlueprint",
                {"user_name": "user1", "plan_name": "plan1", "type_id": 67890},  # 目标节点索引
                {"user_name": "user1", "plan_name": "plan1", "type_id": 67890}  # 目标节点属性
            )
        """
        if not node_index:
            logger.warning("node_index 不能为空")
            return False
        
        if not target_node_index:
            logger.warning("target_node_index 不能为空")
            return False
        
        # 确保 node_properties 和 target_node_properties 不为 None
        node_properties = node_properties or {}
        target_node_properties = target_node_properties or {}
        relation_properties = relation_properties or {}
        relation_index = relation_index or {}
        
        # 重试逻辑：处理死锁错误
        for attempt in range(max_retries):
            try:
                async with neo4j_manager.get_transaction() as tx:
                    # 构建源节点的 MERGE 条件
                    source_conditions = []
                    params = {}
                    for key, value in node_index.items():
                        source_conditions.append(f"{key}: ${key}_source_index")
                        params[f"{key}_source_index"] = value
                    
                    source_where = ", ".join(source_conditions)
                    
                    # 构建源节点的属性设置
                    source_create_props = []
                    source_match_props = []
                    for key, value in node_properties.items():
                        param_key = f"source_prop_{key}"
                        params[param_key] = value
                        source_create_props.append(f"source.{key} = ${param_key}")
                        source_match_props.append(f"source.{key} = COALESCE(${param_key}, source.{key})")
                    
                    source_create_set = ", ".join(source_create_props) if source_create_props else ""
                    source_match_set = ", ".join(source_match_props) if source_match_props else ""
                    
                    # 构建目标节点的 MERGE 条件
                    target_conditions = []
                    for key, value in target_node_index.items():
                        target_conditions.append(f"{key}: ${key}_target_index")
                        params[f"{key}_target_index"] = value
                    
                    target_where = ", ".join(target_conditions)
                    
                    # 构建目标节点的属性设置
                    target_create_props = []
                    target_match_props = []
                    for key, value in target_node_properties.items():
                        param_key = f"target_prop_{key}"
                        params[param_key] = value
                        target_create_props.append(f"target.{key} = ${param_key}")
                        target_match_props.append(f"target.{key} = COALESCE(${param_key}, target.{key})")
                    
                    target_create_set = ", ".join(target_create_props) if target_create_props else ""
                    target_match_set = ", ".join(target_match_props) if target_match_props else ""
                    
                    # 将 relation_index 的属性合并到 relation_properties 中（如果存在）
                    # 这样可以在创建关系时设置这些属性
                    if relation_index:
                        for key, value in relation_index.items():
                            if key not in relation_properties:
                                relation_properties[key] = value
                    
                    # 构建关系的属性设置
                    relation_create_props = []
                    relation_match_props = []
                    for key, value in relation_properties.items():
                        param_key = f"rel_prop_{key}"
                        params[param_key] = value
                        relation_create_props.append(f"r.{key} = ${param_key}")
                        relation_match_props.append(f"r.{key} = COALESCE(${param_key}, r.{key})")
                    
                    relation_create_set = ", ".join(relation_create_props) if relation_create_props else ""
                    relation_match_set = ", ".join(relation_match_props) if relation_match_props else ""
                    
                    # 构建关系的 MERGE 匹配条件（如果 relation_index 不为空，则在 MERGE 中包含属性匹配）
                    relation_merge_conditions = []
                    if relation_index:
                        # 如果提供了 relation_index，则在 MERGE 模式中包含这些属性用于匹配
                        # 这样只有当所有属性都匹配时才会匹配到现有关系，否则创建新关系
                        for key, value in relation_index.items():
                            param_key = f"rel_index_{key}"
                            params[param_key] = value
                            relation_merge_conditions.append(f"{key}: ${param_key}")
                    
                    relation_merge_where = ", ".join(relation_merge_conditions) if relation_merge_conditions else ""
                    relation_merge_pattern = f"[r:{relation_label}]" if not relation_merge_where else f"[r:{relation_label} {{{relation_merge_where}}}]"
                    
                    # 构建查询：MERGE 源节点、目标节点，然后创建关系
                    query_parts = [
                        f"// 找到或创建源节点",
                        f"MERGE (source:{node_label} {{{source_where}}})"
                    ]
                    
                    if source_create_set:
                        query_parts.append(f"ON CREATE SET {source_create_set}")
                    if source_match_set:
                        query_parts.append(f"ON MATCH SET {source_match_set}")
                    
                    query_parts.extend([
                        f"// 找到或创建目标节点",
                        f"WITH source",
                        f"MERGE (target:{target_node_label} {{{target_where}}})"
                    ])
                    
                    if target_create_set:
                        query_parts.append(f"ON CREATE SET {target_create_set}")
                    if target_match_set:
                        query_parts.append(f"ON MATCH SET {target_match_set}")
                    
                    query_parts.extend([
                        f"// 创建或更新关系",
                        f"WITH source, target",
                        f"MERGE (source)-{relation_merge_pattern}->(target)"
                    ])
                    
                    if relation_create_set:
                        query_parts.append(f"ON CREATE SET {relation_create_set}")
                    if relation_match_set:
                        query_parts.append(f"ON MATCH SET {relation_match_set}")
                    
                    query_parts.append("RETURN r")
                    
                    query = "\n".join(query_parts)
                    
                    result = await tx.run(query, params)
                    record = await result.single()
                    
                    if record:
                        logger.debug(
                            f"节点连接成功: {node_label}{node_index} -[{relation_label}]-> "
                            f"{target_node_label}{target_node_index}"
                        )
                        return True
                    else:
                        logger.warning(
                            f"节点连接失败: {node_label}{node_index} -[{relation_label}]-> "
                            f"{target_node_label}{target_node_index}"
                        )
                        return False
            except TransientError as e:
                # 检查是否是死锁错误
                error_code = getattr(e, 'code', '') or ''
                is_deadlock = (
                    'DeadlockDetected' in str(e) or 
                    'Neo.TransientError.Transaction.DeadlockDetected' in error_code or
                    error_code == 'Neo.TransientError.Transaction.DeadlockDetected'
                )
                if is_deadlock:
                    if attempt < max_retries - 1:
                        # 指数退避：等待时间 = 0.1 * (2^attempt) 秒，最大2秒
                        wait_time = min(0.1 * (2 ** attempt), 2.0)
                        logger.debug(
                            f"检测到死锁错误，正在重试 ({attempt + 1}/{max_retries}): "
                            f"{node_label}{node_index} -[{relation_label}]-> {target_node_label}{target_node_index}，"
                            f"等待 {wait_time:.2f} 秒后重试"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            f"节点连接失败（死锁错误，已重试 {max_retries} 次）: "
                            f"{node_label}{node_index} -[{relation_label}]-> "
                            f"{target_node_label}{target_node_index}"
                        )
                        raise
                else:
                    # 其他类型的 TransientError，直接抛出
                    raise
            except Exception as e:
                # 非死锁错误，直接抛出
                logger.error(
                    f"节点连接时发生未预期的错误: {node_label}{node_index} -[{relation_label}]-> "
                    f"{target_node_label}{target_node_index}, 错误: {str(e)}"
                )
                raise
        
        # 如果所有重试都失败了（不应该到达这里，因为会在循环中抛出异常）
        return False

    @staticmethod
    async def get_blueprint_tree(type_id: int) -> Tuple[Dict, List[Tuple[int, int, Dict]]]:
        async with neo4j_manager.get_session() as session:
            # 查询所有Blueprint节点和BP_DEPEND_ON关系
            # 使用MATCH找到根节点及其所有子节点
            query = """
            MATCH (root:Blueprint {type_id: $type_id})
            OPTIONAL MATCH path = (root)-[:BP_DEPEND_ON*0..]->(child:Blueprint)
            WITH collect(DISTINCT child) AS children, root
            WITH children + [root] AS all_nodes
            UNWIND all_nodes AS node
            OPTIONAL MATCH (node)-[r:BP_DEPEND_ON]->(child:Blueprint)
            WHERE child IN all_nodes
            RETURN node, collect({rel: r, child: child}) AS relationships
            """
            # 存储所有节点和关系
            nodes_dict = {}  # {type_id: node_properties}
            relationships_list = []  # [(parent_type_id, child_type_id, rel_properties)]
            result = await session.run(query, {"type_id": type_id})
            async for record in result:
                node = record["node"]
                if node is None:
                    continue
                    
                node_type_id = node.get("type_id")
                if node_type_id is None:
                    continue
                
                # 存储节点属性
                nodes_dict[node_type_id] = dict(node.items())
                
                # 处理关系
                rels = record.get("relationships", [])
                for rel_data in rels:
                    if rel_data.get("rel") is None or rel_data.get("child") is None:
                        continue
                    
                    rel = rel_data["rel"]
                    child = rel_data["child"]
                    child_type_id = child.get("type_id")
                    
                    if child_type_id is not None:
                        # 存储关系属性
                        rel_props = dict(rel.items())
                        relationships_list.append((node_type_id, child_type_id, rel_props))

            return nodes_dict, relationships_list

    @staticmethod
    async def get_relations(
        relation_label: str,
        relation_index: Dict[str, Any],
        source_label: Optional[str] = None,
        source_index: Optional[Dict[str, Any]] = None,
        target_label: Optional[str] = None,
        target_index: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """通用的查询边（关系）方法
        
        Args:
            relation_label: 关系的标签（如 "LOCATED_IN", "PLAN_BP_DEPEND_ON", "BP_DEPEND_ON"）
            relation_index: 用于匹配关系的属性字典（如 {"user_name": "user1", "plan_name": "plan1", "index_id": 1}）
            source_label: 源节点的标签（可选，如 "Asset", "PlanBlueprint"）
            source_index: 用于筛选源节点的属性字典（可选，如 {"owner_id": 123, "item_id": 456}）
            target_label: 目标节点的标签（可选，如 "Asset", "PlanBlueprint"）
            target_index: 用于筛选目标节点的属性字典（可选，如 {"type_id": 12345}）
            
        Returns:
            List[Dict[str, Any]]: 匹配的关系列表，每个元素包含：
                - "relation": 关系的属性字典
                - "source": 源节点的属性字典（如果提供了 source_label）
                - "target": 目标节点的属性字典（如果提供了 target_label）
            
        功能说明：
            1. 根据 relation_label 和 relation_index 匹配关系
            2. 如果提供了 source_label 和 source_index，则同时筛选源节点
            3. 如果提供了 target_label 和 target_index，则同时筛选目标节点
            4. 返回所有匹配的关系及其关联的节点信息
            
        示例：
            # 查询所有满足关系索引的 PLAN_BP_DEPEND_ON 关系
            relations = await Neo4jIndustryUtils.get_relations(
                "PLAN_BP_DEPEND_ON",
                {"user_name": "user1", "plan_name": "plan1", "index_id": 1}
            )
            
            # 查询指定源节点的关系
            relations = await Neo4jIndustryUtils.get_relations(
                "PLAN_BP_DEPEND_ON",
                {"user_name": "user1", "plan_name": "plan1"},
                source_label="PlanBlueprint",
                source_index={"user_name": "user1", "plan_name": "plan1", "type_id": 12345}
            )
            
            # 查询指定源节点和目标节点的关系
            relations = await Neo4jIndustryUtils.get_relations(
                "LOCATED_IN",
                {},
                source_label="Asset",
                source_index={"owner_id": 123, "item_id": 456},
                target_label="Structure",
                target_index={"structure_id": 789}
            )
        """
        # relation_index 可以为空字典，表示不限制关系属性
        relation_index = relation_index or {}
        
        async with neo4j_manager.get_session() as session:
            # 构建源节点的匹配条件
            source_match = ""
            source_conditions = []
            if source_label:
                source_match = f"(source:{source_label})"
                if source_index:
                    for key, value in source_index.items():
                        source_conditions.append(f"source.{key} = $source_{key}")
            else:
                source_match = "(source)"
            
            # 构建目标节点的匹配条件
            target_match = ""
            target_conditions = []
            if target_label:
                target_match = f"(target:{target_label})"
                if target_index:
                    for key, value in target_index.items():
                        target_conditions.append(f"target.{key} = $target_{key}")
            else:
                target_match = "(target)"
            
            # 构建关系的 WHERE 条件
            relation_conditions = []
            params = {}
            for key, value in relation_index.items():
                relation_conditions.append(f"r.{key} = $rel_{key}")
                params[f"rel_{key}"] = value
            
            # 添加源节点的参数
            if source_index:
                for key, value in source_index.items():
                    params[f"source_{key}"] = value
            
            # 添加目标节点的参数
            if target_index:
                for key, value in target_index.items():
                    params[f"target_{key}"] = value
            
            # 构建 WHERE 子句
            where_parts = []
            if relation_conditions:
                where_parts.append(" AND ".join(relation_conditions))
            if source_conditions:
                where_parts.append(" AND ".join(source_conditions))
            if target_conditions:
                where_parts.append(" AND ".join(target_conditions))
            
            where_clause = " AND ".join(where_parts) if where_parts else "1=1"
            
            # 构建 RETURN 子句
            return_parts = ["r AS relation"]
            if source_label:
                return_parts.append("source AS source_node")
            if target_label:
                return_parts.append("target AS target_node")
            
            return_clause = ", ".join(return_parts)
            
            # 构建查询
            query = f"""
            MATCH {source_match}-[r:{relation_label}]->{target_match}
            WHERE {where_clause}
            RETURN {return_clause}
            """
            
            result = await session.run(query, params)
            relations = []
            async for record in result:
                relation_dict = {}
                
                # 获取关系属性
                rel = record.get("relation")
                if rel:
                    relation_dict["relation"] = dict(rel.items())
                else:
                    relation_dict["relation"] = {}
                
                # 获取源节点属性（如果提供了 source_label）
                if source_label and "source_node" in record:
                    source_node = record.get("source_node")
                    if source_node:
                        relation_dict["source"] = dict(source_node.items())
                
                # 获取目标节点属性（如果提供了 target_label）
                if target_label and "target_node" in record:
                    target_node = record.get("target_node")
                    if target_node:
                        relation_dict["target"] = dict(target_node.items())
                
                relations.append(relation_dict)
            
            logger.debug(
                f"查询关系完成: relation_label={relation_label}, relation_index={relation_index}, "
                f"source_label={source_label}, target_label={target_label}, "
                f"found_count={len(relations)}"
            )
            
            return relations

    @staticmethod
    async def get_node_properties(node_label: str, node_index: Dict[str, Any]) -> Dict[str, Any]:
        """获取已存在节点的所有属性
        
        Args:
            node_label: 节点的标签（如 "Asset", "Structure", "Station"）
            node_index: 用于匹配节点的属性字典（如 {"owner_id": 123, "item_id": 456}）
            
        Returns:
            Dict[str, Any]: 节点的所有属性字典，如果节点不存在则返回空字典
            
        功能说明：
            1. 根据 node_label 和 node_index 匹配节点
            2. 返回节点的所有属性
            3. 如果节点不存在，返回空字典
            
        示例：
            # 获取一个 Asset 节点的所有属性
            properties = await Neo4jIndustryUtils.get_node_properties(
                "Asset",
                {"owner_id": 123, "item_id": 456}  # 匹配条件
            )
            if properties:
                print(f"节点数量: {properties.get('quantity')}")
        """
        if not node_index:
            logger.warning("node_index 不能为空")
            return {}
        
        async with neo4j_manager.get_session() as session:
            # 构建 MATCH 的 WHERE 条件
            where_conditions = []
            params = {}
            for key, value in node_index.items():
                where_conditions.append(f"n.{key} = ${key}_index")
                params[f"{key}_index"] = value
            
            where_clause = " AND ".join(where_conditions)
            
            # 构建查询
            query = f"""
            MATCH (n:{node_label})
            WHERE {where_clause}
            RETURN n
            """
            
            result = await session.run(query, params)
            record = await result.single()
            
            if record and record["n"]:
                node = record["n"]
                # 将 Neo4j Node 对象转换为字典
                node_dict = dict(node)
                logger.debug(
                    f"节点属性获取成功: node_label={node_label}, node_index={node_index}"
                )
                return node_dict
            else:
                logger.debug(
                    f"节点不存在: node_label={node_label}, node_index={node_index}"
                )
                return {}

    @staticmethod
    async def get_relation_properties(relation_label: str, relation_index: Dict[str, Any]) -> Dict[str, Any]:
        # 获取已存在的关系的属性
        pass

    @staticmethod
    async def get_user_plan_node_with_distance(user_name: str, plan_name: str) -> List[Dict[str, Any]]:
        """获取用户计划的所有节点
        
        Args:
            user_name: 用户名
            plan_name: 计划名称
            
        Returns:
            List[Dict[str, Any]]: 匹配的所有 PlanBlueprint 节点列表，每个节点以字典形式返回
        """
        async with neo4j_manager.get_session() as session:
            query = """
                //收集距离
                MATCH path = (a:PlanBlueprint|Plan {user_name: $user_name, plan_name: $plan_name})-[:PLAN_BP_DEPEND_ON*1..20]->(b)
                WHERE NOT EXISTS { ()-[]->(a) }
                WITH a, b, length(path) AS path_length
                RETURN a, b, 
                        min(path_length) AS min_distance,
                        max(path_length) AS max_distance
            """
            result = await session.run(query, {"user_name": user_name, "plan_name": plan_name})
            nodes = []
            async for record in result:
                node = record["b"]
                if node:
                    # 将 Neo4j Node 对象转换为字典
                    node_dict = dict(node)
                    node_dict["min_distance"] = record["min_distance"]
                    node_dict["max_distance"] = record["max_distance"]
                    nodes.append(node_dict)
            return nodes

    @staticmethod
    async def get_user_plan_relation(user_name: str, plan_name: str) -> List[Dict[str, Any]]:
        """获取用户计划的所有关系
        
        Args:
            user_name: 用户名
            plan_name: 计划名称
            
        Returns:
            List[Dict[str, Any]]: 匹配的所有 PLAN_BP_DEPEND_ON 关系列表，每个关系以字典形式返回
        """
        async with neo4j_manager.get_session() as session:
            query = """
            MATCH (n:PlanBlueprint|Plan {user_name: $user_name, plan_name: $plan_name})-[path:PLAN_BP_DEPEND_ON]->(m:PlanBlueprint)
            RETURN path
            """
            result = await session.run(query, {"user_name": user_name, "plan_name": plan_name})
            relations = []
            async for record in result:
                relation = record["path"]
                if relation:
                    # 将 Neo4j Node 对象转换为字典
                    relations.append(dict(relation))
            return relations

    @staticmethod
    async def update_node_properties(node_label: str, node_index: Dict[str, Any], node_properties: Dict[str, Any]) -> int:
        """更新已存在节点的属性
        
        Args:
            node_label: 节点的标签（如 "Asset", "Structure", "Station"）
            node_index: 用于匹配节点的属性字典（如 {"owner_id": 123, "item_id": 456}）
            node_properties: 要更新的属性字典
            
        Returns:
            int: 更新的节点数量
            
        功能说明：
            1. 根据 node_label 和 node_index 匹配节点
            2. 使用 SET 更新节点的所有属性（使用 node_properties 中的值）
            3. 只更新已存在的节点，如果节点不存在则不进行任何操作
            
        示例：
            # 更新一个 Asset 节点的属性
            updated_count = await Neo4jIndustryUtils.update_node_properties(
                "Asset",
                {"owner_id": 123, "item_id": 456},  # 匹配条件
                {"quantity": 200, "type_name": "New Name"}  # 要更新的属性
            )
        """
        if not node_index:
            logger.warning("node_index 不能为空")
            return 0
        
        if not node_properties:
            logger.warning("node_properties 不能为空")
            return 0
        
        async with neo4j_manager.get_transaction() as tx:
            # 构建 MATCH 的 WHERE 条件
            where_conditions = []
            params = {}
            for key, value in node_index.items():
                where_conditions.append(f"n.{key} = ${key}_index")
                params[f"{key}_index"] = value
            
            where_clause = " AND ".join(where_conditions)
            
            # 构建 SET 的属性设置
            set_props = []
            for key, value in node_properties.items():
                param_key = f"prop_{key}"
                params[param_key] = value
                set_props.append(f"n.{key} = ${param_key}")
            
            set_clause = ", ".join(set_props)
            
            # 构建查询
            query = f"""
            MATCH (n:{node_label})
            WHERE {where_clause}
            SET {set_clause}
            RETURN count(n) AS updated_count
            """
            
            result = await tx.run(query, params)
            record = await result.single()
            updated_count = record["updated_count"] if record else 0
            
            logger.debug(
                f"节点属性更新完成: node_label={node_label}, node_index={node_index}, "
                f"updated_count={updated_count}"
            )
            
            return updated_count

    @staticmethod
    async def update_relation_properties(relation_label: str, relation_index: Dict[str, Any], relation_properties: Dict[str, Any]) -> int:
        """更新已存在关系的属性
        
        Args:
            relation_label: 关系的标签（如 "LOCATED_IN", "PLAN_BP_DEPEND_ON", "BP_DEPEND_ON"）
            relation_index: 用于匹配关系的属性字典（如 {"user_name": "user1", "plan_name": "plan1", "index_id": 1}）
            relation_properties: 要更新的关系属性字典
            
        Returns:
            int: 更新的关系数量
            
        功能说明：
            1. 根据 relation_label 和 relation_index 匹配关系
            2. 使用 SET 更新关系的所有属性（使用 relation_properties 中的值）
            3. 只更新已存在的关系，如果关系不存在则不进行任何操作
            
        示例：
            # 更新一个 PLAN_BP_DEPEND_ON 关系的属性
            updated_count = await Neo4jIndustryUtils.update_relation_properties(
                "PLAN_BP_DEPEND_ON",
                {"user_name": "user1", "plan_name": "plan1", "index_id": 1, "product": 12345, "material": 67890},  # 匹配条件
                {"material_num": 20, "unit_cost": 100.5}  # 要更新的属性
            )
        """
        if not relation_index:
            logger.warning("relation_index 不能为空")
            return 0
        
        if not relation_properties:
            logger.warning("relation_properties 不能为空")
            return 0
        
        async with neo4j_manager.get_transaction() as tx:
            # 构建关系的 WHERE 条件
            where_conditions = []
            params = {}
            for key, value in relation_index.items():
                where_conditions.append(f"r.{key} = ${key}_index")
                params[f"{key}_index"] = value
            
            where_clause = " AND ".join(where_conditions)
            
            # 构建 SET 的属性设置
            set_props = []
            for key, value in relation_properties.items():
                param_key = f"prop_{key}"
                params[param_key] = value
                set_props.append(f"r.{key} = ${param_key}")
            
            set_clause = ", ".join(set_props)
            
            # 构建查询：匹配关系并更新属性
            query = f"""
            MATCH ()-[r:{relation_label}]->()
            WHERE {where_clause}
            SET {set_clause}
            RETURN count(r) AS updated_count
            """
            
            result = await tx.run(query, params)
            record = await result.single()
            updated_count = record["updated_count"] if record else 0
            
            logger.debug(
                f"关系属性更新完成: relation_label={relation_label}, relation_index={relation_index}, "
                f"updated_count={updated_count}"
            )
            
            return updated_count

    @staticmethod
    async def delete_label_node(label: str):
        """删除指定标签的节点"""
        async with neo4j_manager.get_transaction() as tx:
            query = f"MATCH (n:{label}) DETACH DELETE n RETURN count(n) AS deleted_count"
            result = await tx.run(query)
            record = await result.single()
            deleted_count = record["deleted_count"] if record else 0
            return deleted_count

    @staticmethod
    async def get_structure_node_by_id(structure_id: int) -> Dict[str, Any]:
        """获取结构节点"""
        async with neo4j_manager.get_session() as session:
            query = "MATCH (n:Structure {structure_id: $structure_id}) RETURN n"
            result = await session.run(query, {"structure_id": structure_id})
            record = await result.single()
            return dict(record["n"])