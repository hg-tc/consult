"""
全局文档库API端点
支持公共文档库和工作区分离的架构
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from typing import List, Dict, Any, Optional
import os
import uuid
import logging
from pathlib import Path
from datetime import datetime

# 简化导入，避免复杂的依赖
# from app.models.global_database import GlobalDatabaseService
# from app.services.global_rag_service import GlobalRAGService
# from app.core.database import get_db
from app.services.langchain_rag_service import LangChainRAGService
from app.services.performance_optimizer import get_performance_optimizer
from app.services.file_index_manager import file_index_manager
# 全局RAG服务实例（单例模式）
_global_rag_service = None

def get_global_rag_service():
    """获取全局RAG服务实例（单例模式）"""
    global _global_rag_service
    if _global_rag_service is None:
        # 使用global_db目录，is_global=True标记这不是一个工作区
        _global_rag_service = LangChainRAGService(vector_db_path="global_db", is_global=True)
    return _global_rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/global", tags=["global"])

# 简化的全局服务实例
performance_optimizer = get_performance_optimizer()  # 性能优化器

# 持久化存储路径
GLOBAL_DATA_DIR = Path("/root/consult/backend/global_data")
GLOBAL_DOCUMENTS_FILE = GLOBAL_DATA_DIR / "documents.json"
GLOBAL_WORKSPACES_FILE = GLOBAL_DATA_DIR / "workspaces.json"

# 确保目录存在
GLOBAL_DATA_DIR.mkdir(exist_ok=True)

def load_global_documents():
    """从文件加载全局文档"""
    if GLOBAL_DOCUMENTS_FILE.exists():
        try:
            import json
            with open(GLOBAL_DOCUMENTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载全局文档失败: {e}")
    return []

def save_global_documents(documents):
    """保存全局文档到文件"""
    try:
        import json
        with open(GLOBAL_DOCUMENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(documents, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存全局文档失败: {e}")

def load_global_workspaces():
    """从文件加载全局工作区"""
    if GLOBAL_WORKSPACES_FILE.exists():
        try:
            import json
            with open(GLOBAL_WORKSPACES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载全局工作区失败: {e}")
    return []

def save_global_workspaces(workspaces):
    """保存全局工作区到文件"""
    try:
        import json
        with open(GLOBAL_WORKSPACES_FILE, 'w', encoding='utf-8') as f:
            json.dump(workspaces, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存全局工作区失败: {e}")

def get_global_services():
    """获取简化的全局服务实例"""
    documents = load_global_documents()
    workspaces = load_global_workspaces()
    return documents, workspaces


@router.post("/documents/upload")
async def upload_global_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """上传文档到全局文档库"""
    try:
        # 检查文件类型
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        
        file_ext = os.path.splitext(file.filename)[1].lower()
        # 与前端 accept 对齐，支持 Office 与归档
        allowed_extensions = ['.pdf', '.docx', '.doc', '.txt', '.md', '.xlsx', '.xls', '.pptx', '.ppt', '.zip', '.rar']
        
        if file_ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file_ext}")
        
        # 检查文件大小
        content = await file.read()
        file_size = len(content)
        
        if file_size > 50 * 1024 * 1024:  # 50MB限制
            raise HTTPException(status_code=413, detail="文件大小超过限制")
        
        # 第一步：快速保存文件
        file_id = str(uuid.uuid4())
        filename = f"{file_id}{file_ext}"
        upload_dir = Path("uploads/global")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / filename
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        # 创建文档记录（初始状态为uploaded）
        document_data = {
            'id': file_id,
            'filename': filename,
            'original_filename': file.filename,
            'file_size': file_size,
            'file_path': str(file_path),
            'mime_type': file.content_type or "application/octet-stream",
            'status': 'uploaded',
            'created_at': datetime.now().isoformat(),
            'processing_started': None,
            'processing_completed': None,
            'chunk_count': 0,
            'quality_score': 0.0
        }
        
        # 如果是ZIP或RAR文件，使用专门的归档处理
        if file_ext in ['.zip', '.rar']:
            # 创建归档处理任务
            from app.services.task_queue import get_task_queue, TaskStage
            
            task_queue = get_task_queue()
            task_id = task_queue.create_task(
                task_type="global_archive_processing",
                metadata={
                    'original_filename': file.filename,
                    'file_path': str(file_path),
                    'file_size': file_size,
                    'document_id': file_id,
                    'file_type': file_ext
                },
                workspace_id="global"
            )
            
            # 归档文件不保存到JSON，只由内部文件记录保存
            # 更新进度
            task_queue.update_task_progress(
                task_id=task_id,
                stage=TaskStage.UPLOADING,
                progress=100,
                message="归档文件上传完成"
            )
            
            # 使用app_simple.py中的process_zip_async函数
            from app_simple import process_zip_async
            import asyncio
            asyncio.create_task(process_zip_async(task_id, str(file_path), "global"))
            return {
                "id": file_id,
                "task_id": task_id,
                "filename": filename,
                "original_filename": file.filename,
                "file_size": file_size,
                "status": "uploaded",
                "file_type": file_ext,
                "message": f"{'ZIP' if file_ext == '.zip' else 'RAR'}文件上传成功，正在解压并处理...",
                "processing_status": "queued"
            }
        
        # 保存文档记录到JSON文件
        documents = load_global_documents()
        documents.append(document_data)
        save_global_documents(documents)
        
        # 第二步：创建TaskQueue任务并后台异步处理文档（不阻塞响应）
        from app.services.task_queue import get_task_queue, TaskStage
        
        task_queue = get_task_queue()
        task_id = task_queue.create_task(
            task_type="global_document_processing",
            metadata={
                'original_filename': file.filename,
                'file_path': str(file_path),
                'file_size': file_size,
                'document_id': file_id
            },
            workspace_id="global"
        )
        
        # 后台处理（使用TaskQueue）
        import asyncio
        asyncio.create_task(
            process_global_document_with_progress(
                str(file_path), 
                document_data, 
                task_id
            )
        )
        
        # 立即返回成功响应
        return {
            "id": file_id,
            "task_id": task_id,  # 新增
            "filename": filename,
            "original_filename": file.filename,
            "file_size": file_size,
            "status": "uploaded",
            "message": "文件上传成功，正在后台处理中...",
            "processing_status": "queued"
        }
        
    except Exception as e:
        logger.error(f"全局文档上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


def process_global_document_async(file_path: str, document_data: Dict[str, Any]):
    """异步后台处理全局文档（分步处理）"""
    import asyncio
    asyncio.run(process_global_document_step_by_step(file_path, document_data))

async def process_global_document_with_progress(
    file_path: str, 
    document_data: Dict[str, Any],
    task_id: str
):
    """带进度更新的文档处理"""
    from app.services.task_queue import get_task_queue, TaskStage
    import asyncio
    
    task_queue = get_task_queue()
    
    try:
        doc_id = document_data['id']
        logger.info(f"🚀 开始带进度处理的全局文档: {file_path}, ID: {doc_id}, Task: {task_id}")
        
        # 开始任务
        task_queue.start_task(task_id)
        
        # 阶段1: 解析文档 (0-30%)
        task_queue.update_task_progress(
            task_id, 
            TaskStage.PARSING, 
            10, 
            "正在解析文档..."
        )
        
        # 添加延迟以便观察进度
        await asyncio.sleep(0.5)
        
        # 更新状态为处理中
        await update_document_status(doc_id, 'processing', processing_started=datetime.now().isoformat())
        
        # 调用RAG服务
        global_rag = get_global_rag_service()
        
        logger.info(f"📄 开始解析文档: {document_data['original_filename']}")
        
        # 阶段2: 分块 (30-50%)
        task_queue.update_task_progress(
            task_id, 
            TaskStage.CHUNKING, 
            40, 
            "正在分割文档..."
        )
        
        await asyncio.sleep(0.5)
        
        # 阶段3: 向量化 (50-80%)
        task_queue.update_task_progress(
            task_id, 
            TaskStage.VECTORIZING, 
            60, 
            "正在加载检索模块..."
        )
        
        # 使用 LlamaIndex 导入（增加超时检测）
        logger.info(f"准备开始LlamaIndexRetriever导入和初始化")
        import asyncio as _asyncio
        import concurrent.futures
        
        # 导入超时时间（秒）：60秒 = 1分钟
        IMPORT_TIMEOUT = 60
        
        def import_and_get_retriever():
            """在线程中执行导入和初始化，避免阻塞主事件循环"""
            try:
                from app.services.llamaindex_retriever import get_retriever
                logger.info(f"✅ LlamaIndexRetriever模块导入完成")
                retriever = get_retriever("global")  # 使用缓存单例，避免重复加载模型和索引
                logger.info(f"✅ LlamaIndexRetriever初始化完成")
                return retriever
            except Exception as e:
                logger.error(f"❌ LlamaIndexRetriever导入或初始化失败: {e}", exc_info=True)
                raise
        
        retriever = None
        try:
            # 在线程池中执行导入，设置超时
            loop = _asyncio.get_event_loop()
            task_queue.update_task_progress(
                task_id,
                TaskStage.VECTORIZING,
                62,
                f"正在导入检索模块（最多等待{IMPORT_TIMEOUT}秒）..."
            )
            retriever = await _asyncio.wait_for(
                loop.run_in_executor(None, import_and_get_retriever),
                timeout=IMPORT_TIMEOUT
            )
            logger.info(f"✅ LlamaIndexRetriever导入和初始化成功完成")
        except _asyncio.TimeoutError:
            logger.error(f"⏰ LlamaIndexRetriever导入超时({IMPORT_TIMEOUT}秒): {file_path}")
            # 清理失败的上传
            await cleanup_failed_upload(doc_id, file_path)
            await update_document_status(doc_id, 'failed', 
                                        processing_completed=datetime.now().isoformat(),
                                        error_message=f"导入检索模块超时({IMPORT_TIMEOUT}秒)，请重新上传")
            task_queue.fail_task(task_id, f"导入检索模块超时({IMPORT_TIMEOUT}秒)，文件上传失败，请重新上传")
            return
        except Exception as e:
            logger.error(f"❌ LlamaIndexRetriever导入失败: {e}", exc_info=True)
            # 清理失败的上传
            await cleanup_failed_upload(doc_id, file_path)
            await update_document_status(doc_id, 'failed',
                                        processing_completed=datetime.now().isoformat(),
                                        error_message=f"导入检索模块失败: {str(e)}")
            task_queue.fail_task(task_id, f"导入检索模块失败: {str(e)}，文件上传失败，请重新上传")
            return
        logger.info(f"🔧 LlamaIndex add_document 开始: path={file_path}, size={document_data['file_size']}, mime={document_data['mime_type']}")
        add_task = _asyncio.create_task(
            retriever.add_document(
                file_path=file_path,
                metadata={
                    'document_id': doc_id,
                    'original_filename': document_data['original_filename'],
                    'file_type': document_data['mime_type'],
                    'file_size': document_data['file_size'],
                    'upload_time': document_data['created_at']
                }
            )
        )
        # 心跳轮询：每30秒更新一次，最大等待600秒
        heartbeat_progress = 65
        total_wait = 0
        added_count = 0
        try:
            while True:
                try:
                    added_count = await _asyncio.wait_for(add_task, timeout=30)
                    break
                except _asyncio.TimeoutError:
                    total_wait += 30
                    # 心跳更新
                    task_queue.update_task_progress(
                        task_id,
                        TaskStage.VECTORIZING,
                        min(heartbeat_progress, 85),
                        f"向量化进行中... 已等待 {total_wait}s"
                    )
                    logger.info(f"⏳ add_document 心跳: 等待 {total_wait}s, progress={heartbeat_progress}%")
                    heartbeat_progress += 5
                    if total_wait >= 600:
                        raise _asyncio.TimeoutError()
        except _asyncio.TimeoutError:
            logger.error(f"⏰ LlamaIndex add_document 超时(600s): {file_path}")
            # 尝试从索引中删除可能已添加的数据
            try:
                if retriever:
                    retriever.delete_by_document_id(doc_id)
                    logger.info(f"已尝试从索引中删除超时的文档: {doc_id}")
            except Exception as cleanup_err:
                logger.warning(f"清理索引数据失败: {cleanup_err}")
            # 清理失败的上传
            await cleanup_failed_upload(doc_id, file_path)
            await update_document_status(doc_id, 'failed', 
                                        processing_completed=datetime.now().isoformat(),
                                        error_message="文档处理超时(600秒)，请重新上传")
            task_queue.fail_task(task_id, "文档处理超时(600秒)，文件上传失败，请重新上传")
            return
        except Exception as e:
            logger.error(f"❌ LlamaIndex add_document 失败: {e}")
            # 尝试从索引中删除可能已添加的数据
            try:
                if retriever:
                    retriever.delete_by_document_id(doc_id)
                    logger.info(f"已尝试从索引中删除失败的文档: {doc_id}")
            except Exception as cleanup_err:
                logger.warning(f"清理索引数据失败: {cleanup_err}")
            # 清理失败的上传
            await cleanup_failed_upload(doc_id, file_path)
            await update_document_status(doc_id, 'failed',
                                        processing_completed=datetime.now().isoformat(),
                                        error_message=f"文档处理失败: {str(e)}，请重新上传")
            task_queue.fail_task(task_id, f"文档处理失败: {str(e)}，文件上传失败，请重新上传")
            return
        finally:
            logger.info(f"🔧 LlamaIndex add_document 结束，added_count={added_count}")

        # 持久化也加入超时与心跳
        logger.info("💾 开始持久化索引到存储目录")
        persist_task = _asyncio.create_task(_asyncio.to_thread(retriever.index.storage_context.persist, persist_dir=str(retriever.storage_dir)))
        persist_wait = 0
        try:
            while True:
                try:
                    await _asyncio.wait_for(persist_task, timeout=30)
                    break
                except _asyncio.TimeoutError:
                    persist_wait += 30
                    task_queue.update_task_progress(
                        task_id,
                        TaskStage.INDEXING,
                        90,
                        f"持久化索引中... 已等待 {persist_wait}s"
                    )
                    logger.info(f"⏳ persist 心跳: 等待 {persist_wait}s")
                    if persist_wait >= 600:
                        raise _asyncio.TimeoutError()
        except _asyncio.TimeoutError:
            logger.error("⏰ 持久化索引超时(600s)")
            # 尝试从索引中删除已添加的数据
            try:
                if retriever:
                    retriever.delete_by_document_id(doc_id)
                    logger.info(f"已尝试从索引中删除持久化超时的文档: {doc_id}")
            except Exception as cleanup_err:
                logger.warning(f"清理索引数据失败: {cleanup_err}")
            # 清理失败的上传
            await cleanup_failed_upload(doc_id, file_path)
            await update_document_status(doc_id, 'failed', 
                                        processing_completed=datetime.now().isoformat(),
                                        error_message="索引持久化超时(600秒)，请重新上传")
            task_queue.fail_task(task_id, "索引持久化超时(600秒)，文件上传失败，请重新上传")
            return
        success = bool(added_count)
        
        if success:
            logger.info(f"✅ 文档解析和向量化成功: {document_data['original_filename']}，新增 {added_count} 个节点")
            
            # 统计新增节点数 & 收集node_id列表
            chunk_count = int(added_count) if added_count else 0
            try:
                node_ids = retriever.get_node_ids_by_document_id(doc_id)
            except Exception:
                node_ids = []
            chunk_ids = list(node_ids)
            
            # 阶段4: 索引构建 (80-100%)
            task_queue.update_task_progress(
                task_id, 
                TaskStage.INDEXING, 
                90, 
                "正在建立索引..."
            )
            
            await asyncio.sleep(0.5)
            
            # 更新索引：添加文件信息
            file_index_manager.add_file(
                file_id=doc_id,
                filename=document_data['filename'],
                original_filename=document_data['original_filename'],
                chunk_ids=chunk_ids,
                file_size=document_data['file_size'],
                file_type=document_data['mime_type'],
                file_path=str(file_path),
                upload_time=document_data['created_at']
            )
            
            # 更新状态为处理完成
            await update_document_status(
                doc_id, 
                'completed', 
                processing_completed=datetime.now().isoformat(),
                chunk_count=chunk_count,
                node_ids=chunk_ids,
                quality_score=0.8  # 可以根据实际处理结果调整
            )
            
            # 完成任务
            task_queue.complete_task(task_id, {
                'chunk_count': chunk_count,
                'document_id': doc_id
            })
            
            logger.info(f"🎉 文档处理完成: {document_data['original_filename']}, 生成 {chunk_count} 个向量块")
            
        else:
            logger.warning(f"❌ 文档处理失败: {document_data['original_filename']}")
            await update_document_status(doc_id, 'failed', processing_completed=datetime.now().isoformat())
            task_queue.fail_task(task_id, "文档处理失败")
            
    except Exception as e:
        logger.error(f"❌ 带进度文档处理异常: {file_path}, 错误: {str(e)}", exc_info=True)
        doc_id = document_data.get('id')
        # 尝试从索引中删除可能已添加的数据
        try:
            # 尝试获取retriever（如果之前已经创建）
            try:
                from app.services.llamaindex_retriever import get_retriever
                retriever = get_retriever("global")
                if retriever and doc_id:
                    retriever.delete_by_document_id(doc_id)
                    logger.info(f"已尝试从索引中删除异常处理的文档: {doc_id}")
            except Exception:
                pass  # 如果获取retriever失败，忽略
        except Exception as cleanup_err:
            logger.warning(f"清理索引数据失败: {cleanup_err}")
        # 清理失败的上传
        if doc_id:
            await cleanup_failed_upload(doc_id, file_path)
            await update_document_status(doc_id, 'failed', 
                                        processing_completed=datetime.now().isoformat(),
                                        error_message=f"处理异常: {str(e)}，请重新上传")
        task_queue.fail_task(task_id, f"处理异常: {str(e)}，文件上传失败，请重新上传")

async def process_global_document_step_by_step(file_path: str, document_data: Dict[str, Any]):
    """分步处理全局文档：解析 -> LlamaIndex 导入 -> 持久化"""
    try:
        doc_id = document_data['id']
        logger.info(f"🚀 开始分步处理全局文档: {file_path}, ID: {doc_id}")
        
        # 第一步：更新状态为处理中
        await update_document_status(doc_id, 'processing', processing_started=datetime.now().isoformat())
        
        # 第二步：使用 LlamaIndex 处理文档
        try:
            from app.services.llamaindex_retriever import get_retriever
            logger.info(f"📄 开始解析文档: {document_data['original_filename']}")

            retriever = get_retriever("global")  # 使用缓存单例，避免重复加载模型和索引
            import asyncio as _asyncio
            logger.info(f"🔧[step] LlamaIndex add_document 开始: {file_path}")
            add_task = _asyncio.create_task(
                retriever.add_document(
                    file_path=file_path,
                    metadata={
                        'document_id': doc_id,
                        'original_filename': document_data['original_filename'],
                        'file_type': document_data['mime_type'],
                        'file_size': document_data['file_size'],
                        'upload_time': document_data['created_at']
                    }
                )
            )
            hb = 65
            waited = 0
            try:
                while True:
                    try:
                        added_count = await _asyncio.wait_for(add_task, timeout=30)
                        break
                    except _asyncio.TimeoutError:
                        waited += 30
                        logger.info(f"⏳[step] add_document 心跳: 等待 {waited}s, progress={hb}%")
                        hb = min(hb + 5, 85)
                        if waited >= 600:
                            raise _asyncio.TimeoutError()
            except _asyncio.TimeoutError:
                logger.error(f"⏰[step] LlamaIndex add_document 超时(600s): {file_path}")
                await update_document_status(doc_id, 'failed', processing_completed=datetime.now().isoformat())
                return
            except Exception as e:
                logger.error(f"❌[step] LlamaIndex add_document 失败: {e}")
                await update_document_status(doc_id, 'failed', processing_completed=datetime.now().isoformat())
                return
            finally:
                logger.info("🔧[step] LlamaIndex add_document 结束")
            # 持久化
            logger.info("💾[step] 开始持久化索引到存储目录")
            persist_task = _asyncio.create_task(_asyncio.to_thread(retriever.index.storage_context.persist, persist_dir=str(retriever.storage_dir)))
            waited_persist = 0
            try:
                while True:
                    try:
                        await _asyncio.wait_for(persist_task, timeout=30)
                        break
                    except _asyncio.TimeoutError:
                        waited_persist += 30
                        logger.info(f"⏳[step] persist 心跳: 等待 {waited_persist}s")
                        if waited_persist >= 600:
                            raise _asyncio.TimeoutError()
            except _asyncio.TimeoutError:
                logger.error("⏰[step] 持久化索引超时(600s)")
                await update_document_status(doc_id, 'failed', processing_completed=datetime.now().isoformat())
                return

            if added_count:
                logger.info(f"✅ 文档解析和入库成功: {document_data['original_filename']}，新节点: {added_count}")
                # 简化：无法从 LlamaIndex 直接按 doc_id 统计 chunk 数；记录节点数即可
                chunk_count = int(added_count)
                chunk_ids = []

                # 更新索引：添加文件信息
                file_index_manager.add_file(
                    file_id=doc_id,
                    filename=document_data['filename'],
                    original_filename=document_data['original_filename'],
                    chunk_ids=chunk_ids,
                    file_size=document_data['file_size'],
                    file_type=document_data['mime_type'],
                    file_path=str(file_path),
                    upload_time=document_data['created_at']
                )
                
                # 第三步：更新状态为处理完成
                await update_document_status(
                    doc_id, 
                    'completed', 
                    processing_completed=datetime.now().isoformat(),
                    chunk_count=chunk_count,
                    quality_score=0.8  # 可以根据实际处理结果调整
                )
                
                logger.info(f"🎉 文档处理完成: {document_data['original_filename']}, 生成 {chunk_count} 个向量块")
                
                # 第四步：可选 - 删除原始文件以节省空间
                # await cleanup_original_file(file_path, doc_id)
                
            else:
                logger.warning(f"❌ 文档处理失败: {document_data['original_filename']}")
                await update_document_status(doc_id, 'failed', processing_completed=datetime.now().isoformat())
                
        except Exception as rag_error:
            logger.error(f"❌ RAG服务处理失败: {str(rag_error)}")
            await update_document_status(doc_id, 'failed', processing_completed=datetime.now().isoformat())
        
    except Exception as e:
        logger.error(f"❌ 全局文档处理异常: {file_path}, 错误: {str(e)}")
        await update_document_status(document_data['id'], 'failed', processing_completed=datetime.now().isoformat())

async def update_document_status(doc_id: str, status: str, **kwargs):
    """更新文档状态"""
    try:
        documents = load_global_documents()
        for doc in documents:
            if doc['id'] == doc_id:
                doc['status'] = status
                for key, value in kwargs.items():
                    doc[key] = value
                break
        save_global_documents(documents)
        logger.info(f"📝 文档状态已更新: {doc_id} -> {status}")
    except Exception as e:
        logger.error(f"更新文档状态失败: {str(e)}")

async def cleanup_failed_upload(doc_id: str, file_path: str):
    """清理失败的上传：删除JSON记录和物理文件"""
    try:
        logger.info(f"🗑️ 开始清理失败的上传: doc_id={doc_id}, file_path={file_path}")
        
        # 1. 从JSON中删除文档记录
        documents = load_global_documents()
        original_count = len(documents)
        documents = [doc for doc in documents if doc.get('id') != doc_id]
        if len(documents) < original_count:
            save_global_documents(documents)
            logger.info(f"✅ 已从JSON中删除文档记录: {doc_id}")
        else:
            logger.warning(f"⚠️ JSON中未找到文档记录: {doc_id}")
        
        # 2. 删除物理文件
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"✅ 已删除物理文件: {file_path}")
            except Exception as file_err:
                logger.error(f"删除物理文件失败: {file_path}, 错误: {file_err}")
        else:
            logger.warning(f"⚠️ 文件不存在或路径为空: {file_path}")
        
        # 3. 从文件索引中删除（如果存在）
        try:
            file_index_manager.remove_file(doc_id)
            logger.info(f"✅ 已从文件索引中删除: {doc_id}")
        except Exception as index_err:
            logger.warning(f"从文件索引删除失败（可能不存在）: {index_err}")
        
        logger.info(f"✅ 清理失败上传完成: {doc_id}")
    except Exception as e:
        logger.error(f"清理失败上传时发生错误: {str(e)}", exc_info=True)

async def cleanup_original_file(file_path: str, doc_id: str):
    """清理原始文件（可选）"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"🗑️ 已删除原始文件: {file_path}")
            
            # 更新文档记录
            documents = load_global_documents()
            for doc in documents:
                if doc['id'] == doc_id:
                    doc['original_file_deleted'] = True
                    doc['file_path'] = None  # 清空文件路径
                    break
            save_global_documents(documents)
    except Exception as e:
        logger.error(f"清理原始文件失败: {str(e)}")


@router.get("/documents/status/{doc_id}")
async def get_document_status(doc_id: str):
    """获取文档处理状态"""
    try:
        documents = load_global_documents()
        for doc in documents:
            if doc['id'] == doc_id:
                return {
                    "id": doc_id,
                    "status": doc.get('status', 'unknown'),
                    "original_filename": doc.get('original_filename', ''),
                    "processing_started": doc.get('processing_started'),
                    "processing_completed": doc.get('processing_completed'),
                    "chunk_count": doc.get('chunk_count', 0),
                    "quality_score": doc.get('quality_score', 0.0),
                    "file_size": doc.get('file_size', 0),
                    "created_at": doc.get('created_at')
                }
        
        raise HTTPException(status_code=404, detail="文档未找到")
    except Exception as e:
        logger.error(f"获取文档状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

@router.get("/documents")
async def list_global_documents():
    """列出所有全局文档（只从JSON文件，快速返回）"""
    try:
        # 从 LlamaIndex 向量库加载（新格式）
        vector_documents = []
        try:
            llamaindex_storage_dir = Path("llamaindex_storage/global")
            docstore_file = llamaindex_storage_dir / "docstore.json"
            
            if docstore_file.exists():
                import json
                with open(docstore_file, 'r', encoding='utf-8') as f:
                    docstore_data = json.load(f)
                
                # 解析 LlamaIndex 格式的 docstore
                file_groups = {}
                nodes = docstore_data.get('docstore/data', {})
                
                for node_id, node_data in nodes.items():
                    data = node_data.get('__data__', {})
                    metadata = data.get('metadata', {})
                    
                    original_filename = metadata.get('original_filename') or metadata.get('file_name', f"文档_{node_id[:8]}")
                    
                    if original_filename not in file_groups:
                        file_groups[original_filename] = {
                            "id": node_id,
                            "filename": original_filename,
                            "original_filename": original_filename,
                            "file_size": metadata.get('file_size', 0),
                            "file_type": metadata.get('file_type', metadata.get('mime_type', '')),
                            "status": "completed",
                            "created_at": metadata.get('upload_time', metadata.get('creation_date', '')),
                            "chunk_count": 1
                        }
                    else:
                        file_groups[original_filename]["chunk_count"] += 1
                
                vector_documents = list(file_groups.values())
                logger.info(f"✅ 从 LlamaIndex 向量库加载了 {len(vector_documents)} 个文档")
        except Exception as e:
            logger.warning(f"⚠️ 从 LlamaIndex 加载失败: {e}，使用备用方法")
        
        # 从JSON文件加载
        json_documents = load_global_documents()
        
        # 合并两个数据源，去重（优先使用向量数据库的数据）
        result_map = {}
        
        # 先添加向量数据库中的文档
        for doc in vector_documents:
            key = doc.get('original_filename', '')
            if key not in result_map:
                result_map[key] = doc
        
        # 再添加JSON文件中不存在于向量数据库的文档
        for doc in json_documents:
            # 跳过归档文件记录（兼容历史数据，新上传的归档文件不会写入JSON）
            if doc.get('is_archive', False):
                continue
                
            key = doc.get('original_filename', '')
            if key not in result_map:
                result_map[key] = {
                    "id": doc.get('id', ''),
                    "filename": doc.get('filename', ''),
                    "original_filename": doc.get('original_filename', ''),
                    "file_size": doc.get('file_size', 0),
                    "file_type": doc.get('file_type', ''),
                    "status": doc.get('status', 'completed'),
                    "created_at": doc.get('created_at', ''),
                    "chunk_count": doc.get('chunk_count', 0),
                    # 添加chunk_ids字段，使用id作为第一个chunk ID
                    "chunk_ids": [doc.get('id', '')]
                }
        
        result_documents = list(result_map.values())
        
        logger.info(f"全局文档列表: 向量数据库 {len(vector_documents)} 个，JSON文件 {len(json_documents)} 个，合并后 {len(result_documents)} 个")
        
        return {
            "documents": result_documents,
            "total_count": len(result_documents),
            "message": f"全局文档列表（向量数据库: {len(vector_documents)}, JSON: {len(json_documents)}）"
        }
    except Exception as e:
        logger.error(f"获取全局文档列表失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/search")
async def search_global_documents(
    request: Dict[str, Any]
):
    """搜索全局文档"""
    try:
        # 开始性能计时
        start_time = performance_optimizer.start_search_timer()
        
        query = request.get('query', '')
        workspace_id = request.get('workspace_id')
        top_k = request.get('top_k', 5)
        
        # 检查缓存
        cached_result = performance_optimizer.get_cached_search_result(query, workspace_id or "global")
        if cached_result:
            logger.info(f"使用缓存搜索结果: {query}")
            return cached_result
        
        documents = load_global_documents()
        
        # 使用RAG服务进行真正的文档搜索
        results = []
        try:
            # 创建全局RAG服务实例
            global_rag = get_global_rag_service()
            
            # 使用RAG服务进行真正的文档搜索
            # 直接使用RAG服务的搜索功能，而不是问答功能
            logger.info(f"开始RAG搜索: {query}")
            search_results = await global_rag.ask_question(
                workspace_id="global",
                question=query,
                top_k=top_k
            )
            logger.info(f"RAG搜索完成，引用数量: {len(search_results.get('references', []))}")
            
            if search_results.get('references'):
                logger.info(f"处理 {len(search_results['references'])} 个引用")
                for ref in search_results['references']:
                    # 安全获取内容，处理不同的引用结构
                    content = ref.get('content', ref.get('page_content', ref.get('content_preview', '')))
                    logger.info(f"引用内容长度: {len(content)}")
                    if content:
                        results.append({
                            "content": content[:200] + "..." if len(content) > 200 else content,
                            "metadata": {
                                "document_id": ref.get('document_id', ''),
                                "chunk_id": ref.get('chunk_id', ''),
                                "similarity": ref.get('similarity', 0.0),
                                "original_filename": ref.get('metadata', {}).get('original_filename', '计网.pdf')
                            },
                            "similarity": ref.get('similarity', 0.0)
                        })
                        logger.info(f"添加结果，当前结果数量: {len(results)}")
            else:
                logger.warning("RAG搜索没有返回引用")
            
            # 如果没有找到内容，回退到文件名匹配
            if not results:
                for doc in documents:
                    if query.lower() in doc['original_filename'].lower():
                        results.append({
                            'content': f"文件名: {doc['original_filename']}",
                            'metadata': doc,
                            'similarity': 0.8
                        })
                        
        except Exception as rag_error:
            logger.warning(f"RAG搜索失败，回退到简单搜索: {str(rag_error)}")
            # 回退到简单搜索
            for doc in documents:
                if query.lower() in doc['original_filename'].lower():
                    results.append({
                        'content': f"文件名: {doc['original_filename']}",
                        'metadata': doc,
                        'similarity': 0.8
                    })
        
        search_result = {
            "query": query,
            "results": results[:top_k],
            "total_count": len(results),
            "workspace_id": workspace_id,
            "cached": False
        }
        
        # 缓存搜索结果
        performance_optimizer.cache_search_result(query, workspace_id or "global", search_result)
        
        # 结束性能计时
        search_time = performance_optimizer.end_search_timer(start_time)
        logger.info(f"搜索完成: {query}, 耗时: {search_time:.3f}s, 结果数: {len(results)}")
        
        return search_result
        
    except Exception as e:
        logger.error(f"全局文档搜索失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.post("/chat")
async def global_chat(
    request: Dict[str, Any]
):
    """全局问答"""
    try:
        question = request.get('question', '')
        workspace_id = request.get('workspace_id')
        top_k = request.get('top_k', 5)
        
        documents = load_global_documents()
        
        # 使用RAG服务进行真正的问答
        try:
            # 创建全局RAG服务实例
            global_rag = get_global_rag_service()
            
            # 使用RAG服务进行问答
            rag_result = await global_rag.ask_question(
                workspace_id="global",
                question=question,
                top_k=top_k
            )
            
            if rag_result.get('answer') and rag_result.get('references'):
                return {
                    "answer": rag_result['answer'],
                    "references": rag_result['references'],
                    "confidence": rag_result.get('confidence', 0.7),
                    "metadata": {
                        "mode": "global_rag",
                        "document_count": len(documents),
                        "workspace_id": workspace_id
                    }
                }
            else:
                # 回退到简单问答
                answer = f"根据全局文档库中的 {len(documents)} 个文档，我找到了相关信息。"
                if documents:
                    answer += f" 其中包括: {', '.join([doc['original_filename'] for doc in documents[:3]])}"
                
                return {
                    "answer": answer,
                    "references": [],
                    "confidence": 0.7,
                    "metadata": {
                        "mode": "global_simple",
                        "document_count": len(documents),
                        "workspace_id": workspace_id
                    }
                }
                
        except Exception as rag_error:
            logger.warning(f"RAG问答失败，回退到简单问答: {str(rag_error)}")
            # 回退到简单问答
            answer = f"根据全局文档库中的 {len(documents)} 个文档，我找到了相关信息。"
            if documents:
                answer += f" 其中包括: {', '.join([doc['original_filename'] for doc in documents[:3]])}"
            
            return {
                "answer": answer,
                "references": [],
                "confidence": 0.7,
                "metadata": {
                    "mode": "global_simple",
                    "document_count": len(documents),
                    "workspace_id": workspace_id
                }
            }
        
    except Exception as e:
        logger.error(f"全局问答失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"问答失败: {str(e)}")


@router.get("/stats")
async def get_global_stats():
    """获取全局统计信息"""
    try:
        documents = load_global_documents()
        workspaces = load_global_workspaces()
        
        stats = {
            'global_document_count': len(documents),
            'global_workspace_count': len(workspaces),
            'vector_store_available': False,  # 简化版暂时不可用
            'embedding_model': 'simplified'
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"获取全局统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


# 工作区管理API
@router.post("/workspaces")
async def create_workspace(
    name: str,
    description: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None
):
    """创建工作区"""
    try:
        workspace_id = str(uuid.uuid4())
        
        # 添加到持久化存储
        workspaces = load_global_workspaces()
        workspace_data = {
            "id": workspace_id,
            "name": name,
            "description": description,
            "settings": settings or {},
            "status": "active",
            "created_at": "2025-10-23T22:00:00Z"
        }
        workspaces.append(workspace_data)
        save_global_workspaces(workspaces)
        
        return workspace_data
        
    except Exception as e:
        logger.error(f"创建工作区失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.get("/workspaces")
async def list_workspaces():
    """列出所有工作区"""
    try:
        workspaces = load_global_workspaces()
        
        # 添加默认工作区
        if not workspaces:
            default_workspace = {
                "id": "1",
                "name": "默认工作区",
                "description": "包含所有全局文档的默认工作区",
                "status": "active",
                "document_count": 0,
                "created_at": "2025-10-23T22:00:00Z"
            }
            workspaces.append(default_workspace)
        
        return {
            "workspaces": workspaces,
            "total_count": len(workspaces)
        }
        
    except Exception as e:
        logger.error(f"获取工作区列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/workspaces/{workspace_id}/documents/{document_id}/access")
async def grant_document_access(
    workspace_id: str,
    document_id: str,
    access_level: str = "read"
):
    """授予工作区文档访问权限"""
    try:
        # 简化处理，直接返回成功
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
    document_id: str
):
    """撤销工作区文档访问权限"""
    try:
        # 简化处理，直接返回成功
        return {
            "workspace_id": workspace_id,
            "document_id": document_id,
            "status": "revoked"
        }
        
    except Exception as e:
        logger.error(f"撤销文档访问权限失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"撤销失败: {str(e)}")


# 性能优化API
@router.get("/performance/stats")
async def get_performance_stats():
    """获取性能统计信息"""
    try:
        stats = performance_optimizer.get_performance_stats()
        return stats
        
    except Exception as e:
        logger.error(f"获取性能统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


@router.post("/performance/optimize")
async def optimize_performance():
    """执行性能优化"""
    try:
        # 优化向量索引
        vector_db_path = "/root/consult/backend/global_db"
        optimization_result = performance_optimizer.optimize_vector_index(vector_db_path)
        
        # 清理过期缓存
        cleanup_result = performance_optimizer.clear_cache()
        
        return {
            "success": True,
            "message": "性能优化完成",
            "vector_optimization": optimization_result,
            "cache_cleanup": cleanup_result
        }
        
    except Exception as e:
        logger.error(f"性能优化失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"优化失败: {str(e)}")


@router.delete("/performance/cache")
async def clear_performance_cache(cache_type: str = None):
    """清理性能缓存"""
    try:
        result = performance_optimizer.clear_cache(cache_type)
        return result
        
    except Exception as e:
        logger.error(f"清理缓存失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清理失败: {str(e)}")


@router.get("/documents/{doc_id}/download")
async def download_global_document(doc_id: str):
    """下载全局文档"""
    try:
        from fastapi.responses import FileResponse
        
        # 查找文档文件路径
        rag_service = get_global_rag_service()
        vector_store = rag_service._load_vector_store("global")
        
        if vector_store and hasattr(vector_store, 'docstore'):
            docstore = vector_store.docstore
            if hasattr(docstore, '_dict') and doc_id in docstore._dict:
                doc = docstore._dict[doc_id]
                metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                file_path = metadata.get('file_path')
                
                if file_path and os.path.exists(file_path):
                    filename = metadata.get('original_filename', f"document_{doc_id[:8]}")
                    
                    return FileResponse(
                        path=file_path,
                        filename=filename,
                        media_type='application/octet-stream'
                    )
        
        raise HTTPException(status_code=404, detail="文档未找到")
        
    except Exception as e:
        logger.error(f"下载全局文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@router.delete("/documents/{doc_id}")
async def delete_global_document(doc_id: str):
    """删除全局文档"""
    import asyncio as _asyncio
    
    try:
        logger.info(f"收到删除全局文档请求: {doc_id}")
        
        # 1) 异步获取检索器（带超时）
        RETRIEVER_INIT_TIMEOUT = 120  # 检索器初始化超时时间（秒）
        DELETE_OPERATION_TIMEOUT = 300  # 删除操作超时时间（秒）
        
        def import_and_get_retriever():
            """在线程中执行导入和初始化，避免阻塞主事件循环"""
            try:
                from app.services.llamaindex_retriever import get_retriever
                logger.info(f"✅ LlamaIndexRetriever模块导入完成")
                retriever = get_retriever("global")
                logger.info(f"✅ LlamaIndexRetriever初始化完成")
                return retriever
            except Exception as e:
                logger.error(f"❌ LlamaIndexRetriever导入或初始化失败: {e}", exc_info=True)
                raise
        
        retriever = None
        try:
            loop = _asyncio.get_event_loop()
            logger.info(f"⏳ 开始获取检索器实例（最多等待{RETRIEVER_INIT_TIMEOUT}秒）...")
            retriever = await _asyncio.wait_for(
                loop.run_in_executor(None, import_and_get_retriever),
                timeout=RETRIEVER_INIT_TIMEOUT
            )
            logger.info(f"✅ 检索器实例获取成功")
        except _asyncio.TimeoutError:
            logger.error(f"⏰ 获取检索器超时({RETRIEVER_INIT_TIMEOUT}秒)")
            raise HTTPException(
                status_code=504,
                detail=f"获取检索器超时({RETRIEVER_INIT_TIMEOUT}秒)，请稍后重试"
            )
        except Exception as e:
            logger.error(f"❌ 获取检索器失败: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"获取检索器失败: {str(e)}"
            )
        
        # 2) 异步执行删除操作（带超时）
        def delete_operation():
            """在线程中执行删除操作"""
            try:
                logger.info(f"开始执行删除操作: document_id={doc_id}")
                res = retriever.delete_by_document_id(doc_id)
                logger.info(f"删除操作完成: deleted={res.get('deleted', 0)}")
                return res
            except Exception as e:
                logger.error(f"删除操作失败: {e}", exc_info=True)
                raise
        
        res = None
        try:
            logger.info(f"⏳ 开始删除操作（最多等待{DELETE_OPERATION_TIMEOUT}秒）...")
            res = await _asyncio.wait_for(
                loop.run_in_executor(None, delete_operation),
                timeout=DELETE_OPERATION_TIMEOUT
            )
            logger.info(f"✅ 删除操作成功完成")
        except _asyncio.TimeoutError:
            logger.error(f"⏰ 删除操作超时({DELETE_OPERATION_TIMEOUT}秒)")
            raise HTTPException(
                status_code=504,
                detail=f"删除操作超时({DELETE_OPERATION_TIMEOUT}秒)，索引可能较大，请稍后重试或联系管理员"
            )
        except Exception as e:
            logger.error(f"❌ 删除操作失败: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"删除操作失败: {str(e)}"
            )
        
        deleted = res.get("deleted", 0) if res else 0
        
        # 2) 找出 original_filename 以同步业务 JSON 与物理文件删除
        original_filename = None
        file_path = None
        try:
            ds = getattr(retriever.index.storage_context, 'docstore', None)
            nodes_map = getattr(ds, 'docs', None) or getattr(ds, '_docstore', None) or getattr(ds, '_dict', None) or {}
            # 若按 doc_id 未命中，需要从旧的存储读取元数据（回退逻辑：直接扫描存储文件较重，这里保持轻量行为）
        except Exception:
            nodes_map = {}
        
        # 2) 如果索引中未找到，尝试按文件名删除（可能 document_id 设置不正确）
        if deleted == 0:
            # 先从JSON中获取文件名
            documents = load_global_documents()
            for doc in documents:
                if doc.get('id') == doc_id:
                    original_filename = doc.get('original_filename') or original_filename
                    file_path = doc.get('file_path') or file_path
                    break
            
            # 尝试按文件名删除（异步执行）
            if original_filename:
                logger.warning(f"按 document_id={doc_id} 未在索引中找到，尝试按文件名删除: {original_filename}")
                def delete_by_filename_operation():
                    """在线程中执行按文件名删除操作"""
                    try:
                        logger.info(f"开始按文件名删除操作: filename={original_filename}")
                        res2 = retriever.delete_by_original_filename(original_filename)
                        logger.info(f"按文件名删除操作完成: deleted={res2.get('deleted', 0)}")
                        return res2
                    except Exception as e:
                        logger.error(f"按文件名删除操作失败: {e}", exc_info=True)
                        raise
                
                try:
                    res2 = await _asyncio.wait_for(
                        loop.run_in_executor(None, delete_by_filename_operation),
                        timeout=DELETE_OPERATION_TIMEOUT
                    )
                    deleted = max(deleted, res2.get("deleted", 0))
                    if deleted > 0:
                        logger.info(f"通过文件名删除成功，删除了 {deleted} 个节点")
                except _asyncio.TimeoutError:
                    logger.warning(f"按文件名删除操作超时({DELETE_OPERATION_TIMEOUT}秒)")
                except Exception as e:
                    logger.warning(f"按文件名删除操作失败: {e}")
            
            # 如果仍然未找到，可能是索引创建有问题
            if deleted == 0:
                logger.error(f"⚠️ 文档 {doc_id} 在索引中未找到！这可能表示索引创建时未正确设置 document_id。")
                logger.error(f"请检查上传文档时的日志，确认 metadata 中的 document_id 是否正确设置。")
                # 但仍然尝试清理其他数据
                logger.warning(f"将尝试清理 JSON、文件索引和物理文件...")
        
        # 3) 获取完整的文档信息（用于后续清理）
        if not original_filename or not file_path:
            documents = load_global_documents()
            for doc in documents:
                if doc.get('id') == doc_id:
                    original_filename = doc.get('original_filename') or original_filename
                    file_path = doc.get('file_path') or file_path
                    break
        
        # 4) 删除物理文件
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"成功删除物理文件: {file_path}")
            except Exception as e:
                logger.warning(f"删除物理文件失败: {str(e)}")
        
        # 5) 从文件索引移除
        file_index_removed = False
        try:
            documents_for_index = load_global_documents()
            for doc in documents_for_index:
                if doc.get('id') == doc_id:
                    file_index_manager.remove_file(doc_id)
                    file_index_removed = True
                    logger.info(f"从文件索引删除: {doc_id}")
                    break
                # 如果通过文件名匹配
                elif original_filename and doc.get('original_filename') == original_filename:
                    file_index_manager.remove_file(doc.get('id'))
                    file_index_removed = True
                    logger.info(f"从文件索引删除（按文件名）: {original_filename}")
                    break
        except Exception as e:
            logger.warning(f"从文件索引删除失败: {str(e)}")
        
        # 6) 从 JSON 中删除记录
        documents = load_global_documents()
        before = len(documents)
        if original_filename:
            documents = [d for d in documents if d.get('original_filename') != original_filename]
        else:
            documents = [d for d in documents if d.get('id') != doc_id]
        save_global_documents(documents)
        after = len(documents)
        json_deleted_count = before - after
        if json_deleted_count > 0:
            logger.info(f"从JSON中删除了 {json_deleted_count} 条记录")
        
        # 7) 如果索引中未找到，这是主要问题
        if deleted == 0:
            logger.error(f"❌ 删除失败：文档 {doc_id} 在向量索引中未找到！")
            logger.error(f"这可能是因为：")
            logger.error(f"  1. 上传时 metadata 中的 document_id 未正确设置")
            logger.error(f"  2. 索引创建或持久化时出现问题")
            logger.error(f"  3. 索引加载时节点 metadata 丢失")
            logger.error(f"已清理 JSON 和文件系统数据（{json_deleted_count} 条JSON记录，文件索引: {file_index_removed}）")
            raise HTTPException(
                status_code=404, 
                detail=f"文档在索引中未找到（document_id={doc_id}）。已清理其他数据，但索引可能需要重建。"
            )
        
        return {
            "status": "deleted",
            "id": doc_id,
            "filename": original_filename,
            "deleted_nodes": deleted,
            "message": "文档已从索引、JSON、文件索引和物理文件中删除"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除全局文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.delete("/documents/by-filename")
async def delete_global_document_by_filename(filename: str):
    """按原始文件名删除全局文档并持久化索引。"""
    import asyncio as _asyncio
    
    try:
        if not filename:
            raise HTTPException(status_code=400, detail="缺少文件名")

        logger.info(f"收到按文件名删除全局文档请求: {filename}")

        # 1) 异步获取检索器（带超时）
        RETRIEVER_INIT_TIMEOUT = 120  # 检索器初始化超时时间（秒）
        DELETE_OPERATION_TIMEOUT = 300  # 删除操作超时时间（秒）
        
        def import_and_get_retriever():
            """在线程中执行导入和初始化，避免阻塞主事件循环"""
            try:
                from app.services.llamaindex_retriever import get_retriever
                logger.info(f"✅ LlamaIndexRetriever模块导入完成")
                retriever = get_retriever("global")
                logger.info(f"✅ LlamaIndexRetriever初始化完成")
                return retriever
            except Exception as e:
                logger.error(f"❌ LlamaIndexRetriever导入或初始化失败: {e}", exc_info=True)
                raise
        
        retriever = None
        try:
            loop = _asyncio.get_event_loop()
            logger.info(f"⏳ 开始获取检索器实例（最多等待{RETRIEVER_INIT_TIMEOUT}秒）...")
            retriever = await _asyncio.wait_for(
                loop.run_in_executor(None, import_and_get_retriever),
                timeout=RETRIEVER_INIT_TIMEOUT
            )
            logger.info(f"✅ 检索器实例获取成功")
        except _asyncio.TimeoutError:
            logger.error(f"⏰ 获取检索器超时({RETRIEVER_INIT_TIMEOUT}秒)")
            raise HTTPException(
                status_code=504,
                detail=f"获取检索器超时({RETRIEVER_INIT_TIMEOUT}秒)，请稍后重试"
            )
        except Exception as e:
            logger.error(f"❌ 获取检索器失败: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"获取检索器失败: {str(e)}"
            )

        # 2) 异步执行删除操作（带超时）
        def delete_by_filename_operation():
            """在线程中执行按文件名删除操作"""
            try:
                logger.info(f"开始执行按文件名删除操作: filename={filename}")
                res = retriever.delete_by_original_filename(filename)
                logger.info(f"按文件名删除操作完成: deleted={res.get('deleted', 0)}")
                return res
            except Exception as e:
                logger.error(f"按文件名删除操作失败: {e}", exc_info=True)
                raise
        
        res = None
        try:
            logger.info(f"⏳ 开始按文件名删除操作（最多等待{DELETE_OPERATION_TIMEOUT}秒）...")
            res = await _asyncio.wait_for(
                loop.run_in_executor(None, delete_by_filename_operation),
                timeout=DELETE_OPERATION_TIMEOUT
            )
            logger.info(f"✅ 按文件名删除操作成功完成")
        except _asyncio.TimeoutError:
            logger.error(f"⏰ 按文件名删除操作超时({DELETE_OPERATION_TIMEOUT}秒)")
            raise HTTPException(
                status_code=504,
                detail=f"删除操作超时({DELETE_OPERATION_TIMEOUT}秒)，索引可能较大，请稍后重试或联系管理员"
            )
        except Exception as e:
            logger.error(f"❌ 按文件名删除操作失败: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"删除操作失败: {str(e)}"
            )
        
        deleted = res.get("deleted", 0) if res else 0

        if deleted == 0:
            logger.warning(f"按文件名未命中: {filename}")
            raise HTTPException(status_code=404, detail="文档未在索引中找到")

        # 2) 删除物理文件与 file_index_manager
        documents = load_global_documents()
        removed_files = []
        try:
            for doc in documents:
                if doc.get('original_filename') == filename:
                    fid = doc.get('id')
                    fpath = doc.get('file_path')
                    if fpath and os.path.exists(fpath):
                        try:
                            os.remove(fpath)
                            removed_files.append(fpath)
                        except Exception as e:
                            logger.warning(f"删除物理文件失败: {fpath}, {e}")
                    try:
                        file_index_manager.remove_file(fid)
                    except Exception as e:
                        logger.warning(f"从索引删除失败: {e}")
        except Exception as e:
            logger.warning(f"删除相关物理文件或索引失败: {e}")

        # 3) 过滤并保存 JSON 记录
        before = len(documents)
        documents = [d for d in documents if d.get('original_filename') != filename]
        save_global_documents(documents)
        after = len(documents)
        logger.info(f"从JSON中删除了 {before - after} 条记录，文件: {filename}")

        return {
            "status": "deleted",
            "filename": filename,
            "deleted_nodes": deleted,
            "removed_files": removed_files
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"按文件名删除失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/rebuild-index")
async def rebuild_file_index():
    """重建文件索引（用于数据恢复）"""
    try:
        logger.info("开始重建文件索引...")
        
        rag_service = get_global_rag_service()
        vector_store = rag_service._load_vector_store("global")
        
        # 重建索引
        file_index_manager.rebuild_index_from_vector_store(vector_store)
        
        # 获取重建后的统计信息
        file_count = file_index_manager.get_file_count()
        files = file_index_manager.list_files()
        
        total_chunks = sum(file_info.get("chunk_count", 0) for file_info in files)
        
        logger.info(f"索引重建完成: {file_count} 个文件, {total_chunks} 个块")
        
        return {
            "status": "success",
            "message": "文件索引重建完成",
            "file_count": file_count,
            "total_chunks": total_chunks,
            "files": files
        }
        
    except Exception as e:
        logger.error(f"重建文件索引失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重建索引失败: {str(e)}")


@router.get("/index-status")
async def get_index_status():
    """获取索引状态"""
    try:
        file_count = file_index_manager.get_file_count()
        files = file_index_manager.list_files()
        
        total_chunks = sum(file_info.get("chunk_count", 0) for file_info in files)
        total_size = sum(file_info.get("file_size", 0) for file_info in files)
        
        return {
            "file_count": file_count,
            "total_chunks": total_chunks,
            "total_size": total_size,
            "index_file": str(file_index_manager.index_file),
            "files": files
        }
        
    except Exception as e:
        logger.error(f"获取索引状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")
