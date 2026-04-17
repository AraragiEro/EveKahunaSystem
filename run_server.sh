#!/bin/bash -x

# 服务器管理脚本
# 用于启动和停止 kahunabot 服务器和 MCP 中间件服务

# 获取脚本所在目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 配置
PID_FILE="$SCRIPT_DIR/.server.pid"
MCP_PID_FILE="$SCRIPT_DIR/.mcp_server.pid"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/server.log"
MCP_LOG_FILE="$LOG_DIR/mcp_server.log"
PYTHON_CMD="python"
SERVER_SCRIPT="run_server.py"
MCP_SCRIPT="run_mcp_middleware.py"

# 确保日志目录存在
mkdir -p "$LOG_DIR"

export PYTHONUNBUFFERED=1

# 检查进程是否运行
is_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if kill -0 "$PID" 2>/dev/null; then
            return 0
        else
            # PID 文件存在但进程不存在，清理 PID 文件
            rm -f "$pid_file"
            return 1
        fi
    else
        return 1
    fi
}

# 启动服务器（生产模式）
start_server() {
    # 检查是否已经运行
    if is_running "$PID_FILE"; then
        PID=$(cat "$PID_FILE")
        echo "服务器已经在运行中 (PID: $PID)"
        exit 1
    fi

    # 检查 Python 脚本是否存在
    if [ ! -f "$SERVER_SCRIPT" ]; then
        echo "错误: 找不到 $SERVER_SCRIPT"
        exit 1
    fi

    echo "正在启动服务器（生产模式）..."
    
    # 设置生产环境变量
    export ENVIRONMENT=production
    export POSTGRE_FORCE_REBUILD=false
    
    # 使用 nohup 启动服务器，重定向输出到日志文件
    nohup $PYTHON_CMD "$SERVER_SCRIPT" --prod > "$LOG_FILE" 2>&1 &
    
    # 获取后台进程的 PID
    SERVER_PID=$!
    
    # 等待一下，检查进程是否成功启动
    sleep 2
    
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        # 进程运行正常，保存 PID
        echo "$SERVER_PID" > "$PID_FILE"
        echo "服务器启动成功 (PID: $SERVER_PID)"
        echo "日志文件: $LOG_FILE"
        echo "使用 'tail -f $LOG_FILE' 查看日志"
    else
        echo "错误: 服务器启动失败"
        echo "请查看日志文件: $LOG_FILE"
        exit 1
    fi
}

# 启动服务器（开发模式）
start_dev_server() {
    # 检查是否已经运行
    if is_running "$PID_FILE"; then
        PID=$(cat "$PID_FILE")
        echo "服务器已经在运行中 (PID: $PID)"
        exit 1
    fi

    # 检查 Python 脚本是否存在
    if [ ! -f "$SERVER_SCRIPT" ]; then
        echo "错误: 找不到 $SERVER_SCRIPT"
        exit 1
    fi

    echo "正在启动服务器（开发模式）..."
    
    # 设置开发环境变量
    export ENVIRONMENT=dev
    export POSTGRE_FORCE_REBUILD=true
    export POSTGRE_FK_SKIP_VALIDATION=true
    
    # 使用 nohup 启动服务器，重定向输出到日志文件
    nohup $PYTHON_CMD "$SERVER_SCRIPT" --dev > "$LOG_FILE" 2>&1 &
    
    # 获取后台进程的 PID
    SERVER_PID=$!
    
    # 等待一下，检查进程是否成功启动
    sleep 2
    
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        # 进程运行正常，保存 PID
        echo "$SERVER_PID" > "$PID_FILE"
        echo "服务器启动成功 (PID: $SERVER_PID)"
        echo "日志文件: $LOG_FILE"
        echo "使用 'tail -f $LOG_FILE' 查看日志"
    else
        echo "错误: 服务器启动失败"
        echo "请查看日志文件: $LOG_FILE"
        exit 1
    fi
}

# 启动 MCP 中间件服务
start_mcp() {
    # 检查 MCP 是否已经在运行
    if is_running "$MCP_PID_FILE"; then
        PID=$(cat "$MCP_PID_FILE")
        echo "MCP 服务已经在运行中 (PID: $PID)"
        exit 1
    fi

    # 检查 MCP 脚本是否存在
    if [ ! -f "$MCP_SCRIPT" ]; then
        echo "错误: 找不到 $MCP_SCRIPT"
        exit 1
    fi

    echo "正在启动 MCP 中间件服务..."
    
    # 使用 nohup 启动 MCP 服务，重定向输出到日志文件
    nohup $PYTHON_CMD "$MCP_SCRIPT" > "$MCP_LOG_FILE" 2>&1 &
    
    # 获取后台进程的 PID
    MCP_PID=$!
    
    # 等待一下，检查进程是否成功启动
    sleep 2
    
    if kill -0 "$MCP_PID" 2>/dev/null; then
        # 进程运行正常，保存 PID
        echo "$MCP_PID" > "$MCP_PID_FILE"
        echo "MCP 服务启动成功 (PID: $MCP_PID)"
        echo "日志文件: $MCP_LOG_FILE"
        echo "使用 'tail -f $MCP_LOG_FILE' 查看 MCP 日志"
        echo ""
        echo "MCP 服务访问信息:"
        echo "  - SSE 端点: http://localhost:9000/sse"
        echo "  - 健康检查: http://localhost:9000/health"
    else
        echo "错误: MCP 服务启动失败"
        echo "请查看日志文件: $MCP_LOG_FILE"
        exit 1
    fi
}

# 停止服务器
stop_server() {
    if ! is_running "$PID_FILE"; then
        echo "服务器未运行"
        exit 1
    fi

    PID=$(cat "$PID_FILE")
    echo "正在停止服务器 (PID: $PID)..."
    
    # 尝试优雅停止
    kill "$PID" 2>/dev/null
    
    # 等待进程结束
    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    
    # 如果进程仍在运行，强制杀死
    if kill -0 "$PID" 2>/dev/null; then
        echo "进程未响应，强制停止..."
        kill -9 "$PID" 2>/dev/null
        sleep 1
    fi
    
    # 清理 PID 文件
    if [ -f "$PID_FILE" ]; then
        rm -f "$PID_FILE"
    fi
    
    if kill -0 "$PID" 2>/dev/null; then
        echo "错误: 无法停止服务器"
        exit 1
    else
        echo "服务器已停止"
    fi
}

# 停止 MCP 服务
stop_mcp() {
    if ! is_running "$MCP_PID_FILE"; then
        echo "MCP 服务未运行"
        exit 1
    fi

    PID=$(cat "$MCP_PID_FILE")
    echo "正在停止 MCP 服务 (PID: $PID)..."
    
    # 尝试优雅停止
    kill "$PID" 2>/dev/null
    
    # 等待进程结束
    for i in {1..5}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    
    # 如果进程仍在运行，强制杀死
    if kill -0 "$PID" 2>/dev/null; then
        echo "进程未响应，强制停止..."
        kill -9 "$PID" 2>/dev/null
        sleep 1
    fi
    
    # 清理 PID 文件
    if [ -f "$MCP_PID_FILE" ]; then
        rm -f "$MCP_PID_FILE"
    fi
    
    if kill -0 "$PID" 2>/dev/null; then
        echo "错误: 无法停止 MCP 服务"
        exit 1
    else
        echo "MCP 服务已停止"
    fi
}

# 停止所有服务
stop_all() {
    local has_error=0
    
    # 停止 MCP 服务
    if is_running "$MCP_PID_FILE"; then
        echo "停止 MCP 服务..."
        if ! stop_mcp_internal; then
            has_error=1
        fi
    else
        echo "MCP 服务未运行"
    fi
    
    # 停止主服务器
    if is_running "$PID_FILE"; then
        echo "停止主服务器..."
        if ! stop_server_internal; then
            has_error=1
        fi
    else
        echo "主服务器未运行"
    fi
    
    if [ $has_error -eq 1 ]; then
        exit 1
    fi
}

# 内部停止服务器函数（不输出错误信息）
stop_server_internal() {
    local PID=$(cat "$PID_FILE")
    
    # 尝试优雅停止
    kill "$PID" 2>/dev/null
    
    # 等待进程结束
    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    
    # 如果进程仍在运行，强制杀死
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID" 2>/dev/null
    fi
    
    # 清理 PID 文件
    rm -f "$PID_FILE"
    
    if kill -0 "$PID" 2>/dev/null; then
        return 1
    else
        echo "主服务器已停止"
        return 0
    fi
}

# 内部停止 MCP 函数（不输出错误信息）
stop_mcp_internal() {
    local PID=$(cat "$MCP_PID_FILE")
    
    # 尝试优雅停止
    kill "$PID" 2>/dev/null
    
    # 等待进程结束
    for i in {1..5}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    
    # 如果进程仍在运行，强制杀死
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID" 2>/dev/null
    fi
    
    # 清理 PID 文件
    rm -f "$MCP_PID_FILE"
    
    if kill -0 "$PID" 2>/dev/null; then
        return 1
    else
        echo "MCP 服务已停止"
        return 0
    fi
}

# 查看服务状态
status() {
    echo "===== 服务状态 ====="
    echo ""
    
    # 主服务器状态
    if is_running "$PID_FILE"; then
        PID=$(cat "$PID_FILE")
        echo "主服务器: 运行中 (PID: $PID)"
        echo "  日志: $LOG_FILE"
        echo "  访问: http://localhost:9527"
    else
        echo "主服务器: 未运行"
    fi
    
    echo ""
    
    # MCP 服务状态
    if is_running "$MCP_PID_FILE"; then
        PID=$(cat "$MCP_PID_FILE")
        echo "MCP 服务: 运行中 (PID: $PID)"
        echo "  日志: $MCP_LOG_FILE"
        echo "  SSE 端点: http://localhost:9000/sse"
    else
        echo "MCP 服务: 未运行"
    fi
    
    echo ""
    echo "===================="
}

# 显示使用说明
show_usage() {
    echo "用法: $0 {start|dev|stop|start-mcp|stop-mcp|stop-all|status}"
    echo ""
    echo "主服务器命令:"
    echo "  start     - 启动主服务器（生产模式）"
    echo "  dev       - 启动主服务器（开发模式）"
    echo "  stop      - 停止主服务器"
    echo ""
    echo "MCP 服务命令:"
    echo "  start-mcp - 启动 MCP 中间件服务"
    echo "  stop-mcp  - 停止 MCP 中间件服务"
    echo ""
    echo "其他命令:"
    echo "  stop-all  - 停止所有服务（主服务器 + MCP）"
    echo "  status    - 查看所有服务状态"
    echo ""
    echo "快速启动（开发环境）:"
    echo "  $0 dev && $0 start-mcp"
    echo ""
    echo "环境变量:"
    echo "  生产模式: ENVIRONMENT=production, POSTGRE_FORCE_REBUILD=false"
    echo "  开发模式: ENVIRONMENT=dev, POSTGRE_FORCE_REBUILD=true, POSTGRE_FK_SKIP_VALIDATION=true"
    echo ""
    echo "文件位置:"
    echo "  主服务器 PID: $PID_FILE"
    echo "  MCP PID: $MCP_PID_FILE"
    echo "  主服务器日志: $LOG_FILE"
    echo "  MCP 日志: $MCP_LOG_FILE"
}

# 主逻辑
case "$1" in
    start)
        start_server
        ;;
    dev)
        start_dev_server
        ;;
    stop)
        stop_server
        ;;
    start-mcp)
        start_mcp
        ;;
    stop-mcp)
        stop_mcp
        ;;
    stop-all)
        stop_all
        ;;
    status)
        status
        ;;
    *)
        show_usage
        exit 1
        ;;
esac

exit 0
