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

    console.log('发送消息:', { question, workspaceId })

    try {
      // 使用相对路径，通过 Nginx 代理到后端
      const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || '/api'
      
      const url = `${API_BASE_URL}/chat/langgraph`
      console.log('请求URL:', url)
      
      const response = await fetch(url, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question,
          workspace_id: workspaceId
        })
      })

      console.log('收到响应:', response.status, response.statusText)

      if (!response.ok) {
        const errorText = await response.text()
        console.error('响应错误:', errorText)
        throw new Error(errorText || '请求失败')
      }

      const data = await response.json()
      console.log('解析后的数据:', data)
      
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
