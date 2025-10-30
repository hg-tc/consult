#!/bin/bash
# =============================================================================
# AI咨询平台 - 系统启动脚本
# =============================================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="/root/consult"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# 日志文件
LOG_FILE="$PROJECT_ROOT/system.log"

# 函数：打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] ${message}${NC}"
}

# 函数：检查服务是否运行
check_service() {
    local service_name=$1
    local port=$2
    
    if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
        return 0  # 服务运行中
    else
        return 1  # 服务未运行
    fi
}

# 函数：等待服务启动
wait_for_service() {
    local service_name=$1
    local port=$2
    local max_attempts=30
    local attempt=0
    
    print_message $YELLOW "等待 $service_name 服务启动..."
    
    while [ $attempt -lt $max_attempts ]; do
        if check_service "$service_name" "$port"; then
            print_message $GREEN "✅ $service_name 服务已启动 (端口 $port)"
            return 0
        fi
        
        attempt=$((attempt + 1))
        sleep 2
    done
    
    print_message $RED "❌ $service_name 服务启动超时"
    return 1
}

# 函数：启动后端服务
start_backend() {
    print_message $BLUE "🚀 启动后端服务..."
    
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
    fi
    
    # 设置离线模式
    export TRANSFORMERS_OFFLINE=1
    export HF_HUB_OFFLINE=1
    export HF_DATASETS_OFFLINE=1
    
    # 确保本地 SearXNG 服务已就绪（源码方式，无 Docker）
    "$PROJECT_ROOT/scripts/searxng_start_local.sh"

    # 启动后端服务
    nohup python app_simple.py > "$LOG_FILE" 2>&1 &
    BACKEND_PID=$!
    
    # 保存PID
    echo $BACKEND_PID > "$PROJECT_ROOT/backend.pid"
    
    print_message $GREEN "✅ 后端服务已启动 (PID: $BACKEND_PID)"
}

# 函数：启动前端服务
start_frontend() {
    print_message $BLUE "🚀 启动前端服务..."
    
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
    
    # 启动前端开发服务器
    nohup npm run dev > "$PROJECT_ROOT/frontend.log" 2>&1 &
    FRONTEND_PID=$!
    
    # 保存PID
    echo $FRONTEND_PID > "$PROJECT_ROOT/frontend.pid"
    
    print_message $GREEN "✅ 前端服务已启动 (PID: $FRONTEND_PID)"
}

# 函数：启动Nginx
start_nginx() {
    print_message $BLUE "🚀 启动Nginx..."
    
    # 检查Nginx配置
    if [ ! -f "/etc/nginx/sites-available/agent-platform" ]; then
        print_message $RED "❌ Nginx配置文件不存在"
        exit 1
    fi
    
    # 启用站点
    if [ ! -L "/etc/nginx/sites-enabled/agent-platform" ]; then
        ln -sf /etc/nginx/sites-available/agent-platform /etc/nginx/sites-enabled/
    fi
    
    # 测试配置
    if ! nginx -t; then
        print_message $RED "❌ Nginx配置测试失败"
        exit 1
    fi
    
    # 启动Nginx
    nginx
    
    print_message $GREEN "✅ Nginx已启动"
}

# 函数：检查系统状态
check_system_status() {
    print_message $BLUE "📊 检查系统状态..."
    
    # 检查后端服务
    if check_service "后端" "18000"; then
        print_message $GREEN "✅ 后端服务运行正常 (端口 18000)"
    else
        print_message $RED "❌ 后端服务未运行"
    fi
    
    # 检查前端服务
    if check_service "前端" "3000"; then
        print_message $GREEN "✅ 前端服务运行正常 (端口 3000)"
    else
        print_message $RED "❌ 前端服务未运行"
    fi
    
    # 检查Nginx
    if check_service "Nginx" "13000"; then
        print_message $GREEN "✅ Nginx运行正常 (端口 13000)"
    else
        print_message $RED "❌ Nginx未运行"
    fi
    
    # 显示访问地址
    print_message $BLUE "🌐 系统访问地址:"
    print_message $GREEN "   前端界面: http://localhost:13000"
    print_message $GREEN "   后端API: http://localhost:18000"
    print_message $GREEN "   系统状态: http://localhost:18000/api/status"
}

# 主函数
main() {
    print_message $BLUE "🚀 AI咨询平台启动脚本"
    print_message $BLUE "================================"
    
    # 检查是否已运行
    if check_service "后端" "18000" || check_service "前端" "3000"; then
        print_message $YELLOW "⚠️  系统可能已在运行，请先运行 stop.sh"
        exit 1
    fi
    
    # 启动服务
    start_backend
    start_frontend
    start_nginx
    
    # 等待服务启动
    wait_for_service "后端" "18000"
    wait_for_service "前端" "3000"
    
    # 检查系统状态
    check_system_status
    
    print_message $GREEN "🎉 系统启动完成！"
    print_message $BLUE "📝 日志文件: $LOG_FILE"
    print_message $BLUE "📝 前端日志: $PROJECT_ROOT/frontend.log"
}

# 运行主函数
main "$@"