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

# 持久化存储路径（从配置中获取）
from app.core.config import settings

GLOBAL_DATA_DIR = Path(settings.GLOBAL_DATA_PATH)
GLOBAL_DOCUMENTS_FILE = GLOBAL_DATA_DIR / "documents.json"
GLOBAL_WORKSPACES_FILE = GLOBAL_DATA_DIR / "workspaces.json"

# 确保目录存在
GLOBAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

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
        allowed_extensions = [
            '.pdf', '.docx', '.doc', '.txt', '.md', '.zip', '.rar',
            '.xlsx', '.xls', '.pptx', '.ppt',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'
        ]
        
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
            logger.info(f"还没开始process_zip_async函数")
            # 使用app_simple.py中的process_zip_async函数
            from app_simple import process_zip_async
            import asyncio
            asyncio.create_task(process_zip_async(task_id, str(file_path), "global"))
            logger.info(f"已经完成了process_zip_async函数")
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
            "正在生成向量..."
        )
        
        # 使用 LlamaIndex 导入（增加超时、心跳与细粒度日志）
        logger.info(f"import 之前")
        from app.services.llamaindex_retriever import LlamaIndexRetriever
        logger.info(f"import 之后")
        import asyncio as _asyncio
        retriever = LlamaIndexRetriever.get_instance("global")
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
            await update_document_status(doc_id, 'failed', processing_completed=datetime.now().isoformat())
            task_queue.fail_task(task_id, "LlamaIndex add_document 超时(600s)")
            return
        except Exception as e:
            logger.error(f"❌ LlamaIndex add_document 失败: {e}")
            await update_document_status(doc_id, 'failed', processing_completed=datetime.now().isoformat())
            task_queue.fail_task(task_id, f"LlamaIndex 失败: {str(e)}")
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
            await update_document_status(doc_id, 'failed', processing_completed=datetime.now().isoformat())
            task_queue.fail_task(task_id, "持久化索引超时(600s)")
            return
        success = bool(added_count)
        
        if success:
            logger.info(f"✅ 文档解析和向量化成功: {document_data['original_filename']}，新增 {added_count} 个节点")
            
            # 统计新增节点数
            chunk_count = int(added_count) if added_count else 0
            chunk_ids = []
            
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
        logger.error(f"❌ 带进度文档处理异常: {file_path}, 错误: {str(e)}")
        await update_document_status(document_data['id'], 'failed', processing_completed=datetime.now().isoformat())
        task_queue.fail_task(task_id, str(e))

async def process_global_document_step_by_step(file_path: str, document_data: Dict[str, Any]):
    """分步处理全局文档：解析 -> LlamaIndex 导入 -> 持久化"""
    try:
        doc_id = document_data['id']
        logger.info(f"🚀 开始分步处理全局文档: {file_path}, ID: {doc_id}")
        
        # 第一步：更新状态为处理中
        await update_document_status(doc_id, 'processing', processing_started=datetime.now().isoformat())
        
        # 第二步：使用 LlamaIndex 处理文档
        try:
            from app.services.llamaindex_retriever import LlamaIndexRetriever
            logger.info(f"📄 开始解析文档: {document_data['original_filename']}")

            retriever = LlamaIndexRetriever.get_instance("global")
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
            from app.core.config import settings
            llamaindex_storage_dir = Path(settings.LLAMAINDEX_STORAGE_PATH) / "global"
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
        from app.core.config import settings
        vector_db_path = settings.LANGCHAIN_VECTOR_DB_PATH
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
    try:
        logger.info(f"收到删除全局文档请求: {doc_id}")
        
        # 从 LlamaIndex 向量库中查找匹配的文档
        original_filename = None
        all_node_ids = []
        file_path = None
        
        from app.core.config import settings
        llamaindex_storage_dir = Path(settings.LLAMAINDEX_STORAGE_PATH) / "global"
        docstore_file = llamaindex_storage_dir / "docstore.json"
        
        if docstore_file.exists():
            import json
            with open(docstore_file, 'r', encoding='utf-8') as f:
                docstore_data = json.load(f)
            
            nodes = docstore_data.get('docstore/data', {})
            
            # 查找匹配的文档
            for node_id, node_data in nodes.items():
                data = node_data.get('__data__', {})
                metadata = data.get('metadata', {})
                
                # 检查是否为匹配的节点
                if node_id == doc_id or metadata.get('document_id') == doc_id:
                    original_filename = metadata.get('original_filename') or metadata.get('file_name', '未知文档')
                    file_path = metadata.get('file_path', '')
                    
                    # 找到所有属于这个文档的节点
                    for nid, ndata in nodes.items():
                        nd = ndata.get('__data__', {})
                        nmeta = nd.get('metadata', {})
                        nfilename = nmeta.get('original_filename') or nmeta.get('file_name', '')
                        
                        if nfilename == original_filename:
                            all_node_ids.append(nid)
                    break
        
        logger.info(f"找到文件: {original_filename}, nodes: {len(all_node_ids)}")
        
        if not original_filename:
            logger.warning(f"文档 {doc_id} 在向量数据库中未找到")
            raise HTTPException(status_code=404, detail="文档未找到")
        
        # 从 LlamaIndex 向量存储中删除所有相关节点
        deleted_count = 0
        try:
            # 加载 LlamaIndex 索引
            from app.services.llamaindex_retriever import LlamaIndexRetriever
            retriever = LlamaIndexRetriever.get_instance("global")
            
            # 获取向量存储
            vector_store = retriever.index._vector_store if hasattr(retriever.index, '_vector_store') else None
            
            # 删除所有相关节点
            for node_id in all_node_ids:
                # 从 docstore 删除
                if hasattr(retriever.index, '_docstore') and retriever.index._docstore:
                    retriever.index._docstore.delete_document(node_id, raise_error=False)
                    deleted_count += 1
                    logger.debug(f"删除节点: {node_id}")
                
                # 从向量存储删除
                if vector_store and hasattr(vector_store, '_data'):
                    if node_id in vector_store._data.embedding_dict:
                        del vector_store._data.embedding_dict[node_id]
                        logger.debug(f"从向量存储删除节点: {node_id}")
                    if node_id in vector_store._data.text_id_to_ref_doc_id:
                        del vector_store._data.text_id_to_ref_doc_id[node_id]
                    if node_id in vector_store._data.metadata_dict:
                        del vector_store._data.metadata_dict[node_id]
                
                # 从 index_store 删除
                if hasattr(retriever.index, '_index_struct') and hasattr(retriever.index._index_struct, 'nodes_dict'):
                    if node_id in retriever.index._index_struct.nodes_dict:
                        del retriever.index._index_struct.nodes_dict[node_id]
            
            # 持久化更改
            retriever.index.storage_context.persist(persist_dir=str(retriever.storage_dir))
            logger.info(f"成功删除 {deleted_count} 个节点并持久化")
        except Exception as e:
            logger.error(f"删除节点失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # 删除物理文件
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"成功删除物理文件: {file_path}")
            except Exception as e:
                logger.warning(f"删除物理文件失败: {str(e)}")
        
        # 从 file_index_manager 中删除（如果存在）
        try:
            # 查找文档的原始 ID
            documents = load_global_documents()
            for doc in documents:
                if doc.get('original_filename') == original_filename:
                    file_index_manager.remove_file(doc.get('id'))
                    break
        except Exception as e:
            logger.warning(f"从索引删除失败: {str(e)}")
        
        # 从 JSON 文件中删除记录
        documents = load_global_documents()
        documents_before = len(documents)
        
        # 删除所有同名文件记录
        documents = [doc for doc in documents if doc.get('original_filename') != original_filename]
        
        documents_after = len(documents)
        removed_from_json = documents_before - documents_after
        
        logger.info(f"从JSON中删除了 {removed_from_json} 条记录")
        
        # 保存更新后的文档列表
        save_global_documents(documents)
        
        logger.info(f"文档删除完成: {original_filename}")
        
        return {
            "status": "deleted",
            "id": doc_id,
            "filename": original_filename,
            "message": f"文档 {original_filename} 已成功删除"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除全局文档失败: {str(e)}")
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
