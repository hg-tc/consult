"use client"

import { Clock, AlertCircle, Loader2 } from "lucide-react"
import { Card } from "@/components/ui/card"
import { TaskProgressPanel } from "@/components/task-progress-panel"
import { useGlobalTaskStatus } from "@/hooks/use-global-task-status"

export function StatusPanel() {
  const { tasks, queueStats, isLoading, error } = useGlobalTaskStatus()

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-foreground mb-2">处理状态监控</h2>
        <p className="text-muted-foreground">实时查看文档处理进度和任务状态</p>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
          <span className="ml-2 text-muted-foreground">加载任务状态...</span>
        </div>
      )}

      {error && (
        <Card className="p-6 bg-destructive/10 border-destructive">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="w-5 h-5" />
            <p>加载状态信息失败: {error}</p>
          </div>
        </Card>
      )}

      {/* 任务进度面板 */}
      <TaskProgressPanel />

      {/* 空状态 - 只在没有任务时显示 */}
      {!isLoading && !error && tasks.length === 0 && (
        <Card className="p-12 bg-card border-border text-center">
          <div className="space-y-4">
            <div className="w-16 h-16 mx-auto bg-muted rounded-full flex items-center justify-center">
              <Clock className="w-8 h-8 text-muted-foreground" />
            </div>
            <div>
              <h3 className="text-lg font-medium text-foreground mb-2">暂无处理任务</h3>
              <p className="text-muted-foreground">上传文档后，处理进度将在这里显示</p>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
