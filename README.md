<div align="center">

# 🌟 Kahuna System 🌟

![Logo](https://github.com/user-attachments/assets/40c09a45-f898-4167-9315-20df6a1dc59a)

[![开发状态](https://img.shields.io/badge/状态-开发中-yellow)](https://github.com/AraragiEro/astrbot_plugin_kahunabot)
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

- **市场价格查询** - 支持吉他和联盟市场实时价格查询
- **成本计算** - 精确计算制造和采购成本
- **工业规划** - 智能工业制造规划与报表输出
- **化矿分析** - 矿石精炼与材料分析【**计划中**】
- **采购清单** - 可自定义数据来源的采购清单管理
- **利润分析** - 深度利润分析与市场机会挖掘【**计划中**】
- **挂单分析** - 市场订单分析与优化建议【**计划中**】
- **资产统计** - 角色和公司资产统计与管理【**计划中**】

## 技术栈

- **后端**: Quart (Python 3.13+), Hypercorn
- **前端**: Vue 3, TypeScript, Element Plus, ECharts
- **数据库**: SQLite / PostgreSQL, Neo4j, Redis
- **其他**: ESI API, OAuth2

## 快速开始

### 环境要求

- Python 3.13 或更高版本
- Node.js 18+ (用于前端开发)
- 数据库：SQLite (默认) 或 PostgreSQL + Neo4j + Redis (可选)

### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/AraragiEro/astrbot_plugin_kahunabot.git
cd astrbot_plugin_kahunabot
```

2. **安装后端依赖**

使用 `uv` (推荐):
```bash
uv sync
```

或使用 `pip`:
```bash
pip install -r requirements.txt
```

3. **安装前端依赖**

```bash
cd src_v2/frontend
npm install
```

4. **准备 SDE 数据库**

项目需要 EVE Online 的 SDE (Static Data Export) 数据库。你可以使用 [EVE-SDE-Database-Builder](https://github.com/EVEIPH/EVE-SDE-Database-Builder) 工具生成 SQLite 格式的英文和中文 SDE 数据库。

官方 SDE 数据下载地址: [https://developers.eveonline.com/](https://developers.eveonline.com/)

5. **配置 EVE API**

前往 [EVE Online 开发者中心](https://developers.eveonline.com/) 创建应用，获取 `CLIENT_ID` 和 `SECRET_KEY`。

6. **启动服务**

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

## 数据库部署

### 使用 Docker 部署 PostgreSQL 和 Redis

推荐使用 Docker Compose 快速部署 PostgreSQL 和 Redis 数据库。

#### 创建 docker-compose.yml

在项目根目录创建 `docker-compose.yml` 文件：

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: kahuna-postgres
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: kahuna
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U admin"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: kahuna-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:
```

#### 启动数据库服务

```bash
# 启动服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

#### 停止数据库服务

```bash
# 停止服务（保留数据）
docker-compose stop

# 停止并删除容器（保留数据卷）
docker-compose down

# 停止并删除容器及数据卷（⚠️ 警告：会删除所有数据）
docker-compose down -v
```

#### 数据持久化

数据会保存在 Docker 卷中，即使删除容器也不会丢失数据。卷的位置可以通过以下命令查看：

```bash
docker volume ls
docker volume inspect <volume_name>
```

#### 配置说明

启动数据库后，需要在 `config.toml` 中配置数据库连接信息：

```toml
[POSTGREDB]
Host = "localhost"
Port = 5432
Database = "kahuna"
User = "admin"
Password = "secret"

[REDIS]
Host = "localhost"
Port = 6379
```

### 手动创建 SDE 数据库

如果使用 PostgreSQL 作为 SDE 数据库，需要手动创建数据库。以下是几种创建方法：

#### 方法一：使用 psql 命令行工具

1. 连接到 PostgreSQL：

```bash
psql -U admin -h localhost -p 5432 -d postgres
```

2. 创建 SDE 数据库：

```sql
CREATE DATABASE "sde";
```

3. 退出 psql：

```sql
\q
```

#### 方法二：使用 SQL 命令（需要管理员权限）

```sql
CREATE DATABASE "sde";
```

#### 方法三：使用图形化工具（如 pgAdmin）

1. 连接到 PostgreSQL 服务器（`localhost:5432`）
2. 右键点击 `Databases` -> `Create` -> `Database...`
3. 输入数据库名称：`sde`
4. 点击 `Save` 保存

#### 配置 SDE 数据库

创建数据库后，在 `config.toml` 中配置 SDE 数据库连接信息：

```toml
[SDEDB]
Host = "localhost"
Port = 5432
Database = "sde"
User = "admin"
Password = "secret"
```

## 配置说明

### 配置文件

项目使用 TOML 格式的配置文件。将 `config.toml.example` 复制为 `config.toml` 并填写相应配置。

### 主要配置项

#### [APP] - 应用基础配置
```toml
[APP]
# 图片渲染代理 (留空则不使用)
PIC_RENDER_PROXY = ""
# 代理服务器地址 用于访问esi，自行配置
PROXY = "127.0.0.1"
# 代理端口
PORT = 7890
```

#### [SQLITEDB] - SQLite 数据库配置
```toml
[SQLITEDB]
# 配置数据库路径（绝对路径）
CONFIG_DB = "/path/to/kahuna.db"
CACHE_DB = "/path/to/cache.db"
# SDE 数据库路径
SDEDB = "/path/to/sde.db"           # 英文 SDE 数据库
CN_SDEDB = "/path/to/sde_cn.db"     # 中文 SDE 数据库
```

#### [POSTGREDB] - PostgreSQL 数据库配置 (可选)
```toml
[POSTGREDB]
Host = "localhost"
Port = 5432
Database = "kahuna"
User = "admin"
Password = "secret"
```

#### [REDIS] - Redis 配置 (可选)
```toml
[REDIS]
Host = "localhost"
Port = 6379
```

#### [NEO4J] - Neo4j 图数据库配置 (可选)
```toml
[NEO4J]
Host = "localhost"
Port = 7687
Username = "neo4j"
Password = "password"
```

#### [EVE] - EVE Online API 配置
```toml
[EVE]
# 在 https://developers.eveonline.com/ 申请应用获取
CLIENT_ID = "your_client_id"
SECRET_KEY = "your_secret_key"
# 回调地址
CALLBACK_LOCAL_HOST = ""
CALLBACK_LOCAL_ADD = "https://localhost:9527/"
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

```
- [EVE Online 官网](https://www.eveonline.com/)
- [EVE Online 开发者中心](https://developers.eveonline.com/)
