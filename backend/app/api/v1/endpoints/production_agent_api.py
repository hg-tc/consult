"""
生产级 Agent API 端点
支持 REST API 和 WebSocket
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from pydantic import BaseModel
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/production-agent", tags=["ProductionAgent"])

# 请求模型
class AgentRequest(BaseModel):
    """Agent 请求"""
    user_request: str
    workspace_id: str = "global"
    conversation_history: List[Dict[str, Any]] = []

class ConfirmationRequest(BaseModel):
    """确认请求"""
    task_id: str
    feedback: str = ""
    options: List[str] = []

# 单例工作流实例（在应用启动时初始化）
_production_workflow = None

def get_production_workflow():
    """获取生产工作流实例"""
    global _production_workflow
    if _production_workflow is None:
        from app.services.langchain_rag_service import get_rag_service
        from langchain_openai import ChatOpenAI
        
        rag_service = get_rag_service()
        llm = rag_service.llm
        
        if llm is None:
            # 初始化 LLM
            llm = ChatOpenAI(
                model="gpt-3.5-turbo",
                temperature=0.1
            )
        
        from app.workflows.production_workflow import ProductionWorkflow
        _production_workflow = ProductionWorkflow(llm, rag_service)
    
    return _production_workflow

@router.post("/generate")
async def generate_document(
    request: AgentRequest,
    background_tasks: BackgroundTasks
):
    """
    生成文档（异步）
    支持：Word, Excel, PowerPoint, PDF
    """
    try:
        workflow = get_production_workflow()
        
        # 执行工作流
        result = workflow.execute(
            user_request=request.user_request,
            workspace_id=request.workspace_id,
            conversation_history=request.conversation_history
        )
        
        return {
            "task_id": str(result.get("task_id", "unknown")),
            "status": "processing" if result.get("success") else "failed",
            "quality_score": result.get("quality_score", 0.0),
            "iterations": result.get("iterations", 0),
            "message": "文档生成任务已提交"
        }
        
    except Exception as e:
        logger.error(f"文档生成失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws/generate")
async def websocket_generate(websocket: WebSocket):
    """WebSocket 实时生成（流式输出）"""
    await websocket.accept()
    
    try:
        # 接收请求
        request_data = await websocket.receive_json()
        
        logger.info(f"收到 WebSocket 请求: {request_data}")
        
        # 创建回调
        from app.callbacks import ProductionCallbackHandler
        callback = ProductionCallbackHandler(websocket, enable_langsmith=True)
        
        # 执行工作流
        workflow = get_production_workflow()
        result = await workflow.execute(
            user_request=request_data.get("user_request", ""),
            workspace_id=request_data.get("workspace_id", "global"),
            conversation_history=request_data.get("conversation_history", []),
            config={"callbacks": [callback]}
        )
        
        # 发送完成消息
        await websocket.send_json({
            "type": "complete",
            "result": result,
            "cost_summary": callback.get_summary()
        })
        
    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开")
    except Exception as e:
        logger.error(f"WebSocket 处理失败: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "error": str(e)
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass

@router.post("/confirm")
async def confirm_action(confirmation: ConfirmationRequest):
    """确认人机交互节点"""
    try:
        # 获取工作流
        workflow = get_production_workflow()
        
        # 继续执行（实际实现需要维护任务状态）
        return {
            "status": "confirmed",
            "message": "确认已处理"
        }
    except Exception as e:
        logger.error(f"确认处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_status():
    """获取系统状态"""
    return {
        "status": "running",
        "workflow_available": _production_workflow is not None,
        "version": "1.0.0"
    }

