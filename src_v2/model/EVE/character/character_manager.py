from datetime import datetime, timedelta, timezone
import re
from symtable import Class
from warnings import deprecated
from typing import Dict, AnyStr, List
import os
import asyncio

from .character import Character
from ..eveesi import eveesi
from ..eveesi.eveutils import parse_iso_datetime

# import logger
from src_v2.core.log import logger
from src_v2.core.database.connect_manager import redis_manager

#import Exception
from src_v2.core.utils import KahunaException, SingletonMeta
from ..eveesi.oauth import refresh_token

from src_v2.core.database.kahuna_database_utils_v2 import EveAuthedCharacterDBUtils
from src_v2.core.database.model import EveAuthedCharacter as M_EveAuthedCharacter
from src_v2.core.database.kahuna_database_utils_v2 import EveCorporationDBUtils
from src_v2.core.database.model import EveCorporation as M_EveCorporation
from src_v2.core.database.kahuna_database_utils_v2 import EvePublicCharacterInfoDBUtils
from src_v2.core.database.model import EvePublicCharacterInfo as M_EvePublicCharacterInfo
from src_v2.core.database.kahuna_database_utils_v2 import EveAliasCharacterDBUtils
from src_v2.core.database.model import EveAliasCharacter as M_EveAliasCharacter
from src_v2.core.picture_render.downloader import IconDownloader
from src_v2.core.utils.path import DOWNLOAD_RESOURCE_PATH

from src_v2.model.EVE.character import character

class CharacterManager(metaclass=SingletonMeta):
    async def get_character_by_character_id(self, character_id: int) -> Character:
        character_db_obj = await EveAuthedCharacterDBUtils.select_character_by_character_id(character_id)
        if not character_db_obj:
            raise KahunaException("角色不存在")

        character = Character.from_db_obj(character_db_obj)
        return character

    async def get_corporation_data_by_corporation_id(self, corporation_id: int) -> M_EveCorporation:
        corp_onj = await EveCorporationDBUtils.select_corporation_by_corporation_id(
            corporation_id=corporation_id
        )
        if not corp_onj:
            corporation = await eveesi.corporations_corporation_id(corporation_id)
            corp_onj = M_EveCorporation(
                corporation_id=corporation_id,
                alliance_id=corporation['alliance_id'] if 'alliance_id' in corporation else None,
                ceo_id=corporation['ceo_id'],
                creator_id=corporation['creator_id'],
                date_founded=parse_iso_datetime(corporation['date_founded']).replace(tzinfo=None) if 'date_founded' in corporation else None,
                description=corporation['description'] if 'description' in corporation else None,
                faction_id=corporation['faction_id'] if 'faction_id' in corporation else None,
                home_station_id=corporation['home_station_id'] if 'home_station_id' in corporation else None,
                member_count=corporation['member_count'],
                name=corporation['name'],
                shares=corporation['shares'] if 'shares' in corporation else None,
                tax_rate=corporation['tax_rate'],
                ticker=corporation['ticker'],
                url=corporation['url'] if 'url' in corporation else None,
                war_eligible=corporation['war_eligible'] if 'war_eligible' in corporation else None
            )

            # 下载 corporation icon
            corporation_icon = await eveesi.corporations_corporation_id_icons(corporation_id)
            await IconDownloader.download_from_url2path(url=corporation_icon['px128x128'], save_path=os.path.join(DOWNLOAD_RESOURCE_PATH, "img", f"corporation_{corporation_id}_128.png"))
            corp_onj.corporation_icon = os.path.join(DOWNLOAD_RESOURCE_PATH, "img", f"corporation_{corporation_id}_128.png")
            await EveCorporationDBUtils.save_obj(corp_onj)

        return corp_onj

    async def insert_new_character(self, token_data: Dict, user_name: AnyStr) -> Character:
        ac_token = token_data["ac_token"]
        refresh_token = token_data["refresh_token"]
        expires_at = token_data["expires_at"]

        character_verify_data = await eveesi.verify_token(ac_token)
        if not character_verify_data or 'CharacterID' not in character_verify_data:
            logger.error('No character info found')
            logger.error(character_verify_data)
            raise KahunaException('No character info found')

        character_id = character_verify_data['CharacterID']
        character_data = await eveesi.characters_character(character_id)
        corp_id = character_data['corporation_id']
        character_name = character_verify_data['CharacterName']
        birthday = (parse_iso_datetime(character_data['birthday'])
                    .astimezone(timezone(timedelta(hours=+8), 'Shanghai'))
                    .replace(tzinfo=None))
        corporation_id = character_data['corporation_id']
        expires_time = (parse_iso_datetime(character_verify_data["ExpiresOn"])
                        .astimezone(timezone(timedelta(hours=+8), 'Shanghai'))
                        .replace(tzinfo=None))

        character_db_obj = M_EveAuthedCharacter(
            character_id=character_id,
            owner_user_name=user_name,
            character_name=character_name,
            birthday=birthday,
            access_token=ac_token,
            refresh_token=refresh_token,
            expires_time=expires_time,
            corporation_id=corporation_id
            # director="Director" in character_roles['roles'] if 'roles' in character_roles else None,
        )
        await EveAuthedCharacterDBUtils.merge(character_db_obj)
        character = Character.from_db_obj(character_db_obj)
        character_roles = await eveesi.characters_character_roles(character.ac_token, character_id)
        character_db_obj.director = "Director" in character_roles['roles'] if 'roles' in character_roles else None
        await EveAuthedCharacterDBUtils.merge(character_db_obj)

        return character

    async def get_user_all_characters(self, user_name: str) -> List[M_EveAuthedCharacter]:
        characters_of_user_list = []
        async for character in await EveAuthedCharacterDBUtils.select_all_by_owner_user_name(user_name):
            characters_of_user_list.append(character)
        return characters_of_user_list

    async def delete_character_by_character_name(self, character_name: str, owner_user_name: str):
        character_db_obj = await EveAuthedCharacterDBUtils.select_character_by_character_name(character_name)
        if not character_db_obj:
            raise KahunaException("角色不存在")
        await EveAuthedCharacterDBUtils.delete_obj(character_db_obj)

    async def delete_all_alias_characters_of_main_character(self, main_character_id: int):
        async for alias_character in await EveAliasCharacterDBUtils.select_all_by_main_character_id(main_character_id):
            await EveAliasCharacterDBUtils.delete_obj(alias_character)

    async def delete_all_character_of_user(self, owner_user_name: str):
        async for character in await EveAuthedCharacterDBUtils.select_all_by_owner_user_name(owner_user_name):
            await EveAuthedCharacterDBUtils.delete_obj(character)

    async def update_director_status(self, character_id: int):
        character_db_obj = await EveAuthedCharacterDBUtils.select_character_by_character_id(character_id)
        if not character_db_obj:
            raise KahunaException("角色不存在")

        character = Character.from_db_obj(character_db_obj)
        character_roles = await eveesi.characters_character_roles(character.ac_token, character.character_id)
        director_status = "Director" in character_roles['roles'] if 'roles' in character_roles else None
        if director_status != character_db_obj.director:
            character_db_obj.director = director_status
            await EveAuthedCharacterDBUtils.merge(character_db_obj)

    async def get_character_by_character_name(self, character_name: str):
        character = await EveAuthedCharacterDBUtils.select_character_by_character_name(character_name)
        if not character:
            raise KahunaException("角色不存在")
        return character

    async def get_director_character_id_of_corporation(self, corporation_id: int):
        async for character in await EveAuthedCharacterDBUtils.select_all_characters_by_corporation_id(corporation_id):
            if character.director:
                return character.character_id
        return None

    async def refresh_all_public_characters_info_of_corporation(self, access_token, corporation_id: int):
        last_refresh_time = await redis_manager.redis.get(f"forever:ref_corp_chac_pub_info_corpid_{corporation_id}")
        if last_refresh_time:
            if last_refresh_time == "true":
                return

        # 收集所有角色对象
        characters_id_list = await eveesi.corporations_corporation_id_members(access_token, corporation_id)
        
        # 生成批量任务
        batch_tasks = []
        for character_id in characters_id_list:
            batch_tasks.append(asyncio.create_task(eveesi.characters_character(character_id)))

        # 执行批量任务
        characters_info_list = await asyncio.gather(*batch_tasks)

        # 更新数据库    
        for character_info in characters_info_list:
            character_db_obj = await EvePublicCharacterInfoDBUtils.select_public_character_info_by_character_id(character_info['character_id'])
            if character_db_obj:
                character_db_obj.alliance_id = character_info['alliance_id'] if 'alliance_id' in character_info else None
                character_db_obj.birthday = parse_iso_datetime(character_info['birthday']).replace(tzinfo=None)
                character_db_obj.bloodline_id = character_info['bloodline_id']
                character_db_obj.corporation_id = character_info['corporation_id']
                character_db_obj.description = character_info['description'] if 'description' in character_info else None
                character_db_obj.faction_id = character_info['faction_id'] if 'faction_id' in character_info else None
                character_db_obj.gender = character_info['gender']
                character_db_obj.name = character_info['name']
                character_db_obj.race_id = character_info['race_id']
                character_db_obj.security_status = character_info['security_status'] if 'security_status' in character_info else None
                character_db_obj.title = character_info['title'] if 'title' in character_info else None
                await EvePublicCharacterInfoDBUtils.merge(character_db_obj)
            else:
                await EvePublicCharacterInfoDBUtils.save_obj(M_EvePublicCharacterInfo(
                    character_id=character_info['character_id'],
                    alliance_id=character_info['alliance_id'] if 'alliance_id' in character_info else None,
                    birthday=parse_iso_datetime(character_info['birthday']).replace(tzinfo=None),
                    bloodline_id=character_info['bloodline_id'],
                    corporation_id=character_info['corporation_id'],
                    description=character_info['description'] if 'description' in character_info else None,
                    faction_id=character_info['faction_id'] if 'faction_id' in character_info else None,
                    gender=character_info['gender'],
                    name=character_info['name'],
                    race_id=character_info['race_id'],
                    security_status=character_info['security_status'] if 'security_status' in character_info else None,
                    title=character_info['title'] if 'title' in character_info else None,
                ))

        await redis_manager.redis.set(f"forever:ref_corp_chac_pub_info_corpid_{corporation_id}", "true", ex=60 * 60 * 24)

    async def get_public_character_info_by_character_id(self, character_id: int):
        character_db_obj = await EvePublicCharacterInfoDBUtils.select_public_character_info_by_character_id(character_id)
        if not character_db_obj:
            character_info = await eveesi.characters_character(character_id)
            character_db_obj = M_EvePublicCharacterInfo(
                character_id=character_id,
                alliance_id=character_info['alliance_id'] if 'alliance_id' in character_info else None,
                birthday=parse_iso_datetime(character_info['birthday']).replace(tzinfo=None),
                bloodline_id=character_info['bloodline_id'],
                corporation_id=character_info['corporation_id'],
                description=character_info['description'] if 'description' in character_info else None,
                faction_id=character_info['faction_id'] if 'faction_id' in character_info else None,
                gender=character_info['gender'],
                name=character_info['name'],
                race_id=character_info['race_id'],
                security_status=character_info['security_status'] if 'security_status' in character_info else None,
                title=character_info['title'] if 'title' in character_info else None,
            )
            await EvePublicCharacterInfoDBUtils.save_obj(character_db_obj)
        return character_db_obj