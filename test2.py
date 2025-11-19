import asyncio

AAQQ = 461630479



async def test1():
    # await init_server_service()
    from src_v2.core.database.connect_manager import postgres_manager, redis_manager
    from src_v2.backend.app import init_backend
    from src_v2.model.EVE.eveesi.esi_req_manager import init_esi_manager
    from src_v2.model.EVE.character.character_manager import CharacterManager
    from src_v2.core.user.user_manager import UserManager

    await postgres_manager.init()
    await redis_manager.init()

    await init_esi_manager()
    await init_backend()
    print(111)

async def test2():
    from src_v2.core.database.connect_manager import postgres_manager, redis_manager, neo4j_manager
    from src_v2.backend.app import init_backend
    from src_v2.model.EVE.eveesi.esi_req_manager import init_esi_manager
    from src_v2.model.EVE.character.character_manager import CharacterManager
    from src_v2.core.user.user_manager import UserManager
    from src_v2.model.EVE.asset.asset_manager import AssetManager
    from src_v2.core.database.kahuna_database_utils_v2 import EveAssetPullMissionDBUtils
    from src_v2.core.database.neo4j_utils import Neo4jIndustryUtils as NIU

    await postgres_manager.init()
    await redis_manager.init()
    await neo4j_manager.init()
    
    await init_esi_manager()
    # await init_backend()


    # mission_obj = await EveAssetPullMissionDBUtils.select_mission_by_owner_id_and_owner_type(98446928, 'corp')
    # await AssetManager().processing_asset_pull_mission(mission_obj)
    # await AssetManager().clean_asset_pull_mission_assets(mission_obj)
    # await AssetManager().processing_asset_pull_mission(mission_obj)

    from src_v2.model.EVE.industry.industry_manager import IndustryManager
    from src_v2.model.EVE.industry.industry_utils import MarketTree
    plan_dict = {
        "plan_name": "test",
        "user_name": "111111",
        "plan_settings": {
            "considerate_asset": False,
            "considerate_running_job": False,
            
            "split_to_jobs": True,
            "considerate_bp_relation": True,
            
            "work_type": "in_order" # in_order | whole
        },
        "products": [
            {
                "index_id": 1,
                "type_id": 28661,
                "quantity": 16
            },
            {
                "index_id": 2,
                "type_id": 12005,
                "quantity": 100
            },
            {
                "index_id": 3,
                "type_id": 3764,
                "quantity": 2
            }
        ],
    }
    # await IndustryManager().delete_plan("test", "111111")
    # await IndustryManager().create_plan(plan_dict)
    # await IndustryManager().create_plan_tree(plan_dict)
    # await IndustryManager().update_plan_status("test", "111111")
    
    await MarketTree.init_market_tree(clean=True)
    await MarketTree.link_type_to_market_group(clean=True)
    print(111)
    
    
    # from src_v2.model.EVE.industry.blueprint import BPManager
    # await BPManager.init_bp_data_to_neo4j()
    # await NIU.delete_label_node(label="Blueprint")

    # print(111)

async def main():
    # init_server()
    await test2()
    pass

if __name__ == '__main__':
    # asyncio.run(main())
    asyncio.run(main())