"""
LP (Loyalty Points) 价值评估器
核心功能：对181个NPC军团的LP兑换品进行ISK/LP比率评估，计算收单/出单双向价值。

评估流程：
1. 遍历所有NPC军团，通过ESI获取LP兑换列表
2. 批量获取Jita市场买卖价格
3. 批量获取30天日均成交量
4. 排除不符合条件的兑换项（required_items/ac_cost/BPC/无买价/低成交额）
5. Top-5 日均成交额加权平均聚合军团LP价值
"""

import asyncio

from src_v2.core.database.connect_manager import get_redis_manager
from src_v2.core.log import logger
from src_v2.model.EVE.eveesi.esi_api.loyalty import loyalty_stores_corporation_id_offers
from src_v2.model.EVE.market.market_manager import MarketManager
from src_v2.model.EVE.sde.utils import SdeUtils


class LpEvaluator:
    """LP价值评估器 - 评估NPC军团LP兑换品的ISK/LP比率"""

    def __init__(self):
        self._mm = MarketManager()

    # ──────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────

    async def evaluate_all_corporations(self) -> list[dict]:
        """
        遍历所有拥有LP商店的NPC军团，评估LP兑换品价值。

        流程:
        1. 从SDE查询所有lpOfferTables不为空的NPC军团（约181个）
        2. 通过ESI获取每个军团的兑换列表
        3. 汇总所有type_id，批量获取价格和成交量
        4. 对每个军团的兑换项逐一评估并聚合

        Returns:
            list[dict]: 每个军团的评估结果
        """
        # ── 1. 查询所有有LP商店的NPC军团 ──
        corps = await SdeUtils.get_npc_corporations_with_lp()
        logger.info(f"[LP评估 1/6] 发现 {len(corps)} 个拥有LP商店的NPC军团")

        # ── 2. 逐军团获取兑换列表 ──
        all_offers = []  # list of (corp_dict, offers_list)
        all_type_ids: set[int] = set()

        for corp in corps:
            corp_id = corp["corporationID"]
            try:
                offers = await loyalty_stores_corporation_id_offers(corp_id)
                all_offers.append((corp, offers))
                for offer in offers:
                    all_type_ids.add(offer["type_id"])
            except Exception as e:
                logger.warning(f"获取军团 {corp_id} 兑换列表失败: {e}")
                all_offers.append((corp, []))

        logger.info(
            f"[LP评估 2/6] 共收集 {sum(len(o) for _, o in all_offers)} 个兑换项, "
            f"{len(all_type_ids)} 种不同物品"
        )

        if not all_type_ids:
            logger.warning("未发现任何兑换物品，返回空列表")
            return []

        # ── 构建物品独有/共有映射 ──
        type_corp_map: dict[int, set[int]] = {}
        for corp, offers in all_offers:
            for offer in offers:
                type_corp_map.setdefault(offer["type_id"], set()).add(corp["corporationID"])
        unique_type_ids = {tid for tid, corps in type_corp_map.items() if len(corps) == 1}

        # ── 3. 批量获取价格、成交量、BPC标记、物品名称 ──
        logger.info(f"[LP评估 2/6] 批量获取 {len(all_type_ids)} 种物品的 Jita 市场价格...")
        prices = await self._fetch_prices_batch(all_type_ids)

        # ── 3.5 刷新有价格物品的市场历史数据 ──
        priced_type_ids = {tid for tid, p in prices.items() if p["max_buy"] > 0}
        logger.info(f"[LP评估 3/6] 有价格物品: {len(priced_type_ids)}/{len(all_type_ids)}")
        await self._ensure_volume_data(priced_type_ids)

        logger.info(f"[LP评估 4/6] 批量读取成交量缓存...")
        volumes = await self._fetch_volumes_batch(all_type_ids, prices)
        bpc_type_ids = await self._fetch_bpc_type_ids(all_type_ids)
        type_names = await self._fetch_type_names(all_type_ids)

        # ── 3.6 提取 BPC 的制造成本信息（产品+原料） ──
        bpc_details = await self._fetch_bpc_details(bpc_type_ids)

        # ── 3.7 补取 BPC 产品和原料的价格 ──
        bpc_extra_type_ids: set[int] = set()
        for detail in bpc_details.values():
            if detail.get("product"):
                bpc_extra_type_ids.add(detail["product"][0])
            for mat in detail.get("materials", []):
                bpc_extra_type_ids.add(mat[0])
        if bpc_extra_type_ids:
            bpc_extra_prices = await self._fetch_prices_batch(bpc_extra_type_ids)
            prices.update(bpc_extra_prices)
            logger.info(f"补取 {len(bpc_extra_type_ids)} 个 BPC 相关物品的价格")

        # ── 5. 逐军团评估并聚合 ──
        logger.info(f"[LP评估 5/6] 开始评估 {len(all_offers)} 个军团的 LP 价值...")
        results = []
        for corp, offers in all_offers:
            result = self._evaluate_corporation(
                corp, offers, prices, volumes, bpc_type_ids, bpc_details, type_names, unique_type_ids
            )
            results.append(result)

        # ── 6. 汇总 ──
        total_eval = sum(r["evaluated_offers"] for r in results)
        total_excl = sum(r["excluded_offers"] for r in results)
        corps_with_value = sum(1 for r in results if r["lp_sell_value"] > 0)
        logger.info(
            f"[LP评估 6/6] 完成! {len(results)} 个军团, "
            f"{total_eval} 评估 / {total_excl} 排除, "
            f"{corps_with_value} 个军团有有效估值"
        )
        return results

    # ──────────────────────────────────────────────
    #  Batch Data Fetching
    # ──────────────────────────────────────────────

    async def _fetch_prices_batch(self, type_ids: set[int]) -> dict[int, dict]:
        """
        批量获取Jita市场价格。

        使用 asyncio.Semaphore(20) 控制并发，避免打爆Redis。

        Returns:
            dict: {type_id: {"max_buy": float, "min_sell": float}}
        """
        sem = asyncio.Semaphore(20)
        results: dict[int, dict] = {}

        async def _worker(tid: int):
            async with sem:
                try:
                    buy = await self._mm.get_jita_buy_price(tid)
                    sell = await self._mm.get_jita_sell_price(tid)
                    results[tid] = {"max_buy": float(buy), "min_sell": float(sell)}
                except Exception as e:
                    logger.warning(f"获取 type_id {tid} 价格失败: {e}")
                    results[tid] = {"max_buy": 0.0, "min_sell": 0.0}

        tasks = [asyncio.create_task(_worker(tid)) for tid in type_ids]
        await asyncio.gather(*tasks)

        logger.info(f"批量价格获取完成: {len(results)} 个物品")
        return results

    async def _fetch_volumes_batch(
        self, type_ids: set[int], prices: dict[int, dict]
    ) -> dict[int, dict]:
        """
        批量获取30天成交量，计算日均成交量和日均成交额。

        Redis key: market_region_history:10000002:{type_id}:30DTotalVolume

        Returns:
            dict: {type_id: {"daily_volume": float, "daily_value": float}}
        """
        rdm = get_redis_manager()
        sem = asyncio.Semaphore(20)
        results: dict[int, dict] = {}

        async def _worker(tid: int):
            async with sem:
                try:
                    key = f"market_region_history:10000002:{tid}:30DTotalVolume"
                    vol_str = await rdm.r.get(key)
                    total_volume = float(vol_str) if vol_str else 0.0
                    daily_volume = total_volume / 30.0
                    sell_price = prices.get(tid, {}).get("min_sell", 0.0)
                    daily_value = daily_volume * sell_price
                    results[tid] = {
                        "daily_volume": daily_volume,
                        "daily_value": daily_value,
                    }
                except Exception as e:
                    logger.warning(f"获取 type_id {tid} 成交量失败: {e}")
                    results[tid] = {"daily_volume": 0.0, "daily_value": 0.0}

        tasks = [asyncio.create_task(_worker(tid)) for tid in type_ids]
        await asyncio.gather(*tasks)

        logger.info(f"批量成交量获取完成: {len(results)} 个物品")
        return results

    async def _ensure_volume_data(self, type_ids: set[int]):
        """
        刷新 LP 兑换物品的市场历史数据：ESI → PostgreSQL → Redis。

        每次快照都执行完整管线，确保30天滚动窗口数据最新。
        PG 使用 upsert 不会重复写入。
        """
        if not type_ids:
            return

        type_list = list(type_ids)
        logger.info(f"[LP评估 3/6] 开始刷新 {len(type_list)} 个物品的市场历史数据")

        # 步骤1: ESI → PostgreSQL（upsert，不重复写入）
        logger.info(f"[LP评估 3/6] 步骤1: ESI → PostgreSQL (Semaphore 20 并发)...")
        await self._mm.update_type_id_list_market_region_history(type_list, 10000002)

        # 步骤2: PostgreSQL → Redis（计算30天统计）
        logger.info(f"[LP评估 3/6] 步骤2: PostgreSQL → Redis (30天加权统计)...")
        await self._mm.update_type_id_list_history_detale(10000002, type_list, force=True)

        logger.info(f"[LP评估 3/6] 市场历史数据刷新完成")

    async def _fetch_bpc_type_ids(self, type_ids: set[int]) -> set[int]:
        """查询哪些type_id是蓝图(Blueprint)。"""
        return await SdeUtils.get_bpc_type_ids(type_ids)

    async def _fetch_bpc_details(self, bpc_type_ids: set[int]) -> dict[int, dict]:
        """批量查询 BPC 的制造产品与原料信息。"""
        return await SdeUtils.get_bpc_manufacturing_details(bpc_type_ids)

    async def _fetch_type_names(self, type_ids: set[int]) -> dict[int, dict]:
        """批量查询物品名称（英文+中文）。"""
        return await SdeUtils.get_type_names_batch(type_ids)

    # ──────────────────────────────────────────────
    #  Core Evaluation Logic
    # ──────────────────────────────────────────────

    def _calculate_lp_value(
        self,
        offer: dict,
        prices: dict[int, dict],
        volumes: dict[int, dict],
        bpc_type_ids: set[int],
    ) -> dict:
        """
        计算单个兑换项的LP价值，执行排除检查。

        排除规则（按顺序）:
        1. required_items 非空 → 排除
        2. ak_cost > 0 → 排除
        3. 是蓝图 (categoryID=9) → 排除
        4. max_buy == 0（无买单价） → 排除
        5. daily_value < 500M ISK → 排除

        Args:
            offer: ESI兑换项 {"offer_id", "type_id", "quantity", "lp_cost", "isk_cost", "ak_cost", "required_items"}
            prices: 价格字典 {type_id: {"max_buy", "min_sell"}}
            volumes: 成交量字典 {type_id: {"daily_volume", "daily_value"}}
            bpc_type_ids: 蓝图层type_id集合

        Returns:
            dict with "excluded" flag:
            - excluded=True: {"excluded": True, "excluded_reason": str, ...}
            - excluded=False: full evaluation with lp_buy_value, lp_sell_value, etc.
        """
        type_id = offer["type_id"]

        # Exclusion 1: required_items
        required_items = offer.get("required_items", [])
        if required_items and len(required_items) > 0:
            return {"excluded": True, "excluded_reason": "has_required_items",
                    "offer_id": offer.get("offer_id"), "type_id": type_id}

        # Exclusion 2: ak_cost
        ak_cost = offer.get("ak_cost", 0)
        if ak_cost and ak_cost > 0:
            return {"excluded": True, "excluded_reason": "has_ak_cost",
                    "offer_id": offer.get("offer_id"), "type_id": type_id}

        # Exclusion 3: BPC (Blueprint)
        if type_id in bpc_type_ids:
            return {"excluded": True, "excluded_reason": "is_bpc",
                    "offer_id": offer.get("offer_id"), "type_id": type_id}

        # Exclusion 4: no buy price
        price_info = prices.get(type_id, {"max_buy": 0.0, "min_sell": 0.0})
        max_buy = price_info["max_buy"]
        min_sell = price_info["min_sell"]
        if max_buy == 0.0:
            return {"excluded": True, "excluded_reason": "no_buy_price",
                    "offer_id": offer.get("offer_id"), "type_id": type_id}

        # Exclusion 5: low daily value (only when volume data exists)
        vol_info = volumes.get(type_id, {"daily_volume": 0.0, "daily_value": 0.0})
        daily_volume = vol_info["daily_volume"]
        daily_value = vol_info["daily_value"]
        # 成交量数据缺失时不排除（不等于低成交量，只是从未统计过）
        if daily_volume > 0 and daily_value < 500_000_000:
            return {"excluded": True, "excluded_reason": "low_daily_value",
                    "offer_id": offer.get("offer_id"), "type_id": type_id,
                    "market_buy_price": max_buy, "market_sell_price": min_sell,
                    "daily_volume": daily_volume, "daily_value": daily_value}

        # ── Calculation ──
        quantity = offer.get("quantity", 0)
        lp_cost = offer.get("lp_cost", 1)
        isk_cost = offer.get("isk_cost", 0)

        if lp_cost == 0:
            lp_cost = 1  # 安全兜底，避免除零

        lp_buy_value = (max_buy * quantity - isk_cost) / lp_cost
        lp_sell_value = (min_sell * quantity - isk_cost) / lp_cost

        # Exclusion 6: 异常数据——LP单价超过10000
        if abs(lp_sell_value) > 10000:
            return {"excluded": True, "excluded_reason": "anomalous_lp_value",
                    "offer_id": offer.get("offer_id"), "type_id": type_id,
                    "market_buy_price": max_buy, "market_sell_price": min_sell,
                    "daily_volume": daily_volume, "daily_value": daily_value}

        return {
            "excluded": False,
            "excluded_reason": None,
            "offer_id": offer.get("offer_id"),
            "type_id": type_id,
            "quantity": quantity,
            "lp_cost": lp_cost,
            "isk_cost": isk_cost,
            "market_buy_price": max_buy,
            "market_sell_price": min_sell,
            "daily_volume": daily_volume,
            "daily_value": daily_value,
            "lp_buy_value": round(lp_buy_value, 2),
            "lp_sell_value": round(lp_sell_value, 2),
        }

    def _evaluate_bpc(
        self,
        offer: dict,
        prices: dict[int, dict],
        bpc_details: dict[int, dict],
    ) -> dict:
        """
        评估 BPC 蓝图的 LP 价值：通过成品市价 - 原料成本 - ISK成本 估算。

        公式:
            product_value = product_sell_price × product_quantity
            material_cost  = Σ(material_buy_price × material_quantity)
            lp_profit      = product_value - material_cost - isk_cost
            lp_value       = lp_profit / lp_cost

        排除条件:
            - 无制造产品（SDE 无对应产品）
            - 成品无卖价
            - lp_cost 为 0
        """
        type_id = offer["type_id"]
        details = bpc_details.get(type_id)

        if not details or not details.get("product"):
            return {"excluded": True, "excluded_reason": "is_bpc_no_product",
                    "offer_id": offer.get("offer_id"), "type_id": type_id}

        product_type_id, product_qty = details["product"]
        product_buy = prices.get(product_type_id, {}).get("max_buy", 0.0)
        product_sell = prices.get(product_type_id, {}).get("min_sell", 0.0)
        # 至少有一个价格才能评估
        if product_sell == 0.0 and product_buy == 0.0:
            return {"excluded": True, "excluded_reason": "is_bpc_no_product_price",
                    "offer_id": offer.get("offer_id"), "type_id": type_id}

        # 原料成本（按买价算）
        material_cost = 0.0
        for mat_type_id, mat_qty in details.get("materials", []):
            mat_price = prices.get(mat_type_id, {}).get("max_buy", 0.0)
            material_cost += mat_price * mat_qty

        # ISK / LP 成本
        isk_cost = offer.get("isk_cost", 0)
        lp_cost = offer.get("lp_cost", 1)
        if lp_cost == 0:
            lp_cost = 1

        # 收单价值：成品出给收单(max_buy) - 原料成本 - ISK成本
        buy_profit = product_buy * product_qty - material_cost - isk_cost
        lp_buy_value = buy_profit / lp_cost

        # 出单价值：成品挂单卖出(min_sell) - 原料成本 - ISK成本
        sell_profit = product_sell * product_qty - material_cost - isk_cost
        lp_sell_value = sell_profit / lp_cost

        # 异常数据排除
        if abs(lp_sell_value) > 10000:
            return {"excluded": True, "excluded_reason": "anomalous_lp_value",
                    "offer_id": offer.get("offer_id"), "type_id": type_id}

        quantity = offer.get("quantity", 1)  # BPC runs

        return {
            "excluded": False,
            "excluded_reason": None,
            "offer_id": offer.get("offer_id"),
            "type_id": type_id,
            "quantity": quantity,
            "lp_cost": lp_cost,
            "isk_cost": isk_cost,
            "market_buy_price": round(lp_buy_value, 2),
            "market_sell_price": round(lp_sell_value, 2),
            "daily_volume": 0.0,
            "daily_value": abs(sell_profit),
            "lp_buy_value": round(lp_buy_value, 2),
            "lp_sell_value": round(lp_sell_value, 2),
        }

    @staticmethod
    def _compute_all_items_weighted_avg(evaluated: list[dict]) -> float:
        """
        全部有效物品加权平均 LP 出单价值（lp_sell_value > 0 且 < 3000）。
        """
        valid = [item for item in evaluated
                 if not item.get("excluded")
                 and 0 < item.get("lp_sell_value", 0) < 3000]
        if not valid:
            return 0.0

        total_weight = sum(item.get("daily_value", 0) for item in valid)
        if total_weight == 0:
            return sum(item["lp_sell_value"] for item in valid) / len(valid)

        weighted = sum(item["lp_sell_value"] * item.get("daily_value", 0) for item in valid)
        return round(weighted / total_weight, 2)

    def _aggregate_corp_lp_value(self, evaluated: list[dict], unique_type_ids: set[int]) -> dict:
        """
        取独有物品中流水最高的作为标准 LP 价值，无独有则取共有最高。

        筛选条件: lp_sell_value ∈ (0, 3000)
        排序: 独有优先 → 各自按 daily_value 降序
        """
        if not evaluated:
            return {"lp_buy_value": 0.0, "lp_sell_value": 0.0, "top_items": [], "evaluated_offers": 0}

        # 筛选有效范围
        valid = [i for i in evaluated if 0 < i.get("lp_sell_value", 0) < 3000]
        if not valid:
            return {"lp_buy_value": 0.0, "lp_sell_value": 0.0, "top_items": [], "evaluated_offers": len(evaluated)}

        # 独有优先 → 各自 daily_value 降序
        uniq_valid = [i for i in valid if i["type_id"] in unique_type_ids]
        shared_valid = [i for i in valid if i["type_id"] not in unique_type_ids]
        uniq_valid.sort(key=lambda x: x.get("daily_value", 0), reverse=True)
        shared_valid.sort(key=lambda x: x.get("daily_value", 0), reverse=True)

        # 标准 LP 价值 = 流水最高的独有物品，无独有则用共有
        best = (uniq_valid or shared_valid)[0]

        # 展示用 Top 列表：独有前20 + 共有前20
        top_items = (uniq_valid[:20] + shared_valid[:20])[:20]
        top_type_ids = {item["type_id"] for item in top_items}
        for item in evaluated:
            item["is_in_top"] = item["type_id"] in top_type_ids

        return {
            "lp_buy_value": round(best["lp_buy_value"], 2),
            "lp_sell_value": round(best["lp_sell_value"], 2),
            "top_items": top_items,
            "evaluated_offers": len(evaluated),
        }

    def _evaluate_corporation(
        self,
        corp: dict,
        offers: list[dict],
        prices: dict[int, dict],
        volumes: dict[int, dict],
        bpc_type_ids: set[int],
        bpc_details: dict[int, dict],
        type_names: dict[int, dict],
        unique_type_ids: set[int],
    ) -> dict:
        """
        评估单个军团的LP价值。

        遍历军团所有兑换项，逐项评估并分为"合格"和"排除"两类，
        最后对合格项进行 Top-5 加权聚合。

        Returns:
            dict: 军团完整评估结果（按 plan 定义的输出格式）
        """
        evaluated: list[dict] = []
        excluded: list[dict] = []

        for offer in offers:
            type_id = offer["type_id"]
            # BPC 蓝图走专用评估路径
            if type_id in bpc_type_ids:
                result = self._evaluate_bpc(offer, prices, bpc_details)
            else:
                result = self._calculate_lp_value(offer, prices, volumes, bpc_type_ids)

            # 填入物品名称
            type_id = offer["type_id"]
            names = type_names.get(type_id, {"en": "", "zh": ""})
            result["type_name_en"] = names["en"]
            result["type_name_zh"] = names["zh"]

            if result["excluded"]:
                excluded.append(result)
            else:
                evaluated.append(result)

        aggregation = self._aggregate_corp_lp_value(evaluated, unique_type_ids)

        return {
            "corporation_id": corp["corporationID"],
            "corporation_name": corp.get("name_en", ""),
            "corporation_name_zh": corp.get("name_zh", ""),
            "faction_id": corp.get("factionID"),
            "lp_buy_value": aggregation["lp_buy_value"],
            "lp_sell_value": aggregation["lp_sell_value"],
            "lp_sell_value_all": self._compute_all_items_weighted_avg(evaluated),
            "total_offers": len(offers),
            "evaluated_offers": aggregation["evaluated_offers"],
            "excluded_offers": len(excluded),
            "top_items": aggregation["top_items"],
            "details": evaluated,
            "excluded_details": excluded,
        }
