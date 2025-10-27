#!/bin/bash
# =============================================================================
# AI咨询平台 - 前端服务前台启动脚本
# =============================================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="/root/consult"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# 函数：打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] ${message}${NC}"
}

# 检查并杀死已存在的前端进程
print_message $YELLOW "🛑 检查并停止现有前端服务..."
if [ -f "$PROJECT_ROOT/frontend.pid" ]; then
    PID=$(cat "$PROJECT_ROOT/frontend.pid")
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID 2>/dev/null
        print_message $GREEN "✅ 已停止前端服务 (PID: $PID)"
    fi
    rm -f "$PROJECT_ROOT/frontend.pid"
fi

# 检查并杀死占用端口的进程
FRONTEND_PORT=3000
if netstat -tlnp 2>/dev/null | grep -q ":$FRONTEND_PORT "; then
    print_message $YELLOW "发现占用端口 $FRONTEND_PORT 的进程，正在停止..."
    PID=$(netstat -tlnp 2>/dev/null | grep ":$FRONTEND_PORT " | awk '{print $7}' | cut -d'/' -f1 | head -1)
    if [ ! -z "$PID" ]; then
        kill $PID 2>/dev/null
        sleep 2
    fi
fi

# 检查并启动Nginx
print_message $YELLOW "🛑 检查并停止现有Nginx服务..."
NGINX_PORT=13000
if netstat -tlnp 2>/dev/null | grep -q ":$NGINX_PORT "; then
    PID=$(netstat -tlnp 2>/dev/null | grep ":$NGINX_PORT " | awk '{print $7}' | cut -d'/' -f1 | head -1)
    if [ ! -z "$PID" ]; then
        kill $PID 2>/dev/null
        sleep 1
    fi
fi

# 启动Nginx
print_message $BLUE "🚀 启动Nginx..."

# 启用站点
if [ ! -L "/etc/nginx/sites-enabled/agent-platform" ]; then
    ln -sf /etc/nginx/sites-available/agent-platform /etc/nginx/sites-enabled/
fi

# 测试配置并启动
if nginx -t 2>/dev/null; then
    nginx 2>/dev/null
    print_message $GREEN "✅ Nginx已启动 (端口 $NGINX_PORT)"
else
    print_message $YELLOW "⚠️  Nginx配置有问题，但继续启动前端"
fi

# 启动前端服务
print_message $BLUE "🚀 启动前端服务（前台模式）..."
print_message $BLUE "按 Ctrl+C 停止服务（会同时停止前端和Nginx）"

cd "$FRONTEND_DIR"

# 检查Node.js环境
if ! command -v node &> /dev/null; then
    print_message $RED "❌ Node.js 未安装"
    exit 1
fi

# 检查依赖
if [ ! -d "node_modules" ]; then
    print_message $YELLOW "📦 安装前端依赖..."
    npm install
fi

print_message $GREEN "📝 Node.js: $(node -v)"
print_message $GREEN "📝 npm: $(npm -v)"
print_message $GREEN "================================"

# 前台运行（实时显示日志）
npm run dev

