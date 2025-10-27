#!/bin/bash
# Agent Service Platform 监控脚本
# 此脚本会持续监控应用是否在运行，如果停止了会自动重启

LOG_FILE="/root/consult/frontend/agent-platform.log"

echo "$(date): 监控脚本启动" >> "$LOG_FILE"

while true; do
    # 检查应用是否在运行
    if ! pgrep -f "next dev.*0.0.0.0.*13000" > /dev/null; then
        echo "$(date): 检测到应用未运行，正在重启..." >> "$LOG_FILE"

        # 确保防火墙规则存在
        if command -v iptables &> /dev/null; then
            iptables -C INPUT -p tcp --dport 13000 -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 13000 -j ACCEPT
        fi

        # 启动应用
        cd /root/consult/frontend
        nohup ./start-agent-platform.sh >> "$LOG_FILE" 2>&1 &

        echo "$(date): 应用已重启" >> "$LOG_FILE"
    fi

    # 每30秒检查一次
    sleep 30
done
