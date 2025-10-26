"""
工作区文件管理器
处理生成文件的持久化存储和元数据管理
"""

import json
import shutil
import uuid
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class WorkspaceFileManager:
    """工作区文件管理器"""
    
    def __init__(self, storage_dir: str = "workspace_files"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        self.metadata_file = self.storage_dir / "files_metadata.json"
        self.metadata = {}
        self._load_metadata()
    
    def _load_metadata(self):
        """加载文件元数据"""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
            else:
                self.metadata = {}
        except Exception as e:
            logger.error(f"加载文件元数据失败: {e}")
            self.metadata = {}
    
    def _save_metadata(self):
        """保存文件元数据"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存文件元数据失败: {e}")
    
    def save_generated_file(
        self, 
        workspace_id: str,
        file_path: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        保存生成的文件到工作区
        
        Args:
            workspace_id: 工作区ID
            file_path: 原文件路径
            metadata: 文件元数据
            
        Returns:
            str: 文件ID
        """
        try:
            # 1. 生成唯一文件ID
            file_id = str(uuid.uuid4())
            
            # 2. 创建工作区目录
            workspace_dir = self.storage_dir / workspace_id
            workspace_dir.mkdir(parents=True, exist_ok=True)
            
            # 3. 复制文件到工作区目录
            source_path = Path(file_path)
            dest_path = workspace_dir / source_path.name
            
            if source_path.exists():
                shutil.copy2(source_path, dest_path)
            else:
                logger.error(f"源文件不存在: {file_path}")
                raise FileNotFoundError(f"源文件不存在: {file_path}")
            
            # 4. 保存元数据
            self.metadata[file_id] = {
                'workspace_id': workspace_id,
                'file_path': str(dest_path),
                'filename': source_path.name,
                'file_type': metadata.get('doc_type', 'unknown'),
                'file_size': dest_path.stat().st_size,
                'created_at': datetime.now().isoformat(),
                'title': metadata.get('title', '未命名文档'),
                'source_query': metadata.get('source_query', ''),
                'references': metadata.get('references', []),
                'download_count': 0,
                'last_downloaded': None
            }
            
            self._save_metadata()
            
            logger.info(f"文件保存成功: {file_id} -> {dest_path}")
            return file_id
            
        except Exception as e:
            logger.error(f"保存文件失败: {e}")
            raise
    
    def list_workspace_files(self, workspace_id: str) -> List[Dict]:
        """
        列出工作区的所有生成文件
        
        Args:
            workspace_id: 工作区ID
            
        Returns:
            List[Dict]: 文件列表
        """
        files = []
        for file_id, meta in self.metadata.items():
            if meta['workspace_id'] == workspace_id:
                file_info = {**meta, 'id': file_id}
                files.append(file_info)
        
        # 按创建时间倒序排列
        files.sort(key=lambda x: x['created_at'], reverse=True)
        return files
    
    def get_file_info(self, file_id: str) -> Optional[Dict]:
        """
        获取文件信息
        
        Args:
            file_id: 文件ID
            
        Returns:
            Optional[Dict]: 文件信息
        """
        return self.metadata.get(file_id)
    
    def delete_file(self, file_id: str, workspace_id: str) -> bool:
        """
        删除文件
        
        Args:
            file_id: 文件ID
            workspace_id: 工作区ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            file_info = self.metadata.get(file_id)
            if not file_info or file_info['workspace_id'] != workspace_id:
                logger.warning(f"文件不存在或无权限: {file_id}")
                return False
            
            # 删除物理文件
            file_path = Path(file_info['file_path'])
            if file_path.exists():
                file_path.unlink()
                logger.info(f"物理文件已删除: {file_path}")
            
            # 删除元数据
            del self.metadata[file_id]
            self._save_metadata()
            
            logger.info(f"文件删除成功: {file_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            return False
    
    def record_download(self, file_id: str) -> bool:
        """
        记录文件下载
        
        Args:
            file_id: 文件ID
            
        Returns:
            bool: 是否记录成功
        """
        try:
            if file_id in self.metadata:
                self.metadata[file_id]['download_count'] += 1
                self.metadata[file_id]['last_downloaded'] = datetime.now().isoformat()
                self._save_metadata()
                return True
            return False
        except Exception as e:
            logger.error(f"记录下载失败: {e}")
            return False
    
    def cleanup_old_files(self, max_age_days: int = 30) -> int:
        """
        清理旧文件
        
        Args:
            max_age_days: 最大保留天数
            
        Returns:
            int: 清理的文件数量
        """
        try:
            current_time = datetime.now()
            max_age_seconds = max_age_days * 24 * 3600
            
            files_to_remove = []
            for file_id, meta in self.metadata.items():
                created_time = datetime.fromisoformat(meta['created_at'])
                age_seconds = (current_time - created_time).total_seconds()
                
                if age_seconds > max_age_seconds:
                    files_to_remove.append(file_id)
            
            # 删除旧文件
            cleaned_count = 0
            for file_id in files_to_remove:
                meta = self.metadata[file_id]
                workspace_id = meta['workspace_id']
                if self.delete_file(file_id, workspace_id):
                    cleaned_count += 1
            
            logger.info(f"清理了 {cleaned_count} 个旧文件")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理旧文件失败: {e}")
            return 0
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        try:
            total_files = len(self.metadata)
            total_size = 0
            workspace_counts = {}
            
            for meta in self.metadata.values():
                total_size += meta.get('file_size', 0)
                workspace_id = meta['workspace_id']
                workspace_counts[workspace_id] = workspace_counts.get(workspace_id, 0) + 1
            
            return {
                'total_files': total_files,
                'total_size': total_size,
                'total_size_mb': round(total_size / 1024 / 1024, 2),
                'workspace_counts': workspace_counts,
                'storage_dir': str(self.storage_dir)
            }
            
        except Exception as e:
            logger.error(f"获取存储统计失败: {e}")
            return {
                'total_files': 0,
                'total_size': 0,
                'total_size_mb': 0,
                'workspace_counts': {},
                'storage_dir': str(self.storage_dir)
            }
