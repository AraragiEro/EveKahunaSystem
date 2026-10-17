import asyncio
from datetime import datetime, timedelta
from typing import Any

from src_v2.core.config.config import config
from src_v2.core.log import logger
from src_v2.core.utils import get_beijing_utctime

from .google_sheet_api import google_sheet_api


class KahunaGoogleSheetManager:
    """Google Sheet 读写管理器（适配当前项目配置体系）"""

    def __init__(self):
        self.refresh_running = asyncio.Lock()
        self.sheet_api_test = False
        self._last_refresh_time: datetime | None = None

    @staticmethod
    def _get_market_spreadsheet_id() -> str:
        if "GOOGLE" not in config or "MARKET_MONITOR_SPREADSHEET_ID" not in config["GOOGLE"]:
            raise KeyError("缺少 GOOGLE.MARKET_MONITOR_SPREADSHEET_ID 配置")
        spreadsheet_id = config["GOOGLE"]["MARKET_MONITOR_SPREADSHEET_ID"]
        if not spreadsheet_id:
            raise ValueError("GOOGLE.MARKET_MONITOR_SPREADSHEET_ID 不能为空")
        return spreadsheet_id

    @staticmethod
    def _resolve_spreadsheet_id(spreadsheet_id: str | None) -> str:
        return spreadsheet_id or KahunaGoogleSheetManager._get_market_spreadsheet_id()

    def test_google_sheet_api(self, spreadsheet_id: str | None = None):
        spreadsheet_id = self._resolve_spreadsheet_id(spreadsheet_id)
        now_str = get_beijing_utctime(datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

        try:
            server = google_sheet_api.server
            server.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "data": [
                        {
                            "majorDimension": "ROWS",
                            "range": "欢迎！先看这里!A18",
                            "values": [["链接测试", now_str]],
                        }
                    ],
                    "valueInputOption": "USER_ENTERED",
                },
            ).execute()
            self.sheet_api_test = True
        except Exception as e:
            logger.error(f"google sheet 测试失败: {e}", exc_info=True)
            raise

    def read_range(self, range_name: str, spreadsheet_id: str | None = None) -> list[list[Any]]:
        spreadsheet_id = self._resolve_spreadsheet_id(spreadsheet_id)
        server = google_sheet_api.server
        resp = server.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        ).execute()
        return resp.get("values", [])

    def write_range(
        self,
        range_name: str,
        values: list[list[Any]],
        spreadsheet_id: str | None = None,
        clear_first: bool = False,
        value_input_option: str = "USER_ENTERED",
    ):
        spreadsheet_id = self._resolve_spreadsheet_id(spreadsheet_id)
        server = google_sheet_api.server

        if clear_first:
            server.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=range_name,
            ).execute()

        server.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "data": [
                    {
                        "majorDimension": "ROWS",
                        "range": range_name,
                        "values": values,
                    }
                ],
                "valueInputOption": value_input_option,
            },
        ).execute()

    def write_data_to_monitor(self, spreadsheet_id: str, data: dict[str, Any]):
        server = google_sheet_api.server
        try:
            server.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range="市场",
            ).execute()
        except Exception as e:
            logger.error(f"清空 google sheet 市场 失败: {e}", exc_info=True)
            raise

        try:
            server.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=data,
            ).execute()
        except Exception as e:
            logger.error(f"写入 googlesheet 市场 失败: {e}", exc_info=True)
            raise

    async def refresh_market_monitor(
        self,
        market_rows: list[list[Any]],
        b9_rows: list[list[Any]] | None = None,
        spreadsheet_id: str | None = None,
    ):
        spreadsheet_id = self._resolve_spreadsheet_id(spreadsheet_id)
        now_str = get_beijing_utctime(datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        if b9_rows is None:
            b9_rows = []

        data = {
            "data": [
                {
                    "majorDimension": "ROWS",
                    "range": "市场",
                    "values": market_rows,
                },
                {
                    "majorDimension": "ROWS",
                    "range": "欢迎！先看这里!A17",
                    "values": [["最后更新:", now_str]],
                },
                {
                    "majorDimension": "ROWS",
                    "range": "B-9订单数据",
                    "values": b9_rows,
                },
            ],
            "valueInputOption": "USER_ENTERED",
        }
        self.write_data_to_monitor(spreadsheet_id, data)
        self._last_refresh_time = datetime.now()

    async def refresh_market_monitor_process(
        self,
        market_rows: list[list[Any]],
        b9_rows: list[list[Any]] | None = None,
        force: bool = False,
        hour_interval: int = 2,
        spreadsheet_id: str | None = None,
    ):
        if self.refresh_running.locked():
            return

        async with self.refresh_running:
            if not self.sheet_api_test:
                self.test_google_sheet_api(spreadsheet_id=spreadsheet_id)
                if not self.sheet_api_test:
                    logger.error("google_sheet_api test not pass.")
                    return

            if not force and self._last_refresh_time is not None:
                if datetime.now() - self._last_refresh_time < timedelta(hours=hour_interval):
                    return

            await self.refresh_market_monitor(
                market_rows=market_rows,
                b9_rows=b9_rows,
                spreadsheet_id=spreadsheet_id,
            )


kahuna_google_market_monitor = KahunaGoogleSheetManager()
