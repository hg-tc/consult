"""
上下文管理系统
管理不同工作区的上下文信息，包括对话历史、文档关联、工作区设置等
"""

import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc
from app.models.workspace import Workspace
from app.models.conversation import Conversation, Message
from app.models.document import Document

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceContext:
    """工作区上下文"""
    workspace_id: str
    workspace_name: str
    owner_id: int
    settings: Dict[str, Any]

    # 上下文内容
    recent_conversations: List[Dict[str, Any]]
    relevant_documents: List[Dict[str, Any]]
    active_documents: List[Dict[str, Any]]

    # 统计信息
    total_documents: int
    total_conversations: int
    last_activity: datetime

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class ContextService:
    """上下文服务"""

    def __init__(self):
        self.cache = {}  # 简单的内存缓存
        self.cache_ttl = 300  # 缓存5分钟

    async def get_workspace_context(
        self,
        workspace_id: str,
        max_conversations: int = 5,
        max_documents: int = 10,
        db: AsyncSession = None
    ) -> WorkspaceContext:
        """
        获取工作区上下文

        Args:
            workspace_id: 工作区ID
            max_conversations: 最大对话数量
            max_documents: 最大文档数量
            db: 数据库会话

        Returns:
            WorkspaceContext对象
        """
        # 检查缓存
        cache_key = f"workspace_context_{workspace_id}"
        if cache_key in self.cache:
            cached_data, cache_time = self.cache[cache_key]
            if datetime.now() - cache_time < timedelta(seconds=self.cache_ttl):
                return cached_data

        # 获取工作区基本信息
        workspace_result = await db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        workspace = workspace_result.scalar_one_or_none()

        if not workspace:
            raise ValueError(f"工作区不存在: {workspace_id}")

        # 获取最近的对话
        conv_result = await db.execute(
            select(Conversation)
            .where(Conversation.workspace_id == workspace_id)
            .order_by(desc(Conversation.updated_at))
            .limit(max_conversations)
        )
        conversations = conv_result.scalars().all()

        recent_conversations = [
            {
                'id': conv.id,
                'title': conv.title,
                'message_count': conv.message_count,
                'updated_at': conv.updated_at.isoformat() if conv.updated_at else None
            }
            for conv in conversations
        ]

        # 获取相关文档（最近更新的和活跃的）
        doc_result = await db.execute(
            select(Document)
            .where(Document.workspace_id == workspace_id)
            .where(Document.status == 'completed')
            .order_by(desc(Document.updated_at))
            .limit(max_documents)
        )
        documents = doc_result.scalars().all()

        relevant_documents = [
            {
                'id': doc.id,
                'filename': doc.filename,
                'original_filename': doc.original_filename,
                'file_type': doc.file_type,
                'file_size': doc.file_size,
                'updated_at': doc.updated_at.isoformat() if doc.updated_at else None,
                'is_vectorized': doc.is_vectorized
            }
            for doc in documents
        ]

        # 获取活跃文档（最近被引用或处理的）
        active_docs_result = await db.execute(
            select(Document)
            .where(Document.workspace_id == workspace_id)
            .where(Document.status == 'completed')
            .where(Document.updated_at >= datetime.now() - timedelta(days=7))
            .order_by(desc(Document.updated_at))
            .limit(5)
        )
        active_docs = active_docs_result.scalars().all()

        active_documents = [
            {
                'id': doc.id,
                'filename': doc.filename,
                'file_type': doc.file_type,
                'updated_at': doc.updated_at.isoformat() if doc.updated_at else None
            }
            for doc in active_docs
        ]

        # 获取统计信息
        total_docs_result = await db.execute(
            select(Document).where(Document.workspace_id == workspace_id).where(Document.status == 'completed')
        )
        total_documents = len(total_docs_result.scalars().all())

        total_convs_result = await db.execute(
            select(Conversation).where(Conversation.workspace_id == workspace_id)
        )
        total_conversations = len(total_convs_result.scalars().all())

        # 构建上下文对象
        context = WorkspaceContext(
            workspace_id=str(workspace.id),
            workspace_name=workspace.name,
            owner_id=workspace.owner_id,
            settings=json.loads(workspace.settings) if workspace.settings else {},
            recent_conversations=recent_conversations,
            relevant_documents=relevant_documents,
            active_documents=active_documents,
            total_documents=total_documents,
            total_conversations=total_conversations,
            last_activity=workspace.updated_at or workspace.created_at
        )

        # 更新缓存
        self.cache[cache_key] = (context, datetime.now())

        return context

    async def update_workspace_settings(
        self,
        workspace_id: str,
        settings: Dict[str, Any],
        db: AsyncSession
    ) -> bool:
        """更新工作区设置"""
        try:
            await db.execute(
                f"UPDATE workspaces SET settings = :settings WHERE id = {workspace_id}",
                {'settings': json.dumps(settings)}
            )
            await db.commit()

            # 清除缓存
            cache_key = f"workspace_context_{workspace_id}"
            self.cache.pop(cache_key, None)

            return True
        except Exception as e:
            logger.error(f"更新工作区设置失败: {str(e)}")
            raise

    async def get_conversation_context(
        self,
        conversation_id: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """获取对话上下文"""
        # 获取对话信息
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            raise ValueError(f"对话不存在: {conversation_id}")

        # 获取最近的消息
        msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(10)
        )
        messages = msg_result.scalars().all()

        recent_messages = [
            {
                'id': msg.id,
                'role': msg.role,
                'content': msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
                'created_at': msg.created_at.isoformat() if msg.created_at else None
            }
            for msg in messages
        ]

        return {
            'conversation_id': conversation_id,
            'workspace_id': conversation.workspace_id,
            'model_name': conversation.model_name,
            'system_prompt': conversation.system_prompt,
            'recent_messages': recent_messages,
            'message_count': conversation.message_count
        }

    def build_llm_context(
        self,
        workspace_context: WorkspaceContext,
        conversation_context: Dict[str, Any] = None,
        include_documents: bool = True,
        max_context_length: int = 4000
    ) -> str:
        """
        为大模型构建上下文提示

        Args:
            workspace_context: 工作区上下文
            conversation_context: 对话上下文
            include_documents: 是否包含文档内容
            max_context_length: 最大上下文长度

        Returns:
            格式化的上下文字符串
        """
        context_parts = []

        # 添加工作区信息
        context_parts.append(f"工作区: {workspace_context.workspace_name}")
        if workspace_context.settings:
            context_parts.append(f"工作区设置: {workspace_context.settings}")

        # 添加活跃文档摘要
        if workspace_context.active_documents and include_documents:
            docs_summary = []
            for doc in workspace_context.active_documents:
                docs_summary.append(f"- {doc['filename']} ({doc['file_type']})")
            context_parts.append(f"活跃文档: {'; '.join(docs_summary)}")

        # 添加对话历史（如果有）
        if conversation_context and conversation_context.get('recent_messages'):
            messages = conversation_context['recent_messages']
            if messages:
                context_parts.append("最近对话:")
                for msg in messages[-3:]:  # 只包含最近3条消息
                    role = "用户" if msg['role'] == 'user' else "助手"
                    context_parts.append(f"{role}: {msg['content']}")

        # 合并上下文
        full_context = "\n".join(context_parts)

        # 截断到最大长度
        if len(full_context) > max_context_length:
            full_context = full_context[:max_context_length] + "..."

        return full_context

    def clear_cache(self, workspace_id: str = None):
        """清除缓存"""
        if workspace_id:
            cache_key = f"workspace_context_{workspace_id}"
            self.cache.pop(cache_key, None)
        else:
            self.cache.clear()

    async def get_workspace_activity_summary(
        self,
        workspace_id: str,
        days: int = 7,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """获取工作区活动摘要"""
        # 获取最近的文档活动
        recent_docs_result = await db.execute(
            select(Document)
            .where(Document.workspace_id == workspace_id)
            .where(Document.created_at >= datetime.now() - timedelta(days=days))
            .order_by(desc(Document.created_at))
        )
        recent_docs = recent_docs_result.scalars().all()

        # 获取最近的对话活动
        recent_convs_result = await db.execute(
            select(Conversation)
            .where(Conversation.workspace_id == workspace_id)
            .where(Conversation.created_at >= datetime.now() - timedelta(days=days))
            .order_by(desc(Conversation.created_at))
        )
        recent_convs = recent_convs_result.scalars().all()

        return {
            'workspace_id': workspace_id,
            'period_days': days,
            'new_documents': len(recent_docs),
            'new_conversations': len(recent_convs),
            'total_documents': await self._get_document_count(workspace_id, db),
            'total_conversations': await self._get_conversation_count(workspace_id, db)
        }

    async def _get_document_count(self, workspace_id: str, db: AsyncSession) -> int:
        """获取文档总数"""
        result = await db.execute(
            select(Document).where(Document.workspace_id == workspace_id)
        )
        return len(result.scalars().all())

    async def _get_conversation_count(self, workspace_id: str, db: AsyncSession) -> int:
        """获取对话总数"""
        result = await db.execute(
            select(Conversation).where(Conversation.workspace_id == workspace_id)
        )
        return len(result.scalars().all())
