import asyncio
from datetime import datetime, timedelta, timezone

from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.database.kahuna_database_utils_v2 import EvePublicCharacterInfoDBUtils
from src_v2.core.database.model import EvePublicCharacterInfo as M_EvePublicCharacterInfo
from src_v2.core.log import logger
from src_v2.core.utils import SingletonMeta
from src_v2.model.EVE.eveesi import eveesi
from src_v2.model.EVE.eveesi.eveutils import parse_iso_datetime


class PublicCharacterRefreshTimer(metaclass=SingletonMeta):
    """
    Public Character 信息刷新定时器

    每日凌晨4:00-4:59（+8时区）时间段内自动刷新数据库中所有已存在的 public character 信息。
    通过 Redis flag 防止重复执行，标志过期时间设置为第二天凌晨4点。
    """

    REDIS_FLAG_KEY = "public_character_refresh:flag"
    TARGET_HOUR = 4  # 凌晨4点
    TIMEZONE_OFFSET = 8  # +8时区
    CHECK_INTERVAL_SECONDS = 3600  # 每小时检查一次

    def __init__(self):
        self._running = False
        self._task = None

    def _is_in_target_time_range(self) -> bool:
        """
        检查当前时间是否在目标时间范围内（4:00-4:59）

        Returns:
            bool: 如果当前时间在4:00-4:59之间，返回True
        """
        tz = timezone(timedelta(hours=self.TIMEZONE_OFFSET))
        now = datetime.now(tz)
        return now.hour == self.TARGET_HOUR

    def _get_next_target_time(self) -> datetime:
        """
        计算下一个凌晨4点（+8时区）的时间

        Returns:
            datetime: 下一个凌晨4点的时间（带时区信息）
        """
        # 获取当前+8时区时间
        tz = timezone(timedelta(hours=self.TIMEZONE_OFFSET))
        now = datetime.now(tz)

        # 计算今天的凌晨4点
        today_target = now.replace(
            hour=self.TARGET_HOUR, minute=0, second=0, microsecond=0)

        # 如果当前时间已过今天的4:59，则计算明天的凌晨4点
        # 4:59:59 之后才认为已过
        today_end = today_target.replace(minute=59, second=59)
        if now > today_end:
            next_target = today_target + timedelta(days=1)
        else:
            next_target = today_target

        return next_target

    def _calculate_seconds_until_next_target(self) -> float:
        """
        计算到下一个凌晨4点的秒数

        Returns:
            float: 到下一个凌晨4点的秒数
        """
        next_target = self._get_next_target_time()
        tz = timezone(timedelta(hours=self.TIMEZONE_OFFSET))
        now = datetime.now(tz)
        delta = next_target - now
        return delta.total_seconds()

    def _calculate_expire_seconds(self) -> int:
        """
        计算从当前时间到第二天凌晨4点的秒数（用于设置 Redis key 过期时间）

        Returns:
            int: 到第二天凌晨4点的秒数
        """
        tz = timezone(timedelta(hours=self.TIMEZONE_OFFSET))
        now = datetime.now(tz)

        # 计算明天的凌晨4点
        tomorrow = now + timedelta(days=1)
        tomorrow_target = tomorrow.replace(
            hour=self.TARGET_HOUR, minute=0, second=0, microsecond=0)

        delta = tomorrow_target - now
        return int(delta.total_seconds())

    async def _collect_all_character_ids(self) -> list[int]:
        """
        从数据库查询所有 EvePublicCharacterInfo 记录，收集所有 character_id

        Returns:
            list[int]: 所有 character_id 列表
        """
        character_ids = []
        async for character_info in await EvePublicCharacterInfoDBUtils.select_all():
            character_ids.append(character_info.character_id)
        return character_ids

    async def _refresh_character_info(self, character_id: int) -> bool:
        """
        刷新单个角色的 public 信息

        Args:
            character_id: 角色ID

        Returns:
            bool: 是否成功刷新
        """
        try:
            # 调用 ESI API 获取最新信息
            character_info = await eveesi.characters_character(character_id)

            # 查询数据库中的现有记录
            character_db_obj = await EvePublicCharacterInfoDBUtils.select_public_character_info_by_character_id(character_id)

            if character_db_obj:
                # 更新现有记录
                character_db_obj.alliance_id = character_info.get(
                    'alliance_id')
                character_db_obj.birthday = parse_iso_datetime(
                    character_info['birthday']).replace(tzinfo=None)
                character_db_obj.bloodline_id = character_info['bloodline_id']
                character_db_obj.corporation_id = character_info['corporation_id']
                character_db_obj.description = character_info.get(
                    'description')
                character_db_obj.faction_id = character_info.get('faction_id')
                character_db_obj.gender = character_info['gender']
                character_db_obj.name = character_info['name']
                character_db_obj.race_id = character_info['race_id']
                character_db_obj.security_status = character_info.get(
                    'security_status')
                character_db_obj.title = character_info.get('title')
                await EvePublicCharacterInfoDBUtils.merge(character_db_obj)
            else:
                # 创建新记录
                character_db_obj = M_EvePublicCharacterInfo(
                    character_id=character_id,
                    alliance_id=character_info.get('alliance_id'),
                    birthday=parse_iso_datetime(
                        character_info['birthday']).replace(tzinfo=None),
                    bloodline_id=character_info['bloodline_id'],
                    corporation_id=character_info['corporation_id'],
                    description=character_info.get('description'),
                    faction_id=character_info.get('faction_id'),
                    gender=character_info['gender'],
                    name=character_info['name'],
                    race_id=character_info['race_id'],
                    security_status=character_info.get('security_status'),
                    title=character_info.get('title'),
                )
                await EvePublicCharacterInfoDBUtils.merge(character_db_obj)

            return True
        except Exception as e:
            logger.warning(f"刷新角色 {character_id} 信息失败: {e}")
            return False

    async def _execute_refresh_task(self):
        """
        执行 Public Character 信息刷新任务
        """
        try:
            logger.info("开始执行 Public Character 信息刷新任务")

            # 收集所有 character_id
            character_ids = await self._collect_all_character_ids()

            if not character_ids:
                logger.warning("未找到任何 public character 记录，跳过更新")
                return

            logger.info(
                f"找到 {len(character_ids)} 个 public character 记录，开始批量刷新")

            # 批量刷新角色信息
            # 使用 asyncio.gather 并发执行，但限制并发数量以避免 API 限流
            batch_size = 50  # 每批处理50个角色
            success_count = 0
            fail_count = 0

            for i in range(0, len(character_ids), batch_size):
                batch = character_ids[i:i + batch_size]
                logger.info(
                    f"处理批次 {i // batch_size + 1}/{(len(character_ids) + batch_size - 1) // batch_size}，共 {len(batch)} 个角色")

                # 创建批量任务
                tasks = [self._refresh_character_info(
                    character_id) for character_id in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # 统计成功和失败数量
                for result in results:
                    if isinstance(result, Exception):
                        fail_count += 1
                    elif result:
                        success_count += 1
                    else:
                        fail_count += 1

                # 批次之间添加短暂延迟，避免 API 限流
                if i + batch_size < len(character_ids):
                    await asyncio.sleep(1)

            logger.info(
                f"Public Character 信息刷新任务完成，成功: {success_count}，失败: {fail_count}")

            # 任务完成后设置 Redis flag，过期时间设置为第二天凌晨4点
            expire_seconds = self._calculate_expire_seconds()
            await rdm().r.set(self.REDIS_FLAG_KEY, "1", ex=expire_seconds)
            logger.info(
                f"已设置 Redis flag，过期时间: {expire_seconds} 秒后（第二天凌晨{self.TARGET_HOUR}点）")

        except Exception as e:
            logger.error(f"执行 Public Character 信息刷新任务失败: {e}", exc_info=True)
            # 即使失败也设置一个较短的过期时间，避免一直重试
            try:
                await rdm().r.set(self.REDIS_FLAG_KEY, "1", ex=3600)  # 1小时后过期
            except Exception as redis_error:
                logger.error(f"设置 Redis flag 失败: {redis_error}", exc_info=True)

    async def _run_scheduler(self):
        """
        定时任务主循环

        每小时检查一次 Redis 标志，如果检测不到标志且当前时间在4:00-4:59范围内则执行刷新任务。
        如果标志存在或不在目标时间范围内，则等待到下一个4:00-4:59时间段。
        """
        logger.info("Public Character 信息刷新定时器已启动")

        while self._running:
            try:
                # 检查 Redis flag
                flag_exists = await rdm().r.exists(self.REDIS_FLAG_KEY)

                if not flag_exists:
                    # 检查当前时间是否在目标时间范围内（4:00-4:59）
                    if self._is_in_target_time_range():
                        # 当前时间在4:00-4:59范围内，立即执行刷新任务
                        logger.info(
                            "当前时间在4:00-4:59范围内，开始执行刷新任务")
                        await self._execute_refresh_task()
                    else:
                        # 不在目标时间范围内，计算到下一个4:00的等待时间
                        wait_seconds = self._calculate_seconds_until_next_target()

                        # 如果距离凌晨4点还有较长时间（超过1小时），先等待一段时间再检查
                        if wait_seconds > self.CHECK_INTERVAL_SECONDS:
                            logger.info(
                                f"距离下一个凌晨4点还有 {wait_seconds / 3600:.2f} 小时，等待 {self.CHECK_INTERVAL_SECONDS} 秒后再次检查")
                            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
                            continue

                        # 如果接近凌晨4点，等待到4:00
                        if wait_seconds > 0:
                            logger.info(
                                f"等待 {wait_seconds:.0f} 秒后进入4:00-4:59时间段执行刷新任务")
                            await asyncio.sleep(wait_seconds)
                            # 等待后再次检查是否在时间范围内（可能在4:00-4:59之间）
                            if self._is_in_target_time_range():
                                logger.info(
                                    "已进入4:00-4:59时间段，开始执行刷新任务")
                                await self._execute_refresh_task()
                else:
                    logger.debug("public_character_refresh:flag 存在，跳过本次执行")

                # 等待1小时后再次检查
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info("Public Character 信息刷新定时器被取消")
                break
            except Exception as e:
                logger.error(f"定时器循环出错: {e}", exc_info=True)
                # 出错后等待1小时再继续
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    def start(self):
        """
        启动定时任务
        """
        if self._running:
            logger.warning("Public Character 信息刷新定时器已在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("Public Character 信息刷新定时器已启动")

    def stop(self):
        """
        停止定时任务
        """
        if not self._running:
            logger.warning("Public Character 信息刷新定时器未运行")
            return

        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Public Character 信息刷新定时器已停止")

    async def wait(self):
        """
        等待定时任务完成（用于测试或清理）
        """
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
