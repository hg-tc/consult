"use client"

// 全局文档操作的自定义Hook（用于数据库管理页面）
import { useState } from "react"
import useSWR, { mutate as globalMutate } from "swr"
import { globalDocumentApi } from "@/lib/api-client"

export function useGlobalDocuments() {
  const [isUploading, setIsUploading] = useState(false)

  const { data, error, mutate } = useSWR("/global/documents", () => globalDocumentApi.getDocuments(), {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    fallbackData: { documents: [] },
  })

  const uploadDocument = async (file: File) => {
    console.log("[v0] uploadGlobalDocument called with file:", file.name)
    setIsUploading(true)
    try {
      console.log("[v0] Calling global upload API...")
      const result = await globalDocumentApi.uploadDocument(file)
      console.log("[v0] Global upload API response:", result)
      
      // 保存task_id用于状态追踪
      if (result.task_id) {
        console.log("[v0] 文档上传任务ID:", result.task_id)
        // 可以存储到localStorage或状态管理
        localStorage.setItem(`upload_task_${result.id}`, result.task_id)
      }
      
      console.log("[v0] Refreshing data after upload...")
      await mutate()
      console.log("[v0] Data refreshed after upload")
      return result
    } finally {
      setIsUploading(false)
    }
  }

  const deleteDocument = async (id: string) => {
    try {
      console.log("[v0] Starting global delete for document:", id)
      
      // 立即更新本地缓存，移除被删除的文档
      mutate((currentData) => {
        if (!currentData?.documents) return currentData
        
        const updatedDocuments = currentData.documents.filter((doc: any) => doc.id !== id)
        console.log("[v0] Updated local cache, removed document:", id, "remaining:", updatedDocuments.length)
        
        return {
          ...currentData,
          documents: updatedDocuments
        }
      }, false) // 不重新验证，使用本地更新
      
      // 调用删除API
      const result = await globalDocumentApi.deleteDocument(id)
      console.log("[v0] Global delete API response:", result)
      
      console.log("[v0] Global document deleted and cache updated successfully")
      return result
    } catch (error) {
      console.error("[v0] Global document delete error:", error)
      
      // 如果删除失败，重新获取数据以恢复正确状态
      await mutate()
      throw error
    }
  }

  const downloadDocument = async (id: string, filename: string) => {
    try {
      const blob = await globalDocumentApi.downloadDocument(id)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error("[v0] Global document download error:", error)
      throw error
    }
  }

  return {
    data: data?.documents || [],
    isLoading: !error && !data,
    isError: error,
    isUploading,
    uploadDocument,
    deleteDocument,
    downloadDocument,
    refresh: mutate,
  }
}
