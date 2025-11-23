#!/bin/bash -x

# 服务器管理脚本
# 用于启动和停止 kahunabot 服务器

# 获取脚本所在目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 配置
PID_FILE="$SCRIPT_DIR/.server.pid"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/server.log"
PYTHON_CMD="python"
SERVER_SCRIPT="run_server.py"

# 确保日志目录存在
mkdir -p "$LOG_DIR"

# 检查进程是否运行
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            return 0
        else
            # PID 文件存在但进程不存在，清理 PID 文件
            rm -f "$PID_FILE"
            return 1
        fi
    else
        return 1
    fi
}

# 启动服务器（生产模式）
start_server() {
    # 检查是否已经运行
    if is_running; then
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
    if is_running; then
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

# 停止服务器
stop_server() {
    if ! is_running; then
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

# 显示使用说明
show_usage() {
    echo "用法: $0 {start|dev|stop}"
    echo ""
    echo "命令:"
    echo "  start  - 启动服务器（生产模式）"
    echo "  dev    - 启动服务器（开发模式）"
    echo "  stop   - 停止服务器"
    echo ""
    echo "环境变量:"
    echo "  生产模式: ENVIRONMENT=production, POSTGRE_FORCE_REBUILD=false"
    echo "  开发模式: ENVIRONMENT=dev, POSTGRE_FORCE_REBUILD=true, POSTGRE_FK_SKIP_VALIDATION=true"
    echo ""
    echo "文件位置:"
    echo "  PID 文件: $PID_FILE"
    echo "  日志文件: $LOG_FILE"
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
    *)
        show_usage
        exit 1
        ;;
esac

exit 0

