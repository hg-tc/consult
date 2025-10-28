"use client"

import { useState, useEffect, useCallback } from "react"
import { Plus, FolderOpen, Upload, Edit2, Trash2, AlertCircle, ChevronDown, ChevronRight, FileText, Download, Eye } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useWorkspaces } from "@/hooks/use-workspaces"
import { useWorkspaceDocuments } from "@/hooks/use-workspace-documents"
import { Spinner } from "@/components/ui/spinner"

interface WorkspaceDocumentListProps {
  workspaceId: string
  workspaceName: string
  isExpanded: boolean
  onToggle: () => void
  onStatsUpdate?: (count: number) => void
}

function WorkspaceDocumentList({ workspaceId, workspaceName, isExpanded, onToggle, onStatsUpdate }: WorkspaceDocumentListProps) {
  const { documents, stats, isLoading, error, uploadDocument, deleteDocument, downloadDocument } = useWorkspaceDocuments(workspaceId)
  const [uploading, setUploading] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  
  // 当stats更新时，通知父组件
  useEffect(() => {
    if (onStatsUpdate && stats) {
      onStatsUpdate(stats.document_count)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stats?.document_count]) // 只依赖document_count，不依赖onStatsUpdate

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        await uploadDocument(file)
      }
    } catch (error) {
      console.error("[v0] File upload error:", error)
    } finally {
      setUploading(false)
    }
  }

  const handleDeleteDocument = async (docId: string) => {
    setDeletingId(docId)
    try {
      await deleteDocument(docId)
    } catch (error) {
      console.error("[v0] Document deletion error:", error)
    } finally {
      setDeletingId(null)
    }
  }

  const handleDownloadDocument = async (docId: string, filename: string) => {
    try {
      await downloadDocument(docId, filename)
    } catch (error) {
      console.error("[v0] Document download error:", error)
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 B"
    const k = 1024
    const sizes = ["B", "KB", "MB", "GB"]
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i]
  }

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleDateString("zh-CN")
    } catch {
      return dateString
    }
  }

  return (
    <div className="mt-4 border-t border-border pt-4">
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={onToggle}
          className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
          文档列表 ({stats?.document_count || 0})
        </button>
        
        <label htmlFor={`upload-${workspaceId}`}>
          <Button
            variant="outline"
            size="sm"
            className="cursor-pointer"
            disabled={uploading}
            asChild
          >
            <div>
              {uploading ? (
                <>
                  <Spinner className="w-3 h-3 mr-1" />
                  上传中
                </>
              ) : (
                <>
                  <Upload className="w-3 h-3 mr-1" />
                  上传
                </>
              )}
            </div>
          </Button>
          <input
            id={`upload-${workspaceId}`}
            type="file"
            className="hidden"
            multiple
            accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.md,.zip,.rar"
            onChange={handleFileUpload}
            disabled={uploading}
          />
        </label>
      </div>

      {isExpanded && (
        <div className="space-y-2">
          {isLoading && (
            <div className="flex items-center justify-center py-4">
              <Spinner className="w-4 h-4 text-primary" />
            </div>
          )}

          {error && (
            <div className="text-sm text-destructive bg-destructive/10 p-2 rounded">
              加载文档失败: {error}
            </div>
          )}

          {!isLoading && !error && documents.length === 0 && (
            <div className="text-sm text-muted-foreground text-center py-4">
              暂无文档，点击上传按钮添加文档
            </div>
          )}

          {!isLoading && !error && documents.map((doc) => (
            <div key={doc.id} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {doc.filename}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatFileSize(doc.file_size)} · {doc.chunk_count} 个片段 · {formatDate(doc.upload_time || doc.created_at || '')}
                  </p>
                </div>
              </div>
              
              <div className="flex items-center gap-1 ml-2">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => handleDownloadDocument(doc.id, doc.filename)}
                  title="下载文档"
                >
                  <Download className="w-3 h-3" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-destructive hover:text-destructive"
                  onClick={() => handleDeleteDocument(doc.id)}
                  disabled={deletingId === doc.id}
                  title="删除文档"
                >
                  {deletingId === doc.id ? (
                    <Spinner className="w-3 h-3" />
                  ) : (
                    <Trash2 className="w-3 h-3" />
                  )}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function WorkspacePanel() {
  const { workspaces, isLoading, isError, isCreating, createWorkspace, updateWorkspace, deleteWorkspace, refresh } =
    useWorkspaces()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState("")
  const [expandedWorkspaces, setExpandedWorkspaces] = useState<Set<string>>(new Set())
  
  // 存储每个工作区的实时文档数量
  const [workspaceStats, setWorkspaceStats] = useState<Record<string, number>>({})

  const toggleWorkspaceExpansion = (workspaceId: string) => {
    const newExpanded = new Set(expandedWorkspaces)
    if (newExpanded.has(workspaceId)) {
      newExpanded.delete(workspaceId)
    } else {
      newExpanded.add(workspaceId)
    }
    setExpandedWorkspaces(newExpanded)
  }

  const addWorkspace = async () => {
    try {
      const result = await createWorkspace("新工作区") as any
      setEditingId(result.id)
      setEditName(result.name)
      // 刷新工作区列表
      refresh()
    } catch (error) {
      console.error("[v0] Workspace creation error:", error)
      // 可以添加用户友好的错误提示
    }
  }
  
  // 接收子组件返回的文件数量（使用useCallback避免无限循环）
  const updateWorkspaceStats = useCallback((workspaceId: string, count: number) => {
    setWorkspaceStats((prev) => {
      // 只有当值真正改变时才更新，避免无限循环
      if (prev[workspaceId] === count) {
        return prev
      }
      return { ...prev, [workspaceId]: count }
    })
  }, [])
  

  const startEdit = (workspace: any) => {
    setEditingId(workspace.id)
    setEditName(workspace.name)
  }

  const saveEdit = async (id: string) => {
    try {
      await updateWorkspace(id, editName)
      setEditingId(null)
    } catch (error) {
      console.error("[v0] Workspace update error:", error)
      // 可以添加用户友好的错误提示
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteWorkspace(id)
    } catch (error) {
      console.error("[v0] Workspace deletion error:", error)
      // 可以添加用户友好的错误提示
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-foreground mb-2">工作区管理</h2>
          <p className="text-muted-foreground">为不同客户创建独立的工作区并上传资料</p>
        </div>
        <Button onClick={addWorkspace} disabled={isCreating}>
          {isCreating ? (
            <>
              <Spinner className="w-4 h-4 mr-2" />
              创建中...
            </>
          ) : (
            <>
              <Plus className="w-4 h-4 mr-2" />
              新建工作区
            </>
          )}
        </Button>
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
            <p>加载工作区失败，请刷新页面重试</p>
          </div>
        </Card>
      )}

      {!isLoading && !isError && (
        <div className="grid gap-4 md:grid-cols-2">
          {workspaces.map((workspace: any) => (
            <Card key={workspace.id} className="p-6 bg-card border-border">
              <div className="space-y-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3 flex-1">
                    <div className="w-12 h-12 rounded-lg bg-accent/10 flex items-center justify-center flex-shrink-0">
                      <FolderOpen className="w-6 h-6 text-accent" />
                    </div>
                    <div className="flex-1 min-w-0">
                      {editingId === workspace.id ? (
                        <Input
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          onBlur={() => saveEdit(workspace.id)}
                          onKeyDown={(e) => e.key === "Enter" && saveEdit(workspace.id)}
                          className="h-8 text-base font-medium"
                          autoFocus
                        />
                      ) : (
                        <h3 className="font-medium text-foreground truncate">{workspace.name}</h3>
                      )}
                      <p className="text-sm text-muted-foreground mt-1">
                        {workspaceStats[workspace.id] ?? workspace.files ?? 0} 个文件 · 创建于 {workspace.created}
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-1 ml-2">
                    <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => startEdit(workspace)}>
                      <Edit2 className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive hover:text-destructive"
                      onClick={() => handleDelete(workspace.id)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>

                <WorkspaceDocumentList
                  workspaceId={workspace.id}
                  workspaceName={workspace.name}
                  isExpanded={expandedWorkspaces.has(workspace.id)}
                  onToggle={() => toggleWorkspaceExpansion(workspace.id)}
                  onStatsUpdate={(count) => updateWorkspaceStats(workspace.id, count)}
                />
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}