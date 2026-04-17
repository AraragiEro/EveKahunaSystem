# syntax=docker/dockerfile:1

# ============================================
# KahunaBot 多阶段构建 Dockerfile
# 包含后端服务和 MCP 中间件
# ============================================

# ---------------------------------------------------------
# 阶段 1: 前端构建
# ---------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 复制前端依赖文件
COPY src_v2/frontend/package*.json ./

# 安装依赖
RUN npm ci

# 复制前端源码
COPY src_v2/frontend/ ./

# 构建前端
RUN npm run build-only

# ---------------------------------------------------------
# 阶段 2: 最终运行镜像
# ---------------------------------------------------------
FROM ubuntu:24.04 AS runtime

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libpq5 \
    supervisor \
    wkhtmltopdf \
    python3 \
    python3-venv \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:$PATH"

# 复制项目文件
COPY pyproject.toml requirements.txt ./
COPY src_v2/ ./src_v2/
COPY run_server.py ./
COPY run_mcp_middleware.py ./

# 复制构建好的前端静态文件
COPY --from=frontend-builder /app/frontend/dist ./src_v2/frontend/dist

# 使用 uv sync 安装依赖（会自动创建 .venv 并安装所有依赖）
RUN uv sync --no-cache

# 创建必要的目录
RUN mkdir -p data logs download_resource tmp credentials

# 复制 supervisor 配置
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# 复制入口脚本
COPY docker/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV UV_PYTHON=/app/.venv/bin/python

# 暴露端口
# 9527 - KahunaBot Web 服务
# 9274 - MCP 中间件服务
EXPOSE 9527 9274

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:9527/api/health || exit 1

# 使用入口脚本启动
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
