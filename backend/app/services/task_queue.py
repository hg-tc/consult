"""
任务队列服务 - 异步任务管理和状态追踪
"""

import asyncio
import logging
import uuid
import time
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json

logger = logging.getLogger(__name__)

# 延迟导入，避免循环依赖
def get_parallel_processor():
    from .parallel_processor import get_parallel_processor
    return get_parallel_processor()

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskStage(Enum):
    """处理阶段枚举"""
    UPLOADING = "uploading"
    PARSING = "parsing"
    CHUNKING = "chunking"
    VECTORIZING = "vectorizing"
    INDEXING = "indexing"

@dataclass
class TaskProgress:
    """任务进度信息"""
    stage: TaskStage
    progress: int  # 0-100
    message: str
    details: Dict[str, Any] = None

@dataclass
class Task:
    """任务信息"""
    id: str
    task_type: str
    status: TaskStatus
    progress: TaskProgress
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None
    workspace_id: Optional[str] = None

class TaskQueue:
    """任务队列管理器"""
    
    def __init__(self, max_workers: int = 4, persistent_storage: bool = True):
        self.max_workers = max_workers
        self.persistent_storage = persistent_storage
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks: Dict[str, Task] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.task_callbacks: Dict[str, List[Callable]] = {}
        
        # 持久化存储路径
        self.storage_path = Path("/root/workspace/consult/backend/task_storage")
        self.storage_path.mkdir(exist_ok=True)
        
        # 并行处理器
        self.parallel_processor = None
        
        # 加载已存在的任务
        if persistent_storage:
            self._load_tasks()
    
    def _load_tasks(self):
        """从文件加载任务状态"""
        try:
            tasks_file = self.storage_path / "tasks.json"
            if tasks_file.exists():
                with open(tasks_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for task_data in data:
                        task = Task(
                            id=task_data['id'],
                            task_type=task_data['task_type'],
                            status=TaskStatus(task_data['status']),
                            progress=TaskProgress(
                                stage=TaskStage(task_data['progress']['stage']),
                                progress=task_data['progress']['progress'],
                                message=task_data['progress']['message'],
                                details=task_data['progress'].get('details', {})
                            ),
                            created_at=task_data['created_at'],
                            started_at=task_data.get('started_at'),
                            completed_at=task_data.get('completed_at'),
                            error_message=task_data.get('error_message'),
                            metadata=task_data.get('metadata', {}),
                            workspace_id=task_data.get('workspace_id')
                        )
                        self.tasks[task.id] = task
                logger.info(f"加载了 {len(self.tasks)} 个任务")
        except Exception as e:
            logger.error(f"加载任务失败: {e}")
    
    def _save_tasks(self):
        """保存任务状态到文件"""
        try:
            tasks_file = self.storage_path / "tasks.json"
            data = []
            for task in self.tasks.values():
                task_data = asdict(task)
                task_data['status'] = task.status.value
                task_data['progress']['stage'] = task.progress.stage.value
                data.append(task_data)
            
            with open(tasks_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存任务失败: {e}")
    
    def create_task(self, task_type: str, metadata: Dict[str, Any] = None, 
                   workspace_id: str = None) -> str:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            progress=TaskProgress(
                stage=TaskStage.UPLOADING,
                progress=0,
                message="任务已创建，等待处理"
            ),
            created_at=time.time(),
            metadata=metadata or {},
            workspace_id=workspace_id
        )
        
        self.tasks[task_id] = task
        self.task_callbacks[task_id] = []
        
        # 自动注册 WebSocket 回调
        try:
            from app.websocket.status_ws import manager
            self.add_task_callback(task_id, manager._broadcast_task_update)
        except ImportError:
            logger.warning("WebSocket 管理器不可用，跳过回调注册")
        
        if self.persistent_storage:
            self._save_tasks()
        
        logger.info(f"创建任务: {task_id} ({task_type})")
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务信息"""
        return self.tasks.get(task_id)
    
    def get_tasks_by_workspace(self, workspace_id: str) -> List[Task]:
        """获取指定工作区的任务"""
        return [task for task in self.tasks.values() 
                if task.workspace_id == workspace_id]
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """获取指定状态的任务"""
        return [task for task in self.tasks.values() if task.status == status]
    
    def update_task_progress(self, task_id: str, stage: TaskStage, 
                           progress: int, message: str, details: Dict[str, Any] = None):
        """更新任务进度"""
        if task_id not in self.tasks:
            logger.warning(f"任务不存在: {task_id}")
            return
        
        task = self.tasks[task_id]
        old_progress = task.progress.progress
        old_stage = task.progress.stage
        
        task.progress = TaskProgress(
            stage=stage,
            progress=progress,
            message=message,
            details=details or {}
        )
        
        logger.info(f"📊 更新任务进度: {task_id} - {stage.value} {progress}% - {message}")
        logger.debug(f"📊 进度变化: {old_stage.value} {old_progress}% -> {stage.value} {progress}%")
        
        # 触发回调（支持异步函数）
        callback_count = 0
        for callback in self.task_callbacks.get(task_id, []):
            try:
                callback_count += 1
                # 如果是协程函数，使用asyncio运行
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(task))
                else:
                    callback(task)
                logger.debug(f"📊 回调执行成功: {task_id} - 回调 {callback_count}")
            except Exception as e:
                logger.error(f"📊 任务回调失败: {task_id} - 回调 {callback_count} - {e}")
        
        logger.debug(f"📊 执行了 {callback_count} 个回调")
        
        if self.persistent_storage:
            self._save_tasks()
    
    def start_task(self, task_id: str):
        """开始执行任务"""
        if task_id not in self.tasks:
            logger.warning(f"任务不存在: {task_id}")
            return
        
        task = self.tasks[task_id]
        task.status = TaskStatus.PROCESSING
        task.started_at = time.time()
        
        if self.persistent_storage:
            self._save_tasks()
        
        logger.info(f"开始执行任务: {task_id}")
    
    def complete_task(self, task_id: str, result: Dict[str, Any] = None):
        """完成任务"""
        if task_id not in self.tasks:
            logger.warning(f"任务不存在: {task_id}")
            return
        
        task = self.tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()
        task.progress = TaskProgress(
            stage=TaskStage.INDEXING,
            progress=100,
            message="任务完成"
        )
        
        if result:
            task.metadata.update(result)
        
        if self.persistent_storage:
            self._save_tasks()
        
        logger.info(f"任务完成: {task_id}")
    
    def fail_task(self, task_id: str, error_message: str):
        """任务失败"""
        if task_id not in self.tasks:
            logger.warning(f"任务不存在: {task_id}")
            return
        
        task = self.tasks[task_id]
        task.status = TaskStatus.FAILED
        task.completed_at = time.time()
        task.error_message = error_message
        task.progress = TaskProgress(
            stage=task.progress.stage,
            progress=task.progress.progress,
            message=f"任务失败: {error_message}"
        )
        
        if self.persistent_storage:
            self._save_tasks()
        
        logger.error(f"任务失败: {task_id} - {error_message}")
    
    def cancel_task(self, task_id: str):
        """取消任务"""
        if task_id not in self.tasks:
            logger.warning(f"任务不存在: {task_id}")
            return
        
        task = self.tasks[task_id]
        task.status = TaskStatus.CANCELLED
        task.completed_at = time.time()
        
        # 取消正在运行的任务
        if task_id in self.running_tasks:
            self.running_tasks[task_id].cancel()
            del self.running_tasks[task_id]
        
        if self.persistent_storage:
            self._save_tasks()
        
        logger.info(f"任务已取消: {task_id}")
    
    def add_task_callback(self, task_id: str, callback: Callable[[Task], None]):
        """添加任务状态回调"""
        if task_id not in self.task_callbacks:
            self.task_callbacks[task_id] = []
        self.task_callbacks[task_id].append(callback)
    
    async def submit_task(self, task_id: str, func: Callable, *args, **kwargs):
        """提交任务到线程池执行"""
        if task_id not in self.tasks:
            logger.warning(f"任务不存在: {task_id}")
            return
        
        self.start_task(task_id)
        
        # 在线程池中执行任务
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(self.executor, func, *args, **kwargs)
        
        # 创建异步任务来监控执行
        async_task = asyncio.create_task(self._monitor_task(task_id, future))
        self.running_tasks[task_id] = async_task
        
        return async_task
    
    async def _monitor_task(self, task_id: str, future):
        """监控任务执行"""
        try:
            result = await future
            self.complete_task(task_id, {"result": result})
        except Exception as e:
            self.fail_task(task_id, str(e))
        finally:
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        stats = {
            "total_tasks": len(self.tasks),
            "pending": len(self.get_tasks_by_status(TaskStatus.PENDING)),
            "processing": len(self.get_tasks_by_status(TaskStatus.PROCESSING)),
            "completed": len(self.get_tasks_by_status(TaskStatus.COMPLETED)),
            "failed": len(self.get_tasks_by_status(TaskStatus.FAILED)),
            "cancelled": len(self.get_tasks_by_status(TaskStatus.CANCELLED)),
            "max_workers": self.max_workers,
            "running_tasks": len(self.running_tasks)
        }
        return stats
    
    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """清理旧任务"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        tasks_to_remove = []
        for task_id, task in self.tasks.items():
            if (task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED] 
                and task.completed_at 
                and current_time - task.completed_at > max_age_seconds):
                tasks_to_remove.append(task_id)
        
        for task_id in tasks_to_remove:
            del self.tasks[task_id]
            if task_id in self.task_callbacks:
                del self.task_callbacks[task_id]
        
        if tasks_to_remove and self.persistent_storage:
            self._save_tasks()
        
        logger.info(f"清理了 {len(tasks_to_remove)} 个旧任务")
        return len(tasks_to_remove)
    
    def _get_parallel_processor(self):
        """获取并行处理器实例"""
        if self.parallel_processor is None:
            self.parallel_processor = get_parallel_processor()
        return self.parallel_processor
    
    async def submit_parallel_tasks(self, task_ids: List[str]) -> List[str]:
        """提交多个任务进行并行处理"""
        try:
            processor = self._get_parallel_processor()
            
            # 准备并行处理任务
            parallel_tasks = []
            for task_id in task_ids:
                task = self.get_task(task_id)
                if not task or task.status != TaskStatus.PENDING:
                    continue
                
                # 创建并行处理任务
                from .parallel_processor import ProcessingTask
                parallel_task = ProcessingTask(
                    id=task_id,
                    task_type=task.task_type,
                    file_path=task.metadata.get('file_path', ''),
                    workspace_id=task.workspace_id or 'default',
                    metadata=task.metadata or {}
                )
                
                processor.add_task(parallel_task)
                parallel_tasks.append(task_id)
                
                # 更新任务状态
                self.start_task(task_id)
            
            if not parallel_tasks:
                logger.warning("没有可并行处理的任务")
                return []
            
            # 定义回调函数
            async def process_callback(result):
                task_id = result.task_id
                if result.success:
                    self.complete_task(task_id, {"result": result.result})
                else:
                    self.fail_task(task_id, result.error)
            
            # 开始并行处理
            logger.info(f"开始并行处理 {len(parallel_tasks)} 个任务")
            results = await processor.process_tasks(process_callback)
            
            logger.info(f"并行处理完成: {len(results)} 个结果")
            return parallel_tasks
            
        except Exception as e:
            logger.error(f"并行处理失败: {str(e)}")
            # 将所有任务标记为失败
            for task_id in task_ids:
                self.fail_task(task_id, f"并行处理失败: {str(e)}")
            return []
    
    def get_parallel_queue_status(self) -> Dict[str, Any]:
        """获取并行处理队列状态"""
        try:
            processor = self._get_parallel_processor()
            return processor.get_queue_status()
        except Exception as e:
            logger.error(f"获取并行队列状态失败: {e}")
            return {"error": str(e)}

# 全局任务队列实例
_task_queue_instance: Optional[TaskQueue] = None

def get_task_queue() -> TaskQueue:
    """获取全局任务队列实例"""
    global _task_queue_instance
    if _task_queue_instance is None:
        _task_queue_instance = TaskQueue(max_workers=4, persistent_storage=True)
    return _task_queue_instance
