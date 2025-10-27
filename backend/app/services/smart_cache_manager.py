"""
智能缓存管理器 - 提升响应速度
"""

import asyncio
import logging
import time
import hashlib
import json
import pickle
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from pathlib import Path
from collections import OrderedDict
import threading

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: float
    accessed_at: float
    access_count: int = 0
    ttl: Optional[float] = None  # 生存时间（秒）
    size: int = 0  # 大小（字节）

class LRUCache:
    """LRU缓存实现"""
    
    def __init__(self, max_size: int = 1000, max_memory_mb: int = 100):
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.current_memory = 0
        self.lock = threading.RLock()
        
        logger.info(f"LRU缓存初始化: 最大条目={max_size}, 最大内存={max_memory_mb}MB")
    
    def _calculate_size(self, value: Any) -> int:
        """计算值的大小"""
        try:
            if isinstance(value, (str, bytes)):
                return len(value)
            elif isinstance(value, (dict, list)):
                return len(json.dumps(value, default=str).encode('utf-8'))
            else:
                return len(pickle.dumps(value))
        except Exception:
            return 1024  # 默认大小
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """检查条目是否过期"""
        if entry.ttl is None:
            return False
        return time.time() - entry.created_at > entry.ttl
    
    def _evict_expired(self):
        """清理过期条目"""
        with self.lock:
            expired_keys = []
            for key, entry in self.cache.items():
                if self._is_expired(entry):
                    expired_keys.append(key)
            
            for key in expired_keys:
                self._remove_entry(key)
            
            if expired_keys:
                logger.debug(f"清理了 {len(expired_keys)} 个过期条目")
    
    def _evict_lru(self):
        """清理最少使用的条目"""
        with self.lock:
            while (len(self.cache) >= self.max_size or 
                   self.current_memory >= self.max_memory_bytes):
                if not self.cache:
                    break
                
                # 移除最少使用的条目
                key, entry = self.cache.popitem(last=False)
                self.current_memory -= entry.size
                logger.debug(f"清理LRU条目: {key}")
    
    def _remove_entry(self, key: str):
        """移除缓存条目"""
        if key in self.cache:
            entry = self.cache.pop(key)
            self.current_memory -= entry.size
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self.lock:
            if key not in self.cache:
                return None
            
            entry = self.cache[key]
            
            # 检查是否过期
            if self._is_expired(entry):
                self._remove_entry(key)
                return None
            
            # 更新访问信息
            entry.accessed_at = time.time()
            entry.access_count += 1
            
            # 移动到末尾（最近使用）
            self.cache.move_to_end(key)
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """设置缓存值"""
        with self.lock:
            # 计算大小
            size = self._calculate_size(value)
            
            # 如果键已存在，先移除
            if key in self.cache:
                self._remove_entry(key)
            
            # 创建新条目
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                accessed_at=time.time(),
                ttl=ttl,
                size=size
            )
            
            # 检查是否需要清理
            if (len(self.cache) >= self.max_size or 
                self.current_memory + size >= self.max_memory_bytes):
                self._evict_lru()
            
            # 添加新条目
            self.cache[key] = entry
            self.current_memory += size
    
    def delete(self, key: str):
        """删除缓存条目"""
        with self.lock:
            self._remove_entry(key)
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.current_memory = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self.lock:
            self._evict_expired()
            
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "memory_usage_mb": self.current_memory / (1024 * 1024),
                "max_memory_mb": self.max_memory_bytes / (1024 * 1024),
                "hit_rate": self._calculate_hit_rate(),
                "oldest_entry": min(self.cache.values(), key=lambda x: x.created_at).created_at if self.cache else None,
                "newest_entry": max(self.cache.values(), key=lambda x: x.created_at).created_at if self.cache else None
            }
    
    def _calculate_hit_rate(self) -> float:
        """计算命中率"""
        if not self.cache:
            return 0.0
        
        total_access = sum(entry.access_count for entry in self.cache.values())
        if total_access == 0:
            return 0.0
        
        return sum(entry.access_count for entry in self.cache.values()) / total_access

class SmartCacheManager:
    """智能缓存管理器"""
    
    def __init__(self):
        # 不同类型的缓存
        self.query_cache = LRUCache(max_size=500, max_memory_mb=50)  # 查询结果缓存
        self.document_cache = LRUCache(max_size=200, max_memory_mb=100)  # 文档内容缓存
        self.embedding_cache = LRUCache(max_size=1000, max_memory_mb=200)  # 嵌入向量缓存
        self.metadata_cache = LRUCache(max_size=1000, max_memory_mb=10)  # 元数据缓存
        
        # 持久化存储
        self.persistent_dir = Path("/root/consult/backend/cache_storage")
        self.persistent_dir.mkdir(exist_ok=True)
        
        # 加载持久化缓存
        self._load_persistent_cache()
        
        # 定期清理任务
        self._start_cleanup_task()
        
        logger.info("智能缓存管理器初始化完成")
    
    def _start_cleanup_task(self):
        """启动定期清理任务"""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(300)  # 每5分钟清理一次
                    self._cleanup_expired()
                except Exception as e:
                    logger.error(f"缓存清理任务失败: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
    
    def _cleanup_expired(self):
        """清理过期缓存"""
        for cache_name, cache in [
            ("query_cache", self.query_cache),
            ("document_cache", self.document_cache),
            ("embedding_cache", self.embedding_cache),
            ("metadata_cache", self.metadata_cache)
        ]:
            try:
                cache._evict_expired()
                logger.debug(f"清理 {cache_name} 过期条目")
            except Exception as e:
                logger.error(f"清理 {cache_name} 失败: {e}")
    
    def _load_persistent_cache(self):
        """加载持久化缓存"""
        try:
            # 加载查询缓存
            query_file = self.persistent_dir / "query_cache.json"
            if query_file.exists():
                with open(query_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        self.query_cache.set(key, value, ttl=3600)  # 1小时TTL
                logger.info(f"加载了 {len(data)} 个查询缓存条目")
        except Exception as e:
            logger.error(f"加载持久化缓存失败: {e}")
    
    def _save_persistent_cache(self):
        """保存持久化缓存"""
        try:
            # 保存查询缓存（只保存未过期的）
            query_data = {}
            for key, entry in self.query_cache.cache.items():
                if not self.query_cache._is_expired(entry):
                    query_data[key] = entry.value
            
            query_file = self.persistent_dir / "query_cache.json"
            with open(query_file, 'w', encoding='utf-8') as f:
                json.dump(query_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"保存了 {len(query_data)} 个查询缓存条目")
        except Exception as e:
            logger.error(f"保存持久化缓存失败: {e}")
    
    def cache_query_result(self, query: str, workspace_id: str, result: Any, ttl: float = 3600):
        """缓存查询结果"""
        key = self._generate_query_key(query, workspace_id)
        self.query_cache.set(key, result, ttl=ttl)
        logger.debug(f"缓存查询结果: {query[:50]}...")
    
    def get_cached_query_result(self, query: str, workspace_id: str) -> Optional[Any]:
        """获取缓存的查询结果"""
        key = self._generate_query_key(query, workspace_id)
        result = self.query_cache.get(key)
        if result:
            logger.debug(f"命中查询缓存: {query[:50]}...")
        return result
    
    def cache_document_content(self, file_path: str, content: Any, ttl: float = 7200):
        """缓存文档内容"""
        key = self._generate_document_key(file_path)
        self.document_cache.set(key, content, ttl=ttl)
        logger.debug(f"缓存文档内容: {file_path}")
    
    def get_cached_document_content(self, file_path: str) -> Optional[Any]:
        """获取缓存的文档内容"""
        key = self._generate_document_key(file_path)
        result = self.document_cache.get(key)
        if result:
            logger.debug(f"命中文档缓存: {file_path}")
        return result
    
    def cache_embedding(self, text: str, embedding: List[float], ttl: float = 86400):
        """缓存嵌入向量"""
        key = self._generate_embedding_key(text)
        self.embedding_cache.set(key, embedding, ttl=ttl)
        logger.debug(f"缓存嵌入向量: {text[:50]}...")
    
    def get_cached_embedding(self, text: str) -> Optional[List[float]]:
        """获取缓存的嵌入向量"""
        key = self._generate_embedding_key(text)
        result = self.embedding_cache.get(key)
        if result:
            logger.debug(f"命中嵌入缓存: {text[:50]}...")
        return result
    
    def cache_metadata(self, key: str, metadata: Any, ttl: float = 1800):
        """缓存元数据"""
        self.metadata_cache.set(key, metadata, ttl=ttl)
        logger.debug(f"缓存元数据: {key}")
    
    def get_cached_metadata(self, key: str) -> Optional[Any]:
        """获取缓存的元数据"""
        result = self.metadata_cache.get(key)
        if result:
            logger.debug(f"命中元数据缓存: {key}")
        return result
    
    def put_embedding(self, text: str, embedding: List[float]):
        """存储嵌入向量（兼容性方法）"""
        self.cache_embedding(text, embedding)
    
    def _generate_query_key(self, query: str, workspace_id: str) -> str:
        """生成查询缓存键"""
        content = f"{workspace_id}:{query}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _generate_document_key(self, file_path: str) -> str:
        """生成文档缓存键"""
        return hashlib.md5(file_path.encode('utf-8')).hexdigest()
    
    def _generate_embedding_key(self, text: str) -> str:
        """生成嵌入缓存键"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有缓存统计"""
        return {
            "query_cache": self.query_cache.get_stats(),
            "document_cache": self.document_cache.get_stats(),
            "embedding_cache": self.embedding_cache.get_stats(),
            "metadata_cache": self.metadata_cache.get_stats(),
            "persistent_dir": str(self.persistent_dir)
        }
    
    def clear_all(self):
        """清空所有缓存"""
        self.query_cache.clear()
        self.document_cache.clear()
        self.embedding_cache.clear()
        self.metadata_cache.clear()
        logger.info("已清空所有缓存")
    
    def __del__(self):
        """析构函数，保存持久化缓存"""
        try:
            self._save_persistent_cache()
        except Exception as e:
            logger.error(f"保存持久化缓存失败: {e}")

# 全局缓存管理器实例
_cache_manager_instance: Optional[SmartCacheManager] = None

def get_cache_manager() -> SmartCacheManager:
    """获取全局缓存管理器实例"""
    global _cache_manager_instance
    if _cache_manager_instance is None:
        _cache_manager_instance = SmartCacheManager()
    return _cache_manager_instance