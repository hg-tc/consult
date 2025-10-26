"""
对话管理端点
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.conversation import Conversation, Message

router = APIRouter()


@router.get("/")
async def get_conversations(
    workspace_id: int = None,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """获取对话列表"""
    query = select(Conversation).offset(skip).limit(limit)

    if workspace_id:
        query = query.where(Conversation.workspace_id == workspace_id)

    result = await db.execute(query)
    conversations = result.scalars().all()

    return [
        {
            "id": conv.id,
            "title": conv.title,
            "workspace_id": conv.workspace_id,
            "message_count": conv.message_count,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
        }
        for conv in conversations
    ]


@router.post("/")
async def create_conversation(
    workspace_id: int = 1,  # 暂时固定工作区ID
    title: str = "新对话",
    db: AsyncSession = Depends(get_db)
):
    """创建新对话"""
    conversation = Conversation(
        title=title,
        workspace_id=workspace_id,
        model_name="gpt-3.5-turbo"
    )

    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    return {
        "id": conversation.id,
        "title": conversation.title,
        "workspace_id": conversation.workspace_id,
        "message": "对话创建成功"
    }


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取对话消息"""
    # 获取对话
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在"
        )

    # 获取消息
    msg_result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
    )
    messages = msg_result.scalars().all()

    return [
        {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }
        for msg in messages
    ]


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    content: str,
    role: str = "user",
    db: AsyncSession = Depends(get_db)
):
    """发送消息"""
    # 获取对话
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在"
        )

    # 创建用户消息
    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=content
    )

    db.add(user_message)

    # 更新对话消息计数
    conversation.message_count += 1

    await db.commit()
    await db.refresh(user_message)

    # 模拟AI回复（暂时返回固定回复）
    ai_response = "我已收到您的消息，正在思考如何回复您..."

    ai_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=ai_response
    )

    db.add(ai_message)
    conversation.message_count += 1

    await db.commit()

    return {
        "user_message": {
            "id": user_message.id,
            "content": user_message.content,
            "role": user_message.role,
        },
        "ai_message": {
            "id": ai_message.id,
            "content": ai_message.content,
            "role": ai_message.role,
        },
        "message": "消息发送成功"
    }
