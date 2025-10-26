"""
问答系统端点
"""

import json
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.qa_service import QAService

router = APIRouter()
qa_service = QAService()


@router.post("/ask")
async def ask_question(
    workspace_id: int,
    question: str,
    conversation_id: str = None,
    model_provider: str = Query("openai", description="模型提供商"),
    temperature: float = Query(0.7, description="温度参数"),
    max_tokens: int = Query(1000, description="最大token数"),
    db: AsyncSession = Depends(get_db)
):
    """
    问答接口

    - **workspace_id**: 工作区ID
    - **question**: 问题内容
    - **conversation_id**: 对话ID（可选）
    - **model_provider**: 模型提供商 (openai, claude)
    - **temperature**: 温度参数 (0-1)
    - **max_tokens**: 最大token数
    """
    try:
        result = await qa_service.ask_question(
            workspace_id=str(workspace_id),
            question=question,
            conversation_id=conversation_id,
            model_provider=model_provider,
            temperature=temperature,
            max_tokens=max_tokens,
            db=db
        )

        return {
            "answer": result.answer,
            "references": result.references,
            "sources": result.sources,
            "confidence": result.confidence,
            "metadata": result.metadata
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"问答失败: {str(e)}"
        )


@router.post("/ask/stream")
async def ask_question_streaming(
    workspace_id: int,
    question: str,
    conversation_id: str = None,
    model_provider: str = Query("openai", description="模型提供商"),
    temperature: float = Query(0.7, description="温度参数"),
    max_tokens: int = Query(1000, description="最大token数"),
    db: AsyncSession = Depends(get_db)
):
    """
    流式问答接口

    返回Server-Sent Events格式的流式响应
    """

    async def generate_response():
        try:
            async for chunk in qa_service.ask_streaming(
                workspace_id=str(workspace_id),
                question=question,
                conversation_id=conversation_id,
                model_provider=model_provider,
                temperature=temperature,
                max_tokens=max_tokens,
                db=db
            ):
                # 将数据格式化为SSE格式
                if chunk["type"] == "answer":
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "error":
                    yield f"data: {json.dumps(chunk)}\n\n"

        except Exception as e:
            error_data = {
                "type": "error",
                "content": f"流式问答失败: {str(e)}",
                "done": True
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/providers")
async def get_available_providers():
    """获取可用的大模型提供商"""
    providers = qa_service.llm_service.get_available_providers()
    models = {}

    for provider in providers:
        models[provider] = qa_service.llm_service.get_provider_models(provider)

    return {
        "providers": providers,
        "models": models
    }


@router.post("/reindex/{workspace_id}")
async def reindex_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    重新索引工作区文档

    这将重新处理工作区中的所有文档并重建向量索引
    """
    try:
        # 获取工作区中的所有文档
        from sqlalchemy import select
        from app.models.document import Document

        result = await db.execute(
            select(Document).where(Document.workspace_id == workspace_id)
        )
        documents = result.scalars().all()

        if not documents:
            return {"message": "工作区中没有文档需要索引"}

        # 获取文档内容和分块
        reindexed_count = 0
        for doc in documents:
            if doc.status == "completed":
                # 获取文档分块
                from app.models.document import DocumentChunk
                chunks_result = await db.execute(
                    select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
                )
                chunks = chunks_result.scalars().all()

                if chunks:
                    # 转换为向量服务需要的格式
                    chunks_data = [
                        {
                            'content': chunk.content,
                            'metadata': json.loads(chunk.metadata) if chunk.metadata else {}
                        }
                        for chunk in chunks
                    ]

                    # 重新索引
                    await qa_service.vector_service.add_document_chunks(
                        workspace_id=str(workspace_id),
                        document_id=str(doc.id),
                        chunks=chunks_data
                    )

                    reindexed_count += 1

        return {
            "message": f"成功重新索引 {reindexed_count} 个文档",
            "total_documents": len(documents)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新索引失败: {str(e)}"
        )
