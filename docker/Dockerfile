# syntax=docker/dockerfile:1

# ============================================
# KahunaBot 多阶段构建 Dockerfile
# 包含后端服务和 MCP 中间件
#
# 优化说明：
# 1. 多阶段构建分离依赖安装，利用 Docker 层缓存
# 2. 使用 BuildKit 缓存挂载加速 uv 依赖下载
# 3. 代码变更时无需重新安装依赖
# ============================================

# ---------------------------------------------------------
# 阶段 1: 前端构建
# ---------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 构建参数：是否使用国内 npm 镜像源
ARG NPM_REGISTRY=""

# 复制前端依赖文件（变化少，层可缓存）
COPY src_v2/frontend/package*.json ./

# 如指定了国内源则配置 npm registry
RUN if [ -n "$NPM_REGISTRY" ]; then npm config set registry "$NPM_REGISTRY"; fi

# 安装依赖
RUN npm ci

# 复制前端源码（变化频繁）
COPY src_v2/frontend/ ./

# 构建前端
RUN npm run build-only

# ---------------------------------------------------------
# 阶段 2: Python 依赖层（可缓存）
# ---------------------------------------------------------
FROM ubuntu:24.04 AS python-deps

WORKDIR /app

# 安装 uv 所需的系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libpq5 \
    libpq-dev \
    python3 \
    python3-venv \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:$PATH"

# 安装 Python 3.13（项目需要 3.13+）
RUN uv python install 3.13

# 只复制依赖文件（变化少，层可缓存）
# 注意：必须一并复制 uv.lock，否则 uv sync 会重新解析依赖导致版本漂移
# （曾因此装到 sqlalchemy 2.1.3，greenlet 只在 [asyncio] extra 中，启动即崩）
COPY pyproject.toml requirements.txt uv.lock ./

# 安装依赖（利用 Docker 层缓存和 BuildKit 缓存挂载）
# --frozen 严格按 uv.lock 安装，不重新解析，保证构建可复现
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --python 3.13 --frozen

# ---------------------------------------------------------
# 阶段 3: 最终运行镜像
# ---------------------------------------------------------
FROM ubuntu:24.04 AS runtime

WORKDIR /app

# 安装运行时系统依赖（最小化）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libpq5 \
    supervisor \
    wkhtmltopdf \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# 从依赖层复制 uv 可执行文件
COPY --from=python-deps /root/.local/bin/uv /usr/local/bin/uv

# 从依赖层复制已安装好的虚拟环境
COPY --from=python-deps /app/.venv ./.venv

# 安装 Python 3.13 到虚拟环境（确保解释器可用）
RUN uv python install 3.13 --default --preview

ENV UV_PYTHON=/app/.venv/bin/python
ENV PATH="/app/.venv/bin:$PATH"

# 复制项目代码（变化频繁，放在后面）
COPY src_v2/ ./src_v2/
COPY run_server.py ./
COPY run_mcp_middleware.py ./

# 复制构建好的前端静态文件
COPY --from=frontend-builder /app/frontend/dist ./src_v2/frontend/dist

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
