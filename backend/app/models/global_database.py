"""
全局数据库模型
实现公共文档库和工作区分离的架构
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Dict, List, Any, Optional

Base = declarative_base()


class GlobalDocument(Base):
    """全局文档表 - 所有工作区共享"""
    __tablename__ = "global_documents"
    
    id = Column(String, primary_key=True)  # UUID
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String, nullable=False)  # pdf, docx, etc.
    mime_type = Column(String, nullable=False)
    
    # 文档内容
    content = Column(Text)
    doc_metadata = Column(JSON)  # 文档元数据
    
    # 处理状态
    status = Column(String, default="processing")  # processing, completed, failed
    vectorized = Column(Boolean, default=False)
    chunk_count = Column(Integer, default=0)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    workspace_access = relationship("WorkspaceDocumentAccess", back_populates="document")
    chunks = relationship("GlobalDocumentChunk", back_populates="document")


class GlobalDocumentChunk(Base):
    """全局文档分块表 - 所有工作区共享"""
    __tablename__ = "global_document_chunks"
    
    id = Column(String, primary_key=True)  # UUID
    document_id = Column(String, ForeignKey("global_documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    chunk_metadata = Column(JSON)
    
    # 向量信息
    vector_id = Column(String)  # FAISS中的向量ID
    embedding_model = Column(String)  # 使用的嵌入模型
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联关系
    document = relationship("GlobalDocument", back_populates="chunks")


class Workspace(Base):
    """工作区表 - 独立的工作区配置"""
    __tablename__ = "workspaces"
    
    id = Column(String, primary_key=True)  # UUID
    name = Column(String, nullable=False)
    description = Column(Text)
    
    # 工作区配置
    settings = Column(JSON)  # 工作区特定设置
    llm_config = Column(JSON)  # LLM配置
    retrieval_config = Column(JSON)  # 检索配置
    
    # 状态
    status = Column(String, default="active")  # active, inactive, archived
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    document_access = relationship("WorkspaceDocumentAccess", back_populates="workspace")
    conversations = relationship("Conversation", back_populates="workspace")


class WorkspaceDocumentAccess(Base):
    """工作区文档访问权限表 - 控制哪些文档对哪些工作区可见"""
    __tablename__ = "workspace_document_access"
    
    id = Column(String, primary_key=True)  # UUID
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    document_id = Column(String, ForeignKey("global_documents.id"), nullable=False)
    
    # 访问权限
    access_level = Column(String, default="read")  # read, write, admin
    is_active = Column(Boolean, default=True)
    
    # 工作区特定设置
    workspace_settings = Column(JSON)  # 该文档在工作区中的特定设置
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联关系
    workspace = relationship("Workspace", back_populates="document_access")
    document = relationship("GlobalDocument", back_populates="workspace_access")


class Conversation(Base):
    """对话历史表 - 按工作区存储"""
    __tablename__ = "conversations"
    
    id = Column(String, primary_key=True)  # UUID
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    
    # 对话内容
    user_message = Column(Text, nullable=False)
    agent_response = Column(Text, nullable=False)
    
    # 检索信息
    retrieved_documents = Column(JSON)  # 检索到的文档信息
    references = Column(JSON)  # 引用信息
    
    # 元数据
    conv_metadata = Column(JSON)
    confidence_score = Column(Integer)  # 置信度分数
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联关系
    workspace = relationship("Workspace", back_populates="conversations")


class GlobalVectorIndex(Base):
    """全局向量索引表 - 管理所有文档的向量索引"""
    __tablename__ = "global_vector_index"
    
    id = Column(String, primary_key=True)  # UUID
    index_name = Column(String, nullable=False, unique=True)  # 索引名称
    embedding_model = Column(String, nullable=False)  # 使用的嵌入模型
    
    # 索引信息
    index_path = Column(String, nullable=False)  # FAISS索引文件路径
    document_count = Column(Integer, default=0)  # 索引中的文档数量
    chunk_count = Column(Integer, default=0)  # 索引中的分块数量
    
    # 状态
    status = Column(String, default="active")  # active, rebuilding, error
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    # 配置
    config = Column(JSON)  # 索引配置信息


# 数据访问层接口
class GlobalDatabaseService:
    """全局数据库服务"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    # 文档管理
    def add_global_document(self, document_data: Dict[str, Any]) -> str:
        """添加全局文档"""
        pass
    
    def get_global_document(self, document_id: str) -> Optional[GlobalDocument]:
        """获取全局文档"""
        pass
    
    def list_global_documents(self) -> List[GlobalDocument]:
        """列出所有全局文档"""
        pass
    
    # 工作区管理
    def create_workspace(self, workspace_data: Dict[str, Any]) -> str:
        """创建工作区"""
        pass
    
    def get_workspace_documents(self, workspace_id: str) -> List[GlobalDocument]:
        """获取工作区可访问的文档"""
        pass
    
    def grant_document_access(self, workspace_id: str, document_id: str, access_level: str = "read"):
        """授予工作区文档访问权限"""
        pass
    
    def revoke_document_access(self, workspace_id: str, document_id: str):
        """撤销工作区文档访问权限"""
        pass
    
    # 检索服务
    def search_documents(self, query: str, workspace_id: str = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索文档 - 支持工作区过滤"""
        pass
    
    # 对话管理
    def save_conversation(self, workspace_id: str, user_message: str, agent_response: str, 
                         retrieved_docs: List[Dict], references: List[Dict]) -> str:
        """保存对话历史"""
        pass
    
    def get_conversation_history(self, workspace_id: str, limit: int = 50) -> List[Conversation]:
        """获取工作区对话历史"""
        pass
