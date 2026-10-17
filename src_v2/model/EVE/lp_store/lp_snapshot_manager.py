"""
LP快照编排器
负责调用评估器并将结果存储到PostgreSQL数据库。
"""
from datetime import date

from sqlalchemy import text

from src_v2.core.database.connect_manager import get_postgres_manager
from src_v2.core.database.model import (
    EveLpValueSnapshot,
    EveLpValueSnapshotDetail,
)
from src_v2.core.log import logger
from src_v2.model.EVE.lp_store.lp_evaluator import LpEvaluator


class LpSnapshotManager:
    """LP快照编排器 — 评估所有军团LP价值并批量写入数据库"""

    async def take_snapshot(self) -> int:
        """
        执行LP价值快照：评估所有军团 → 批量写入数据库。

        流程：
        1. 调用 LpEvaluator 评估所有NPC军团
        2. 删除当天的旧快照（幂等覆盖）
        3. 逐军团写入 EveLpValueSnapshot + EveLpValueSnapshotDetail

        Returns:
            int: 写入的快照记录数（EveLpValueSnapshot 行数）
        """
        evaluator = LpEvaluator()
        results = await evaluator.evaluate_all_corporations()

        if not results:
            logger.warning("LP评估未产生任何结果，跳过快照")
            return 0

        today = date.today()
        snapshot_count = 0

        db = get_postgres_manager()
        async with db.get_session() as session:
            # Step 1: 删除当天已有快照（幂等覆盖）
            await session.execute(
                text(
                    "DELETE FROM eve_lp_value_snapshot_detail "
                    "WHERE snapshot_id IN ("
                    "  SELECT id FROM eve_lp_value_snapshot WHERE snapshot_date = :date"
                    ")"
                ),
                {"date": today},
            )
            await session.execute(
                text("DELETE FROM eve_lp_value_snapshot WHERE snapshot_date = :date"),
                {"date": today},
            )
            await session.flush()

            # Step 2: 逐军团写入快照
            for corp_result in results:
                # 写入 snapshot 主记录
                snapshot_row = EveLpValueSnapshot(
                    snapshot_date=today,
                    corporation_id=corp_result["corporation_id"],
                    corporation_name=corp_result["corporation_name"],
                    corporation_name_zh=corp_result["corporation_name_zh"],
                    faction_id=corp_result["faction_id"],
                    lp_buy_value=corp_result["lp_buy_value"],
                    lp_sell_value=corp_result["lp_sell_value"],
                    lp_sell_value_all=corp_result.get("lp_sell_value_all", 0.0),
                    top_items_json=corp_result["top_items"],
                    total_offers=corp_result["total_offers"],
                    evaluated_offers=corp_result["evaluated_offers"],
                    excluded_offers=corp_result["excluded_offers"],
                )
                session.add(snapshot_row)
                await session.flush()  # 获取 auto-increment ID

                snapshot_id = snapshot_row.id

                # 写入 detail 子记录（评估项 + 排除项）
                detail_batch: list[EveLpValueSnapshotDetail] = []
                all_items = corp_result.get("details", []) + corp_result.get("excluded_details", [])

                for item in all_items:
                    detail_row = EveLpValueSnapshotDetail(
                        snapshot_id=snapshot_id,
                        corporation_id=corp_result["corporation_id"],
                        offer_id=item.get("offer_id", 0),
                        type_id=item.get("type_id", 0),
                        type_name_en=item.get("type_name_en", ""),
                        type_name_zh=item.get("type_name_zh", ""),
                        quantity=item.get("quantity", 0),
                        lp_cost=item.get("lp_cost", 0),
                        isk_cost=int(item.get("isk_cost", 0)),
                        market_buy_price=item.get("market_buy_price"),
                        market_sell_price=item.get("market_sell_price"),
                        daily_volume_30d=item.get("daily_volume"),
                        daily_value_30d=item.get("daily_value"),
                        lp_buy_value=item.get("lp_buy_value"),
                        lp_sell_value=item.get("lp_sell_value"),
                        is_in_top=item.get("is_in_top", False),
                        excluded=item.get("excluded", False),
                        excluded_reason=item.get("excluded_reason"),
                    )
                    detail_batch.append(detail_row)

                session.add_all(detail_batch)
                snapshot_count += 1

                # 每10个军团 flush 一次，控制内存
                if snapshot_count % 10 == 0:
                    await session.flush()

            # 最终 flush 由 context manager 退出时 commit 负责
            await session.flush()
            await session.commit()

        logger.info(f"LP快照完成: 写入 {snapshot_count} 个军团记录")
        return snapshot_count
