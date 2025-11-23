"""
SDE Builder 模块
用于从官方网站下载、解压、解析并导入 SDE 数据到 PostgreSQL 数据库
"""

from .sde_builder import SDEBuilder
from .database_manager import SDEDatabaseManager, SDEModel
from .downloader import SDEDownloader
from .extractor import SDEExtractor
from .parser import SDEParser
from .importer import SDEImporter
from .model_generator import SDEModelGenerator
from .inv_types_model import InvTypes, process_inv_types_row, calculate_packaged_volume
from .blueprints_model import (
    IndustryBlueprints, IndustryActivities, IndustryActivityMaterials, IndustryActivityProducts,
    process_blueprints_row
)
from .meta_groups_model import MetaGroups, process_meta_groups_row
from .inv_groups_model import InvGroups, process_inv_groups_row
from .inv_categories_model import InvCategories, process_inv_categories_row
from .market_groups_model import MarketGroups, process_market_groups_row
from .map_solar_systems_model import MapSolarSystems, process_map_solar_systems_row
from .map_regions_model import MapRegions, process_map_regions_row

__all__ = [
    'SDEBuilder',
    'SDEDatabaseManager',
    'SDEModel',
    'SDEDownloader',
    'SDEExtractor',
    'SDEParser',
    'SDEImporter',
    'SDEModelGenerator',
    'InvTypes',
    'process_inv_types_row',
    'calculate_packaged_volume',
    'IndustryBlueprints',
    'IndustryActivities',
    'IndustryActivityMaterials',
    'IndustryActivityProducts',
    'process_blueprints_row',
    'MetaGroups',
    'process_meta_groups_row',
    'InvGroups',
    'process_inv_groups_row',
    'InvCategories',
    'process_inv_categories_row',
    'MarketGroups',
    'process_market_groups_row',
    'MapSolarSystems',
    'process_map_solar_systems_row',
    'MapRegions',
    'process_map_regions_row',
]

