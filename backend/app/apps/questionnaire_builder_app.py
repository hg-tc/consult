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
                phase: Optional[str] = (data.get("phase") or None)

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
                # 安全导入检索器，超过5秒直接报错
                from app.utils.import_with_timeout import import_symbol_with_timeout
                LlamaIndexRetriever = import_symbol_with_timeout(
                    "app.services.llamaindex_retriever", "LlamaIndexRetriever", timeout_seconds=5.0
                )
                
                from app.core.config import settings
                from app.services.web_search_service import get_web_search_service
                from app.workflows.questionnaire_builder_workflow import QuestionnaireBuilderWorkflow

                workspace = workspace_id or "global"
                retriever_workspace = LlamaIndexRetriever.get_instance(workspace)
                retriever_global = LlamaIndexRetriever.get_instance("global")

                
                web_search = get_web_search_service()

                workflow = QuestionnaireBuilderWorkflow(
                    workspace_retriever=retriever_workspace,
                    global_retriever=retriever_global,
                    web_search_service=web_search,
                    llm=None
                )

                result = await workflow.run(request_context, phase=phase)

                return result
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"问卷生成失败: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"问卷生成失败: {str(e)}")

        @self.router.post("/revise-report")
        async def revise_report(data: Dict[str, Any]):
            """对阶段二报告进行修订（占位：直接返回合并文本）。"""
            try:
                original: str = data.get("original") or ""
                instruction: str = data.get("instruction") or ""
                if not original:
                    raise HTTPException(status_code=400, detail="original 为必填")
                # 占位策略：简单拼接（后续可调用 LLM 做编辑）
                revised = original.strip()
                if instruction:
                    revised = revised + "\n\n---\n用户修订说明：\n" + instruction.strip()
                return {"revised_report_md": revised}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"报告修订失败: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"报告修订失败: {str(e)}")

        @self.router.post("/upload-answers")
        async def upload_answers(data: Dict[str, Any]):
            """上传问卷答案元数据（占位：直接回显）。"""
            try:
                workspace_id: Optional[str] = data.get("workspace_id")
                answers: Any = data.get("answers")
                if answers is None:
                    raise HTTPException(status_code=400, detail="answers 为必填")
                # 占位：直接回显并打时间戳（省略存储）
                return {"workspace_id": workspace_id, "accepted": True, "answers": answers}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"上传答案失败: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"上传答案失败: {str(e)}")


# 实例与工厂方法
APP = QuestionnaireBuilderApp()


def get_app():
    return APP


