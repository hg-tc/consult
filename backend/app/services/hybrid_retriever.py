"""
混合检索系统 - BM25 + 向量检索 + RRF融合
实现先进的混合检索策略，提升中文检索准确率
"""

import os
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import pickle
import json
from collections import defaultdict

# BM25检索
from rank_bm25 import BM25Okapi

# 向量检索
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from sentence_transformers import SentenceTransformer

# 重排序
from .reranker_service import RerankerService

logger = logging.getLogger(__name__)


class HybridRetriever:
    """混合检索器 - BM25 + 向量检索 + RRF融合"""
    
    def __init__(self, workspace_id: str, vector_db_path: str = "langchain_vector_db"):
        self.workspace_id = workspace_id
        self.vector_db_path = Path(vector_db_path)
        
        # 初始化组件
        self.bm25_index = None
        self.vector_store = None
        self.reranker_service = RerankerService()
        self.documents = []
        self.document_ids = []
        
        # 配置参数
        self.bm25_weight = 0.3  # BM25权重
        self.vector_weight = 0.7  # 向量检索权重
        self.rrf_k = 60  # RRF参数
        
        self._initialize_components()
    
    def _initialize_components(self):
        """初始化检索组件"""
        try:
            # 初始化BGE嵌入模型
            self.embeddings = HuggingFaceEmbeddings(
                model_name='BAAI/bge-large-zh-v1.5',
                model_kwargs={'device': 'cuda' if os.getenv('CUDA_VISIBLE_DEVICES') else 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
            
            # 重排序服务已在初始化时创建
            if self.reranker_service.is_available():
                logger.info("✅ 重排序服务初始化成功")
            else:
                logger.warning("重排序服务不可用")
            
            # 加载向量存储
            self._load_vector_store()
            
            # 构建BM25索引
            self._build_bm25_index()
            
            logger.info(f"混合检索器初始化完成: {self.workspace_id}")
            
        except Exception as e:
            logger.error(f"混合检索器初始化失败: {e}")
            raise
    
    def _load_vector_store(self):
        """加载向量存储"""
        try:
            store_path = self.vector_db_path / f"workspace_{self.workspace_id}"
            if store_path.exists():
                self.vector_store = FAISS.load_local(
                    str(store_path),
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                logger.info(f"向量存储加载成功: {self.workspace_id}")
            else:
                logger.warning(f"向量存储不存在: {self.workspace_id}")
                self.vector_store = None
        except Exception as e:
            logger.error(f"向量存储加载失败: {e}")
            self.vector_store = None
    
    def _build_bm25_index(self):
        """构建BM25索引"""
        try:
            if not self.vector_store:
                logger.warning("向量存储为空，无法构建BM25索引")
                return
            
            # 从向量存储中提取文档
            if hasattr(self.vector_store, 'docstore') and hasattr(self.vector_store.docstore, '_dict'):
                docstore = self.vector_store.docstore
                self.documents = []
                self.document_ids = []
                
                for doc_id, doc in docstore._dict.items():
                    # 分词处理（简单的中文分词）
                    content = doc.page_content
                    # 使用简单的字符级分词，适合中文
                    tokens = list(content)
                    self.documents.append(tokens)
                    self.document_ids.append(doc_id)
                
                if self.documents:
                    self.bm25_index = BM25Okapi(self.documents)
                    logger.info(f"BM25索引构建成功: {len(self.documents)} 个文档")
                else:
                    logger.warning("没有文档可用于构建BM25索引")
            
        except Exception as e:
            logger.error(f"BM25索引构建失败: {e}")
            self.bm25_index = None
    
    def _bm25_search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """BM25检索"""
        if not self.bm25_index:
            return []
        
        try:
            # 查询分词
            query_tokens = list(query)
            
            # BM25检索
            scores = self.bm25_index.get_scores(query_tokens)
            
            # 获取Top-K结果
            top_indices = np.argsort(scores)[::-1][:top_k]
            
            results = []
            for idx in top_indices:
                if scores[idx] > 0:  # 只返回有分数的结果
                    doc_id = self.document_ids[idx]
                    doc = self.vector_store.docstore._dict[doc_id]
                    
                    results.append({
                        'doc_id': doc_id,
                        'content': doc.page_content,
                        'metadata': doc.metadata,
                        'bm25_score': float(scores[idx]),
                        'rank': len(results) + 1
                    })
            
            logger.info(f"BM25检索完成: {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"BM25检索失败: {e}")
            return []
    
    def _vector_search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """向量检索"""
        if not self.vector_store:
            return []
        
        try:
            # 执行相似性搜索
            docs_with_scores = self.vector_store.similarity_search_with_score(query, k=top_k)
            
            results = []
            for i, (doc, score) in enumerate(docs_with_scores):
                # 获取文档ID
                doc_id = None
                if hasattr(self.vector_store, 'docstore') and hasattr(self.vector_store.docstore, '_dict'):
                    for idx, stored_doc in self.vector_store.docstore._dict.items():
                        if stored_doc.page_content == doc.page_content:
                            doc_id = idx
                            break
                
                results.append({
                    'doc_id': doc_id or f"vector_{i}",
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'vector_score': float(1 - score),  # 转换为相似度
                    'rank': i + 1
                })
            
            logger.info(f"向量检索完成: {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []
    
    def _rrf_fusion(self, bm25_results: List[Dict], vector_results: List[Dict]) -> List[Dict[str, Any]]:
        """RRF (Reciprocal Rank Fusion) 融合"""
        try:
            # 创建文档ID到分数的映射
            doc_scores = defaultdict(float)
            doc_info = {}
            
            # BM25结果处理
            for i, result in enumerate(bm25_results):
                doc_id = result['doc_id']
                rrf_score = 1.0 / (self.rrf_k + i + 1)  # RRF公式
                doc_scores[doc_id] += self.bm25_weight * rrf_score
                doc_info[doc_id] = result
            
            # 向量检索结果处理
            for i, result in enumerate(vector_results):
                doc_id = result['doc_id']
                rrf_score = 1.0 / (self.rrf_k + i + 1)
                doc_scores[doc_id] += self.vector_weight * rrf_score
                if doc_id not in doc_info:
                    doc_info[doc_id] = result
            
            # 按融合分数排序
            sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
            
            # 构建最终结果
            fused_results = []
            for doc_id, fused_score in sorted_docs:
                result = doc_info[doc_id].copy()
                result['fused_score'] = fused_score
                result['rank'] = len(fused_results) + 1
                fused_results.append(result)
            
            logger.info(f"RRF融合完成: {len(fused_results)} 个结果")
            return fused_results
            
        except Exception as e:
            logger.error(f"RRF融合失败: {e}")
            return []
    
    def _rerank_results(self, query: str, results: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """重排序结果"""
        if not self.reranker_service.is_available() or not results:
            return results[:top_k]
        
        try:
            # 使用重排序服务
            reranked_results = self.reranker_service.rerank(query, results, top_k)
            
            logger.info(f"重排序完成: {len(reranked_results)} 个结果")
            return reranked_results
            
        except Exception as e:
            logger.error(f"重排序失败: {e}")
            return results[:top_k]
    
    def search(self, query: str, top_k: int = 5, use_rerank: bool = True) -> List[Dict[str, Any]]:
        """
        混合检索主入口
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            use_rerank: 是否使用重排序
            
        Returns:
            检索结果列表
        """
        try:
            logger.info(f"开始混合检索: '{query}', top_k={top_k}")
            
            # 1. BM25检索
            bm25_results = self._bm25_search(query, top_k=20)
            
            # 2. 向量检索
            vector_results = self._vector_search(query, top_k=20)
            
            # 3. RRF融合
            fused_results = self._rrf_fusion(bm25_results, vector_results)
            
            # 4. 重排序（可选）
            if use_rerank and self.reranker_service.is_available():
                final_results = self._rerank_results(query, fused_results, top_k)
            else:
                final_results = fused_results[:top_k]
            
            # 5. 添加检索元信息
            for i, result in enumerate(final_results):
                result['retrieval_method'] = 'hybrid'
                result['final_rank'] = i + 1
                result['query'] = query
            
            logger.info(f"混合检索完成: {len(final_results)} 个结果")
            return final_results
            
        except Exception as e:
            logger.error(f"混合检索失败: {e}")
            # 回退到向量检索
            try:
                vector_results = self._vector_search(query, top_k)
                logger.info("回退到向量检索")
                return vector_results
            except Exception as fallback_error:
                logger.error(f"回退检索也失败: {fallback_error}")
                return []
    
    def add_documents(self, documents: List[Dict[str, Any]]):
        """添加文档到索引"""
        try:
            # 添加到向量存储
            if self.vector_store:
                from langchain.schema import Document
                langchain_docs = []
                for doc_data in documents:
                    doc = Document(
                        page_content=doc_data['content'],
                        metadata=doc_data.get('metadata', {})
                    )
                    langchain_docs.append(doc)
                
                self.vector_store.add_documents(langchain_docs)
            
            # 重建BM25索引
            self._build_bm25_index()
            
            logger.info(f"文档添加成功: {len(documents)} 个文档")
            
        except Exception as e:
            logger.error(f"文档添加失败: {e}")
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """获取检索器统计信息"""
        return {
            'workspace_id': self.workspace_id,
            'bm25_available': self.bm25_index is not None,
            'vector_available': self.vector_store is not None,
            'reranker_available': self.reranker_service.is_available(),
            'document_count': len(self.documents),
            'bm25_weight': self.bm25_weight,
            'vector_weight': self.vector_weight,
            'rrf_k': self.rrf_k,
            'reranker_info': self.reranker_service.get_model_info()
        }
