"use client"

import { useState, useCallback, useEffect } from 'react'
import { getClientId } from '@/lib/client-id'

interface LangGraphResult {
  answer: string
  sources: string[]
  thread_id?: string
  metadata: {
    intent?: string
    complexity?: string
    quality_score?: number
    iterations?: number
    processing_steps?: string[]
    retrieval_strategy?: string
    conversation_length?: number
  }
}

export function useLangGraphChat() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<LangGraphResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [threadId, setThreadId] = useState<string | null>(null)
  const [conversationHistory, setConversationHistory] = useState<any[]>([])

  // localStorage 键名
  const STORAGE_KEY_THREAD_ID = 'langgraph_chat_thread_id'
  const STORAGE_KEY_HISTORY = 'langgraph_chat_history'

  // 从 localStorage 加载 threadId 和对话历史
  useEffect(() => {
    try {
      const savedThreadId = localStorage.getItem(STORAGE_KEY_THREAD_ID)
      if (savedThreadId) {
        setThreadId(savedThreadId)
      }
      
      const savedHistory = localStorage.getItem(STORAGE_KEY_HISTORY)
      if (savedHistory) {
        const parsed = JSON.parse(savedHistory)
        setConversationHistory(parsed)
      }
    } catch (e) {
      console.error('[useLangGraphChat] 加载缓存失败:', e)
    }
  }, [])

  // 保存 threadId 到 localStorage
  useEffect(() => {
    if (threadId) {
      try {
        localStorage.setItem(STORAGE_KEY_THREAD_ID, threadId)
      } catch (e) {
        console.error('[useLangGraphChat] 保存threadId失败:', e)
      }
    }
  }, [threadId])

  // 保存对话历史到 localStorage
  useEffect(() => {
    if (conversationHistory.length > 0) {
      try {
        localStorage.setItem(STORAGE_KEY_HISTORY, JSON.stringify(conversationHistory))
      } catch (e) {
        console.error('[useLangGraphChat] 保存历史失败:', e)
      }
    }
  }, [conversationHistory])

  const sendMessage = useCallback(async (
    question: string,
    workspaceId: string = 'global'
  ): Promise<LangGraphResult | null> => {
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      // 获取客户端ID，确保不同设备的对话记忆隔离
      const clientId = getClientId()
      
      // 如果thread_id存在，添加客户端ID前缀，确保不同设备的thread_id不冲突
      const isolatedThreadId = threadId ? `${clientId}:${threadId}` : undefined
      
      const response = await fetch('/api/apps/langgraph-chat/chat', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question,
          workspace_id: workspaceId,
          thread_id: isolatedThreadId,  // 使用带客户端ID前缀的thread_id
          conversation_history: conversationHistory,  // 传递对话历史
          client_id: clientId  // 也传递客户端ID，便于后端识别
        })
      })

      // 先读取响应文本（响应体只能读取一次）
      const text = await response.text()
      
      // 检查响应状态
      if (!response.ok) {
        // 尝试解析错误响应
        let errorMessage = `请求失败: ${response.status} ${response.statusText}`
        if (text) {
          try {
            const contentType = response.headers.get('content-type')
            if (contentType && contentType.includes('application/json')) {
              const errorData = JSON.parse(text)
              errorMessage = errorData.detail || errorData.error || errorMessage
            } else {
              errorMessage = text
            }
          } catch (parseErr) {
            // 如果无法解析，使用原始文本
            errorMessage = text || errorMessage
          }
        }
        throw new Error(errorMessage)
      }

      // 检查响应内容类型
      const contentType = response.headers.get('content-type')
      if (!contentType || !contentType.includes('application/json')) {
        throw new Error(`服务器返回了非 JSON 响应: ${text || '空响应'}`)
      }

      // 检查响应是否为空
      if (!text || text.trim().length === 0) {
        throw new Error('服务器返回了空响应')
      }

      // 解析 JSON
      let data: LangGraphResult
      try {
        data = JSON.parse(text)
      } catch (jsonErr) {
        throw new Error(`无法解析 JSON 响应: ${jsonErr instanceof Error ? jsonErr.message : '未知错误'}`)
      }

      setResult(data)
      
      // 更新 thread_id 和对话历史
      // 注意：后端返回的thread_id可能包含客户端ID，需要提取原始ID
      if (data.thread_id) {
        const clientId = getClientId()
        // 如果thread_id包含客户端ID前缀，去除它
        const extractedThreadId = data.thread_id.startsWith(`${clientId}:`) 
          ? data.thread_id.substring(clientId.length + 1)
          : data.thread_id
        setThreadId(extractedThreadId)
      }
      
      // 更新对话历史
      if (data.answer) {
        setConversationHistory(prev => [
          ...prev,
          {
            user: question,
            assistant: data.answer,
            timestamp: new Date().toISOString()
          }
        ])
      }
      
      return data
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '请求失败'
      setError(errorMessage)
      console.error('LangGraph chat error:', err)
      return null
    } finally {
      setLoading(false)
    }
  }, [threadId, conversationHistory])

  const clearResult = useCallback(() => {
    setResult(null)
    setError(null)
  }, [])

  const clearConversation = useCallback(() => {
    setThreadId(null)
    setConversationHistory([])
    clearResult()
    // 清除 localStorage
    try {
      localStorage.removeItem(STORAGE_KEY_THREAD_ID)
      localStorage.removeItem(STORAGE_KEY_HISTORY)
    } catch (e) {
      console.error('[useLangGraphChat] 清除缓存失败:', e)
    }
  }, [clearResult])

  return { 
    sendMessage, 
    loading, 
    result, 
    error,
    clearResult,
    clearConversation,
    threadId,
    conversationHistory
  }
}

