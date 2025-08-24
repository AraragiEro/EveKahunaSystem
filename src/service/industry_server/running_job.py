from tqdm import tqdm

# from ..database_server.model import IndustryJobs as M_IndustryJobs, IndustryJobsCache as M_IndustryJobsCache
from ..database_server.sqlalchemy.kahuna_database_utils import (
    IndustryJobsDBUtils, IndustryJobsCacheDBUtils
)
from ..character_server.character import Character
from ..evesso_server.eveesi import characters_character_id_industry_jobs, corporations_corporation_id_industry_jobs
# from ..database_server.connect import DatabaseConectManager

# kahuna logger
from ..log_server import logger

class RunningJobOwner:
    @classmethod
    async def refresh_character_running_job(cls, character: Character):
        logger.info(f"开始刷新 {character.character_name} job")
        character_running_job = await characters_character_id_industry_jobs(character.ac_token, character.character_id)
        if not character_running_job:
            return

        for data in character_running_job:
            data['location_id'] = data['station_id']
            data.pop('station_id')
            data.update({'owner_id': character.character_id})
        await IndustryJobsDBUtils.delete_jobs_by_owner_id(character.character_id)
        await IndustryJobsDBUtils.insert_many(character_running_job)

    @classmethod
    async def refresh_corp_running_job(cls, corp_id, character: Character):
        logger.info(f"开始刷新 corp {corp_id} job。")
        results = await corporations_corporation_id_industry_jobs(character.ac_token, corp_id)
        await IndustryJobsDBUtils.delete_jobs_by_owner_id(corp_id)
        for result in results:
            for data in result:
                data.update({'owner_id': corp_id})
            await IndustryJobsDBUtils.insert_many(result)

    @classmethod
    async def copy_to_cache(cls):
        await IndustryJobsCacheDBUtils.copy_base_to_cache()

    @classmethod
    async def get_job_with_starter(cls, character_id_list: list):
        return await IndustryJobsCacheDBUtils.select_jobs_by_installer_id_list(character_id_list)

    @classmethod
    async def get_using_bp_set(cls):
        running_jobs = await IndustryJobsCacheDBUtils.select_all()

        return set(job.blueprint_id for job in running_jobs)

    @classmethod
    async def get_character_using_count(cls, character_id: int):
        manu_jobs = await IndustryJobsCacheDBUtils.select_jobs_by_installer_id_and_type(character_id, 1)
        reac_job = await IndustryJobsCacheDBUtils.select_jobs_by_installer_id_and_type(character_id, 11)

        return {
            'manu': len(manu_jobs),
            'reac': len(reac_job)
        }

    @classmethod
    async def get_using_count_of_alias_characters(cls, character_id_list: list):
        res = {}
        for character_id in character_id_list:
            res[character_id] = await cls.get_character_using_count(character_id)

        return res