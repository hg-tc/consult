"""
文档管理端点
"""

from typing import List
import os
import uuid
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.document import Document, DocumentChunk
from app.services.file_processor import FileProcessor
from app.services.vector_service import VectorService
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()
file_processor = FileProcessor()
vector_service = VectorService()


async def process_document_content(document_id: int, file_path: str, db: AsyncSession):
    """后台处理文档内容"""
    try:
        # 更新状态为处理中
        await db.execute(
            f"UPDATE documents SET status = 'processing' WHERE id = {document_id}"
        )
        await db.commit()

        # 解析文档内容
        result = file_processor.process_file(file_path)

        # 更新文档信息
        await db.execute(f"""
            UPDATE documents SET
                status = 'completed',
                title = :title,
                content = :content,
                metadata = :metadata,
                is_vectorized = false,
                vector_count = 0
            WHERE id = {document_id}
        """, {
            'title': result.get('metadata', {}).get('title', ''),
            'content': result['content'][:50000],  # 限制内容长度
            'metadata': str(result.get('metadata', {}))
        })

        # 创建文档分块
        chunks_data = result.get('chunks', [])
        for i, chunk in enumerate(chunks_data[:100]):  # 限制分块数量
            db.add(DocumentChunk(
                document_id=document_id,
                chunk_index=i,
                content=chunk.get('content', '')[:2000],
                metadata=str(chunk.get('metadata', {}))
            ))

        await db.commit()

        # 获取工作区ID
        doc_result = await db.execute(
            select(Document.workspace_id).where(Document.id == document_id)
        )
        workspace_id = doc_result.scalar_one()

        # 自动向量化文档分块
        if chunks_data:
            try:
                await vector_service.add_document_chunks(
                    workspace_id=str(workspace_id),
                    document_id=str(document_id),
                    chunks=chunks_data
                )

                # 更新向量化状态
                await db.execute(f"""
                    UPDATE documents SET
                        is_vectorized = true,
                        vector_count = :count
                    WHERE id = {document_id}
                """, {'count': len(chunks_data)})
                await db.commit()

                logger.info(f"文档向量化完成: {document_id}, 分块数量: {len(chunks_data)}")

            except Exception as e:
                logger.error(f"文档向量化失败 {document_id}: {str(e)}")
                # 不阻止文档处理，继续标记为完成但向量化失败

        logger.info(f"文档处理完成: {document_id}")

    except Exception as e:
        logger.error(f"文档处理失败 {document_id}: {str(e)}")
        # 更新状态为失败
        await db.execute(f"""
            UPDATE documents SET
                status = 'failed',
                error_message = :error
            WHERE id = {document_id}
        """, {'error': str(e)})
        await db.commit()


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    workspace_id: int = 1,  # 暂时固定工作区ID
    db: AsyncSession = Depends(get_db)
):
    """上传文档"""
    # 检查文件类型
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件名不能为空"
        )

    # 检查文件扩展名
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file_ext}"
        )

    # 检查文件大小
    file_size = 0
    content = await file.read()
    file_size = len(content)

    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件大小超过限制"
        )

    # 保存文件
    file_id = str(uuid.uuid4())
    filename = f"{file_id}{file_ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, filename)

    # 确保上传目录存在
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    with open(file_path, "wb") as f:
        f.write(content)

    # 保存到数据库
    document = Document(
        filename=filename,
        original_filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        mime_type=file.content_type or "application/octet-stream",
        file_type=file_ext[1:],  # 去掉点
        workspace_id=workspace_id,
        status="processing"  # 初始状态为处理中
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    # 启动后台处理
    background_tasks.add_task(process_document_content, document.id, file_path, db)

    return {
        "id": document.id,
        "filename": document.filename,
        "original_filename": document.original_filename,
        "file_size": document.file_size,
        "status": document.status,
        "message": "文件上传成功，正在后台处理内容..."
    }


@router.get("/")
async def get_documents(
    workspace_id: int = None,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """获取文档列表"""
    query = select(Document).offset(skip).limit(limit)

    if workspace_id:
        query = query.where(Document.workspace_id == workspace_id)

    result = await db.execute(query)
    documents = result.scalars().all()

    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "original_filename": doc.original_filename,
            "file_size": doc.file_size,
            "file_type": doc.file_type,
            "status": doc.status,
            "workspace_id": doc.workspace_id,
            "is_vectorized": doc.is_vectorized,
            "vector_count": doc.vector_count,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        }
        for doc in documents
    ]


@router.get("/{document_id}/download")
async def download_document(
    document_id: int,
    db: AsyncSession = Depends(get_db)
):
    """下载文档"""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在"
        )

    if not os.path.exists(document.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )

    return FileResponse(
        path=document.file_path,
        filename=document.original_filename,
        media_type=document.mime_type
    )


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取文档内容"""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在"
        )

    if document.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文档处理尚未完成，当前状态: {document.status}"
        )

    # 获取文档分块
    chunks_result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    chunks = chunks_result.scalars().all()

    return {
        "id": document.id,
        "title": document.title,
        "content": document.content,
        "chunks": [
            {
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "metadata": chunk.metadata
            }
            for chunk in chunks
        ],
        "metadata": document.metadata,
        "file_type": document.file_type,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


@router.post("/{document_id}/vectorize")
async def vectorize_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """对文档进行向量化"""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在"
        )

    if document.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文档处理尚未完成，当前状态: {document.status}"
        )

    if document.is_vectorized:
        return {"message": "文档已经向量化", "vector_count": document.vector_count}

    # 获取文档分块
    chunks_result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    chunks = chunks_result.scalars().all()

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文档没有分块，无法向量化"
        )

    # 启动后台向量化
    background_tasks.add_task(vectorize_document_chunks, document_id, document.workspace_id, chunks, db)

    return {"message": "开始向量化文档，请稍后查看状态"}


async def vectorize_document_chunks(document_id: int, workspace_id: int, chunks: List, db: AsyncSession):
    """后台向量化工夫分块"""
    try:
        # 更新状态为向量化中
        await db.execute(f"""
            UPDATE documents SET status = 'vectorizing' WHERE id = {document_id}
        """)
        await db.commit()

        # 转换为向量服务需要的格式
        chunks_data = [
            {
                'content': chunk.content,
                'metadata': json.loads(chunk.metadata) if chunk.metadata else {}
            }
            for chunk in chunks
        ]

        # 执行向量化
        await vector_service.add_document_chunks(
            workspace_id=str(workspace_id),
            document_id=str(document_id),
            chunks=chunks_data
        )

        # 更新向量化状态
        await db.execute(f"""
            UPDATE documents SET
                status = 'completed',
                is_vectorized = true,
                vector_count = :count
            WHERE id = {document_id}
        """, {'count': len(chunks_data)})
        await db.commit()

        logger.info(f"文档向量化完成: {document_id}, 分块数量: {len(chunks_data)}")

    except Exception as e:
        logger.error(f"文档向量化失败 {document_id}: {str(e)}")
        # 更新状态为向量化失败
        await db.execute(f"""
            UPDATE documents SET
                status = 'vectorization_failed',
                error_message = :error
            WHERE id = {document_id}
        """, {'error': str(e)})
        await db.commit()


@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除文档"""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在"
        )

    # 删除物理文件
    if os.path.exists(document.file_path):
        os.remove(document.file_path)

    # 删除数据库记录
    await db.delete(document)
    await db.commit()

    return {"message": "文档删除成功"}
