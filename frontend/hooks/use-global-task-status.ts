"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { Task, TaskQueueStats } from "@/types/task"

export type TaskStatus = Task
export type QueueStats = TaskQueueStats

// 全局状态存储
let globalTasks: TaskStatus[] = []
let globalQueueStats: QueueStats | null = null
let globalWebSocket: WebSocket | null = null
let globalListeners: Set<(tasks: TaskStatus[], stats: QueueStats | null) => void> = new Set()

// 全局WebSocket连接管理
class GlobalWebSocketManager {
  private ws: WebSocket | null = null
  private reconnectTimeout: NodeJS.Timeout | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private isManuallyDisconnected = false

  connect() {
    if (this.isManuallyDisconnected || this.reconnectAttempts >= this.maxReconnectAttempts) {
      return
    }

    // 使用相对路径，通过前端代理连接
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || `${protocol}//${window.location.host}/ws/status`
    
    try {
      this.ws = new WebSocket(wsUrl)
      
      this.ws.onopen = () => {
        console.log('[GlobalWebSocket] 连接已建立')
        this.reconnectAttempts = 0
        if (this.reconnectTimeout) {
          clearTimeout(this.reconnectTimeout)
          this.reconnectTimeout = null
        }
      }
      
      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          console.log('[GlobalWebSocket] 收到消息:', data)
          
          if (data.type === 'initial_status') {
            globalTasks = data.tasks || []
            globalQueueStats = data.queue_stats || null
            this.notifyListeners()
          } else if (data.type === 'task_update') {
            console.log('[GlobalWebSocket] 任务更新:', data.task_id, data.status, data.stage, data.progress + '%')
            globalTasks = globalTasks.filter(task => task.id !== data.task_id)
            globalTasks.push({
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
            this.notifyListeners()
          }
        } catch (error) {
          console.error('[GlobalWebSocket] 解析消息失败:', error)
        }
      }
      
      this.ws.onclose = () => {
        console.log('[GlobalWebSocket] 连接已关闭')
        if (!this.isManuallyDisconnected && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++
          this.reconnectTimeout = setTimeout(() => this.connect(), 5000)
        }
      }
      
      this.ws.onerror = (error) => {
        console.error('[GlobalWebSocket] 连接错误:', error)
      }
      
      globalWebSocket = this.ws
    } catch (error) {
      console.error('[GlobalWebSocket] 连接失败:', error)
    }
  }

  disconnect() {
    this.isManuallyDisconnected = true
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    globalWebSocket = null
  }

  private notifyListeners() {
    globalListeners.forEach(listener => {
      try {
        listener([...globalTasks], globalQueueStats)
      } catch (error) {
        console.error('[GlobalWebSocket] 通知监听器失败:', error)
      }
    })
  }

  addListener(listener: (tasks: TaskStatus[], stats: QueueStats | null) => void) {
    globalListeners.add(listener)
    // 立即通知当前状态
    listener([...globalTasks], globalQueueStats)
  }

  removeListener(listener: (tasks: TaskStatus[], stats: QueueStats | null) => void) {
    globalListeners.delete(listener)
  }
}

const globalWebSocketManager = new GlobalWebSocketManager()

export function useGlobalTaskStatus(workspaceId?: string) {
  const [tasks, setTasks] = useState<TaskStatus[]>([])
  const [queueStats, setQueueStats] = useState<QueueStats | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isInitialized = useRef(false)
  const isFirstLoad = useRef(true) // 标记是否为首次加载

  const fetchTasks = useCallback(async (showLoading = false) => {
    try {
      // 只在首次加载或明确要求显示加载状态时才设置 isLoading
      if (showLoading || isFirstLoad.current) {
        setIsLoading(true)
      }
      setError(null)
      
      const params = workspaceId ? `?workspace_id=${workspaceId}` : ''
      const response = await fetch(`/api/tasks${params}`)
      
      if (!response.ok) {
        throw new Error(`Failed to fetch tasks: ${response.statusText}`)
      }
      
      const data = await response.json()
      globalTasks = data.tasks || []
      globalQueueStats = data.queue_stats || null
      setTasks(globalTasks)
      setQueueStats(globalQueueStats)
      
      // 首次加载完成后，标记为已加载
      if (isFirstLoad.current) {
        isFirstLoad.current = false
      }
    } catch (err) {
      console.error("[GlobalTaskStatus] Failed to fetch tasks:", err)
      // 只在首次加载或明确要求时才显示错误
      if (showLoading || isFirstLoad.current) {
        setError(err instanceof Error ? err.message : "Failed to fetch tasks")
      }
    } finally {
      if (showLoading || isFirstLoad.current) {
        setIsLoading(false)
      }
    }
  }, [workspaceId])

  // 初始化全局WebSocket连接 - 暂时禁用WebSocket
  useEffect(() => {
    if (!isInitialized.current) {
      isInitialized.current = true
      // 暂时禁用WebSocket连接，避免CSP错误
      // globalWebSocketManager.connect()
    }
  }, [])

  // 监听全局状态变化 - 暂时禁用WebSocket监听
  // useEffect(() => {
  //   const listener = (newTasks: TaskStatus[], newStats: QueueStats | null) => {
  //     if (workspaceId) {
  //       const filteredTasks = newTasks.filter(task => task.workspace_id === workspaceId)
  //       setTasks(filteredTasks)
  //     } else {
  //       setTasks(newTasks)
  //     }
  //     setQueueStats(newStats)
  //   }

  //   globalWebSocketManager.addListener(listener)

  //   return () => {
  //     globalWebSocketManager.removeListener(listener)
  //   }
  // }, [workspaceId])

  // 初始加载（显示加载状态）
  useEffect(() => {
    isFirstLoad.current = true
    fetchTasks(true) // 首次加载显示加载状态
  }, [workspaceId])

  // 使用定时器定期刷新任务状态（后台静默刷新）
  useEffect(() => {
    // 首次加载后，每3秒静默刷新一次（不显示加载状态）
    const interval = setInterval(() => {
      if (!isFirstLoad.current) {
        // 只在非首次加载时进行静默刷新
        fetchTasks(false) // 不显示加载状态
      }
    }, 3000) // 每3秒刷新一次

    return () => clearInterval(interval)
  }, [fetchTasks])

  const getTaskById = useCallback(async (taskId: string): Promise<TaskStatus | null> => {
    try {
      const response = await fetch(`/api/tasks/${taskId}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch task: ${response.statusText}`)
      }
      return await response.json()
    } catch (err) {
      console.error("[GlobalTaskStatus] Failed to fetch task:", err)
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
      // WebSocket会自动更新状态，不需要手动刷新
      return true
    } catch (err) {
      console.error("[GlobalTaskStatus] Failed to cancel task:", err)
      return false
    }
  }, [])

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

// 导出全局WebSocket管理器，用于手动控制连接
export { globalWebSocketManager }
