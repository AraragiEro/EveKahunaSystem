from datetime import datetime, timedelta
from cachetools import TTLCache

from .common import api
from .common.client_utils import excol as excol
from .common.spreadsheets import Spreadsheets
from .common.client_utils import (get_spreadsheet_token_by_name)
from ..log_server.kahuna_logger import logger

class LinkShareEntity():
    tenant_readable = 'tenant_readable'
    tenant_editable = 'tenant_editable'
    partner_tenant_readable = 'partner_tenant_readable'
    partner_tenant_editable = 'partner_tenant_editable'
    anyone_readable = 'anyone_readable'
    anyone_editable = 'anyone_editable'
    closed = 'closed'

class FileType():
    DOC = "doc"  # 旧版文档
    SHEET = "sheet"  # 电子表格
    FILE = "file"  # 云空间文件
    WIKI = "wiki"  # 知识库节点
    BITABLE = "bitable"  # 多维表格
    DOCX = "docx"  # 新版文档
    MINDNOTE = "mindnote"  # 思维笔记
    MINUTES = "minutes"  # 妙记
    SLIDES = "slides"  # 幻灯片


class FeiShuClient:
    api = None
    secret_id = None
    _access_token = None
    expire_time = 0
    _folder_token = None
    cache = TTLCache(maxsize=10, ttl=15 * 60)
    sheet_info_cache = TTLCache(maxsize=10, ttl=15 * 60)
    sheet_query_cache = TTLCache(maxsize=10, ttl=15 * 60)

    def __init__(self, app_id, secret_id):
        self.app_id = app_id
        self.secret_id = secret_id
        try:
            self.get_access_token()
        except Exception as e:
            logger.error(f"飞书 get_access_token error: {e}")

    def get_access_token(self):
        res = api.post_tenant_access_token(self.app_id, self.secret_id)
        self._access_token = res['tenant_access_token']
        self.expire_time = datetime.now() + timedelta(seconds=res['expire'])

    @property
    def access_token(self):
        if datetime.now() > self.expire_time:
            self.get_access_token()
        return self._access_token

    @property
    def folder_token(self):
        if not self._folder_token:
            raise Exception("folder_token is empty.")
        return self._folder_token

    def set_folder_token(self, folder_token):
        self._folder_token = folder_token

    """ == api == """
    def get_spreadsheets(self, sheet_name: str):
        sheet_token = get_spreadsheet_token_by_name(self.access_token, self.folder_token, sheet_name)

        spreadsheets = Spreadsheets(self, sheet_token)
        return spreadsheets

    def create_spreadsheets(self, title: str, ignore_exist: bool = False):
        if not ignore_exist:
            try:
                return self.get_spreadsheets(title)
            except Exception:
                pass

        res = api.post_sheets_v3_spreadsheets(self.access_token, title, self.folder_token)

        spreadsheet = Spreadsheets(self, res['data']['spreadsheet']['spreadsheet_token'])
        return spreadsheet
