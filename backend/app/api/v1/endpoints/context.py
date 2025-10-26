"""
上下文管理端点
"""

import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.context_service import ContextService

router = APIRouter()
context_service = ContextService()


@router.get("/workspace/{workspace_id}")
async def get_workspace_context(
    workspace_id: int,
    max_conversations: int = 5,
    max_documents: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """获取工作区上下文"""
    try:
        context = await context_service.get_workspace_context(
            workspace_id=str(workspace_id),
            max_conversations=max_conversations,
            max_documents=max_documents,
            db=db
        )

        return {
            "workspace_id": context.workspace_id,
            "workspace_name": context.workspace_name,
            "owner_id": context.owner_id,
            "settings": context.settings,
            "recent_conversations": context.recent_conversations,
            "relevant_documents": context.relevant_documents,
            "active_documents": context.active_documents,
            "total_documents": context.total_documents,
            "total_conversations": context.total_conversations,
            "last_activity": context.last_activity.isoformat() if context.last_activity else None
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取工作区上下文失败: {str(e)}"
        )


@router.get("/conversation/{conversation_id}")
async def get_conversation_context(
    conversation_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取对话上下文"""
    try:
        context = await context_service.get_conversation_context(
            conversation_id=conversation_id,
            db=db
        )

        return context

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取对话上下文失败: {str(e)}"
        )


@router.put("/workspace/{workspace_id}/settings")
async def update_workspace_settings(
    workspace_id: int,
    settings: dict,
    db: AsyncSession = Depends(get_db)
):
    """更新工作区设置"""
    try:
        success = await context_service.update_workspace_settings(
            workspace_id=str(workspace_id),
            settings=settings,
            db=db
        )

        if success:
            return {"message": "工作区设置更新成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="工作区设置更新失败"
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新工作区设置失败: {str(e)}"
        )


@router.get("/workspace/{workspace_id}/activity")
async def get_workspace_activity(
    workspace_id: int,
    days: int = 7,
    db: AsyncSession = Depends(get_db)
):
    """获取工作区活动摘要"""
    try:
        activity = await context_service.get_workspace_activity_summary(
            workspace_id=str(workspace_id),
            days=days,
            db=db
        )

        return activity

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取工作区活动失败: {str(e)}"
        )


@router.post("/cache/clear")
async def clear_context_cache(
    workspace_id: str = None
):
    """清除上下文缓存"""
    try:
        context_service.clear_cache(workspace_id)
        return {"message": "缓存清除成功"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清除缓存失败: {str(e)}"
        )
