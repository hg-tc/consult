"""
API路由配置
"""

from fastapi import APIRouter
from app.api.v1.endpoints import auth, workspaces, documents, conversations, templates, qa, context, generation, health

api_router = APIRouter()

# 包含各个模块的路由
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["工作区"])
api_router.include_router(documents.router, prefix="/documents", tags=["文档"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["对话"])
api_router.include_router(templates.router, prefix="/templates", tags=["模板"])
api_router.include_router(qa.router, prefix="/qa", tags=["问答系统"])
api_router.include_router(context.router, prefix="/context", tags=["上下文管理"])
api_router.include_router(generation.router, prefix="/generation", tags=["文档生成"])
api_router.include_router(health.router, prefix="/health", tags=["健康检查"])
