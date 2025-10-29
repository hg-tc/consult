"""
问卷生成应用 - 基于 LangGraph 的政策问卷生成
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
import logging

from app.apps.base_app import BaseApp

logger = logging.getLogger(__name__)


class QuestionnaireBuilderApp(BaseApp):
    """问卷生成应用"""

    def __init__(self):
        super().__init__(
            app_id="questionnaire-builder",
            app_name="问卷生成应用",
            app_description="基于客户画像、申请项目与内外部信息，生成政策问卷与材料清单"
        )

    def _register_routes(self):
        @self.router.post("/generate")
        async def generate_questionnaire(data: Dict[str, Any]):
            """根据输入生成问卷（必须包含 target_projects）"""
            try:
                workspace_id: Optional[str] = data.get("workspace_id")
                company_name: Optional[str] = data.get("company_name")
                target_projects: List[str] = data.get("target_projects") or []
                known_info: Dict[str, Any] = data.get("known_info") or {}

                if not target_projects or not isinstance(target_projects, list):
                    raise HTTPException(status_code=400, detail="target_projects 为必填，且必须为字符串数组")

                # 组装上下文
                request_context = {
                    "workspace_id": workspace_id,
                    "company_name": company_name,
                    "target_projects": target_projects,
                    "known_info": known_info,
                }

                # 依赖注入：检索器、LLM、Web 搜索
                from app.services.llamaindex_retriever import LlamaIndexRetriever
                from app.services.langchain_rag_service import LangChainRAGService
                from app.core.config import settings
                from app.services.web_search_service import get_web_search_service
                from app.workflows.questionnaire_builder_workflow import QuestionnaireBuilderWorkflow

                workspace = workspace_id or "global"
                retriever_workspace = LlamaIndexRetriever.get_instance(workspace)
                retriever_global = LlamaIndexRetriever.get_instance("global")

                rag_service = LangChainRAGService(vector_db_path=settings.LANGCHAIN_VECTOR_DB_PATH)
                web_search = get_web_search_service()

                workflow = QuestionnaireBuilderWorkflow(
                    workspace_retriever=retriever_workspace,
                    global_retriever=retriever_global,
                    web_search_service=web_search,
                    llm=rag_service.llm
                )

                result = await workflow.run(request_context)

                return result
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"问卷生成失败: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"问卷生成失败: {str(e)}")


# 实例与工厂方法
APP = QuestionnaireBuilderApp()


def get_app():
    return APP


