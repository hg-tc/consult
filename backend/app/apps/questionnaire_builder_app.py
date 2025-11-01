"""
问卷生成应用 - 基于 LangGraph 的政策问卷生成
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
import logging
import asyncio

from app.apps.base_app import BaseApp

logger = logging.getLogger(__name__)


async def _execute_questionnaire_task(task_id: str, request_data: Dict[str, Any]):
    """后台执行问卷生成任务"""
    task_queue = None
    try:
        from app.services.task_queue import get_task_queue
        from app.utils.import_with_timeout import import_symbol_with_timeout
        from app.services.web_search_service import get_web_search_service
        from app.workflows.questionnaire_builder_workflow import QuestionnaireBuilderWorkflow
        from app.core.config import settings
        import asyncio
        
        task_queue = get_task_queue()
        
        # 更新任务状态为处理中
        task_queue.start_task(task_id)
        
        # 将当前任务添加到 running_tasks（用于跟踪）
        # 注意：这里我们创建一个占位符，因为实际的异步任务已经在外面通过 asyncio.create_task 创建
        # 但我们需要在 running_tasks 中标记这个任务正在运行
        current_task = asyncio.current_task()
        if current_task and task_id not in task_queue.running_tasks:
            task_queue.running_tasks[task_id] = current_task
        task_queue.update_task_progress(
            task_id=task_id,
            stage=None,  # 使用自定义stage
            progress=5,
            message="正在初始化检索器和搜索服务..."
        )
        
        workspace_id: Optional[str] = request_data.get("workspace_id")
        company_name: Optional[str] = request_data.get("company_name")
        target_projects: List[str] = request_data.get("target_projects") or []
        known_info: Dict[str, Any] = request_data.get("known_info") or {}
        client_id: str = request_data.get("client_id", "")
        
        # 组装上下文
        request_context = {
            "workspace_id": workspace_id,
            "company_name": company_name,
            "target_projects": target_projects,
            "known_info": known_info,
            "client_id": client_id,
            "task_id": task_id,  # 传入task_id用于进度更新
        }
        
        # 依赖注入：检索器、LLM、Web 搜索
        LlamaIndexRetriever = import_symbol_with_timeout(
            "app.services.llamaindex_retriever", "LlamaIndexRetriever", timeout_seconds=5.0
        )
        
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
        
        task_queue.update_task_progress(
            task_id=task_id,
            stage=None,
            progress=10,
            message="开始执行问卷生成工作流..."
        )
        
        # 执行工作流（不使用wait_for，因为这是后台任务）
        try:
            result = await workflow.run(request_context)
            
            # 保存结果到任务metadata
            task_queue.complete_task(
                task_id=task_id,
                result={
                    "final_analysis": result.get("final_analysis"),
                    "final_md": result.get("final_md"),
                }
            )
            logger.info(f"问卷生成任务完成: {task_id}")
            
        except Exception as e:
            error_msg = f"问卷生成失败: {str(e)}"
            logger.error(f"任务 {task_id} 失败: {error_msg}", exc_info=True)
            if task_queue:
                task_queue.fail_task(task_id, error_msg)
            
    except Exception as e:
        logger.error(f"执行问卷生成任务异常: {task_id}, 错误: {e}", exc_info=True)
        if not task_queue:
            try:
                from app.services.task_queue import get_task_queue
                task_queue = get_task_queue()
            except:
                pass
        if task_queue:
            task_queue.fail_task(task_id, f"任务执行异常: {str(e)}")


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
            """根据输入生成问卷（后台任务模式，立即返回task_id）"""
            try:
                from app.services.task_queue import get_task_queue
                import asyncio
                
                workspace_id: Optional[str] = data.get("workspace_id")
                company_name: Optional[str] = data.get("company_name")
                target_projects: List[str] = data.get("target_projects") or []
                known_info: Dict[str, Any] = data.get("known_info") or {}
                client_id: str = data.get("client_id", "")

                if not target_projects or not isinstance(target_projects, list):
                    raise HTTPException(status_code=400, detail="target_projects 为必填，且必须为字符串数组")

                # 创建后台任务
                task_queue = get_task_queue()
                # 生成友好的显示名称
                display_name = f"问卷生成"
                if company_name:
                    display_name += f" - {company_name}"
                if target_projects:
                    projects_str = ", ".join(target_projects[:3])
                    if len(target_projects) > 3:
                        projects_str += f"等{len(target_projects)}项"
                    display_name += f" ({projects_str})"
                
                task_id = task_queue.create_task(
                    task_type="questionnaire_generation",
                    metadata={
                        "original_filename": display_name,  # 用于前端显示
                        "workspace_id": workspace_id,
                        "company_name": company_name,
                        "target_projects": target_projects,
                        "known_info": known_info,
                        "client_id": client_id,
                    },
                    workspace_id=workspace_id
                )

                # 启动后台任务
                asyncio.create_task(_execute_questionnaire_task(task_id, data))
                
                # 立即返回task_id
                return {
                    "task_id": task_id,
                    "status": "pending",
                    "message": "问卷生成任务已提交，正在后台处理"
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"创建问卷生成任务失败: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")

        @self.router.get("/result/{task_id}")
        async def get_questionnaire_result(task_id: str):
            """根据task_id获取问卷生成结果"""
            try:
                from app.services.task_queue import get_task_queue
                task_queue = get_task_queue()
                task = task_queue.get_task(task_id)
                
                if not task:
                    # 任务可能已被清理（超过保留时间或数量限制）
                    # 或者任务从未创建成功
                    logger.warning(f"查询不存在的任务: {task_id}")
                    raise HTTPException(
                        status_code=404, 
                        detail=f"任务不存在或已被清理: {task_id}。任务可能在1小时后被自动清理，或任务从未创建成功。"
                    )
                
                if task.status.value == "completed":
                    # 从metadata中提取结果
                    result = {
                        "task_id": task_id,
                        "status": "completed",
                        "final_analysis": task.metadata.get("final_analysis"),
                        "final_md": task.metadata.get("final_md"),
                    }
                    return result
                elif task.status.value == "failed":
                    return {
                        "task_id": task_id,
                        "status": "failed",
                        "error_message": task.error_message,
                    }
                else:
                    # 还在处理中，返回进度信息
                    return {
                        "task_id": task_id,
                        "status": task.status.value,
                        "progress": task.progress.progress,
                        "message": task.progress.message,
                    }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"获取问卷结果失败: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"获取结果失败: {str(e)}")

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


