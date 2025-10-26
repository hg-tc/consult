"use client"

import { useState, useEffect, useCallback } from "react"
import { statusApi } from "@/lib/api-client"
import { Task, TaskQueueStats } from "@/types/task"

export type TaskStatus = Task

export type QueueStats = TaskQueueStats

export function useTaskStatus(workspaceId?: string) {
  const [tasks, setTasks] = useState<TaskStatus[]>([])
  const [queueStats, setQueueStats] = useState<QueueStats | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ws, setWs] = useState<WebSocket | null>(null)

  const fetchTasks = useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)
      
      const params = workspaceId ? `?workspace_id=${workspaceId}` : ''
      const response = await fetch(`/api/tasks${params}`)
      
      if (!response.ok) {
        throw new Error(`Failed to fetch tasks: ${response.statusText}`)
      }
      
      const data = await response.json()
      setTasks(data.tasks || [])
      setQueueStats(data.queue_stats || null)
    } catch (err) {
      console.error("[v0] Failed to fetch tasks:", err)
      setError(err instanceof Error ? err.message : "Failed to fetch tasks")
    } finally {
      setIsLoading(false)
    }
  }, [workspaceId])

  // WebSocket连接
  useEffect(() => {
            const wsUrl = process.env.NEXT_PUBLIC_WS_URL ? `${process.env.NEXT_PUBLIC_WS_URL}/status` : "ws://localhost:13000/ws/status"
    
    const websocket = new WebSocket(wsUrl)
    
    websocket.onopen = () => {
      console.log('[v0] WebSocket连接已建立')
    }
    
    websocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        console.log('[v0] 收到WebSocket消息:', data)
        
        if (data.type === 'initial_status') {
          setTasks(data.tasks || [])
          setQueueStats(data.queue_stats || null)
        } else if (data.type === 'task_update') {
          setTasks(prev => {
            const updated = prev.filter(task => task.id !== data.task_id)
            updated.push({
              id: data.task_id,
              task_type: data.task_type || 'document_processing',
              status: data.status,
              stage: data.stage,
              progress: data.progress,
              message: data.message,
              details: data.details,
              workspace_id: data.workspace_id,
              created_at: data.timestamp,
              metadata: {}
            })
            return updated
          })
        }
      } catch (error) {
        console.error('[v0] 解析WebSocket消息失败:', error)
      }
    }
    
    websocket.onclose = () => {
      console.log('[v0] WebSocket连接已关闭')
    }
    
    websocket.onerror = (error) => {
      console.error('[v0] WebSocket错误:', error)
    }
    
    setWs(websocket)
    
    return () => {
      websocket.close()
    }
  }, [])

  const getTaskById = useCallback(async (taskId: string): Promise<TaskStatus | null> => {
    try {
      const response = await fetch(`/api/tasks/${taskId}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch task: ${response.statusText}`)
      }
      return await response.json()
    } catch (err) {
      console.error("[v0] Failed to fetch task:", err)
      return null
    }
  }, [])

  const cancelTask = useCallback(async (taskId: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/tasks/${taskId}/cancel`, {
        method: "POST"
      })
      if (!response.ok) {
        throw new Error(`Failed to cancel task: ${response.statusText}`)
      }
      await fetchTasks() // 刷新任务列表
      return true
    } catch (err) {
      console.error("[v0] Failed to cancel task:", err)
      return false
    }
  }, [fetchTasks])

  // 定期刷新任务状态
  useEffect(() => {
    fetchTasks()
    
    const interval = setInterval(fetchTasks, 5000) // 每5秒刷新一次，减少频率
    
    return () => clearInterval(interval)
  }, [fetchTasks])

  return {
    tasks,
    queueStats,
    isLoading,
    error,
    fetchTasks,
    getTaskById,
    cancelTask,
  }
}
