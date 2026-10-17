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

# 安全校验提示：应用签名密钥不能沿用模板占位符（安全审计 #12，生产模式会拒绝启动）
if grep -qE '^[[:space:]]*SECRET_KEY[[:space:]]*=[[:space:]]*"(change-me|your-secret|placeholder)' config.toml 2>/dev/null; then
    log_warn "检测到 [APP] SECRET_KEY 仍是模板占位符，生产模式将拒绝启动。"
    log_warn "请生成并填写随机密钥，或通过环境变量注入（优先）："
    log_warn "  python -c \"import secrets;print(secrets.token_urlsafe(32))\""
    log_warn "  export KAHUNA_SECRET_KEY=<生成的密钥>"
fi

log_info "启动 KahunaBot 服务..."

# 检查 uv 是否安装（支持两种路径）
UV_BIN=""
if [ -f "/usr/local/bin/uv" ]; then
    UV_BIN="/usr/local/bin/uv"
elif [ -f "/root/.local/bin/uv" ]; then
    UV_BIN="/root/.local/bin/uv"
else
    log_error "uv 未找到"
    exit 1
fi

log_info "uv 版本: $($UV_BIN --version)"

# 检查虚拟环境
if [ ! -d "/app/.venv" ]; then
    log_warn "虚拟环境不存在，执行 uv sync..."
    cd /app && $UV_BIN sync --no-cache
fi

log_info "虚拟环境就绪"

# 执行主命令
exec "$@"
