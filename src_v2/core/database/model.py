from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Float,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    BigInteger,
    UUID,
    ARRAY,
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
    user_name = Column(Text, ForeignKey("user.user_name"))
    create_date = Column(DateTime)
    used_date = Column(DateTime)
all_model.append(InvitCode)

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
    owner_user_name = Column(Text, ForeignKey("user.user_name"))
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
    main_character_id = Column(Integer, ForeignKey("eve_authed_character.character_id"), index=True)
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

class EveAssetPullMission(PostgreModel):
    __tablename__ = 'eve_asset_pull_mission'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, ForeignKey("user.user_name"))
    access_character_id = Column(Integer, ForeignKey("eve_authed_character.character_id"))
    asset_owner_type = Column(Text)
    asset_owner_id = Column(Integer)
    active = Column(Boolean)
    last_pull_time = Column(DateTime)
all_model.append(EveAssetPullMission)

class EveAssetNodeAccess(PostgreModel):
    __tablename__ = 'eve_asset_node_access'
    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_owner_type = Column(Text)
    asset_owner_id = Column(Integer)
all_model.append(EveAssetNodeAccess)

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

class EveIndustryPlanConfigFlow(PostgreModel):
    __tablename__ = 'eve_industry_plan_config_flow'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(Text, index=True)
    plan_name = Column(Text, index=True)
    
all_model.append(EveIndustryPlanConfigFlow)

# class EveIndustryPlanSetting(PostgreModel):
#     __tablename__ = 'eve_industry_plan_setting'
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     user_name = Column(Text, ForeignKey("user.user_name"), index=True)
#     plan_name = Column(Text, ForeignKey("eve_industry_plan.plan_name"), index=True)
#     settings = Column(JSONB)
# all_model.append(EveIndustryPlanSetting)