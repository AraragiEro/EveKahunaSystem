import os
from peewee import SqliteDatabase
from peewee import Model
from peewee import CharField, IntegerField, TextField, FloatField, ForeignKeyField

from src_v2.core.utils import KahunaException
from src_v2.core.config.config import config

if config['SQLITEDB']['CN_SDEDB']:
    db = SqliteDatabase(config['SQLITEDB']['CN_SDEDB'])
else:
    raise KahunaException("sde db open failed")

class BaseModel(Model):
    class Meta:
        database = db

# 所有的type信息
class InvTypes(BaseModel):
    typeID = IntegerField(primary_key=True)
    groupID = IntegerField(null=True)
    typeName = TextField(null=True)
    description = TextField(null=True)
    mass = FloatField(null=True)
    volume = FloatField(null=True)
    packagedVolume = FloatField(null=True)
    capacity = FloatField(null=True)
    portionSize = IntegerField(null=True)
    factionID = IntegerField(null=True)
    raceID = IntegerField(null=True)
    basePrice = FloatField(null=True)
    published = IntegerField(null=True)
    marketGroupID = IntegerField(null=True)
    graphicID = IntegerField(null=True)
    radius = FloatField(null=True)
    iconID = IntegerField(null=True)
    soundID = IntegerField(null=True)
    sofFactionName = TextField(null=True)
    sofMaterialSetID = IntegerField(null=True)
    metaGroupID = IntegerField(null=True)
    variationparentTypeID = IntegerField(null=True)

    class Meta:
        table_name = 'invTypes'

# 蓝图原料信息
class IndustryActivityMaterials(BaseModel):
    blueprintTypeID = IntegerField()    # 蓝图id
    activityID = IntegerField()         # 活动类型id
    materialTypeID = IntegerField()     # 原料id
    quantity = IntegerField()           # 原料数量
    class Meta:
        table_name = 'industryActivityMaterials'

# 蓝图产品信息
class IndustryActivityProducts(BaseModel):
    blueprintTypeID = IntegerField()    # 蓝图id
    activityID = IntegerField()         # 活动类型id
    productTypeID = IntegerField()     # 产品id
    quantity = IntegerField()           # 产品数量
    probability = FloatField()          # 概率

    class Meta:
        table_name = 'industryActivityProducts'


# 蓝图活动信息
class IndustryActivities(BaseModel):
    blueprintTypeID = IntegerField()    # 蓝图id
    activityID = IntegerField()         # 活动类型id
    time = IntegerField()               # 时间消耗

    class Meta:
        table_name = 'industryActivities'
        indexes = (
            (('blueprintTypeID', 'activityID'), True),  # 唯一索引
            (('activityID',), False)  # 普通索引
        )

class IndustryBlueprints(BaseModel):
    blueprintTypeID = IntegerField(primary_key=True)  # 主键
    maxProductionLimit = IntegerField(null=True)  # 可为空的整数字段

    class Meta:
        table_name = 'industryBlueprints'  # 指定表名

# 元组id信息
class MetaGroups(BaseModel):
    metaGroupID = IntegerField(primary_key=True)
    descriptionID = TextField(null=True)
    iconID = IntegerField(null=True)
    iconSuffix = TextField(null=True)
    nameID = TextField(null=True)

    class Meta:
        table_name = 'metaGroups'

# 组id对应
class InvGroups(BaseModel):
    groupID = IntegerField(primary_key=True)
    categoryID = IntegerField(null=True)
    groupName = TextField(null=True)
    iconID = IntegerField(null=True)
    useBasePrice = IntegerField(null=True)
    anchored = IntegerField(null=True)
    anchorable = IntegerField(null=True)
    fittableNonSingleton = IntegerField(null=True)
    published = IntegerField(null=True)

    class Meta:
        table_name = 'invGroups'

# 属性id对应
class InvCategories(BaseModel):
    categoryID = IntegerField(primary_key=True)
    categoryName = TextField(null=True)
    published = IntegerField(null=True)
    iconID = IntegerField(null=True)

    class Meta:
        table_name = 'invCategories'

class MarketGroups(BaseModel):
    marketGroupID = IntegerField(primary_key=True)
    descriptionID = CharField(max_length=300, null=True)
    hasTypes = IntegerField(null=True)
    iconID = IntegerField(null=True)
    nameID = CharField(max_length=100, null=True)
    parentGroupID = IntegerField()

    class Meta:
        # Replace with the name of your database
        db_table = 'marketGroups'  # The name of the table in the database
        indexes = (
            # CREATE INDEX IDX_marketGroups_MGID ON marketGroups (marketGroupID)
            (('marketGroupID',), False),
        )


class MapSolarSystems(BaseModel):
    solarSystemID = IntegerField(primary_key=True)
    solarSystemName = CharField(max_length=100, null=True)
    regionID = IntegerField(null=True)
    constellationID = IntegerField(null=True)
    x = FloatField(null=True)
    y = FloatField(null=True)
    z = FloatField(null=True)
    x_Min = FloatField(null=True)
    x_Max = FloatField(null=True)
    y_Min = FloatField(null=True)
    y_Max = FloatField(null=True)
    z_Min = FloatField(null=True)
    z_Max = FloatField(null=True)
    luminosity = FloatField(null=True)
    border = IntegerField(null=True)
    corridor = IntegerField(null=True)
    fringe = IntegerField(null=True)
    hub = IntegerField(null=True)
    international = IntegerField(null=True)
    regional = IntegerField(null=True)
    security = FloatField(null=True)
    factionID = IntegerField(null=True)
    radius = FloatField(null=True)
    sunTypeID = IntegerField(null=True)
    securityClass = CharField(max_length=2, null=True)
    solarSystemNameID = IntegerField(null=True)
    visualEffect = CharField(max_length=50, null=True)
    descriptionID = IntegerField(null=True)
    class Meta:
        table_name = 'mapSolarSystems'

class MapRegions(BaseModel):
    regionID = IntegerField(primary_key=True)
    regionName = CharField(max_length=100, null=True)
    x = FloatField(null=True)
    y = FloatField(null=True)
    z = FloatField(null=True)
    x_Min = FloatField(null=True)
    x_Max = FloatField(null=True)
    y_Min = FloatField(null=True)
    y_Max = FloatField(null=True)
    z_Min = FloatField(null=True)
    z_Max = FloatField(null=True)
    factionID = IntegerField(null=True)
    nameID = IntegerField(null=True)
    descriptionID = IntegerField(null=True)
    class Meta:
        table_name = 'mapRegions'

db.connect()
