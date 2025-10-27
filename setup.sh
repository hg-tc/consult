#!/bin/bash
# =============================================================================
# AI咨询平台 - 系统安装脚本
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

# 函数：打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] ${message}${NC}"
}

# 函数：检查命令是否存在
check_command() {
    local cmd=$1
    if command -v "$cmd" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# 函数：安装系统依赖
install_system_dependencies() {
    print_message $BLUE "📦 安装系统依赖..."
    
    # 更新包列表
    apt-get update
    
    # 安装基础工具
    apt-get install -y curl wget git vim net-tools
    
    # 安装Python3和pip
    if ! check_command python3; then
        apt-get install -y python3 python3-pip python3-venv
    fi
    
    # 安装Node.js
    if ! check_command node; then
        curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
        apt-get install -y nodejs
    fi
    
    # 安装Nginx
    if ! check_command nginx; then
        apt-get install -y nginx
    fi
    
    # 安装系统依赖
    apt-get install -y build-essential libffi-dev libssl-dev
    
    print_message $GREEN "✅ 系统依赖安装完成"
}

# 函数：安装后端依赖
install_backend_dependencies() {
    print_message $BLUE "📦 安装后端依赖..."
    
    cd "$BACKEND_DIR"
    
    # 创建虚拟环境
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 升级pip
    pip install --upgrade pip
    
    # 安装依赖
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    else
        print_message $RED "❌ requirements.txt 不存在"
        exit 1
    fi
    
    print_message $GREEN "✅ 后端依赖安装完成"
}

# 函数：安装前端依赖
install_frontend_dependencies() {
    print_message $BLUE "📦 安装前端依赖..."
    
    cd "$FRONTEND_DIR"
    
    # 检查package.json
    if [ ! -f "package.json" ]; then
        print_message $RED "❌ package.json 不存在"
        exit 1
    fi
    
    # 安装依赖
    npm install
    
    print_message $GREEN "✅ 前端依赖安装完成"
}

# 函数：配置Nginx
configure_nginx() {
    print_message $BLUE "⚙️  配置Nginx..."
    
    # 创建Nginx配置
    cat > /etc/nginx/sites-available/agent-platform << 'EOF'
server {
    listen 80;
    server_name localhost;
    
    # 增加上传限制
    client_max_body_size 50M;
    client_body_timeout 60s;
    client_header_timeout 60s;
    
    # 前端开发服务器代理
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # 增加超时时间
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Next.js静态资源 - 代理到开发服务器
    location /_next/ {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 缓存静态资源
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # 后端API代理
    location /api/ {
        proxy_pass http://127.0.0.1:18000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
        
        # 增加超时时间
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline' 'unsafe-eval'" always;
}
EOF
    
    # 启用站点
    ln -sf /etc/nginx/sites-available/agent-platform /etc/nginx/sites-enabled/
    
    # 删除默认站点
    rm -f /etc/nginx/sites-enabled/default
    
    # 测试配置
    nginx -t
    
    print_message $GREEN "✅ Nginx配置完成"
}

# 函数：创建环境变量文件
create_env_file() {
    print_message $BLUE "⚙️  创建环境变量文件..."
    
    cd "$BACKEND_DIR"
    
    if [ ! -f ".env" ]; then
        cat > .env << 'EOF'
# AI咨询平台环境变量配置

# 第三方API配置
THIRD_PARTY_API_BASE=https://api.qingyuntop.top/v1
THIRD_PARTY_API_KEY=your_api_key_here

# 数据库配置
DATABASE_URL=sqlite:///./consult.db

# 日志配置
LOG_LEVEL=INFO

# 模型配置
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
LLM_MODEL=gpt-3.5-turbo

# 离线模式
TRANSFORMERS_OFFLINE=1
HF_HUB_OFFLINE=1
HF_DATASETS_OFFLINE=1
EOF
        
        print_message $YELLOW "⚠️  请编辑 $BACKEND_DIR/.env 文件，设置正确的API密钥"
    else
        print_message $GREEN "✅ 环境变量文件已存在"
    fi
}

# 函数：设置脚本权限
set_script_permissions() {
    print_message $BLUE "⚙️  设置脚本权限..."
    
    chmod +x "$PROJECT_ROOT"/*.sh
    
    print_message $GREEN "✅ 脚本权限设置完成"
}

# 主函数
main() {
    print_message $BLUE "🚀 AI咨询平台安装脚本"
    print_message $BLUE "================================"
    
    # 检查是否为root用户
    if [ "$EUID" -ne 0 ]; then
        print_message $RED "❌ 请以root用户运行此脚本"
        exit 1
    fi
    
    # 检查项目目录
    if [ ! -d "$PROJECT_ROOT" ]; then
        print_message $RED "❌ 项目目录不存在: $PROJECT_ROOT"
        exit 1
    fi
    
    # 安装系统依赖
    install_system_dependencies
    
    # 安装后端依赖
    install_backend_dependencies
    
    # 安装前端依赖
    install_frontend_dependencies
    
    # 配置Nginx
    configure_nginx
    
    # 创建环境变量文件
    create_env_file
    
    # 设置脚本权限
    set_script_permissions
    
    print_message $GREEN "🎉 系统安装完成！"
    print_message $BLUE "📝 下一步操作:"
    print_message $BLUE "   1. 编辑 $BACKEND_DIR/.env 文件，设置API密钥"
    print_message $BLUE "   2. 运行 ./start.sh 启动系统"
    print_message $BLUE "   3. 访问 http://localhost:13000 使用系统"
}

# 运行主函数
main "$@"
