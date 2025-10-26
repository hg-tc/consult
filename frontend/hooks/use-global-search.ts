"use client"

import { useState, useEffect } from "react"
import { agentApi } from "@/lib/api-client"

interface GlobalSearchResult {
  answer: string
  references: Array<{
    content_preview: string
    metadata: {
      original_filename: string
      file_path: string
      file_type: string
    }
    similarity: number
  }>
  confidence: number
  metadata: {
    mode: string
    document_count: number
    workspace_id?: string
  }
}

export function useGlobalSearch() {
  const [isSearching, setIsSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<GlobalSearchResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const searchGlobal = async (query: string, workspaceId?: string) => {
    setIsSearching(true)
    setError(null)
    
    try {
      const response = await fetch('/api/global/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          question: query,
          workspace_id: workspaceId,
          top_k: 5
        })
      })

      if (!response.ok) {
        throw new Error(`搜索失败: ${response.status}`)
      }

      const result = await response.json()
      setSearchResults(result)
      return result
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '搜索失败'
      setError(errorMessage)
      console.error('全局搜索失败:', err)
      return null
    } finally {
      setIsSearching(false)
    }
  }

  const clearResults = () => {
    setSearchResults(null)
    setError(null)
  }

  return {
    searchGlobal,
    searchResults,
    isSearching,
    error,
    clearResults
  }
}

export function useGlobalDocuments() {
  const [documents, setDocuments] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadDocuments = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await fetch('/api/global/documents')
      
      if (!response.ok) {
        throw new Error(`加载文档失败: ${response.status}`)
      }

      const result = await response.json()
      setDocuments(result.documents || [])
      return result
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '加载文档失败'
      setError(errorMessage)
      console.error('加载全局文档失败:', err)
      return null
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadDocuments()
  }, [])

  return {
    documents,
    isLoading,
    error,
    reload: loadDocuments
  }
}
