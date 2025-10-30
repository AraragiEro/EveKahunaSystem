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
    ARRAY
)
from sqlalchemy.ext.declarative import declarative_base

from .connect_manager import PostgreModel
__all__ = []

class User(PostgreModel):
    __tablename__ = 'user'
    user_name = Column(Text, primary_key=True)
    create_date = Column(DateTime)
    password_hash = Column(Text)
    user_role = Column(Text)
    user_permission = Column(ARRAY(Text))
__all__.append(User)

class UserData(PostgreModel):
    __tablename__ = 'user_data'
    user_name = Column(Text, ForeignKey("user.user_name"), primary_key=True)
    user_qq = Column(Integer, index=True)
    main_character_id = Column(Integer, index=True)
__all__.append(UserData)

class VipStatus(PostgreModel):
    __tablename__ = 'vip_status'
    user_name = Column(Text, ForeignKey("user.user_name"), primary_key=True)
    user_qq = Column(Integer, primary_key=True)
    vip_level = Column(Integer)
    vip_end_date = Column(DateTime)
__all__.append(VipStatus)

class InvitCode(PostgreModel):
    __tablename__ = 'invite_code'
    invite_code = Column(Text, primary_key=True)
    user_name = Column(Text, ForeignKey("user.user_name"))
    create_date = Column(DateTime)
    used_date = Column(DateTime)
__all__.append(InvitCode)

class EveAuthedCharacter(PostgreModel):
    __tablename__ = 'character'
    character_id = Column(Integer, primary_key=True)
    character_name = Column(Text)
    QQ = Column(Integer)
    create_date = Column(DateTime)
    token = Column(Text)
    refresh_token = Column(Text)
    expires_date = Column(DateTime)
    corp_id = Column(Integer)
    director = Column(Boolean)
__all__.append(EveAuthedCharacter)

class EveAliasCharacter(PostgreModel):
    __tablename__ = 'alias_character'
    alias_character_id = Column(Integer, primary_key=True)
    main_character_id = Column(Integer, nullable=False, index=True)
    character_name = Column(Text)
__all__.append(EveAliasCharacter)

class IndustryPlan(PostgreModel):
    __tablename__ = 'industry_plan'
    id = Column(Integer, primary_key=True)
__all__.append(IndustryPlan)

class IndustryPlanProdution(PostgreModel):
    __tablename__ = 'industry_plan_item'
    id = Column(Integer, primary_key=True)
__all__.append(IndustryPlanProdution)

class IndustryPlanMatcher(PostgreModel):
    __tablename__ = 'industry_plan_matcher'
    id = Column(Integer, primary_key=True)
__all__.append(IndustryPlanMatcher)
