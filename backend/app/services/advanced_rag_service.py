"""
高级RAG服务 - 集成混合检索、重排序和智能分块
基于LangChain的高级RAG实现，支持混合检索策略
"""

import os
import logging
import asyncio
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json
from datetime import datetime

# LangChain imports
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    TextLoader, 
    PyPDFLoader, 
    Docx2txtLoader,
    UnstructuredExcelLoader,
    UnstructuredPowerPointLoader
)
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.embeddings import HuggingFaceEmbeddings
from sentence_transformers import SentenceTransformer
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain

# 导入混合检索器和智能分块器
from .hybrid_retriever import HybridRetriever
from .smart_chunker import SmartChunker

logger = logging.getLogger(__name__)


class AdvancedRAGService:
    """高级RAG服务 - 集成混合检索和智能分块"""
    
    def __init__(self, vector_db_path: str = "langchain_vector_db"):
        self.vector_db_path = Path(vector_db_path)
        self.vector_db_path.mkdir(exist_ok=True)
        
        # 初始化组件
        self.embeddings = None
        self.llm = None
        self.smart_chunker = SmartChunker()
        self.hybrid_retrievers = {}  # 按工作区存储混合检索器
        
        self._initialize_components()
    
    def _initialize_components(self):
        """初始化LangChain组件"""
        try:
            # 设置OpenAI配置
            os.environ['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY', '')
            os.environ['OPENAI_BASE_URL'] = os.getenv('THIRD_PARTY_API_BASE', 'https://api.openai.com/v1')
            
            # 初始化嵌入模型
            self.embeddings = self._initialize_embeddings()
            
            # 初始化LLM
            self.llm = ChatOpenAI(
                model="gpt-3.5-turbo",
                temperature=0.1,
                openai_api_base=os.getenv('THIRD_PARTY_API_BASE', 'https://api.openai.com/v1')
            )
            
            # 智能分块器已在初始化时创建
            
            logger.info("高级RAG服务组件初始化成功")
            
        except Exception as e:
            logger.error(f"高级RAG服务组件初始化失败: {str(e)}")
            raise
    
    def _initialize_embeddings(self):
        """初始化嵌入模型"""
        try:
            # 强制启用离线模式
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['HF_DATASETS_OFFLINE'] = '1'
            
            # 使用BGE模型
            model_name = 'BAAI/bge-large-zh-v1.5'
            
            try:
                logger.info(f"正在加载BGE模型: {model_name}")
                
                embeddings = HuggingFaceEmbeddings(
                    model_name=model_name,
                    model_kwargs={'device': 'cuda' if os.getenv('CUDA_VISIBLE_DEVICES') else 'cpu'},
                    encode_kwargs={'normalize_embeddings': True}
                )
                
                # 测试嵌入
                test_embedding = embeddings.embed_query('测试')
                logger.info(f"✅ BGE模型加载成功: {model_name}, 维度: {len(test_embedding)}")
                return embeddings
                
            except Exception as e:
                logger.error(f"BGE模型加载失败: {str(e)}")
                # 回退到OpenAI API
                logger.warning("回退到OpenAI API")
                return OpenAIEmbeddings(
                    model="text-embedding-3-small",
                    openai_api_base=os.getenv('THIRD_PARTY_API_BASE', 'https://api.openai.com/v1')
                )
            
        except Exception as e:
            logger.error(f"嵌入模型初始化失败: {str(e)}")
            # 最终回退到OpenAI API
            return OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_base=os.getenv('THIRD_PARTY_API_BASE', 'https://api.openai.com/v1')
            )
    
    
    def _get_hybrid_retriever(self, workspace_id: str) -> HybridRetriever:
        """获取或创建混合检索器"""
        if workspace_id not in self.hybrid_retrievers:
            self.hybrid_retrievers[workspace_id] = HybridRetriever(
                workspace_id=workspace_id,
                vector_db_path=str(self.vector_db_path)
            )
        return self.hybrid_retrievers[workspace_id]
    
    def _smart_chunk_documents(self, documents: List[Document]) -> List[Document]:
        """智能文档分块"""
        return self.smart_chunker.chunk_documents(documents)
    
    def _load_document(self, file_path: str) -> List[Document]:
        """加载文档 - 使用增强型处理器"""
        try:
            # 使用增强型文档处理器
            from .enhanced_document_processor import EnhancedDocumentProcessor
            
            processor = EnhancedDocumentProcessor()
            
            # 异步处理文档
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, processor.process_document(file_path))
                        processed_doc = future.result()
                else:
                    processed_doc = loop.run_until_complete(processor.process_document(file_path))
            except RuntimeError:
                processed_doc = asyncio.run(processor.process_document(file_path))
            
            # 转换为LangChain Document格式
            documents = []
            for chunk in processed_doc.chunks:
                doc = Document(
                    page_content=chunk.content,
                    metadata={
                        **chunk.metadata,
                        'chunk_type': chunk.chunk_type.value,
                        'has_table': chunk.has_table,
                        'has_image': chunk.has_image,
                        'page_number': chunk.page_number,
                        'section': chunk.section,
                        'file_path': file_path,
                        'file_type': processed_doc.file_type,
                        'quality_score': processed_doc.quality_score,
                        'processing_time': processed_doc.processing_time
                    }
                )
                documents.append(doc)
            
            logger.info(f"增强型文档处理完成: {file_path}, 块数: {len(documents)}")
            return documents
            
        except Exception as e:
            logger.error(f"增强型文档处理失败，回退到基础处理: {str(e)}")
            return self._load_document_fallback(file_path)
    
    def _load_document_fallback(self, file_path: str) -> List[Document]:
        """基础文档加载（回退方案）"""
        file_path = Path(file_path)
        file_extension = file_path.suffix.lower()
        
        try:
            if file_extension == '.txt':
                loader = TextLoader(str(file_path), encoding='utf-8')
            elif file_extension == '.pdf':
                loader = PyPDFLoader(str(file_path))
            elif file_extension == '.docx':
                loader = Docx2txtLoader(str(file_path))
            elif file_extension == '.doc':
                # 旧版.doc文件使用unstructured库
                try:
                    from unstructured.partition.doc import partition_doc
                    elements = partition_doc(filename=str(file_path))
                    text_parts = []
                    for element in elements:
                        if hasattr(element, 'text') and element.text:
                            text_parts.append(element.text)
                    text = '\n\n'.join(text_parts)
                except ImportError:
                    # 回退到docx2txt
                    import docx2txt
                    text = docx2txt.process(str(file_path))
                
                from langchain_core.documents import Document as LangchainDocument
                documents = [LangchainDocument(page_content=text, metadata={'source': str(file_path)})]
                logger.info(f"成功处理旧版Word文件: {file_path}")
                return documents
            elif file_extension in ['.xlsx', '.xls']:
                loader = UnstructuredExcelLoader(str(file_path))
            elif file_extension in ['.pptx', '.ppt']:
                loader = UnstructuredPowerPointLoader(str(file_path))
            else:
                raise ValueError(f"不支持的文件类型: {file_extension}")
            
            documents = loader.load()
            logger.info(f"基础文档加载完成: {file_path}, 页数: {len(documents)}")
            return documents
            
        except Exception as e:
            logger.error(f"基础文档加载失败 {file_path}: {str(e)}")
            raise
    
    async def add_document(self, workspace_id: str, file_path: str, metadata: Dict[str, Any] = None) -> bool:
        """添加文档到高级RAG系统"""
        try:
            # 加载文档
            documents = self._load_document(file_path)
            
            if not documents:
                logger.warning(f"文档为空: {file_path}")
                return False
            
            # 添加元数据
            if metadata:
                original_filename = metadata.get('original_filename', '')
                for doc in documents:
                    doc.metadata.update(metadata)
                    # 将文件名添加到文档内容开头
                    if original_filename:
                        doc.page_content = f"文件名: {original_filename}\n\n{doc.page_content}"
            
            # 智能分块
            chunked_documents = self._smart_chunk_documents(documents)
            
            # 获取混合检索器
            hybrid_retriever = self._get_hybrid_retriever(workspace_id)
            
            # 添加到向量存储
            vector_store_path = self.vector_db_path / f"workspace_{workspace_id}"
            vector_store_path.mkdir(exist_ok=True)
            
            # 加载或创建向量存储
            if vector_store_path.exists():
                vector_store = FAISS.load_local(
                    str(vector_store_path),
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                vector_store.add_documents(chunked_documents)
            else:
                vector_store = FAISS.from_documents(chunked_documents, self.embeddings)
            
            # 保存向量存储
            vector_store.save_local(str(vector_store_path))
            
            # 更新混合检索器
            hybrid_retriever._build_bm25_index()
            
            logger.info(f"文档添加成功: {file_path}, 工作区: {workspace_id}")
            return True
            
        except Exception as e:
            logger.error(f"文档添加失败: {str(e)}")
            return False
    
    async def search_documents(self, workspace_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """高级文档搜索"""
        try:
            hybrid_retriever = self._get_hybrid_retriever(workspace_id)
            
            # 使用混合检索
            results = hybrid_retriever.search(query, top_k=top_k, use_rerank=True)
            
            logger.info(f"高级搜索完成: 查询='{query}', 结果数={len(results)}")
            return results
            
        except Exception as e:
            logger.error(f"高级文档搜索失败: {str(e)}")
            return []
    
    async def ask_question(self, workspace_id: str, question: str, top_k: int = 5) -> Dict[str, Any]:
        """使用高级RAG回答问题"""
        try:
            # 使用混合检索搜索相关文档
            search_results = await self.search_documents(workspace_id, question, top_k)
            
            if not search_results:
                raise Exception(f"工作区 {workspace_id} 没有相关文档")
            
            # 构建上下文
            context_parts = []
            references = []
            
            for i, result in enumerate(search_results):
                content = result['content']
                context_parts.append(f"[文档片段 {i+1}]\n{content}")
                
                # 构建引用信息
                reference = {
                    'document_id': result.get('doc_id', f'doc_{i}'),
                    'document_name': result.get('metadata', {}).get('original_filename', f'文档_{i+1}'),
                    'chunk_id': result.get('doc_id', f'chunk_{i}'),
                    'content': content[:300] + "..." if len(content) > 300 else content,
                    'page_number': result.get('metadata', {}).get('page_number', 1),
                    'similarity': result.get('rerank_score', result.get('fused_score', 0.8)),
                    'rank': i + 1,
                    'highlight': self._extract_keywords(question, content),
                    'access_url': f"/api/documents/{result.get('doc_id', f'doc_{i}')}/preview"
                }
                references.append(reference)
            
            context = "\n\n".join(context_parts)
            
            # 创建增强的提示模板
            prompt_template = """你是一个专业的AI助手，请根据以下上下文信息回答问题。

上下文信息:
{context}

问题: {input}

回答要求：
1. 基于上下文信息提供准确、详细的回答
2. 如果上下文信息不足，可以结合你的通用知识
3. 在回答中引用具体的文档片段
4. 回答要简洁明了，重点突出

请提供专业、准确的回答:"""
            
            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["context", "input"]
            )
            
            # 创建文档链
            document_chain = create_stuff_documents_chain(self.llm, prompt)
            
            # 生成回答
            response = await document_chain.ainvoke({
                "context": context,
                "input": question
            })
            
            # 安全提取答案
            answer = response.get("answer", "")
            if isinstance(answer, dict):
                answer = str(answer)
            elif not isinstance(answer, str):
                answer = str(answer)
            
            return {
                "answer": answer,
                "references": references,
                "sources": search_results,
                "confidence": 0.9,
                "metadata": {
                    "model": "gpt-3.5-turbo",
                    "mode": "advanced_rag",
                    "retrieval_method": "hybrid",
                    "reranked": True,
                    "retrieved_chunks": len(search_results),
                    "query": question
                }
            }
            
        except Exception as e:
            logger.error(f"高级RAG问答失败: {str(e)}")
            raise Exception("高级RAG服务不可用")
    
    def _extract_keywords(self, query: str, content: str) -> str:
        """提取关键词用于高亮"""
        # 简单的关键词提取
        query_words = query.split()
        highlighted_words = []
        
        for word in query_words:
            if len(word) > 2 and word in content:
                highlighted_words.append(word)
        
        return ", ".join(highlighted_words[:3])  # 最多返回3个关键词
    
    def get_workspace_stats(self, workspace_id: str) -> Dict[str, Any]:
        """获取工作区统计信息"""
        try:
            hybrid_retriever = self._get_hybrid_retriever(workspace_id)
            stats = hybrid_retriever.get_stats()
            
            return {
                "workspace_id": workspace_id,
                "document_count": stats['document_count'],
                "status": "active" if stats['document_count'] > 0 else "empty",
                "retrieval_methods": {
                    "bm25_available": stats['bm25_available'],
                    "vector_available": stats['vector_available'],
                    "reranker_available": stats['reranker_available']
                },
                "config": {
                    "bm25_weight": stats['bm25_weight'],
                    "vector_weight": stats['vector_weight'],
                    "rrf_k": stats['rrf_k']
                }
            }
        except Exception as e:
            logger.error(f"获取工作区统计失败: {str(e)}")
            return {
                "workspace_id": workspace_id,
                "document_count": 0,
                "status": "error",
                "error": str(e)
            }
    
    def delete_document(self, workspace_id: str, doc_id: str) -> bool:
        """删除文档"""
        try:
            hybrid_retriever = self._get_hybrid_retriever(workspace_id)
            
            # 从向量存储中删除
            vector_store_path = self.vector_db_path / f"workspace_{workspace_id}"
            if vector_store_path.exists():
                vector_store = FAISS.load_local(
                    str(vector_store_path),
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                
                if hasattr(vector_store, 'docstore') and hasattr(vector_store.docstore, '_dict'):
                    if doc_id in vector_store.docstore._dict:
                        del vector_store.docstore._dict[doc_id]
                        vector_store.save_local(str(vector_store_path))
                        
                        # 重建BM25索引
                        hybrid_retriever._build_bm25_index()
                        
                        logger.info(f"文档删除成功: {doc_id}")
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"文档删除失败: {str(e)}")
            return False
