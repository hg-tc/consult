"""
重排序服务 - BGE-reranker-v2-m3
提供高质量的重排序功能，提升检索结果的相关性
"""

import os
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import torch

logger = logging.getLogger(__name__)


class RerankerService:
    """重排序服务"""
    
    def __init__(self):
        self.reranker = None
        self.model_name = "BAAI/bge-reranker-v2-m3"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.use_fp16 = torch.cuda.is_available()
        
        self._initialize_reranker()
    
    def _initialize_reranker(self):
        """初始化重排序模型"""
        try:
            # 强制启用离线模式
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['HF_DATASETS_OFFLINE'] = '1'
            
            logger.info(f"正在加载重排序模型: {self.model_name}")
            
            # 尝试使用FlagEmbedding
            try:
                from FlagEmbedding import FlagReranker
                self.reranker = FlagReranker(
                    self.model_name, 
                    use_fp16=self.use_fp16,
                    device=self.device
                )
                logger.info(f"✅ FlagReranker加载成功: {self.model_name}")
                
            except ImportError:
                logger.warning("FlagEmbedding不可用，尝试使用sentence-transformers")
                # 回退到sentence-transformers
                from sentence_transformers import CrossEncoder
                self.reranker = CrossEncoder(
                    'cross-encoder/ms-marco-MiniLM-L-12-v2',
                    device=self.device
                )
                logger.info("✅ CrossEncoder加载成功")
                
            except Exception as e:
                logger.error(f"重排序模型加载失败: {e}")
                self.reranker = None
                
        except Exception as e:
            logger.error(f"重排序服务初始化失败: {e}")
            self.reranker = None
    
    def rerank(self, query: str, documents: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        重排序文档
        
        Args:
            query: 查询文本
            documents: 待排序的文档列表
            top_k: 返回的文档数量
            
        Returns:
            重排序后的文档列表
        """
        if not self.reranker or not documents:
            logger.warning("重排序模型不可用或文档为空，返回原始排序")
            return documents[:top_k]
        
        try:
            # 准备重排序数据
            pairs = []
            for doc in documents:
                content = doc.get('content', '')
                pairs.append([query, content])
            
            # 执行重排序
            if hasattr(self.reranker, 'compute_score'):
                # FlagReranker
                scores = self.reranker.compute_score(pairs)
                if isinstance(scores, np.ndarray):
                    scores = scores.tolist()
            else:
                # CrossEncoder
                scores = self.reranker.predict(pairs)
                if isinstance(scores, np.ndarray):
                    scores = scores.tolist()
            
            # 更新文档分数
            for i, doc in enumerate(documents):
                doc['rerank_score'] = float(scores[i])
                doc['original_rank'] = i + 1
            
            # 按重排序分数排序
            reranked_docs = sorted(documents, key=lambda x: x['rerank_score'], reverse=True)
            
            logger.info(f"重排序完成: {len(documents)} -> {len(reranked_docs)} 个文档")
            return reranked_docs[:top_k]
            
        except Exception as e:
            logger.error(f"重排序失败: {e}")
            return documents[:top_k]
    
    def batch_rerank(self, queries: List[str], documents_list: List[List[Dict[str, Any]]], top_k: int = 5) -> List[List[Dict[str, Any]]]:
        """
        批量重排序
        
        Args:
            queries: 查询列表
            documents_list: 每个查询对应的文档列表
            top_k: 每个查询返回的文档数量
            
        Returns:
            重排序后的文档列表
        """
        if not self.reranker:
            logger.warning("重排序模型不可用，返回原始排序")
            return [docs[:top_k] for docs in documents_list]
        
        try:
            results = []
            for query, documents in zip(queries, documents_list):
                reranked = self.rerank(query, documents, top_k)
                results.append(reranked)
            
            logger.info(f"批量重排序完成: {len(queries)} 个查询")
            return results
            
        except Exception as e:
            logger.error(f"批量重排序失败: {e}")
            return [docs[:top_k] for docs in documents_list]
    
    def get_rerank_score(self, query: str, document: str) -> float:
        """
        获取单个文档的重排序分数
        
        Args:
            query: 查询文本
            document: 文档内容
            
        Returns:
            重排序分数
        """
        if not self.reranker:
            return 0.0
        
        try:
            if hasattr(self.reranker, 'compute_score'):
                # FlagReranker
                score = self.reranker.compute_score([[query, document]])
                if isinstance(score, np.ndarray):
                    score = score[0]
                return float(score)
            else:
                # CrossEncoder
                score = self.reranker.predict([[query, document]])
                if isinstance(score, np.ndarray):
                    score = score[0]
                return float(score)
                
        except Exception as e:
            logger.error(f"获取重排序分数失败: {e}")
            return 0.0
    
    def is_available(self) -> bool:
        """检查重排序服务是否可用"""
        return self.reranker is not None
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "model_name": self.model_name,
            "device": self.device,
            "use_fp16": self.use_fp16,
            "available": self.is_available(),
            "model_type": "FlagReranker" if hasattr(self.reranker, 'compute_score') else "CrossEncoder" if self.reranker else "None"
        }
