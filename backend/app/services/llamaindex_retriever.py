"""
LlamaIndex 高级检索引擎
提供混合检索、重排序、语义分块、上下文压缩等功能
"""

from typing import List, Dict, Optional, Any
from pathlib import Path
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

try:
    # 使用最小依赖集合，避免触发 LLM 模块
    from llama_index.core.indices.vector_store import VectorStoreIndex
    from llama_index.core.storage.storage_context import StorageContext
    from llama_index.core.indices.loading import load_index_from_storage
    from llama_index.core.node_parser import SemanticSplitterNodeParser
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.core import SimpleDirectoryReader
    from llama_index.core import Document as LI_Document  # type: ignore
except ImportError as e:
    # 0.10.x 备用导入路径（进一步最小化）
    logger.error(f"LlamaIndex 导入失败: {e}，尝试备用路径")
    try:
        from llama_index import VectorStoreIndex, StorageContext, load_index_from_storage, SimpleDirectoryReader
        from llama_index.node_parser import SemanticSplitterNodeParser
        from llama_index.embeddings import HuggingFaceEmbedding
    except ImportError:
        raise ImportError("无法导入 LlamaIndex 模块，请检查安装")

# 全局缓存：避免重复加载模型和索引
_retriever_cache = {}
_cache_lock = threading.Lock()  # 线程锁，确保并发安全

def get_retriever(workspace_id: str = "global") -> "LlamaIndexRetriever":
    """
    获取或创建检索器（单例模式，线程安全）
    重要：请使用此函数获取检索器实例，而不是直接实例化 LlamaIndexRetriever
    """
    # 第一次快速检查（无锁，用于已经缓存的情况）
    if workspace_id in _retriever_cache:
        logger.debug(f"使用缓存的检索器: {workspace_id}")
        return _retriever_cache[workspace_id]
    
    # 需要创建时，使用锁确保线程安全
    with _cache_lock:
        # 双重检查，防止在获取锁的期间其他线程已经创建了实例
        if workspace_id not in _retriever_cache:
            logger.info(f"创建新的检索器实例: {workspace_id}（这可能需要几秒钟加载模型和索引）")
            _retriever_cache[workspace_id] = LlamaIndexRetriever(workspace_id)
            logger.info(f"✅ 检索器实例创建完成: {workspace_id}")
        else:
            logger.debug(f"检索器已被其他线程创建，使用缓存: {workspace_id}")
        return _retriever_cache[workspace_id]

class LlamaIndexRetriever:
    """LlamaIndex 高级检索引擎 - 为 LangGraph 提供检索服务"""
    
    def __init__(self, workspace_id: str = "global"):
        init_start_time = time.time()
        logger.info(f"LlamaIndexRetriever init 开始: workspace_id={workspace_id}")
        self.workspace_id = workspace_id
        self.storage_dir = Path(f"llamaindex_storage/{workspace_id}")
        
        # 嵌入模型（强制本地加载，避免连接HuggingFace）
        model_load_start = time.time()
        local_model_dir = os.getenv("LOCAL_BGE_MODEL_DIR", "")
        logger.info(f"本地BGE模型: {local_model_dir}")
        if not local_model_dir or not Path(local_model_dir).exists():
            raise RuntimeError(
                f"LOCAL_BGE_MODEL_DIR 未设置或目录不存在: {local_model_dir}\n"
                f"请设置环境变量 LOCAL_BGE_MODEL_DIR 指向本地BGE模型目录，或确保该目录存在。"
            )
        # 强制离线模式
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['HF_DATASETS_OFFLINE'] = '1'
        logger.info(f"开始加载BGE嵌入模型（这可能需要几秒到几十秒）...")
        self.embed_model = HuggingFaceEmbedding(
            model_name=local_model_dir,
            cache_folder=local_model_dir  # 使用模型目录作为缓存
        )
        model_load_time = time.time() - model_load_start
        logger.info(f"✅ BGE模型加载完成（耗时 {model_load_time:.2f} 秒）: {local_model_dir}")
        
        # 语义分块器
        parser_start = time.time()
        self.node_parser = SemanticSplitterNodeParser(
            buffer_size=1,
            breakpoint_percentile_threshold=95,
            embed_model=self.embed_model
        )
        parser_time = time.time() - parser_start
        logger.debug(f"语义分块器初始化完成（耗时 {parser_time:.2f} 秒）")
        
        # # 后处理器栈
        # self._init_postprocessors()
        
        # 索引
        index_load_start = time.time()
        self.index = self._load_or_create_index()
        index_load_time = time.time() - index_load_start
        logger.info(f"✅ 索引加载完成（耗时 {index_load_time:.2f} 秒）")
        
        total_time = time.time() - init_start_time
        logger.info(f"✅ LlamaIndexRetriever 初始化完成（总耗时 {total_time:.2f} 秒）：模型={model_load_time:.2f}s, 索引={index_load_time:.2f}s")
    
    def _init_postprocessors(self):
        """初始化后处理器栈"""
        # 重排序
        self.reranker = SentenceTransformerRerank(
            model="BAAI/bge-reranker-v2-m3",
            top_n=10
        )
        
        # 相似度过滤
        self.similarity_filter = SimilarityPostprocessor(
            similarity_cutoff=0.7
        )
        
        # 句子级压缩（LlamaIndex 原生）- 如果可用则启用
        if SentenceEmbeddingOptimizer is not None:
            self.sentence_optimizer = SentenceEmbeddingOptimizer(
                embed_model=self.embed_model,
                percentile_cutoff=0.5,
                threshold_cutoff=0.7
            )
        else:
            logger.warning("SentenceEmbeddingOptimizer 不可用，跳过句子级压缩")
            self.sentence_optimizer = None
        
        # 长上下文重排序
        self.context_reorder = LongContextReorder()
    
    def _load_or_create_index(self):
        """加载或创建索引"""
        try:
            if self.storage_dir.exists():
                # 检查是否有必要的索引文件
                docstore_file = self.storage_dir / "docstore.json"
                if docstore_file.exists():
                    # 检查索引文件大小，估算加载时间
                    try:
                        file_size_mb = docstore_file.stat().st_size / (1024 * 1024)
                        logger.info(f"检测到索引文件大小: {file_size_mb:.2f} MB，开始加载...")
                    except Exception:
                        logger.info(f"开始加载索引...")
                    
                    storage_context = StorageContext.from_defaults(
                        persist_dir=str(self.storage_dir)
                    )
                    index = load_index_from_storage(
                        storage_context,
                        embed_model=self.embed_model
                    )
                    
                    # 统计节点数量
                    try:
                        node_count = len(index.storage_context.docstore.docs) if hasattr(index.storage_context, 'docstore') else 0
                        logger.info(f"✅ 索引加载完成: workspace={self.workspace_id}, 节点数={node_count}")
                    except Exception:
                        logger.info(f"✅ 索引加载完成: {self.workspace_id}")
                    return index
                else:
                    logger.warning(f"⚠️ 索引文件不完整，重新创建: {self.workspace_id}")
                    # 创建空索引
                    return VectorStoreIndex([], embed_model=self.embed_model)
            else:
                # wiki目录不存在，创建空索引
                self.storage_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"创建新索引: {self.workspace_id}")
                return VectorStoreIndex([], embed_model=self.embed_model)
        except Exception as e:
            logger.error(f"加载索引失败: {e}，使用后备方案")
            # 创建空索引作为后备
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"后备方案：创建空索引: {self.workspace_id}")
            return VectorStoreIndex([], embed_model=self.embed_model)
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        use_hybrid: bool = True,
        use_compression: bool = True
    ) -> List[Dict]:
        """
        高级检索 - 返回 LangGraph 可用的格式
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            use_hybrid: 是否使用混合检索
            use_compression: 是否使用压缩
        
        Returns:
            List[Dict]: 包含 content, metadata, score, node_id
        """
        try:
            # 如果索引为空，返回空结果
            if self.index is None or len(self.index.storage_context.docstore.docs) == 0:
                logger.info(f"索引为空，返回空结果: {self.workspace_id}")
                return []
            
            # 1. 检索（使用内置简化检索器，避免触发 LLM 相关模块）
            retriever = self.index.as_retriever(similarity_top_k=top_k * (4 if use_hybrid else 2))
            try:
                nodes = await retriever.aretrieve(query)
            except Exception as e:
                # 容错：若底层引用坏节点，尽量返回空而不是报错
                logger.error(f"底层检索异常（可能包含坏节点），已忽略: {e}")
                nodes = []
            
            # 4. 转换格式
            results = []
            for node in nodes[:top_k]:
                # 确保 score 是原生的 Python float，而非 numpy 类型
                score = node.score if hasattr(node, 'score') else 0.0
                if hasattr(score, 'item'):  # numpy type
                    score = float(score.item())
                else:
                    score = float(score)
                
                try:
                    results.append({
                        "content": node.get_content(),
                        "metadata": getattr(node, 'metadata', {}),
                        "score": score,
                        "node_id": getattr(node, 'node_id', '')
                    })
                except Exception as node_err:
                    # 忽略无法反序列化/缺失的节点
                    logger.warning(f"忽略坏节点: {node_err}")
            
            return results
            
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return []
    
    async def add_document(self, file_path: str, metadata: Dict = None) -> int:
        """添加文档（按文件类型解析 -> Document 列表 -> 插入与持久化）"""
        import traceback
        file_path_str = str(file_path)
        try:
            ext = Path(file_path_str).suffix.lower()
            docs: List[Any] = []

            # 基础元数据
            base_meta: Dict[str, Any] = metadata.copy() if metadata else {}
            base_meta.setdefault('original_filename', Path(file_path_str).name)
            base_meta.setdefault('file_path', file_path_str)

            if ext in {'.xlsx', '.xls'}:
                try:
                    from app.services.parsers.excel_parser import parse_excel_to_documents
                    docs = parse_excel_to_documents(file_path_str, base_meta)
                except Exception as e:
                    logger.error(f"Excel 解析失败，回退 SimpleDirectoryReader: {e}")
            elif ext in {'.pptx'}:
                try:
                    from app.services.parsers.ppt_parser import parse_ppt_to_documents
                    docs = parse_ppt_to_documents(file_path_str, base_meta)
                except Exception as e:
                    logger.error(f"PPT 解析失败，回退 SimpleDirectoryReader: {e}")
            elif ext in {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}:
                try:
                    from app.services.parsers.image_parser import parse_image_to_documents
                    docs = parse_image_to_documents(file_path_str, base_meta)
                except Exception as e:
                    logger.error(f"图片 OCR 解析失败，回退 SimpleDirectoryReader: {e}")

            if not docs:
                # 通用回退：让 SimpleDirectoryReader 尝试
                logger.info("[LlamaIndex] 使用 SimpleDirectoryReader 进行通用加载回退")
                documents = SimpleDirectoryReader(input_files=[file_path_str]).load_data()
                # 附加元数据
                if metadata:
                    for d in documents:
                        d.metadata.update(base_meta)
                docs = documents

            if not docs:
                logger.warning("未获得可插入的 Document，终止导入")
                return 0

            logger.info(f"[LlamaIndex] 开始插入文档到索引: blocks={len(docs)}, file={file_path_str}")
            logger.info(f"[LlamaIndex] base_meta keys: {list(base_meta.keys())}, document_id={base_meta.get('document_id')}")
            
            inserted = 0
            for idx, doc in enumerate(docs):
                # 兼容外部 Document 对象或纯文本
                if isinstance(doc, LI_Document):
                    # 确保 metadata 中包含 base_meta（特别是 document_id）
                    if not doc.metadata:
                        doc.metadata = {}
                    doc.metadata.update(base_meta)  # 确保 base_meta 中的字段（如 document_id）被包含
                    
                    # 验证 document_id 是否在 metadata 中
                    if base_meta.get('document_id') and base_meta.get('document_id') not in doc.metadata:
                        logger.warning(f"Document metadata 中缺少 document_id，补充中...")
                        doc.metadata['document_id'] = base_meta.get('document_id')
                    
                    if idx < 3:  # 前3个文档记录日志
                        logger.debug(f"插入 Document #{idx}: metadata keys={list(doc.metadata.keys())[:10]}, document_id={doc.metadata.get('document_id')}")
                    
                    self.index.insert(doc)
                else:
                    # 构造 LI Document 对象
                    try:
                        from llama_index.core import Document as _Doc
                    except Exception:
                        from llama_index import Document as _Doc
                    text = doc.get('text') if isinstance(doc, dict) else str(doc)
                    meta = doc.get('metadata', {}) if isinstance(doc, dict) else {}
                    # 合并 base_meta，确保 document_id 存在
                    final_meta = {**base_meta, **meta}
                    
                    if idx < 3:  # 前3个文档记录日志
                        logger.debug(f"插入 Document #{idx} (constructed): metadata keys={list(final_meta.keys())[:10]}, document_id={final_meta.get('document_id')}")
                    
                    self.index.insert(_Doc(text=text, metadata=final_meta))
                inserted += 1
                if inserted % 20 == 0:
                    logger.info(f"[LlamaIndex] 已插入 {inserted}/{len(docs)} 块…")

            # 持久化前做节点计数校验
            node_count = 0
            try:
                if hasattr(self.index, '_docstore') and self.index._docstore:
                    node_count = len(self.index._docstore.docs)
            except Exception:
                node_count = 0

            if inserted > 0 and node_count > 0:
                logger.info(f"[LlamaIndex] 开始持久化索引: inserted={inserted}, nodes={node_count}, dir={self.storage_dir}")
                self.index.storage_context.persist(persist_dir=str(self.storage_dir))
                logger.info("[LlamaIndex] 索引持久化完成")
            else:
                logger.warning(f"未检测到有效节点（inserted={inserted}, nodes={node_count}），跳过持久化")

            logger.info(f"[LlamaIndex] 文档插入完成: added_blocks={inserted}, current_nodes={node_count}")
            return max(inserted, node_count)

        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            logger.error(traceback.format_exc())
            return 0

    def _rebuild_index_from_nodes(self, kept_nodes: List[Any]) -> int:
        """使用保留的节点重建索引（用于删除后保持一致性）。"""
        try:
            # 将节点转为 Document 再构建索引，避免直接操作底层存储导致不一致
            try:
                from llama_index.core import Document as _Doc
            except Exception:
                from llama_index import Document as _Doc

            documents: List[_Doc] = []
            for node in kept_nodes:
                try:
                    text = node.get_content() if hasattr(node, 'get_content') else getattr(node, 'text', '')
                    metadata = getattr(node, 'metadata', {}) or {}
                    documents.append(_Doc(text=text or '', metadata=metadata))
                except Exception as e:
                    logger.warning(f"重建时跳过异常节点: {e}")

            # 创建新索引
            from llama_index.core.indices.vector_store import VectorStoreIndex as _VSI
            new_index = _VSI(documents, embed_model=self.embed_model)
            self.index = new_index
            self.index.storage_context.persist(persist_dir=str(self.storage_dir))
            try:
                if hasattr(self.index, '_docstore') and self.index._docstore:
                    return len(self.index._docstore.docs)
            except Exception:
                pass
            return len(documents)
        except Exception as e:
            logger.error(f"重建索引失败: {e}")
            return 0

    def delete_by_original_filename(self, original_filename: str) -> Dict[str, Any]:
        """根据 original_filename 删除对应所有节点，并持久化重建索引。"""
        try:
            ds = getattr(self.index.storage_context, 'docstore', None)
            if ds is None:
                return {"deleted": 0, "kept": 0}
            # LlamaIndex docstore 可能为 dict-like: .docs or ._dict
            nodes_map = getattr(ds, 'docs', None) or getattr(ds, '_docstore', None) or getattr(ds, '_dict', None) or {}
            if hasattr(nodes_map, 'items'):
                items = list(nodes_map.items())
            else:
                # 兼容结构
                items = []
            kept_nodes: List[Any] = []
            deleted = 0
            for _, node in items:
                meta = getattr(node, 'metadata', {}) or {}
                fname = meta.get('original_filename') or meta.get('file_name') or ''
                if fname == original_filename:
                    deleted += 1
                else:
                    kept_nodes.append(node)
            kept = len(kept_nodes)
            self._rebuild_index_from_nodes(kept_nodes)
            return {"deleted": deleted, "kept": kept}
        except Exception as e:
            logger.error(f"按文件名删除失败: {e}")
            return {"deleted": 0, "kept": 0, "error": str(e)}

    def inspect_all_nodes_metadata(self) -> List[Dict[str, Any]]:
        """调试函数：检查索引中所有节点的metadata"""
        nodes_info = []
        try:
            ds = getattr(self.index.storage_context, 'docstore', None)
            if ds is None:
                logger.warning("docstore 不存在")
                return nodes_info
            
            # 尝试多种方式访问节点映射
            nodes_map = None
            for attr_name in ['docs', '_docstore', '_dict']:
                nodes_map = getattr(ds, attr_name, None)
                if nodes_map is not None:
                    break
            
            if nodes_map is None or not hasattr(nodes_map, 'items'):
                logger.warning(f"无法访问节点映射，docstore 类型: {type(ds)}")
                return nodes_info
            
            items = list(nodes_map.items())
            logger.info(f"检查 {len(items)} 个节点的metadata")
            
            for node_id, node in items:
                # 尝试多种方式访问 metadata
                meta = {}
                node_type = type(node).__name__
                
                # 方法1: 直接访问 node.metadata
                if hasattr(node, 'metadata'):
                    meta_raw = getattr(node, 'metadata', None)
                    if isinstance(meta_raw, dict):
                        meta = meta_raw
                    elif meta_raw is not None:
                        try:
                            meta = dict(meta_raw) if hasattr(meta_raw, '__iter__') else {}
                        except:
                            meta = {}
                
                # 方法2: 通过 node.node.metadata 访问
                elif hasattr(node, 'node') and hasattr(node.node, 'metadata'):
                    meta_raw = getattr(node.node, 'metadata', None)
                    if isinstance(meta_raw, dict):
                        meta = meta_raw
                
                # 方法3: 尝试通过反射获取
                if not meta:
                    try:
                        if hasattr(node, '__dict__'):
                            node_dict = node.__dict__
                            if 'metadata' in node_dict:
                                meta = node_dict['metadata'] if isinstance(node_dict['metadata'], dict) else {}
                    except:
                        pass
                
                # 记录节点信息
                node_info = {
                    'node_id': str(node_id)[:100],
                    'node_type': node_type,
                    'has_metadata': bool(meta),
                    'metadata': dict(meta) if isinstance(meta, dict) else {},
                    'document_id': meta.get('document_id') if isinstance(meta, dict) else None,
                    'original_filename': meta.get('original_filename') if isinstance(meta, dict) else None,
                    'metadata_keys': list(meta.keys()) if isinstance(meta, dict) else []
                }
                nodes_info.append(node_info)
            
            return nodes_info
        except Exception as e:
            logger.error(f"检查节点metadata失败: {e}", exc_info=True)
            return nodes_info

    def _iter_docstore_items(self) -> List[Any]:
        """内部工具：以(items)形式返回docstore节点列表。"""
        ds = getattr(self.index.storage_context, 'docstore', None)
        if ds is None:
            return []
        nodes_map = None
        for attr_name in ['docs', '_docstore', '_dict']:
            nodes_map = getattr(ds, attr_name, None)
            if nodes_map is not None:
                break
        if nodes_map is None or not hasattr(nodes_map, 'items'):
            return []
        try:
            return list(nodes_map.items())
        except Exception:
            return []

    def resolve_document_id(self, id_or_node_id: str) -> Optional[str]:
        """
        解析传入的ID：
        - 若它本身就是某些节点metadata.document_id，直接返回该ID；
        - 若它匹配某个node_id，则从该节点metadata中取document_id并返回；
        - 否则返回None。
        """
        items = self._iter_docstore_items()
        if not items:
            return None
        candidate_doc_id: Optional[str] = None
        # 第一遍：如果传入的是document_id，看看是否存在任何节点引用它
        for _, node in items:
            meta = getattr(node, 'metadata', {}) or {}
            if isinstance(meta, dict):
                doc_id = meta.get('document_id') or meta.get('doc_id') or meta.get('docId')
                if doc_id and doc_id == id_or_node_id:
                    return id_or_node_id
        # 第二遍：如果传入的是node_id，尝试用node_id命中
        for node_id, node in items:
            if str(node_id) == id_or_node_id:
                meta = getattr(node, 'metadata', {}) or {}
                if isinstance(meta, dict):
                    doc_id = meta.get('document_id') or meta.get('doc_id') or meta.get('docId')
                    if doc_id:
                        candidate_doc_id = doc_id
                        break
        return candidate_doc_id

    def get_node_ids_by_document_id(self, document_id: str) -> List[str]:
        """返回与给定document_id关联的所有node_id列表。"""
        node_ids: List[str] = []
        for node_id, node in self._iter_docstore_items():
            meta = getattr(node, 'metadata', {}) or {}
            if isinstance(meta, dict):
                doc_id = meta.get('document_id') or meta.get('doc_id') or meta.get('docId')
                if doc_id == document_id:
                    node_ids.append(str(node_id))
        return node_ids

    def delete_by_document_id(self, document_id: str) -> Dict[str, Any]:
        """根据 metadata.document_id 删除对应所有节点，并持久化重建索引。"""
        try:
            # 先解析：允许传入的是 node_id 或 document_id
            resolved_doc_id = self.resolve_document_id(document_id)
            if not resolved_doc_id:
                logger.warning(f"无法解析为有效document_id: {document_id}")
                return {"deleted": 0, "kept": 0}

            ds = getattr(self.index.storage_context, 'docstore', None)
            if ds is None:
                logger.warning(f"docstore 不存在，无法删除 document_id={resolved_doc_id}")
                return {"deleted": 0, "kept": 0}
            
            # 尝试多种方式访问节点映射
            nodes_map = None
            for attr_name in ['docs', '_docstore', '_dict']:
                nodes_map = getattr(ds, attr_name, None)
                if nodes_map is not None:
                    break
            
            if nodes_map is None:
                logger.warning(f"无法访问节点映射，docstore 类型: {type(ds)}")
                return {"deleted": 0, "kept": 0}
            
            if not hasattr(nodes_map, 'items'):
                logger.warning(f"节点映射不支持 items()，类型: {type(nodes_map)}")
                return {"deleted": 0, "kept": 0}
            
            items = list(nodes_map.items())
            logger.info(f"开始检查 {len(items)} 个节点，查找 document_id={resolved_doc_id}")
            
            kept_nodes: List[Any] = []
            deleted = 0
            found_nodes_info = []  # 用于调试
            
            for node_id, node in items:
                # 尝试多种方式访问 metadata
                meta = {}
                node_type = type(node).__name__
                
                # 方法1: 直接访问 node.metadata
                if hasattr(node, 'metadata'):
                    meta_raw = getattr(node, 'metadata', None)
                    if isinstance(meta_raw, dict):
                        meta = meta_raw
                    elif meta_raw is not None:
                        try:
                            meta = dict(meta_raw) if hasattr(meta_raw, '__iter__') else {}
                        except:
                            meta = {}
                
                # 方法2: 通过 node.node.metadata 访问（节点可能被包装）
                if not meta and hasattr(node, 'node'):
                    if hasattr(node.node, 'metadata'):
                        meta_raw = getattr(node.node, 'metadata', None)
                        if isinstance(meta_raw, dict):
                            meta = meta_raw
                
                # 方法3: 尝试通过反射获取
                if not meta and hasattr(node, '__dict__'):
                    try:
                        node_dict = node.__dict__
                        if 'metadata' in node_dict:
                            meta_raw = node_dict['metadata']
                            if isinstance(meta_raw, dict):
                                meta = meta_raw
                    except:
                        pass
                
                # 确保 meta 是字典
                if not isinstance(meta, dict):
                    meta = {}
                
                # 获取 document_id（尝试多种字段名）
                doc_id = None
                if isinstance(meta, dict):
                    doc_id = meta.get('document_id') or meta.get('doc_id') or meta.get('docId')
                
                # 调试日志：记录前10个节点的信息
                if len(found_nodes_info) < 10:
                    found_nodes_info.append({
                        'node_id': str(node_id)[:50],
                        'node_type': node_type,
                        'doc_id': doc_id,
                        'has_meta': bool(meta),
                        'meta_keys': list(meta.keys())[:10] if isinstance(meta, dict) else [],
                        'original_filename': meta.get('original_filename') if isinstance(meta, dict) else None
                    })
                
                if doc_id == resolved_doc_id:
                    deleted += 1
                    logger.debug(f"找到匹配节点: node_id={node_id}, document_id={doc_id}, type={node_type}")
                else:
                    kept_nodes.append(node)
            
            if deleted == 0 and found_nodes_info:
                logger.warning(f"未找到 document_id={resolved_doc_id}")
                logger.info(f"索引中前10个节点的信息: {found_nodes_info}")
            
            kept = len(kept_nodes)
            logger.info(f"删除结果: deleted={deleted}, kept={kept}, 总数={len(items)}")
            
            if deleted > 0:
                self._rebuild_index_from_nodes(kept_nodes)
                logger.info(f"已重建索引，保留 {kept} 个节点")
            
            return {"deleted": deleted, "kept": kept, "all_nodes_info": found_nodes_info[:20], "resolved_document_id": resolved_doc_id}
        except Exception as e:
            logger.error(f"按 document_id 删除失败: {e}", exc_info=True)
            return {"deleted": 0, "kept": 0, "error": str(e)}

