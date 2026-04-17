# KahunaBot Docker 部署指南

本文档说明如何使用 Docker 一键部署 KahunaBot 后端服务和 MCP 中间件。

## 包含的服务

- **KahunaBot Web 服务** (端口: 9527) - Quart 后端 + Vue3 前端
- **MCP 中间件** (端口: 9000) - Model Context Protocol 服务

## 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- 外部数据库服务（PostgreSQL、Redis、Neo4j）

## 快速开始

### 1. 准备配置文件

Docker 部署会直接使用项目根目录的 `config.toml` 配置文件。

**如果你已有配置好的 `config.toml`：**
直接确保文件在项目根目录即可，无需额外操作。

**如果你是新部署：**
可以从模板创建配置文件：

```bash
cd docker
cp config.toml.docker ../config.toml
```

然后编辑根目录的 `config.toml`，填写必要的配置：

```toml
[EVE]
CLIENT_ID = "你的客户端ID"
SECRET_KEY = "你的密钥"
CALLBACK_LOCAL_HOST = "localhost:9527/"

[ADMIN]
# 首次启动会创建默认管理员账号
create_admin = true
admin_user = "kahuna"
admin_passwd = "你的安全密码"
```

如需使用外部数据库，配置对应的数据库连接信息。

### 2. 启动服务

```bash
cd docker
docker-compose up -d
```

### 3. 验证服务

- Web 界面: http://localhost:9527
- MCP 端点: http://localhost:9000/sse
- 健康检查: http://localhost:9527/api/health

### 4. 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f kahunabot
```

### 5. 停止服务

```bash
docker-compose down
```

## 常用命令

```bash
# 重新构建镜像
docker-compose build --no-cache

# 重启服务
docker-compose restart

# 查看运行状态
docker-compose ps

# 进入容器内部
docker-compose exec kahunabot bash
```

## 数据持久化

以下数据通过 Docker Volume 持久化：

- `app_data` - 应用数据（SQLite 数据库）
- `app_logs` - 日志文件
- `app_downloads` - 下载资源
- `app_tmp` - 临时文件

## 配置说明

### 环境变量

| 变量名             | 说明              | 默认值 |
| ------------------ | ----------------- | ------ |
| `PYTHONUNBUFFERED` | Python 无缓冲输出 | 1      |

### 端口映射

| 端口 | 服务          | 说明             |
| ---- | ------------- | ---------------- |
| 9527 | KahunaBot Web | 主应用访问端口   |
| 9274 | MCP 中间件    | MCP 协议服务端口 |

## 故障排查

### 服务无法启动

1. 检查配置文件是否存在
2. 检查 EVE API 配置是否正确
3. 查看日志: `docker-compose logs`

### MCP 连接失败

确保 MCP 配置的 `quart-url` 正确指向 KahunaBot 服务。

### 数据库连接失败

检查 `config.toml` 中的数据库连接配置是否正确。

## 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker-compose up -d --build
```

## 注意事项

1. 首次启动时会自动创建默认管理员账号（kahuna/kahuna）
2. 生产环境请修改默认密码和 SECRET_KEY
3. 建议定期备份 `data` 目录
