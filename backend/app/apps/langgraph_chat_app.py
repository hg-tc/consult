"""
智能问答应用 - LangGraph 智能 RAG 问答系统
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

from app.apps.base_app import BaseApp

logger = logging.getLogger(__name__)


class LangGraphChatApp(BaseApp):
    """智能问答应用"""
    
    def __init__(self):
        super().__init__(
            app_id="langgraph-chat",
            app_name="智能问答应用",
            app_description="基于 LangGraph 的智能 RAG 问答"
        )
    
    def _register_routes(self):
        """注册智能问答相关的路由"""
        
        @self.router.post("/chat")
        async def chat_with_langgraph(data: Dict[str, Any]):
            """LangGraph 智能 RAG API"""
            try:
                question = data.get("question") or data.get("message", "")
                workspace_id = data.get("workspace_id") or data.get("workspaceId", "global")
                # Debug 入参
                try:
                    q_preview = str(question)
                    if q_preview is None:
                        q_preview = "<None>"
                    if len(q_preview) > 300:
                        q_preview = q_preview[:300] + "...<truncated>"
                    logger.debug(
                        f"[langgraph_chat_app.chat.debug] workspace_id={workspace_id}, type(question)={type(question)}, question_preview={q_preview}"
                    )
                except Exception as _dbg_err:
                    logger.warning(f"langgraph_chat_app /chat 入参调试信息记录失败: {_dbg_err}")
                
                if not question:
                    raise HTTPException(status_code=400, detail="question 或 message 不能为空")
                
                # 导入新组件
                from app.utils.import_with_timeout import import_symbol_with_timeout
                LlamaIndexRetriever = import_symbol_with_timeout(
                    "app.services.llamaindex_retriever", "LlamaIndexRetriever", timeout_seconds=5.0
                )
                from app.workflows.langgraph_rag_workflow import LangGraphRAGWorkflow
                
                # 获取或创建检索器
                workspace_retriever = LlamaIndexRetriever.get_instance(workspace_id)
                global_retriever = LlamaIndexRetriever.get_instance("global")
                
                # 获取 LLM
                from app.services.langchain_rag_service import LangChainRAGService
                from app.core.config import settings
                rag_service = LangChainRAGService(vector_db_path=settings.LANGCHAIN_VECTOR_DB_PATH)
                
                # 创建工作流
                workflow = LangGraphRAGWorkflow(
                    workspace_retriever=workspace_retriever,
                    global_retriever=global_retriever,
                    llm=rag_service.llm
                )
                
                # 执行工作流
                result = await workflow.run(question, workspace_id)
                
                return {
                    "answer": result["answer"],
                    "sources": result["sources"],
                    "metadata": result["metadata"]
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"LangGraph 查询失败: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"查询失败: {str(e)}"
                )
        
        @self.router.post("/agent/chat")
        async def ask_question(data: Dict[str, Any]):
            """统一代理到 LangGraph + LlamaIndex 实现"""
            try:
                return await chat_with_langgraph(data)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"/api/agent/chat 处理失败: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"处理失败: {str(e)}"
                )


# 创建应用实例
APP = LangGraphChatApp()

# 提供 get_app 函数用于注册器
def get_app():
    return APP

