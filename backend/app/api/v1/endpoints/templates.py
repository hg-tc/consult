"""
模板管理端点
"""

from typing import List
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.template import Template

router = APIRouter()


@router.post("/upload")
async def upload_template(
    file: UploadFile = File(...),
    name: str = None,
    description: str = None,
    category: str = "general",
    owner_id: int = 1,  # 暂时固定用户ID
    db: AsyncSession = Depends(get_db)
):
    """上传模板文件"""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件名不能为空"
        )

    # 检查文件扩展名
    file_ext = os.path.splitext(file.filename)[1].lower()
    allowed_types = [".docx", ".doc", ".pdf", ".pptx", ".ppt"]

    if file_ext not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的模板文件类型: {file_ext}"
        )

    # 保存文件
    file_id = str(uuid.uuid4())
    filename = f"{file_id}{file_ext}"
    file_path = os.path.join("templates", filename)

    # 确保模板目录存在
    os.makedirs("templates", exist_ok=True)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # 保存到数据库
    template = Template(
        name=name or file.filename,
        description=description,
        filename=filename,
        file_path=file_path,
        file_size=len(content),
        template_type=file_ext[1:],  # 去掉点
        category=category,
        owner_id=owner_id
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return {
        "id": template.id,
        "name": template.name,
        "filename": template.filename,
        "template_type": template.template_type,
        "message": "模板上传成功"
    }


@router.get("/")
async def get_templates(
    category: str = None,
    owner_id: int = None,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """获取模板列表"""
    query = select(Template).offset(skip).limit(limit)

    if category:
        query = query.where(Template.category == category)

    if owner_id:
        query = query.where(Template.owner_id == owner_id)

    result = await db.execute(query)
    templates = result.scalars().all()

    return [
        {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "template_type": template.template_type,
            "category": template.category,
            "usage_count": template.usage_count,
            "created_at": template.created_at.isoformat() if template.created_at else None,
        }
        for template in templates
    ]


@router.get("/{template_id}/download")
async def download_template(
    template_id: int,
    db: AsyncSession = Depends(get_db)
):
    """下载模板"""
    result = await db.execute(
        select(Template).where(Template.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模板不存在"
        )

    if not os.path.exists(template.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模板文件不存在"
        )

    return FileResponse(
        path=template.file_path,
        filename=template.name,
        media_type="application/octet-stream"
    )
