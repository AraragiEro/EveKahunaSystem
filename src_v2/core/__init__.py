async def init_database():
    from src_v2.core.database.connect_manager import postgres_manager, redis_manager, neo4j_manager

    await postgres_manager.init()
    await redis_manager.init()
    await neo4j_manager.init()
