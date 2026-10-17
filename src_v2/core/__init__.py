async def init_database(subprocess=False):
    from src_v2.core.database.connect_manager import get_postgres_manager, get_redis_manager, get_neo4j_manager
    from src_v2.model.EVE.sde.sde_builder.database_manager import sde_database_manager

    await get_postgres_manager().init(subprocess=subprocess)
    await get_redis_manager().init()
    await get_neo4j_manager().init(subprocess=subprocess)
    await sde_database_manager.init(subprocess=subprocess)

async def close_database():
    from src_v2.core.database.connect_manager import get_postgres_manager, get_redis_manager, get_neo4j_manager
    from src_v2.model.EVE.sde.sde_builder.database_manager import sde_database_manager
    
    await sde_database_manager.close()
    await get_postgres_manager().close()
    await get_redis_manager().close()
    await get_neo4j_manager().close()