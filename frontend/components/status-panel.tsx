"use client"

import { CheckCircle2, Clock, AlertCircle, Loader2, Play, Square } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useStatus } from "@/hooks/use-status"
import { Spinner } from "@/components/ui/spinner"

interface ProcessStatus {
  id: string
  workspace: string
  status: "running" | "completed" | "pending" | "error"
  progress: number
  message: string
  timestamp: string
}

export function StatusPanel() {
  const { statuses, isLoading, isError, startProcessing, stopProcessing } = useStatus()

  const getStatusIcon = (status: ProcessStatus["status"]) => {
    switch (status) {
      case "running":
        return <Loader2 className="w-5 h-5 text-primary animate-spin" />
      case "completed":
        return <CheckCircle2 className="w-5 h-5 text-accent" />
      case "pending":
        return <Clock className="w-5 h-5 text-muted-foreground" />
      case "error":
        return <AlertCircle className="w-5 h-5 text-destructive" />
    }
  }

  const getStatusColor = (status: ProcessStatus["status"]) => {
    switch (status) {
      case "running":
        return "bg-primary"
      case "completed":
        return "bg-accent"
      case "pending":
        return "bg-muted"
      case "error":
        return "bg-destructive"
    }
  }

  const handleToggleProcessing = async (workspaceId: string, currentStatus: string) => {
    try {
      if (currentStatus === "running") {
        await stopProcessing(workspaceId)
      } else {
        await startProcessing(workspaceId)
      }
    } catch (error) {
      console.error("[v0] Toggle processing error:", error)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-foreground mb-2">处理状态监控</h2>
        <p className="text-muted-foreground">实时查看各工作区的Agent运行状态</p>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Spinner className="w-8 h-8 text-primary" />
        </div>
      )}

      {isError && (
        <Card className="p-6 bg-destructive/10 border-destructive">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="w-5 h-5" />
            <p>加载状态信息失败，请刷新页面重试</p>
          </div>
        </Card>
      )}

      {!isLoading && !isError && (
        <div className="grid gap-4">
          {statuses.map((status: ProcessStatus) => (
            <Card key={status.id} className="p-6 bg-card border-border">
              <div className="space-y-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3 flex-1">
                    {getStatusIcon(status.status)}
                    <div className="flex-1">
                      <h3 className="font-medium text-foreground">{status.workspace}</h3>
                      <p className="text-sm text-muted-foreground mt-1">{status.message}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-muted-foreground">{status.timestamp}</span>
                    {status.status !== "completed" && (
                      <Button
                        size="sm"
                        variant={status.status === "running" ? "destructive" : "default"}
                        onClick={() => handleToggleProcessing(status.id, status.status)}
                      >
                        {status.status === "running" ? (
                          <>
                            <Square className="w-3 h-3 mr-1" />
                            停止
                          </>
                        ) : (
                          <>
                            <Play className="w-3 h-3 mr-1" />
                            启动
                          </>
                        )}
                      </Button>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">进度</span>
                    <span className="font-medium text-foreground">{status.progress}%</span>
                  </div>
                  <div className="h-2 bg-secondary rounded-full overflow-hidden">
                    <div
                      className={cn("h-full transition-all duration-500", getStatusColor(status.status))}
                      style={{ width: `${status.progress}%` }}
                    />
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
