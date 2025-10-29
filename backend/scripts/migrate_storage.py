#!/usr/bin/env python3
"""
存储路径迁移脚本
将向量数据库从旧路径迁移到新路径（支持从 /root/consult/backend 迁移到 /home）
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def migrate_storage(
    old_base_path: str,
    new_base_path: str,
    dry_run: bool = False
) -> bool:
    """
    迁移存储数据
    
    Args:
        old_base_path: 旧的基础路径
        new_base_path: 新的基础路径
        dry_run: 如果为 True，只打印将要执行的操作，不实际执行
    
    Returns:
        bool: 是否成功
    """
    old_base = Path(old_base_path)
    new_base = Path(new_base_path)
    
    if not old_base.exists():
        logger.warning(f"旧路径不存在: {old_base_path}，跳过迁移")
        return True
    
    # 需要迁移的目录
    dirs_to_migrate = [
        "llamaindex_storage",
        "langchain_vector_db",
        "cache_storage",
        "global_db",  # 旧的全局数据库路径
        "vector_db",  # 旧的向量数据库路径
    ]
    
    if dry_run:
        logger.info("=== 干运行模式：将执行以下操作 ===")
    else:
        logger.info("=== 开始迁移存储数据 ===")
    
    migrated_count = 0
    for dir_name in dirs_to_migrate:
        old_dir = old_base / dir_name
        new_dir = new_base / dir_name
        
        if not old_dir.exists():
            logger.debug(f"跳过不存在的目录: {old_dir}")
            continue
        
        if dry_run:
            size = sum(f.stat().st_size for f in old_dir.rglob('*') if f.is_file())
            logger.info(f"将迁移: {old_dir} -> {new_dir} ({size / (1024*1024):.2f} MB)")
        else:
            try:
                # 如果新目录已存在，合并（保留新目录的现有文件）
                if new_dir.exists():
                    logger.warning(f"目标目录已存在: {new_dir}，将合并内容")
                    # 复制旧目录中不存在的文件
                    for old_file in old_dir.rglob('*'):
                        if old_file.is_file():
                            rel_path = old_file.relative_to(old_dir)
                            new_file = new_dir / rel_path
                            if not new_file.exists():
                                new_file.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(old_file, new_file)
                                logger.info(f"已复制: {rel_path}")
                else:
                    # 直接移动整个目录
                    new_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(old_dir), str(new_dir))
                    logger.info(f"已移动: {old_dir} -> {new_dir}")
                
                migrated_count += 1
            except Exception as e:
                logger.error(f"迁移失败 {old_dir} -> {new_dir}: {e}")
                return False
    
    if dry_run:
        logger.info("=== 干运行完成（未实际执行迁移） ===")
        return True
    
    logger.info(f"=== 迁移完成，共迁移 {migrated_count} 个目录 ===")
    return True


def create_symlink(old_path: str, new_path: str, dry_run: bool = False) -> bool:
    """
    创建符号链接（可选，用于向后兼容）
    
    Args:
        old_path: 旧路径
        new_path: 新路径
        dry_run: 干运行模式
    """
    old = Path(old_path)
    new = Path(new_path)
    
    if not new.exists():
        logger.warning(f"新路径不存在，无法创建符号链接: {new_path}")
        return False
    
    if old.exists() and not old.is_symlink():
        logger.warning(f"旧路径已存在且不是符号链接: {old_path}")
        return False
    
    if dry_run:
        logger.info(f"将创建符号链接: {old_path} -> {new_path}")
        return True
    
    try:
        if old.exists():
            old.unlink()
        old.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(new.absolute()), str(old))
        logger.info(f"已创建符号链接: {old_path} -> {new_path}")
        return True
    except Exception as e:
        logger.error(f"创建符号链接失败: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="迁移存储路径")
    parser.add_argument(
        "--old-path",
        type=str,
        default="/root/consult/backend",
        help="旧的存储基础路径（默认: /root/consult/backend）"
    )
    parser.add_argument(
        "--new-path",
        type=str,
        default=None,
        help="新的存储基础路径（默认从环境变量 STORAGE_BASE_PATH 获取，或使用 ~/consult_storage）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干运行模式，只显示将要执行的操作"
    )
    parser.add_argument(
        "--create-symlink",
        action="store_true",
        help="创建符号链接以保持向后兼容"
    )
    
    args = parser.parse_args()
    
    # 确定新路径
    if args.new_path:
        new_base = args.new_path
    else:
        new_base = os.getenv(
            "STORAGE_BASE_PATH",
            os.path.join(os.path.expanduser("~"), "consult_storage")
        )
    
    logger.info(f"旧路径: {args.old_path}")
    logger.info(f"新路径: {new_base}")
    logger.info(f"模式: {'干运行' if args.dry_run else '实际执行'}")
    
    # 执行迁移
    success = migrate_storage(
        old_base_path=args.old_path,
        new_base_path=new_base,
        dry_run=args.dry_run
    )
    
    if success and args.create_symlink and not args.dry_run:
        # 创建符号链接
        logger.info("=== 创建符号链接以保持向后兼容 ===")
        from app.core.config import settings
        
        symlinks = [
            ("llamaindex_storage", settings.LLAMAINDEX_STORAGE_PATH),
            ("langchain_vector_db", settings.LANGCHAIN_VECTOR_DB_PATH),
            ("cache_storage", settings.CACHE_STORAGE_PATH),
        ]
        
        old_base = Path(args.old_path)
        for dir_name, new_path in symlinks:
            old_dir = old_base / dir_name
            new_dir = Path(new_path)
            create_symlink(str(old_dir), str(new_dir))
    
    if success:
        logger.info("✅ 迁移成功完成！")
        if not args.dry_run:
            logger.info("请重启服务以使新路径生效")
    else:
        logger.error("❌ 迁移失败！")
        exit(1)

