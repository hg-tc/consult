"""
文档生成应用 - DeepResearch 风格长文档生成
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

from app.apps.base_app import BaseApp

logger = logging.getLogger(__name__)


class DocumentGeneratorApp(BaseApp):
    """文档生成应用"""
    
    def __init__(self):
        super().__init__(
            app_id="document-generator",
            app_name="文档生成应用",
            app_description="基于 DeepResearch 技术的长文档生成"
        )
    
    def _register_routes(self):
        """注册文档生成相关的路由"""
        
        @self.router.post("/generate")
        async def generate_document(data: Dict[str, Any]):
            """DeepResearch 风格长文档生成 API"""
            try:
                task_description = data.get("task_description", "")
                workspace_id = data.get("workspace_id", "global")
                doc_requirements = data.get("doc_requirements", {
                    "target_words": 5000,
                    "writing_style": "专业、严谨、客观"
                })
                
                if not task_description:
                    raise HTTPException(status_code=400, detail="task_description 不能为空")
                
                # 导入新组件
                from app.utils.import_with_timeout import import_symbol_with_timeout
                LlamaIndexRetriever = import_symbol_with_timeout(
                    "app.services.llamaindex_retriever", "LlamaIndexRetriever", timeout_seconds=5.0
                )
                from app.workflows.deepresearch_doc_workflow import DeepResearchDocWorkflow
                from app.services.web_search_service import get_web_search_service
                
                # 获取或创建检索器
                workspace_retriever = LlamaIndexRetriever.get_instance(workspace_id)
                global_retriever = LlamaIndexRetriever.get_instance("global")
                
                # 获取 LLM 和网络搜索服务
                web_search_service = get_web_search_service()
                
                # 创建文档生成工作流
                workflow = DeepResearchDocWorkflow(
                    workspace_retriever=workspace_retriever,
                    global_retriever=global_retriever,
                    web_search_service=web_search_service,
                    llm=None
                )
                
                # 执行工作流
                result = await workflow.run(task_description, workspace_id, doc_requirements)
                
                return {
                    "document": result["document"],
                    "quality_metrics": result["quality_metrics"],
                    "references": result["references"],
                    "outline": result["outline"],
                    "processing_steps": result["processing_steps"]
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"DeepResearch 文档生成失败: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"文档生成失败: {str(e)}"
                )


# 创建应用实例
APP = DocumentGeneratorApp()

# 提供 get_app 函数用于注册器
def get_app():
    return APP

