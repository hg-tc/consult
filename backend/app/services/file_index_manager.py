"""
文件名索引管理器
用于快速查找文件名对应的所有数据块
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class FileIndexManager:
    """文件名索引管理器"""
    
    def __init__(self, index_file: str = "global_data/file_index.json"):
        self.index_file = Path(index_file)
        self.index_file.parent.mkdir(exist_ok=True)
        self._index: Dict[str, Dict] = {}
        self._load_index()
    
    def _load_index(self):
        """加载索引文件"""
        try:
            if self.index_file.exists():
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    self._index = json.load(f)
                logger.info(f"加载文件索引: {len(self._index)} 个文件")
            else:
                self._index = {}
                logger.info("创建新的文件索引")
        except Exception as e:
            logger.error(f"加载文件索引失败: {str(e)}")
            self._index = {}
    
    def _save_index(self):
        """保存索引文件"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
            logger.debug(f"保存文件索引: {len(self._index)} 个文件")
        except Exception as e:
            logger.error(f"保存文件索引失败: {str(e)}")
    
    def add_file(self, file_id: str, filename: str, original_filename: str, 
                 chunk_ids: List[str], file_size: int, file_type: str, 
                 file_path: str = None, upload_time: str = None):
        """添加文件到索引"""
        try:
            self._index[file_id] = {
                "filename": filename,
                "original_filename": original_filename,
                "chunk_ids": chunk_ids,
                "file_size": file_size,
                "file_type": file_type,
                "file_path": file_path,
                "upload_time": upload_time or datetime.now().isoformat(),
                "status": "completed",
                "chunk_count": len(chunk_ids)
            }
            self._save_index()
            logger.info(f"添加文件到索引: {original_filename} ({len(chunk_ids)} 个块)")
        except Exception as e:
            logger.error(f"添加文件到索引失败: {str(e)}")
    
    def remove_file(self, file_id: str) -> bool:
        """从索引中删除文件"""
        try:
            if file_id in self._index:
                file_info = self._index[file_id]
                del self._index[file_id]
                self._save_index()
                logger.info(f"从索引中删除文件: {file_info.get('original_filename', file_id)}")
                return True
            else:
                logger.warning(f"文件 {file_id} 在索引中未找到")
                return False
        except Exception as e:
            logger.error(f"从索引中删除文件失败: {str(e)}")
            return False
    
    def get_file_info(self, file_id: str) -> Optional[Dict]:
        """获取文件信息"""
        return self._index.get(file_id)
    
    def get_file_chunks(self, file_id: str) -> List[str]:
        """获取文件的所有chunk IDs"""
        file_info = self._index.get(file_id)
        return file_info.get("chunk_ids", []) if file_info else []
    
    def list_files(self) -> List[Dict]:
        """列出所有文件"""
        return list(self._index.values())
    
    def find_file_by_name(self, filename: str) -> Optional[str]:
        """根据文件名查找文件ID"""
        for file_id, file_info in self._index.items():
            if file_info.get("original_filename") == filename:
                return file_id
        return None
    
    def get_file_count(self) -> int:
        """获取文件总数"""
        return len(self._index)
    
    def update_file_status(self, file_id: str, status: str, **kwargs):
        """更新文件状态"""
        if file_id in self._index:
            self._index[file_id]["status"] = status
            for key, value in kwargs.items():
                self._index[file_id][key] = value
            self._save_index()
            logger.info(f"更新文件状态: {file_id} -> {status}")
    
    def rebuild_index_from_vector_store(self, vector_store):
        """从向量存储重建索引（用于数据恢复）"""
        try:
            logger.info("开始从向量存储重建索引...")
            self._index = {}
            
            if vector_store and hasattr(vector_store, 'docstore'):
                docstore = vector_store.docstore
                if hasattr(docstore, '_dict'):
                    # 按document_id分组chunks
                    file_groups = {}
                    
                    for chunk_id, doc in docstore._dict.items():
                        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                        document_id = metadata.get('document_id')
                        
                        if document_id:
                            if document_id not in file_groups:
                                file_groups[document_id] = {
                                    'chunk_ids': [],
                                    'metadata': metadata
                                }
                            file_groups[document_id]['chunk_ids'].append(chunk_id)
                    
                    # 重建索引
                    for file_id, group in file_groups.items():
                        metadata = group['metadata']
                        self._index[file_id] = {
                            "filename": metadata.get('original_filename', f"document_{file_id[:8]}"),
                            "original_filename": metadata.get('original_filename', f"document_{file_id[:8]}"),
                            "chunk_ids": group['chunk_ids'],
                            "file_size": metadata.get('file_size', 0),
                            "file_type": metadata.get('file_type', ''),
                            "file_path": metadata.get('file_path', ''),
                            "upload_time": metadata.get('upload_time', ''),
                            "status": "completed",
                            "chunk_count": len(group['chunk_ids'])
                        }
            
            self._save_index()
            logger.info(f"索引重建完成: {len(self._index)} 个文件")
            
        except Exception as e:
            logger.error(f"从向量存储重建索引失败: {str(e)}")

# 全局索引管理器实例
file_index_manager = FileIndexManager()
