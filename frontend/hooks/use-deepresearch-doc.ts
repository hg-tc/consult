"use client"

import { useState, useCallback, useEffect } from 'react'

export interface DocRequirements {
  target_words?: number
  writing_style?: string
}

export interface DeepResearchResult {
  document: string
  quality_metrics: {
    total_words: number
    total_sections: number
    references_count: number
  }
  references: Array<{
    id: number
    source: string
  }>
  outline: {
    title: string
    sections: any[]
  }
  processing_steps: string[]
}

export function useDeepResearchDoc() {
  const STORAGE_KEY = 'deepresearch_doc_result'
  
  const [loading, setLoading] = useState(false)
  // 从 localStorage 加载结果
  const [result, setResult] = useState<DeepResearchResult | null>(() => {
    if (typeof window === 'undefined') return null
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      return saved ? JSON.parse(saved) : null
    } catch (e) {
      return null
    }
  })
  const [error, setError] = useState<string | null>(null)

  // 保存结果到 localStorage
  useEffect(() => {
    if (result) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(result))
      } catch (e) {
        console.error('[useDeepResearchDoc] 保存结果失败:', e)
      }
    }
  }, [result])

  const generateDocument = useCallback(async (
    taskDescription: string,
    workspaceId: string = 'global',
    docRequirements: DocRequirements = {}
  ): Promise<DeepResearchResult | null> => {
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch('/api/apps/document-generator/generate', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          task_description: taskDescription,
          workspace_id: workspaceId,
          doc_requirements: {
            target_words: 5000,
            writing_style: '专业、严谨、客观',
            ...docRequirements
          }
        })
      })

      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.error || '生成失败')
      }

      setResult(data)
      return data
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '生成失败'
      setError(errorMessage)
      console.error('DeepResearch generation error:', err)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const clearResult = useCallback(() => {
    setResult(null)
    setError(null)
    // 清除 localStorage
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch (e) {
      console.error('[useDeepResearchDoc] 清除结果缓存失败:', e)
    }
  }, [])

  const downloadDocument = useCallback(() => {
    if (!result?.document) return

    const blob = new Blob([result.document], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${result.outline?.title || 'document'}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [result])

  return { 
    generateDocument, 
    loading, 
    result, 
    error,
    clearResult,
    downloadDocument
  }
}

