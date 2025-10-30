from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Float,
    Boolean,
    ForeignKey,
    JSON,
    UniqueConstraint,
    BigInteger
)
from sqlalchemy.ext.declarative import declarative_base

from .connect_manager import PostgreModel

class User(PostgreModel):
    __tablename__ = 'user'
    user_name = Column(Integer, primary_key=True)
    create_date = Column(DateTime)
    password_hash = Column(Text)

class UserData(PostgreModel):
    __tablename__ = 'user_data'
    user_name = Column(Integer, ForeignKey("user.user_name"), primary_key=True)
    user_qq = Column(Integer, index=True)
    main_character_id = Column(Integer, index=True)


class VipStatus(PostgreModel):
    __tablename__ = 'vip_status'
    user_qq = Column(Integer, primary_key=True)
    vip_level = Column(Integer)
    vip_end_date = Column(DateTime)

class InvitCode(PostgreModel):
    __tablename__ = 'invite_code'
    invite_code = Column(Text, primary_key=True)
    user_qq = Column(Integer, ForeignKey("user.user_qq"))
    create_date = Column(DateTime)
    used_data = Column(DateTime)

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

class EveAliasCharacter(PostgreModel):
    __tablename__ = 'alias_character'
    alias_character_id = Column(Integer, primary_key=True)
    main_character_id = Column(Integer, nullable=False, index=True)
    character_name = Column(Text)

class IndustryPlan(PostgreModel):
    __tablename__ = 'industry_plan'
    id = Column(Integer, primary_key=True)

class IndustryPlanProdution(PostgreModel):
    __tablename__ = 'industry_plan_item'
    id = Column(Integer, primary_key=True)

class IndustryPlanMatcher(PostgreModel):
    __tablename__ = 'industry_plan_matcher'
    id = Column(Integer, primary_key=True)

