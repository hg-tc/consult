"""
LlamaIndex 高级检索引擎
提供混合检索、重排序、语义分块、上下文压缩等功能
"""

from typing import List, Dict, Optional
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

try:
    # 使用最小依赖集合，避免触发 LLM 模块
    from llama_index.core.indices.vector_store import VectorStoreIndex
    from llama_index.core.storage.storage_context import StorageContext
    from llama_index.core.indices.loading import load_index_from_storage
    from llama_index.core.node_parser import SemanticSplitterNodeParser
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.core import SimpleDirectoryReader
except ImportError as e:
    # 0.10.x 备用导入路径（进一步最小化）
    logger.error(f"LlamaIndex 导入失败: {e}，尝试备用路径")
    try:
        from llama_index import VectorStoreIndex, StorageContext, load_index_from_storage, SimpleDirectoryReader
        from llama_index.node_parser import SemanticSplitterNodeParser
        from llama_index.embeddings import HuggingFaceEmbedding
    except ImportError:
        raise ImportError("无法导入 LlamaIndex 模块，请检查安装")

class LlamaIndexRetriever:
    """LlamaIndex 高级检索引擎 - 为 LangGraph 提供检索服务"""
    
    def __init__(self, workspace_id: str = "global"):
        self.workspace_id = workspace_id
        self.storage_dir = Path(f"llamaindex_storage/{workspace_id}")
        
        # 嵌入模型（强制本地加载，避免连接HuggingFace）
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
        self.embed_model = HuggingFaceEmbedding(
            model_name=local_model_dir,
            cache_folder=local_model_dir  # 使用模型目录作为缓存
        )
        logger.info(f"✅ 使用本地BGE模型（离线模式）: {local_model_dir}")
        
        # 语义分块器
        self.node_parser = SemanticSplitterNodeParser(
            buffer_size=1,
            breakpoint_percentile_threshold=95,
            embed_model=self.embed_model
        )
        
        # # 后处理器栈
        # self._init_postprocessors()
        
        # 索引
        self.index = self._load_or_create_index()
        logger.info(f"✅ init完成")
    
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
            
            # 4. 转换格式
            results = []
            for node in nodes[:top_k]:
                results.append({
                    "content": node.get_content(),
                    "metadata": node.metadata,
                    "score": node.score if hasattr(node, 'score') else 0.0,
                    "node_id": node.node_id
                })
            
            return results
            
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return []
    
    async def add_document(self, file_path: str, metadata: Dict = None):
        """添加文档（使用语义分块并生成向量）"""
        try:
            from llama_index.core import SimpleDirectoryReader
            import traceback
            
            logger.info(f"📄 开始加载文档: {file_path}")
            documents = SimpleDirectoryReader(input_files=[file_path]).load_data()
            logger.info(f"✅ 文档加载完成，页数: {len(documents)}")
            
            if metadata:
                for doc in documents:
                    doc.metadata.update(metadata)
            
            logger.info(f"📝 开始插入文档到索引...")
            # 使用 insert 逐个插入文档，索引会自动处理分块和向量化
            for doc in documents:
                self.index.insert(doc)
            
            logger.info(f"💾 开始持久化索引...")
            self.index.storage_context.persist(persist_dir=str(self.storage_dir))
            logger.info(f"✅ 索引持久化完成")
            
            # 从索引中获取节点数量
            if hasattr(self.index, '_docstore') and self.index._docstore:
                node_count = len(self.index._docstore.docs)
                logger.info(f"✅ 文档插入完成，总节点数: {node_count}")
                return node_count
            else:
                logger.warning("⚠️ 无法获取节点数量")
                return len(documents)  # 回退到文档数量
            
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            logger.error(traceback.format_exc())
            return 0

