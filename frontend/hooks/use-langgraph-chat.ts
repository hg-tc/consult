"use client"

import { useState, useCallback } from 'react'

interface LangGraphResult {
  answer: string
  sources: string[]
  metadata: {
    intent?: string
    complexity?: string
    quality_score?: number
    iterations?: number
    processing_steps?: string[]
    retrieval_strategy?: string
  }
}

export function useLangGraphChat() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<LangGraphResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const sendMessage = useCallback(async (
    question: string,
    workspaceId: string = 'global'
  ): Promise<LangGraphResult | null> => {
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch('/api/apps/langgraph-chat/chat', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question,
          workspace_id: workspaceId
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
      return data
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '请求失败'
      setError(errorMessage)
      console.error('LangGraph chat error:', err)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const clearResult = useCallback(() => {
    setResult(null)
    setError(null)
  }, [])

  return { 
    sendMessage, 
    loading, 
    result, 
    error,
    clearResult
  }
}

