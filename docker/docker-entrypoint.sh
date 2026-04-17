#!/bin/sh
# ============================================
# KahunaBot Docker 入口脚本
# ============================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo "${RED}[ERROR]${NC} $1"
}

# 检查配置文件
log_info "检查配置文件..."

if [ ! -f "config.toml" ]; then
    if [ -f "docker/config.toml.docker" ]; then
        log_warn "配置文件不存在，使用 Docker 模板创建"
        cp docker/config.toml.docker config.toml
        log_warn "请修改 config.toml 中的 EVE API 配置 (CLIENT_ID 和 SECRET_KEY)"
    else
        log_error "配置文件不存在且找不到模板文件"
        exit 1
    fi
fi

log_info "启动 KahunaBot 服务..."

# 检查 uv 是否安装
if [ ! -f "/root/.local/bin/uv" ]; then
    log_error "uv 未找到: /root/.local/bin/uv"
    exit 1
fi

log_info "uv 版本: $(/root/.local/bin/uv --version)"

# 检查虚拟环境
if [ ! -d "/app/.venv" ]; then
    log_warn "虚拟环境不存在，执行 uv sync..."
    cd /app && /root/.local/bin/uv sync --no-cache
fi

log_info "虚拟环境就绪"

# 执行主命令
exec "$@"
