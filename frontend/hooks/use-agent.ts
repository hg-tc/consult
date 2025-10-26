"use client"

// Agent交互的自定义Hook
import React, { useState, useEffect } from "react"
import useSWR from "swr"
import { agentApi } from "@/lib/api-client"

export function useAgent(workspaceId: string | null) {
  const [isSending, setIsSending] = useState(false)
  const [localMessages, setLocalMessages] = useState<any[]>([])

  const { data, error, mutate } = useSWR(workspaceId ? `/agent/chat/${workspaceId}` : null, () =>
    workspaceId ? agentApi.getChatHistory(workspaceId) : null,
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      onError: (err) => {
        console.error("[v0] Agent API error:", err)
      },
      fallbackData: { messages: [], files: [], actions: [] },
    }
  )

  // 新增：使用localStorage持久化每个工作区的对话历史
  const storageKey = workspaceId ? `workspace_history_${workspaceId}` : null

  // 初始化时从localStorage加载历史
  useEffect(() => {
    if (storageKey) {
      try {
        const savedHistory = localStorage.getItem(storageKey)
        if (savedHistory) {
          const parsed = JSON.parse(savedHistory)
          setLocalMessages(parsed)
          console.log(`[useAgent] 加载历史: ${parsed.length} 条消息`)
        } else {
          setLocalMessages([])
        }
      } catch (e) {
        console.error('[useAgent] 加载历史失败:', e)
        setLocalMessages([])
      }
    } else {
      setLocalMessages([])
    }
  }, [storageKey])

  // 保存历史到localStorage
  useEffect(() => {
    if (storageKey && localMessages.length > 0) {
      try {
        localStorage.setItem(storageKey, JSON.stringify(localMessages))
        console.log(`[useAgent] 保存历史: ${localMessages.length} 条消息`)
      } catch (e) {
        console.error('[useAgent] 保存历史失败:', e)
      }
    }
  }, [localMessages, storageKey])

  // 合并服务器消息和本地消息，避免重复
  const messages = React.useMemo(() => {
    const serverMessages = data?.messages || []
    const allMessages = [...serverMessages, ...localMessages]
    
    // 去重：基于id去重
    const uniqueMessages = allMessages.reduce((acc, message) => {
      if (!acc.find(m => m.id === message.id)) {
        acc.push(message)
      }
      return acc
    }, [] as any[])
    
    // 按时间戳排序
    return uniqueMessages.sort((a, b) => 
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )
  }, [data?.messages, localMessages])

  const sendMessage = async (message: string) => {
    if (!workspaceId) return

    setIsSending(true)
    try {
      // 添加用户消息到本地消息列表
      const userMessage = {
        id: `user_${Date.now()}`,
        role: "user",
        content: message,
        timestamp: new Date().toISOString()
      }
      setLocalMessages(prev => [...prev, userMessage])

      // 构建对话历史（发送给后端）
      const history = localMessages.map(msg => ({
        role: msg.role,
        content: msg.content
      }))

      console.log(`[useAgent] 发送消息，包含 ${history.length} 条历史`)

      // 发送消息到服务器（包含历史）
      const result = await agentApi.sendMessage(workspaceId, message, history)

      // 添加AI回复到本地消息列表
      const aiMessage = {
        id: `ai_${Date.now()}`,
        role: "agent",
        content: result.answer,
        timestamp: new Date().toISOString(),
        metadata: result
      }
      setLocalMessages(prev => [...prev, aiMessage])

      // 刷新服务器数据
      await mutate()
      return result
    } finally {
      setIsSending(false)
    }
  }

  const downloadFile = async (fileId: string, filename: string) => {
    const blob = await agentApi.downloadFile(fileId)
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }

  const executeAction = async (actionId: string, params?: any) => {
    if (!workspaceId) return

    const result = await agentApi.executeAction(workspaceId, actionId, params)
    await mutate()
    return result
  }

  // 新增：清除历史功能
  const clearHistory = () => {
    setLocalMessages([])
    if (storageKey) {
      localStorage.removeItem(storageKey)
      console.log(`[useAgent] 清除历史: ${storageKey}`)
    }
  }

  return {
    messages: messages,
    files: data?.files || [],
    actions: data?.actions || [],
    isLoading: !error && !data,
    isError: error,
    isSending,
    sendMessage,
    downloadFile,
    executeAction,
    clearHistory,  // 导出清除功能
    refresh: mutate,
  }
}
