# Google Sheet 模块接入说明（`src_v2/model/google_API`）

## 1. 模块现状概览

`src_v2/model/google_API` 目前包含以下文件：

- `google_sheet_api.py`：封装 Google Sheets API 连接与鉴权。
- `googlesheet_kahuna.py`：封装业务级写表逻辑（市场监视器数据刷新）。
- `__init__.py`：导出 `google_sheet_api` 与 `kahuna_google_market_monitor`。

该模块已按当前仓库完成适配，配置读取方式与 `src_v2/core/config/config.py` 一致。

---

## 2. 当前项目的配置文件适配方式

当前仓库配置入口是根目录 `config.toml`，由 `src_v2/core/config/config.py` + `src_v2/core/config/toml_config.py` 读取。

### 2.1 需要新增的配置节

请在 `config.toml` 增加 `GOOGLE` 配置节（若已存在则补齐字段）：

```toml
[GOOGLE]
# Google Cloud 服务账号密钥 JSON 文件路径（建议绝对路径或相对项目根目录路径）
CREDENTIALS = "credentials/google-service-account.json"

# 目标 Google Sheet 的 spreadsheetId（不是完整 URL）
MARKET_MONITOR_SPREADSHEET_ID = "1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 2.2 代理配置说明

`google_sheet_api.py` 支持读取：

- `APP.PROXY`
- `APP.PORT`

并通过 `httplib2.ProxyInfo` 走 HTTP 代理访问 Google API。

如果配置了代理，则需保证：

1. `config.toml` 中 `[APP]` 的代理地址和端口可用；
2. 该代理可访问 `googleapis.com`。

如果不配置代理，模块会自动走直连。

---

## 3. 需要的配置文件与部署方式

## 3.1 必需文件

- `config.toml`：包含 `[GOOGLE]`、`[APP]` 的相关字段。
- Google 服务账号密钥文件（JSON）：例如 `credentials/google-service-account.json`。

## 3.2 Python 依赖

仓库 `requirements.txt` 已包含 Google 相关依赖：

- `google_api_python_client`
- `google_auth_httplib2`
- `httplib2`

部署时执行（PowerShell）：

```powershell
pip install -r requirements.txt
```

## 3.3 部署步骤（Windows/PowerShell）

1. 在项目根目录创建密钥目录（示例）：

```powershell
New-Item -ItemType Directory -Force credentials
```

2. 将 Google 服务账号 JSON 放入该目录。
3. 更新 `config.toml` 的 `[GOOGLE]` 配置。
4. 确认目标 Google Sheet 已共享给服务账号邮箱（至少编辑权限）。
5. 启动项目后调用测试接口（见第 5 节）验证联通性。

---

## 4. 当前暴露的接口与使用方法

## 4.1 低层 API 封装

文件：`src_v2/model/google_API/google_sheet_api.py`

模块级实例：`google_sheet_api`

主要接口：

- `google_sheet_api.get_proxy_http()`：创建带代理的 `httplib2.Http`。
- `google_sheet_api.get_credentials()`：读取服务账号 JSON 并创建凭据。
- `google_sheet_api.get_service()`：构建 Google Sheets v4 service。
- `google_sheet_api.server`（property）：每次访问返回一个可用 service。

使用示例：

```python
from src_v2.model.google_API.google_sheet_api import google_sheet_api

service = google_sheet_api.server
resp = service.spreadsheets().values().get(
    spreadsheetId="<你的spreadsheetId>",
    range="Sheet1!A1:B10"
).execute()
print(resp)
```

## 4.2 业务层封装（市场监视器）

文件：`src_v2/model/google_API/googlesheet_kahuna.py`

模块级实例：`kahuna_google_market_monitor`

当前公开方法：

- `test_google_sheet_api(spreadsheet_id=None)`：向 `欢迎！先看这里!A18` 写入测试数据。
- `read_range(range_name, spreadsheet_id=None)`：读取指定区域数据。
- `write_range(range_name, values, spreadsheet_id=None, clear_first=False)`：写入指定区域数据。
- `write_data_to_monitor(spreadsheet_id, data)`：清空“市场”后批量写入。
- `refresh_market_monitor(market_rows, b9_rows=None, spreadsheet_id=None)`：按固定模板刷新市场监视器三个区域。
- `refresh_market_monitor_process(market_rows, b9_rows=None, force=False, hour_interval=2, spreadsheet_id=None)`：带并发锁和时间窗口控制的刷新入口。

调用示例：

```python
from src_v2.model.google_API.googlesheet_kahuna import kahuna_google_market_monitor

# 异步上下文中调用
await kahuna_google_market_monitor.refresh_market_monitor_process(
    market_rows=[["typeID", "name"], [34, "Tritanium"]],
    b9_rows=[["id", "type_id", "price"], [1, 34, 5.01]],
    force=True,
)
```

---

## 5. Google API 密钥文件获取与使用说明

## 5.1 获取流程（服务账号）

1. 进入 Google Cloud Console，创建/选择一个项目。
2. 启用 API：`Google Sheets API`。
3. 在 `IAM & Admin -> Service Accounts` 创建服务账号。
4. 在该服务账号下创建 `JSON` 类型密钥并下载。

下载后的 JSON 即本模块所需密钥文件。

## 5.2 使用方式

1. 将 JSON 放到项目可访问路径（建议 `credentials/`）。
2. 在 `config.toml` 的 `[GOOGLE].CREDENTIALS` 填写该文件路径。
3. 打开目标 Google Sheet，将服务账号邮箱（通常是 `xxx@xxx.iam.gserviceaccount.com`）加入共享。
4. 赋予“编辑者”权限，否则写入会报 `403`。

## 5.3 安全建议

- 不要把密钥 JSON 提交到 Git 仓库。
- 建议将 `credentials/` 加入 `.gitignore`。
- 线上建议使用受控目录和最小权限账号。

---

## 6. 说明

当前模块已移除旧项目中的强耦合市场依赖（旧版 `sde_service/market_server/database_server` 路径），并保留为通用 Google Sheet 读写能力 + 轻量市场监视器写入封装。若后续需要恢复“自动拉市场数据并写表”，建议在当前仓库中新增独立数据组装层，再调用 `refresh_market_monitor` 写入。
