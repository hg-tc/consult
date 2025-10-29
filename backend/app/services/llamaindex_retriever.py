"""
LlamaIndex 高级检索引擎
提供混合检索、重排序、语义分块、上下文压缩等功能
"""

# ============================================
# 关键：必须在所有 HuggingFace 相关导入之前设置离线模式
# HuggingFace 在 import 时就会尝试联网检查更新、下载配置等
# ============================================
import os

# 强制离线模式 - 必须在 import 之前设置
os.environ['HF_HUB_OFFLINE'] = '1'  # 禁用 HuggingFace Hub 连接
os.environ['HF_DATASETS_OFFLINE'] = '1'  # 禁用数据集下载
os.environ['TRANSFORMERS_OFFLINE'] = '1'  # 禁用 Transformers 在线功能
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'  # 禁用遥测（避免联网）
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'  # 禁用进度条（可能触发网络检查）
os.environ['HF_HUB_DISABLE_EXPERIMENTAL_WARNING'] = '1'  # 禁用实验性警告

# 禁用自动下载和更新检查
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['TRANSFORMERS_NO_ADVISORY_WARNINGS'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'  # 避免 tokenizer 初始化时的网络检查

# 更严格的离线控制（防止导入时联网）
os.environ['HF_HUB_DISABLE_VERSION_CHECK'] = '1'  # 禁用版本检查
os.environ['NO_PROXY'] = '*'  # 禁用所有代理
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

# 设置网络超时为0（立即失败，不等待）
os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '0.1'
os.environ['REQUESTS_TIMEOUT'] = '0.1'

# 禁用所有可能触发网络请求的功能
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'  # 禁用HF传输（可能触发网络检查）
os.environ['HF_HUB_DISABLE_EXPLICIT_TIMEOUT'] = '1'  # 禁用显式超时检查

# 设置本地缓存目录（避免尝试从远程下载）
# 如果已经设置了 LOCAL_BGE_MODEL_DIR，使用它作为缓存
if 'LOCAL_BGE_MODEL_DIR' in os.environ:
    local_model_dir = os.environ['LOCAL_BGE_MODEL_DIR']
    os.environ['HF_HOME'] = local_model_dir
    os.environ['HUGGINGFACE_HUB_CACHE'] = local_model_dir
    os.environ['TRANSFORMERS_CACHE'] = local_model_dir

from typing import List, Dict, Optional
from pathlib import Path
import logging
import threading
import time

logger = logging.getLogger(__name__)

# 全局实例缓存（线程安全）
_retriever_cache: Dict[str, 'LlamaIndexRetriever'] = {}
_embed_model_cache: Optional[object] = None
# 使用两把独立的锁，避免实例化期间发生自锁
_retriever_lock = threading.Lock()
_embed_lock = threading.Lock()

# 模块导入时间统计（用于诊断导入性能问题）
_import_start_time = time.time()
logger.info(f"🔄 开始加载 LlamaIndex 模块（离线模式已启用）")

try:
    # 使用最小依赖集合，避免触发 LLM 模块
    _module_times = {}
    
    # VectorStoreIndex
    _t0 = time.time()
    from llama_index.core.indices.vector_store import VectorStoreIndex
    _module_times['VectorStoreIndex'] = time.time() - _t0
    logger.info(f"✅ VectorStoreIndex 加载成功 ({_module_times['VectorStoreIndex']:.3f}s)")
    
    # StorageContext
    _t0 = time.time()
    from llama_index.core.storage.storage_context import StorageContext
    _module_times['StorageContext'] = time.time() - _t0
    logger.info(f"✅ StorageContext 加载成功 ({_module_times['StorageContext']:.3f}s)")
    
    # load_index_from_storage
    _t0 = time.time()
    from llama_index.core.indices.loading import load_index_from_storage
    _module_times['load_index_from_storage'] = time.time() - _t0
    logger.info(f"✅ load_index_from_storage 加载成功 ({_module_times['load_index_from_storage']:.3f}s)")
    
    # SemanticSplitterNodeParser
    _t0 = time.time()
    from llama_index.core.node_parser import SemanticSplitterNodeParser
    _module_times['SemanticSplitterNodeParser'] = time.time() - _t0
    logger.info(f"✅ SemanticSplitterNodeParser 加载成功 ({_module_times['SemanticSplitterNodeParser']:.3f}s)")
    
    # HuggingFaceEmbedding（可能最耗时，因为它会触发 transformers 导入）
    _t0 = time.time()
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    _module_times['HuggingFaceEmbedding'] = time.time() - _t0
    logger.info(f"✅ HuggingFaceEmbedding 加载成功 ({_module_times['HuggingFaceEmbedding']:.3f}s)")
    
    # SimpleDirectoryReader
    _t0 = time.time()
    from llama_index.core import SimpleDirectoryReader
    _module_times['SimpleDirectoryReader'] = time.time() - _t0
    logger.info(f"✅ SimpleDirectoryReader 加载成功 ({_module_times['SimpleDirectoryReader']:.3f}s)")
    
    _total_import_time = time.time() - _import_start_time
    logger.info(f"✅ 所有 LlamaIndex 模块加载完成，总耗时: {_total_import_time:.3f}s")
    logger.debug(f"模块加载时间明细: {_module_times}")
    
    # 如果总耗时超过5秒，发出警告
    if _total_import_time > 5.0:
        logger.warning(f"⚠️ 模块加载耗时较长 ({_total_import_time:.3f}s)，可能触发了网络请求或慢速检查")
        if _module_times.get('HuggingFaceEmbedding', 0) > 3.0:
            logger.warning(f"⚠️ HuggingFaceEmbedding 导入耗时 {_module_times['HuggingFaceEmbedding']:.3f}s，可能是 transformers 库触发了网络检查")
            
except ImportError as e:
    # 0.10.x 备用导入路径（进一步最小化）
    logger.error(f"❌ LlamaIndex 导入失败: {e}，尝试备用路径")
    try:
        from llama_index import VectorStoreIndex, StorageContext, load_index_from_storage, SimpleDirectoryReader
        from llama_index.node_parser import SemanticSplitterNodeParser
        from llama_index.embeddings import HuggingFaceEmbedding
        logger.info(f"✅ 使用备用导入路径加载成功")
    except ImportError:
        raise ImportError("无法导入 LlamaIndex 模块，请检查安装")

def _get_shared_embed_model():
    """获取共享的嵌入模型（单例，避免重复加载）"""
    global _embed_model_cache
    
    if _embed_model_cache is None:
        with _embed_lock:
            # 双重检查
            if _embed_model_cache is None:
                local_model_dir = os.getenv("LOCAL_BGE_MODEL_DIR", "")
                if not local_model_dir or not Path(local_model_dir).exists():
                    raise RuntimeError(
                        f"LOCAL_BGE_MODEL_DIR 未设置或目录不存在: {local_model_dir}\n"
                        f"请设置环境变量 LOCAL_BGE_MODEL_DIR 指向本地BGE模型目录。"
                    )
                
                # 再次确保离线模式（虽然已在顶部设置，但再次确认）
                # 注意：此时环境变量已经在模块导入前设置，这里只是双重保险
                os.environ['HF_HUB_OFFLINE'] = '1'
                os.environ['HF_DATASETS_OFFLINE'] = '1'
                os.environ['TRANSFORMERS_OFFLINE'] = '1'
                
                logger.info(f"🔄 初始化共享嵌入模型（离线模式）: {local_model_dir}")
                
                try:
                    _embed_model_cache = HuggingFaceEmbedding(
                        model_name=local_model_dir,
                        cache_folder=local_model_dir,
                        trust_remote_code=True,  # 信任本地模型
                    )
                    logger.info(f"✅ 共享嵌入模型已缓存")
                except Exception as e:
                    logger.error(f"加载嵌入模型失败: {e}")
                    raise RuntimeError(
                        f"无法从本地目录加载模型: {local_model_dir}\n"
                        f"请确保该目录包含完整的 BGE 模型文件。\n"
                        f"错误详情: {str(e)}"
                    )
    
    return _embed_model_cache


class LlamaIndexRetriever:
    """LlamaIndex 高级检索引擎 - 为 LangGraph 提供检索服务"""
    
    @classmethod
    def get_instance(cls, workspace_id: str = "global") -> 'LlamaIndexRetriever':
        """获取实例（单例模式，按 workspace_id 缓存）"""
        cache_key = workspace_id

        # 快路径：无锁读取
        instance = _retriever_cache.get(cache_key)
        if instance is not None:
            return instance

        # 构造实例放到锁外，避免持锁期间执行耗时初始化
        new_instance = cls(workspace_id, use_cache=True)
        
        # 放入缓存（双检）
        with _retriever_lock:
            instance = _retriever_cache.get(cache_key)
            if instance is None:
                logger.info(f"🔄 创建新 LlamaIndexRetriever 实例: {workspace_id}")
                _retriever_cache[cache_key] = new_instance
                logger.info(f"✅ LlamaIndexRetriever 实例已缓存: {workspace_id}")
                return new_instance
            else:
                return instance
    
    def __init__(self, workspace_id: str = "global", use_cache: bool = False):
        """
        初始化检索器
        
        Args:
            workspace_id: 工作区ID
            use_cache: 是否使用缓存的嵌入模型（内部使用）
        """
        self.workspace_id = workspace_id
        
        # 从配置中获取存储路径
        from app.core.config import settings
        storage_base = Path(settings.LLAMAINDEX_STORAGE_PATH)
        self.storage_dir = storage_base / workspace_id
        
        # 使用共享的嵌入模型（避免重复加载）
        if use_cache:
            self.embed_model = _get_shared_embed_model()
        else:
            # 兼容旧代码：直接创建
            self.embed_model = _get_shared_embed_model()
            logger.warning(f"⚠️ 直接创建 LlamaIndexRetriever 实例，建议使用 get_instance() 方法")
        
        # 语义分块器（轻量，不需要缓存）
        self.node_parser = SemanticSplitterNodeParser(
            buffer_size=1,
            breakpoint_percentile_threshold=95,
            embed_model=self.embed_model
        )
        
        # 索引（延迟加载，在第一次使用时加载）
        self._index = None
        self._index_loaded = False
    
    @property
    def index(self):
        """延迟加载索引"""
        if not self._index_loaded:
            self._index = self._load_or_create_index()
            self._index_loaded = True
        return self._index
    
    def _load_or_create_index(self):
        """加载或创建索引"""
        try:
            if self.storage_dir.exists():
                # 检查是否有必要的索引文件
                docstore_file = self.storage_dir / "docstore.json"
                if docstore_file.exists():
                    storage_context = StorageContext.from_defaults(
                        persist_dir=str(self.storage_dir)
                    )
                    index = load_index_from_storage(
                        storage_context,
                        embed_model=self.embed_model
                    )
                    logger.info(f"✅ 加载索引: {self.workspace_id}")
                    return index
                else:
                    logger.warning(f"⚠️ 索引文件不完整，重新创建: {self.workspace_id}")
                    # 创建空索引
                    return VectorStoreIndex([], embed_model=self.embed_model)
            else:
                # wiki目录不存在，创建空索引
                self.storage_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"创建索引: {self.workspace_id}")
                return VectorStoreIndex([], embed_model=self.embed_model)
        except Exception as e:
            logger.error(f"加载索引失败: {e}")
            # 创建空索引作为后备
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"后备方案：创建空索引: {self.workspace_id}")
            return VectorStoreIndex([], embed_model=self.embed_model)
    
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
                    storage_context = StorageContext.from_defaults(
                        persist_dir=str(self.storage_dir)
                    )
                    index = load_index_from_storage(
                        storage_context,
                        embed_model=self.embed_model
                    )
                    logger.info(f"✅ 加载索引: {self.workspace_id}")
                    return index
                else:
                    logger.warning(f"⚠️ 索引文件不完整，重新创建: {self.workspace_id}")
                    # 创建空索引
                    return VectorStoreIndex([], embed_model=self.embed_model)
            else:
                # wiki目录不存在，创建空索引
                self.storage_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"创建索引: {self.workspace_id}")
                return VectorStoreIndex([], embed_model=self.embed_model)
        except Exception as e:
            logger.error(f"加载索引失败: {e}")
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
            nodes = await retriever.aretrieve(query)
            
            # 4. 转换格式（确保所有数据类型都是 Python 原生类型，避免 msgpack 序列化错误）
            results = []
            for node in nodes[:top_k]:
                # 确保 score 是 Python float，不是 numpy.float64
                score = node.score if hasattr(node, 'score') else 0.0
                if hasattr(score, 'item'):  # numpy 类型有 item() 方法
                    score = float(score.item())
                else:
                    score = float(score)
                
                # 确保 metadata 中的值也都是 Python 原生类型
                metadata = {}
                if hasattr(node, 'metadata') and node.metadata:
                    for key, value in node.metadata.items():
                        # 转换 numpy 类型为 Python 原生类型
                        if hasattr(value, 'item'):  # numpy 类型
                            metadata[key] = value.item()
                        elif hasattr(value, 'tolist'):  # numpy array
                            metadata[key] = value.tolist()
                        else:
                            metadata[key] = value
                
                results.append({
                    "content": node.get_content(),
                    "metadata": metadata,
                    "score": score,
                    "node_id": node.node_id
                })
            
            return results
            
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return []
    
    async def add_document(self, file_path: str, metadata: Dict = None):
        """添加文档：对常见格式先转换为 Markdown，再写入索引；其他格式回退 SimpleDirectoryReader。"""
        try:
            import traceback
            from pathlib import Path as _Path
            from llama_index.core.schema import Document as LIDocument

            suffix = _Path(file_path).suffix.lower()
            text: Optional[str] = None
            md_meta: Dict = {}

            try:
                if suffix in [".xlsx", ".xls"]:
                    from app.services.excel_parser import parse_excel_to_markdown
                    res = parse_excel_to_markdown(file_path)
                    text = res.get("content", "")
                    md_meta.update(res.get("metadata", {}))
                    md_meta["file_type"] = "excel"
                elif suffix in [".pptx", ".ppt"]:
                    from app.services.ppt_processor import process_ppt_to_markdown
                    res = process_ppt_to_markdown(file_path)
                    text = res.get("content", "")
                    md_meta.update(res.get("metadata", {}))
                    md_meta["file_type"] = "powerpoint"
                elif suffix in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"]:
                    from app.services.file_processor import FileProcessor
                    fp = FileProcessor()
                    res = fp._process_image(file_path)
                    text = res.get("content", "")
                    md_meta.update(res.get("metadata", {}))
                    md_meta["file_type"] = "image"
                else:
                    # PDF/WORD 等优先尝试现有处理器（若已增强则输出 Markdown）
                    from app.services.file_processor import FileProcessor
                    fp = FileProcessor()
                    try:
                        res = fp.process_file(file_path)
                        text = res.get("content", "")
                        md_meta.update(res.get("metadata", {}))
                        md_meta["file_type"] = res.get("file_type", suffix.lstrip('.'))
                    except Exception:
                        text = None
            except Exception as proc_err:
                logger.warning(f"自定义处理器失败，回退默认读取: {proc_err}")
                text = None

            documents = []
            if text and text.strip():
                # 构建层级信息前缀（如果有层级信息，添加到文档内容前端以确保向量化）
                hierarchy_prefix = ""
                if metadata and metadata.get('hierarchy_path'):
                    hierarchy_info = []
                    archive_name = metadata.get('archive_name')
                    archive_hierarchy = metadata.get('archive_hierarchy')
                    folder_path = metadata.get('folder_path')
                    
                    if archive_name:
                        hierarchy_info.append(f"压缩包: {archive_name}")
                    if archive_hierarchy:
                        hierarchy_info.append(f"嵌套路径: {archive_hierarchy}")
                    if folder_path:
                        hierarchy_info.append(f"文件夹: {folder_path}")
                    
                    if hierarchy_info:
                        hierarchy_prefix = f"## 文件层级信息\n\n" + "\n".join(hierarchy_info) + "\n\n---\n\n"
                    
                    # 完整层级路径也添加到元数据
                    doc_meta = metadata.copy() if metadata else {}
                    doc_meta.update(md_meta)
                    doc_meta.setdefault("original_path", str(file_path))
                    doc_meta.setdefault("hierarchy_path", metadata.get('hierarchy_path'))
                else:
                    doc_meta = metadata.copy() if metadata else {}
                    doc_meta.update(md_meta)
                    doc_meta.setdefault("original_path", str(file_path))
                
                # 将层级信息添加到文档内容前端
                enhanced_text = hierarchy_prefix + text if hierarchy_prefix else text
                documents = [LIDocument(text=enhanced_text, metadata=doc_meta)]
            else:
                # 回退 SimpleDirectoryReader
                from llama_index.core import SimpleDirectoryReader
                documents = SimpleDirectoryReader(input_files=[file_path]).load_data()
                if metadata:
                    # 如果有层级信息，也添加到回退方案的文档中
                    if metadata.get('hierarchy_path'):
                        hierarchy_info = []
                        archive_name = metadata.get('archive_name')
                        archive_hierarchy = metadata.get('archive_hierarchy')
                        folder_path = metadata.get('folder_path')
                        
                        if archive_name:
                            hierarchy_info.append(f"压缩包: {archive_name}")
                        if archive_hierarchy:
                            hierarchy_info.append(f"嵌套路径: {archive_hierarchy}")
                        if folder_path:
                            hierarchy_info.append(f"文件夹: {folder_path}")
                        
                        hierarchy_prefix = ""
                        if hierarchy_info:
                            hierarchy_prefix = f"## 文件层级信息\n\n" + "\n".join(hierarchy_info) + "\n\n---\n\n"
                    
                    for d in documents:
                        d.metadata.update(metadata)
                        if metadata.get('hierarchy_path'):
                            d.metadata['hierarchy_path'] = metadata.get('hierarchy_path')
                        # 如果有层级前缀，添加到文档内容
                        if hierarchy_prefix:
                            d.text = hierarchy_prefix + d.text

            # 插入与持久化
            for doc in documents:
                self.index.insert(doc)
            self.index.storage_context.persist(persist_dir=str(self.storage_dir))

            if hasattr(self.index, '_docstore') and self.index._docstore:
                return len(self.index._docstore.docs)
            return len(documents)

        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            logger.error(traceback.format_exc())
            return 0

