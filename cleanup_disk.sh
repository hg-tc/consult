#!/bin/bash
# 磁盘清理脚本

echo "正在清理磁盘空间..."

# 1. 清理旧的构建缓存
if [ -d "/root/consult/frontend/.next" ]; then
    echo "清理 .next 构建缓存..."
    rm -rf /root/consult/frontend/.next
fi

# 2. 清理 Python 缓存
echo "清理 Python 缓存..."
find /root/consult/backend -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find /root/consult/backend -type f -name "*.pyc" -delete 2>/dev/null

# 3. 清空/截断大日志文件（保留文件但清空内容）
if [ -f "/root/consult/backend/debug.log" ]; then
    echo "清空 debug.log..."
    > /root/consult/backend/debug.log
fi

# 4. 清理7天前的任务存储（可选，谨慎使用）
# find /root/consult/backend/task_storage -type f -name "*.json" -mtime +7 -delete 2>/dev/null

echo "清理完成！"
df -h / | tail -1
