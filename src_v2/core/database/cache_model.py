from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, JSON, UniqueConstraint, \
    BigInteger
from sqlalchemy.ext.declarative import declarative_base

__all__ = []

from .connect_manager import CacheModel


class Asset(CacheModel):
    __tablename__ = 'asset'
    id=Column(Integer, primary_key=True)
    asset_type = Column(Integer)
    owner_id = Column(Integer)
    is_blueprint_copy = Column(Boolean)
    is_singleton = Column(Boolean)
    item_id = Column(BigInteger)
    location_flag = Column(Text)
    location_id = Column(BigInteger)
    location_type = Column(Text)
    quantity = Column(Integer)
    type_id = Column(Integer)
    __table_args__ = (
        UniqueConstraint('item_id', 'owner_id', 'quantity'),
    )

class AssetCache(CacheModel):
    __tablename__ = 'asset_cache'
    id = Column(Integer, primary_key=True)
    asset_type = Column(Integer)
    owner_id = Column(Integer)
    is_blueprint_copy = Column(Boolean)
    is_singleton = Column(Boolean)
    item_id = Column(BigInteger)
    location_flag = Column(Text)
    location_id = Column(BigInteger)
    location_type = Column(Text)
    quantity = Column(Integer)
    type_id = Column(Integer)
    __table_args__ = (
        UniqueConstraint('item_id', 'owner_id', 'quantity'),
    )


class MarketOrder(CacheModel):
    __tablename__ = 'market_order'
    id = Column(Integer, primary_key=True)
    duration = Column(Integer)
    is_buy_order = Column(Boolean)
    issued = Column(Text)
    location_id = Column(Integer)
    min_volume = Column(Integer)
    order_id = Column(Float)
    price = Column(Float)
    range = Column(Text)
    system_id = Column(Integer, nullable=True)
    type_id = Column(Integer)
    volume_remain = Column(Integer)
    volume_total = Column(Integer)


class MarketOrderCache(CacheModel):
    __tablename__ = 'market_order_cache'
    id = Column(Integer, primary_key=True)
    duration = Column(Integer)
    is_buy_order = Column(Boolean)
    issued = Column(Text)
    location_id = Column(Integer)
    min_volume = Column(Integer)
    order_id = Column(Float)
    price = Column(Float)
    range = Column(Text)
    system_id = Column(Integer, nullable=True)
    type_id = Column(Integer)
    volume_remain = Column(Integer)
    volume_total = Column(Integer)


class IndustryJobs(CacheModel):
    __tablename__ = 'industry_jobs'
    id = Column(Integer, primary_key=True)
    activity_id = Column(Integer)
    blueprint_id = Column(BigInteger)
    blueprint_location_id = Column(BigInteger)
    blueprint_type_id = Column(Integer)
    completed_character_id = Column(Integer, nullable=True)
    completed_date = Column(Text, nullable=True)
    cost = Column(Float, nullable=True)
    duration = Column(Integer)
    end_date = Column(Text)
    facility_id = Column(BigInteger)
    installer_id = Column(Integer)
    job_id = Column(Integer)
    licensed_runs = Column(Integer, nullable=True)
    location_id = Column(BigInteger)  # station_id in character api return
    output_location_id = Column(BigInteger)
    pause_date = Column(Text, nullable=True)
    probability = Column(Float, nullable=True)
    product_type_id = Column(Integer, nullable=True)
    runs = Column(Integer)
    start_date = Column(Text)
    status = Column(Text)
    successful_runs = Column(Integer, nullable=True)
    owner_id = Column(Integer)


class IndustryJobsCache(CacheModel):
    __tablename__ = 'industry_jobs_cache'
    id = Column(Integer, primary_key=True)
    activity_id = Column(Integer)
    blueprint_id = Column(BigInteger)
    blueprint_location_id = Column(BigInteger)
    blueprint_type_id = Column(Integer)
    completed_character_id = Column(Integer, nullable=True)
    completed_date = Column(Text, nullable=True)
    cost = Column(Float, nullable=True)
    duration = Column(Integer)
    end_date = Column(Text)
    facility_id = Column(BigInteger)
    installer_id = Column(Integer)
    job_id = Column(Integer)
    licensed_runs = Column(Integer, nullable=True)
    location_id = Column(BigInteger)  # station_id in character api return
    output_location_id = Column(BigInteger)
    pause_date = Column(Text, nullable=True)
    probability = Column(Float, nullable=True)
    product_type_id = Column(Integer, nullable=True)
    runs = Column(Integer)
    start_date = Column(Text)
    status = Column(Text)
    successful_runs = Column(Integer, nullable=True)

    owner_id = Column(Integer)


class SystemCost(CacheModel):
    __tablename__ = "system_cost"
    solar_system_id = Column(Integer, primary_key=True)
    manufacturing = Column(Float, nullable=True)
    researching_time_efficiency = Column(Float, nullable=True)
    researching_material_efficiency = Column(Float, nullable=True)
    copying = Column(Float, nullable=True)
    invention = Column(Float, nullable=True)
    reaction = Column(Float, nullable=True)


class SystemCostCache(CacheModel):
    __tablename__ = "system_cost_cache"
    solar_system_id = Column(Integer, primary_key=True)
    manufacturing = Column(Float, nullable=True)
    researching_time_efficiency = Column(Float, nullable=True)
    researching_material_efficiency = Column(Float, nullable=True)
    copying = Column(Float, nullable=True)
    invention = Column(Float, nullable=True)
    reaction = Column(Float, nullable=True)


class BlueprintAsset(CacheModel):
    __tablename__ = "blueprint_asset"
    id = Column(Integer, primary_key=True)
    item_id = Column(BigInteger)
    location_flag = Column(Text)
    location_id = Column(BigInteger)
    material_efficiency = Column(Integer)
    quantity = Column(Integer)
    runs = Column(Integer)
    time_efficiency = Column(Integer)
    type_id = Column(Integer)

    owner_id = Column(Integer)
    owner_type = Column(Text)


class BlueprintAssetCache(CacheModel):
    __tablename__ = "blueprint_asset_cache"
    id = Column(Integer, primary_key=True)
    item_id = Column(BigInteger)
    location_flag = Column(Text)
    location_id = Column(BigInteger)
    material_efficiency = Column(Integer)
    quantity = Column(Integer)
    runs = Column(Integer)
    time_efficiency = Column(Integer)
    type_id = Column(Integer)

    owner_id = Column(Integer)
    owner_type = Column(Text)

class MarketPrice(CacheModel):
    __tablename__ = "market_price"
    adjusted_price = Column(Float, nullable=True)
    average_price = Column(Float, nullable=True)
    type_id = Column(Integer, primary_key=True)

class MarketPriceCache(CacheModel):
    __tablename__ = "market_price_cache"
    adjusted_price = Column(Float, nullable=True)
    average_price = Column(Float, nullable=True)
    type_id = Column(Integer, primary_key=True)

class MarketHistory(CacheModel):
    __tablename__ = "market_history"
    id = Column(Integer, primary_key=True)
    region_id = Column(Integer)
    type_id = Column(Integer)
    date = Column(Text)
    average = Column(Integer)
    highest = Column(Integer)
    lowest = Column(Integer)
    order_count = Column(Integer)
    volume = Column(Integer)
    __table_args__ = (
        UniqueConstraint('region_id', 'type_id', 'date', name='market_history_unique_index'),
    )

class RefreshDate(CacheModel):
    __tablename__ = "refresh_date"
    id = Column(Text, primary_key=True)
    date = Column(DateTime)
