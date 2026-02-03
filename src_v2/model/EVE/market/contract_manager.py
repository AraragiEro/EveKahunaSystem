from datetime import datetime, timezone

from src_v2.core.config.config import config
from src_v2.core.database.kahuna_database_utils_v2 import EveCorporationContractDBUtils
from src_v2.core.log import logger
from src_v2.core.utils import tqdm_manager
from src_v2.model.EVE.character.character_manager import CharacterManager
from src_v2.model.EVE.eveesi.esi_api.contracts import (
    corporations_corporation_contracts,
    corporations_corporation_contracts_contract_id_items,
)


class ContractManager():
    def __init__(self):
        pass

    async def refresh_alliance_contracts(self, alliance_id: int = 99003581):
        # 检查配置文件是否配置基础设施权限角色id
        infrastructure_role_id = config.getint(
            'EVE', 'INFRASTRUCTURE_CHARACTER_ID')
        if not infrastructure_role_id:
            logger.warning(f"配置文件未配置基础设施权限角色id")
            logger.warning(f"联盟合同刷新跳过。")
            return

        # 通过id获取角色
        try:
            character_manager = CharacterManager()
            character = await character_manager.get_character_by_character_id(infrastructure_role_id)
        except Exception as e:
            logger.error(f"获取基础设施权限角色失败: {e}")
            logger.warning(f"联盟合同刷新跳过。")
            return
    
        contract_price_cache = {}

        # 获取联盟合同
        contracts = await corporations_corporation_contracts(character.ac_token, character.corporation_id)
        # 展开
        c1 = []
        for contract_list in contracts:
            c1.extend(contract_list)
        # 筛选联盟合同，当前只考虑大宗货物和plex等通货
        capital = [
            con for con in c1
            if con['status'] == 'outstanding'
            and con['assignee_id'] == 99003581
            and con['volume'] > 10000000
        ]
        capital = capital
        small = [
            con for con in c1
            if con['status'] == 'outstanding'
            and con['assignee_id'] == 99003581
            and con['volume'] < 1
        ]
        small = small

        await tqdm_manager.add_mission(f'refresh_alliance_capital_contracts_{alliance_id}', len(capital))
        for contract in capital:
            if (contract['issuer_id'], contract['price']) in contract_price_cache:
                items = contract_price_cache[(contract['issuer_id'], contract['price'])]
            else:
                items = await corporations_corporation_contracts_contract_id_items(character.ac_token, character.corporation_id, contract['contract_id'])
                if items is None:
                    items = []
                contract_price_cache[(contract['issuer_id'], contract['price'])] = items
            contract['contract_item'] = items
            contract['item_typeids'] = list(
                set([item['type_id'] for item in items]))
            await tqdm_manager.update_mission(f'refresh_alliance_capital_contracts_{alliance_id}', 1)
        await tqdm_manager.complete_mission(f'refresh_alliance_capital_contracts_{alliance_id}')

        await tqdm_manager.add_mission(f'refresh_alliance_small_contracts_{alliance_id}', len(small))
        for contract in small:
            if(contract['issuer_id'], contract['price']) in contract_price_cache:
                items = contract_price_cache[(contract['issuer_id'], contract['price'])]
            else:
                items = await corporations_corporation_contracts_contract_id_items(character.ac_token, character.corporation_id, contract['contract_id'])
                if items is None:
                    items = []
                contract_price_cache[(contract['issuer_id'], contract['price'])] = items
            contract['contract_item'] = items
            contract['item_typeids'] = list(
                set([item['type_id'] for item in items]))
            await tqdm_manager.update_mission(f'refresh_alliance_small_contracts_{alliance_id}', 1)
        await tqdm_manager.complete_mission(f'refresh_alliance_small_contracts_{alliance_id}')

        # 清理数据库，批量入库
        try:
            # 先清空表
            logger.info("开始清空合同表...")
            await EveCorporationContractDBUtils.delete_all()
            logger.info("合同表清空完成")

            # 转换合同数据格式并批量入库
            def convert_contract_to_db_row(contract: dict) -> dict:
                """将API返回的合同数据转换为数据库行格式"""
                def parse_datetime(dt_str):
                    """解析ISO格式的日期时间字符串"""
                    if not dt_str:
                        return None
                    if isinstance(dt_str, datetime):
                        dt = dt_str
                    else:
                        # 处理带 Z 的 ISO 字符串
                        dt_str = dt_str.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(dt_str)
                    # 如果是 offset-aware，转换为 UTC 后移除时区信息
                    if dt.tzinfo is not None:
                        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                    return dt

                row = {
                    "acceptor_id": contract.get("acceptor_id"),
                    "assignee_id": contract.get("assignee_id"),
                    "availability": contract.get("availability"),
                    "contract_id": contract.get("contract_id"),
                    "date_expired": parse_datetime(contract.get("date_expired")),
                    "date_issued": parse_datetime(contract.get("date_issued")),
                    "for_corporation": contract.get("for_corporation"),
                    "issuer_corporation_id": contract.get("issuer_corporation_id"),
                    "issuer_id": contract.get("issuer_id"),
                    "status": contract.get("status"),
                    "type": contract.get("type"),
                    "buyout": contract.get("buyout"),
                    "collateral": contract.get("collateral"),
                    "date_accepted": parse_datetime(contract.get("date_accepted")),
                    "date_completed": parse_datetime(contract.get("date_completed")),
                    "days_to_complete": contract.get("days_to_complete"),
                    "end_location_id": contract.get("end_location_id"),
                    "price": contract.get("price"),
                    "reward": contract.get("reward"),
                    "start_location_id": contract.get("start_location_id"),
                    "title": contract.get("title"),
                    "volume": contract.get("volume"),
                    "contract_item": contract.get("contract_item", {}),
                    "item_typeids": contract.get("item_typeids"),
                }
                return row

            # 合并所有合同（大宗商品和小型商品）
            all_contracts = capital + small

            if all_contracts:
                # 转换为数据库行格式
                db_rows = [convert_contract_to_db_row(
                    contract) for contract in all_contracts]

                # 批量插入（表已清空，直接插入即可）
                await EveCorporationContractDBUtils.insert_many(rows_list=db_rows)

                logger.info(
                    f"成功入库 {len(db_rows)} 个合同（大宗: {len(capital)}, 小型: {len(small)}）")
            else:
                logger.info("没有需要入库的合同")

        except Exception as e:
            logger.error(f"合同入库失败: {e}", exc_info=True)
            raise


contract_manager = ContractManager()
