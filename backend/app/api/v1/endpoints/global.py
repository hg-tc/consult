"""
全局文档库API端点
支持公共文档库和工作区分离的架构
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import os
import uuid
import logging

from app.models.global_database import GlobalDatabaseService
from app.services.global_rag_service import GlobalRAGService
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/global", tags=["global"])

# 全局服务实例
global_db_service = None
global_rag_service = None

def get_global_services():
    """获取全局服务实例"""
    global global_db_service, global_rag_service
    
    if global_db_service is None:
        global_db_service = GlobalDatabaseService(None)  # 简化处理
    
    if global_rag_service is None:
        global_rag_service = GlobalRAGService(global_db_service)
    
    return global_db_service, global_rag_service


@router.post("/documents/upload")
async def upload_global_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """上传文档到全局文档库"""
    try:
        # 检查文件类型
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        
        file_ext = os.path.splitext(file.filename)[1].lower()
        allowed_extensions = ['.pdf', '.docx', '.doc', '.txt', '.md']
        
        if file_ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file_ext}")
        
        # 检查文件大小
        content = await file.read()
        file_size = len(content)
        
        if file_size > 50 * 1024 * 1024:  # 50MB限制
            raise HTTPException(status_code=413, detail="文件大小超过限制")
        
        # 保存文件
        file_id = str(uuid.uuid4())
        filename = f"{file_id}{file_ext}"
        upload_dir = Path("uploads/global")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / filename
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        # 获取全局服务
        _, rag_service = get_global_services()
        
        # 后台处理文档
        metadata = {
            'original_filename': file.filename,
            'file_size': file_size,
            'mime_type': file.content_type or "application/octet-stream"
        }
        
        background_tasks.add_task(
            process_global_document, 
            str(file_path), 
            metadata
        )
        
        return {
            "id": file_id,
            "filename": filename,
            "original_filename": file.filename,
            "file_size": file_size,
            "status": "processing",
            "message": "文件上传成功，正在后台处理..."
        }
        
    except Exception as e:
        logger.error(f"全局文档上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


async def process_global_document(file_path: str, metadata: Dict[str, Any]):
    """后台处理全局文档"""
    try:
        _, rag_service = get_global_services()
        
        # 添加到全局文档库
        document_id = await rag_service.add_global_document(file_path, metadata)
        
        if document_id:
            logger.info(f"全局文档处理完成: {file_path}, ID: {document_id}")
        else:
            logger.error(f"全局文档处理失败: {file_path}")
            
    except Exception as e:
        logger.error(f"全局文档后台处理失败: {str(e)}")


@router.get("/documents")
async def list_global_documents(
    db: Session = Depends(get_db)
):
    """列出所有全局文档"""
    try:
        # 这里应该从数据库查询，简化处理
        return {
            "documents": [],
            "total_count": 0,
            "message": "全局文档列表功能待实现"
        }
        
    except Exception as e:
        logger.error(f"获取全局文档列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/search")
async def search_global_documents(
    query: str,
    workspace_id: Optional[str] = None,
    top_k: int = 5,
    db: Session = Depends(get_db)
):
    """搜索全局文档"""
    try:
        _, rag_service = get_global_services()
        
        results = await rag_service.search_documents(query, workspace_id, top_k)
        
        return {
            "query": query,
            "results": results,
            "total_count": len(results),
            "workspace_id": workspace_id
        }
        
    except Exception as e:
        logger.error(f"全局文档搜索失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.post("/chat")
async def global_chat(
    question: str,
    workspace_id: Optional[str] = None,
    top_k: int = 5,
    db: Session = Depends(get_db)
):
    """全局问答"""
    try:
        # 改为 LlamaIndex 检索
        from app.services.llamaindex_retriever import LlamaIndexRetriever
        workspace = workspace_id or "global"
        retriever = LlamaIndexRetriever.get_instance(workspace)
        results = await retriever.retrieve(query=question, top_k=top_k, use_hybrid=True, use_compression=True)
        return {
            "answer": "",
            "sources": results,
            "metadata": {
                "retriever": "llamaindex",
                "workspace_id": workspace,
                "top_k": top_k
            }
        }
        
    except Exception as e:
        logger.error(f"全局问答失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"问答失败: {str(e)}")


@router.get("/stats")
async def get_global_stats(
    db: Session = Depends(get_db)
):
    """获取全局统计信息"""
    try:
        _, rag_service = get_global_services()
        
        stats = rag_service.get_global_stats()
        
        return stats
        
    except Exception as e:
        logger.error(f"获取全局统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


# 工作区管理API
@router.post("/workspaces")
async def create_workspace(
    name: str,
    description: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db)
):
    """创建工作区"""
    try:
        workspace_id = str(uuid.uuid4())
        
        # 这里应该保存到数据库，简化处理
        return {
            "id": workspace_id,
            "name": name,
            "description": description,
            "settings": settings or {},
            "status": "active",
            "created_at": "2025-10-23T21:00:00Z"
        }
        
    except Exception as e:
        logger.error(f"创建工作区失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.get("/workspaces")
async def list_workspaces(
    db: Session = Depends(get_db)
):
    """列出所有工作区"""
    try:
        # 这里应该从数据库查询，简化处理
        return {
            "workspaces": [
                {
                    "id": "1",
                    "name": "默认工作区",
                    "description": "包含所有全局文档的默认工作区",
                    "status": "active",
                    "document_count": 0,  # 待实现
                    "created_at": "2025-10-23T21:00:00Z"
                }
            ],
            "total_count": 1
        }
        
    except Exception as e:
        logger.error(f"获取工作区列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/workspaces/{workspace_id}/documents/{document_id}/access")
async def grant_document_access(
    workspace_id: str,
    document_id: str,
    access_level: str = "read",
    db: Session = Depends(get_db)
):
    """授予工作区文档访问权限"""
    try:
        # 这里应该保存到数据库，简化处理
        return {
            "workspace_id": workspace_id,
            "document_id": document_id,
            "access_level": access_level,
            "status": "granted"
        }
        
    except Exception as e:
        logger.error(f"授予文档访问权限失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"授权失败: {str(e)}")


@router.delete("/workspaces/{workspace_id}/documents/{document_id}/access")
async def revoke_document_access(
    workspace_id: str,
    document_id: str,
    db: Session = Depends(get_db)
):
    """撤销工作区文档访问权限"""
    try:
        # 这里应该从数据库删除，简化处理
        return {
            "workspace_id": workspace_id,
            "document_id": document_id,
            "status": "revoked"
        }
        
    except Exception as e:
        logger.error(f"撤销文档访问权限失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"撤销失败: {str(e)}")
