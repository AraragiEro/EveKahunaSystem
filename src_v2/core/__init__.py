async def init_database(subprocess=False):
    from src_v2.core.database.connect_manager import postgres_manager, redis_manager, neo4j_manager
    from src_v2.model.EVE.sde.sde_builder.database_manager import sde_database_manager

    await postgres_manager.init(subprocess=subprocess)
    await redis_manager.init()
    await neo4j_manager.init(subprocess=subprocess)
    await sde_database_manager.init(subprocess=subprocess)

async def close_database():
    from src_v2.core.database.connect_manager import postgres_manager, redis_manager, neo4j_manager
    from src_v2.model.EVE.sde.sde_builder.database_manager import sde_database_manager
    
    await sde_database_manager.close()
    await postgres_manager.close()
    await redis_manager.close()
    await neo4j_manager.close()