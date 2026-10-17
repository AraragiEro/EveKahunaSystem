# 🌟 Kahuna System 🌟

![Logo](https://github.com/user-attachments/assets/40c09a45-f898-4167-9315-20df6a1dc59a)

[![开发状态](https://img.shields.io/badge/状态-开发中-yellow)](https://github.com/AraragiEro/EveKahunaSystem)
[![EVE Online](https://img.shields.io/badge/游戏-EVE%20Online-blue)](https://www.eveonline.com/)
[![Quart](https://img.shields.io/badge/框架-Quart-green)](https://github.com/AstrBotDevs/AstrBot.git)
[![Vue3](https://img.shields.io/badge/框架-Vue3-green)](https://github.com/AstrBotDevs/AstrBot.git)

_Kahuna认为bot已经无法满足搓牛角包需要的庞大计算量_

_又一座新的**X**山拔地而起！！！_

🥰 _爱来自 凛冬联盟群 紫竹梅重工_

![sty](https://github.com/user-attachments/assets/f37a6a06-b925-4836-8561-282720f06506)

</div>

基于 Quart 和 Vue3 的 EVE Online 一体化 Web 应用平台，为玩家提供市场价格查询、成本计算、工业规划等综合服务。

## 项目简介

Kahuna System 是一个专为 EVE Online 玩家设计的 Web 应用平台，集成了市场数据分析、工业制造规划、资产统计等核心功能。平台采用现代化的前后端分离架构，提供直观的用户界面和强大的计算能力。

## 核心功能

- **自选市场价格查询与利润成本分析** - 支持吉他和联盟市场实时价格查询
  - <img width="2560" height="1271" alt="image" src="https://github.com/user-attachments/assets/dd98f790-af19-484d-b43e-c82588a6bd88" />
- **成本计算** - 精确计算制造和采购成本
  - <img width="2560" height="1271" alt="image" src="https://github.com/user-attachments/assets/5c45aac0-fd2e-4bfd-b5ff-57085d4eca11" />
- **工业规划** - 智能工业制造规划与报表输出
  - <img width="2560" height="1271" alt="image" src="https://github.com/user-attachments/assets/559e5711-62b4-42e0-867e-2687d587574c" />
  - <img width="2560" height="1271" alt="image" src="https://github.com/user-attachments/assets/a3409290-7c64-42a8-a800-870d3172d45a" />
- **化矿分析** - 矿石精炼与材料分析
  - <img width="2560" height="1271" alt="landing-page-化矿计算" src="https://github.com/user-attachments/assets/9f98ee62-9211-49e6-9377-b6305954840f" />
- **采购清单** - 可自定义数据来源的采购清单管理
  - <img width="2560" height="1271" alt="image" src="https://github.com/user-attachments/assets/6c1eb759-f83a-4c7f-b4e0-e899d865807b" />
- **挂单分析** - 市场订单分析与优化建议【**计划中**】
- **资产统计** - 角色和公司资产统计与管理【**计划中**】

## 技术栈

- **后端**: Quart (Python 3.13+), Hypercorn
- **前端**: Vue 3, TypeScript, Element Plus, ECharts
- **数据库**: SQLite / PostgreSQL, Neo4j, Redis
- **MCP 中间件**: FastMCP (Model Context Protocol)
- **其他**: ESI API, OAuth2

## 快速开始

### 方式一：Docker Compose 一键部署（推荐）

使用 Docker Compose 可以快速部署完整的 KahunaSystem，无需安装 Python 和 Node.js。

#### 1. 克隆项目

```bash
git clone https://github.com/AraragiEro/EveKahunaSystem.git
cd EveKahunaSystem
```

#### 2. 启动数据库服务

```bash
cd docker_database
cp docker-compose.yml.example docker-compose.yml
docker compose up -d
cd ..
```

这套 compose 会启动 4 个服务，宿主端口映射如下（供下一步 `config.toml` 使用）：

| 服务 | 容器 | 宿主端口 | 库 / 说明 |
|---|---|---|---|
| PostgreSQL（主库） | kahunaSystemPostgreDatabase | **6201** | 库 `kahunabot`，账号密码均为 `kahunabot` |
| PostgreSQL（SDE 库） | kahunaSystemSdeDatabase | **6202** | 库 `sde`，由 `update_sde.py` 写入 |
| Redis | KahunaSystemRedis | **6203** | |
| Neo4j | KahunaSystemNeo4j | **7687** / 7474 | 由 `init_neo4j.py` 写入图数据 |

> 数据库是**必需**的：服务启动时会初始化 PostgreSQL、Redis、Neo4j，缺任何一项都会启动失败。

#### 3. 配置应用

```bash
# 从模板创建配置文件（必须放在项目根目录）
cp docker/config.toml.docker config.toml
```

然后编辑 `config.toml`，至少确认以下几项（其余项含义见「主要配置项」一节）：

```toml
[EDITION]
# 开源（社区）版固定为 community
Edition = "community"

[APP]
# 必填：应用签名密钥（≥32 位随机串）
# 生成：python -c "import secrets;print(secrets.token_urlsafe(32))"
# ⚠️ 保留模板占位符（change-me-*）时生产模式会直接拒绝启动
SECRET_KEY = "生成的随机密钥"

[POSTGREDB]
Host = "172.17.0.1"      # 应用在容器内，连宿主机映射端口
Port = 6201
Database = "kahunabot"
User = "kahunabot"
Password = "kahunabot"

[SDEDB]
Host = "172.17.0.1"
Port = 6202
Database = "sde"
User = "kahunabot"
Password = "kahunabot"

[REDIS]
Host = "172.17.0.1"
Port = 6203

[NEO4J]
Host = "172.17.0.1"
Port = 7687
Username = "neo4j"
Password = "你的Neo4j密码"

[EVE]
CLIENT_ID = "你的客户端ID"
SECRET_KEY = "你的ESI密钥"
CALLBACK_LOCAL_HOST = "localhost:9527/"
```

> `Host` 填宿主机地址：Linux 一般用 Docker 网桥 `172.17.0.1`，Windows/macOS 可用 `host.docker.internal`。
> 数据库容器与应用容器不在同一 Docker 网络时，不能用容器名互访，只能走宿主机映射端口。
> `[ADMIN]` 默认管理员账号是可选功能，需要时按 [docker/README.md](docker/README.md) 填写账号与 ≥12 位口令。

#### 4. 启动 KahunaSystem

```bash
cd docker
cp docker-compose.yml.example docker-compose.yml
docker compose up -d --build
```

首次构建需要拉取基础镜像并安装 npm / Python 依赖，通常 5–10 分钟；国内网络可参考 [docker/README.md](docker/README.md) 配置 npm 镜像源再构建。

#### 5. 访问服务

- Web 界面: http://localhost:9527
- MCP 端点: http://localhost:9274/sse

更多 Docker 部署细节请参考 [docker/README.md](docker/README.md)。

---

### 方式二：手动安装

#### 环境要求

- **Python 3.13**（`pyproject.toml` 锁定 `>=3.13,<3.14`，Python 3.14 暂不兼容）
- **Node.js 20.19+ 或 22.12+**（Vite 7 的硬性要求；Node 18 无法完成前端构建）
- **数据库**：PostgreSQL（主库 + SDE 库）、Redis、Neo4j —— 三者均为必需，缺任何一项服务都无法启动

#### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/AraragiEro/EveKahunaSystem.git
cd EveKahunaSystem
```

2. **安装后端依赖**

使用 `uv`
```bash
uv sync
```

3. **安装前端依赖**

```bash
cd src_v2/frontend
npm install
```

4. **创建配置文件**

```bash
cp config.toml.example config.toml
```

按「主要配置项」一节填写 `[APP] SECRET_KEY`、数据库连接与 `[EVE]`；`[APP] SECRET_KEY` 必须是 ≥32 位随机串，否则生产模式会拒绝启动。

5. **准备 SDE 数据库**

参考 [手动创建 SDE 数据库](#手动创建-sde-数据库) 一节，再用 `python update_sde.py` 导入 SDE 数据。

6. **配置 EVE API**

前往 [EVE Online 开发者中心](https://developers.eveonline.com/) 创建应用，获取 `CLIENT_ID` 和 `SECRET_KEY`。

7. **启动服务**

开发模式:
```bash
python run_server.py --dev --host 0.0.0.0 --port 9527
```

生产模式:
```bash
# 先构建前端
cd src_v2/frontend
npm run build
cd ../..

# 启动服务
python run_server.py --prod --host 0.0.0.0 --port 9527
```

或使用提供的脚本 (Linux/macOS):
```bash
./run_server.sh dev    # 开发模式
./run_server.sh start  # 生产模式
./run_server.sh stop   # 停止服务
```

启动成功后，访问 `http://localhost:9527` 即可使用平台。

**启动 MCP 中间件服务（可选，用于 Astrbot 集成）**:
```bash
# 启动 MCP 服务
./run_server.sh start-mcp

# 查看服务状态
./run_server.sh status

# 停止所有服务
./run_server.sh stop-all
```

## 数据库部署

### 使用 Docker 部署数据库服务

推荐使用 Docker Compose 快速部署 PostgreSQL、Redis 和 Neo4j 数据库。

#### 使用仓库内置的数据库 Compose

推荐直接用仓库里的 `docker_database/docker-compose.yml.example` —— 它包含主库、SDE 库、Redis、Neo4j 四个服务，无需自己手写：

```bash
cd docker_database
cp docker-compose.yml.example docker-compose.yml
docker compose up -d
```

端口映射与默认账号（与 `config.toml` 的数据库段一一对应）：

| 服务 | 容器名 | 宿主端口 | 库 / 账号 |
|---|---|---|---|
| PostgreSQL 主库 | kahunaSystemPostgreDatabase | 6201 | `kahunabot` / `kahunabot` |
| PostgreSQL SDE 库 | kahunaSystemSdeDatabase | 6202 | `sde` / `kahunabot` |
| Redis | KahunaSystemRedis | 6203 | 无密码（可在 `config.toml` 的 `[REDIS] Password` 设置） |
| Neo4j | KahunaSystemNeo4j | 7687 / 7474 | `neo4j` / 自定义密码 |

> 需要改端口时，改 compose 的 `ports` 后同步更新 `config.toml`。
> 想接入已有的 PostgreSQL / Redis / Neo4j 实例也可以，跳过本节直接改 `config.toml`。

#### 启动数据库服务

```bash
# 启动服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f
```

#### 停止数据库服务

```bash
# 停止服务（保留数据）
docker compose stop

# 停止并删除容器（保留数据卷）
docker compose down

# 停止并删除容器及数据卷（⚠️ 警告：会删除所有数据）
docker compose down -v
```

#### 数据持久化

数据会保存在 Docker 卷中，即使删除容器也不会丢失数据。卷的位置可以通过以下命令查看：

```bash
docker volume ls
docker volume inspect <volume_name>
```

#### 安装 Neo4j APOC 插件
##### 下载 APOC 插件

1. 访问 [APOC GitHub Releases](https://github.com/neo4j/apoc/releases) 页面
2. 下载与 Neo4j 版本匹配的 APOC 插件（版本 2025.10.1）：
   - 直接下载链接：https://github.com/neo4j/apoc/releases/download/2025.10.1/apoc-2025.10.1-core.jar
   - 或使用 wget/curl 下载：
     ```bash
     wget https://github.com/neo4j/apoc/releases/download/2025.10.1/apoc-2025.10.1-core.jar -O ./neo4j_plugins/apoc-2025.10.1-core.jar
     ```

##### 安装步骤

1. **将下载的 jar 文件放到映射的 plugins 文件夹内**：
   ```bash
   # 创建插件目录（如果不存在）
   mkdir -p ./neo4j_plugins
   
   # 将下载的 apoc-2025.10.1-core.jar 文件放到该目录
   # 确保文件路径为：./neo4j_plugins/apoc-2025.10.1-core.jar
   ```

2. **重启 Neo4j 容器**使插件生效：
   ```bash
   docker compose restart neo4j
   ```

3. **验证插件是否安装成功**（可选）：
   
   使用 Neo4j Browser（访问 http://localhost:7474）或 cypher-shell 执行：
   ```cypher
   CALL apoc.help("path");
   ```
   
   有返回信息无报错即安装成功

##### 注意事项

- APOC 插件版本必须与 Neo4j 版本匹配（2025.10.1）
- 确保 `neo4j_plugins` 目录已正确映射到容器内的 `/plugins` 目录
- 首次启动 Neo4j 后，建议修改默认密码（通过 `NEO4J_AUTH` 环境变量或首次登录后修改）
- 如果插件未生效，检查容器日志：`docker compose logs neo4j`


#### 配置说明

启动数据库后，在 `config.toml` 中填入对应连接信息（端口以 `docker_database/docker-compose.yml` 的映射为准）：

```toml
[POSTGREDB]
Host = "localhost"   # 应用在宿主机时填 localhost；应用在容器内要填宿主机地址（如 172.17.0.1）
Port = 6201
Database = "kahunabot"
User = "kahunabot"
Password = "kahunabot"

[REDIS]
Host = "localhost"
Port = 6203
Password = ""        # docker_database 默认不设密码；自建实例有密码就填这里

[NEO4J]
Host = "localhost"
Port = 7687
Username = "neo4j"
Password = "你的Neo4j密码"

[SDEDB]
Host = "localhost"
Port = 6202          # SDE 是独立数据库（对应 postgres-sde 服务）
Database = "sde"
User = "kahunabot"
Password = "kahunabot"
```

**注意**：应用跑在 Docker 容器内时，`Host` 必须填宿主机地址 —— 容器里的 `localhost` 指的是容器自己，连不到宿主机的数据库。

**注意**：SDE 数据库使用前需要初始化，见下方「数据库初始化脚本」章节。

## 数据库迁移

项目使用自动化数据库迁移系统，支持完整的生命周期管理：

- **首次安装** - 自动创建所有表
- **模型变更** - 自动检测并迁移
- **版本历史** - 记录所有变更
- **一键回滚** - 出现问题时恢复

### 自动迁移

应用启动时会自动检测并执行迁移：

```python
from src_v2.core import init_database

# 正常启动，自动检测并执行迁移
await init_database()
```

### CLI 工具

```bash
# 预览即将执行的变更（dry-run）
python -m src_v2.core.database.migration_cli --dry-run

# 执行迁移
python -m src_v2.core.database.migration_cli

# 查看迁移历史
python -m src_v2.core.database.migration_cli --history

# 回滚上次迁移
python -m src_v2.core.database.migration_cli --rollback

# 开发模式（自动确认所有变更）
python -m src_v2.core.database.migration_cli --dev
```

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MIGRATION_DRY_RUN` | 仅预览不执行 | `false` |
| `MIGRATION_AUTO_CONFIRM` | 自动确认中等风险变更 | `false` |
| `POSTGRES_HOST` | PostgreSQL 主机 | `localhost` |
| `POSTGRES_PORT` | PostgreSQL 端口 | `5432` |
| `POSTGRES_DB` | 数据库名 | `kahunabot` |
| `POSTGRES_USER` | 用户名 | `kahunabot` |
| `POSTGRES_PASSWORD` | 密码 | `kahunabot` |

### 迁移行为

#### 🟢 自动执行（安全变更）
- 新增表
- 新增列

#### 🟡 需确认（中等风险）
- 删除列（会备份数据）
- 修改列类型
- 修改 NULL 约束

#### 🔴 需人工处理（危险操作）
- 删除表
- 修改主键
- 大规模数据迁移

### 生产环境迁移建议

1. **备份数据**
   ```bash
   pg_dump -h localhost -U kahunabot kahunabot > backup.sql
   ```

2. **Dry-run 预览**
   ```bash
   MIGRATION_DRY_RUN=true python -m src_v2.core.database.migration_cli
   ```

3. **执行迁移**
   ```bash
   python -m src_v2.core.database.migration_cli
   ```

4. **验证结果**
   ```bash
   python -m src_v2.core.database.migration_cli --history
   ```

更多详情请参考 [docs/database_migration.md](docs/database_migration.md)。

### 主要配置项

#### [EDITION] - 版本类型
```toml
[EDITION]
# community = 社区版（开源仓库默认）；enterprise = 企业版（需要企业版代码，开源版请勿修改）
Edition = "community"
```

#### [APP] - 应用基础配置
```toml
[APP]
# 必填：应用签名密钥（JWT / 会话签名），要求 ≥32 位随机串
# 生成：python -c "import secrets;print(secrets.token_urlsafe(32))"
# ⚠️ 留空或保持模板占位符（change-me-*）时启动会被拒绝；
#    也可用环境变量 KAHUNA_SECRET_KEY 注入（优先级更高）
SECRET_KEY = "生成的随机密钥"
# 图片渲染代理 (留空则不使用)
PIC_RENDER_PROXY = ""
# 代理服务器地址 用于访问esi，自行配置
PROXY = ""
# 代理端口
PORT = 7890
# 计算子进程并发数
SUBWORKER_COUNT = 3
# API 文档（Swagger）开关
ENABLE_API_DOCS = false
```

#### [ADMIN] - 管理员账号初始化配置
```toml
[ADMIN]
# 是否在启动时创建默认管理员账号
# ⚠️ 口令要求 ≥12 位，且不能是 kahuna/admin/password/123456 之类弱口令，
#    否则启动只会记录告警并跳过建号
create_admin = false
admin_user = "你的管理员账号"
admin_passwd = "你的安全口令（至少 12 位）"
```

#### [POSTGREDB] - PostgreSQL 主库配置（必需）
```toml
[POSTGREDB]
Host = "localhost"
Port = 6201
Database = "kahunabot"
User = "kahunabot"
Password = "kahunabot"
```

#### [REDIS] - Redis 配置（必需）
```toml
[REDIS]
Host = "localhost"
Port = 6203
# 口令：docker_database 默认不设；自建实例有密码时填写
# 也可用环境变量 REDIS_PASSWORD 覆盖
Password = ""
```

#### [NEO4J] - Neo4j 图数据库配置（必需）
```toml
[NEO4J]
Host = "localhost"
Port = 7687
Username = "neo4j"
Password = "你的Neo4j密码"
```

#### [SDEDB] - SDE 数据库配置（必需）
```toml
[SDEDB]
Host = "localhost"
Port = 6202
Database = "sde"
User = "kahunabot"
Password = "kahunabot"
```

#### [SERVICE] - 服务间认证（接入 MCP 中间件 / QQ 机器人时需要）
```toml
[SERVICE]
# 共享服务密钥：调用方在请求头 X-Internal-API-Key 中携带
# 生成：python -c "import secrets;print(secrets.token_urlsafe(32))"
# 留空 = 拒绝所有服务间请求（fail-closed）
API_KEY = ""
# enforce = 强制执行（默认）；warn = 仅告警不拦截
MODE = "enforce"
```

#### [EVE] - EVE Online API 配置
```toml
[EVE]
# 在 https://developers.eveonline.com/ 申请应用获取
CLIENT_ID = "your_client_id"
SECRET_KEY = "your_secret_key"
# 回调地址
CALLBACK_LOCAL_HOST = "localhost:9527/"
```

#### [ESI] - ESI API 权限配置

根据你的需求启用或禁用相应的 ESI 权限。常用权限示例：

```toml
[ESI]
# 公共数据访问
publicData = false

# 资产相关权限
"esi-assets.read_assets.v1" = true
"esi-assets.read_corporation_assets.v1" = true

# 市场相关权限
"esi-markets.structure_markets.v1" = true
"esi-markets.read_character_orders.v1" = true

# 工业相关权限
"esi-industry.read_character_jobs.v1" = true
"esi-industry.read_corporation_jobs.v1" = true

# 蓝图相关权限
"esi-characters.read_blueprints.v1" = true
"esi-corporations.read_blueprints.v1" = true

# 技能相关权限
"esi-skills.read_skills.v1" = true

# 钱包相关权限
"esi-wallet.read_character_wallet.v1" = true
```

完整的权限列表请参考 `config.toml.example` 文件。

### 配置文件位置

配置文件应命名为 `config.toml` 并放置在项目根目录。

## 数据库初始化脚本

项目提供了两个数据库初始化脚本，用于初始化和更新数据库数据。

### 手动创建 SDE 数据库

`update_sde.py` 写入的是**独立的 SDE 数据库**（默认库名 `sde`），不是主库：

- 用 `docker_database/docker-compose.yml.example` 部署时，`postgres-sde` 服务已自动建库（宿主端口 6202），无需额外操作；
- 使用已有 PostgreSQL 实例时，手动建库：

```sql
CREATE DATABASE sde OWNER kahunabot;
```

然后在 `config.toml` 的 `[SDEDB]` 段填入该库的连接信息，再执行 `python update_sde.py` 导入数据。

### update_sde.py - SDE 数据更新工具

用于更新 EVE Online 的 SDE (Static Data Export) 数据库。该脚本会自动下载最新的 SDE 数据并导入到 PostgreSQL 数据库中。

#### 功能说明

- 自动检查最新版本
- 下载并解析 SDE 数据
- 导入到 PostgreSQL 数据库
- 支持版本检查和强制更新

#### 使用方法

```bash
# 检查当前版本和最新版本（不执行更新）
python update_sde.py --check-only

# 正常更新（仅在新版本时更新）
python update_sde.py

# 强制更新（即使版本相同也更新）
python update_sde.py --force

# 更新到指定版本
python update_sde.py --version <版本号>
```

#### 参数说明

- `--check-only`: 仅检查版本信息，不执行更新
- `--force`: 强制更新，即使版本相同也会重新导入数据
- `--version <版本号>`: 更新到指定的版本号

#### 使用示例

```bash
# 检查是否需要更新
python update_sde.py --check-only

# 执行更新
python update_sde.py

# 如果需要强制重新导入数据
python update_sde.py --force
```

#### 注意事项

- 更新过程可能需要较长时间，请耐心等待
- 确保 PostgreSQL 数据库已正确配置并可以连接
- 确保已创建 SDE 数据库（参考 [手动创建 SDE 数据库](#手动创建-sde-数据库) 部分）
- 更新过程中会占用一定的系统资源，建议在服务器负载较低时执行

### init_neo4j.py - Neo4j 数据库初始化脚本

用于初始化 Neo4j 图数据库中的市场树和蓝图树数据。该脚本会从 SDE 数据库中读取数据并构建图数据库结构。

#### 功能说明

脚本会执行以下 5 个步骤：

1. **初始化数据库连接** - 连接 PostgreSQL、Redis、Neo4j 和 SDE 数据库
2. **初始化市场树** - 构建市场分组树形结构
3. **链接类型到市场组** - 将物品类型链接到对应的市场组
4. **清理现有蓝图节点** - 清理旧的蓝图数据（如果使用 `--clean` 参数）
5. **初始化蓝图数据** - 导入蓝图相关数据到 Neo4j

#### 使用方法

```bash
# 正常初始化（保留现有数据，仅初始化缺失的数据）
python init_neo4j.py

# 清理模式（清理现有数据后重新初始化）
python init_neo4j.py --clean

# 或使用简写形式
python init_neo4j.py -c
```

#### 参数说明

- `--clean` 或 `-c`: 清理现有数据后重新初始化。使用此参数会删除所有现有的市场树和蓝图数据，然后重新构建。

#### 使用示例

```bash
# 首次初始化
python init_neo4j.py

# 如果需要重新初始化所有数据
python init_neo4j.py --clean
```

#### 注意事项

- 确保 PostgreSQL、Redis 和 Neo4j 数据库已正确配置并可以连接
- 确保 SDE 数据库已更新到最新版本（使用 `update_sde.py` 更新）
- 初始化过程可能需要较长时间，请耐心等待
- 使用 `--clean` 参数会删除所有现有数据，请谨慎使用
- 初始化过程中会占用一定的系统资源，建议在服务器负载较低时执行

#### 执行流程

脚本执行时会显示详细的进度信息：


- [EVE Online 官网](https://www.eveonline.com/)
- [EVE Online 开发者中心](https://developers.eveonline.com/)

## MCP 中间件配置

Kahuna System 提供 MCP (Model Context Protocol) 中间件服务，允许 AI 助手（如 Astrbot）通过标准化协议访问系统功能。

### 什么是 MCP

MCP (Model Context Protocol) 是一种开放协议，允许 AI 助手安全地访问外部工具和数据源。Kahuna MCP 服务作为中间件层，将 AI 请求转发到 Quart 后端 API，实现以下功能：

- **安全隔离**: MCP 服务与主服务分离，通过 HTTP API 通信
- **工具暴露**: 暴露 9 个核心工具供 AI 调用
- **实时监控**: 支持 QQ 群 VIP 状态查询、市场价格查询等

### MCP 工具列表

#### QQ 相关工具
| 工具名         | 描述                                              |
| -------------- | ------------------------------------------------- |
| `qq_vip_state` | 查询 QQ 群 VIP 状态，返回已激活和未激活的用户列表 |

#### 市场相关工具
| 工具名                  | 描述                       |
| ----------------------- | -------------------------- |
| `market_tag_list`       | 获取市场价格标签列表       |
| `market_price_detail`   | 查询特定类型的市场价格详情 |
| `market_type_cost`      | 计算特定类型的采购成本     |
| `market_fuzz_type_name` | 模糊搜索类型名称           |
| `market_type_metrics`   | 获取特定类型的市场指标     |

#### 工业相关工具
| 工具名                                    | 描述                       |
| ----------------------------------------- | -------------------------- |
| `running_jobs_overview`                   | 获取正在进行的工业作业概览 |
| `plan_missing_blueprint_workflow_summary` | 获取缺失蓝图的工业规划摘要 |
| `get_company_medica_vouchers`             | 获取公司医疗券信息（传入 qq，只返回本人记录） |

### 启动 MCP 服务

#### 使用脚本启动（推荐）

```bash
# 启动 MCP 服务
./run_server.sh start-mcp

# 停止 MCP 服务
./run_server.sh stop-mcp

# 查看服务状态
./run_server.sh status

# 停止所有服务
./run_server.sh stop-all
```

#### 手动启动

```bash
# 直接启动 MCP 服务
python run_mcp_middleware.py

# 或作为后台进程启动
nohup python run_mcp_middleware.py > logs/mcp_server.log 2>&1 &
```

### Astrbot MCP 配置

在 Astrbot 的 `cmd_config.json` 或管理面板中配置 MCP：

```json
{
    "mcpServers": {
        "kahuna-system": {
            "transport": "http",
            "url": "http://localhost:9274/sse"
        }
    }
}
```

#### 配置参数说明

- **transport**: 传输协议，固定为 `http`
- **url**: MCP 服务 SSE 端点地址，端口取决于启动方式：
  - **Docker 部署**（`docker/` 下的 compose）：`http://localhost:9274/sse`
  - **`run_server.sh start-mcp`**：`http://localhost:9000/sse`
  - 远程服务器：把 `localhost` 换成服务器地址

> ⚠️ **开源（社区）版功能边界**：MCP 服务本身可用，但依赖企业版服务的工具（`qq_vip_state`、`get_company_medica_vouchers` 等）在社区版会返回 503 —— 对应的企业版 AstrBot/QQ 服务没有随开源版发布。

### 服务架构

```
Astrbot (AI 助手)
    ↓ (MCP 协议)
MCP 中间件服务 (Docker: 9274 / 脚本: 9000)
    ↓ (HTTP API，服务间认证 X-Internal-API-Key)
Quart 后端服务 (端口 9527)
    ↓ (数据库)
PostgreSQL / Redis / Neo4j
```

### 端口说明

| 服务 | 端口 | 用途 |
| --- | --- | --- |
| Quart 后端 | 9527 | Web 界面和 API |
| MCP 中间件（Docker） | 9274 | MCP 协议服务（`docker/` compose 映射） |
| MCP 中间件（脚本） | 9000 | `run_server.sh start-mcp` 启动时使用 |
| PostgreSQL 主库 | 6201 | 主数据库（`docker_database` 映射） |
| PostgreSQL SDE 库 | 6202 | SDE 静态数据 |
| Redis | 6203 | 缓存 |
| Neo4j | 7687 | 图数据库 |

### 故障排查

#### MCP 服务无法启动

1. **检查端口占用**（Docker 部署为 9274，脚本启动为 9000）
   ```bash
   netstat -tulpn | grep -E '9274|9000'
   # 或
   lsof -i :9274
   ```

2. **检查依赖安装**
   ```bash
   # mcp / fastmcp 已在 pyproject 依赖中，重新同步即可
   uv sync
   ```

3. **查看日志**
   ```bash
   tail -f logs/mcp_server.log
   # Docker 部署：docker compose logs -f kahunabot
   ```

#### Astrbot 无法连接 MCP

1. **检查服务状态**
   ```bash
   ./run_server.sh status
   # Docker 部署：docker compose ps
   ```

2. **确认 SSE 端点可连通**
   ```bash
   # MCP 服务只暴露 /sse（没有 /health 端点），用 curl 观察握手
   curl -N --max-time 5 http://localhost:9274/sse
   ```

3. **检查防火墙设置**
   - 确保 MCP 端口对外开放（Docker 9274 / 脚本 9000）
   - 如果是远程服务器，检查安全组规则

4. **验证工具注册**
   ```bash
   # MCP 服务启动时会在日志中打印已注册的工具
   grep -i "tool" logs/mcp_server.log | head
   ```

#### 工具调用失败

1. **检查后端服务**
   - 确保 Quart 后端服务已启动
   - 检查后端日志：`tail -f logs/*.log`（Docker 部署在 `docker/app_logs/`）

2. **检查内部 API**（需要服务间密钥，路径以 `/api/internal/mcp/` 开头）
   ```bash
   # 示例：QQ VIP 状态；密钥取自 config.toml 的 [SERVICE] API_KEY
   curl -H "X-Internal-API-Key: <你的SERVICE_API_KEY>" \
        "http://localhost:9527/api/internal/mcp/qq/vip?qq=123456"
   ```
   > 社区版该接口返回 503（企业版服务未随开源版发布），属预期行为。

3. **检查数据库连接**
    - 确保 PostgreSQL、Redis、Neo4j 服务正常运行
    - 验证配置文件 `config.toml` 中的连接信息

---

## 测试

项目已建立系统化测试工程，覆盖后端单元测试、DAO 集成测试、API 路由测试、业务逻辑集成测试、前端单元测试和 E2E 冒烟测试。

### 测试统计

| 层 | 框架 | 文件数 | 测试数 | 耗时 |
|---|------|--------|--------|------|
| 后端单元测试 | pytest | 4 | 57 | ~1s |
| DAO 集成测试 | pytest + SQLite | 5 | 73 | ~2s |
| API 路由测试 | pytest + Quart test client | 4 | 103 | ~6s |
| 业务集成测试 | pytest | 1 | 24 | ~0.1s |
| 前端单元测试 | Vitest | 4 | 75 | ~1.5s |
| **合计** | | **18** | **332** | **~11s** |

### 后端测试

#### 安装测试依赖

```bash
# 使用 uv（推荐）
uv sync --group test
```

#### 运行测试

```bash
# 运行所有测试
uv run pytest tests/ -v

# 运行特定层级
uv run pytest tests/unit/ -v       # 单元测试
uv run pytest tests/dao/ -v        # DAO 集成测试（SQLite 内存数据库）
uv run pytest tests/api/ -v        # API 路由测试
uv run pytest tests/integration/ -v # 业务逻辑集成测试

# 按标记筛选
uv run pytest -m unit -v
uv run pytest -m dao -v
uv run pytest -m api -v
uv run pytest -m integration -v

# 生成覆盖率报告
uv run pytest tests/ --cov=src_v2 --cov-report=html
```

#### 集成测试（需要真实数据库）

部分测试需要真实的 PostgreSQL 和 Redis 服务：

```bash
# 设置环境变量启用集成测试
export POSTGRES_TEST_ENABLED=1
export REDIS_TEST_ENABLED=1

# 运行集成测试
uv run pytest tests/ -m integration -v
```

在 CI 中自动启动服务容器（见 `.github/workflows/test.yml`）。

### 前端测试

#### 安装

```bash
cd src_v2/frontend
npm install
```

#### 运行

```bash
# 运行所有测试
npm test

# 监听模式
npm run test:watch

# 生成覆盖率
npm run test:coverage

# E2E 测试（需要运行中的服务器）
npm run test:e2e
```

### 测试架构

```
tests/
├── conftest.py                 # 全局 fixture（Quart 客户端、DB mock、JWT headers）
├── unit/                       # 单元测试 — 纯逻辑，无外部依赖
│   ├── test_auth.py           # JWT 验证
│   ├── test_utils/            # 工具函数（roundup、chunks、key builder）
│   └── test_industry_utils/   # 加密/解密
├── dao/                        # DAO 集成测试 — SQLite 内存数据库
│   ├── conftest.py            # SQLite fixture
│   ├── test_user_dao.py       # 用户 CRUD
│   ├── test_permission_dao.py # 权限 RBAC
│   ├── test_industry_plan_dao.py # 工业计划
│   └── test_asset_dao.py     # 资产视图
├── api/                        # API 路由测试 — Quart 测试客户端
│   ├── test_auth_routes.py    # 登录/注册/鉴权
│   ├── test_permission_routes.py # RBAC 权限链
│   ├── test_public_routes.py  # 公开端点
│   └── test_mcp_routes.py    # MCP 代理
└── integration/                # 业务集成测试
    └── test_esi_req_manager.py # ESI 令牌桶算法

src_v2/frontend/src/
├── composables/__tests__/     # 前端 Composable 测试
│   └── useEdition.spec.ts
├── stores/__tests__/          # Pinia Store 测试
│   └── auth.spec.ts
├── __tests__/                 # 工具函数测试
│   └── http.spec.ts
└── e2e/                       # Playwright E2E
    └── smoke.spec.ts
```

### CI/CD

推送代码到 `main` 或 `develop` 分支时，GitHub Actions 自动执行：

1. **后端测试** — ruff lint → pytest（unit + dao + api + integration）→ 覆盖率上传
2. **前端测试** — TypeScript 类型检查 → Vitest 测试
3. **集成测试**（仅 main 分支）— 启动 PostgreSQL + Redis 服务容器 → 运行 integration 标记测试

工作流文件：`.github/workflows/test.yml`

### 测试规范

- 新增功能需同步编写对应层级的测试
- 后端纯逻辑覆盖率目标 > 85%
- API 端点覆盖率目标 > 80%
- 禁止使用 `as any`、`@ts-ignore` 绕过类型错误
- 禁止在测试中调用真实外部 API（ESI、Google Sheets）
- 修改数据库模型后需运行迁移并更新对应 DAO 测试
