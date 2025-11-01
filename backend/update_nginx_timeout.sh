#!/bin/bash
# 更新nginx超时配置脚本

echo "正在更新nginx超时配置..."

# 备份原配置
if [ -f /etc/nginx/sites-available/agent-platform ]; then
    cp /etc/nginx/sites-available/agent-platform /etc/nginx/sites-available/agent-platform.backup.$(date +%Y%m%d_%H%M%S)
fi

# 更新超时配置
sed -i 's/proxy_connect_timeout 60s/proxy_connect_timeout 300s/g' /etc/nginx/sites-available/agent-platform
sed -i 's/proxy_send_timeout 60s/proxy_send_timeout 300s/g' /etc/nginx/sites-available/agent-platform
sed -i 's/proxy_read_timeout 60s/proxy_read_timeout 300s/g' /etc/nginx/sites-available/agent-platform
sed -i 's/client_body_timeout 60s/client_body_timeout 300s/g' /etc/nginx/sites-available/agent-platform
sed -i 's/client_header_timeout 60s/client_header_timeout 300s/g' /etc/nginx/sites-available/agent-platform

# 测试配置
if nginx -t; then
    echo "✓ nginx配置测试通过"
    echo "正在重新加载nginx..."
    systemctl reload nginx
    echo "✓ nginx已重新加载，超时时间已更新为300秒"
else
    echo "✗ nginx配置测试失败，请检查配置文件"
    exit 1
fi

