"""
价格趋势聚合服务。

供"求解/汇总类"接口一次带上价格趋势使用：调用方给出 type_id 列表，
这里统一按「按成交量加权、排除最近 2 天」的口径算好摘要，
并把缺失物品排入 ESI 采集（进程内 single-flight，避免重复拉取）。
"""
import asyncio
import traceback
from datetime import datetime, timedelta, timezone

from src_v2.core.database.kahuna_database_utils_v2 import (
    EveMarketRegionHistoryStatisticDBUtils,
)
from src_v2.core.log import logger

# 进行中的采集任务（key: f"{region_id}:{type_id}"）
_TREND_JOBS: dict[str, asyncio.Task] = {}

DEFAULT_DAYS = 30
# 与 update_type_id_history_detale 一致：排除最近 2 天（ESI 有滞后）
WINDOW_OFFSET_DAYS = 2


def _date_windows(days: int):
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    end_dt = (now - timedelta(days=WINDOW_OFFSET_DAYS)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start_dt = (now - timedelta(days=days + WINDOW_OFFSET_DAYS)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start_dt.replace(tzinfo=None), end_dt.replace(tzinfo=None)


def schedule_collect(type_ids: list[int], region_id: int) -> int:
    """把缺失物品排入后台采集，同一物品只跑一次。返回新排入的数量。"""
    try:
        from src_v2.model.EVE.market.market_manager import MarketManager
    except Exception:
        return 0

    todo = [tid for tid in type_ids if f"{region_id}:{tid}" not in _TREND_JOBS]
    if not todo:
        return 0

    async def _run(tids: list[int]):
        try:
            await MarketManager().update_type_id_list_market_region_history(tids, region_id)
            logger.info(f"价格趋势采集完成: region={region_id}, 数量={len(tids)}")
        except Exception:
            logger.error(f"价格趋势采集失败: {traceback.format_exc()}")
        finally:
            for tid in tids:
                _TREND_JOBS.pop(f"{region_id}:{tid}", None)

    for tid in todo:
        _TREND_JOBS[f"{region_id}:{tid}"] = asyncio.create_task(_run([tid]))
    return len(todo)


async def build_price_trends(
    type_ids: list[int],
    region_id: int,
    days: int = DEFAULT_DAYS,
    collect_missing: bool = True,
) -> tuple[dict, dict]:
    """
    批量构建价格趋势摘要。

    :return: (data, meta)
        data: { str(type_id): {last_avg, wavg, pct, min_low, max_high, spark, volume, as_of} }
        meta: {missing: [int], collecting: int, as_of: str}
    """
    type_ids = list(dict.fromkeys([int(t) for t in type_ids if t]))
    if not type_ids:
        return {}, {"missing": [], "collecting": 0, "as_of": ""}

    start_dt, end_dt = _date_windows(days)
    records = await EveMarketRegionHistoryStatisticDBUtils.get_records_by_type_ids(
        type_ids=type_ids,
        region_id=region_id,
        start_date=start_dt,
        end_date=end_dt,
    )

    buckets: dict[int, list] = {}
    for record in records:
        date_obj = record.date.date() if isinstance(record.date, datetime) else record.date
        buckets.setdefault(int(record.type_id), []).append(
            {
                "date": date_obj.isoformat(),
                "highest": float(record.highest) if record.highest else 0.0,
                "lowest": float(record.lowest) if record.lowest else 0.0,
                "average": float(record.average) if record.average else 0.0,
                "volume": int(record.volume) if record.volume else 0,
            }
        )

    data: dict[str, dict] = {}
    as_of = ""
    for tid, rows in buckets.items():
        rows.sort(key=lambda x: x["date"])
        total_vol = sum(r["volume"] for r in rows)
        weighted = sum(r["average"] * r["volume"] for r in rows)
        wavg = (weighted / total_vol) if total_vol > 0 else 0.0
        if not wavg:
            avgs = [r["average"] for r in rows if r["average"] > 0]
            wavg = (sum(avgs) / len(avgs)) if avgs else 0.0
        last_avg = rows[-1]["average"] or 0.0
        step = max(1, len(rows) // 15)
        data[str(tid)] = {
            "last_avg": round(last_avg, 2),
            "wavg": round(wavg, 2),
            "pct": round(((last_avg - wavg) / wavg) * 100, 2) if wavg else 0.0,
            "min_low": round(min((r["lowest"] or r["average"]) for r in rows), 2),
            "max_high": round(max((r["highest"] or r["average"]) for r in rows), 2),
            "spark": [round(r["average"], 2) for r in rows[::step]][:15],
            "volume": total_vol,
            "as_of": rows[-1]["date"],
        }
        as_of = max(as_of, rows[-1]["date"])

    missing = [tid for tid in type_ids if str(tid) not in data]
    collecting = schedule_collect(missing, region_id) if (missing and collect_missing) else 0
    return data, {"missing": missing, "collecting": collecting, "as_of": as_of}