#!/bin/bash
# =============================================================================
# AI咨询平台 - 后端服务前台启动脚本
# =============================================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="/root/consult"
BACKEND_DIR="$PROJECT_ROOT/backend"

# 函数：打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] ${message}${NC}"
}

# 检查并杀死已存在的后端进程
print_message $YELLOW "🛑 检查并停止现有后端服务..."
if [ -f "$PROJECT_ROOT/backend.pid" ]; then
    PID=$(cat "$PROJECT_ROOT/backend.pid")
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID 2>/dev/null
        print_message $GREEN "✅ 已停止后端服务 (PID: $PID)"
    fi
    rm -f "$PROJECT_ROOT/backend.pid"
fi

# 检查并杀死占用端口的进程
BACKEND_PORT=18000
if netstat -tlnp 2>/dev/null | grep -q ":$BACKEND_PORT "; then
    print_message $YELLOW "发现占用端口 $BACKEND_PORT 的进程，正在停止..."
    PID=$(netstat -tlnp 2>/dev/null | grep ":$BACKEND_PORT " | awk '{print $7}' | cut -d'/' -f1 | head -1)
    if [ ! -z "$PID" ]; then
        kill $PID 2>/dev/null
        sleep 2
    fi
fi

# 启动后端服务
print_message $BLUE "🚀 启动后端服务（前台模式）..."
print_message $BLUE "按 Ctrl+C 停止服务"

cd "$BACKEND_DIR"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    print_message $RED "❌ 虚拟环境不存在，请先运行 setup.sh"
    exit 1
fi

# 激活虚拟环境
source venv/bin/activate

# 加载环境变量
if [ -f ".env" ]; then
    source .env
    print_message $GREEN "✅ 已加载环境变量"
fi

# 设置离线模式
export TRANSFORMERS_OFFLINE=1
export HF_HUB_OFFLINE=1
export HF_DATASETS_OFFLINE=1

print_message $GREEN "📝 虚拟环境已激活"
print_message $GREEN "📝 Python: $(which python)"
print_message $GREEN "================================"

# 前台运行（实时显示日志）
python app_simple.py

