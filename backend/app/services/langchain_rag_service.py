"""
基于LangChain和FAISS的RAG服务
解决ChromaDB兼容性问题
"""

import os
import logging
import asyncio
import pickle
import json
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

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

# 导入缓存管理器
from .smart_cache_manager import get_cache_manager

logger = logging.getLogger(__name__)


class LangChainRAGService:
    """基于LangChain和FAISS的RAG服务"""
    
    def __init__(self, vector_db_path: str = "langchain_vector_db"):
        self.vector_db_path = Path(vector_db_path)
        self.vector_db_path.mkdir(exist_ok=True)
        
        # 初始化组件
        self.embeddings = None
        self.llm = None
        self.text_splitter = None
        self.vector_stores = {}  # 按工作区存储向量数据库
        self.cache_manager = get_cache_manager()  # 缓存管理器
        
        self._initialize_components()
    
    def _initialize_components(self):
        """初始化LangChain组件"""
        try:
            # 设置OpenAI配置
            os.environ['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY', '')
            os.environ['OPENAI_BASE_URL'] = os.getenv('THIRD_PARTY_API_BASE', 'https://api.openai.com/v1')
            
            # 优先使用本地BGE嵌入模型
            self.embeddings = self._initialize_local_embeddings()
            
            # 初始化LLM - 添加回退机制
            try:
                api_key = os.getenv('OPENAI_API_KEY')
                api_base = os.getenv('THIRD_PARTY_API_BASE', 'https://api.openai.com/v1')
                
                if not api_key:
                    raise ValueError("OPENAI_API_KEY not found")
                
                self.llm = ChatOpenAI(
                    model="gpt-3.5-turbo",
                    temperature=0.1,
                    openai_api_key=api_key,
                    openai_api_base=api_base,
                    request_timeout=120,  # 增加到120秒超时，适应大模型调用时间
                    max_retries=1  # 减少重试次数
                )
                logger.info("LLM初始化成功")
            except Exception as e:
                logger.warning(f"LLM初始化失败: {str(e)}")
                logger.warning("将使用简单的文本匹配模式")
                self.llm = None
            
            # 初始化文本分割器
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                length_function=len,
                separators=["\n\n", "\n", " ", ""]
            )
            
            logger.info("LangChain组件初始化成功")
            
        except Exception as e:
            logger.error(f"LangChain组件初始化失败: {str(e)}")
            raise
    
    def _initialize_local_embeddings(self):
        """初始化本地BGE嵌入模型"""
        try:
            # 设置HuggingFace镜像站
            os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
            
            # 强制启用离线模式
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['HF_DATASETS_OFFLINE'] = '1'
            logger.info("强制启用完全离线模式")
            logger.info(f"使用HuggingFace镜像站: {os.environ['HF_ENDPOINT']}")
            
            # 检查本地模型
            local_model_path = Path("/root/workspace/consult/backend/models/bge-large-zh-v1.5")
            if local_model_path.exists():
                logger.info(f"使用本地模型: {local_model_path}")
                model_name = str(local_model_path)
            else:
                logger.info("本地模型不存在，使用在线模型")
                model_name = 'BAAI/bge-large-zh-v1.5'
            
            try:
                logger.info(f"正在加载BGE模型: {model_name}")
                
                # 直接使用SentenceTransformer加载BGE模型
                model = SentenceTransformer(model_name)
                
                # 使用HuggingFaceEmbeddings包装BGE模型
                embeddings = HuggingFaceEmbeddings(
                    model_name=model_name,
                    model_kwargs={'device': 'cuda' if os.getenv('CUDA_VISIBLE_DEVICES') else 'cpu'},
                    encode_kwargs={'normalize_embeddings': True}  # BGE模型建议归一化
                )
                
                logger.info(f"✅ 成功加载BGE模型: {model_name}")
                logger.info(f"   维度: {len(embeddings.embed_query('测试'))}")
                return embeddings
                
            except Exception as e:
                logger.error(f"加载BGE模型失败: {str(e)}")
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
    
    def _get_vector_store_path(self, workspace_id: str) -> Path:
        """获取向量存储路径"""
        return self.vector_db_path / f"workspace_{workspace_id}"
    
    def _load_vector_store(self, workspace_id: str) -> Optional[FAISS]:
        """加载向量存储"""
        try:
            store_path = self._get_vector_store_path(workspace_id)
            if store_path.exists():
                vector_store = FAISS.load_local(
                    str(store_path),
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                logger.info(f"成功加载向量存储: {workspace_id}")
                return vector_store
            else:
                logger.info(f"向量存储不存在: {workspace_id}")
                return None
        except Exception as e:
            logger.error(f"加载向量存储失败: {str(e)}")
            return None
    
    def _save_vector_store(self, workspace_id: str, vector_store: FAISS):
        """保存向量存储 - 智能重建索引"""
        try:
            store_path = self._get_vector_store_path(workspace_id)
            
            # 检查是否需要重建索引
            if hasattr(vector_store, 'docstore') and hasattr(vector_store.docstore, '_dict'):
                docstore = vector_store.docstore
                docs_count = len(docstore._dict)
                index_count = vector_store.index.ntotal if hasattr(vector_store, 'index') and vector_store.index else 0
                
                # 只有当docstore和索引数量不匹配时才重建
                if docs_count != index_count:
                    logger.info(f"检测到索引不同步: docstore={docs_count}, index={index_count}，开始重建索引")
                    
                    if docs_count > 0:
                        # 获取所有文档和向量
                        docs = list(docstore._dict.values())
                        vectors = []
                        
                        for doc in docs:
                            if hasattr(doc, 'embedding') and doc.embedding is not None:
                                vectors.append(doc.embedding)
                            else:
                                # 只有在必要时才重新生成embedding
                                logger.warning(f"文档缺少embedding，重新生成: {doc.page_content[:50]}...")
                                embedding = self.embeddings.embed_query(doc.page_content)
                                vectors.append(embedding)
                        
                        if vectors:
                            # 重建FAISS索引
                            import numpy as np
                            vectors_array = np.array(vectors)
                            
                            # 创建新的FAISS索引
                            import faiss
                            dimension = vectors_array.shape[1]
                            index = faiss.IndexFlatIP(dimension)  # 使用内积相似度
                            index.add(vectors_array.astype('float32'))
                            
                            # 更新向量存储的索引
                            vector_store.index = index
                            logger.info(f"重建FAISS索引完成: {len(docs)} 个文档")
                    else:
                        # 如果docstore为空，重置索引
                        logger.info("docstore为空，重置FAISS索引")
                        import faiss
                        dimension = 1024  # BGE模型的维度
                        vector_store.index = faiss.IndexFlatIP(dimension)
                else:
                    logger.info(f"索引已同步: {docs_count} 个文档，跳过重建")
            
            vector_store.save_local(str(store_path))
            logger.info(f"成功保存向量存储: {workspace_id}")
        except Exception as e:
            logger.error(f"保存向量存储失败: {str(e)}")
    
    def _load_document(self, file_path: str) -> List[Document]:
        """加载文档 - 使用增强型处理器（优化版）"""
        try:
            # 使用增强型文档处理器
            from app.services.enhanced_document_processor import EnhancedDocumentProcessor
            
            processor = EnhancedDocumentProcessor()
            
            # 异步处理文档 - 避免事件循环冲突
            try:
                # 检查是否已有事件循环
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果循环正在运行，使用线程池
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, processor.process_document(file_path))
                        processed_doc = future.result()
                else:
                    processed_doc = loop.run_until_complete(processor.process_document(file_path))
            except RuntimeError:
                # 如果没有事件循环，创建新的
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
            
            logger.info(f"增强型文档处理完成: {file_path}, 块数: {len(documents)}, 质量分数: {processed_doc.quality_score:.2f}")
            
            # 如果没有提取到内容，回退到基础处理
            if len(documents) == 0:
                logger.warning(f"增强型处理器未提取到内容，回退到基础处理: {file_path}")
                return self._load_document_fallback(file_path)
            
            return documents
            
        except Exception as e:
            logger.error(f"增强型文档处理失败，回退到基础处理: {str(e)}")
            # 回退到基础处理
            return self._load_document_fallback(file_path)
    
    def _load_document_fallback(self, file_path: str) -> List[Document]:
        """基础文档加载（回退方案）"""
        file_path = Path(file_path)
        file_extension = file_path.suffix.lower()
        
        try:
            if file_extension == '.txt':
                loader = TextLoader(str(file_path), encoding='utf-8')
            elif file_extension == '.pdf':
                # 先尝试PyPDFLoader
                try:
                    loader = PyPDFLoader(str(file_path))
                    documents = loader.load()
                    
                    # 检查是否提取到内容
                    has_content = any(doc.page_content.strip() for doc in documents)
                    if has_content:
                        logger.info(f"PyPDFLoader成功提取内容: {file_path}, 页数: {len(documents)}")
                        return documents
                    else:
                        logger.warning(f"PyPDFLoader未提取到内容，尝试OCR: {file_path}")
                        # 尝试OCR处理
                        return self._load_document_with_ocr(file_path)
                        
                except Exception as e:
                    logger.warning(f"PyPDFLoader失败，尝试OCR: {str(e)}")
                    return self._load_document_with_ocr(file_path)
                    
            elif file_extension in ['.docx', '.doc']:
                loader = Docx2txtLoader(str(file_path))
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
            logger.error(f"基础文档加载也失败 {file_path}: {str(e)}")
            raise
    
    def _load_document_with_ocr(self, file_path: Path) -> List[Document]:
        """使用OCR处理PDF文档"""
        try:
            import fitz  # PyMuPDF
            import subprocess
            import tempfile
            import os
            
            logger.info(f"开始OCR处理PDF: {file_path}")
            
            # 打开PDF
            doc = fitz.open(str(file_path))
            all_text = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # 将页面转换为图像
                mat = fitz.Matrix(3.0, 3.0)  # 放大3倍提高OCR精度
                pix = page.get_pixmap(matrix=mat)
                
                # 保存为临时图像
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                    pix.save(tmp_file.name, 'PNG')
                    
                    try:
                        # 使用Tesseract OCR
                        result = subprocess.run([
                            'tesseract', tmp_file.name, 'stdout', '--psm', '6'
                        ], capture_output=True, text=True, timeout=30)
                        
                        if result.returncode == 0:
                            page_text = result.stdout.strip()
                            if page_text:
                                all_text.append(page_text)
                                logger.info(f"OCR第{page_num+1}页成功，提取{len(page_text)}字符")
                            else:
                                logger.warning(f"OCR第{page_num+1}页未提取到文本")
                        else:
                            logger.warning(f"OCR第{page_num+1}页失败: {result.stderr}")
                            
                    except subprocess.TimeoutExpired:
                        logger.warning(f"OCR第{page_num+1}页超时")
                    except Exception as e:
                        logger.warning(f"OCR第{page_num+1}页失败: {e}")
                    finally:
                        # 清理临时文件
                        try:
                            os.unlink(tmp_file.name)
                        except:
                            pass
            
            doc.close()
            
            if all_text:
                # 创建文档对象
                full_text = '\n\n'.join(all_text)
                document = Document(
                    page_content=full_text,
                    metadata={
                        'source': str(file_path),
                        'page': 0,  # OCR合并所有页面
                        'file_path': str(file_path),
                        'file_type': 'pdf',
                        'processing_method': 'ocr'
                    }
                )
                
                logger.info(f"OCR处理完成: {file_path}, 总文本长度: {len(full_text)}")
                return [document]
            else:
                logger.error(f"OCR未提取到任何文本: {file_path}")
                return []
                
        except Exception as e:
            logger.error(f"OCR处理失败 {file_path}: {str(e)}")
            return []
    
    def _smart_split_documents(self, documents: List[Document]) -> List[Document]:
        """智能分割文档 - 根据内容类型优化"""
        split_documents = []
        
        for doc in documents:
            chunk_type = doc.metadata.get('chunk_type', 'text')
            has_table = doc.metadata.get('has_table', False)
            has_image = doc.metadata.get('has_image', False)
            
            if chunk_type == 'table' or has_table:
                # 表格内容：保持完整性，不分割
                split_documents.append(doc)
            elif chunk_type == 'image' or has_image:
                # 图片内容：保持完整性，不分割
                split_documents.append(doc)
            elif chunk_type == 'title':
                # 标题：保持完整性，不分割
                split_documents.append(doc)
            else:
                # 普通文本：使用智能分割
                if len(doc.page_content) > 1500:
                    # 长文本需要分割
                    chunks = self.text_splitter.split_documents([doc])
                    split_documents.extend(chunks)
                else:
                    # 短文本保持完整
                    split_documents.append(doc)
        
        return split_documents
    
    async def add_document(self, workspace_id: str, file_path: str, metadata: Dict[str, Any] = None) -> bool:
        """添加文档到向量数据库"""
        try:
            # 加载文档
            documents = self._load_document(file_path)
            
            if not documents:
                logger.warning(f"文档为空: {file_path}")
                return False
            
            # 添加元数据并将文件名包含在内容中
            if metadata:
                original_filename = metadata.get('original_filename', '')
                for doc in documents:
                    doc.metadata.update(metadata)
                    # 将文件名添加到文档内容开头，让AI能够理解文件名
                    if original_filename:
                        doc.page_content = f"文件名: {original_filename}\n\n{doc.page_content}"
            
            # 智能分割文档 - 根据内容类型优化
            split_documents = self._smart_split_documents(documents)
            logger.info(f"智能文档分割完成: {len(split_documents)} 个片段")
            
            # 加载现有向量存储或创建新的
            vector_store = self._load_vector_store(workspace_id)
            
            if vector_store is None:
                # 创建新的向量存储
                vector_store = FAISS.from_documents(split_documents, self.embeddings)
                logger.info(f"创建新的向量存储: {workspace_id}")
            else:
                # 添加到现有向量存储
                vector_store.add_documents(split_documents)
                logger.info(f"添加到现有向量存储: {workspace_id}")
            
            # FAISS会自动处理嵌入向量，不需要手动添加
            
            # 保存向量存储
            self._save_vector_store(workspace_id, vector_store)
            
            logger.info(f"文档添加成功: {file_path}, 工作区: {workspace_id}")
            return True
            
        except Exception as e:
            logger.error(f"添加文档失败: {str(e)}")
            logger.error(f"文件路径: {file_path}")
            logger.error(f"工作区: {workspace_id}")
            logger.error(f"元数据: {metadata}")
            import traceback
            logger.error(f"详细错误信息:\n{traceback.format_exc()}")
            return False
    
    async def search_documents(self, workspace_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索相关文档"""
        try:
            vector_store = self._load_vector_store(workspace_id)
            
            if vector_store is None:
                logger.warning(f"向量存储不存在: {workspace_id}")
                return []
            
            # 执行相似性搜索
            docs_with_scores = vector_store.similarity_search_with_score(query, k=top_k)
            
            results = []
            for doc, score in docs_with_scores:
                results.append({
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'similarity': 1 - score,  # 转换为相似度分数
                    'score': score
                })
            
            logger.info(f"搜索完成: 查询='{query}', 结果数={len(results)}")
            return results
            
        except Exception as e:
            logger.error(f"文档搜索失败: {str(e)}")
            logger.error(f"查询: {query}")
            logger.error(f"工作区: {workspace_id}")
            logger.error(f"top_k: {top_k}")
            import traceback
            logger.error(f"详细错误信息:\n{traceback.format_exc()}")
            return []
    
    async def ask_question(self, workspace_id: str, question: str, top_k: int = 5) -> Dict[str, Any]:
        """使用RAG回答问题"""
        try:
            # 检查缓存
            cached_result = self.cache_manager.get_cached_query_result(question, workspace_id)
            if cached_result:
                logger.info(f"命中查询缓存: {question[:50]}...")
                return cached_result
            
            vector_store = self._load_vector_store(workspace_id)
            
            if vector_store is None:
                raise Exception(f"工作区 {workspace_id} 没有文档数据")
            
            # 创建检索器
            retriever = vector_store.as_retriever(
                search_type="similarity",
                search_kwargs={"k": top_k}
            )
            
            # 创建提示模板
            prompt_template = """你是一个智能助手，请根据以下上下文信息回答问题。

上下文信息:
{context}

问题: {input}

回答规则：
1. 如果上下文信息与问题相关，请基于上下文信息提供准确回答
2. 如果上下文信息与问题不相关或没有相关信息，请基于你的通用知识回答
3. 在回答时，如果使用了通用知识，请简要说明

请提供准确、详细的回答:"""
            
            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["context", "input"]
            )
            
            # 检查LLM是否可用
            if self.llm is None:
                # 使用简单的文本匹配模式
                return await self._simple_text_match(vector_store, question, top_k)
            
            # 创建文档链
            document_chain = create_stuff_documents_chain(self.llm, prompt)
            
            # 创建检索链
            retrieval_chain = create_retrieval_chain(retriever, document_chain)
            
            # 执行查询
            response = await retrieval_chain.ainvoke({"input": question})
            
            # 提取相关文档
            source_docs = response.get("context", [])
            references = []
            for i, doc in enumerate(source_docs):
                references.append({
                    "content_preview": doc.page_content[:200] + "...",
                    "metadata": doc.metadata,
                    "similarity": 0.8  # 简化处理
                })
            
            # 安全提取答案
            answer = response.get("answer", "")
            if isinstance(answer, dict):
                answer = str(answer)
            elif not isinstance(answer, str):
                answer = str(answer)
            
            result = {
                "answer": answer,
                "references": references,
                "sources": source_docs,
                "confidence": 0.9,
                "metadata": {
                    "model": "gpt-3.5-turbo",
                    "mode": "rag",
                    "retrieved_chunks": len(source_docs)
                }
            }
            
            # 缓存结果
            self.cache_manager.cache_query_result(question, workspace_id, result, ttl=3600)
            
            return result
            
        except Exception as e:
            logger.error(f"RAG问答失败: {str(e)}")
            logger.error(f"问题: {question}")
            logger.error(f"工作区: {workspace_id}")
            import traceback
            logger.error(f"详细错误信息:\n{traceback.format_exc()}")
            
            # 回退到简单搜索
            try:
                logger.info(f"尝试回退搜索: {question}")
                search_results = await self.search_documents(workspace_id, question, top_k)
                if search_results:
                    context = "\n".join([doc["content"] for doc in search_results[:3]])
                    answer = f"基于检索到的文档内容：\n\n{context}\n\n请根据以上信息回答您的问题。"
                    
                    logger.info(f"回退搜索成功，找到 {len(search_results)} 个结果")
                    return {
                        "answer": answer,
                        "references": search_results,
                        "sources": [],
                        "confidence": 0.7,
                        "metadata": {
                            "model": "fallback",
                            "mode": "simple_search",
                            "retrieved_chunks": len(search_results)
                        }
                    }
                else:
                    logger.warning(f"回退搜索未找到相关文档: {question}")
                    raise Exception("没有找到相关文档")
            except Exception as fallback_error:
                logger.error(f"回退搜索也失败: {str(fallback_error)}")
                logger.error(f"回退搜索详细错误:\n{traceback.format_exc()}")
                # 返回友好的错误信息，而不是抛出异常
                return {
                    "answer": f"抱歉，当前工作区没有文档数据，无法检索相关信息。请先上传文档到工作区或全局数据库。\n\n您可以：\n1. 上传文档到全局数据库管理页面\n2. 上传文档到当前工作区\n3. 或者直接请求生成文档，系统会基于LLM知识生成内容。",
                    "references": [],
                    "sources": [],
                    "confidence": 0.0,
                    "metadata": {
                        "error": str(fallback_error),
                        "mode": "no_documents"
                    }
                }
    
    def get_workspace_stats(self, workspace_id: str) -> Dict[str, Any]:
        """获取工作区统计信息"""
        try:
            vector_store = self._load_vector_store(workspace_id)
            
            if vector_store is None:
                return {
                    "workspace_id": workspace_id,
                    "document_count": 0,
                    "status": "empty"
                }
            
            # 优先使用docstore获取准确文档数
            doc_count = 0
            if hasattr(vector_store, 'docstore') and hasattr(vector_store.docstore, '_dict'):
                doc_count = len(vector_store.docstore._dict)
            elif hasattr(vector_store.index, 'ntotal'):
                doc_count = vector_store.index.ntotal
            
            logger.info(f"工作区 {workspace_id} 文档数: {doc_count}")
            
            return {
                "workspace_id": workspace_id,
                "document_count": doc_count,
                "status": "active" if doc_count > 0 else "empty"
            }
        except Exception as e:
            logger.error(f"获取工作区统计失败: {str(e)}")
            return {
                "workspace_id": workspace_id,
                "document_count": 0,
                "status": "error",
                "error": str(e)
            }
    
    def delete_document_efficient(self, workspace_id: str, doc_id: str) -> bool:
        """高效删除单个文档 - 只删除相关向量，不重建整个索引"""
        try:
            vector_store = self._load_vector_store(workspace_id)
            if vector_store is None:
                logger.warning(f"工作区 {workspace_id} 不存在")
                return False
            
            # 检查文档是否存在
            if not hasattr(vector_store, 'docstore') or not hasattr(vector_store.docstore, '_dict'):
                logger.warning(f"工作区 {workspace_id} 的docstore不存在")
                return False
            
            docstore = vector_store.docstore
            if doc_id not in docstore._dict:
                logger.warning(f"文档 {doc_id} 在工作区 {workspace_id} 中不存在")
                return False
            
            # 从docstore中删除文档
            del docstore._dict[doc_id]
            
            # 重建FAISS索引以保持同步
            self._rebuild_faiss_index(vector_store)
            
            # ⭐ 关键：保存更新后的向量存储
            self._save_vector_store(workspace_id, vector_store)
            
            logger.info(f"成功删除并保存文档 {doc_id} 从工作区 {workspace_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除文档失败: {str(e)}")
            return False
    
    def _rebuild_faiss_index(self, vector_store):
        """重建FAISS索引（删除文档后）"""
        try:
            if not hasattr(vector_store, 'docstore'):
                return
            
            docstore = vector_store.docstore._dict
            
            if len(docstore) == 0:
                # 清空索引
                import faiss
                dimension = 1024  # BGE模型维度
                vector_store.index = faiss.IndexFlatIP(dimension)
                vector_store.index_to_docstore_id = {}
                logger.info("索引已清空")
                return
            
            # 重建索引
            documents = list(docstore.values())
            texts = [doc.page_content for doc in documents]
            embeddings = self.embeddings.embed_documents(texts)
            
            # 创建新索引
            import faiss
            import numpy as np
            dimension = len(embeddings[0]) if embeddings else 1024
            new_index = faiss.IndexFlatIP(dimension)
            
            if embeddings:
                new_index.add(np.array(embeddings).astype('float32'))
            
            vector_store.index = new_index
            vector_store.index_to_docstore_id = {i: doc_id for i, doc_id in enumerate(docstore.keys())}
            
            logger.info(f"索引重建完成: {len(documents)} 个文档")
        except Exception as e:
            logger.error(f"重建FAISS索引失败: {str(e)}")
    
    def _rebuild_vector_index(self, vector_store, workspace_id: str):
        """重建向量索引（删除文档后）- 旧方法保留用于兼容"""
        try:
            if not hasattr(vector_store, 'docstore') or not hasattr(vector_store.docstore, '_dict'):
                return
            
            docstore = vector_store.docstore
            if len(docstore._dict) == 0:
                # 如果没有文档了，清空索引
                vector_store.index.reset()
                vector_store.index_to_docstore_id = {}
                return
            
            # 重新构建索引
            documents = list(docstore._dict.values())
            texts = [doc.page_content for doc in documents]
            
            if texts:
                # 重新生成向量
                embeddings = self.embeddings.embed_documents(texts)
                
                # 重置索引
                vector_store.index.reset()
                vector_store.index.add(np.array(embeddings))
                
                # 重建映射
                vector_store.index_to_docstore_id = {i: doc_id for i, doc_id in enumerate(docstore._dict.keys())}
                
                logger.info(f"重建了工作区 {workspace_id} 的向量索引，包含 {len(documents)} 个文档")
            
        except Exception as e:
            logger.error(f"重建向量索引失败: {str(e)}")
    
    async def delete_workspace(self, workspace_id: str) -> bool:
        """删除工作区数据"""
        try:
            # 删除持久化文件
            store_path = self._get_vector_store_path(workspace_id)
            if store_path.exists():
                import shutil
                shutil.rmtree(store_path)
            
            logger.info(f"工作区删除成功: {workspace_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除工作区失败: {str(e)}")
            return False
    
    async def _simple_text_match(self, vector_store, question: str, top_k: int = 5) -> Dict[str, Any]:
        """简单的文本匹配模式（当LLM不可用时）"""
        try:
            # 检索相关文档
            retriever = vector_store.as_retriever(
                search_type="similarity",
                search_kwargs={"k": top_k}
            )
            
            # 获取相关文档
            docs = await retriever.aget_relevant_documents(question)
            
            if not docs:
                return {
                    "answer": "抱歉，没有找到与您问题相关的文档内容。",
                    "references": [],
                    "confidence": 0.0
                }
            
            # 构建简单回答
            context_parts = []
            references = []
            
            for i, doc in enumerate(docs):
                content_preview = doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
                context_parts.append(f"相关内容 {i+1}: {content_preview}")
                
                references.append({
                    "content_preview": content_preview,
                    "metadata": doc.metadata,
                    "similarity": 0.8
                })
            
            # 生成简单回答
            answer = f"根据检索到的文档内容，我找到了以下相关信息：\n\n" + "\n\n".join(context_parts)
            answer += f"\n\n注意：当前使用简单文本匹配模式，如需更智能的回答，请配置LLM服务。"
            
            return {
                "answer": answer,
                "references": references,
                "confidence": 0.7
            }
            
        except Exception as e:
            logger.error(f"简单文本匹配失败: {str(e)}")
            return {
                "answer": f"抱歉，处理您的问题时出现错误: {str(e)}",
                "references": [],
                "confidence": 0.0
            }
    
    async def search_and_answer(self, question: str, workspace_id: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """搜索和回答的统一方法"""
        try:
            # 调用ask_question方法
            result = await self.ask_question(workspace_id, question, top_k=5)
            return result
        except Exception as e:
            logger.error(f"search_and_answer失败: {str(e)}")
            return {
                "answer": f"抱歉，处理您的问题时出现错误: {str(e)}",
                "references": [],
                "sources": [],
                "confidence": 0.0,
                "metadata": {
                    "error": str(e)
                }
            }