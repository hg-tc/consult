"""
WebSocket服务 - 实时状态推送
"""

import asyncio
import json
import logging
from typing import Dict, Set, Any
from fastapi import WebSocket, WebSocketDisconnect
from app.services.task_queue import TaskQueue, Task, get_task_queue

logger = logging.getLogger(__name__)

class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.task_queue = get_task_queue()
        self._setup_task_callbacks()
    
    def _setup_task_callbacks(self):
        """设置任务状态回调"""
        # 为所有现有任务添加回调
        for task_id in self.task_queue.tasks:
            self.task_queue.add_task_callback(task_id, self._broadcast_task_update)
    
    def _broadcast_task_update(self, task: Task):
        """广播任务更新"""
        message = {
            "type": "task_update",
            "task_id": task.id,
            "status": task.status.value,
            "stage": task.progress.stage.value,
            "progress": task.progress.progress,
            "message": task.progress.message,
            "details": task.progress.details or {},
            "workspace_id": task.workspace_id,
            "timestamp": task.completed_at or task.started_at or task.created_at
        }
        
        logger.info(f"📡 WebSocket广播任务更新: {task.id} - {task.status.value} - {task.progress.stage.value} {task.progress.progress}%")
        logger.debug(f"📡 任务详情: {json.dumps(message, ensure_ascii=False)}")
        
        # 广播给所有连接
        asyncio.create_task(self._broadcast_to_all(message))
        
        # 如果指定了工作区，也广播给该工作区的连接
        if task.workspace_id:
            asyncio.create_task(self._broadcast_to_workspace(task.workspace_id, message))
    
    async def _broadcast_to_all(self, message: Dict[str, Any]):
        """广播给所有连接"""
        disconnected = set()
        total_connections = sum(len(connections) for connections in self.active_connections.values())
        logger.debug(f"📡 开始广播给所有连接: {total_connections} 个连接")
        
        for workspace_id, connections in self.active_connections.items():
            logger.debug(f"📡 广播到工作区 {workspace_id}: {len(connections)} 个连接")
            for connection in connections:
                try:
                    await connection.send_text(json.dumps(message))
                    logger.debug(f"📡 消息发送成功到工作区 {workspace_id}")
                except Exception as e:
                    logger.warning(f"📡 消息发送失败到工作区 {workspace_id}: {e}")
                    disconnected.add((workspace_id, connection))
        
        # 清理断开的连接
        for workspace_id, connection in disconnected:
            self.active_connections[workspace_id].discard(connection)
            if not self.active_connections[workspace_id]:
                del self.active_connections[workspace_id]
            logger.debug(f"📡 清理断开连接: {workspace_id}")
        
        logger.debug(f"📡 广播完成，清理了 {len(disconnected)} 个断开连接")
    
    async def _broadcast_to_workspace(self, workspace_id: str, message: Dict[str, Any]):
        """广播给指定工作区的连接"""
        if workspace_id not in self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections[workspace_id]:
            try:
                await connection.send_text(json.dumps(message))
            except:
                disconnected.add(connection)
        
        # 清理断开的连接
        for connection in disconnected:
            self.active_connections[workspace_id].discard(connection)
        
        if not self.active_connections[workspace_id]:
            del self.active_connections[workspace_id]
    
    async def connect(self, websocket: WebSocket, workspace_id: str = "global"):
        """接受WebSocket连接"""
        await websocket.accept()
        
        if workspace_id not in self.active_connections:
            self.active_connections[workspace_id] = set()
        
        self.active_connections[workspace_id].add(websocket)
        total_connections = sum(len(connections) for connections in self.active_connections.values())
        logger.info(f"📡 WebSocket连接建立: {workspace_id}, 总连接数: {total_connections}")
        logger.debug(f"📡 当前连接分布: {self.get_connection_count()}")
        
        # 发送当前任务状态
        await self._send_current_status(websocket, workspace_id)
    
    def disconnect(self, websocket: WebSocket, workspace_id: str = "global"):
        """断开WebSocket连接"""
        if workspace_id in self.active_connections:
            self.active_connections[workspace_id].discard(websocket)
            if not self.active_connections[workspace_id]:
                del self.active_connections[workspace_id]
        logger.info(f"WebSocket连接断开: {workspace_id}")
    
    async def _send_current_status(self, websocket: WebSocket, workspace_id: str):
        """发送当前任务状态"""
        try:
            # 获取工作区相关任务
            if workspace_id == "global":
                tasks = list(self.task_queue.tasks.values())
            else:
                tasks = self.task_queue.get_tasks_by_workspace(workspace_id)
            
            # 发送任务列表
            message = {
                "type": "initial_status",
                "tasks": [
                    {
                        "task_id": task.id,
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
                        "error_message": task.error_message
                    }
                    for task in tasks
                ],
                "queue_stats": self.task_queue.get_queue_stats()
            }
            
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"发送初始状态失败: {e}")
    
    def get_connection_count(self) -> Dict[str, int]:
        """获取连接统计"""
        return {
            workspace_id: len(connections)
            for workspace_id, connections in self.active_connections.items()
        }

# 全局连接管理器实例
manager = ConnectionManager()

async def websocket_endpoint(websocket: WebSocket, workspace_id: str = "global"):
    """WebSocket端点"""
    await manager.connect(websocket, workspace_id)
    try:
        while True:
            # 保持连接活跃
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # 处理客户端消息
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif message.get("type") == "get_status":
                await manager._send_current_status(websocket, workspace_id)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, workspace_id)
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        manager.disconnect(websocket, workspace_id)
