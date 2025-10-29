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

      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.error || '请求失败')
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

