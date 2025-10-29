"""
简化的后端应用 - 跳过有问题的依赖
"""

from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi import File, UploadFile, Form
import os
import uuid
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# ============================================
# 关键：强制 HuggingFace 离线模式（必须在导入任何 HF 相关模块之前设置）
# HuggingFace 在 import 时就会尝试联网，必须在最早阶段禁用
# ============================================
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('HF_DATASETS_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '1')
os.environ.setdefault('HF_HUB_DISABLE_EXPERIMENTAL_WARNING', '1')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
os.environ.setdefault('TRANSFORMERS_NO_ADVISORY_WARNINGS', '1')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

# 如果设置了本地模型目录，使用它作为 HF 缓存目录
if 'LOCAL_BGE_MODEL_DIR' in os.environ:
    local_model_dir = os.environ['LOCAL_BGE_MODEL_DIR']
    os.environ.setdefault('HF_HOME', local_model_dir)
    os.environ.setdefault('HUGGINGFACE_HUB_CACHE', local_model_dir)
    os.environ.setdefault('TRANSFORMERS_CACHE', local_model_dir)

# 设置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/root/consult/backend/debug.log')
    ]
)
logger = logging.getLogger(__name__)
logger.info("日志系统已配置为DEBUG级别")

# WebSocket连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket连接已建立，当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket连接已断开，当前连接数: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"发送个人消息失败: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"广播消息失败: {e}")
                disconnected.append(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# 全局RAG服务实例（单例模式）
_rag_service_instance = None

def get_rag_service():
    """获取全局RAG服务实例（单例模式）"""
    global _rag_service_instance
    if _rag_service_instance is None:
        from app.services.langchain_rag_service import LangChainRAGService
        # 使用global_db目录，is_global=True标记这不是一个工作区
        _rag_service_instance = LangChainRAGService(vector_db_path="global_db", is_global=True)
    return _rag_service_instance

def get_workspace_rag_service(workspace_id: str):
    """获取工作区RAG服务实例"""
    from app.services.langchain_rag_service import LangChainRAGService
    return LangChainRAGService(vector_db_path=f"langchain_vector_db/workspace_{workspace_id}")

def get_global_rag_service():
    """获取全局RAG服务实例"""
    from app.services.langchain_rag_service import LangChainRAGService
    # 使用global_db目录，is_global=True标记这不是一个工作区
    return LangChainRAGService(vector_db_path="global_db", is_global=True)

app = FastAPI(
    title="Agent Service Platform API",
    description="简化的AI Agent服务平台后端API",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:13000", "http://116.136.130.162:13000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------
# LlamaIndex 存储健康检查（可选）
# ------------------------
@app.get("/api/llamaindex/health/{workspace_id}")
async def llamaindex_health(workspace_id: str = "global"):
    try:
        from pathlib import Path
        base = Path(f"llamaindex_storage/{workspace_id}")
        docstore = base / "docstore"
        index_store = base / "index_store"
        vector_store = base / "vector_store"

        return {
            "workspace_id": workspace_id,
            "base_exists": base.exists(),
            "docstore_exists": docstore.exists(),
            "index_store_exists": index_store.exists(),
            "vector_store_exists": vector_store.exists(),
            "base_path": str(base)
        }
    except Exception as e:
        return {
            "workspace_id": workspace_id,
            "error": str(e)
        }

# 内存存储（临时替代数据库）
workspaces_db = []
documents_db = []
conversations_db = []

@app.get("/")
async def root():
    """根路径 - 返回服务信息"""
    return {
        "message": "Agent Service Platform API",
        "version": "1.0.0",
        "frontend_url": "http://localhost:3000",
        "api_docs": "http://localhost:13000/docs",
        "health_check": "http://localhost:13000/api/health"
    }

@app.get("/favicon.ico")
async def favicon():
    """favicon图标"""
    from fastapi.responses import FileResponse
    return FileResponse("/root/consult/backend/favicon.ico")

@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "message": "Agent Service Platform is running (simplified mode)",
        "timestamp": datetime.now().isoformat()
    }

# 旧的工作区API已删除，使用新的RAG集成版本

# 旧的文档API已删除，使用新的RAG集成版本

# 导入全局API
from app.api.v1.endpoints.global_api import router as global_router

# 注册全局API路由
app.include_router(global_router)

# 导入WebSocket
from app.websocket.status_ws import websocket_endpoint, manager

@app.get("/api/database/content")
async def get_database_content(limit: int = 100, offset: int = 0):
    """获取全局数据库内容"""
    try:
        logger.info("[DEBUG] 前端请求全局数据库内容")
        
        # 从全局API获取文档列表
        from app.api.v1.endpoints.global_api import list_global_documents
        
        global_result = await list_global_documents()
        documents = global_result.get('documents', [])
        
        logger.info(f"[DEBUG] 全局数据库文档数量: {len(documents)}")
        
        # 转换为前端期望的格式
        formatted_documents = []
        for doc in documents:
            formatted_documents.append({
                "id": doc.get("id", ""),
                "filename": doc.get("original_filename", doc.get("filename", "")),
                "file_size": doc.get("file_size", 0),
                "file_type": doc.get("mime_type", ""),
                "status": doc.get("status", "unknown"),
                "created_at": doc.get("created_at", datetime.now().isoformat())
            })
        
        return {
            "total": len(formatted_documents),
            "limit": limit,
            "offset": offset,
            "data": formatted_documents[offset:offset + limit]
        }
        
    except Exception as e:
        logger.error(f"[DEBUG] 获取全局数据库内容失败: {e}")
        return {
            "total": 0,
            "limit": limit,
            "offset": offset,
            "data": []
        }

@app.post("/api/database/upload")
async def upload_database(file: UploadFile = File(...)):
    """上传数据库文件到全局数据库"""
    try:
        logger.info(f"[DEBUG] 全局数据库上传请求: filename={file.filename}, size={file.size}")
        
        # 检查文件类型
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        
        file_ext = os.path.splitext(file.filename)[1].lower()
        allowed_extensions = ['.pdf', '.docx', '.doc', '.txt', '.md', '.xlsx', '.xls', '.pptx', '.ppt', '.csv', '.json', '.sql', '.zip', '.rar']
        
        if file_ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file_ext}")
        
        # 检查文件大小
        content = await file.read()
        file_size = len(content)
        
        if file_size > 50 * 1024 * 1024:  # 50MB限制
            raise HTTPException(status_code=413, detail="文件大小超过限制")
        
        # 保存文件到全局数据库目录
        upload_dir = Path("uploads/global")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        file_id = str(uuid.uuid4())
        filename = f"{file_id}_{file.filename}"
        file_path = upload_dir / filename
        
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        logger.info(f"[DEBUG] 全局数据库文件保存完成: {file_path}, {file_size} bytes")
        
        # 创建异步处理任务
        from app.services.task_queue import get_task_queue, TaskStage
        
        task_queue = get_task_queue()
        task_id = task_queue.create_task(
            task_type="global_document_processing",
            metadata={
                "original_filename": file.filename,
                "file_size": file_size,
                "file_path": str(file_path),
                "file_type": file_ext,
                "upload_time": datetime.now().isoformat(),
                "source": "global_database_api"
            },
            workspace_id="global"
        )
        
        # 更新任务进度
        task_queue.update_task_progress(
            task_id=task_id,
            stage=TaskStage.UPLOADING,
            progress=100,
            message="文件上传完成"
        )
        
        # 如果是归档文件（ZIP或RAR），进行特殊处理
        if file_ext == '.zip' or file_ext == '.rar':
            archive_type = "RAR" if file_ext == '.rar' else "ZIP"
            # 启动归档文件处理任务
            asyncio.create_task(process_zip_async(task_id, str(file_path), "global"))
            
            logger.info(f"[DEBUG] 全局数据库{archive_type}任务创建成功: {task_id}")
            
            return {
                "status": "success",
                "message": f"{archive_type}文件 {file.filename} 上传到全局数据库成功，正在解压并处理",
                "task_id": task_id,
                "workspace_id": "global",
                "file_type": file_ext,
                "file_size": file_size,
                "processing_info": {
                    "note": f"{archive_type}文件正在后台解压并处理，包含多个文件"
                }
            }
        
        # 启动普通文档后台处理任务
        asyncio.create_task(process_global_document_async(task_id, str(file_path)))
        
        logger.info(f"[DEBUG] 全局数据库任务创建成功: {task_id}")
        
        # 立即返回结果
        return {
            "status": "success",
            "message": f"文档 {file.filename} 上传到全局数据库成功，正在后台处理",
            "task_id": task_id,
            "workspace_id": "global",
            "file_path": str(file_path),
            "file_size": file_size,
            "processing_info": {
                "note": "文档正在后台处理，可通过任务ID查询进度"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DEBUG] 全局数据库上传失败: {str(e)}")
        logger.error(f"[DEBUG] 文件名: {file.filename}")
        logger.error(f"[DEBUG] 文件大小: {file.size if hasattr(file, 'size') else 'unknown'}")
        import traceback
        logger.error(f"[DEBUG] 堆栈跟踪:\n{traceback.format_exc()}")
        return {
            "status": "error",
            "message": f"上传失败: {str(e)}"
        }

@app.get("/api/conversations")
async def get_conversations(workspace_id: int = None):
    """获取对话列表"""
    if workspace_id:
        return [conv for conv in conversations_db if conv["workspace_id"] == workspace_id]
    return conversations_db

@app.post("/api/conversations")
async def create_conversation(data: dict):
    """创建对话"""
    conversation = {
        "id": str(uuid.uuid4()),
        "title": data.get("title", "新对话"),
        "workspace_id": data.get("workspace_id", 1),
        "created_at": datetime.now().isoformat(),
        "message_count": 0
    }
    conversations_db.append(conversation)
    return {"message": "对话创建成功", "conversation": conversation}

@app.get("/api/agent/chat/{workspace_id}")
async def get_chat_history(workspace_id: str):
    """获取聊天历史"""
    # 简化版：返回模拟的聊天历史
    messages = [
        {
            "id": "msg_1",
            "role": "agent",
            "content": f"欢迎使用工作区 {workspace_id} 的Agent服务。我可以帮助您分析文档、回答问题和执行各种任务。",
            "timestamp": "2024-01-01T10:00:00Z"
        }
    ]

    # 获取工作区的可用操作
    actions = [
        {"id": "data_analysis", "name": "数据分析", "description": "分析工作区中的数据文件"},
        {"id": "report_generation", "name": "报告生成", "description": "生成分析报告"},
        {"id": "file_processing", "name": "文件处理", "description": "处理上传的文件"}
    ]

    # 获取可下载的文件
    workspace_files = [doc for doc in documents_db if str(doc["workspace_id"]) == workspace_id]
    files = [
        {
            "id": doc["id"],
            "name": doc["original_filename"],
            "size": f"{doc['file_size']} bytes",
            "date": doc["created_at"]
        }
        for doc in workspace_files[:5]  # 只显示最近5个文件
    ]

    return {
        "messages": messages,
        "files": files,
        "actions": actions
    }

@app.post("/api/chat/langgraph")
async def chat_with_langgraph(data: dict):
    """LangGraph 智能 RAG API"""
    try:
        question = data.get("question") or data.get("message", "")
        workspace_id = data.get("workspace_id") or data.get("workspaceId", "global")
        
        # 导入新组件
        from app.services.llamaindex_retriever import LlamaIndexRetriever
        from app.workflows.langgraph_rag_workflow import LangGraphRAGWorkflow
        
        # 获取或创建检索器
        workspace_retriever = LlamaIndexRetriever.get_instance(workspace_id)
        global_retriever = LlamaIndexRetriever.get_instance("global")
        
        # 获取 LLM
        from app.services.langchain_rag_service import LangChainRAGService
        rag_service = LangChainRAGService(vector_db_path="langchain_vector_db")
        
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
    except Exception as e:
        logger.error(f"LangGraph 查询失败: {e}")
        return {
            "answer": f"抱歉，处理您的问题时出现错误: {str(e)}",
            "sources": [],
            "metadata": {"error": str(e)}
        }

@app.post("/api/document/generate-deepresearch")
async def generate_deepresearch_document(data: dict):
    """DeepResearch 风格长文档生成 API"""
    try:
        task_description = data.get("task_description", "")
        workspace_id = data.get("workspace_id", "global")
        doc_requirements = data.get("doc_requirements", {
            "target_words": 5000,
            "writing_style": "专业、严谨、客观"
        })
        
        # 导入新组件
        from app.services.llamaindex_retriever import LlamaIndexRetriever
        from app.workflows.deepresearch_doc_workflow import DeepResearchDocWorkflow
        from app.services.web_search_service import get_web_search_service
        
        # 获取或创建检索器
        workspace_retriever = LlamaIndexRetriever.get_instance(workspace_id)
        global_retriever = LlamaIndexRetriever.get_instance("global")
        
        # 获取 LLM 和网络搜索服务
        from app.services.langchain_rag_service import LangChainRAGService
        rag_service = LangChainRAGService(vector_db_path="langchain_vector_db")
        web_search_service = get_web_search_service()
        
        # 创建文档生成工作流
        workflow = DeepResearchDocWorkflow(
            workspace_retriever=workspace_retriever,
            global_retriever=global_retriever,
            web_search_service=web_search_service,
            llm=rag_service.llm
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
    except Exception as e:
        logger.error(f"DeepResearch 文档生成失败: {e}")
        return {
            "document": f"抱歉，文档生成失败: {str(e)}",
            "quality_metrics": {},
            "references": [],
            "过程中的错误": str(e)
        }

@app.post("/api/agent/chat")
async def ask_question(data: dict):
    """统一代理到 LangGraph + LlamaIndex 实现"""
    try:
        return await chat_with_langgraph(data)
    except Exception as e:
        logger.error(f"/api/agent/chat 处理失败: {e}")
        return {
            "answer": f"抱歉，处理您的问题时出现错误: {str(e)}",
            "sources": [],
            "metadata": {"error": str(e)}
        }

    # 旧实现保留在下方，但已不再执行（上方已返回）。
    question = data.get("question") or data.get("message", "")
    workspace_id = data.get("workspace_id") or data.get("workspaceId", "1")
    conversation_history = data.get("history", [])
    enable_web_search = data.get("enable_web_search", False)

    try:
        print("=== 开始处理请求 ===")
        print(f"问题: {question}")
        print(f"工作区: {workspace_id}")
        print(f"联网搜索: {enable_web_search}")
        
        # 1. 意图识别
        print("=== 开始意图识别 ===")
        from app.services.intent_classifier import IntentClassifier
        from app.services.content_aggregator import ContentAggregator
        from app.services.document_generator_service import DocumentGeneratorService, DocumentType
        from app.services.workspace_file_manager import WorkspaceFileManager
        from app.workflows.workflow_orchestrator import WorkflowOrchestrator
        
        # 使用LangChain RAG服务 - 使用正确的路径
        from app.services.langchain_rag_service import LangChainRAGService
        # 使用langchain_vector_db作为基础路径，以支持工作区查询
        rag_service = LangChainRAGService(vector_db_path="langchain_vector_db")
        
        # 初始化意图分类器
        intent_classifier = IntentClassifier(rag_service.llm)
        
        intent = await intent_classifier.classify_intent(question, conversation_history)
        
        print(f"意图识别结果: {intent.is_generation_intent}, 类型: {intent.doc_type.value}, 置信度: {intent.confidence}")
        print("=== 意图识别完成 ===")
        
        # 如果是普通问答，直接返回答案
        if not intent.is_generation_intent:
            # 使用RAG服务进行问答
            response_data = await rag_service.search_and_answer(question, workspace_id, conversation_history)
            return {
                "answer": response_data.get('answer', ''),
                "intent_detected": False,
                "metadata": {
                    "workflow_type": "simple_qa",
                    "current_step": "completed",
                    "intent_type": "qa"
                },
                "references": response_data.get('references', [])
            }
        
        # 2. 如果是文件生成意图
        if intent.is_generation_intent:
            # 2.1 需要确认？
            confirm_generation = data.get("confirm_generation", False)
            if intent.needs_confirmation and not confirm_generation:
                return {
                    "answer": intent.confirmation_message,
                    "intent_detected": True,
                    "intent_type": "file_generation",
                    "pending_confirmation": True,
                    "suggested_params": intent.extracted_params
                }
            
            # 2.2 使用生产级 Agent 工作流
            print("=== 开始生产级 Agent 工作流处理 ===")
            
            try:
                # 检查 LLM 是否可用
                if not rag_service.llm:
                    raise ValueError("LLM不可用：请配置OPENAI_API_KEY或THIRD_PARTY_API环境变量")
                
                from app.workflows.production_workflow import ProductionWorkflow
                
                # 初始化生产工作流
                production_workflow = ProductionWorkflow(
                    llm=rag_service.llm,
                    rag_service=rag_service,
                    web_search_service=None  # 暂时不使用网络搜索
                )
                
                # 执行生产工作流
                workflow_result = await production_workflow.execute(
                    user_request=question,
                    workspace_id=workspace_id,
                    conversation_history=conversation_history
                )
                
                # 转换结果格式以适配现有返回结构
                if workflow_result.get('success'):
                    workflow_result['workflow_type'] = 'production_agent'
                    workflow_result['complexity_analysis'] = {
                        'complexity': 'complex',
                        'estimated_time': 60
                    }
            except Exception as production_error:
                print(f"生产工作流失败: {production_error}")
                # 回退到旧的工作流
                from app.services.web_search_service import get_web_search_service
                web_search_service = get_web_search_service()
                
                workflow_orchestrator = WorkflowOrchestrator(
                    rag_service.llm, 
                    rag_service, 
                    web_search_service
                )
                
                requirements = {
                    "doc_type": intent.doc_type.value,
                    "enable_web_search": enable_web_search,
                    "workspace_id": workspace_id,
                    "conversation_history": conversation_history,
                    "intent_params": intent.extracted_params
                }
                
                workflow_result = await workflow_orchestrator.execute_task(question, requirements)
            
            print(f"工作流执行完成: {workflow_result.get('success', False)}")
            print(f"使用工作流类型: {workflow_result.get('workflow_type', 'unknown')}")
            
            # 统一返回格式，包含完整的进度信息
            result_metadata = {
                "workflow_type": workflow_result.get('workflow_type', 'simple'),
                "current_step": workflow_result.get('current_step', 'completed'),
                "workflow_success": workflow_result.get('success', False),
                "quality_score": workflow_result.get('quality_score'),
                "complexity_analysis": workflow_result.get('complexity_analysis')
            }
            
            if workflow_result.get('success', False):
                # 2.3 处理工作流结果
                final_result = workflow_result.get('result', {})
                
                # 如果是简单工作流，使用原有逻辑
                if workflow_result.get('workflow_type') == 'simple':
                    aggregated_content = final_result.get('aggregated_content')
                    doc_result = final_result.get('result', {})
                    
                    if doc_result.get('success'):
                        file_manager = WorkspaceFileManager()
                        file_id = file_manager.save_generated_file(
                            workspace_id,
                            doc_result['file_path'],
                            {
                                'doc_type': doc_result['doc_type'],
                                'title': aggregated_content.title if aggregated_content else question[:50],
                                'source_query': question,
                                'references': aggregated_content.references if aggregated_content else []
                            }
                        )
                        
                        # 获取文档类型显示名称
                        doc_type_map = {
                            "word": "Word文档",
                            "excel": "Excel表格", 
                            "ppt": "PPT演示文稿",
                            "pdf": "PDF文档"
                        }
                        doc_type_display = doc_type_map.get(intent.doc_type.value, "文档")
                        
                        return {
                            "answer": f"已为您生成{doc_type_display}：{aggregated_content.title if aggregated_content else '文档'}",
                            "file_generated": True,
                            "file_info": {
                                "file_id": file_id,
                                "filename": doc_result['filename'],
                                "file_type": doc_result['doc_type'],
                                "file_size": doc_result['file_size'],
                                "download_url": f"/api/workspace/{workspace_id}/files/{file_id}/download"
                            },
                            "references": aggregated_content.references if aggregated_content else [],
                            "intent_detected": True,
                            "intent_type": "file_generation",
                            "metadata": result_metadata,
                            "workflow_type": workflow_result.get('workflow_type'),
                            "workflow_details": workflow_result.get('complexity_analysis', {})
                        }
                
                # 其他工作流类型的结果处理
                else:
                    # 从工作流结果中提取文档内容
                    final_document = None
                    workflow_type = workflow_result.get('workflow_type', 'unknown')
                    
                    if workflow_type in ['plan_execute', 'plan_and_execute']:
                        # Plan-and-Execute工作流的结果处理
                        execution_result = final_result.get('execution_result', {})
                        step_results = execution_result.get('step_results', {})
                        
                        # 查找生成步骤的结果（优先generate，其次analyze）
                        for step_id, step_result in step_results.items():
                            if isinstance(step_result, dict):
                                action_type = step_result.get('action_type')
                                if action_type == 'generate':
                                    final_document = {
                                        'content': step_result.get('content', ''),
                                        'title': question[:50],
                                        'format': step_result.get('format', 'word')
                                    }
                                    break
                                elif action_type == 'analyze' and not final_document:
                                    # 如果没有generate，使用analyze的结果
                                    analysis = step_result.get('analysis', '')
                                    if analysis:
                                        final_document = {
                                            'content': analysis,
                                            'title': question[:50],
                                            'format': 'word'
                                        }
                    
                    elif 'final_document' in final_result:
                        final_document = final_result['final_document']
                    elif 'final_state' in final_result:
                        final_document = final_result['final_state'].get('final_document', {})
                    
                    if final_document and final_document.get('content'):
                        # 生成文档文件
                        doc_generator = DocumentGeneratorService()
                        doc_result = doc_generator.generate_document(
                            final_document['content'],
                            DocumentType(intent.doc_type.value)
                        )
                        
                        if doc_result.get('success'):
                            file_manager = WorkspaceFileManager()
                            file_id = file_manager.save_generated_file(
                                workspace_id,
                                doc_result['file_path'],
                                {
                                    'doc_type': doc_result['doc_type'],
                                    'title': final_document.get('title', question[:50]),
                                    'source_query': question,
                                    'references': []
                                }
                            )
                            
                            # 获取文档类型显示名称
                            doc_type_map = {
                                "word": "Word文档",
                                "excel": "Excel表格", 
                                "ppt": "PPT演示文稿",
                                "pdf": "PDF文档"
                            }
                            doc_type_display = doc_type_map.get(intent.doc_type.value, "文档")
                            
                            return {
                                "answer": f"已为您生成{doc_type_display}：{final_document.get('title', '文档')}",
                                "file_generated": True,
                                "file_info": {
                                    "file_id": file_id,
                                    "filename": doc_result['filename'],
                                    "file_type": doc_result['doc_type'],
                                    "file_size": doc_result['file_size'],
                                    "download_url": f"/api/workspace/{workspace_id}/files/{file_id}/download"
                                },
                                "references": [],
                                "intent_detected": True,
                                "intent_type": "file_generation",
                                "metadata": result_metadata,
                                "workflow_type": workflow_result.get('workflow_type'),
                                "workflow_details": workflow_result.get('complexity_analysis', {}),
                                "quality_score": final_document.get('quality_score', 0)
                            }
            
            # 工作流执行失败
            return {
                "answer": f"文档生成失败：{workflow_result.get('error', '工作流执行失败')}",
                "file_generated": False,
                "intent_detected": True,
                "intent_type": "file_generation",
                "metadata": result_metadata,
                "workflow_type": workflow_result.get('workflow_type'),
                "error": workflow_result.get('error')
            }
        
        # 3. 普通对话流程（现有逻辑）
        
        # 处理对话历史
        history_context = ""
        if conversation_history:
            history_lines = []
            # 只保留最近10条对话
            recent_history = conversation_history[-10:] if len(conversation_history) > 10 else conversation_history
            for msg in recent_history:
                role_name = "用户" if msg.get('role') == 'user' else "AI助手"
                history_lines.append(f"{role_name}: {msg.get('content', '')}")
            history_context = "\n".join(history_lines)
            print(f"对话历史: {len(recent_history)} 条消息")
        
        # 构建增强问题（包含历史上下文）
        enhanced_question = question
        if history_context:
            enhanced_question = f"{question}"  # 历史将在提示模板中单独处理
        
        # 检查工作区和全局数据库状态
        workspace_stats = rag_service.get_workspace_stats(workspace_id)
        global_stats = rag_service.get_workspace_stats("global")
        
        print(f"工作区状态: {workspace_stats}")
        print(f"全局数据库状态: {global_stats}")
        
        workspace_has_docs = workspace_stats.get('document_count', 0) > 0
        global_has_docs = global_stats.get('document_count', 0) > 0
        
        # 如果全局数据库状态检查失败，直接检查文件索引
        if not global_has_docs:
            try:
                from app.services.file_index_manager import file_index_manager
                global_file_count = file_index_manager.get_file_count()
                global_has_docs = global_file_count > 0
                print(f"通过文件索引检查全局数据库: {global_file_count} 个文件")
            except Exception as e:
                print(f"文件索引检查失败: {str(e)}")
        
        if not workspace_has_docs and not global_has_docs:
            print("工作区和全局数据库都没有文档，使用通用知识回答")
            raise Exception("没有可用文档")
        
        # 混合检索：检索工作区和全局数据库
        workspace_results = []
        global_results = []
        
        # 检索工作区文档
        if workspace_has_docs:
            print(f"正在检索工作区文档...")
            try:
                workspace_response = await rag_service.ask_question(
                    workspace_id=str(workspace_id),
                    question=enhanced_question,
                    top_k=5
                )
                print(f"工作区检索完成，找到 {len(workspace_response.get('references', []))} 个相关文档")
                
                # 标记来源
                for i, ref in enumerate(workspace_response.get('references', [])):
                    ref['source_type'] = 'workspace'
                    ref['workspace_id'] = workspace_id
                    ref['rank'] = i + 1
                    ref['chunk_id'] = ref.get('metadata', {}).get('file_path', f'workspace_chunk_{i}')
                    workspace_results.append(ref)
                
            except Exception as e:
                print(f"工作区检索失败: {str(e)}")
        else:
            print(f"工作区 {workspace_id} 没有文档，跳过工作区检索")
        
        # 检索全局数据库文档
        if global_has_docs:
            print(f"正在检索全局数据库文档...")
            try:
                global_response = await rag_service.ask_question(
                    workspace_id="global",
                    question=enhanced_question,
                    top_k=5
                )
                print(f"全局数据库检索完成，找到 {len(global_response.get('references', []))} 个相关文档")
                
                # 标记来源
                for i, ref in enumerate(global_response.get('references', [])):
                    ref['source_type'] = 'global'
                    ref['workspace_id'] = 'global'
                    ref['rank'] = i + 1
                    ref['chunk_id'] = ref.get('metadata', {}).get('file_path', f'global_chunk_{i}')
                    global_results.append(ref)
                
            except Exception as e:
                print(f"全局数据库检索失败: {str(e)}")
        
        # 如果没有找到任何相关文档
        if not workspace_results and not global_results:
            print("没有找到相关文档，使用通用知识回答")
            raise Exception("没有找到相关文档")
        
        # 合并所有检索结果
        all_references = workspace_results + global_results
        final_references = all_references[:5]  # 限制为5个最相关的
        
        print(f"混合检索完成，共找到 {len(final_references)} 个相关文档")
        print(f"工作区文档: {len([r for r in final_references if r.get('source_type') == 'workspace'])}")
        print(f"全局数据库文档: {len([r for r in final_references if r.get('source_type') == 'global'])}")
        
        # 使用LangChain生成答案（无max_tokens限制）
        from langchain.schema import Document
        from langchain.prompts import PromptTemplate
        from langchain.chains.combine_documents import create_stuff_documents_chain
        
        # 将检索结果转换为LangChain Document对象
        context_docs = []
        for ref in final_references:
            # 优先使用完整的content_preview，如果被截断则尝试从metadata中获取完整内容
            content = ref.get('content_preview', '')
            if content.endswith('...') and len(content) <= 203:  # 被截断的内容
                # 尝试从metadata中获取完整内容
                metadata = ref.get('metadata', {})
                if 'file_path' in metadata:
                    # 重新从向量存储中获取完整内容
                    try:
                        vector_store = rag_service._load_vector_store(ref.get('workspace_id', 'global'))
                        if vector_store and hasattr(vector_store, 'docstore'):
                            docstore = vector_store.docstore
                            if hasattr(docstore, '_dict'):
                                # 查找匹配的文档
                                for doc_id, doc in docstore._dict.items():
                                    if (doc.metadata.get('original_filename') == metadata.get('original_filename') and 
                                        doc.metadata.get('processing_method') == metadata.get('processing_method')):
                                        content = doc.page_content
                                        break
                    except Exception as e:
                        print(f"获取完整内容失败: {e}")
            
            doc = Document(
                page_content=content,
                metadata={
                    'source_type': ref.get('source_type'),
                    'workspace_id': ref.get('workspace_id'),
                    'original_filename': ref.get('metadata', {}).get('original_filename', '未知文档'),
                    **ref.get('metadata', {})
                }
            )
            context_docs.append(doc)
        
        # 检查LLM是否可用
        if rag_service.llm is None:
            print("LLM不可用，使用简化回答")
            raise Exception("LLM服务不可用")
        
        # 创建提示模板（包含对话历史）
        if history_context:
            prompt_template = """你是一个智能助手。请根据以下信息回答问题。

对话历史：
{history}

检索到的文档内容：
{context}

当前问题：{input}

回答规则：
1. 综合考虑对话历史和检索到的文档内容
2. 优先使用文档内容回答，如果文档不足可以使用通用知识
3. 如果问题涉及之前的对话，请结合历史上下文回答
4. 标注信息来源（工作区文档或全局文档）

请提供准确、详细的回答："""
        else:
            prompt_template = """你是一个智能助手。请根据以下检索到的文档内容回答问题。

检索到的文档内容：
{context}

问题：{input}

回答规则：
1. 优先使用文档内容回答
2. 如果文档内容不足，可以使用通用知识
3. 标注信息来源（工作区文档或全局文档）

请提供准确、详细的回答："""
        
        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["history", "context", "input"] if history_context else ["context", "input"]
        )
        
        # 创建文档链
        document_chain = create_stuff_documents_chain(rag_service.llm, prompt)
        
        # 执行生成
        if history_context:
            response = await document_chain.ainvoke({
                "history": history_context,
                "context": context_docs,
                "input": question
            })
        else:
            response = await document_chain.ainvoke({
                "context": context_docs,
                "input": question
            })
        
        # 提取答案
        answer = response if isinstance(response, str) else str(response)
        
        return {
            "answer": answer,
            "references": final_references,
            "confidence": 0.9,
            "metadata": {
                "model": "gpt-3.5-turbo",
                "mode": "hybrid_langchain_rag",
                "retrieved_chunks": len(final_references),
                "workspace_docs": len([r for r in final_references if r.get('source_type') == 'workspace']),
                "global_docs": len([r for r in final_references if r.get('source_type') == 'global']),
                "has_history": len(conversation_history) > 0,
                "history_length": len(conversation_history)
            }
        }

    except Exception as e:
        # 如果QA服务失败，尝试使用LLM直接回答
        logger.error(f"RAG服务失败，尝试直接LLM回答: {str(e)}")
        logger.error(f"问题: {question}")
        logger.error(f"工作区: {workspace_id}")
        import traceback
        logger.error(f"详细错误信息:\n{traceback.format_exc()}")
        
        try:
            from app.services.llm_service import LLMService
            llm_service = LLMService()

            if llm_service.get_available_providers():
                # 有可用的LLM服务，直接回答问题
                messages = [
                    {"role": "system", "content": "你是一个专业的AI助手，请简洁地回答用户问题。"},
                    {"role": "user", "content": question}
                ]

                llm_response = await llm_service.chat(
                    messages=messages,
                    provider="third_party",
                    model="gpt-3.5-turbo",
                    max_tokens=500
                )

                return {
                    "answer": llm_response["content"],
                    "references": [],
                    "sources": [],
                    "confidence": 0.8,
                    "metadata": {
                        "model": llm_response.get("model", "unknown"),
                        "mode": "direct_llm",
                        "retrieved_chunks": 0,
                        "note": "当前工作区没有文档，使用通用知识回答"
                    }
                }
            else:
                raise Exception("No LLM service available")
        except Exception as llm_error:
            print(f"LLM服务也失败: {str(llm_error)}")
            
            # 最后的回退方案
            answer = f"抱歉，当前工作区没有相关文档，我无法基于文档内容回答您的问题「{question}」。请先上传相关文档，然后我就能为您提供基于文档的智能回答了。"

            return {
                "answer": answer,
                "references": [],
                "sources": [],
                "confidence": 0.3,
                "metadata": {
                    "model": "fallback",
                    "mode": "no_documents",
                    "error": str(e),
                    "suggestion": "请上传相关文档到当前工作区"
                }
            }

@app.get("/api/agent/workspace/{workspace_id}/status")
async def get_workspace_status(workspace_id: str):
    """获取工作区状态"""
    try:
        from app.services.langchain_rag_service import LangChainRAGService
        
        rag_service = LangChainRAGService()
        stats = rag_service.get_workspace_stats(workspace_id)
        
        return {
            "workspace_id": workspace_id,
            "status": stats.get("status", "empty"),
            "document_count": stats.get("document_count", 0),
            "rag_available": stats.get("document_count", 0) > 0,
            "retrieval_methods": stats.get("retrieval_methods", {}),
            "config": stats.get("config", {}),
            "message": "工作区有文档，支持高级RAG问答" if stats.get("document_count", 0) > 0 else "工作区为空，将使用通用知识回答"
        }
    except Exception as e:
        return {
            "workspace_id": workspace_id,
            "status": "error",
            "document_count": 0,
            "rag_available": False,
            "error": str(e)
        }

@app.get("/api/agent/actions/{workspace_id}")
async def get_available_actions(workspace_id: str):
    """获取可用的应用操作"""
    return {
        "actions": [
            {"id": "data_analysis", "name": "数据分析", "description": "分析工作区中的数据文件"},
            {"id": "report_generation", "name": "报告生成", "description": "生成分析报告"},
            {"id": "file_processing", "name": "文件处理", "description": "处理上传的文件"}
        ]
    }

@app.post("/api/agent/upload-document")
async def upload_document_for_rag(
    file: UploadFile = File(...),
    workspace_id: int = 1,
    enable_ocr: bool = True,
    extract_tables: bool = True,
    extract_images: bool = True
):
    """上传文档到RAG系统（切换为 LlamaIndex 导入并持久化）"""
    try:
        from app.services.llamaindex_retriever import LlamaIndexRetriever
        
        # 保存上传的文件
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        
        file_path = upload_dir / f"{uuid.uuid4()}_{file.filename}"
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # 使用 LlamaIndex 导入并持久化
        retriever = LlamaIndexRetriever.get_instance(str(workspace_id))
        added = await retriever.add_document(
            file_path=str(file_path),
            metadata={
                "original_filename": file.filename,
                "file_size": len(content),
                "upload_time": datetime.now().isoformat(),
                "enable_ocr": enable_ocr,
                "extract_tables": extract_tables,
                "extract_images": extract_images
            }
        )
        # 持久化到 llamaindex_storage/<workspace_id>
        retriever.index.storage_context.persist(persist_dir=str(retriever.storage_dir))
        
        if added:
            return {
                "status": "success",
                "message": f"文档 {file.filename} 已成功添加到RAG系统",
                "workspace_id": workspace_id,
                "file_path": str(file_path),
                "processing_info": {
                    "note": "文档处理成功"
                }
            }
        else:
            return {
                "status": "error",
                "message": f"文档 {file.filename} 添加失败"
            }
            
    except Exception as e:
        logger.error(f"文档上传失败: {str(e)}")
        return {
            "status": "error",
            "message": f"上传失败: {str(e)}"
        }

# 文档管理API端点
@app.post("/api/documents/upload")
async def upload_document_api(
    file: UploadFile = File(...),
    workspace_id: str = Form("1")
):
    """文档上传API - 前端调用（异步处理）[已禁用]"""
    raise HTTPException(
        status_code=410, 
        detail="此接口已禁用，请使用 /api/database/upload 或 /api/workspaces/{workspace_id}/documents/upload"
    )

async def process_document_async(task_id: str, file_path: str, workspace_id: str):
    """异步处理文档"""
    from app.services.task_queue import get_task_queue, TaskStage
    from app.services.langchain_rag_service import LangChainRAGService
    
    task_queue = get_task_queue()
    
    try:
        logger.info(f"[DEBUG] 开始异步处理文档: {task_id}")
        
        # 更新进度：开始解析
        task_queue.update_task_progress(
            task_id=task_id,
            stage=TaskStage.PARSING,
            progress=10,
            message="开始解析文档"
        )
        
        # 初始化RAG服务
        rag_service = LangChainRAGService()
        
        # 更新进度：解析中
        task_queue.update_task_progress(
            task_id=task_id,
            stage=TaskStage.PARSING,
            progress=30,
            message="正在解析文档内容"
        )
        
        # 获取任务元数据
        task = task_queue.get_task(task_id)
        task_metadata = task.metadata if task else {}
        original_filename = task_metadata.get('original_filename', Path(file_path).name)
        
        # 使用 LlamaIndex 导入并持久化
        from app.services.llamaindex_retriever import LlamaIndexRetriever
        retriever_async = LlamaIndexRetriever.get_instance(workspace_id)
        logger.info(f"LlamaIndexRetriever创建完成")
        added_cnt = await retriever_async.add_document(
            file_path=file_path,
            metadata={
                "task_id": task_id,
                "original_filename": original_filename,
                "file_size": Path(file_path).stat().st_size,
                "upload_time": datetime.now().isoformat(),
                "source": "async_processing"
            }
        )
        retriever_async.index.storage_context.persist(persist_dir=str(retriever_async.storage_dir))
        success = bool(added_cnt)
        
        if success:
            # 统计新增节点数（LlamaIndex 返回值）
            chunk_count = int(added_cnt) if added_cnt else 0
            
            # 保存到JSON文件（全局和工作区都保存）
            try:
                doc_id = str(uuid.uuid4())
                document_data = {
                    'id': doc_id,
                    'filename': Path(file_path).name,
                    'original_filename': original_filename,
                    'file_size': Path(file_path).stat().st_size,
                    'file_path': file_path,
                    'status': 'completed',
                    'created_at': datetime.now().isoformat(),
                    'processing_started': datetime.now().isoformat(),
                    'processing_completed': datetime.now().isoformat(),
                    'chunk_count': chunk_count,
                    'quality_score': 0.8
                }
                
                if workspace_id == "global":
                    # 保存到全局JSON
                    from app.api.v1.endpoints.global_api import load_global_documents, save_global_documents
                    
                    documents = load_global_documents()
                    documents.append(document_data)
                    save_global_documents(documents)
                    logger.info(f"[DEBUG] 已保存全局文档记录到JSON")
                else:
                    # 保存到工作区JSON
                    from app.services.workspace_document_manager import add_workspace_document
                    
                    add_workspace_document(workspace_id, document_data)
                    logger.info(f"[DEBUG] 已保存工作区文档记录到JSON: {workspace_id}")
            except Exception as json_error:
                logger.warning(f"[DEBUG] 保存到JSON失败: {json_error}")
                import traceback
                logger.error(f"[DEBUG] 详细错误: {traceback.format_exc()}")
            
            # 更新进度：完成
            task_queue.update_task_progress(
                task_id=task_id,
                stage=TaskStage.INDEXING,
                progress=100,
                message="文档处理完成"
            )
            task_queue.complete_task(task_id, {"success": True})
            logger.info(f"[DEBUG] 文档处理成功: {task_id}")
        else:
            task_queue.fail_task(task_id, "RAG系统添加文档失败")
            logger.error(f"[DEBUG] 文档处理失败: {task_id}")
            
    except Exception as e:
        task_queue.fail_task(task_id, str(e))
        logger.error(f"[DEBUG] 异步处理异常: {task_id} - {str(e)}")
        logger.error(f"[DEBUG] 文件路径: {file_path}")
        logger.error(f"[DEBUG] 工作区: {workspace_id}")
        import traceback
        logger.error(f"[DEBUG] 堆栈跟踪:\n{traceback.format_exc()}")

async def process_global_document_async(task_id: str, file_path: str):
    """异步处理全局文档"""
    from app.services.task_queue import get_task_queue, TaskStage
    from app.services.langchain_rag_service import LangChainRAGService
    
    task_queue = get_task_queue()
    
    try:
        logger.info(f"[DEBUG] 开始异步处理全局文档: {task_id}")
        
        # 更新进度：开始解析
        task_queue.update_task_progress(
            task_id=task_id,
            stage=TaskStage.PARSING,
            progress=10,
            message="开始解析全局文档"
        )
        
        # 初始化RAG服务
        rag_service = LangChainRAGService()
        
        # 更新进度：解析中
        task_queue.update_task_progress(
            task_id=task_id,
            stage=TaskStage.PARSING,
            progress=30,
            message="正在解析全局文档内容"
        )
        
        # 添加到全局RAG系统
        from app.services.llamaindex_retriever import LlamaIndexRetriever
        retriever_global = LlamaIndexRetriever.get_instance("global")
        added_cnt = await retriever_global.add_document(
            file_path=file_path,
            metadata={
                "task_id": task_id,
                "original_filename": Path(file_path).name,
                "file_size": Path(file_path).stat().st_size,
                "upload_time": datetime.now().isoformat(),
                "source": "global_async_processing"
            }
        )
        retriever_global.index.storage_context.persist(persist_dir=str(retriever_global.storage_dir))
        success = bool(added_cnt)
        
        if success:
            # 更新进度：完成
            task_queue.update_task_progress(
                task_id=task_id,
                stage=TaskStage.INDEXING,
                progress=100,
                message="全局文档处理完成"
            )
            task_queue.complete_task(task_id, {"success": True})
            logger.info(f"[DEBUG] 全局文档处理成功: {task_id}")
        else:
            task_queue.fail_task(task_id, "全局RAG系统添加文档失败")
            logger.error(f"[DEBUG] 全局文档处理失败: {task_id}")
            
    except Exception as e:
        task_queue.fail_task(task_id, str(e))
        logger.error(f"[DEBUG] 全局异步处理异常: {task_id} - {str(e)}")
        logger.error(f"[DEBUG] 文件路径: {file_path}")
        import traceback
        logger.error(f"[DEBUG] 堆栈跟踪:\n{traceback.format_exc()}")

async def process_zip_async(task_id: str, zip_path: str, workspace_id: str = "global"):
    """异步处理ZIP文件"""
    from app.services.task_queue import get_task_queue, TaskStage
    from app.services.langchain_rag_service import LangChainRAGService
    from app.services.zip_processor import ZipProcessor
    import tempfile
    
    task_queue = get_task_queue()
    extract_dir = None
    
    try:
        logger.info(f"[ZIP] 开始处理ZIP文件: {zip_path}")
        
        # 阶段1: 解压ZIP文件
        task_queue.update_task_progress(
            task_id=task_id,
            stage=TaskStage.UPLOADING,
            progress=10,
            message="ZIP文件上传完成，开始解压"
        )
        
        # 创建临时解压目录
        extract_dir = tempfile.mkdtemp(prefix=f"zip_extract_{task_id}_")
        logger.info(f"[ZIP] 临时解压目录: {extract_dir}")
        
        # 解压归档文件（ZIP或RAR）
        extracted_files = await ZipProcessor.extract_archive(zip_path, extract_dir)
        
        if not extracted_files:
            task_queue.fail_task(task_id, "ZIP文件中没有找到支持的文件")
            return
        
        # 阶段2: 更新进度
        task_queue.update_task_progress(
            task_id=task_id,
            stage=TaskStage.PARSING,
            progress=20,
            message=f"已解压 {len(extracted_files)} 个文件，开始并行处理"
        )
        
        # 阶段3: 并行处理文件
        rag_service = LangChainRAGService()
        
        total_files = len(extracted_files)
        results = []
        
        # 使用并行处理
        async def process_single_file(file_info: dict, index: int):
            """处理单个文件"""
            try:
                logger.info(f"[ZIP] 处理文件 ({index+1}/{total_files}): {file_info['original_filename']}")
                
                # 使用 LlamaIndex 导入
                from app.services.llamaindex_retriever import LlamaIndexRetriever
                zip_retriever = LlamaIndexRetriever.get_instance(workspace_id)
                added_cnt = await zip_retriever.add_document(
                    file_path=file_info['file_path'],
                    metadata={
                        "task_id": task_id,
                        "original_filename": file_info['original_filename'],
                        "file_size": file_info['file_size'],
                        "upload_time": datetime.now().isoformat(),
                        "source": "zip_batch_processing",
                        "zip_file": Path(zip_path).name,
                        "file_type": file_info['file_type']
                    }
                )
                zip_retriever.index.storage_context.persist(persist_dir=str(zip_retriever.storage_dir))
                success = bool(added_cnt)
                
                # 为每个内部文件生成唯一ID（用于后续保存到JSON）
                internal_file_id = str(uuid.uuid4())
                
                return {
                    "filename": file_info['original_filename'],
                    "success": success,
                    "file_type": file_info['file_type'],
                    "file_id": internal_file_id if success else None,
                    "file_info": file_info if success else None
                }
            except Exception as e:
                logger.error(f"[ZIP] 处理文件失败: {file_info['original_filename']}, 错误: {e}")
                return {
                    "filename": file_info['original_filename'],
                    "success": False,
                    "error": str(e),
                    "file_id": None,
                    "file_info": None
                }
        
        # 并发处理所有文件（限制并发数为5）
        semaphore = asyncio.Semaphore(5)
        
        async def process_with_semaphore(file_info, index):
            async with semaphore:
                return await process_single_file(file_info, index)
        
        # 创建所有任务
        tasks = [process_with_semaphore(file_info, idx) for idx, file_info in enumerate(extracted_files)]
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks)
        
        # 统计结果
        successful = sum(1 for r in results if r['success'])
        failed = total_files - successful
        
        # 批量保存成功的文件到JSON（全局和工作区都保存）
        if successful > 0:
            try:
                from app.services.workspace_document_manager import add_workspace_document
                
                if workspace_id == "global":
                    # 全局数据库
                    from app.api.v1.endpoints.global_api import load_global_documents, save_global_documents
                    
                    # 加载现有文档
                    documents = load_global_documents()
                else:
                    documents = []
                
                # 为每个成功处理的文件创建记录
                for result in results:
                    if result['success'] and result.get('file_id'):
                        file_info = result.get('file_info', {})
                        # 获取chunks数量
                        chunk_count = file_info.get('chunk_count', 0)
                        
                        internal_document = {
                            'id': result['file_id'],
                            'filename': result['filename'],
                            'original_filename': result['filename'],
                            'file_size': file_info.get('file_size', 0),
                            'file_path': file_info.get('file_path', ''),
                            'file_type': result.get('file_type', ''),
                            'status': 'completed',
                            'created_at': datetime.now().isoformat(),
                            'processing_started': datetime.now().isoformat(),
                            'processing_completed': datetime.now().isoformat(),
                            'chunk_count': chunk_count,
                            'quality_score': 0.8,
                            'is_archive': False,
                            'source_archive': Path(zip_path).name
                        }
                        
                        # 根据工作区类型保存
                        if workspace_id == "global":
                            documents.append(internal_document)
                        else:
                            # 保存到工作区JSON
                            add_workspace_document(workspace_id, internal_document)
                
                # 如果是全局数据库，批量保存所有文档
                if workspace_id == "global":
                    save_global_documents(documents)
                    logger.info(f"[ZIP] 已批量保存 {successful} 个内部文件记录到全局JSON")
                else:
                    logger.info(f"[ZIP] 已保存 {successful} 个内部文件记录到工作区 {workspace_id} JSON")
            except Exception as json_error:
                logger.warning(f"[ZIP] 批量保存到JSON失败: {json_error}")
                import traceback
                logger.error(f"[ZIP] 详细错误: {traceback.format_exc()}")
        
        # 阶段4: 清理临时文件
        try:
            if extract_dir:
                await ZipProcessor.cleanup_extracted_files(extract_dir)
                logger.info(f"[ZIP] 临时文件已清理: {extract_dir}")
        except Exception as e:
            logger.warning(f"[ZIP] 清理临时文件失败: {e}")
        
        # 阶段5: 完成任务
        if successful > 0:
            task_queue.update_task_progress(
                task_id=task_id,
                stage=TaskStage.INDEXING,
                progress=100,
                message=f"处理完成: 成功 {successful}/{total_files}"
            )
            task_queue.complete_task(task_id, {
                "success": True,
                "total_files": total_files,
                "successful": successful,
                "failed": failed,
                "results": results
            })
            logger.info(f"[ZIP] ZIP文件处理完成: 成功 {successful}/{total_files}")
        else:
            task_queue.fail_task(task_id, "所有文件处理失败")
            
    except Exception as e:
        task_queue.fail_task(task_id, str(e))
        logger.error(f"[ZIP] ZIP文件处理异常: {str(e)}")
        import traceback
        logger.error(f"[ZIP] 详细错误信息:\n{traceback.format_exc()}")
        
        # 确保清理临时文件
        try:
            if extract_dir:
                await ZipProcessor.cleanup_extracted_files(extract_dir)
        except:
            pass

# 任务状态API
@app.get("/api/tasks")
async def get_tasks_api(workspace_id: str = None):
    """获取任务列表API"""
    try:
        from app.services.task_queue import get_task_queue
        
        task_queue = get_task_queue()
        
        if workspace_id:
            tasks = task_queue.get_tasks_by_workspace(workspace_id)
        else:
            tasks = list(task_queue.tasks.values())
        
        return {
            "tasks": [
                {
                    "id": task.id,
                    "task_type": task.task_type,
                    "status": task.status.value,
                    "stage": task.progress.stage.value,
                    "progress": task.progress.progress,
                    "message": task.progress.message,
                    "details": task.progress.details or {},
                    "workspace_id": task.workspace_id,
                    "created_at": task.created_at,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at,
                    "error_message": task.error_message,
                    "metadata": task.metadata or {}
                }
                for task in tasks
            ],
            "queue_stats": task_queue.get_queue_stats()
        }
        
    except Exception as e:
        logger.error(f"获取任务列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")

@app.get("/api/tasks/parallel-status")
async def get_parallel_status_api():
    """获取并行处理状态API"""
    try:
        from app.services.task_queue import get_task_queue
        
        task_queue = get_task_queue()
        parallel_status = task_queue.get_parallel_queue_status()
        queue_stats = task_queue.get_queue_stats()
        
        return {
            "parallel_status": parallel_status,
            "queue_stats": queue_stats
        }
        
    except Exception as e:
        logger.error(f"获取并行状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取并行状态失败: {str(e)}")

@app.post("/api/tasks/cleanup")
async def cleanup_tasks_api():
    """清理旧任务API"""
    try:
        from app.services.task_queue import get_task_queue
        
        task_queue = get_task_queue()
        cleaned_count = task_queue.cleanup_old_tasks(max_age_hours=0)  # 清理所有已完成/失败/取消的任务
        
        return {
            "message": f"成功清理了 {cleaned_count} 个旧任务",
            "cleaned_count": cleaned_count,
            "remaining_tasks": len(task_queue.tasks)
        }
        
    except Exception as e:
        logger.error(f"清理任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清理任务失败: {str(e)}")

@app.post("/api/tasks/parallel-process")
async def parallel_process_tasks_api(task_ids: List[str]):
    """并行处理任务API"""
    try:
        from app.services.task_queue import get_task_queue
        
        task_queue = get_task_queue()
        processed_tasks = await task_queue.submit_parallel_tasks(task_ids)
        
        return {
            "message": f"已提交 {len(processed_tasks)} 个任务进行并行处理",
            "processed_tasks": processed_tasks,
            "total_submitted": len(task_ids)
        }
        
    except Exception as e:
        logger.error(f"并行处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"并行处理失败: {str(e)}")

@app.get("/api/tasks/{task_id}")
async def get_task_api(task_id: str):
    """获取单个任务信息API"""
    try:
        from app.services.task_queue import get_task_queue
        
        task_queue = get_task_queue()
        task = task_queue.get_task(task_id)
        
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return {
            "id": task.id,
            "task_type": task.task_type,
            "status": task.status.value,
            "stage": task.progress.stage.value,
            "progress": task.progress.progress,
            "message": task.progress.message,
            "details": task.progress.details or {},
            "workspace_id": task.workspace_id,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error_message": task.error_message,
            "metadata": task.metadata or {}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务信息失败: {str(e)}")

@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task_api(task_id: str):
    """取消任务API"""
    try:
        from app.services.task_queue import get_task_queue
        
        task_queue = get_task_queue()
        task_queue.cancel_task(task_id)
        
        return {"message": "任务已取消", "task_id": task_id}
        
    except Exception as e:
        logger.error(f"取消任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"取消任务失败: {str(e)}")

# 缓存管理API
@app.get("/api/cache/stats")
async def get_cache_stats_api():
    """获取缓存统计API"""
    try:
        from app.services.smart_cache_manager import get_cache_manager
        
        cache_manager = get_cache_manager()
        stats = cache_manager.get_all_stats()
        
        return {
            "cache_stats": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取缓存统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取缓存统计失败: {str(e)}")

@app.post("/api/cache/clear")
async def clear_cache_api():
    """清空缓存API"""
    try:
        from app.services.smart_cache_manager import get_cache_manager
        
        cache_manager = get_cache_manager()
        cache_manager.clear_all()
        
        return {
            "message": "缓存已清空",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"清空缓存失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清空缓存失败: {str(e)}")

# WebSocket端点
@app.websocket("/ws/status/{workspace_id}")
async def websocket_status_endpoint(websocket: WebSocket, workspace_id: str):
    """WebSocket状态推送端点"""
    await websocket_endpoint(websocket, workspace_id)

@app.websocket("/ws/status")
async def websocket_global_status_endpoint(websocket: WebSocket):
    """WebSocket全局状态推送端点"""
    await websocket_endpoint(websocket, "global")

@app.get("/api/documents")
async def get_documents_api(workspace_id: str = None):
    """获取文档列表API - 前端调用（优化版）"""
    try:
        import time
        
        # 简单的内存缓存
        cache_key = workspace_id or "default"
        current_time = time.time()
        
        # 检查缓存（30秒有效期）
        if hasattr(get_documents_api, '_cache') and hasattr(get_documents_api, '_cache_time'):
            if (cache_key in get_documents_api._cache and 
                current_time - get_documents_api._cache_time < 30):
                logger.info(f"使用缓存返回文档列表: {len(get_documents_api._cache[cache_key])} 个文档")
                return {"documents": get_documents_api._cache[cache_key]}
        
        from app.services.langchain_rag_service import LangChainRAGService
        rag_service = LangChainRAGService()
        
        if workspace_id:
            # 获取特定工作区的真实文档信息
            stats = rag_service.get_workspace_stats(workspace_id)
            vector_store = rag_service._load_vector_store(workspace_id)
            
            documents = []
            if vector_store and hasattr(vector_store, 'docstore'):
                # 从docstore获取真实文档信息
                docstore = vector_store.docstore
                if hasattr(docstore, '_dict'):
                    # 聚合同名文件
                    file_groups = {}
                    for doc_id, doc in docstore._dict.items():
                        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                        original_filename = metadata.get('original_filename') or metadata.get('source', f"文档_{doc_id[:8]}")
                        
                        if original_filename not in file_groups:
                            file_groups[original_filename] = {
                                "id": doc_id,  # 使用第一个文档的ID
                                "filename": original_filename,
                                "original_filename": original_filename,
                                "workspace_id": workspace_id,
                                "status": "processed",
                                "vectorized": True,
                                "file_size": metadata.get('file_size', 0),
                                "file_type": metadata.get('file_type', 'unknown'),
                                "created_at": metadata.get('upload_time', datetime.now().isoformat()),
                                "chunk_count": 1,
                                "chunk_ids": [doc_id]
                            }
                        else:
                            # 更新文件大小和块数量
                            file_groups[original_filename]["chunk_count"] += 1
                            file_groups[original_filename]["chunk_ids"].append(doc_id)
                            # 使用最新的上传时间
                            if metadata.get('upload_time'):
                                file_groups[original_filename]["created_at"] = metadata.get('upload_time')
                    
                    # 转换为列表
                    documents = list(file_groups.values())
            
            return {"documents": documents}
        else:
            # 优化：只返回工作区1的文档，避免遍历所有工作区
            logger.info("获取默认工作区的文档列表")
            stats = rag_service.get_workspace_stats("1")
            vector_store = rag_service._load_vector_store("1")
            
            documents = []
            if vector_store and hasattr(vector_store, 'docstore'):
                docstore = vector_store.docstore
                if hasattr(docstore, '_dict'):
                    # 聚合同名文件
                    file_groups = {}
                    for doc_id, doc in docstore._dict.items():
                        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                        original_filename = metadata.get('original_filename') or metadata.get('source', f"文档_{doc_id[:8]}")
                        
                        if original_filename not in file_groups:
                            file_groups[original_filename] = {
                                "id": doc_id,  # 使用第一个文档的ID
                                "filename": original_filename,
                                "original_filename": original_filename,
                                "workspace_id": "1",
                                "status": "processed",
                                "vectorized": True,
                                "file_size": metadata.get('file_size', 0),
                                "file_type": metadata.get('file_type', 'unknown'),
                                "created_at": metadata.get('upload_time', datetime.now().isoformat()),
                                "chunk_count": 1,
                                "chunk_ids": [doc_id]
                            }
                        else:
                            # 更新文件大小和块数量
                            file_groups[original_filename]["chunk_count"] += 1
                            file_groups[original_filename]["chunk_ids"].append(doc_id)
                            # 使用最新的上传时间
                            if metadata.get('upload_time'):
                                file_groups[original_filename]["created_at"] = metadata.get('upload_time')
                    
                    # 转换为列表
                    documents = list(file_groups.values())
            
            logger.info(f"默认工作区返回 {len(documents)} 个文档")
            
            # 存储到缓存
            if not hasattr(get_documents_api, '_cache'):
                get_documents_api._cache = {}
            get_documents_api._cache[cache_key] = documents
            get_documents_api._cache_time = current_time
            
            return {"documents": documents}
            
    except Exception as e:
        logger.error(f"获取文档列表失败: {str(e)}")
        return {"documents": []}

@app.delete("/api/documents/{doc_id}")
async def delete_document_api(doc_id: str):
    """删除文档API - 前端调用"""
    try:
        from app.services.langchain_rag_service import LangChainRAGService
        rag_service = LangChainRAGService()
        
        logger.info(f"收到删除文档请求: {doc_id}")
        
        # 在所有工作区中查找并删除文档
        deleted = False
        workspace_id = None
        deleted_chunks = 0
        filename = None
        
        # 首先查找文档，获取文件名和所有相关块
        file_groups = {}
        for ws_id in ["1", "2", "4", "7", "9", "10"]:
            try:
                vector_store = rag_service._load_vector_store(ws_id)
                if vector_store and hasattr(vector_store, 'docstore'):
                    docstore = vector_store.docstore
                    if hasattr(docstore, '_dict'):
                        for chunk_id, doc in docstore._dict.items():
                            metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                            original_filename = metadata.get('original_filename') or metadata.get('source', f"文档_{chunk_id[:8]}")
                            
                            if original_filename not in file_groups:
                                file_groups[original_filename] = {
                                    "workspace_id": ws_id,
                                    "chunk_ids": [chunk_id]
                                }
                            else:
                                file_groups[original_filename]["chunk_ids"].append(chunk_id)
            except Exception as e:
                logger.warning(f"在工作区 {ws_id} 中查找文档失败: {str(e)}")
                continue
        
        # 找到包含目标文档ID的文件组
        target_filename = None
        for fname, group in file_groups.items():
            if doc_id in group["chunk_ids"]:
                target_filename = fname
                workspace_id = group["workspace_id"]
                break
        
        if not target_filename:
            logger.warning(f"文档 {doc_id} 未找到")
            return {
                "status": "not_found",
                "id": doc_id,
                "message": "文档未找到"
            }
        
        # 删除该文件的所有块
        for chunk_id in file_groups[target_filename]["chunk_ids"]:
            try:
                if rag_service.delete_document(workspace_id, chunk_id):
                    deleted_chunks += 1
                    deleted = True
            except Exception as e:
                logger.warning(f"删除块 {chunk_id} 失败: {str(e)}")
        
        if deleted:
            logger.info(f"成功删除文件 {target_filename} 的 {deleted_chunks} 个块")
            
            # 清除缓存
            if hasattr(get_documents_api, '_cache'):
                get_documents_api._cache.clear()
                logger.info("已清除文档列表缓存")
            
            return {
                "status": "deleted", 
                "id": doc_id,
                "filename": target_filename,
                "workspace_id": workspace_id,
                "deleted_chunks": deleted_chunks,
                "message": f"文件 {target_filename} 已成功删除（{deleted_chunks} 个块）"
            }
        else:
            logger.warning(f"文件 {target_filename} 删除失败")
            return {
                "status": "error",
                "id": doc_id,
                "message": "删除失败"
            }
            
    except Exception as e:
        logger.error(f"删除文档失败: {str(e)}")
        return {
            "status": "error",
            "id": doc_id,
            "error": f"删除失败: {str(e)}"
        }

@app.post("/api/documents/{doc_id}/vectorize")
async def vectorize_document_api(doc_id: str):
    """文档向量化API - 前端调用"""
    try:
        # 文档已经在RAG系统中，直接返回成功
        return {"status": "vectorized", "id": doc_id}
    except Exception as e:
        logger.error(f"文档向量化失败: {str(e)}")
        return {"error": f"向量化失败: {str(e)}"}

# 工作区文件管理API端点
@app.post("/api/workspaces/{workspace_id}/files")
async def upload_workspace_file_api(
    workspace_id: str,
    file: UploadFile = File(...)
):
    """工作区文件上传API - 前端调用"""
    try:
        # 保存上传的文件
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        
        file_path = upload_dir / f"{uuid.uuid4()}_{file.filename}"
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # 添加到RAG系统
        from app.services.langchain_rag_service import LangChainRAGService
        rag_service = LangChainRAGService()
        success = await rag_service.add_document(
            workspace_id=workspace_id,
            file_path=str(file_path),
            metadata={
                "original_filename": file.filename,
                "file_size": len(content),
                "upload_time": datetime.now().isoformat(),
                "source": "workspace_api"
            }
        )
        
        if success:
            return {
                "id": str(uuid.uuid4()),
                "filename": file.filename,
                "size": len(content),
                "workspace_id": workspace_id,
                "status": "uploaded",
                "created_at": datetime.now().isoformat()
            }
        else:
            return {
                "error": "文件添加失败"
            }
            
    except Exception as e:
        logger.error(f"工作区文件上传失败: {str(e)}")
        return {
            "error": f"上传失败: {str(e)}"
        }

@app.get("/api/workspaces/{workspace_id}/files")
async def get_workspace_files_api(workspace_id: str):
    """获取工作区文件列表API - 前端调用"""
    try:
        from app.services.langchain_rag_service import LangChainRAGService
        rag_service = LangChainRAGService()
        
        stats = rag_service.get_workspace_stats(workspace_id)
        files = []
        
        for i in range(stats.get('document_count', 0)):
            files.append({
                "id": f"file_{workspace_id}_{i}",
                "filename": f"文件_{i+1}",
                "size": 1024,  # 模拟文件大小
                "workspace_id": workspace_id,
                "status": "processed",
                "created_at": datetime.now().isoformat()
            })
        
        return {"files": files}
        
    except Exception as e:
        logger.error(f"获取工作区文件列表失败: {str(e)}")
        return {"files": []}

@app.delete("/api/workspaces/{workspace_id}/files/{file_id}")
async def delete_workspace_file_api(workspace_id: str, file_id: str):
    """删除工作区文件API - 前端调用"""
    try:
        return {"status": "deleted", "id": file_id}
    except Exception as e:
        logger.error(f"删除工作区文件失败: {str(e)}")
        return {"error": f"删除失败: {str(e)}"}

# 调试端点
@app.get("/api/debug")
async def debug_api():
    """调试API"""
    return {"message": "调试端点正常工作", "timestamp": datetime.now().isoformat()}

# 工作区管理API端点
@app.get("/api/workspaces")
async def get_workspaces_api():
    """获取工作区列表API - 前端调用（只显示真正的工作区）"""
    try:
        logger.info("[DEBUG] 前端请求工作区列表")
        
        # 只从RAG服务获取真正存在的工作区
        workspaces = []
        
        try:
            from app.services.langchain_rag_service import LangChainRAGService
            
            # 检查向量数据库目录，找出所有工作区
            vector_db_path = Path("/root/consult/backend/langchain_vector_db")
            if vector_db_path.exists():
                # 查找所有工作区目录（排除workspace_global，它应该已经被迁移到global_db）
                for item in vector_db_path.iterdir():
                    if item.is_dir() and item.name.startswith("workspace_") and item.name != "workspace_global":
                        workspace_id = item.name.replace("workspace_", "")
                        
                        # 使用工作区特定的RAG服务获取统计
                        rag_service = LangChainRAGService(vector_db_path=f"langchain_vector_db/workspace_{workspace_id}")
                        
                        try:
                            stats = rag_service.get_workspace_stats(workspace_id)
                            logger.info(f"[DEBUG] 工作区 {workspace_id} 统计: {stats}")
                            workspaces.append({
                                "id": workspace_id,
                                "name": f"工作区 {workspace_id[:8]}",
                                "files": stats.get('document_count', 0),
                                "document_count": stats.get('document_count', 0),
                                "status": stats.get('status', 'active'),
                                "created": datetime.now().strftime("%Y-%m-%d"),
                                "created_at": datetime.now().isoformat()
                            })
                            logger.info(f"[DEBUG] 找到工作区: {workspace_id}")
                        except Exception as e:
                            logger.warning(f"[DEBUG] 工作区 {workspace_id} 统计失败: {e}")
                            # 即使统计失败，也添加空工作区
                            workspaces.append({
                                "id": workspace_id,
                                "name": f"工作区 {workspace_id[:8]}",
                                "files": 0,
                                "document_count": 0,
                                "status": "error",
                                "created": datetime.now().strftime("%Y-%m-%d"),
                                "created_at": datetime.now().isoformat()
                            })
                            logger.info(f"[DEBUG] 添加失败工作区: {workspace_id}")
            
            logger.info(f"[DEBUG] 找到 {len(workspaces)} 个工作区: {[w['id'] for w in workspaces]}")
            
        except Exception as e:
            logger.warning(f"[DEBUG] 获取工作区失败: {e}")
            import traceback
            logger.error(f"详细错误:\n{traceback.format_exc()}")
        
        # 如果没有找到任何工作区，返回空列表
        if not workspaces:
            logger.info("[DEBUG] 没有找到任何工作区")
            workspaces = []
        
        return {"workspaces": workspaces}
        
    except Exception as e:
        # 如果出错，返回默认工作区
        return {
            "workspaces": [
                {
                    "id": "1",
                    "name": "工作区 1",
                    "files": 0,
                    "document_count": 0,
                    "status": "empty",
                    "created": datetime.now().strftime("%Y-%m-%d"),
                    "created_at": datetime.now().isoformat()
                }
            ]
        }

@app.post("/api/workspaces")
async def create_workspace_api(data: dict):
    """创建工作区API - 前端调用（创建独立的工作区数据库）"""
    try:
        logger.info(f"[DEBUG] 前端创建工作区请求: {data}")
        
        workspace_name = data.get("name", "新工作区")
        
        # 生成工作区ID
        workspace_id = str(uuid.uuid4())
        
        # 创建工作区目录
        workspace_dir = Path(f"/root/consult/backend/langchain_vector_db/workspace_{workspace_id}")
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[DEBUG] 创建工作区目录: {workspace_dir}")
        
        # 初始化RAG服务
        from app.services.langchain_rag_service import LangChainRAGService
        rag_service = LangChainRAGService(vector_db_path=f"langchain_vector_db/workspace_{workspace_id}")
        
        # 返回前端期望的格式
        result = {
            "id": workspace_id,
            "name": workspace_name,
            "description": None,
            "document_count": 0,
            "status": "active",
            "created_at": datetime.now().isoformat()
        }
        
        logger.info(f"[DEBUG] 工作区创建成功: {result}")
        return result
        
    except Exception as e:
        logger.error(f"[DEBUG] 创建工作区失败: {str(e)}")
        import traceback
        logger.error(f"[DEBUG] 堆栈跟踪:\n{traceback.format_exc()}")
        return {"error": f"创建失败: {str(e)}"}

@app.patch("/api/workspaces/{workspace_id}")
async def update_workspace_api(workspace_id: str, data: dict):
    """更新工作区API - 前端调用"""
    try:
        workspace_name = data.get("name", f"工作区 {workspace_id}")
        
        return {
            "id": workspace_id,
            "name": workspace_name,
            "updated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"更新工作区失败: {str(e)}")
        return {"error": f"更新失败: {str(e)}"}

@app.delete("/api/workspaces/{workspace_id}")
async def delete_workspace_api(workspace_id: str):
    """删除工作区API - 前端调用（真正删除工作区目录）"""
    try:
        import shutil
        
        logger.info(f"[DEBUG] 删除工作区请求: {workspace_id}")
        
        # 删除工作区目录
        workspace_dir = Path(f"/root/consult/backend/langchain_vector_db/workspace_{workspace_id}")
        
        if workspace_dir.exists():
            # 删除整个工作区目录
            shutil.rmtree(workspace_dir)
            logger.info(f"[DEBUG] 成功删除工作区目录: {workspace_dir}")
            
            # 尝试删除工作区JSON文件
            from app.services.workspace_document_manager import get_workspace_documents_file
            json_file = get_workspace_documents_file(workspace_id)
            if json_file.exists():
                json_file.unlink()
                logger.info(f"[DEBUG] 成功删除工作区JSON文件: {json_file}")
            
            return {
                "status": "deleted", 
                "id": workspace_id,
                "message": "工作区已成功删除"
            }
        else:
            logger.warning(f"[DEBUG] 工作区目录不存在: {workspace_dir}")
            return {
                "status": "not_found",
                "id": workspace_id,
                "message": "工作区不存在"
            }
            
    except Exception as e:
        logger.error(f"删除工作区失败: {str(e)}")
        import traceback
        logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")
        return {"error": f"删除失败: {str(e)}"}

# 工作区文档管理API
@app.get("/api/workspaces/{workspace_id}/documents")
async def get_workspace_documents_api(workspace_id: str):
    """获取工作区文档列表API（从JSON快速返回）"""
    try:
        # 优先从JSON文件加载（快速）
        from app.services.workspace_document_manager import load_workspace_documents
        
        json_documents = load_workspace_documents(workspace_id)
        
        # 如果JSON中有数据，直接返回
        if json_documents:
            result_documents = []
            for doc in json_documents:
                result_documents.append({
                    "id": doc.get('id', ''),
                    "filename": doc.get('filename', ''),
                    "original_filename": doc.get('original_filename', ''),
                    "file_size": doc.get('file_size', 0),
                    "file_type": doc.get('file_type', ''),
                    "status": doc.get('status', 'completed'),
                    "created_at": doc.get('created_at', ''),
                    "upload_time": doc.get('created_at', ''),  # 兼容字段
                    "chunk_count": doc.get('chunk_count', 0),
                    # 添加chunk_ids字段，使用id作为第一个chunk ID
                    "chunk_ids": [doc.get('id', '')]
                })
            
            logger.info(f"工作区 {workspace_id} 从JSON加载 {len(result_documents)} 个文档")
            
            # 获取统计信息（使用JSON文档的数量）
            stats = {
                "workspace_id": workspace_id,
                "document_count": len(result_documents),
                "status": "active" if len(result_documents) > 0 else "empty"
            }
            
            # 返回统一格式
            return {
                "workspace_id": workspace_id,
                "documents": result_documents,
                "stats": stats
            }
        
        # 如果JSON为空，返回空列表（文档列表应该从JSON管理，向量数据库只用于检索）
        logger.info(f"工作区 {workspace_id} JSON为空，返回空列表")
        
        # 返回空列表
        return {
            "workspace_id": workspace_id,
            "documents": [],
            "stats": {
                "workspace_id": workspace_id,
                "document_count": 0,
                "status": "empty"
            }
        }
        
    except Exception as e:
        logger.error(f"获取工作区文档列表失败: {str(e)}")
        return {"error": f"获取失败: {str(e)}"}

@app.post("/api/workspaces/{workspace_id}/documents/upload")
async def upload_workspace_document_api(
    workspace_id: str,
    file: UploadFile = File(...)
):
    """上传文档到工作区API"""
    try:
        # 生成唯一文件名
        file_id = str(uuid.uuid4())
        file_extension = os.path.splitext(file.filename)[1]
        safe_filename = f"{file_id}_{file.filename}"
        
        # 保存文件
        upload_dir = Path("uploads") / workspace_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / safe_filename
        
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # 创建任务
        from app.services.task_queue import get_task_queue
        task_queue = get_task_queue()
        
        task_id = task_queue.create_task(
            task_type="document_processing",
            workspace_id=workspace_id,
            metadata={
                "original_filename": file.filename,
                "file_size": len(content),
                "file_path": str(file_path),
                "file_type": file_extension,
                "upload_time": datetime.now().isoformat(),
                "source": "workspace_documents_api"
            }
        )
        
        # 如果是归档文件（ZIP或RAR），进行特殊处理
        if file_extension == '.zip' or file_extension == '.rar':
            # 启动ZIP处理任务
            archive_type = "RAR" if file_extension == '.rar' else "ZIP"
            asyncio.create_task(process_zip_async(task_id, str(file_path), workspace_id))
            
            return {
                "status": "success",
                "message": f"{archive_type}文件 {file.filename} 上传到工作区成功，正在解压并处理",
                "task_id": task_id,
                "workspace_id": workspace_id,
                "file_type": file_extension,
                "file_size": len(content)
            }
        
        # 启动普通文档异步处理
        from app_simple import process_document_async
        asyncio.create_task(process_document_async(task_id, str(file_path), workspace_id))
        
        return {
            "status": "success",
            "message": f"文档 {file.filename} 上传成功，正在后台处理",
            "task_id": task_id,
            "workspace_id": workspace_id,
            "file_path": str(file_path),
            "file_size": len(content)
        }
        
    except Exception as e:
        logger.error(f"上传工作区文档失败: {str(e)}")
        return {"error": f"上传失败: {str(e)}"}

@app.post("/api/global/documents/upload")
async def upload_global_document_api(
    file: UploadFile = File(...)
):
    """上传文档到全局数据库API（固定 workspace_id = 'global'）"""
    try:
        workspace_id = "global"

        # 生成唯一文件名
        file_id = str(uuid.uuid4())
        file_extension = os.path.splitext(file.filename)[1]
        safe_filename = f"{file_id}_{file.filename}"

        # 保存文件到 uploads/global/
        upload_dir = Path("uploads") / workspace_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / safe_filename

        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # 创建任务
        from app.services.task_queue import get_task_queue
        task_queue = get_task_queue()

        task_id = task_queue.create_task(
            task_type="document_processing",
            workspace_id=workspace_id,
            metadata={
                "original_filename": file.filename,
                "file_size": len(content),
                "file_path": str(file_path),
                "file_type": file_extension,
                "upload_time": datetime.now().isoformat(),
                "source": "global_documents_api"
            }
        )

        # 压缩包特殊处理
        if file_extension == '.zip' or file_extension == '.rar':
            archive_type = "RAR" if file_extension == '.rar' else "ZIP"
            asyncio.create_task(process_zip_async(task_id, str(file_path), workspace_id))
            return {
                "status": "success",
                "message": f"{archive_type}文件 {file.filename} 上传到全局成功，正在解压并处理",
                "task_id": task_id,
                "workspace_id": workspace_id,
                "file_type": file_extension,
                "file_size": len(content)
            }

        # 普通文档异步处理
        from app_simple import process_document_async
        asyncio.create_task(process_document_async(task_id, str(file_path), workspace_id))

        return {
            "status": "success",
            "message": f"文档 {file.filename} 上传成功，正在后台处理",
            "task_id": task_id,
            "workspace_id": workspace_id,
            "file_path": str(file_path),
            "file_size": len(content)
        }

    except Exception as e:
        logger.error(f"上传全局文档失败: {str(e)}")
        return {"error": f"上传失败: {str(e)}"}

@app.delete("/api/workspaces/{workspace_id}/documents/{doc_id}")
async def delete_workspace_document_api(workspace_id: str, doc_id: str):
    """删除工作区文档API"""
    try:
        from app.services.langchain_rag_service import LangChainRAGService
        from app.services.workspace_document_manager import load_workspace_documents, save_workspace_documents
        
        logger.info(f"收到删除工作区文档请求: {workspace_id}/{doc_id}")
        
        # 首先从JSON删除
        json_documents = load_workspace_documents(workspace_id)
        filtered_documents = [doc for doc in json_documents if doc.get('id') != doc_id]
        
        deleted = False
        if len(filtered_documents) < len(json_documents):
            # JSON中有此文档，获取要删除的文档的原始文件名
            deleted_doc = [doc for doc in json_documents if doc.get('id') == doc_id][0]
            deleted_filename = deleted_doc.get('original_filename')
            
            # 保存过滤后的JSON
            save_workspace_documents(workspace_id, filtered_documents)
            logger.info(f"从JSON中删除了文档: {doc_id}, 文件名: {deleted_filename}")
            deleted = True
            
            # 尝试从向量数据库删除相关chunks（通过文件名匹配）
            try:
                rag_service = LangChainRAGService(vector_db_path="langchain_vector_db")
                vector_store = rag_service._load_vector_store(workspace_id)
                
                if vector_store and hasattr(vector_store, 'docstore'):
                    docstore = vector_store.docstore
                    if hasattr(docstore, '_dict'):
                        # 查找并删除匹配文件名的所有chunks
                        deleted_chunks = 0
                        chunks_to_delete = []
                        for chunk_id, doc in docstore._dict.items():
                            metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                            original_filename = metadata.get('original_filename') or metadata.get('source', '')
                            # 通过文件名匹配
                            if original_filename == deleted_filename:
                                chunks_to_delete.append(chunk_id)
                        
                        # 删除匹配的chunks
                        for chunk_id in chunks_to_delete:
                            try:
                                if rag_service.delete_document(workspace_id, chunk_id):
                                    deleted_chunks += 1
                            except Exception as e:
                                logger.warning(f"删除块 {chunk_id} 失败: {str(e)}")
                        
                        if deleted_chunks > 0:
                            logger.info(f"从向量数据库删除了 {deleted_chunks} 个块（文件名: {deleted_filename}）")
            except Exception as vec_error:
                logger.warning(f"从向量数据库删除失败: {vec_error}")
            
            return {
                "status": "deleted",
                "id": doc_id,
                "message": "文档已成功删除"
            }
        else:
            logger.warning(f"文档 {doc_id} 在工作区 {workspace_id} 的JSON中未找到")
            return {
                "status": "not_found",
                "id": doc_id,
                "message": "文档未找到"
            }
                    
    except Exception as e:
        logger.error(f"删除工作区文档失败: {str(e)}")
        return {
            "status": "error",
            "id": doc_id,
            "error": f"删除失败: {str(e)}"
        }

@app.get("/api/workspaces/{workspace_id}/documents/{doc_id}/download")
async def download_workspace_document_api(workspace_id: str, doc_id: str):
    """下载工作区文档API"""
    try:
        from app.services.langchain_rag_service import LangChainRAGService
        rag_service = LangChainRAGService()
        
        # 查找文档文件路径
        vector_store = rag_service._load_vector_store(workspace_id)
        if vector_store and hasattr(vector_store, 'docstore'):
            docstore = vector_store.docstore
            if hasattr(docstore, '_dict') and doc_id in docstore._dict:
                doc = docstore._dict[doc_id]
                metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                file_path = metadata.get('file_path')
                
                if file_path and os.path.exists(file_path):
                    filename = metadata.get('original_filename', f"document_{doc_id[:8]}")
                    
                    from fastapi.responses import FileResponse
                    return FileResponse(
                        path=file_path,
                        filename=filename,
                        media_type='application/octet-stream'
                    )
        
        raise HTTPException(status_code=404, detail="文档未找到")
        
    except Exception as e:
        logger.error(f"下载工作区文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")

# 状态管理API端点
@app.get("/api/status")
async def get_all_status_api():
    """获取所有工作区状态API - 前端调用"""
    try:
        from app.services.langchain_rag_service import LangChainRAGService
        
        # 找出所有工作区
        statuses = []
        vector_db_path = Path("/root/consult/backend/langchain_vector_db")
        if vector_db_path.exists():
            rag_service = LangChainRAGService(vector_db_path="langchain_vector_db")
            
            for item in vector_db_path.iterdir():
                if item.is_dir() and item.name.startswith("workspace_") and item.name != "workspace_global":
                    workspace_id = item.name.replace("workspace_", "")
                    try:
                        stats = rag_service.get_workspace_stats(workspace_id)
                        # 返回正确的格式给status-panel
                        statuses.append({
                            "id": workspace_id,
                            "workspace": f"工作区 {workspace_id[:8]}",
                            "status": stats.get('status', 'empty'),
                            "progress": 100 if stats.get('status') == 'active' else 0,
                            "message": "工作区正常运行" if stats.get('status') == 'active' else "工作区无文档",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
                        })
                    except Exception as e:
                        logger.warning(f"获取工作区 {workspace_id} 状态失败: {e}")
        
        return {"statuses": statuses}
        
    except Exception as e:
        logger.error(f"获取状态失败: {str(e)}")
        return {"statuses": []}

@app.get("/api/status/{workspace_id}")
async def get_workspace_status_api(workspace_id: str):
    """获取特定工作区状态API - 前端调用"""
    try:
        from app.services.langchain_rag_service import LangChainRAGService
        rag_service = LangChainRAGService()
        
        stats = rag_service.get_workspace_stats(workspace_id)
        return {
            "workspace_id": workspace_id,
            "status": stats.get('status', 'empty'),
            "document_count": stats.get('document_count', 0),
            "rag_available": stats.get('status') == 'active',
            "last_updated": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取工作区状态失败: {str(e)}")
        return {
            "workspace_id": workspace_id,
            "status": "error",
            "document_count": 0,
            "rag_available": False,
            "error": str(e)
        }

@app.post("/api/agent/execute")
async def execute_action(data: dict):
    """执行特定应用操作"""
    workspace_id = data.get("workspaceId")
    action_id = data.get("actionId")
    params = data.get("params", {})

    # 简化版：返回模拟的执行结果
    return {
        "action_id": action_id,
        "status": "completed",
        "result": f"成功执行操作 {action_id}",
        "output_files": [
            {
                "id": str(uuid.uuid4()),
                "name": f"result_{action_id}_{int(datetime.now().timestamp())}.txt",
                "type": "text",
                "size": "1.5 KB"
            }
        ]
    }

@app.get("/api/documents/{doc_id}/preview")
async def preview_document_api(doc_id: str, chunk_id: str = None, highlight: str = None):
    """文档预览API - 支持高亮显示"""
    try:
        from app.services.langchain_rag_service import LangChainRAGService
        rag_service = LangChainRAGService()
        
        logger.info(f"收到文档预览请求: doc_id={doc_id}, chunk_id={chunk_id}")
        
        # 查找文档
        document_content = None
        document_metadata = {}
        
        # 在所有工作区中查找文档
        for workspace_id in ["1", "2", "4", "7", "9", "10"]:
            try:
                hybrid_retriever = rag_service._get_hybrid_retriever(workspace_id)
                if hybrid_retriever.vector_store and hasattr(hybrid_retriever.vector_store, 'docstore'):
                    docstore = hybrid_retriever.vector_store.docstore
                    if hasattr(docstore, '_dict') and doc_id in docstore._dict:
                        doc = docstore._dict[doc_id]
                        document_content = doc.page_content
                        document_metadata = doc.metadata
                        break
            except Exception as e:
                logger.warning(f"在工作区 {workspace_id} 中查找文档失败: {str(e)}")
                continue
        
        if not document_content:
            return {
                "error": "文档未找到",
                "doc_id": doc_id
            }
        
        # 处理高亮
        if highlight and highlight in document_content:
            # 简单的关键词高亮
            highlighted_content = document_content.replace(
                highlight, 
                f"<mark style='background-color: yellow;'>{highlight}</mark>"
            )
        else:
            highlighted_content = document_content
        
        # 如果指定了chunk_id，尝试定位到特定位置
        if chunk_id:
            # 这里可以实现更精确的定位逻辑
            pass
        
        return {
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "content": highlighted_content,
            "metadata": document_metadata,
            "highlight": highlight,
            "preview_url": f"/api/documents/{doc_id}/preview"
        }
        
    except Exception as e:
        logger.error(f"文档预览失败: {str(e)}")
        return {
            "error": f"预览失败: {str(e)}",
            "doc_id": doc_id
        }

@app.get("/api/documents/{doc_id}/download")
async def download_document_api(doc_id: str):
    """文档下载API"""
    try:
        from app.services.langchain_rag_service import LangChainRAGService
        rag_service = LangChainRAGService()
        
        # 查找文档文件路径
        file_path = None
        original_filename = None
        
        for workspace_id in ["1", "2", "4", "7", "9", "10"]:
            try:
                hybrid_retriever = rag_service._get_hybrid_retriever(workspace_id)
                if hybrid_retriever.vector_store and hasattr(hybrid_retriever.vector_store, 'docstore'):
                    docstore = hybrid_retriever.vector_store.docstore
                    if hasattr(docstore, '_dict') and doc_id in docstore._dict:
                        doc = docstore._dict[doc_id]
                        metadata = doc.metadata
                        file_path = metadata.get('file_path')
                        original_filename = metadata.get('original_filename', f'document_{doc_id}.txt')
                        break
            except Exception as e:
                logger.warning(f"在工作区 {workspace_id} 中查找文档失败: {str(e)}")
                continue
        
        if not file_path or not os.path.exists(file_path):
            return {
                "error": "文档文件未找到",
                "doc_id": doc_id
            }
        
        # 返回文件下载信息
        return {
            "doc_id": doc_id,
            "file_path": file_path,
            "original_filename": original_filename,
            "download_url": f"/api/documents/{doc_id}/download"
        }
        
    except Exception as e:
        logger.error(f"文档下载失败: {str(e)}")
        return {
            "error": f"下载失败: {str(e)}",
            "doc_id": doc_id
        }


@app.get("/api/status/{workspace_id}")
async def get_workspace_status(workspace_id: str):
    """获取特定工作区的处理状态（重定向到新API）"""
    # 直接调用新的API
    return await get_workspace_status_api(workspace_id)

@app.post("/api/agent/generate-document")
async def generate_document_api(data: dict):
    """文档生成API"""
    try:
        from app.services.document_generator_service import DocumentGeneratorService, DocumentType
        
        request_text = data.get("request", "")
        doc_type_str = data.get("doc_type", "pdf")
        filename = data.get("filename")
        
        if not request_text:
            return {
                "success": False,
                "error": "请提供生成请求"
            }
        
        # 创建生成服务
        generator_service = DocumentGeneratorService()
        
        # 解析请求
        content, doc_type = generator_service.parse_generation_request(request_text)
        
        # 覆盖文档类型
        if doc_type_str.lower() == "word":
            doc_type = DocumentType.WORD
        elif doc_type_str.lower() == "pdf":
            doc_type = DocumentType.PDF
        
        # 生成文档
        result = generator_service.generate_document(content, doc_type, filename)
        
        if result["success"]:
            return {
                "success": True,
                "message": "文档生成成功",
                "file_info": {
                    "filename": result["filename"],
                    "file_size": result["file_size"],
                    "doc_type": result["doc_type"],
                    "download_url": f"/api/documents/download/{result['filename']}"
                },
                "generated_at": result["generated_at"]
            }
        else:
            return {
                "success": False,
                "error": result["error"]
            }
            
    except Exception as e:
        logger.error(f"文档生成失败: {str(e)}")
        return {
            "success": False,
            "error": f"生成失败: {str(e)}"
        }

@app.get("/api/documents/download/{filename}")
async def download_generated_document(filename: str):
    """下载生成的文档"""
    try:
        from fastapi.responses import FileResponse
        from pathlib import Path
        
        # 安全检查：防止路径遍历
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="无效的文件名")
        
        file_path = Path("generated_documents") / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type='application/octet-stream'
        )
        
    except Exception as e:
        logger.error(f"文档下载失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


# 工作区文件管理API端点
@app.get("/api/workspace/{workspace_id}/files")
async def list_workspace_generated_files(workspace_id: str):
    """列出工作区的生成文件"""
    try:
        from app.services.workspace_file_manager import WorkspaceFileManager
        
        file_manager = WorkspaceFileManager()
        files = file_manager.list_workspace_files(workspace_id)
        
        return {
            "files": files,
            "count": len(files),
            "workspace_id": workspace_id
        }
        
    except Exception as e:
        logger.error(f"列出工作区文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"列出文件失败: {str(e)}")


@app.get("/api/workspace/{workspace_id}/files/{file_id}/download")
async def download_workspace_file(workspace_id: str, file_id: str):
    """下载工作区生成的文件"""
    try:
        from app.services.workspace_file_manager import WorkspaceFileManager
        from fastapi.responses import FileResponse
        
        file_manager = WorkspaceFileManager()
        file_info = file_manager.get_file_info(file_id)
        
        if not file_info or file_info['workspace_id'] != workspace_id:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 记录下载
        file_manager.record_download(file_id)
        
        return FileResponse(
            path=file_info['file_path'],
            filename=file_info['filename'],
            media_type='application/octet-stream'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载工作区文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@app.delete("/api/workspace/{workspace_id}/files/{file_id}")
async def delete_workspace_file(workspace_id: str, file_id: str):
    """删除工作区生成的文件"""
    try:
        from app.services.workspace_file_manager import WorkspaceFileManager
        
        file_manager = WorkspaceFileManager()
        success = file_manager.delete_file(file_id, workspace_id)
        
        if success:
            return {"message": "文件删除成功", "file_id": file_id}
        else:
            raise HTTPException(status_code=404, detail="文件不存在或无权限删除")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除工作区文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@app.post("/api/agent/chat/confirm-generation")
async def confirm_generation(data: dict):
    """确认文件生成（二次确认）"""
    try:
        from app.services.intent_classifier import IntentClassifier
        from app.services.content_aggregator import ContentAggregator
        from app.services.document_generator_service import DocumentGeneratorService
        from app.services.workspace_file_manager import WorkspaceFileManager
        
        workspace_id = data.get("workspace_id", "1")
        conversation_history = data.get("history", [])
        confirmed_params = data.get("confirmed_params", {})
        
        # 使用确认的参数重新生成文档
        rag_service = get_rag_service()
        
        # 创建确认后的意图
        from app.services.intent_classifier import IntentResult
        from app.services.document_generator_service import DocumentType
        intent = IntentResult(
            is_generation_intent=True,
            doc_type=DocumentType(confirmed_params.get('doc_type', 'word')),
            content_source=confirmed_params.get('content_source', 'mixed'),
            title=confirmed_params.get('title', '确认生成的文档'),
            inferred_query=confirmed_params.get('query', ''),
            needs_confirmation=False,
            confirmation_message=None,
            extracted_params=confirmed_params,
            confidence=0.9
        )
        
        # 聚合内容
        content_aggregator = ContentAggregator(rag_service, rag_service.llm)
        aggregated_content = await content_aggregator.aggregate_content(
            intent, workspace_id, conversation_history
        )
        
        # 生成文档
        doc_generator = DocumentGeneratorService()
        result = doc_generator.generate_document(
            aggregated_content.to_document_content(),
            intent.doc_type
        )
        
        # 保存到工作区
        if result['success']:
            file_manager = WorkspaceFileManager()
            file_id = file_manager.save_generated_file(
                workspace_id,
                result['file_path'],
                {
                    'doc_type': result['doc_type'],
                    'title': aggregated_content.title,
                    'source_query': confirmed_params.get('query', ''),
                    'references': [ref.get('document_id', ref.get('chunk_id', '')) for ref in aggregated_content.references]
                }
            )
            
            return {
                "success": True,
                "message": f"文档生成成功：{aggregated_content.title}",
                "file_info": {
                    "file_id": file_id,
                    "filename": result['filename'],
                    "file_type": result['doc_type'],
                    "file_size": result['file_size'],
                    "download_url": f"/api/workspace/{workspace_id}/files/{file_id}/download"
                },
                "references": aggregated_content.references
            }
        else:
            return {
                "success": False,
                "error": result.get('error', '文档生成失败')
            }
            
    except Exception as e:
        logger.error(f"确认生成失败: {str(e)}")
        return {
            "success": False,
            "error": f"生成失败: {str(e)}"
        }

# 全局文档API
@app.get("/api/global/documents")
async def list_global_documents():
    """列出所有全局文档"""
    try:
        from app.api.v1.endpoints.global_api import load_global_documents
        
        documents = load_global_documents()
        
        # 转换格式
        result_documents = []
        for doc in documents:
            result_documents.append({
                "id": doc.get('id', ''),
                "filename": doc.get('filename', ''),
                "original_filename": doc.get('original_filename', ''),
                "file_size": doc.get('file_size', 0),
                "file_type": doc.get('file_type', ''),
                "status": doc.get('status', 'completed'),
                "created_at": doc.get('created_at', ''),
                "chunk_count": doc.get('chunk_count', 0)
            })
        
        return {
            "documents": result_documents,
            "total_count": len(result_documents),
            "message": "全局文档列表"
        }
    except Exception as e:
        logger.error(f"获取全局文档列表失败: {str(e)}")
        import traceback
        traceback.print_exc()
        # 返回空列表而不是错误
        return {
            "documents": [],
            "total_count": 0,
            "message": "暂无全局文档"
        }

@app.get("/api/global/workspaces")
async def list_global_workspaces():
    """列出所有全局工作区"""
    try:
        from app.api.v1.endpoints.global_api import load_global_workspaces
        
        workspaces = load_global_workspaces()
        
        return {
            "workspaces": workspaces,
            "total_count": len(workspaces),
            "message": "全局工作区列表"
        }
    except Exception as e:
        logger.error(f"获取全局工作区列表失败: {str(e)}")
        import traceback
        traceback.print_exc()
        # 返回空列表而不是错误
        return {
            "workspaces": [],
            "total_count": 0,
            "message": "暂无全局工作区"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18000)
