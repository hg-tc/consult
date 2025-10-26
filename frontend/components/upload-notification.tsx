"use client"

import { Upload, X, CheckCircle2, AlertCircle, Loader2, FileText, Scissors, Zap, Database } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"

interface UploadProgress {
  id: string
  filename: string
  size: string
  progress: number
  speed: string
  status: 'uploading' | 'processing' | 'completed' | 'failed'
  taskId?: string
  error?: string
  stage?: 'uploading' | 'parsing' | 'chunking' | 'vectorizing' | 'indexing'
  stageMessage?: string
  stageProgress?: number
}

interface UploadNotificationProps {
  uploads: UploadProgress[]
  onCancel: (uploadId: string) => void
  onClose: (uploadId: string) => void
}

export function UploadNotification({ uploads, onCancel, onClose }: UploadNotificationProps) {
  if (uploads.length === 0) return null

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'uploading':
        return <Upload className="w-5 h-5 text-primary animate-pulse" />
      case 'processing':
        return <Loader2 className="w-5 h-5 text-primary animate-spin" />
      case 'completed':
        return <CheckCircle2 className="w-5 h-5 text-accent" />
      case 'failed':
        return <AlertCircle className="w-5 h-5 text-destructive" />
      default:
        return <Upload className="w-5 h-5 text-primary" />
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case 'uploading':
        return '上传中'
      case 'processing':
        return '处理中'
      case 'completed':
        return '已完成'
      case 'failed':
        return '失败'
      default:
        return '未知'
    }
  }

  const getStageText = (stage: string) => {
    switch (stage) {
      case 'uploading':
        return '文件上传'
      case 'parsing':
        return '文档解析'
      case 'chunking':
        return '内容分块'
      case 'vectorizing':
        return '向量化'
      case 'indexing':
        return '建立索引'
      default:
        return '处理中'
    }
  }

  const getStageIcon = (stage: string) => {
    switch (stage) {
      case 'uploading':
        return <Upload className="w-3 h-3" />
      case 'parsing':
        return <FileText className="w-3 h-3" />
      case 'chunking':
        return <Scissors className="w-3 h-3" />
      case 'vectorizing':
        return <Zap className="w-3 h-3" />
      case 'indexing':
        return <Database className="w-3 h-3" />
      default:
        return <Loader2 className="w-3 h-3" />
    }
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-96 space-y-3 max-h-96 overflow-y-auto">
      {uploads.map((upload) => (
        <Card key={upload.id} className="p-4 bg-card border-border shadow-lg">
          <div className="flex items-start gap-3">
            {getStatusIcon(upload.status)}
            <div className="flex-1 space-y-2">
              <div className="flex justify-between">
                <span className="text-sm font-medium text-foreground truncate">
                  {upload.filename}
                </span>
                <span className="text-xs text-muted-foreground ml-2">
                  {upload.size}
                </span>
              </div>
              
              {/* 进度条 */}
              <div className="space-y-1">
                <Progress value={upload.progress} className="h-1.5" />
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">
                    {upload.status === 'uploading' ? upload.speed : getStatusText(upload.status)}
                  </span>
                  <span className="text-primary">
                    {upload.progress}%
                  </span>
                </div>
              </div>

              {/* 处理阶段详情 */}
              {upload.status === 'processing' && upload.stage && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-xs">
                    {getStageIcon(upload.stage)}
                    <span className="text-muted-foreground">
                      {getStageText(upload.stage)}
                    </span>
                    {upload.stageProgress !== undefined && (
                      <span className="text-primary font-medium">
                        {upload.stageProgress}%
                      </span>
                    )}
                  </div>
                  
                  {/* 阶段进度条 */}
                  {upload.stageProgress !== undefined && (
                    <Progress value={upload.stageProgress} className="h-1" />
                  )}
                  
                  {/* 阶段消息 */}
                  {upload.stageMessage && (
                    <div className="text-xs text-muted-foreground">
                      {upload.stageMessage}
                    </div>
                  )}
                </div>
              )}

              {/* 错误信息 */}
              {upload.error && (
                <div className="text-xs text-destructive bg-destructive/10 p-2 rounded">
                  {upload.error}
                </div>
              )}

              {/* 任务ID（处理中时显示） */}
              {upload.taskId && upload.status === 'processing' && (
                <div className="text-xs text-muted-foreground">
                  任务ID: {upload.taskId}
                </div>
              )}
            </div>
            
            {/* 操作按钮 */}
            <div className="flex flex-col gap-1">
              {upload.status === 'uploading' && (
                <Button 
                  size="icon" 
                  variant="ghost" 
                  onClick={() => onCancel(upload.id)}
                  className="h-6 w-6"
                >
                  <X className="w-3 h-3" />
                </Button>
              )}
              
              {(upload.status === 'completed' || upload.status === 'failed') && (
                <Button 
                  size="icon" 
                  variant="ghost" 
                  onClick={() => onClose(upload.id)}
                  className="h-6 w-6"
                >
                  <X className="w-3 h-3" />
                </Button>
              )}
            </div>
          </div>
        </Card>
      ))}
    </div>
  )
}
