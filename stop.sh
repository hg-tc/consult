#!/bin/bash
# =============================================================================
# AI咨询平台 - 系统停止脚本
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

# 函数：打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] ${message}${NC}"
}

# 函数：停止服务
stop_service() {
    local service_name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            print_message $YELLOW "🛑 停止 $service_name 服务 (PID: $pid)..."
            kill "$pid"
            
            # 等待进程结束
            local count=0
            while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
                sleep 1
                count=$((count + 1))
            done
            
            # 强制杀死进程
            if kill -0 "$pid" 2>/dev/null; then
                print_message $YELLOW "强制停止 $service_name 服务..."
                kill -9 "$pid"
            fi
            
            print_message $GREEN "✅ $service_name 服务已停止"
        else
            print_message $YELLOW "⚠️  $service_name 服务进程不存在"
        fi
        rm -f "$pid_file"
    else
        print_message $YELLOW "⚠️  $service_name PID文件不存在"
    fi
}

# 函数：停止Nginx
stop_nginx() {
    print_message $YELLOW "🛑 停止Nginx..."
    
    # 查找nginx进程
    local nginx_pids=$(pgrep nginx 2>/dev/null || true)
    
    if [ -n "$nginx_pids" ]; then
        print_message $YELLOW "发现Nginx进程: $nginx_pids"
        # 优雅停止
        kill $nginx_pids 2>/dev/null || true
        sleep 2
        
        # 强制停止
        kill -9 $nginx_pids 2>/dev/null || true
        print_message $GREEN "✅ Nginx已停止"
    else
        print_message $YELLOW "⚠️  Nginx未运行"
    fi
}

# 函数：清理进程
cleanup_processes() {
    print_message $BLUE "🧹 清理残留进程..."
    
    # 清理Python进程
    pkill -f "python.*app_simple.py" 2>/dev/null || true
    pkill -f "uvicorn.*app_simple" 2>/dev/null || true
    pkill -f "python.*app_simple" 2>/dev/null || true
    
    # 清理Node.js进程
    pkill -f "next dev" 2>/dev/null || true
    pkill -f "npm.*start" 2>/dev/null || true
    pkill -f "npm.*dev" 2>/dev/null || true
    pkill -f "node.*next" 2>/dev/null || true
    
    # 清理所有相关进程
    pkill -f "consult" 2>/dev/null || true
    
    # 等待进程结束
    sleep 2
    
    # 清理端口占用进程
    local port_80_pid=$(lsof -ti:80 2>/dev/null || true)
    local port_13000_pid=$(lsof -ti:13000 2>/dev/null || true)
    local port_18000_pid=$(lsof -ti:18000 2>/dev/null || true)
    local port_3000_pid=$(lsof -ti:3000 2>/dev/null || true)
    
    if [ -n "$port_80_pid" ]; then
        print_message $YELLOW "强制清理端口80进程: $port_80_pid"
        kill -9 $port_80_pid 2>/dev/null || true
    fi
    
    if [ -n "$port_13000_pid" ]; then
        print_message $YELLOW "强制清理端口13000进程: $port_13000_pid"
        kill -9 $port_13000_pid 2>/dev/null || true
    fi
    
    if [ -n "$port_18000_pid" ]; then
        print_message $YELLOW "强制清理端口18000进程: $port_18000_pid"
        kill -9 $port_18000_pid 2>/dev/null || true
    fi
    
    if [ -n "$port_3000_pid" ]; then
        print_message $YELLOW "强制清理端口3000进程: $port_3000_pid"
        kill -9 $port_3000_pid 2>/dev/null || true
    fi
    
    # 最终检查并强制清理
    local remaining_pids=$(pgrep -f "app_simple\|next\|npm.*dev" 2>/dev/null || true)
    if [ -n "$remaining_pids" ]; then
        print_message $YELLOW "发现残留进程，强制清理: $remaining_pids"
        kill -9 $remaining_pids 2>/dev/null || true
    fi
    
    print_message $GREEN "✅ 进程清理完成"
}

# 函数：检查系统状态
check_system_status() {
    print_message $BLUE "📊 检查系统状态..."
    
    # 检查端口占用
    if netstat -tlnp 2>/dev/null | grep -q ":18000 "; then
        print_message $RED "❌ 后端服务仍在运行 (端口 18000)"
    else
        print_message $GREEN "✅ 后端服务已停止"
    fi
    
    if netstat -tlnp 2>/dev/null | grep -q ":3000 "; then
        print_message $RED "❌ 前端服务仍在运行 (端口 3000)"
    else
        print_message $GREEN "✅ 前端服务已停止"
    fi
    
    if pgrep nginx >/dev/null 2>&1; then
        print_message $RED "❌ Nginx仍在运行"
    else
        print_message $GREEN "✅ Nginx已停止"
    fi
}

# 主函数
main() {
    print_message $BLUE "🛑 AI咨询平台停止脚本"
    print_message $BLUE "================================"
    
    # 停止服务
    # 先停止本地 SearXNG（若有）
    if [ -x "/root/consult/scripts/searxng_stop_local.sh" ]; then
        /root/consult/scripts/searxng_stop_local.sh || true
    fi
    stop_service "后端" "$PROJECT_ROOT/backend.pid"
    stop_service "前端" "$PROJECT_ROOT/frontend.pid"
    stop_nginx
    
    # 清理进程
    cleanup_processes
    
    # 检查系统状态
    check_system_status
    
    print_message $GREEN "🎉 系统停止完成！"
}

# 运行主函数
main "$@"
