#!/usr/bin/env python3
"""
直接启动后端服务（跳过start.sh的问题）
"""
import os
import sys
import uvicorn

# 添加路径
sys.path.insert(0, '/root/workspace/consult/backend')

# 设置工作目录
os.chdir('/root/workspace/consult/backend')

# 导入app
from app_simple import app

if __name__ == "__main__":
    print("🚀 启动后端服务...")
    print("后端服务将在 http://localhost:18000 启动")
    
    # 启动服务
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=18000,
        log_level="info"
    )
