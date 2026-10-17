"""
LP 价值快照 API
提供LP价值评估快照数据查询
"""
from quart import Blueprint, jsonify

from src_v2.core.database.kahuna_database_utils_v2 import EveLpValueSnapshotDBUtils

api_lp_bp = Blueprint('api_lp', __name__, url_prefix='/api/EVE/lp')


@api_lp_bp.route('/snapshot/latest', methods=['GET'])
async def get_latest_snapshot():
    """
    获取最新LP价值快照。

    返回最新 snapshot_date 的所有军团排行列表，包含 Top-5 物品详情。
    """
    # 查询最新快照日期
    latest_date = await EveLpValueSnapshotDBUtils.get_latest_snapshot_date()

    if not latest_date:
        return jsonify({"status": 200, "data": {"snapshot_date": "", "data": []}}), 200

    # 查询该日期所有军团快照，按 lp_sell_value 降序（封装内已精简响应字段）
    snapshots = await EveLpValueSnapshotDBUtils.select_snapshots_by_date(latest_date)

    return jsonify({"status": 200, "data": {"snapshot_date": str(latest_date), "data": snapshots}}), 200


@api_lp_bp.route('/snapshot/latest/corp/<int:corp_id>', methods=['GET'])
async def get_corp_lp_details(corp_id: int):
    """
    获取最新快照中某军团的全部兑换项详情（含评估项和排除项）。
    """
    # 查最新快照的 (id, snapshot_date)
    snap = await EveLpValueSnapshotDBUtils.get_latest_snapshot_id_and_date()
    if not snap:
        return jsonify({"status": 200, "data": []}), 200

    sid, snap_date = snap

    # 查该军团的最新快照 id
    snapshot_id = await EveLpValueSnapshotDBUtils.select_snapshot_id_by_date_and_corp(
        snap_date, corp_id
    )
    if not snapshot_id:
        return jsonify({"status": 200, "data": []}), 200

    # 获取全部详情（封装内已按 excluded 升序、daily_value_30d 降序并精简响应字段）
    items = await EveLpValueSnapshotDBUtils.select_details_by_snapshot_id(snapshot_id)

    return jsonify({"status": 200, "data": items}), 200
