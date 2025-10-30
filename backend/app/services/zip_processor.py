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
import unicodedata

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
    
    # 支持的文件类型（包括图片文件）
    SUPPORTED_EXTENSIONS = [
        '.pdf', '.docx', '.doc', 
        '.txt', '.md', 
        '.xlsx', '.xls', '.pptx', '.ppt',
        '.csv', '.json', '.sql',
        # 图片文件类型
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'
    ]
    
    # 支持的归档格式
    ARCHIVE_EXTENSIONS = ['.zip', '.rar']
    
    # 需要忽略的文件夹和文件
    IGNORE_PATTERNS = [
        '__MACOSX', '.DS_Store', 'Thumbs.db',
        '.git', '.svn', 'node_modules'
    ]
    
    @staticmethod
    def _prefer_chinese_decoding(original: str, candidate: str) -> bool:
        """简单启发式：若候选文本包含更多中日韩字符，且非空，则认为更优。"""
        def cjk_count(s: str) -> int:
            return sum(1 for ch in s if (
                '\u4e00' <= ch <= '\u9fff' or  # CJK Unified
                '\u3400' <= ch <= '\u4dbf' or  # CJK Ext A
                '\uf900' <= ch <= '\ufaff' or  # CJK Compatibility Ideographs
                '\u3040' <= ch <= '\u30ff' or  # JP Kana
                '\uac00' <= ch <= '\ud7af'     # Hangul
            ))
        return cjk_count(candidate) > cjk_count(original) and candidate.strip() != ''

    @staticmethod
    def _decode_zip_filename(name: str) -> str:
        """尝试将因 CP437 解码导致的乱码还原为 GB18030（常见于中文 Windows 打包）。"""
        try:
            # zipfile 在未设置 UTF-8 标志时使用 CP437 解码为 str，这里尝试逆向回 bytes 再用 GB18030 还原
            raw_bytes = name.encode('cp437', errors='ignore')
            candidate = raw_bytes.decode('gb18030', errors='ignore')
            if ZipProcessor._prefer_chinese_decoding(name, candidate):
                return candidate
        except Exception:
            pass
        return name

    @staticmethod
    def _sanitize_relative_name(name: str, max_component_len: int = 120) -> str:
        """规范化并截断路径，避免因超长/非法字符导致解压失败。
        - Unicode 规范化（NFKC）
        - 替换非法字符（这里主要针对 POSIX，保留中文；过滤控制字符）
        - 对每个路径组件截断到 max_component_len
        """
        # 统一规范化
        name = unicodedata.normalize('NFKC', name)
        # 替换控制字符为下划线
        safe = ''.join(ch if (ch >= ' ' and ch != '\\') else '_' for ch in name)
        # 拆分并逐段截断
        parts = [p[:max_component_len] if p else p for p in safe.split('/')]
        # 去除可能出现的空组件
        parts = [p for p in parts if p not in (None, '', '.')]
        return '/'.join(parts)
    
    @staticmethod
    async def extract_archive(archive_path: str, extract_to: str, max_depth: int = 5, archive_name: str = None) -> List[Dict]:
        """
        解压归档文件（ZIP或RAR）并返回文件列表（支持递归解压嵌套压缩文件）
        
        Args:
            archive_path: 归档文件路径
            extract_to: 解压目标目录
            max_depth: 最大递归深度（防止无限递归）
            archive_name: 压缩包名称（用于构建层级路径）
            
        Returns:
            文件信息列表，每个文件包含层级路径信息
        """
        file_ext = Path(archive_path).suffix.lower()
        
        if archive_name is None:
            archive_name = Path(archive_path).stem
        
        if file_ext == '.zip':
            return await ZipProcessor.extract_zip(archive_path, extract_to, max_depth=max_depth, top_level_archive_name=archive_name)
        elif file_ext == '.rar':
            return await ZipProcessor.extract_rar(archive_path, extract_to, max_depth=max_depth, top_level_archive_name=archive_name)
        else:
            raise ValueError(f"不支持的归档格式: {file_ext}")
    
    @staticmethod
    async def extract_zip(zip_path: str, extract_to: str, max_depth: int = 5, current_depth: int = 0, parent_path: str = "", top_level_archive_name: str = None, archive_hierarchy: str = "") -> List[Dict]:
        """
        解压ZIP文件并返回文件列表（支持递归解压嵌套压缩文件）
        
        Args:
            zip_path: ZIP文件路径
            extract_to: 解压目标目录
            max_depth: 最大递归深度
            current_depth: 当前递归深度
            parent_path: 父路径（用于构建相对路径）
            top_level_archive_name: 顶级压缩包名称
            archive_hierarchy: 压缩包层级路径（如：archive1/archive2）
            
        Returns:
            文件信息列表，每个元素包含:
            - file_path: 文件路径
            - relative_path: 相对ZIP内的路径
            - hierarchy_path: 完整层级路径（包括压缩包名称和文件夹结构）
            - archive_name: 顶级压缩包名称
            - archive_hierarchy: 压缩包层级路径
            - file_size: 文件大小
            - file_type: 文件类型
        """
        extracted_files = []
        extract_dir = Path(extract_to)
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        # 防止无限递归
        if current_depth >= max_depth:
            logger.warning(f"[ZIP] 达到最大递归深度 {max_depth}，跳过嵌套压缩文件: {zip_path}")
            return extracted_files
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # 获取所有文件列表
                file_list = zip_ref.namelist()
                
                logger.info(f"[ZIP] 开始解压ZIP文件 (深度 {current_depth}): {zip_path}, 包含 {len(file_list)} 个文件")
                
                # 先解压所有文件到临时目录
                nested_archives = []
                
                for file_info in zip_ref.infolist():
                    # 检查是否应该忽略
                    if ZipProcessor._should_ignore(file_info.filename):
                        continue
                    
                    try:
                        # 准备安全文件名与目标路径（避免原始过长名称导致 extract 失败）
                        original_zip_name = file_info.filename
                        decoded_name = ZipProcessor._decode_zip_filename(original_zip_name)
                        safe_name = ZipProcessor._sanitize_relative_name(decoded_name)
                        target_path = extract_dir / safe_name
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # 以流方式写入，避免使用 extract 导致过长文件名报错
                        with zip_ref.open(file_info, 'r') as src, open(target_path, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                        file_path = target_path
                        
                        # 跳过目录
                        if file_path.is_dir():
                            continue
                        
                        # 检查文件扩展名
                        file_ext = Path(safe_name).suffix.lower()
                        
                        # 检查是否是嵌套的压缩文件
                        if file_ext in ZipProcessor.ARCHIVE_EXTENSIONS:
                            # 记录嵌套压缩文件，稍后递归处理
                            nested_archives.append({
                                'archive_path': str(file_path),
                                'relative_path': safe_name,
                                'original_filename': Path(safe_name).name
                            })
                            logger.info(f"[ZIP] 发现嵌套压缩文件: {safe_name}")
                            continue
                        
                        # 检查是否是支持的文件类型（包括图片）
                        if file_ext in ZipProcessor.SUPPORTED_EXTENSIONS:
                            if file_path.exists() and file_path.is_file():
                                # 构建相对路径
                                relative_path = f"{parent_path}/{safe_name}".lstrip('/') if parent_path else safe_name
                                
                                # 构建完整层级路径（用于唯一标识和显示）
                                # 格式：压缩包名/嵌套压缩包/文件夹/文件名
                                hierarchy_parts = []
                                if top_level_archive_name:
                                    hierarchy_parts.append(top_level_archive_name)
                                if archive_hierarchy:
                                    hierarchy_parts.append(archive_hierarchy)
                                
                                # 提取文件夹路径（去掉文件名）
                                dir_path = str(Path(safe_name).parent)
                                if dir_path and dir_path != '.':
                                    hierarchy_parts.append(dir_path)
                                
                                hierarchy_path = '/'.join(hierarchy_parts) if hierarchy_parts else ''
                                full_hierarchy_path = f"{hierarchy_path}/{Path(safe_name).name}" if hierarchy_path else Path(safe_name).name
                                
                                extracted_files.append({
                                    'file_path': str(file_path),
                                    'relative_path': relative_path,
                                    'hierarchy_path': full_hierarchy_path,  # 完整层级路径
                                    'archive_name': top_level_archive_name or Path(zip_path).stem,
                                    'archive_hierarchy': archive_hierarchy,  # 嵌套压缩包路径
                                    'folder_path': dir_path if dir_path and dir_path != '.' else '',  # 文件夹路径
                                    'file_size': file_info.file_size,
                                    'file_type': file_ext,
                                    'original_filename': Path(safe_name).name,
                                    'original_zip_filename': original_zip_name
                                })
                                logger.info(f"[ZIP] 解压文件: {full_hierarchy_path} ({file_info.file_size} bytes)")
                        else:
                            logger.debug(f"[ZIP] 跳过不支持的文件类型: {safe_name} (类型: {file_ext})")
                            
                    except Exception as e:
                        logger.warning(f"[ZIP] 解压文件失败: {file_info.filename}, 错误: {e}")
                        continue
                
                # 递归处理嵌套的压缩文件
                for nested_archive in nested_archives:
                    try:
                        # 创建嵌套解压目录
                        nested_extract_dir = extract_dir / Path(nested_archive['relative_path']).stem
                        nested_extract_dir.mkdir(parents=True, exist_ok=True)
                        
                        # 构建嵌套路径前缀
                        nested_parent_path = f"{parent_path}/{Path(nested_archive['relative_path']).stem}".lstrip('/') if parent_path else Path(nested_archive['relative_path']).stem
                        
                        # 递归解压嵌套压缩文件
                        if nested_archive['archive_path'].endswith('.zip'):
                            nested_files = await ZipProcessor.extract_zip(
                                nested_archive['archive_path'],
                                str(nested_extract_dir),
                                max_depth=max_depth,
                                current_depth=current_depth + 1,
                                parent_path=nested_parent_path,
                                top_level_archive_name=top_level_archive_name,
                                archive_hierarchy=(f"{archive_hierarchy}/{Path(nested_archive['relative_path']).stem}".lstrip('/') if archive_hierarchy else Path(nested_archive['relative_path']).stem)
                            )
                        elif nested_archive['archive_path'].endswith('.rar'):
                            nested_files = await ZipProcessor.extract_rar(
                                nested_archive['archive_path'],
                                str(nested_extract_dir),
                                max_depth=max_depth,
                                current_depth=current_depth + 1,
                                parent_path=nested_parent_path
                            )
                        else:
                            nested_files = []
                        
                        # 将嵌套文件添加到结果列表
                        extracted_files.extend(nested_files)
                        
                        # 删除已处理的嵌套压缩文件（已解压，不再需要）
                        try:
                            Path(nested_archive['archive_path']).unlink()
                            logger.debug(f"[ZIP] 已删除嵌套压缩文件: {nested_archive['archive_path']}")
                        except Exception as e:
                            logger.warning(f"[ZIP] 删除嵌套压缩文件失败: {nested_archive['archive_path']}, 错误: {e}")
                            
                    except Exception as e:
                        logger.error(f"[ZIP] 递归解压嵌套压缩文件失败: {nested_archive['archive_path']}, 错误: {e}")
                        continue
                
                logger.info(f"[ZIP] ZIP文件解压完成 (深度 {current_depth})，成功提取 {len(extracted_files)} 个文件")
                
        except zipfile.BadZipFile:
            logger.error(f"[ZIP] 无效的ZIP文件: {zip_path}")
            raise ValueError("无效的ZIP文件")
        except Exception as e:
            logger.error(f"[ZIP] 解压ZIP文件失败: {e}")
            raise
        
        return extracted_files
    
    @staticmethod
    async def extract_rar(rar_path: str, extract_to: str, max_depth: int = 5, current_depth: int = 0, parent_path: str = "", top_level_archive_name: str = None, archive_hierarchy: str = "") -> List[Dict]:
        """
        解压RAR文件并返回文件列表（支持递归解压嵌套压缩文件）
        
        Args:
            rar_path: RAR文件路径
            extract_to: 解压目标目录
            max_depth: 最大递归深度
            current_depth: 当前递归深度
            parent_path: 父路径（用于构建相对路径）
            top_level_archive_name: 顶级压缩包名称
            archive_hierarchy: 压缩包层级路径（如：archive1/archive2）
            
        Returns:
            文件信息列表，每个元素包含层级路径信息
        """
        extracted_files = []
        extract_dir = Path(extract_to)
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        # 防止无限递归
        if current_depth >= max_depth:
            logger.warning(f"[RAR] 达到最大递归深度 {max_depth}，跳过嵌套压缩文件: {rar_path}")
            return extracted_files
        
        if not RARFILE_AVAILABLE:
            raise ValueError("rarfile库未安装，无法处理RAR文件。请运行: pip install rarfile")
        
        try:
            with rarfile.RarFile(rar_path, 'r') as rar_ref:
                # 获取所有文件列表
                file_list = rar_ref.namelist()
                
                logger.info(f"[RAR] 开始解压RAR文件 (深度 {current_depth}): {rar_path}, 包含 {len(file_list)} 个文件")
                
                # 先解压所有文件到临时目录
                nested_archives = []
                
                for file_info in rar_ref.infolist():
                    # 跳过目录
                    if file_info.is_dir():
                        continue
                    
                    # 检查是否应该忽略
                    if ZipProcessor._should_ignore(file_info.filename):
                        continue
                    
                    try:
                        # 准备安全文件名与目标路径（避免原始过长名称导致 extract 失败）
                        original_rar_name = file_info.filename
                        decoded_name = ZipProcessor._decode_zip_filename(original_rar_name)
                        safe_name = ZipProcessor._sanitize_relative_name(decoded_name)
                        target_path = extract_dir / safe_name
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # 以流方式写入
                        with rar_ref.open(file_info) as src, open(target_path, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                        file_path = target_path
                        
                        # 验证文件是否真的存在且为文件
                        if not file_path.exists() or not file_path.is_file():
                            continue
                        
                        # 检查文件扩展名
                        file_ext = Path(safe_name).suffix.lower()
                        
                        # 检查是否是嵌套的压缩文件
                        if file_ext in ZipProcessor.ARCHIVE_EXTENSIONS:
                            # 记录嵌套压缩文件，稍后递归处理
                            nested_archives.append({
                                'archive_path': str(file_path),
                                'relative_path': safe_name,
                                'original_filename': Path(safe_name).name
                            })
                            logger.info(f"[RAR] 发现嵌套压缩文件: {safe_name}")
                            continue
                        
                        # 检查是否是支持的文件类型（包括图片）
                        if file_ext in ZipProcessor.SUPPORTED_EXTENSIONS:
                            # 构建相对路径
                            relative_path = f"{parent_path}/{safe_name}".lstrip('/') if parent_path else safe_name
                            
                            # 构建完整层级路径（用于唯一标识和显示）
                            hierarchy_parts = []
                            if top_level_archive_name:
                                hierarchy_parts.append(top_level_archive_name)
                            if archive_hierarchy:
                                hierarchy_parts.append(archive_hierarchy)
                            
                            # 提取文件夹路径（去掉文件名）
                            dir_path = str(Path(safe_name).parent)
                            if dir_path and dir_path != '.':
                                hierarchy_parts.append(dir_path)
                            
                            hierarchy_path = '/'.join(hierarchy_parts) if hierarchy_parts else ''
                            full_hierarchy_path = f"{hierarchy_path}/{Path(safe_name).name}" if hierarchy_path else Path(safe_name).name
                            
                            extracted_files.append({
                                'file_path': str(file_path),
                                'relative_path': relative_path,
                                'hierarchy_path': full_hierarchy_path,  # 完整层级路径
                                'archive_name': top_level_archive_name or Path(rar_path).stem,
                                'archive_hierarchy': archive_hierarchy,  # 嵌套压缩包路径
                                'folder_path': dir_path if dir_path and dir_path != '.' else '',  # 文件夹路径
                                'file_size': file_info.file_size,
                                'file_type': file_ext,
                                'original_filename': Path(safe_name).name,
                                'original_zip_filename': original_rar_name
                            })
                            logger.info(f"[RAR] 解压文件: {full_hierarchy_path} ({file_info.file_size} bytes)")
                        else:
                            logger.debug(f"[RAR] 跳过不支持的文件类型: {safe_name} (类型: {file_ext})")
                            
                    except Exception as e:
                        logger.warning(f"[RAR] 解压文件失败: {file_info.filename}, 错误: {e}")
                        continue
                
                # 递归处理嵌套的压缩文件
                for nested_archive in nested_archives:
                    try:
                        # 创建嵌套解压目录
                        nested_extract_dir = extract_dir / Path(nested_archive['relative_path']).stem
                        nested_extract_dir.mkdir(parents=True, exist_ok=True)
                        
                        # 构建嵌套路径前缀
                        nested_parent_path = f"{parent_path}/{Path(nested_archive['relative_path']).stem}".lstrip('/') if parent_path else Path(nested_archive['relative_path']).stem
                        
                        # 构建嵌套压缩包的层级路径
                        nested_archive_name = Path(nested_archive['relative_path']).stem
                        nested_archive_hierarchy = f"{archive_hierarchy}/{nested_archive_name}".lstrip('/') if archive_hierarchy else nested_archive_name
                        
                        # 递归解压嵌套压缩文件
                        if nested_archive['archive_path'].endswith('.zip'):
                            nested_files = await ZipProcessor.extract_zip(
                                nested_archive['archive_path'],
                                str(nested_extract_dir),
                                max_depth=max_depth,
                                current_depth=current_depth + 1,
                                parent_path=nested_parent_path,
                                top_level_archive_name=top_level_archive_name or Path(rar_path).stem,
                                archive_hierarchy=nested_archive_hierarchy
                            )
                        elif nested_archive['archive_path'].endswith('.rar'):
                            nested_files = await ZipProcessor.extract_rar(
                                nested_archive['archive_path'],
                                str(nested_extract_dir),
                                max_depth=max_depth,
                                current_depth=current_depth + 1,
                                parent_path=nested_parent_path,
                                top_level_archive_name=top_level_archive_name or Path(rar_path).stem,
                                archive_hierarchy=nested_archive_hierarchy
                            )
                        else:
                            nested_files = []
                        
                        # 将嵌套文件添加到结果列表
                        extracted_files.extend(nested_files)
                        
                        # 删除已处理的嵌套压缩文件（已解压，不再需要）
                        try:
                            Path(nested_archive['archive_path']).unlink()
                            logger.debug(f"[RAR] 已删除嵌套压缩文件: {nested_archive['archive_path']}")
                        except Exception as e:
                            logger.warning(f"[RAR] 删除嵌套压缩文件失败: {nested_archive['archive_path']}, 错误: {e}")
                            
                    except Exception as e:
                        logger.error(f"[RAR] 递归解压嵌套压缩文件失败: {nested_archive['archive_path']}, 错误: {e}")
                        continue
                
                logger.info(f"[RAR] RAR文件解压完成 (深度 {current_depth})，成功提取 {len(extracted_files)} 个文件")
                
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
