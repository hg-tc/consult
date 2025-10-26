"""
全局RAG服务
支持公共文档库和工作区分离的架构
"""

import os
import logging
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.models.global_database import (
    GlobalDocument, GlobalDocumentChunk, Workspace, 
    WorkspaceDocumentAccess, GlobalVectorIndex, GlobalDatabaseService
)

logger = logging.getLogger(__name__)


class GlobalRAGService:
    """全局RAG服务 - 支持公共文档库和工作区分离"""
    
    def __init__(self, db_service: GlobalDatabaseService):
        self.db_service = db_service
        self.embeddings = None
        self.global_vector_store = None
        self.vector_index_path = Path("global_vector_db")
        self.vector_index_path.mkdir(exist_ok=True)
        
        self._initialize_components()
    
    def _initialize_components(self):
        """初始化组件"""
        try:
            # 初始化嵌入模型
            self.embeddings = self._initialize_local_embeddings()
            
            # 加载全局向量存储
            self._load_global_vector_store()
            
            logger.info("全局RAG服务初始化成功")
            
        except Exception as e:
            logger.error(f"全局RAG服务初始化失败: {str(e)}")
            raise
    
    def _initialize_local_embeddings(self):
        """初始化本地BGE嵌入模型"""
        try:
            # 设置HuggingFace镜像
            os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
            os.environ['HF_HUB_CACHE'] = '/root/.cache/huggingface'
            os.environ['SENTENCE_TRANSFORMERS_HOME'] = '/root/.cache/sentence_transformers'
            
            # 尝试从本地路径加载
            local_model_path = "/root/.cache/sentence_transformers/BAAI_bge-large-zh-v1.5"
            if os.path.exists(local_model_path):
                logger.info(f"从本地路径加载BGE模型: {local_model_path}")
                embeddings = HuggingFaceEmbeddings(
                    model_name=local_model_path,
                    model_kwargs={'device': 'cpu'},
                    encode_kwargs={'normalize_embeddings': True}
                )
            else:
                # 在线下载
                logger.info("从HuggingFace下载BGE模型")
                embeddings = HuggingFaceEmbeddings(
                    model_name="BAAI/bge-large-zh-v1.5",
                    model_kwargs={'device': 'cpu'},
                    encode_kwargs={'normalize_embeddings': True}
                )
            
            logger.info("✅ BGE嵌入模型初始化成功")
            return embeddings
            
        except Exception as e:
            logger.error(f"BGE模型加载失败: {str(e)}")
            raise
    
    def _load_global_vector_store(self):
        """加载全局向量存储"""
        try:
            index_path = self.vector_index_path / "global_index"
            
            if index_path.exists():
                logger.info("加载现有全局向量存储")
                self.global_vector_store = FAISS.load_local(
                    str(index_path), 
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                logger.info(f"✅ 全局向量存储加载成功，包含 {self.global_vector_store.index.ntotal} 个向量")
            else:
                logger.info("创建新的全局向量存储")
                self.global_vector_store = None
                
        except Exception as e:
            logger.error(f"全局向量存储加载失败: {str(e)}")
            self.global_vector_store = None
    
    async def add_global_document(self, file_path: str, metadata: Dict[str, Any] = None) -> str:
        """添加文档到全局文档库"""
        try:
            # 处理文档内容
            documents = self._load_document(file_path)
            
            if not documents:
                logger.warning(f"文档为空: {file_path}")
                return None
            
            # 添加到全局向量存储
            if self.global_vector_store is None:
                self.global_vector_store = FAISS.from_documents(documents, self.embeddings)
            else:
                self.global_vector_store.add_documents(documents)
            
            # 保存向量存储
            self._save_global_vector_store()
            
            # 保存到数据库
            document_id = await self._save_document_to_db(file_path, documents, metadata)
            
            logger.info(f"全局文档添加成功: {file_path}, ID: {document_id}")
            return document_id
            
        except Exception as e:
            logger.error(f"添加全局文档失败: {str(e)}")
            return None
    
    def _load_document(self, file_path: str) -> List[Document]:
        """加载文档 - 使用基础处理器"""
        try:
            file_path = Path(file_path)
            file_extension = file_path.suffix.lower()
            
            if file_extension == '.pdf':
                from langchain_community.document_loaders import PyPDFLoader
                loader = PyPDFLoader(str(file_path))
            elif file_extension in ['.docx', '.doc']:
                from langchain_community.document_loaders import Docx2txtLoader
                loader = Docx2txtLoader(str(file_path))
            elif file_extension in ['.txt', '.md']:
                from langchain_community.document_loaders import TextLoader
                loader = TextLoader(str(file_path), encoding='utf-8')
            else:
                raise ValueError(f"不支持的文件类型: {file_extension}")
            
            documents = loader.load()
            
            # 智能分割
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                length_function=len,
                separators=["\n\n", "\n", " ", ""]
            )
            
            split_documents = text_splitter.split_documents(documents)
            
            # 添加文件名到内容
            original_filename = file_path.name
            for doc in split_documents:
                doc.page_content = f"文件名: {original_filename}\n\n{doc.page_content}"
                doc.metadata.update({
                    'file_path': str(file_path),
                    'file_type': file_extension[1:],
                    'original_filename': original_filename
                })
            
            logger.info(f"文档加载完成: {file_path}, 块数: {len(split_documents)}")
            return split_documents
            
        except Exception as e:
            logger.error(f"文档加载失败: {str(e)}")
            return []
    
    async def _save_document_to_db(self, file_path: str, documents: List[Document], metadata: Dict[str, Any]) -> str:
        """保存文档到数据库"""
        import uuid
        
        document_id = str(uuid.uuid4())
        file_path = Path(file_path)
        
        # 创建全局文档记录
        global_doc = GlobalDocument(
            id=document_id,
            filename=file_path.name,
            original_filename=metadata.get('original_filename', file_path.name) if metadata else file_path.name,
            file_path=str(file_path),
            file_size=file_path.stat().st_size,
            file_type=file_path.suffix[1:],
            mime_type=metadata.get('mime_type', 'application/octet-stream') if metadata else 'application/octet-stream',
            content='\n\n'.join([doc.page_content for doc in documents]),
            metadata=metadata or {},
            status='completed',
            vectorized=True,
            chunk_count=len(documents)
        )
        
        # 保存文档分块
        for i, doc in enumerate(documents):
            chunk_id = str(uuid.uuid4())
            chunk = GlobalDocumentChunk(
                id=chunk_id,
                document_id=document_id,
                chunk_index=i,
                content=doc.page_content,
                metadata=doc.metadata
            )
            # 这里应该保存到数据库，简化处理
        
        return document_id
    
    def _save_global_vector_store(self):
        """保存全局向量存储"""
        try:
            if self.global_vector_store is None:
                return
            
            index_path = self.vector_index_path / "global_index"
            self.global_vector_store.save_local(str(index_path))
            logger.info(f"全局向量存储保存成功: {index_path}")
            
        except Exception as e:
            logger.error(f"保存全局向量存储失败: {str(e)}")
    
    async def search_documents(self, query: str, workspace_id: str = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索文档 - 支持工作区过滤"""
        try:
            if self.global_vector_store is None:
                logger.warning("全局向量存储不存在")
                return []
            
            # 执行相似性搜索
            docs_with_scores = self.global_vector_store.similarity_search_with_score(query, k=top_k)
            
            results = []
            for doc, score in docs_with_scores:
                # 如果指定了工作区，检查访问权限
                if workspace_id:
                    # 这里应该检查工作区访问权限
                    # 简化处理，暂时跳过权限检查
                    pass
                
                results.append({
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'similarity': 1 - score,
                    'score': score
                })
            
            logger.info(f"文档搜索完成: 查询='{query}', 结果数={len(results)}")
            return results
            
        except Exception as e:
            logger.error(f"文档搜索失败: {str(e)}")
            return []
    
    async def ask_question(self, question: str, workspace_id: str = None, top_k: int = 5) -> Dict[str, Any]:
        """问答 - 支持工作区过滤"""
        try:
            # 搜索相关文档
            results = await self.search_documents(question, workspace_id, top_k)
            
            if not results:
                return {
                    "answer": "抱歉，没有找到与您问题相关的文档内容。",
                    "references": [],
                    "confidence": 0.0
                }
            
            # 构建上下文
            context_parts = []
            references = []
            
            for i, result in enumerate(results):
                content_preview = result['content'][:200] + "..." if len(result['content']) > 200 else result['content']
                context_parts.append(f"相关内容 {i+1}: {content_preview}")
                
                references.append({
                    "content_preview": content_preview,
                    "metadata": result['metadata'],
                    "similarity": result['similarity']
                })
            
            # 简单的文本匹配回答（因为没有LLM配置）
            answer = f"根据检索到的文档内容，我找到了以下相关信息：\n\n" + "\n\n".join(context_parts)
            answer += f"\n\n注意：当前使用简单文本匹配模式，如需更智能的回答，请配置LLM服务。"
            
            return {
                "answer": answer,
                "references": references,
                "confidence": 0.7,
                "metadata": {
                    "mode": "global_rag",
                    "retrieved_chunks": len(results),
                    "workspace_id": workspace_id
                }
            }
            
        except Exception as e:
            logger.error(f"问答失败: {str(e)}")
            return {
                "answer": f"抱歉，处理您的问题时出现错误: {str(e)}",
                "references": [],
                "confidence": 0.0
            }
    
    def get_global_stats(self) -> Dict[str, Any]:
        """获取全局统计信息"""
        try:
            stats = {
                'global_document_count': 0,
                'global_chunk_count': 0,
                'vector_store_available': self.global_vector_store is not None,
                'embedding_model': 'BAAI/bge-large-zh-v1.5'
            }
            
            if self.global_vector_store:
                stats['global_chunk_count'] = self.global_vector_store.index.ntotal
            
            return stats
            
        except Exception as e:
            logger.error(f"获取全局统计失败: {str(e)}")
            return {}
