"""
LP蓝图成本计算器

通过查询LP兑换快照数据，计算势力(Faction)蓝图产品的ISK成本。
公式: (min_lp_buy_value * lp_cost + isk_cost) / products_per_run
"""

from sqlalchemy import desc, select

from src_v2.core.database.connect_manager import get_postgres_manager
from src_v2.core.database.model import EveLpValueSnapshot, EveLpValueSnapshotDetail
from src_v2.core.log import logger
from src_v2.model.EVE.sde import SdeUtils

from ..blueprint import BPManager


class LpBlueprintCostCalculator:
    """LP蓝图成本计算器。

    通过查询LP快照数据，计算势力蓝图产品的ISK制造成本。
    读取eve_lp_value_snapshot和eve_lp_value_snapshot_detail表（只读）。
    """

    async def calc_blueprint_cost(
        self,
        product_type_id: int,
        sdm=None,
        db=None,
    ) -> float:
        """计算势力蓝图产品的ISK成本。

        Args:
            product_type_id: 产品typeID（如Fed Navy Comet = 3516）
            sdm: SDE数据库管理器（可选，用于BPManager和SdeUtils）
            db: PostgreSQL数据库管理器（可选，默认使用get_postgres_manager()）

        Returns:
            float: 每个产品的ISK成本。非势力产品或无数据时返回0.0。
        """
        try:
            # Step 1: 检查是否为势力产品
            meta = await SdeUtils.get_metaname_by_typeid(
                product_type_id, pdm=sdm,
            )
            if meta != "Faction":
                return 0.0

            # Step 2: 获取BPC的typeID
            bpc_type_id = await BPManager.get_bp_id_by_prod_typeid(
                product_type_id, pdm=sdm,
            )
            if bpc_type_id is None:
                logger.warning(
                    f"LP蓝图成本: 未找到产品 {product_type_id} 的BPC"
                )
                return 0.0

            # Step 3: 获取数据库管理器
            if db is None:
                db = get_postgres_manager()

            # Step 4: 查询LP兑换详情
            offers = await self._query_lp_offer_detail(bpc_type_id, db)
            if not offers:
                logger.warning(
                    f"LP蓝图成本: 未找到BPC {bpc_type_id} (产品{product_type_id})的LP兑换数据"
                )
                return 0.0

            # Step 5: 优先用detail自身的lp_buy_value（BPC评估值），否则查军团快照
            corp_costs = []
            for lp_cost, isk_cost, corp_id, detail_lp_buy_value in offers:
                if detail_lp_buy_value is not None and detail_lp_buy_value > 0 and lp_cost > 0:
                    # BPC已由_evaluate_bpc评估，直接用评估值
                    corp_costs.append((detail_lp_buy_value, lp_cost, isk_cost))
                elif lp_cost > 0:
                    # 普通物品或无BPC评估值，查军团快照的标准LP价值
                    lp_buy_value = await self._query_lp_snapshot(corp_id, db)
                    if lp_buy_value is not None:
                        corp_costs.append((lp_buy_value, lp_cost, isk_cost))

            if not corp_costs:
                logger.warning(
                    f"LP蓝图成本: BPC {bpc_type_id} 的所有军团均无LP快照数据"
                )
                return 0.0

            # 选lp_buy_value最低的军团
            min_lp_buy_value, lp_cost, isk_cost = min(
                corp_costs, key=lambda x: x[0],
            )

            # Step 6: 获取单次制造产量
            products_per_run = await BPManager.get_bp_product_quantity_typeid(
                product_type_id, pdm=sdm,
            )

            # Step 7: 计算成本
            return (min_lp_buy_value * lp_cost + isk_cost) / products_per_run

        except Exception as e:
            logger.warning(
                f"LP蓝图成本计算异常: product_type_id={product_type_id}, error={e}"
            )
            return 0.0

    async def _query_lp_offer_detail(
        self, bpc_type_id: int, db,
    ) -> list:
        """查询最新快照中指定BPC的LP兑换详情。

        Args:
            bpc_type_id: BPC的typeID
            db: PostgreSQL数据库管理器

        Returns:
            list of (lp_cost, isk_cost, corporation_id, detail_lp_buy_value) tuples
        """
        async with db.get_session() as session:
            # 子查询：找到有该type_id数据的最新snapshot_date
            latest_date_subq = (
                select(EveLpValueSnapshot.snapshot_date)
                .select_from(EveLpValueSnapshotDetail)
                .join(
                    EveLpValueSnapshot,
                    EveLpValueSnapshotDetail.snapshot_id == EveLpValueSnapshot.id,
                )
                .where(EveLpValueSnapshotDetail.type_id == bpc_type_id)
                .order_by(desc(EveLpValueSnapshot.snapshot_date))
                .limit(1)
            ).scalar_subquery()

            # 主查询：获取最新日期下所有军团的兑换详情
            stmt = (
                select(
                    EveLpValueSnapshotDetail.lp_cost,
                    EveLpValueSnapshotDetail.isk_cost,
                    EveLpValueSnapshotDetail.corporation_id,
                    EveLpValueSnapshotDetail.lp_buy_value,
                )
                .select_from(EveLpValueSnapshotDetail)
                .join(
                    EveLpValueSnapshot,
                    EveLpValueSnapshotDetail.snapshot_id == EveLpValueSnapshot.id,
                )
                .where(
                    (EveLpValueSnapshotDetail.type_id == bpc_type_id)
                    & (EveLpValueSnapshot.snapshot_date == latest_date_subq)
                )
            )
            result = await session.execute(stmt)
            rows = result.all()
            return [
                (row.lp_cost, row.isk_cost, row.corporation_id, row.lp_buy_value)
                for row in rows
            ]

    async def _query_lp_snapshot(
        self, corp_id: int, db,
    ) -> float | None:
        """查询最新快照中指定军团的LP收单价值。

        Args:
            corp_id: 军团ID
            db: PostgreSQL数据库管理器

        Returns:
            float: lp_buy_value (ISK/LP)，无数据时返回None
        """
        async with db.get_session() as session:
            stmt = (
                select(EveLpValueSnapshot.lp_buy_value)
                .where(EveLpValueSnapshot.corporation_id == corp_id)
                .order_by(desc(EveLpValueSnapshot.snapshot_date))
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
