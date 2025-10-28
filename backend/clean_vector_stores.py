#!/usr/bin/env python3
"""
清理不兼容的向量存储
用于解决 Pydantic 版本兼容性问题
"""

import os
import shutil
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_vector_stores():
    """清理所有向量存储"""
    
    # 查找所有可能的向量存储目录
    storage_dirs = [
        "langchain_vector_db",
        "global_db", 
        "llamaindex_storage",
        "backend/langchain_vector_db",
        "backend/global_db",
        "backend/llamaindex_storage",
    ]
    
    cleaned = []
    skipped = []
    
    for storage_dir in storage_dirs:
        path = Path(storage_dir)
        if path.exists():
            logger.info(f"找到向量存储目录: {path}")
            
            # 备份目录名
            backup_path = path.parent / f"{path.name}_backup"
            
            # 如果备份已存在，先删除
            if backup_path.exists():
                logger.info(f"删除旧的备份: {backup_path}")
                shutil.rmtree(backup_path)
            
            # 移动到备份目录
            shutil.move(str(path), str(backup_path))
            logger.info(f"✅ 已备份到: {backup_path}")
            cleaned.append(path)
        else:
            skipped.append(path)
    
    logger.info("\n" + "="*60)
    logger.info("清理完成！")
    logger.info(f"已清理 {len(cleaned)} 个向量存储目录")
    logger.info(f"已跳过 {len(skipped)} 个不存在的目录")
    
    if cleaned:
        logger.info("\n备份位置:")
        for path in cleaned:
            backup_path = path.parent / f"{path.name}_backup"
            logger.info(f"  - {backup_path}")
        
        logger.info("\n⚠️  重要提示:")
        logger.info("1. 请重新上传文档到系统中")
        logger.info("2. 如果需要恢复旧数据，可以从备份目录恢复")
        logger.info("3. 确认新数据正常后，可以删除备份目录")

if __name__ == "__main__":
    print("⚠️  警告：此操作将备份所有向量存储！")
    print("即将清理的目录:")
    print("  - langchain_vector_db")
    print("  - global_db")
    print("  - llamaindex_storage")
    print()
    
    confirm = input("确认继续？(yes/no): ")
    
    if confirm.lower() in ['yes', 'y']:
        clean_vector_stores()
    else:
        print("已取消操作")

