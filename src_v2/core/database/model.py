from datetime import datetime

from sqlalchemy import (
    ARRAY,
    UUID,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
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
    __tablename__ = "user"
    user_name = Column(Text, primary_key=True)
    create_date = Column(DateTime)
    password_hash = Column(Text)


all_model.append(User)


class UserData(PostgreModel):
    __tablename__ = "user_data"
    user_name = Column(Text, ForeignKey("user.user_name"), primary_key=True)
    user_qq = Column(Integer, index=True)
    main_character_id = Column(Integer, index=True)
    setting = Column(JSONB, default={}, server_default="{}")


all_model.append(UserData)


class UserQQBinding(PostgreModel):
    __tablename__ = "user_qq_binding"
    user_name = Column(Text, ForeignKey("user.user_name"), primary_key=True)
    user_qq = Column(BigInteger, unique=True, index=True)
    bind_time = Column(DateTime)


all_model.append(UserQQBinding)


class InvitCode(PostgreModel):
    __tablename__ = "invite_code"
    invite_code = Column(Text, primary_key=True)
    creator_user_name = Column(Text)
    create_date = Column(DateTime)
    used_count_max = Column(Integer)
    used_count_current = Column(Integer, default=0, server_default="0")


all_model.append(InvitCode)


class VipState(PostgreModel):
    __tablename__ = "vip_state"
    user_name = Column(Text, ForeignKey("user.user_name"), primary_key=True)
    vip_level = Column(Text)
    vip_end_date = Column(DateTime)


all_model.append(VipState)


class InviteCodeUsedHistory(PostgreModel):
    __tablename__ = "invite_code_used_history"
    id = Column(Integer, primary_key=True)
    invite_code = Column(Text, ForeignKey("invite_code.invite_code"))
    used_user_name = Column(Text)
    used_date = Column(DateTime)


all_model.append(InviteCodeUsedHistory)


class Roles(PostgreModel):
    __tablename__ = "roles"
    role_name = Column(Text, primary_key=True)
    role_description = Column(Text)


all_model.append(Roles)


class Permissions(PostgreModel):
    __tablename__ = "permissions"
    permission_name = Column(Text, primary_key=True)
    permission_description = Column(Text)


all_model.append(Permissions)


class UserRoles(PostgreModel):
    __tablename__ = "user_roles"
    id = Column(Integer, primary_key=True)
    user_name = Column(Text, ForeignKey("user.user_name"), index=True)
    role_name = Column(Text, ForeignKey("roles.role_name"))


all_model.append(UserRoles)


class RolePermissions(PostgreModel):
    __tablename__ = "role_permissions"
    id = Column(Integer, primary_key=True)
    role_name = Column(Text, ForeignKey("roles.role_name"), index=True)
    permission_name = Column(Text, ForeignKey("permissions.permission_name"))


all_model.append(RolePermissions)


class UserPermissions(PostgreModel):
    __tablename__ = "user_permissions"
    id = Column(Integer, primary_key=True)
    user_name = Column(Text, ForeignKey("user.user_name"), index=True)
    permission_name = Column(Text, ForeignKey("permissions.permission_name"))


all_model.append(UserPermissions)


class RoleHierarchy(PostgreModel):
    __tablename__ = "role_hierarchy"
    id = Column(Integer, primary_key=True)
    parent_role_name = Column(Text, ForeignKey("roles.role_name"), index=True)
    child_role_name = Column(Text, ForeignKey("roles.role_name"), index=True)


all_model.append(RoleHierarchy)


class EveAuthedCharacter(PostgreModel):
    __tablename__ = "eve_authed_character"
    character_id = Column(Integer, primary_key=True)
    owner_user_name = Column(Text)
    character_name = Column(Text, index=True)
    birthday = Column(DateTime)
    access_token = Column(Text)
    refresh_token = Column(Text)
    expires_time = Column(DateTime)
    corporation_id = Column(Integer)
    director = Column(Boolean)
    refresh_failure_count = Column(Integer, default=0)  # token 刷新连续失败次数
    last_refresh_error = Column(Text, nullable=True)     # 最近一次刷新失败的错误信息


all_model.append(EveAuthedCharacter)


class EveAliasCharacter(PostgreModel):
    __tablename__ = "eve_alias_character"
    alias_character_id = Column(Integer, primary_key=True)
    main_character_id = Column(Integer, index=True)
    character_name = Column(Text)
    enabled = Column(Boolean)


all_model.append(EveAliasCharacter)


class EvePublicCharacterInfo(PostgreModel):
    __tablename__ = "eve_public_character_info"
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
    __tablename__ = "eve_corporation"
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
    __tablename__ = "eve_asset_pull_mission"
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
    __tablename__ = "eve_industry_asset_container_permission"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    asset_owner_id = Column(BigInteger)
    asset_container_id = Column(BigInteger, index=True)
    structure_id = Column(BigInteger)
    system_id = Column(Integer)
    location_flag = Column(Text)
    tag = Column(Text)


all_model.append(EveIndustryAssetContainerPermission)

# 资产视图


class EveAssetView(PostgreModel):
    __tablename__ = "eve_asset_view"
    sid = Column(Text, primary_key=True)
    user_name = Column(Text, index=True)
    asset_owner_id = Column(BigInteger)  # 废弃，保留但不再使用
    asset_container_id = Column(BigInteger, index=True)  # 废弃，保留但不再使用
    # 新字段，存储 {container_id, owner_id} 组合
    asset_container_id_list = Column(ARRAY(JSONB))
    structure_id = Column(BigInteger)
    system_id = Column(Integer)
    tag = Column(Text)
    public = Column(Boolean, default=False)
    view_type = Column(Text, default="default")
    config = Column(JSONB)
    filter = Column(JSONB)


all_model.append(EveAssetView)

# 工业计划


class EveIndustryPlan(PostgreModel):
    __tablename__ = "eve_industry_plan"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text)
    plan_name = Column(Text)
    settings = Column(JSONB)

    # ===== 新增字段：工作流分享功能 =====
    public = Column(Boolean, default=False, index=True)  # 公开开关
    share_token = Column(Text, nullable=True, index=True)  # 分享令牌（唯一）
    filter_snapshot = Column(JSONB, default=dict)  # 过滤条件快照
    # ===================

    __table_args__ = (
        UniqueConstraint("share_token", name="uq_plan_share_token"),
        Index("idx_plan_public_user", "public", "user_name"),
    )


all_model.append(EveIndustryPlan)


class EveIndustryPlanProduct(PostgreModel):
    __tablename__ = "eve_industry_plan_product"
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
    __tablename__ = "eve_industry_plan_product_jsonb"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    plan_name = Column(Text, index=True)
    product_data = Column(JSONB)


all_model.append(EveIndustryPlanProductJSONB)

# 工业计划配置流 配置库


class EveIndustryPlanConfigFlowConfig(PostgreModel):
    __tablename__ = "eve_industry_plan_config_flow_config"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    config_type = Column(Text)
    config_value = Column(JSONB)
    config_tag = Column(Text)


all_model.append(EveIndustryPlanConfigFlowConfig)


class EveIndustryPlanConfigFlow(PostgreModel):
    __tablename__ = "eve_industry_plan_config_flow"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    plan_name = Column(Text, index=True)
    config_list = Column(ARRAY(Integer))


all_model.append(EveIndustryPlanConfigFlow)


class EveIndustrryPlanConfigFlowPreset(PostgreModel):
    __tablename__ = "eve_industry_plan_config_flow_preset"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    preset_name = Column(Text)
    config_list = Column(ARRAY(Integer))


all_model.append(EveIndustrryPlanConfigFlowPreset)


class EveIndustryPlanConfigFlowPresupposition(PostgreModel):
    __tablename__ = "eve_industry_plan_config_flow_presupposition"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    presupposition_name = Column(Text)
    config_list = Column(ARRAY(Integer))


all_model.append(EveIndustryPlanConfigFlowPresupposition)


class EveIndustryCalculateHistory(PostgreModel):
    __tablename__ = "eve_industry_calculate_history"
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
    __tablename__ = "enterprise_market"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, ForeignKey("user.user_name"), index=True)
    tag = Column(Text)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    product_type_ids = Column(ARRAY(Integer))
    container_id_list = Column(ARRAY(BigInteger))  # 废弃，保留但不再使用
    # 新字段，存储 {container_id, owner_id} 组合
    asset_pull_permission = Column(ARRAY(JSONB))


all_model.append(EnterpriseMarket)


class MessageCard(PostgreModel):
    """
    留言卡片表
    """

    __tablename__ = "message_card"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 创建人用户名（关联 user.user_name）
    author_user_name = Column(
        Text, ForeignKey("user.user_name"), index=True, nullable=False
    )
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
    auto_closed = Column(Boolean, default=False, server_default="false")
    closed_at = Column(DateTime)
    closed_by = Column(Text, ForeignKey("user.user_name"))
    close_reason = Column(Text)
    # 隐藏状态（管理员可隐藏，只有发布者可见）
    is_hidden = Column(Boolean, default=False, server_default="false")


all_model.append(MessageCard)


class MessageReply(PostgreModel):
    """
    留言回复表
    """

    __tablename__ = "message_reply"

    id = Column(Integer, primary_key=True, autoincrement=True)
    card_id = Column(Integer, ForeignKey("message_card.id"), nullable=False, index=True)
    author_user_name = Column(
        Text, ForeignKey("user.user_name"), nullable=False, index=True
    )
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False, server_default="false")
    # 隐藏状态（管理员可隐藏，只有发布者可见）
    is_hidden = Column(Boolean, default=False, server_default="false")


all_model.append(MessageReply)


class EveMarketRegionHistoryStatistic(PostgreModel):
    __tablename__ = "eve_market_region_history_statistic"
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
        UniqueConstraint(
            "type_id",
            "region_id",
            "date",
            name="eve_market_region_history_statistic_unique",
        ),
    )


all_model.append(EveMarketRegionHistoryStatistic)


class EveMarketRegionOrders(PostgreModel):
    __tablename__ = "eve_market_region_orders"
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

# Overview历史数据


class EveOverviewHistory(PostgreModel):
    __tablename__ = "eve_overview_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, ForeignKey("user.user_name"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    data = Column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_name", "date", name="eve_overview_history_unique"),
    )


all_model.append(EveOverviewHistory)


class EveCharacterOrdersStats(PostgreModel):
    __tablename__ = "eve_character_orders_stats"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, nullable=False, index=True)
    period_type = Column(Text, nullable=False)
    period_start = Column(Date, nullable=False)
    buy_order_count = Column(Integer, default=0)
    sell_order_count = Column(Integer, default=0)
    buy_volume = Column(BigInteger, default=0)
    sell_volume = Column(BigInteger, default=0)
    buy_total_isk = Column(Float, default=0.0)
    sell_total_isk = Column(Float, default=0.0)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_name", "period_type", "period_start", name="uix_orders_stats"),
    )


all_model.append(EveCharacterOrdersStats)


class EveCharacterOrdersStatsDetail(PostgreModel):
    __tablename__ = "eve_character_orders_stats_detail"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, nullable=False, index=True)
    period_type = Column(Text, nullable=False)
    period_start = Column(Date, nullable=False)
    type_id = Column(Integer, nullable=False, index=True)
    is_buy_order = Column(Boolean, nullable=False)
    order_count = Column(Integer, default=0)
    volume = Column(BigInteger, default=0)
    total_isk = Column(Float, default=0.0)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_name", "period_type", "period_start", "type_id", "is_buy_order",
            name="uix_orders_stats_detail",
        ),
    )


all_model.append(EveCharacterOrdersStatsDetail)

# 公司合同


class EveCorporationContract(PostgreModel):
    __tablename__ = "eve_corporation_contract"
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 必需字段
    acceptor_id = Column(BigInteger, nullable=True)
    assignee_id = Column(BigInteger, nullable=True)
    availability = Column(String, nullable=False)
    contract_id = Column(BigInteger, unique=True, nullable=False, index=True)
    date_expired = Column(DateTime, nullable=False)
    date_issued = Column(DateTime, nullable=False)
    for_corporation = Column(Boolean, nullable=False)
    issuer_corporation_id = Column(BigInteger, nullable=False)
    issuer_id = Column(BigInteger, nullable=False, index=True)
    status = Column(String, nullable=False)
    type = Column(String, nullable=False)

    # 可选字段
    buyout = Column(Float, nullable=True)
    collateral = Column(Float, nullable=True)
    date_accepted = Column(DateTime, nullable=True)
    date_completed = Column(DateTime, nullable=True)
    days_to_complete = Column(BigInteger, nullable=True)
    end_location_id = Column(BigInteger, nullable=True)
    price = Column(Float, nullable=True)
    reward = Column(Float, nullable=True)
    start_location_id = Column(BigInteger, nullable=True)
    title = Column(Text, nullable=True)
    volume = Column(Float, nullable=True)

    # 额外字段：合同物品详情
    contract_item = Column(JSONB, nullable=True, default={}, server_default="{}")
    item_typeids = Column(ARRAY(BigInteger), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "contract_id", name="eve_corporation_contract_contract_id_unique"
        ),
    )


all_model.append(EveCorporationContract)

# 企业版市场成本历史缓存


class EnterpriseMarketCostHistory(PostgreModel):
    __tablename__ = "enterprise_market_cost_history"
    type_id = Column(Integer, primary_key=True, index=True)
    history_data = Column(JSONB, nullable=False)


all_model.append(EnterpriseMarketCostHistory)


# ============ 工作流任务接取功能 ============


class EveIndustryPlanTaskClaim(PostgreModel):
    """工作流任务接取记录表"""

    __tablename__ = "eve_industry_plan_task_claim"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 关联信息
    plan_token = Column(Text, index=True, nullable=False)  # 分享链接token
    workflow_item_key = Column(Text, nullable=False)  # 工作流项唯一标识

    # 接取信息
    claimed_by = Column(Text, ForeignKey("user.user_name"), nullable=False)
    claimed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 接取数量（支持部分接取，如接取40线中的20线）
    claimed_quantity = Column(Integer, default=1, nullable=False)

    # 任务状态（claimed: 已接取, completed: 已完成, cancelled: 已取消）
    status = Column(Text, default="claimed")

    # 唯一约束：同一用户对同一工作流项只能有一条接取记录
    __table_args__ = (
        UniqueConstraint(
            "plan_token",
            "workflow_item_key",
            "claimed_by",
            name="uq_task_claim_per_user_item",
        ),
        Index("idx_claim_plan_token", "plan_token"),
        Index("idx_claim_claimed_by", "claimed_by"),
    )


all_model.append(EveIndustryPlanTaskClaim)


# ============ 工作流实施标记功能 ============


class EveIndustryPlanTaskImplementation(PostgreModel):
    """工作流实施标记记录表（云端备份）"""

    __tablename__ = "eve_industry_plan_task_implementation"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 关联信息
    user_name = Column(Text, index=True, nullable=False)
    plan_name = Column(Text, index=True, nullable=False)
    calculation_id = Column(BigInteger, index=True, nullable=False)

    # 工作流项标识
    workflow_item_key = Column(Text, nullable=False)

    # 实施信息
    implemented = Column(Boolean, default=True)
    runs_implemented = Column(Integer, nullable=True)

    # 时间戳（用于冲突解决）
    modified_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    modified_by_client = Column(Text)  # 标识哪个客户端做的修改

    __table_args__ = (
        # 唯一约束：同一计算周期内同一工作流项只能有一条记录
        UniqueConstraint(
            "user_name",
            "plan_name",
            "calculation_id",
            "workflow_item_key",
            name="uq_impl_user_plan_calc_item",
        ),
        Index("idx_impl_modified", "modified_at"),
        Index("idx_impl_user_plan_calc", "user_name", "plan_name", "calculation_id"),
    )


all_model.append(EveIndustryPlanTaskImplementation)


class EveLpValueSnapshot(PostgreModel):
    __tablename__ = "eve_lp_value_snapshot"
    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False, index=True)       # 快照日期
    corporation_id = Column(Integer, nullable=False, index=True)    # 军团ID
    corporation_name = Column(Text, nullable=True)                  # 军团英文名
    corporation_name_zh = Column(Text, nullable=True)               # 军团中文名
    faction_id = Column(Integer, nullable=True)                     # 势力ID
    lp_buy_value = Column(Float, nullable=True)                     # LP收单标准价值 (ISK/LP)
    lp_sell_value = Column(Float, nullable=True)                    # LP出单标准价值 (ISK/LP) — 前5加权
    lp_sell_value_all = Column(Float, nullable=True)                # LP出单价值 — 全部有效物品加权平均
    top_items_json = Column(JSONB, nullable=True)                   # Top-5物品JSON
    total_offers = Column(Integer, default=0)                       # 总兑换项数
    evaluated_offers = Column(Integer, default=0)                   # 有效评估数
    excluded_offers = Column(Integer, default=0)                    # 排除数
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('snapshot_date', 'corporation_id', name='uq_lp_snapshot_date_corp'),
    )


all_model.append(EveLpValueSnapshot)


class EveLpValueSnapshotDetail(PostgreModel):
    __tablename__ = "eve_lp_value_snapshot_detail"
    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, nullable=False, index=True)       # 关联snapshot.id
    corporation_id = Column(Integer, nullable=False, index=True)
    offer_id = Column(Integer, nullable=False)                      # ESI offer_id
    type_id = Column(Integer, nullable=False, index=True)           # 物品typeID
    type_name_en = Column(Text, nullable=True)                      # 物品英文名
    type_name_zh = Column(Text, nullable=True)                      # 物品中文名
    quantity = Column(Integer, nullable=False)                      # 单次兑换数量
    lp_cost = Column(Integer, nullable=False)                       # LP消耗
    isk_cost = Column(BigInteger, nullable=False)                   # ISK消耗
    market_buy_price = Column(Float, nullable=True)                 # Jita max_buy
    market_sell_price = Column(Float, nullable=True)                # Jita min_sell
    daily_volume_30d = Column(Float, nullable=True)                 # 30天日均成交量
    daily_value_30d = Column(Float, nullable=True)                  # 30天日均成交额
    lp_buy_value = Column(Float, nullable=True)                     # LP收单价值
    lp_sell_value = Column(Float, nullable=True)                    # LP出单价值
    is_in_top = Column(Boolean, default=False)                      # 是否入选Top-5
    excluded = Column(Boolean, default=False)                       # 是否被排除
    excluded_reason = Column(Text, nullable=True)                   # 排除原因

    __table_args__ = (
        Index('idx_lp_detail_snapshot_corp', 'snapshot_id', 'corporation_id'),
    )


all_model.append(EveLpValueSnapshotDetail)


class EsiUsageLog(PostgreModel):
    """ESI 请求调用日志表"""

    __tablename__ = "esi_usage_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, index=True, nullable=False)
    endpoint = Column(Text, nullable=False)
    pool_name = Column(Text, nullable=True)
    character_id = Column(Integer, nullable=True, default=0)
    status_code = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)


all_model.append(EsiUsageLog)


# ============ 系数监控 - 用户关注星系 ============


class UserWatchedSystem(PostgreModel):
    """用户关注的星系列表（系数监控用）"""

    __tablename__ = "user_watched_system"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, nullable=False, index=True)
    system_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_name", "system_id", name="uq_user_watched_system"),
    )


all_model.append(UserWatchedSystem)
