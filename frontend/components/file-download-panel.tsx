"use client"

import { useState, useEffect } from "react"
import { Download, FileText, FileIcon, Trash2, RefreshCw } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

interface GeneratedFile {
  id: string
  filename: string
  file_type: string
  file_size: number
  created_at: string
  title?: string
  source_query?: string
  download_count?: number
  last_downloaded?: string
}

interface FileDownloadPanelProps {
  workspaceId: string
  className?: string
}

export function FileDownloadPanel({ workspaceId, className }: FileDownloadPanelProps) {
  const [files, setFiles] = useState<GeneratedFile[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchFiles = async () => {
    try {
      setIsLoading(true)
      setError(null)
      
      const response = await fetch(`/api/workspace/${workspaceId}/files`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      setFiles(data.files || [])
    } catch (error) {
      console.error("Failed to fetch workspace files:", error)
      setError(error instanceof Error ? error.message : "An unknown error occurred")
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (workspaceId) {
      fetchFiles()
    }
  }, [workspaceId])

  const handleDownloadFile = async (file: GeneratedFile) => {
    try {
      const response = await fetch(`/api/workspace/${workspaceId}/files/${file.id}/download`)
      if (!response.ok) throw new Error('下载失败')
      
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = file.filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      
      // 刷新文件列表以更新下载统计
      fetchFiles()
    } catch (error) {
      console.error('文件下载失败:', error)
      alert('文件下载失败，请重试')
    }
  }

  const handleDeleteFile = async (fileId: string) => {
    if (!confirm('确定要删除这个文件吗？')) return
    
    try {
      const response = await fetch(`/api/workspace/${workspaceId}/files/${fileId}`, {
        method: 'DELETE'
      })
      
      if (!response.ok) {
        throw new Error('删除失败')
      }
      
      // 从列表中移除文件
      setFiles(prev => prev.filter(file => file.id !== fileId))
    } catch (error) {
      console.error('文件删除失败:', error)
      alert('文件删除失败，请重试')
    }
  }

  const getFileIcon = (fileType: string) => {
    switch (fileType) {
      case 'word':
        return <FileText className="w-4 h-4 text-blue-600" />
      case 'excel':
        return <FileIcon className="w-4 h-4 text-green-600" />
      case 'ppt':
        return <FileIcon className="w-4 h-4 text-orange-600" />
      default:
        return <FileIcon className="w-4 h-4 text-gray-600" />
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  return (
    <Card className={`p-4 ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <FileText className="w-5 h-5" />
          生成文件管理
        </h3>
        <Button
          variant="ghost"
          size="sm"
          onClick={fetchFiles}
          disabled={isLoading}
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">加载中...</span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 p-3 bg-destructive/10 border border-destructive/20 rounded">
          <FileIcon className="w-4 h-4 text-destructive" />
          <span className="text-sm text-destructive">加载失败: {error}</span>
        </div>
      )}

      {!isLoading && !error && files.length === 0 && (
        <div className="text-center py-8 text-muted-foreground">
          <FileText className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>暂无生成文件</p>
          <p className="text-sm">与Agent对话生成文档后，文件将在这里显示</p>
        </div>
      )}

      {!isLoading && !error && files.length > 0 && (
        <div className="space-y-3">
          {files.map(file => (
            <div key={file.id} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                {getFileIcon(file.file_type)}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <p className="text-sm font-medium truncate">{file.filename}</p>
                    <Badge variant="secondary" className="text-xs">
                      {file.file_type.toUpperCase()}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span>{formatFileSize(file.file_size)}</span>
                    <span>{formatDate(file.created_at)}</span>
                    {file.download_count && file.download_count > 0 && (
                      <span>已下载 {file.download_count} 次</span>
                    )}
                  </div>
                  {file.title && file.title !== file.filename && (
                    <p className="text-xs text-muted-foreground mt-1 truncate">
                      标题: {file.title}
                    </p>
                  )}
                </div>
              </div>
              
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleDownloadFile(file)}
                  className="h-8 w-8 p-0"
                >
                  <Download className="w-4 h-4" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleDeleteFile(file.id)}
                  className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {files.length > 0 && (
        <div className="mt-4 pt-3 border-t text-xs text-muted-foreground">
          共 {files.length} 个文件
        </div>
      )}
    </Card>
  )
}
