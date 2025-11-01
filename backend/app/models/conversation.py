"""
对话模型
"""

from sqlalchemy import Column, String, Text, Integer, ForeignKey, DateTime, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base, BaseModel


class Conversation(BaseModel):
    """对话表"""
    __tablename__ = "conversations"

    title = Column(String)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)

    # 对话设置
    model_name = Column(String)  # 默认值在创建时从settings读取
    system_prompt = Column(Text)
    settings = Column(JSON)  # 对话参数设置

    # 统计信息
    message_count = Column(Integer, default=0)
    token_count = Column(Integer, default=0)

    # 关系
    workspace = relationship("Workspace", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Conversation(id={self.id}, title={self.title}, workspace_id={self.workspace_id})>"


class Message(BaseModel):
    """消息表"""
    __tablename__ = "messages"

    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)

    # 消息元数据
    model_name = Column(String)
    token_count = Column(Integer)
    msg_metadata = Column(JSON)  # 额外的消息数据

    # 引用信息（如果适用）
    references = Column(JSON)  # 引用来源信息

    # 关系
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, role={self.role}, conversation_id={self.conversation_id})>"
