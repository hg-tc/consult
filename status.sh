#!/bin/bash
# =============================================================================
# AI咨询平台 - 系统状态检查脚本
# =============================================================================

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

# 函数：检查服务状态
check_service_status() {
    local service_name=$1
    local port=$2
    local url=$3
    
    if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
        print_message $GREEN "✅ $service_name 服务运行正常 (端口 $port)"
        
        # 测试HTTP连接
        if [ -n "$url" ]; then
            if curl -s --connect-timeout 5 "$url" > /dev/null 2>&1; then
                print_message $GREEN "   HTTP连接正常: $url"
            else
                print_message $YELLOW "   HTTP连接异常: $url"
            fi
        fi
    else
        print_message $RED "❌ $service_name 服务未运行 (端口 $port)"
    fi
}

# 函数：检查进程状态
check_process_status() {
    local service_name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            print_message $GREEN "✅ $service_name 进程运行正常 (PID: $pid)"
        else
            print_message $RED "❌ $service_name 进程不存在 (PID: $pid)"
        fi
    else
        print_message $YELLOW "⚠️  $service_name PID文件不存在"
    fi
}

# 函数：检查系统资源
check_system_resources() {
    print_message $BLUE "📊 系统资源使用情况:"
    
    # CPU使用率
    local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | awk -F'%' '{print $1}')
    print_message $BLUE "   CPU使用率: ${cpu_usage}%"
    
    # 内存使用率
    local mem_usage=$(free | grep Mem | awk '{printf("%.1f%%", $3/$2 * 100.0)}')
    print_message $BLUE "   内存使用率: $mem_usage"
    
    # 磁盘使用率
    local disk_usage=$(df -h / | awk 'NR==2{printf "%s", $5}')
    print_message $BLUE "   磁盘使用率: $disk_usage"
}

# 函数：检查日志文件
check_log_files() {
    print_message $BLUE "📝 日志文件状态:"
    
    # 系统日志
    if [ -f "$PROJECT_ROOT/system.log" ]; then
        local log_size=$(du -h "$PROJECT_ROOT/system.log" | cut -f1)
        print_message $BLUE "   系统日志: $log_size"
    else
        print_message $YELLOW "   系统日志: 不存在"
    fi
    
    # 前端日志
    if [ -f "$PROJECT_ROOT/frontend.log" ]; then
        local log_size=$(du -h "$PROJECT_ROOT/frontend.log" | cut -f1)
        print_message $BLUE "   前端日志: $log_size"
    else
        print_message $YELLOW "   前端日志: 不存在"
    fi
}

# 函数：检查数据库状态
check_database_status() {
    print_message $BLUE "🗄️  数据库状态:"
    
    # 检查向量数据库目录
    local vector_db_dir="$PROJECT_ROOT/backend/langchain_vector_db"
    if [ -d "$vector_db_dir" ]; then
        local workspace_count=$(ls -1 "$vector_db_dir" | wc -l)
        print_message $BLUE "   向量数据库: $workspace_count 个工作区"
        
        # 检查工作区1的文档数量
        local workspace_1_dir="$vector_db_dir/workspace_1"
        if [ -d "$workspace_1_dir" ]; then
            if [ -f "$workspace_1_dir/index.pkl" ]; then
                print_message $BLUE "   工作区1: 有索引文件"
            else
                print_message $YELLOW "   工作区1: 无索引文件"
            fi
        else
            print_message $YELLOW "   工作区1: 不存在"
        fi
    else
        print_message $YELLOW "   向量数据库: 不存在"
    fi
}

# 主函数
main() {
    print_message $BLUE "📊 AI咨询平台系统状态"
    print_message $BLUE "================================"
    
    # 检查服务状态
    print_message $BLUE "🔍 服务状态检查:"
    check_service_status "后端" "18000" "http://localhost:18000/api/status"
    check_service_status "前端" "3000" "http://localhost:3000"
    check_service_status "Nginx" "13000" "http://localhost:13000"
    
    echo ""
    
    # 检查进程状态
    print_message $BLUE "🔍 进程状态检查:"
    check_process_status "后端" "$PROJECT_ROOT/backend.pid"
    check_process_status "前端" "$PROJECT_ROOT/frontend.pid"
    
    echo ""
    
    # 检查系统资源
    check_system_resources
    
    echo ""
    
    # 检查数据库状态
    check_database_status
    
    echo ""
    
    # 检查日志文件
    check_log_files
    
    echo ""
    
    # 显示访问地址
    print_message $BLUE "🌐 系统访问地址:"
    print_message $GREEN "   前端界面: http://localhost:13000"
    print_message $GREEN "   后端API: http://localhost:18000"
    print_message $GREEN "   系统状态: http://localhost:18000/api/status"
    
    echo ""
    print_message $GREEN "✅ 系统状态检查完成！"
}

# 运行主函数
main "$@"