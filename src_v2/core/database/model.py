from sqlalchemy import (
    ARRAY,
    UUID,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base

from .connect_manager import PostgreModel

all_model = []

class User(PostgreModel):
    __tablename__ = 'user'
    user_name = Column(Text, primary_key=True)
    create_date = Column(DateTime)
    password_hash = Column(Text)
all_model.append(User)

class UserData(PostgreModel):
    __tablename__ = 'user_data'
    user_name = Column(Text, ForeignKey("user.user_name"), primary_key=True)
    user_qq = Column(Integer, index=True)
    main_character_id = Column(Integer, index=True)
all_model.append(UserData)

class InvitCode(PostgreModel):
    __tablename__ = 'invite_code'
    invite_code = Column(Text, primary_key=True)
    creator_user_name = Column(Text)
    create_date = Column(DateTime)
    used_count_max = Column(Integer)
    used_count_current = Column(Integer, default=0, server_default='0')
all_model.append(InvitCode)

class VipState(PostgreModel):
    __tablename__ = 'vip_state'
    user_name = Column(Text, ForeignKey("user.user_name"), primary_key=True)
    vip_level = Column(Text)
    vip_end_date = Column(DateTime)
all_model.append(VipState)

class InviteCodeUsedHistory(PostgreModel):
    __tablename__ = 'invite_code_used_history'
    id = Column(Integer, primary_key=True)
    invite_code = Column(Text, ForeignKey("invite_code.invite_code"))
    used_user_name = Column(Text)
    used_date = Column(DateTime)
all_model.append(InviteCodeUsedHistory)

class Roles(PostgreModel):
    __tablename__ = 'roles'
    role_name = Column(Text, primary_key=True)
    role_description = Column(Text)
all_model.append(Roles)

class Permissions(PostgreModel):
    __tablename__ = 'permissions'
    permission_name = Column(Text, primary_key=True)
    permission_description = Column(Text)
all_model.append(Permissions)

class UserRoles(PostgreModel):
    __tablename__ = 'user_roles'
    id = Column(Integer, primary_key=True)
    user_name = Column(Text, ForeignKey("user.user_name"), index=True)
    role_name = Column(Text, ForeignKey("roles.role_name"))
all_model.append(UserRoles)

class RolePermissions(PostgreModel):
    __tablename__ = 'role_permissions'
    id = Column(Integer, primary_key=True)
    role_name = Column(Text, ForeignKey("roles.role_name"), index=True)
    permission_name = Column(Text, ForeignKey("permissions.permission_name"))
all_model.append(RolePermissions)

class UserPermissions(PostgreModel):
    __tablename__ = 'user_permissions'
    id = Column(Integer, primary_key=True)
    user_name = Column(Text, ForeignKey("user.user_name"), index=True)
    permission_name = Column(Text, ForeignKey("permissions.permission_name"))
all_model.append(UserPermissions)

class RoleHierarchy(PostgreModel):
    __tablename__ = 'role_hierarchy'
    id = Column(Integer, primary_key=True)
    parent_role_name = Column(Text, ForeignKey("roles.role_name"), index=True)
    child_role_name = Column(Text, ForeignKey("roles.role_name"), index=True)
all_model.append(RoleHierarchy)

class EveAuthedCharacter(PostgreModel):
    __tablename__ = 'eve_authed_character'
    character_id = Column(Integer, primary_key=True)
    owner_user_name = Column(Text)
    character_name = Column(Text, index=True)
    birthday = Column(DateTime)
    access_token = Column(Text)
    refresh_token = Column(Text)
    expires_time = Column(DateTime)
    corporation_id = Column(Integer)
    director = Column(Boolean)
all_model.append(EveAuthedCharacter)

class EveAliasCharacter(PostgreModel):
    __tablename__ = 'eve_alias_character'
    alias_character_id = Column(Integer, primary_key=True)
    main_character_id = Column(Integer, index=True)
    character_name = Column(Text)
    enabled = Column(Boolean)
all_model.append(EveAliasCharacter)

class EvePublicCharacterInfo(PostgreModel):
    __tablename__ = 'eve_public_character_info'
    character_id = Column(Integer, primary_key=True)
    alliance_id = Column(Integer)
    birthday = Column(DateTime)
    bloodline_id = Column(Integer)
    corporation_id = Column(Integer)
    description = Column(Text)
    faction_id = Column(Integer)
    gender = Column(Text)
    name = Column(Text)
    race_id = Column(Integer)
    security_status = Column(Float)
    title = Column(Text)
all_model.append(EvePublicCharacterInfo)

class EveCorporation(PostgreModel):
    __tablename__ = 'eve_corporation'
    corporation_id = Column(Integer, primary_key=True)
    alliance_id = Column(Integer)
    ceo_id = Column(Integer)
    creator_id = Column(Integer)
    date_founded = Column(DateTime)
    description = Column(Text)
    faction_id = Column(Integer)
    home_station_id = Column(Integer)
    member_count = Column(Integer)
    name = Column(Text)
    shares = Column(Integer)
    tax_rate = Column(Float)
    ticker = Column(Text)
    url = Column(Text)
    war_eligible = Column(Boolean)

    corporation_icon = Column(Text)
all_model.append(EveCorporation)

# 资产拉取任务
class EveAssetPullMission(PostgreModel):
    __tablename__ = 'eve_asset_pull_mission'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text)
    access_character_id = Column(Integer)
    asset_owner_type = Column(Text)
    asset_owner_id = Column(Integer)
    active = Column(Boolean)
    last_pull_time = Column(DateTime)
all_model.append(EveAssetPullMission)

# 工业资产容器权限
class EveIndustryAssetContainerPermission(PostgreModel):
    __tablename__ = 'eve_industry_asset_container_permission'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    asset_owner_id = Column(BigInteger)
    asset_container_id = Column(BigInteger, index=True)
    structure_id = Column(BigInteger)
    system_id = Column(Integer)
    tag = Column(Text)
all_model.append(EveIndustryAssetContainerPermission)

# 资产视图
class EveAssetView(PostgreModel):
    __tablename__ = 'eve_asset_view'
    sid = Column(Text, primary_key=True)
    user_name = Column(Text, index=True)
    asset_owner_id = Column(BigInteger)  # 废弃，保留但不再使用
    asset_container_id = Column(BigInteger, index=True)  # 废弃，保留但不再使用
    asset_container_id_list = Column(ARRAY(JSONB))  # 新字段，存储 {container_id, owner_id} 组合
    structure_id = Column(BigInteger)
    system_id = Column(Integer)
    tag = Column(Text)
    public = Column(Boolean, default=False)
    view_type = Column(Text, default='default')
    config = Column(JSONB)
    filter = Column(JSONB)
all_model.append(EveAssetView)

# 工业计划
class EveIndustryPlan(PostgreModel):
    __tablename__ = 'eve_industry_plan'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text)
    plan_name = Column(Text)
    settings = Column(JSONB)
all_model.append(EveIndustryPlan)

class EveIndustryPlanProduct(PostgreModel):
    __tablename__ = 'eve_industry_plan_product'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    plan_name = Column(Text, index=True)
    index_id = Column(Integer, index=True)
    product_type_id = Column(Integer, index=True)
    quantity = Column(Integer)
all_model.append(EveIndustryPlanProduct)

"""
planproductdata重构
product_data数据结构：
[
    {
        "type": str, # "group" | "product"
        # product属性
        "type_id": int, # product_type_id
        "quantity": int, # product_quantity
        # group属性
        "name": str, # group_name
        "products": [
            {
                ... # product的属性
            }
        ]
    }
]
"""
class EveIndustryPlanProductJSONB(PostgreModel):
    __tablename__ = 'eve_industry_plan_product_jsonb'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    plan_name = Column(Text, index=True)
    product_data = Column(JSONB)
all_model.append(EveIndustryPlanProductJSONB)

# 工业计划配置流 配置库
class EveIndustryPlanConfigFlowConfig(PostgreModel):
    __tablename__ = 'eve_industry_plan_config_flow_config'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    config_type = Column(Text)
    config_value = Column(JSONB)
    config_tag = Column(Text)
all_model.append(EveIndustryPlanConfigFlowConfig)

class EveIndustryPlanConfigFlow(PostgreModel):
    __tablename__ = 'eve_industry_plan_config_flow'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    plan_name = Column(Text, index=True)
    config_list = Column(ARRAY(Integer))
all_model.append(EveIndustryPlanConfigFlow)

class EveIndustrryPlanConfigFlowPreset(PostgreModel):
    __tablename__ = 'eve_industry_plan_config_flow_preset'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    preset_name = Column(Text)
    config_list = Column(ARRAY(Integer))
all_model.append(EveIndustrryPlanConfigFlowPreset)

class EveIndustryPlanConfigFlowPresupposition(PostgreModel):
    __tablename__ = 'eve_industry_plan_config_flow_presupposition'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    presupposition_name = Column(Text)
    config_list = Column(ARRAY(Integer))
all_model.append(EveIndustryPlanConfigFlowPresupposition)

class EveIndustryCalculateHistory(PostgreModel):
    __tablename__ = 'eve_industry_calculate_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    plan_name = Column(Text, index=True)
    product_count = Column(Integer)
    calculate_start_time = Column(DateTime, index=True)
    calculate_time = Column(DateTime, index=True)
    calculate_result = Column(JSONB)
all_model.append(EveIndustryCalculateHistory)

# class EveIndustryPlanSetting(PostgreModel):
#     __tablename__ = 'eve_industry_plan_setting'
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     user_name = Column(Text, ForeignKey("user.user_name"), index=True)
#     plan_name = Column(Text, ForeignKey("eve_industry_plan.plan_name"), index=True)
#     settings = Column(JSONB)
# all_model.append(EveIndustryPlanSetting)

# 企业版自选市场
class EnterpriseMarket(PostgreModel):
    __tablename__ = 'enterprise_market'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, ForeignKey("user.user_name"), index=True)
    tag = Column(Text)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    product_type_ids = Column(ARRAY(Integer))
    container_id_list = Column(ARRAY(BigInteger))  # 废弃，保留但不再使用
    asset_pull_permission = Column(ARRAY(JSONB))  # 新字段，存储 {container_id, owner_id} 组合
all_model.append(EnterpriseMarket)


class MessageCard(PostgreModel):
    """
    留言卡片表
    """
    __tablename__ = 'message_card'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 创建人用户名（关联 user.user_name）
    author_user_name = Column(Text, ForeignKey("user.user_name"), index=True, nullable=False)
    # 类型：bug / feat / chat
    type = Column(Text, nullable=False, index=True)
    # 状态：created / in_progress / closed
    status = Column(Text, nullable=False, index=True)
    # 标题与正文
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    # 创建与更新时间
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)
    # 最近回复时间与最近回复人（可为空）
    last_reply_at = Column(DateTime, index=True)
    last_reply_user_name = Column(Text, ForeignKey("user.user_name"))
    # 关闭信息
    auto_closed = Column(Boolean, default=False, server_default='false')
    closed_at = Column(DateTime)
    closed_by = Column(Text, ForeignKey("user.user_name"))
    close_reason = Column(Text)
    # 隐藏状态（管理员可隐藏，只有发布者可见）
    is_hidden = Column(Boolean, default=False, server_default='false')


all_model.append(MessageCard)


class MessageReply(PostgreModel):
    """
    留言回复表
    """
    __tablename__ = 'message_reply'

    id = Column(Integer, primary_key=True, autoincrement=True)
    card_id = Column(Integer, ForeignKey("message_card.id"), nullable=False, index=True)
    author_user_name = Column(Text, ForeignKey("user.user_name"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False, server_default='false')
    # 隐藏状态（管理员可隐藏，只有发布者可见）
    is_hidden = Column(Boolean, default=False, server_default='false')


all_model.append(MessageReply)


class EveMarketRegionHistoryStatistic(PostgreModel):
    __tablename__ = 'eve_market_region_history_statistic'
    id = Column(Integer, primary_key=True, autoincrement=True)
    type_id = Column(BigInteger, nullable=False, index=True)
    region_id = Column(BigInteger, nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    average = Column(Float, nullable=False)
    highest = Column(Float, nullable=False)
    lowest = Column(Float, nullable=False)
    order_count = Column(BigInteger, nullable=False)
    volume = Column(BigInteger, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('type_id', 'region_id', 'date', name='eve_market_region_history_statistic_unique'),
    )
all_model.append(EveMarketRegionHistoryStatistic)

class EveMarketRegionOrders(PostgreModel):
    __tablename__ = 'eve_market_region_orders'
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, nullable=False, index=True)
    type_id = Column(BigInteger, nullable=False, index=True)
    region_id = Column(BigInteger, index=True)
    system_id = Column(BigInteger, index=True)
    location_id = Column(BigInteger, index=True)
    price = Column(Float, nullable=False)
    volume_total = Column(BigInteger, nullable=False)
    volume_remain = Column(BigInteger, nullable=False)
    min_volume = Column(BigInteger, nullable=False)
    is_buy_order = Column(Boolean, nullable=False)
    duration = Column(Integer, nullable=False)
    issued = Column(DateTime, nullable=False)
    range = Column(Text)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
all_model.append(EveMarketRegionOrders)