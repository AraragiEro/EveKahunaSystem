import os
os.environ["KAHUNA_DB_DIR"] = r"F:\WorkSpace\GIT\kahuna_bot\AstrBot\data\plugins\kahuna_bot"

# 导出新的 SQLAlchemy 模型（从 sde_builder）
from .sde_builder import (
    InvTypes,
    InvGroups,
    InvCategories,
    MetaGroups,
    IndustryActivityMaterials,
    IndustryActivityProducts,
    IndustryBlueprints,
    IndustryActivities,
    MapSolarSystems,
    MapRegions,
    MarketGroups,
)
from .utils import SdeUtils