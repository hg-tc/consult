"""
归档文件处理服务 - 解压ZIP和RAR并批量处理文件
"""

import zipfile
import logging
import os
import shutil
from pathlib import Path
from typing import List, Dict
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

# 尝试导入rarfile库
try:
    import rarfile
    RARFILE_AVAILABLE = True
except ImportError:
    RARFILE_AVAILABLE = False
    logger.warning("rarfile库未安装，RAR文件功能将不可用。安装命令: pip install rarfile")


class ZipProcessor:
    """归档文件处理器 (支持ZIP和RAR)"""
    
    # 支持的文件类型
    SUPPORTED_EXTENSIONS = [
        '.pdf', '.docx', '.doc', 
        '.txt', '.md', 
        '.xlsx', '.xls', '.pptx', '.ppt',
        '.csv', '.json', '.sql'
    ]
    
    # 支持的归档格式
    ARCHIVE_EXTENSIONS = ['.zip', '.rar']
    
    # 需要忽略的文件夹和文件
    IGNORE_PATTERNS = [
        '__MACOSX', '.DS_Store', 'Thumbs.db',
        '.git', '.svn', 'node_modules'
    ]
    
    @staticmethod
    async def extract_archive(archive_path: str, extract_to: str) -> List[Dict]:
        """
        解压归档文件（ZIP或RAR）并返回文件列表
        
        Args:
            archive_path: 归档文件路径
            extract_to: 解压目标目录
            
        Returns:
            文件信息列表
        """
        file_ext = Path(archive_path).suffix.lower()
        
        if file_ext == '.zip':
            return await ZipProcessor.extract_zip(archive_path, extract_to)
        elif file_ext == '.rar':
            return await ZipProcessor.extract_rar(archive_path, extract_to)
        else:
            raise ValueError(f"不支持的归档格式: {file_ext}")
    
    @staticmethod
    async def extract_zip(zip_path: str, extract_to: str) -> List[Dict]:
        """
        解压ZIP文件并返回文件列表
        
        Args:
            zip_path: ZIP文件路径
            extract_to: 解压目标目录
            
        Returns:
            文件信息列表，每个元素包含:
            - file_path: 文件路径
            - relative_path: 相对ZIP内的路径
            - file_size: 文件大小
            - file_type: 文件类型
        """
        extracted_files = []
        extract_dir = Path(extract_to)
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # 获取所有文件列表
                file_list = zip_ref.namelist()
                
                logger.info(f"[ZIP] 开始解压ZIP文件: {zip_path}, 包含 {len(file_list)} 个文件")
                
                for file_info in zip_ref.infolist():
                    # 检查是否应该忽略
                    if ZipProcessor._should_ignore(file_info.filename):
                        continue
                    
                    # 检查文件扩展名
                    file_ext = Path(file_info.filename).suffix.lower()
                    if file_ext in ZipProcessor.SUPPORTED_EXTENSIONS:
                        try:
                            # 解压文件
                            zip_ref.extract(file_info, extract_dir)
                            
                            file_path = extract_dir / file_info.filename
                            
                            # 验证文件是否真的存在且为文件（不是目录）
                            if file_path.exists() and file_path.is_file():
                                extracted_files.append({
                                    'file_path': str(file_path),
                                    'relative_path': file_info.filename,
                                    'file_size': file_info.file_size,
                                    'file_type': file_ext,
                                    'original_filename': Path(file_info.filename).name
                                })
                                logger.info(f"[ZIP] 解压文件: {file_info.filename} ({file_info.file_size} bytes)")
                        except Exception as e:
                            logger.warning(f"[ZIP] 解压文件失败: {file_info.filename}, 错误: {e}")
                            continue
                    else:
                        logger.debug(f"[ZIP] 跳过不支持的文件类型: {file_info.filename} (类型: {file_ext})")
                
                logger.info(f"[ZIP] ZIP文件解压完成，成功提取 {len(extracted_files)} 个文件")
                
        except zipfile.BadZipFile:
            logger.error(f"[ZIP] 无效的ZIP文件: {zip_path}")
            raise ValueError("无效的ZIP文件")
        except Exception as e:
            logger.error(f"[ZIP] 解压ZIP文件失败: {e}")
            raise
        
        return extracted_files
    
    @staticmethod
    async def extract_rar(rar_path: str, extract_to: str) -> List[Dict]:
        """
        解压RAR文件并返回文件列表
        
        Args:
            rar_path: RAR文件路径
            extract_to: 解压目标目录
            
        Returns:
            文件信息列表
        """
        extracted_files = []
        extract_dir = Path(extract_to)
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        if not RARFILE_AVAILABLE:
            raise ValueError("rarfile库未安装，无法处理RAR文件。请运行: pip install rarfile")
        
        try:
            with rarfile.RarFile(rar_path, 'r') as rar_ref:
                # 获取所有文件列表
                file_list = rar_ref.namelist()
                
                logger.info(f"[RAR] 开始解压RAR文件: {rar_path}, 包含 {len(file_list)} 个文件")
                
                for file_info in rar_ref.infolist():
                    # 跳过目录
                    if file_info.is_dir():
                        continue
                    
                    # 检查是否应该忽略
                    if ZipProcessor._should_ignore(file_info.filename):
                        continue
                    
                    # 检查文件扩展名
                    file_ext = Path(file_info.filename).suffix.lower()
                    if file_ext in ZipProcessor.SUPPORTED_EXTENSIONS:
                        try:
                            # 解压文件
                            rar_ref.extract(file_info, extract_dir)
                            
                            file_path = extract_dir / file_info.filename
                            
                            # 验证文件是否真的存在且为文件
                            if file_path.exists() and file_path.is_file():
                                extracted_files.append({
                                    'file_path': str(file_path),
                                    'relative_path': file_info.filename,
                                    'file_size': file_info.file_size,
                                    'file_type': file_ext,
                                    'original_filename': Path(file_info.filename).name
                                })
                                logger.info(f"[RAR] 解压文件: {file_info.filename} ({file_info.file_size} bytes)")
                        except Exception as e:
                            logger.warning(f"[RAR] 解压文件失败: {file_info.filename}, 错误: {e}")
                            continue
                    else:
                        logger.debug(f"[RAR] 跳过不支持的文件类型: {file_info.filename} (类型: {file_ext})")
                
                logger.info(f"[RAR] RAR文件解压完成，成功提取 {len(extracted_files)} 个文件")
                
        except rarfile.RarCannotExec:
            logger.error(f"[RAR] 无法执行RAR解压，可能缺少unrar工具")
            raise ValueError("RAR解压失败：需要安装unrar工具")
        except rarfile.BadRarFile:
            logger.error(f"[RAR] 无效的RAR文件: {rar_path}")
            raise ValueError("无效的RAR文件")
        except Exception as e:
            logger.error(f"[RAR] 解压RAR文件失败: {e}")
            raise
        
        return extracted_files
    
    @staticmethod
    def _should_ignore(filename: str) -> bool:
        """检查文件是否应该被忽略"""
        # 检查是否包含应该忽略的模式
        for pattern in ZipProcessor.IGNORE_PATTERNS:
            if pattern in filename:
                return True
        
        # 检查是否以斜杠结尾（目录）
        if filename.endswith('/'):
            return True
            
        # 检查是否在忽略的路径中
        parts = filename.split('/')
        for part in parts:
            if part.startswith('.') and part != '.' and part != '..':
                return True
        
        return False
    
    @staticmethod
    async def cleanup_extracted_files(extract_dir: str):
        """清理解压的文件"""
        try:
            extract_path = Path(extract_dir)
            if extract_path.exists():
                shutil.rmtree(extract_path)
                logger.info(f"[ZIP] 清理解压目录: {extract_dir}")
        except Exception as e:
            logger.warning(f"[ZIP] 清理解压目录失败: {extract_dir}, 错误: {e}")
    
    @staticmethod
    def organize_files_by_type(files: List[Dict]) -> Dict[str, List[Dict]]:
        """按文件类型组织文件"""
        organized = {}
        for file_info in files:
            file_type = file_info['file_type']
            if file_type not in organized:
                organized[file_type] = []
            organized[file_type].append(file_info)
        return organized
