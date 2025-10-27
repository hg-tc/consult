#!/bin/bash
# =============================================================================
# AI咨询平台 - 系统重启脚本
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

# 主函数
main() {
    print_message $BLUE "🔄 AI咨询平台重启脚本"
    print_message $BLUE "================================"
    
    # 停止系统
    print_message $YELLOW "🛑 停止系统..."
    bash "$PROJECT_ROOT/stop.sh"
    
    # 等待一段时间
    print_message $YELLOW "⏳ 等待系统完全停止..."
    sleep 5
    
    # 启动系统
    print_message $YELLOW "🚀 启动系统..."
    bash "$PROJECT_ROOT/start.sh"
    
    print_message $GREEN "🎉 系统重启完成！"
}

# 运行主函数
main "$@"
