"""
并行处理器 - 多任务并行处理优化
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import psutil

logger = logging.getLogger(__name__)

@dataclass
class ProcessingTask:
    """处理任务"""
    id: str
    task_type: str
    file_path: str
    workspace_id: str
    metadata: Dict[str, Any]
    priority: int = 0  # 优先级，数字越小优先级越高
    created_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()

@dataclass
class ProcessingResult:
    """处理结果"""
    task_id: str
    success: bool
    result: Any = None
    error: str = None
    processing_time: float = 0
    metadata: Dict[str, Any] = None

class ParallelProcessor:
    """并行处理器"""
    
    def __init__(self, max_workers: Optional[int] = None):
        # 根据CPU核心数确定最大工作线程数
        cpu_count = psutil.cpu_count()
        self.max_workers = max_workers or min(cpu_count * 2, 8)  # 限制最大8个线程
        
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.task_queue: List[ProcessingTask] = []
        self.running_tasks: Dict[str, Any] = {}
        self.completed_tasks: Dict[str, ProcessingResult] = {}
        
        # 资源监控
        self.memory_limit = psutil.virtual_memory().total * 0.8  # 80%内存限制
        self.cpu_limit = 90  # 90%CPU限制
        
        logger.info(f"并行处理器初始化: 最大工作线程={self.max_workers}, CPU核心={cpu_count}")
    
    def _check_resources(self) -> bool:
        """检查系统资源是否充足"""
        try:
            memory_usage = psutil.virtual_memory().percent
            cpu_usage = psutil.cpu_percent(interval=0.1)
            
            if memory_usage > 80:
                logger.warning(f"内存使用率过高: {memory_usage}%")
                return False
            
            if cpu_usage > self.cpu_limit:
                logger.warning(f"CPU使用率过高: {cpu_usage}%")
                return False
            
            return True
        except Exception as e:
            logger.error(f"资源检查失败: {e}")
            return True  # 如果检查失败，允许继续处理
    
    def _get_task_priority(self, task: ProcessingTask) -> int:
        """计算任务优先级"""
        # 小文件优先
        file_size = task.metadata.get('file_size', 0)
        if file_size < 1024 * 1024:  # 1MB以下
            return 1
        elif file_size < 10 * 1024 * 1024:  # 10MB以下
            return 2
        else:
            return 3
    
    def add_task(self, task: ProcessingTask) -> str:
        """添加处理任务"""
        # 设置优先级
        task.priority = self._get_task_priority(task)
        
        # 按优先级插入队列
        inserted = False
        for i, existing_task in enumerate(self.task_queue):
            if task.priority < existing_task.priority:
                self.task_queue.insert(i, task)
                inserted = True
                break
        
        if not inserted:
            self.task_queue.append(task)
        
        logger.info(f"添加任务到队列: {task.id}, 优先级={task.priority}, 队列长度={len(self.task_queue)}")
        return task.id
    
    def _process_single_task(self, task: ProcessingTask) -> ProcessingResult:
        """处理单个任务"""
        start_time = time.time()
        
        try:
            logger.info(f"开始处理任务: {task.id}")
            
            # 检查资源
            if not self._check_resources():
                return ProcessingResult(
                    task_id=task.id,
                    success=False,
                    error="系统资源不足",
                    processing_time=time.time() - start_time
                )
            
            # 根据任务类型选择处理函数
            if task.task_type == "document_processing":
                result = self._process_document(task)
            else:
                result = self._process_generic(task)
            
            processing_time = time.time() - start_time
            logger.info(f"任务处理完成: {task.id}, 耗时={processing_time:.2f}s")
            
            return ProcessingResult(
                task_id=task.id,
                success=True,
                result=result,
                processing_time=processing_time,
                metadata=task.metadata
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"任务处理失败: {task.id}, 错误={str(e)}")
            
            return ProcessingResult(
                task_id=task.id,
                success=False,
                error=str(e),
                processing_time=processing_time,
                metadata=task.metadata
            )
    
    def _process_document(self, task: ProcessingTask) -> Any:
        """处理文档任务"""
        from app.services.langchain_rag_service import LangChainRAGService
        
        rag_service = LangChainRAGService()
        
        # 同步调用异步方法
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                rag_service.add_document(
                    workspace_id=task.workspace_id,
                    file_path=task.file_path,
                    metadata=task.metadata
                )
            )
            return result
        finally:
            loop.close()
    
    def _process_generic(self, task: ProcessingTask) -> Any:
        """处理通用任务"""
        # 这里可以添加其他类型的任务处理逻辑
        time.sleep(0.1)  # 模拟处理时间
        return {"status": "processed", "task_type": task.task_type}
    
    async def process_tasks(self, callback: Optional[Callable] = None) -> List[ProcessingResult]:
        """并行处理任务队列"""
        if not self.task_queue:
            logger.info("任务队列为空")
            return []
        
        logger.info(f"开始并行处理 {len(self.task_queue)} 个任务")
        
        # 提交所有任务到线程池
        future_to_task = {}
        for task in self.task_queue:
            future = self.executor.submit(self._process_single_task, task)
            future_to_task[future] = task
            self.running_tasks[task.id] = future
        
        # 清空队列
        self.task_queue.clear()
        
        results = []
        
        # 等待任务完成
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            
            try:
                result = future.result()
                results.append(result)
                self.completed_tasks[task.id] = result
                
                # 从运行中任务移除
                if task.id in self.running_tasks:
                    del self.running_tasks[task.id]
                
                # 调用回调函数
                if callback:
                    try:
                        await callback(result)
                    except Exception as e:
                        logger.error(f"回调函数执行失败: {e}")
                
                logger.info(f"任务完成: {task.id}, 成功={result.success}")
                
            except Exception as e:
                logger.error(f"任务执行异常: {task.id}, 错误={str(e)}")
                
                error_result = ProcessingResult(
                    task_id=task.id,
                    success=False,
                    error=str(e),
                    metadata=task.metadata
                )
                results.append(error_result)
                self.completed_tasks[task.id] = error_result
                
                if task.id in self.running_tasks:
                    del self.running_tasks[task.id]
        
        logger.info(f"并行处理完成: 成功={len([r for r in results if r.success])}, 失败={len([r for r in results if not r.success])}")
        return results
    
    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        return {
            "queue_length": len(self.task_queue),
            "running_tasks": len(self.running_tasks),
            "completed_tasks": len(self.completed_tasks),
            "max_workers": self.max_workers,
            "system_resources": {
                "memory_usage": psutil.virtual_memory().percent,
                "cpu_usage": psutil.cpu_percent(),
                "memory_available": psutil.virtual_memory().available / (1024**3)  # GB
            }
        }
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        # 从队列中移除
        self.task_queue = [task for task in self.task_queue if task.id != task_id]
        
        # 取消运行中的任务
        if task_id in self.running_tasks:
            future = self.running_tasks[task_id]
            future.cancel()
            del self.running_tasks[task_id]
            logger.info(f"任务已取消: {task_id}")
            return True
        
        return False
    
    def clear_completed(self):
        """清理已完成的任务"""
        self.completed_tasks.clear()
        logger.info("已清理所有完成的任务")
    
    def shutdown(self):
        """关闭处理器"""
        logger.info("正在关闭并行处理器...")
        
        # 取消所有运行中的任务
        for task_id, future in self.running_tasks.items():
            future.cancel()
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        
        logger.info("并行处理器已关闭")

# 全局并行处理器实例
_parallel_processor_instance: Optional[ParallelProcessor] = None

def get_parallel_processor() -> ParallelProcessor:
    """获取全局并行处理器实例"""
    global _parallel_processor_instance
    if _parallel_processor_instance is None:
        _parallel_processor_instance = ParallelProcessor()
    return _parallel_processor_instance
