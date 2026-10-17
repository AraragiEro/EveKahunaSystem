"""
Redis 启动清理模块
在服务器启动时清理残留的计算状态 key，防止因进程崩溃/重启导致的状态堆积。
"""
from src_v2.core.database.connect_manager import get_redis_manager as rdm
from src_v2.core.log import logger


async def run_startup_cleanup(skip_if_reloader: bool = False) -> int:
    """
    启动时清理 Redis 中残留的计算状态。

    按顺序执行三类清理：
    1. 清理计划计算状态 (pending/waiting/running)
    2. 清理市场成本计算进度 (zombie progress)
    3. 清理孤立的分布式锁

    Args:
        skip_if_reloader: 如果为 True 则在热重载模式下跳过清理。

    Returns:
        清理的 key 总数。
    """
    if skip_if_reloader:
        logger.warning("开发模式(热重载)下跳过启动清理")
        return 0

    logger.info("开始清理残留的Redis计算状态...")
    total_cleaned = 0

    # 1. 清理计划计算状态
    cleaned = await _cleanup_plan_calculate_status()
    total_cleaned += cleaned

    # 2. 清理市场成本计算进度
    cleaned = await _cleanup_market_cost_progress()
    total_cleaned += cleaned

    # 3. 清理孤立的分布式锁
    cleaned = await _cleanup_orphaned_locks()
    total_cleaned += cleaned

    logger.info(f"Redis启动清理完成，共清理 {total_cleaned} 个残留key")
    return total_cleaned


async def _cleanup_plan_calculate_status() -> int:
    """
    清理残留的计划计算状态 (pending/waiting/running)。

    服务器重启后内存队列已清空，这些状态已无实际意义。
    同时删除关联的进度 key (total_progress / current_progress)。

    使用 SCAN 非阻塞扫描，不删除 completed 状态和 result key。
    """
    pattern = "plan_calculate_status:*:*"
    cleaned = 0
    cursor = 0

    try:
        while True:
            cursor, keys = await rdm().r.scan(cursor=cursor, match=pattern, count=100)

            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                try:
                    raw_status = await rdm().r.get(key_str)
                    if raw_status is None:
                        continue
                    status = raw_status.decode() if isinstance(raw_status, bytes) else raw_status

                    # 只清理 pending / waiting:* / running
                    if status not in ("pending", "running") and not status.startswith("waiting:"):
                        continue

                    # 解析 user 和 plan (plan_name 可能包含冒号)
                    # format: plan_calculate_status:user_id:plan_name
                    parts = key_str.split(":")
                    if len(parts) < 3:
                        continue
                    user_id = parts[1]
                    plan_name = ":".join(parts[2:])

                    # 删除状态 key
                    await rdm().r.delete(key_str)
                    cleaned += 1
                    logger.info(f"启动清理: 删除残留key {key_str} (原因: 状态={status})")

                    # 删除关联的进度 key
                    for companion_suffix in (
                        f"plan_calculate_total_progress:{user_id}:{plan_name}",
                        f"plan_calculate_current_progress:{user_id}:{plan_name}",
                    ):
                        exists = await rdm().r.exists(companion_suffix)
                        if exists:
                            await rdm().r.delete(companion_suffix)
                            cleaned += 1
                            logger.info(
                                f"启动清理: 删除残留key {companion_suffix} "
                                f"(原因: 关联的status已清理)"
                            )

                except Exception as e:
                    logger.warning(f"启动清理: 处理 key {key_str} 时出错: {e}")
                    continue

            if cursor == 0:
                break
    except Exception as e:
        logger.error(f"启动清理 plan_calculate_status 失败: {e}", exc_info=True)

    return cleaned


async def _cleanup_market_cost_progress() -> int:
    """
    清理残留的市场成本计算进度。

    扫描 market_cost_calculation_progress:* 中 status=running 的 key，
    如果对应的 calculate_cost_lock 不存在（说明进程已崩溃），
    则删除进度 key 和关联的 total key。

    逻辑参考 cost_refresher.py cleanup_zombie_progress()，
    但使用 SCAN 而非 KEYS 以避免阻塞。
    """
    pattern = "market_cost_calculation_progress:*:*"
    cleaned = 0
    cursor = 0

    try:
        while True:
            cursor, keys = await rdm().r.scan(cursor=cursor, match=pattern, count=100)

            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                try:
                    # 提取 user_name 和 market_id
                    # format: market_cost_calculation_progress:user_name:market_id
                    parts = key_str.split(":")
                    if len(parts) < 3:
                        continue
                    user_name = parts[-2]
                    market_id = int(parts[-1])

                    # 读取 hash 内容
                    raw_data = await rdm().r.hgetall(key_str)
                    if not raw_data:
                        continue

                    # 解码字段
                    decoded = {}
                    for k, v in raw_data.items():
                        k_str = k.decode() if isinstance(k, bytes) else k
                        v_str = v.decode() if isinstance(v, bytes) else v
                        decoded[k_str] = v_str

                    status = decoded.get("status", "")
                    if status != "running":
                        continue

                    # 检查对应的分布式锁是否存在
                    lock_key = f"calculate_cost_lock:{user_name}:{market_id}"
                    lock_exists = await rdm().r.exists(lock_key)

                    if lock_exists:
                        logger.debug(f"启动清理: 跳过正在运行的任务 {key_str} (锁存在)")
                        continue

                    # 锁已消失，删除进度 key
                    await rdm().r.delete(key_str)
                    cleaned += 1
                    logger.info(f"启动清理: 删除残留key {key_str} (原因: status=running 但锁不存在)")

                    # 删除关联的 total key
                    total_key = f"market_cost_calculation_total:{user_name}:{market_id}"
                    total_exists = await rdm().r.exists(total_key)
                    if total_exists:
                        await rdm().r.delete(total_key)
                        cleaned += 1
                        logger.info(f"启动清理: 删除残留key {total_key} (原因: 关联的progress已清理)")

                except (ValueError, IndexError) as e:
                    logger.warning(f"启动清理: 解析 key 失败 {key_str}: {e}")
                    continue

            if cursor == 0:
                break
    except Exception as e:
        logger.error(f"启动清理 market_cost_progress 失败: {e}", exc_info=True)

    return cleaned


async def _cleanup_orphaned_locks() -> int:
    """
    清理孤立的分布式锁。

    服务器重启后所有锁都已失效（即使 TTL 未到，没有持有进程会释放它们），
    删除这些锁避免阻塞新的操作。

    分别扫描并删除:
    - calculate_cost_lock:*:*  (锁 TTL: 3600s)
    - cost_refresh_lock:*:*  (锁 TTL: 300s)
    """
    cleaned = 0

    for prefix in ("calculate_cost_lock", "cost_refresh_lock"):
        pattern = f"{prefix}:*:*"
        cursor = 0

        try:
            while True:
                cursor, keys = await rdm().r.scan(cursor=cursor, match=pattern, count=100)

                if keys:
                    await rdm().r.delete(*keys)
                    for key in keys:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        logger.info(f"启动清理: 删除残留key {key_str} (原因: 孤立锁)")
                    cleaned += len(keys)

                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"启动清理 {pattern} 失败: {e}")

    return cleaned
