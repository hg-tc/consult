import { useState, useEffect, useCallback } from "react"
import { statusApi } from "@/lib/api-client"

export interface WorkspaceDocument {
  filename: string
  chunk_count: number
  file_size: number
  upload_time: string
  file_type: string
  chunk_ids: string[]
}

export interface WorkspaceStats {
  workspace_id: string
  document_count: number
  status: string
}

export interface WorkspaceDocumentsResponse {
  workspace_id: string
  documents: WorkspaceDocument[]
  stats: WorkspaceStats
}

export function useWorkspaceDocuments(workspaceId: string) {
  const [documents, setDocuments] = useState<WorkspaceDocument[]>([])
  const [stats, setStats] = useState<WorkspaceStats | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchDocuments = useCallback(async () => {
    if (!workspaceId) return
    
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/documents`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const data: WorkspaceDocumentsResponse = await response.json()
      setDocuments(data.documents || [])
      setStats(data.stats)
    } catch (err) {
      console.error("[v0] Fetch workspace documents error:", err)
      setError(err instanceof Error ? err.message : "获取文档列表失败")
    } finally {
      setIsLoading(false)
    }
  }, [workspaceId])

  const uploadDocument = useCallback(async (file: File) => {
    try {
      const formData = new FormData()
      formData.append("file", file)
      
      const response = await fetch(`/api/workspaces/${workspaceId}/documents/upload`, {
        method: "POST",
        body: formData,
      })
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const result = await response.json()
      
      // 刷新文档列表
      await fetchDocuments()
      
      return result
    } catch (err) {
      console.error("[v0] Upload workspace document error:", err)
      throw err
    }
  }, [workspaceId, fetchDocuments])

  const deleteDocument = useCallback(async (docId: string) => {
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/documents/${docId}`, {
        method: "DELETE",
      })
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const result = await response.json()
      
      // 刷新文档列表
      await fetchDocuments()
      
      return result
    } catch (err) {
      console.error("[v0] Delete workspace document error:", err)
      throw err
    }
  }, [workspaceId, fetchDocuments])

  const downloadDocument = useCallback(async (docId: string, filename: string) => {
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/documents/${docId}/download`)
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      console.error("[v0] Download workspace document error:", err)
      throw err
    }
  }, [workspaceId])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  return {
    documents,
    stats,
    isLoading,
    error,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
    downloadDocument,
  }
}
