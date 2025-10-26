"""
工作区管理端点
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.workspace import Workspace
from app.models.user import User

router = APIRouter()


@router.get("/", response_model=List[dict])
async def get_workspaces(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """获取工作区列表"""
    result = await db.execute(
        select(Workspace).offset(skip).limit(limit)
    )
    workspaces = result.scalars().all()

    return [
        {
            "id": ws.id,
            "name": ws.name,
            "description": ws.description,
            "owner_id": ws.owner_id,
            "created_at": ws.created_at.isoformat() if ws.created_at else None,
        }
        for ws in workspaces
    ]


@router.post("/")
async def create_workspace(
    name: str,
    description: str = None,
    owner_id: int = 1,  # 暂时固定用户ID
    db: AsyncSession = Depends(get_db)
):
    """创建工作区"""
    workspace = Workspace(
        name=name,
        description=description,
        owner_id=owner_id
    )

    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)

    return {
        "id": workspace.id,
        "name": workspace.name,
        "description": workspace.description,
        "message": "工作区创建成功"
    }


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取工作区详情"""
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="工作区不存在"
        )

    return {
        "id": workspace.id,
        "name": workspace.name,
        "description": workspace.description,
        "owner_id": workspace.owner_id,
        "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
    }
