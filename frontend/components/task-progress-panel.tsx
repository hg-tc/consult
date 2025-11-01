"use client"

import { Card } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { 
  FileIcon, 
  CheckCircle2, 
  Loader2, 
  Clock, 
  AlertCircle, 
  XCircle,
  X,
  RefreshCw
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useGlobalTaskStatus } from "@/hooks/use-global-task-status"
import { Task, TaskStage, TaskStatus } from "@/types/task"
import { useState, useEffect, useMemo } from "react"

interface TaskProgressCardProps {
  task: Task
  onCancel?: (taskId: string) => void
  onRefresh?: () => void
}

function TaskProgressCard({ task, onCancel, onRefresh }: TaskProgressCardProps) {
  const getStatusIcon = () => {
    switch (task.status) {
      case "completed":
        return <CheckCircle2 className="w-5 h-5 text-green-600" />
      case "failed":
        return <XCircle className="w-5 h-5 text-red-600" />
      case "cancelled":
        return <XCircle className="w-5 h-5 text-gray-600" />
      case "processing":
        return <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />
      default:
        return <Clock className="w-5 h-5 text-yellow-600" />
    }
  }

  const getStatusColor = () => {
    switch (task.status) {
      case "completed":
        return "bg-green-100 text-green-800 border-green-200"
      case "failed":
        return "bg-red-100 text-red-800 border-red-200"
      case "cancelled":
        return "bg-gray-100 text-gray-800 border-gray-200"
      case "processing":
        return "bg-blue-100 text-blue-800 border-blue-200"
      default:
        return "bg-yellow-100 text-yellow-800 border-yellow-200"
    }
  }

  const getStageText = () => {
    switch (task.stage) {
      case "uploading":
        return "上传中"
      case "parsing":
        return "解析文档"
      case "chunking":
        return "分割文档"
      case "vectorizing":
        return "向量化处理"
      case "indexing":
        return "建立索引"
      case "completed":
        return "处理完成"
      case "failed":
        return "处理失败"
      default:
        return "等待处理"
    }
  }

  return (
    <Card className="p-4 bg-card border-border">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          {getStatusIcon()}
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <FileIcon className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-medium text-foreground truncate">
                {task.metadata?.original_filename || "未知文件"}
              </span>
            </div>
            <Badge className={cn("text-xs", getStatusColor())}>
              {task.status === "processing" ? (
                task.progress >= 100 ? "已完成" : "处理中"
              ) : task.status === "completed" ? "已完成" :
               task.status === "failed" ? "失败" :
               task.status === "cancelled" ? "已取消" : "等待中"}
            </Badge>
          </div>
          
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{getStageText()}</span>
              <span>{task.progress}%</span>
            </div>
            
            <Progress value={task.progress} className="h-2" />
            
            <div className="text-xs text-muted-foreground">
              {task.message}
            </div>
            
            {task.error_message && (
              <div className="flex items-center gap-1 text-xs text-red-600">
                <AlertCircle className="w-3 h-3" />
                <span>{task.error_message}</span>
              </div>
            )}
            
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                工作区: {task.workspace_id}
              </span>
              <span>
                {new Date(task.created_at * 1000).toISOString().slice(11, 19)}
              </span>
            </div>
          </div>
        </div>
        
        <div className="flex-shrink-0 flex gap-1">
          {task.status === "processing" && task.progress < 100 && onCancel && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onCancel(task.id)}
              className="h-8 w-8 p-0"
            >
              <X className="w-3 h-3" />
            </Button>
          )}
          {onRefresh && (
            <Button
              size="sm"
              variant="outline"
              onClick={onRefresh}
              className="h-8 w-8 p-0"
            >
              <RefreshCw className="w-3 h-3" />
            </Button>
          )}
        </div>
      </div>
    </Card>
  )
}

interface TaskProgressPanelProps {
  workspaceId?: string
  className?: string
}

export function TaskProgressPanel({ workspaceId, className }: TaskProgressPanelProps) {
  const { tasks, queueStats, isLoading, error, fetchTasks, cancelTask } = useGlobalTaskStatus(workspaceId)
  
  const handleCancelTask = async (taskId: string) => {
    const success = await cancelTask(taskId)
    if (success) {
      console.log("[v0] Task cancelled successfully:", taskId)
    } else {
      console.error("[v0] Failed to cancel task:", taskId)
    }
  }

  // 使用useMemo优化任务过滤，避免不必要的重新计算
  // 注意：如果progress是100，即使status是processing也视为已完成
  const activeTasks = useMemo(() => 
    tasks.filter(task => {
      const isActiveStatus = task.status === "pending" || task.status === "processing"
      // 如果进度是100，即使状态是processing，也视为已完成
      if (isActiveStatus && task.progress >= 100) {
        return false
      }
      return isActiveStatus
    }), [tasks])
  
  // 过滤已完成任务：只显示最近完成的（1小时内）或最近10个
  const recentTasks = useMemo(() => {
    const now = Date.now() / 1000 // 转换为秒
    const oneHourAgo = now - 3600 // 1小时前
    
    const completedTasks = tasks.filter(task => {
      const isCompleted = task.status === "completed" || task.status === "failed" || task.status === "cancelled"
      if (!isCompleted) return false
      
      // 如果有完成时间，检查是否在1小时内
      if (task.completed_at) {
        return task.completed_at > oneHourAgo
      }
      // 如果没有完成时间，使用创建时间（防止任务状态异常）
      if (task.created_at) {
        return task.created_at > oneHourAgo
      }
      return false // 没有时间信息的任务不显示
    })
    
    // 按完成时间倒序排列，只显示最近10个
    return completedTasks
      .sort((a, b) => (b.completed_at || b.created_at || 0) - (a.completed_at || a.created_at || 0))
      .slice(0, 10)
  }, [tasks])

  // 只在首次加载且没有任务时显示加载状态
  // 避免定期刷新时出现加载转圈
  if (isLoading && tasks.length === 0 && !queueStats) {
    return (
      <Card className={cn("p-6", className)}>
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 text-primary animate-spin" />
          <span className="ml-2 text-muted-foreground">加载任务状态...</span>
        </div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className={cn("p-6 bg-destructive/10 border-destructive", className)}>
        <div className="flex items-center gap-2 text-destructive">
          <AlertCircle className="w-5 h-5" />
          <p>加载任务状态失败: {error}</p>
        </div>
      </Card>
    )
  }

  return (
    <div className={cn("space-y-4", className)}>
      {/* 队列统计 */}
      {queueStats && (
        <Card className="p-4 bg-card border-border">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-foreground">处理队列状态</h3>
            <Button
              size="sm"
              variant="outline"
              onClick={() => fetchTasks(true)}
              className="h-8"
            >
              <RefreshCw className="w-3 h-3 mr-1" />
              刷新
            </Button>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div key="total-tasks">
              <div className="text-lg font-semibold text-primary">{queueStats.total_tasks}</div>
              <div className="text-xs text-muted-foreground">总任务</div>
            </div>
            <div key="pending-tasks">
              <div className="text-lg font-semibold text-yellow-600">{queueStats.pending}</div>
              <div className="text-xs text-muted-foreground">等待中</div>
            </div>
            <div key="processing-tasks">
              <div className="text-lg font-semibold text-blue-600">{queueStats.processing}</div>
              <div className="text-xs text-muted-foreground">处理中</div>
            </div>
            <div key="completed-tasks">
              <div className="text-lg font-semibold text-green-600">{queueStats.completed}</div>
              <div className="text-xs text-muted-foreground">已完成</div>
            </div>
          </div>
        </Card>
      )}

      {/* 活跃任务 */}
      {activeTasks.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-foreground mb-3">
            正在处理的任务 ({activeTasks.length})
          </h3>
          <div className="space-y-3">
            {activeTasks.map((task) => (
              <TaskProgressCard
                key={task.id}
                task={task}
                onCancel={handleCancelTask}
                onRefresh={() => fetchTasks(false)}
              />
            ))}
          </div>
        </div>
      )}

      {/* 最近完成的任务 */}
      {recentTasks.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-foreground">
              最近完成的任务 ({recentTasks.length})
            </h3>
            <Button
              size="sm"
              variant="ghost"
              onClick={async () => {
                // 调用后端清理API
                try {
                  await fetch('/api/tasks/cleanup', { method: 'POST' })
                  fetchTasks(false) // 静默刷新
                } catch (e) {
                  console.error('清理任务失败:', e)
                  // 即使清理失败也刷新
                  fetchTasks(false) // 静默刷新
                }
              }}
              className="h-7 text-xs"
            >
              <X className="w-3 h-3 mr-1" />
              清理旧任务
            </Button>
          </div>
          <div className="space-y-3">
            {recentTasks.map((task) => (
              <TaskProgressCard
                key={task.id}
                task={task}
                onRefresh={() => fetchTasks(false)}
              />
            ))}
          </div>
        </div>
      )}

      {/* 无任务状态 */}
      {tasks.length === 0 && (
        <Card className="p-6 bg-card border-border">
          <div className="text-center text-muted-foreground">
            <FileIcon className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>暂无处理任务</p>
          </div>
        </Card>
      )}
    </div>
  )
}
