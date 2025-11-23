import os
from peewee import SqliteDatabase
from peewee import Model
from peewee import CharField, IntegerField, TextField, FloatField, ForeignKeyField

from src_v2.core.utils import KahunaException

from peewee import SqliteDatabase

from src_v2.core.config.config import config

if config['SQLITEDB']['SDEDB']:
    db = SqliteDatabase(config['SQLITEDB']['SDEDB'])
else:
    raise KahunaException("sde db open failed")

class BaseModel(Model):
    class Meta:
        database = db

"""
{
    "_key": 0,
    "groupID": 0,
    "mass": 1.0,
    "name": {
        "en": "#System",
        "zh": "#星系"
    },
    "portionSize": 1,
    "published": false
}
"""
# 所有的type信息
class InvTypes(BaseModel):
    typeID = IntegerField(primary_key=True) # types.jsonl._key
    groupID = IntegerField(null=True)       # types.jsonl.groupID
    typeName = TextField(null=True)         # types.jsonl.name.{en,zh}
    description = TextField(null=True)      # types.jsonl.description.{en,zh}
    mass = FloatField(null=True)            # types.jsonl.mass
    volume = FloatField(null=True)          # types.jsonl.volume
    # 如果存在于GROUP_ID_PACKAGED_VOLUME字典，则取值
    # 如果存在于TYPE_ID_PACKAGE_VOLUME，则取值
    # 如果存在volume，则等于volume
    packagedVolume = FloatField(null=True)  # 需要计算
    capacity = FloatField(null=True)        # types.jsonl.capacity
    portionSize = IntegerField(null=True)   # types.jsonl.portionSize
    factionID = IntegerField(null=True)     # types.jsonl.factionID
    raceID = IntegerField(null=True)        # types.jsonl.raceID
    basePrice = FloatField(null=True)       # types.jsonl.basePrice
    published = IntegerField(null=True)     # types.jsonl.published
    marketGroupID = IntegerField(null=True) # types.jsonl.marketGroupID
    graphicID = IntegerField(null=True)     # types.jsonl.graphicID
    radius = FloatField(null=True)          # types.jsonl.radius
    iconID = IntegerField(null=True)
    soundID = IntegerField(null=True)
    sofFactionName = TextField(null=True)
    sofMaterialSetID = IntegerField(null=True)
    metaGroupID = IntegerField(null=True)   # types.jsonl.metaGroupID
    variationparentTypeID = IntegerField(null=True)

    class Meta:
        table_name = 'invTypes'


class IndustryBlueprints(BaseModel):
    blueprintTypeID = IntegerField(primary_key=True)  # blueprints.jsonl.blueprintTypeID
    maxProductionLimit = IntegerField(null=True)  # blueprints.jsonl.maxProductionLimit

    class Meta:
        table_name = 'industryBlueprints'  # 指定表名


# 蓝图活动信息
class IndustryActivities(BaseModel):
    blueprintTypeID = IntegerField()    # blueprints.jsonl.blueprintTypeID
    # 根据blueprints.jsonl.activities中的key，映射到ACTIVITY_ID_MAP中
    # 如果不存在则跳过，不插入数据库
    activityID = IntegerField()
    # 如果activities存在time
    # 根据blueprints.jsonl.activities中对应value的time，插入时间消耗
    time = IntegerField()               # 时间消耗

    class Meta:
        table_name = 'industryActivities'
        indexes = (
            (('blueprintTypeID', 'activityID'), True),  # 唯一索引
            (('activityID',), False)  # 普通索引
        )


# 蓝图原料信息
class IndustryActivityMaterials(BaseModel):
    blueprintTypeID = IntegerField()    # blueprints.jsonl.blueprintTypeID
    # 根据blueprints.jsonl.activities中的key，映射到ACTIVITY_ID_MAP中
    activityID = IntegerField()         # 活动类型id
    # 如果activities存在materials
    # 根据blueprints.jsonl.activities中对应value的materials的list中每个成员的typeID，插入原料id
    materialTypeID = IntegerField()     # 原料id
    # 如果activities存在materials
    # 根据blueprints.jsonl.activities中对应value的materials的list中每个成员的quantity，插入原料数量
    quantity = IntegerField()           # 原料数量
    class Meta:
        table_name = 'industryActivityMaterials'

# 蓝图产品信息
class IndustryActivityProducts(BaseModel):
    blueprintTypeID = IntegerField()    # blueprints.jsonl.blueprintTypeID
    # 根据blueprints.jsonl.activities中的key，映射到ACTIVITY_ID_MAP中
    # 如果不存在则跳过，不插入数据库
    activityID = IntegerField()         # 活动类型id
    # 如果activities存在products
    # 根据blueprints.jsonl.activities中对应value的products的list中每个成员的typeID，插入产品id
    productTypeID = IntegerField()     # 产品id
    # 如果activities存在products
    # 根据blueprints.jsonl.activities中对应value的products的list中每个成员的quantity，插入产品数量
    quantity = IntegerField()           # 产品数量
    # 如果activities存在products
    # 根据blueprints.jsonl.activities中对应value的products的list中每个成员的probability，插入概率
    probability = FloatField()          # 概率

    class Meta:
        table_name = 'industryActivityProducts'

# 元组id信息
class MetaGroups(BaseModel):
    metaGroupID = IntegerField(primary_key=True)    # metaGroups.jsonl._key
    descriptionID = TextField(null=True)            # metaGroups.jsonl.description{en,zh}
    iconID = IntegerField(null=True)                # metaGroups.jsonl.iconID
    iconSuffix = TextField(null=True)               # metaGroups.jsonl.iconSuffix
    nameID = TextField(null=True)                   # metaGroups.jsonl.name{en,zh}

    class Meta:
        table_name = 'metaGroups'

# 组id对应
class InvGroups(BaseModel):
    groupID = IntegerField(primary_key=True)        # groups.jsonl._key
    categoryID = IntegerField(null=True)        # groups.jsonl.categoryID
    groupName = TextField(null=True)            # groups.jsonl.name{en,zh}
    iconID = IntegerField(null=True)            # groups.jsonl.iconID
    useBasePrice = IntegerField(null=True)      # groups.jsonl.useBasePrice
    anchored = IntegerField(null=True)          # groups.jsonl.anchored
    anchorable = IntegerField(null=True)        # groups.jsonl.anchorable
    fittableNonSingleton = IntegerField(null=True) # groups.jsonl.fittableNonSingleton
    published = IntegerField(null=True)         # groups.jsonl.published

    class Meta:
        table_name = 'invGroups'

# 属性id对应
class InvCategories(BaseModel):
    categoryID = IntegerField(primary_key=True)        # categories.jsonl._key
    categoryName = TextField(null=True)                # categories.jsonl.name{en,zh}
    published = IntegerField(null=True)                # categories.jsonl.published
    iconID = IntegerField(null=True)                   # categories.jsonl.iconID

    class Meta:
        table_name = 'invCategories'

class MarketGroups(BaseModel):
    marketGroupID = IntegerField(primary_key=True)          # marketGroups.jsonl._key
    descriptionID = CharField(max_length=300, null=True) # marketGroups.jsonl.description{en,zh}
    hasTypes = IntegerField(null=True)                  # marketGroups.jsonl.hasTypes
    iconID = IntegerField(null=True)                    # marketGroups.jsonl.iconID
    nameID = CharField(max_length=100, null=True)       # marketGroups.jsonl.name{en,zh}
    parentGroupID = IntegerField()                      # marketGroups.jsonl.parentGroupID

    class Meta:
        # Replace with the name of your database
        db_table = 'marketGroups'  # The name of the table in the database
        indexes = (
            # CREATE INDEX IDX_marketGroups_MGID ON marketGroups (marketGroupID)
            (('marketGroupID',), False),
        )

class MapSolarSystems(BaseModel):
    solarSystemID = IntegerField(primary_key=True)  # mapSolarSystems.jsonl._key
    solarSystemName = CharField(max_length=100, null=True)  # mapSolarSystems.jsonl.name.{en,zh}
    regionID = IntegerField(null=True)  # mapSolarSystems.jsonl.regionID
    constellationID = IntegerField(null=True)  # mapSolarSystems.jsonl.constellationID
    x = FloatField(null=True)  # mapSolarSystems.jsonl.position.x
    y = FloatField(null=True)  # mapSolarSystems.jsonl.position.y
    z = FloatField(null=True)  # mapSolarSystems.jsonl.position.z
    x_Min = FloatField(null=True)
    x_Max = FloatField(null=True)
    y_Min = FloatField(null=True)
    y_Max = FloatField(null=True)
    z_Min = FloatField(null=True)
    z_Max = FloatField(null=True)
    luminosity = FloatField(null=True)  # mapSolarSystems.jsonl.luminosity
    border = IntegerField(null=True)  # mapSolarSystems.jsonl.border (布尔值转换为整数)
    corridor = IntegerField(null=True)
    fringe = IntegerField(null=True)
    hub = IntegerField(null=True)  # mapSolarSystems.jsonl.hub (布尔值转换为整数)
    international = IntegerField(null=True)  # mapSolarSystems.jsonl.international (布尔值转换为整数)
    regional = IntegerField(null=True)  # mapSolarSystems.jsonl.regional (布尔值转换为整数)
    security = FloatField(null=True)  # mapSolarSystems.jsonl.securityStatus
    factionID = IntegerField(null=True)
    radius = FloatField(null=True)  # mapSolarSystems.jsonl.radius
    sunTypeID = IntegerField(null=True)  # mapSolarSystems.jsonl.starID
    securityClass = CharField(max_length=2, null=True)  # mapSolarSystems.jsonl.securityClass
    solarSystemNameID = IntegerField(null=True)
    visualEffect = CharField(max_length=50, null=True)
    descriptionID = IntegerField(null=True)
    class Meta:
        table_name = 'mapSolarSystems'

class MapRegions(BaseModel):
    regionID = IntegerField(primary_key=True)  # mapRegions.jsonl._key
    regionName = CharField(max_length=100, null=True)  # mapRegions.jsonl.name.{en,zh}
    x = FloatField(null=True)  # mapRegions.jsonl.position.x
    y = FloatField(null=True)  # mapRegions.jsonl.position.y
    z = FloatField(null=True)  # mapRegions.jsonl.position.z
    factionID = IntegerField(null=True)  # mapRegions.jsonl.factionID
    nameID = IntegerField(null=True)  # 从 mapRegions.jsonl.name 提取的ID
    descriptionID = IntegerField(null=True)  # 从 mapRegions.jsonl.description 提取的ID
    class Meta:
        table_name = 'mapRegions'

db.connect()
