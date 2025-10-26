#!/bin/bash
# Agent Service Platform 启动脚本

cd /root/workspace/consult/frontend

# 检查Node.js是否安装
if ! command -v node &> /dev/null; then
    echo "Node.js 未安装，正在安装..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
    apt-get install -y nodejs
fi

# 检查依赖是否安装
if [ ! -d "node_modules" ]; then
    echo "安装项目依赖..."
    npm install --legacy-peer-deps
fi

# 恢复防火墙规则（如果需要）
if command -v iptables &> /dev/null; then
    echo "配置防火墙规则..."
    if [ -f "/root/workspace/consult/frontend/iptables-rules.backup" ]; then
        iptables-restore < /root/workspace/consult/frontend/iptables-rules.backup
    fi
    # 确保端口13000开放
    iptables -C INPUT -p tcp --dport 13000 -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 13000 -j ACCEPT
fi

# 启动应用
echo "启动 Agent Service Platform..."
npm run dev -- --hostname 0.0.0.0 --port 13000
