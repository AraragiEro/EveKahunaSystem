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

### 环境要求

- Python 3.13
- Node.js 18+ (用于前端开发)
- 数据库：SQLite (默认) 或 PostgreSQL + Neo4j + Redis

### 安装步骤

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

4. **准备 SDE 数据库**

请参考**手动创建 SDE 数据库**章节

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

  neo4j:
    image: neo4j:2025.10.1
    container_name: kahuna-neo4j
    ports:
      - "7687:7687"  # Bolt协议
      - "7474:7474"  # HTTP
    environment:
      - NEO4J_AUTH=neo4j/password
      - NEO4J_PLUGINS=["apoc"]
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - neo4j_plugins:/var/lib/neo4j/plugins
      - neo4j_conf:/var/lib/neo4j/conf
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "password", "RETURN 1"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:
  neo4j_data:
  neo4j_logs:
  neo4j_conf:
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
   docker-compose restart neo4j
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
- 如果插件未生效，检查容器日志：`docker-compose logs neo4j`


#### 配置说明

启动数据库后，需要在 `config.toml` 中配置数据库连接信息：

```toml
[POSTGREDB]
Host = "localhost"
Port = 5432 # 具体看你创建容器时的映射端口
Database = "kahuna"
User = "admin"
Password = "secret"

[REDIS]
Host = "localhost"
Port = 6379 # 具体看你创建容器时的映射端口

[NEO4J]
Host = "localhost"
Port = 7687 # 具体看你创建容器时的映射端口
Username = "neo4j"
Password = "password"

[SDEDB]
Host = "localhost"
Port = 5432 # 具体看你创建容器时的映射端口
Database = "sde"
User = "admin"
Password = "secret"
```

**注意**：如果使用 Docker Compose 部署，Neo4j 的 Host 应设置为 `localhost`（从宿主机访问）或容器名称 `kahuna-neo4j`（从其他容器访问）。首次启动 Neo4j 后，建议修改默认密码。

**注意**：SDE数据库使用前需要初始化，请看下面的sde数据库更新工具。

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

### [ADMIN] 管理员账号初始化配置
```toml
[ADMIN]
# 是否创建默认管理员账号
create_admin = false
admin_user = "kahuna"
admin_passwd = "kahuna"
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

## MCP 中间件配置

Kahuna System 提供 MCP (Model Context Protocol) 中间件服务，允许 AI 助手（如 Astrbot）通过标准化协议访问系统功能。

### 什么是 MCP

MCP (Model Context Protocol) 是一种开放协议，允许 AI 助手安全地访问外部工具和数据源。Kahuna MCP 服务作为中间件层，将 AI 请求转发到 Quart 后端 API，实现以下功能：

- **安全隔离**: MCP 服务与主服务分离，通过 HTTP API 通信
- **工具暴露**: 暴露 9 个核心工具供 AI 调用
- **实时监控**: 支持 QQ 群 VIP 状态查询、市场价格查询等

### MCP 工具列表

#### QQ 相关工具
| 工具名 | 描述 |
|--------|------|
| `qq_vip_state` | 查询 QQ 群 VIP 状态，返回已激活和未激活的用户列表 |

#### 市场相关工具
| 工具名 | 描述 |
|--------|------|
| `market_tag_list` | 获取市场价格标签列表 |
| `market_price_detail` | 查询特定类型的市场价格详情 |
| `market_type_cost` | 计算特定类型的采购成本 |
| `market_fuzz_type_name` | 模糊搜索类型名称 |
| `market_type_metrics` | 获取特定类型的市场指标 |

#### 工业相关工具
| 工具名 | 描述 |
|--------|------|
| `running_jobs_overview` | 获取正在进行的工业作业概览 |
| `plan_missing_blueprint_workflow_summary` | 获取缺失蓝图的工业规划摘要 |
| `get_company_medica_vouchers` | 获取公司医疗券信息 |

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
            "url": "http://localhost:9000/sse"
        }
    }
}
```

#### 配置参数说明

- **transport**: 传输协议，固定为 `http`
- **url**: MCP 服务 SSE 端点地址
  - 本地开发: `http://localhost:9000/sse`
  - 远程服务器: `http://your-server-ip:9000/sse`

### 服务架构

```
Astrbot (AI 助手)
    ↓ (MCP 协议)
MCP 中间件服务 (端口 9000)
    ↓ (HTTP API)
Quart 后端服务 (端口 9527)
    ↓ (数据库)
PostgreSQL / Redis / Neo4j
```

### 端口说明

| 服务 | 端口 | 用途 |
|------|------|------|
| Quart 后端 | 9527 | Web 界面和 API |
| MCP 中间件 | 9000 | MCP 协议服务 |
| PostgreSQL | 5432 | 主数据库 |
| Redis | 6379 | 缓存 |
| Neo4j | 7687 | 图数据库 |

### 故障排查

#### MCP 服务无法启动

1. **检查端口占用**
   ```bash
   # 检查 9000 端口是否被占用
   netstat -tulpn | grep 9000
   # 或
   lsof -i :9000
   ```

2. **检查依赖安装**
   ```bash
   # 确保安装了 mcp 库
   pip install mcp
   ```

3. **查看日志**
   ```bash
   tail -f logs/mcp_server.log
   ```

#### Astrbot 无法连接 MCP

1. **检查服务状态**
   ```bash
   ./run_server.sh status
   ```

2. **测试 MCP 健康检查**
   ```bash
   curl http://localhost:9000/health
   # 应返回: {"status": "healthy", "backend_connected": true}
   ```

3. **检查防火墙设置**
   - 确保端口 9000 对外开放
   - 如果是远程服务器，检查安全组规则

4. **验证工具列表**
   ```bash
   # MCP 服务启动时会打印注册的工具列表
   # 检查日志中是否有 9 个工具
   grep "MCP 工具注册完成" logs/mcp_server.log
   ```

#### 工具调用失败

1. **检查后端服务**
   - 确保 Quart 后端服务已启动
   - 检查后端日志: `tail -f logs/server.log`

2. **检查内部 API**
   ```bash
   # 测试内部 API 是否可访问
   curl http://localhost:9527/api/internal/mcp/qq_vip_state
   ```

3. **检查数据库连接**
   - 确保 PostgreSQL、Redis、Neo4j 服务正常运行
   - 验证配置文件 `config.toml` 中的连接信息
