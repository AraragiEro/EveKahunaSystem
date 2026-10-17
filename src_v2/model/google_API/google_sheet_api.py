import os
import time
from http.client import HTTPException

import google_auth_httplib2
import httplib2
from google.oauth2 import service_account
from googleapiclient import discovery
from googleapiclient.errors import HttpError

from src_v2.core.config.config import config
from src_v2.core.log import logger

class GoogleSheetApi:
    def __init__(self):
        self._server = None

    @staticmethod
    def _has_google_credentials_config() -> bool:
        return "GOOGLE" in config and "CREDENTIALS" in config["GOOGLE"]

    @staticmethod
    def _has_proxy_config() -> bool:
        return (
            "APP" in config
            and "PROXY" in config["APP"]
            and "PORT" in config["APP"]
            and bool(config["APP"]["PROXY"])
            and bool(config["APP"]["PORT"])
        )

    def get_proxy_http(self):
        if not self._has_proxy_config():
            return httplib2.Http()

        # 兼容环境中未安装 socks 扩展导致的 httplib2.socks 为空问题
        if getattr(httplib2, "socks", None) is None:
            logger.warning("检测到 httplib2.socks 为 None，未启用 socks 扩展，忽略代理配置，直接使用直连 Http。"
                          "如需启用代理，请安装 `httplib2[socks]` 依赖。")
            return httplib2.Http()

        proxy = config["APP"]["PROXY"]
        port = int(config["APP"]["PORT"])
        proxy_info = httplib2.ProxyInfo(
            httplib2.socks.PROXY_TYPE_HTTP,
            proxy,
            port
        )
        return httplib2.Http(proxy_info=proxy_info)

    def get_credentials_path(self) -> str:
        if not self._has_google_credentials_config():
            raise KeyError("缺少 GOOGLE.CREDENTIALS 配置")

        credentials_json = config["GOOGLE"]["CREDENTIALS"]
        if not credentials_json:
            raise ValueError("GOOGLE.CREDENTIALS 不能为空")
        return os.path.abspath(credentials_json)

    def get_credentials(self):
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials_json = self.get_credentials_path()
        credentials = service_account.Credentials.from_service_account_file(
            credentials_json,
            scopes=scopes
        )
        return credentials

    def get_service(self):
        credential = self.get_credentials()
        http_proxy = self.get_proxy_http()

        authorize_http = google_auth_httplib2.AuthorizedHttp(credential, http=http_proxy)
        service = discovery.build("sheets", "v4", http=authorize_http, cache_discovery=False)

        return service

    def reload_service(self):
        self._server = None

    @staticmethod
    def _is_retryable_exception(exc: Exception) -> bool:
        if isinstance(exc, (BrokenPipeError, TimeoutError, ConnectionError, OSError, HTTPException)):
            return True
        if isinstance(exc, HttpError) and exc.resp is not None:
            return int(exc.resp.status) >= 500
        return "Broken pipe" in str(exc)

    def execute_with_retry(self, request_builder, retries: int = 2, retry_interval: float = 0.6):
        """
        统一执行 Google API 请求，遇到短暂连接问题自动重建并重试。

        request_builder: callable(service) -> googleapiclient request
        """
        last_error: Exception | None = None
        max_attempt = retries + 1
        for attempt in range(1, max_attempt + 1):
            try:
                request = request_builder(self.server)
                return request.execute()
            except Exception as exc:
                last_error = exc
                if not self._is_retryable_exception(exc) or attempt >= max_attempt:
                    raise
                logger.warning(
                    f"google api request failed (attempt {attempt}/{max_attempt}), retrying: {exc}"
                )
                self.reload_service()
                time.sleep(retry_interval * attempt)
        if last_error is not None:
            raise last_error

    @property
    def server(self):
        try:
            if self._server is None:
                self._server = self.get_service()
            return self._server
        except Exception as e:
            logger.error(f"get_server error: {e}")
            raise


google_sheet_api = GoogleSheetApi()
