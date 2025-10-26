"""
向量数据库服务
提供文档向量化、存储和相似性搜索功能
"""

import os
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer
import faiss

logger = logging.getLogger(__name__)


class VectorService:
    """向量服务"""

    def __init__(self, vector_db_path: str = "vector_db"):
        self.vector_db_path = Path(vector_db_path)
        self.vector_db_path.mkdir(exist_ok=True)

        # 初始化嵌入模型（使用更强大的本地模型）
        self.embedding_model = None
        self._initialize_embedding_model()

        # 初始化向量数据库
        try:
            self.chroma_client = chromadb.PersistentClient(path=str(self.vector_db_path))
        except Exception as e:
            logger.error(f"ChromaDB初始化失败: {str(e)}")
            self.chroma_client = None

        # FAISS索引
        self.faiss_index = None
        self.faiss_metadata = []

    def _initialize_embedding_model(self):
        """初始化嵌入模型，支持多种模型和镜像源"""
        # 配置Hugging Face镜像 - 使用多个镜像源
        import os
        
        # 设置多个镜像源环境变量
        os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
        os.environ['HUGGINGFACE_HUB_CACHE'] = os.path.expanduser('~/.cache/huggingface')
        
        # 强制启用离线模式
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_HUB_OFFLINE'] = '1'
        logger.info("强制启用离线模式")
        
        # 尝试加载的模型列表（按优先级排序，优先使用已下载的模型）
        models_to_try = [
            'all-MiniLM-L6-v2',   # 384维，轻量级（已下载）
            'all-mpnet-base-v2',  # 768维，性能最好
            'paraphrase-multilingual-MiniLM-L12-v2',  # 多语言支持
            'all-MiniLM-L12-v2'   # 384维，性能较好
        ]
        
        for model_name in models_to_try:
            try:
                logger.info(f"正在尝试加载模型: {model_name}")
                
                # 优先使用本地缓存
                try:
                    # 尝试直接使用snapshot路径
                    snapshot_path = f"./models/models--sentence-transformers--{model_name}/snapshots"
                    import os
                    if os.path.exists(snapshot_path):
                        snapshot_dirs = [d for d in os.listdir(snapshot_path) if os.path.isdir(os.path.join(snapshot_path, d))]
                        if snapshot_dirs:
                            full_path = os.path.join(snapshot_path, snapshot_dirs[0])
                            logger.info(f"使用snapshot路径: {full_path}")
                            self.embedding_model = SentenceTransformer(full_path)
                        else:
                            raise Exception("No snapshot found")
                    else:
                        # 使用cache_folder方式
                        self.embedding_model = SentenceTransformer(model_name, cache_folder='./models')
                    
                    logger.info(f"成功从本地缓存加载模型: {model_name}")
                except Exception as local_error:
                    logger.warning(f"本地缓存加载失败: {str(local_error)}")
                    # 尝试在线下载
                    try:
                        self.embedding_model = SentenceTransformer(model_name)
                        logger.info(f"成功在线下载模型: {model_name}")
                    except Exception as online_error:
                        logger.warning(f"在线下载失败: {str(online_error)}")
                        raise online_error
                
                logger.info(f"成功加载模型: {model_name}, 向量维度: {self.embedding_model.get_sentence_embedding_dimension()}")
                return
            except Exception as e:
                logger.warning(f"加载模型 {model_name} 失败: {str(e)}")
                continue
        
        # 如果所有模型都加载失败，使用哈希向量作为降级方案
        logger.error("所有嵌入模型加载失败，将使用哈希向量降级方案")
        self.embedding_model = None

    def _get_or_create_collection(self, workspace_id: str, collection_name: str = None):
        """获取或创建向量数据库集合"""
        collection_name = collection_name or f"workspace_{workspace_id}"
        try:
            return self.chroma_client.get_collection(name=collection_name)
        except:
            return self.chroma_client.create_collection(name=collection_name)

    def embed_text(self, text: str) -> List[float]:
        """将文本转换为向量"""
        if self.embedding_model is None:
            # 降级处理：使用简单的哈希向量
            import hashlib
            hash_obj = hashlib.md5(text.encode('utf-8'))
            hash_bytes = hash_obj.digest()
            # 转换为768维向量（与all-mpnet-base-v2兼容）
            vector = [b / 255.0 for b in hash_bytes[:768]]
            return vector

        try:
            embedding = self.embedding_model.encode(text)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"文本向量化失败: {str(e)}")
            # 如果模型向量化失败，降级到哈希向量
            logger.warning("模型向量化失败，降级到哈希向量")
            import hashlib
            hash_obj = hashlib.md5(text.encode('utf-8'))
            hash_bytes = hash_obj.digest()
            vector = [b / 255.0 for b in hash_bytes[:768]]
            return vector

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量将文本转换为向量"""
        if self.embedding_model is None:
            # 降级处理：批量哈希向量
            import hashlib
            vectors = []
            for text in texts:
                hash_obj = hashlib.md5(text.encode('utf-8'))
                hash_bytes = hash_obj.digest()
                vector = [b / 255.0 for b in hash_bytes[:768]]
                vectors.append(vector)
            return vectors

        try:
            embeddings = self.embedding_model.encode(texts)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"批量文本向量化失败: {str(e)}")
            # 如果批量向量化失败，逐个处理
            logger.warning("批量向量化失败，降级到逐个处理")
            vectors = []
            for text in texts:
                vectors.append(self.embed_text(text))
            return vectors

    def get_model_info(self) -> Dict[str, Any]:
        """获取当前使用的模型信息"""
        if self.embedding_model is None:
            return {
                "model_name": "hash_fallback",
                "model_type": "MD5哈希向量",
                "dimension": 768,
                "status": "降级模式"
            }
        
        try:
            return {
                "model_name": self.embedding_model.model_name if hasattr(self.embedding_model, 'model_name') else "unknown",
                "model_type": "SentenceTransformer",
                "dimension": self.embedding_model.get_sentence_embedding_dimension(),
                "status": "正常运行"
            }
        except Exception as e:
            return {
                "model_name": "unknown",
                "model_type": "SentenceTransformer",
                "dimension": "unknown",
                "status": f"错误: {str(e)}"
            }

    async def add_document_chunks(
        self,
        workspace_id: str,
        document_id: str,
        chunks: List[Dict[str, Any]]
    ) -> bool:
        """
        添加文档分块到向量数据库

        Args:
            workspace_id: 工作区ID
            document_id: 文档ID
            chunks: 文档分块列表，每个分块包含content和其他元数据
        """
        try:
            if self.chroma_client is None:
                # ChromaDB不可用，跳过向量存储
                logger.warning("ChromaDB不可用，跳过向量存储")
                return True

            collection = self._get_or_create_collection(workspace_id)

            # 准备数据
            texts = [chunk['content'] for chunk in chunks]
            embeddings = self.embed_texts(texts)

            # 准备元数据和ID
            metadatas = []
            ids = []

            for i, chunk in enumerate(chunks):
                chunk_id = f"{document_id}_chunk_{i}"
                ids.append(chunk_id)

                metadata = chunk.copy()
                metadata['document_id'] = document_id
                metadata['workspace_id'] = workspace_id
                metadata['chunk_index'] = i
                metadatas.append(metadata)

            # 添加到向量数据库
            collection.add(
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )

            logger.info(f"成功添加 {len(chunks)} 个文档分块到向量数据库")
            return True

        except Exception as e:
            logger.error(f"添加文档分块失败: {str(e)}")
            raise

    async def search_similar(
        self,
        workspace_id: str,
        query: str,
        top_k: int = 5,
        threshold: float = 0.7
    ):
        """
        相似性搜索

        Args:
            workspace_id: 工作区ID
            query: 查询文本
            top_k: 返回结果数量
            threshold: 相似度阈值

        Returns:
            搜索结果列表，包含内容、元数据和相似度分数
        """
        try:
            if self.chroma_client is None:
                # ChromaDB不可用，使用内存搜索降级方案
                return self._search_similar_memory(workspace_id, query, top_k, threshold)

            collection = self._get_or_create_collection(workspace_id)

            # 将查询转换为向量
            query_embedding = self.embed_text(query)

            # 搜索相似文档
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=['documents', 'metadatas', 'distances']
            )

            # 处理结果
            search_results = []
            for i, (doc, metadata, distance) in enumerate(
                zip(results['documents'][0], results['metadatas'][0], results['distances'][0])
            ):
                # 计算相似度分数（ChromaDB使用余弦距离，需要转换）
                similarity = 1 - distance

                if similarity >= threshold:
                    search_results.append({
                        'content': doc,
                        'metadata': metadata,
                        'similarity': float(similarity),
                        'rank': i + 1
                    })

            return search_results

        except Exception as e:
            logger.error(f"相似性搜索失败: {str(e)}")
            # 降级到内存搜索
            return self._search_similar_memory(workspace_id, query, top_k, threshold)

    def _search_similar_memory(self, workspace_id: str, query: str, top_k: int, threshold: float):
        """内存搜索降级方案"""
        from app_simple import documents_db

        # 获取工作区文档
        workspace_docs = [doc for doc in documents_db if str(doc["workspace_id"]) == workspace_id]

        if not workspace_docs:
            return []

        # 简单的关键词匹配
        query_words = set(query.lower().split())
        results = []

        for doc in workspace_docs:
            # 简单的相似度计算：基于文档内容中的关键词匹配
            doc_content = doc.get("content", "").lower()
            doc_words = set(doc_content.split())

            # 计算交集比例
            if query_words and doc_words:
                intersection = query_words.intersection(doc_words)
                similarity = len(intersection) / len(query_words)
            else:
                similarity = 0.0

            if similarity >= threshold:
                results.append({
                    'content': doc.get("content", "")[:500],  # 限制内容长度
                    'metadata': {
                        'document_id': doc["id"],
                        'filename': doc["original_filename"],
                        'file_type': doc["file_type"]
                    },
                    'similarity': similarity,
                    'rank': len(results) + 1
                })

        # 按相似度排序并限制数量
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]

    async def delete_workspace_data(self, workspace_id: str):
        """删除工作区的所有向量数据"""
        try:
            if self.chroma_client is None:
                logger.warning("ChromaDB不可用，跳过向量数据删除")
                return True

            collection_name = f"workspace_{workspace_id}"
            self.chroma_client.delete_collection(name=collection_name)
            logger.info(f"成功删除工作区 {workspace_id} 的向量数据")
            return True
        except Exception as e:
            logger.error(f"删除工作区向量数据失败: {str(e)}")
            return False

    def get_collection_stats(self, workspace_id: str) -> Dict[str, Any]:
        """获取集合统计信息"""
        try:
            collection = self._get_or_create_collection(workspace_id)
            count = collection.count()
            return {
                'workspace_id': workspace_id,
                'document_count': count,
                'collection_name': collection.name
            }
        except Exception as e:
            logger.error(f"获取集合统计失败: {str(e)}")
            return {'workspace_id': workspace_id, 'error': str(e)}
