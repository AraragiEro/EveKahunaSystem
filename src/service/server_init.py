import sys
import asyncio
from .asset_server.asset_manager import AssetManager
from .character_server.character_manager import CharacterManager
from .google_server.googlesheet_kahuna import kahuna_google_market_monitor
from .industry_server.industry_advice import IndustryAdvice
from .industry_server.industry_config import IndustryConfigManager
from .industry_server.industry_manager import IndustryManager
from .industry_server.structure import StructureManager
from .industry_server.order import order_manager
from .market_server.market_manager import MarketManager
from .user_server.user_manager import UserManager
from .evesso_server.esi_req_manager import init_esi_manager
from .log_server import logger
from .industry_server.providers import init_providers
from .database_server.sqlalchemy.connect_manager import database_manager as dbm
from ..utils import run_func_delay_min, async_refresh_per_min

init_flag = False


async def init_server_service(log: bool = True):
    if not log:
        logger.setLevel(sys.maxsize)
    # 同步初始化
    # DatabaseConectManager.init()
    await dbm.init()
    await CharacterManager.init()
    await UserManager.init()
    await StructureManager.init()
    await AssetManager.init()
    await IndustryConfigManager.init()
    MarketManager.init()
    await init_providers()
    await init_esi_manager()

    global init_flag
    init_flag = True


async def init_server_cycle_mission():
    # 延时初始化
    asyncio.create_task(run_func_delay_min(0, CharacterManager.refresh_all_characters_at_init))
    asyncio.create_task(async_refresh_per_min(0, 5, MarketManager.refresh_market))
    asyncio.create_task(async_refresh_per_min(0, 5, AssetManager.refresh_all_asset))
    asyncio.create_task(async_refresh_per_min(0, 5, IndustryManager.refresh_running_status))
    asyncio.create_task(async_refresh_per_min(0, 20, IndustryManager.refresh_system_cost))
    asyncio.create_task(async_refresh_per_min(0, 20, IndustryManager.refresh_market_price))
    asyncio.create_task(async_refresh_per_min(0, 28, IndustryAdvice.refresh_all_asset_statistics))
    asyncio.create_task(async_refresh_per_min(0, 60, order_manager.refresh_all_order))
    asyncio.create_task(async_refresh_per_min(0, 34, kahuna_google_market_monitor.refresh_market_monitor_process))

async def init_server(log=True):
    await init_server_service()
    await init_server_cycle_mission()

