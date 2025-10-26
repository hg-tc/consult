"use client"

// 工作区操作的自定义Hook
import { useState } from "react"
import useSWR from "swr"
import { workspaceApi } from "@/lib/api-client"

export function useWorkspaces() {
  const [isCreating, setIsCreating] = useState(false)

  const { data, error, mutate } = useSWR("/workspaces", () => workspaceApi.getWorkspaces(), {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    onError: (err) => {
      console.error("[v0] Workspaces API error:", err)
    },
    fallbackData: { workspaces: [] },
    // 添加更积极的重新验证策略
    dedupingInterval: 0, // 禁用去重，确保每次都是最新数据
    refreshInterval: 0, // 禁用自动刷新
  })

  const createWorkspace = async (name: string) => {
    setIsCreating(true)
    try {
      const result = await workspaceApi.createWorkspace(name)
      
      // 立即更新本地缓存，添加新工作区
      mutate((currentData) => {
        if (!currentData?.workspaces) return currentData
        
        const updatedWorkspaces = [...currentData.workspaces, result]
        console.log("[v0] Updated local cache, added workspace:", result.id, "total:", updatedWorkspaces.length)
        
        return {
          ...currentData,
          workspaces: updatedWorkspaces
        }
      }, false) // 不重新验证，使用本地更新
      
      // 强制重新获取数据以确保同步
      await mutate()
      
      return result
    } catch (error) {
      console.error("[v0] Workspace creation error:", error)
      throw error
    } finally {
      setIsCreating(false)
    }
  }

  const updateWorkspace = async (id: string, name: string) => {
    try {
      await workspaceApi.updateWorkspace(id, name)
      await mutate()
    } catch (error) {
      console.error("[v0] Workspace update error:", error)
      throw error
    }
  }

  const deleteWorkspace = async (id: string) => {
    try {
      console.log("[v0] Starting delete for workspace:", id)
      
      // 调用删除API
      const result = await workspaceApi.deleteWorkspace(id)
      console.log("[v0] Delete workspace API response:", result)
      
      // 手动更新缓存，移除已删除的工作区
      mutate((currentData) => {
        if (!currentData?.workspaces) return currentData
        
        const updatedWorkspaces = currentData.workspaces.filter((workspace: any) => workspace.id !== id)
        console.log("[v0] Updated local cache, removed workspace:", id, "remaining:", updatedWorkspaces.length)
        
        return {
          ...currentData,
          workspaces: updatedWorkspaces
        }
      }, false) // false表示不重新验证，直接使用本地更新
      
      console.log("[v0] Workspace deleted and cache updated successfully")
      return result
    } catch (error) {
      console.error("[v0] Workspace delete error:", error)
      
      // 如果删除失败，重新获取数据以恢复正确状态
      await mutate()
      throw error
    }
  }

  const uploadFile = async (workspaceId: string, file: File) => {
    try {
      const result = await workspaceApi.uploadFile(workspaceId, file)
      await mutate()
      return result
    } catch (error) {
      console.error("[v0] File upload error:", error)
      throw error
    }
  }

  return {
    workspaces: data?.workspaces || [],
    isLoading: !error && !data,
    isError: error,
    isCreating,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
    uploadFile,
    refresh: mutate,
  }
}
