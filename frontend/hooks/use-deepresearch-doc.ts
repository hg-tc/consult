"use client"

import { useState, useCallback } from 'react'

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
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<DeepResearchResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const generateDocument = useCallback(async (
    taskDescription: string,
    workspaceId: string = 'global',
    docRequirements: DocRequirements = {}
  ): Promise<DeepResearchResult | null> => {
    setLoading(true)
    setError(null)
    setResult(null)

    console.log('发送文档生成请求:', { taskDescription, workspaceId })

    try {
      // 使用相对路径，通过 Nginx 代理到后端
      const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || '/api'
      
      const url = `${API_BASE_URL}/document/generate-deepresearch`
      console.log('请求URL:', url)
      
      const response = await fetch(url, {
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

      console.log('收到响应:', response.status, response.statusText)

      if (!response.ok) {
        const errorText = await response.text()
        console.error('响应错误:', errorText)
        throw new Error(errorText || '生成失败')
      }

      const data = await response.json()
      console.log('解析后的数据:', data)
      
      setResult(data)
      return data
    } catch (err) {
      let errorMessage = '生成失败'
      if (err instanceof TypeError && err.message === 'Failed to fetch') {
        errorMessage = '无法连接到后端服务器，请确保后端服务正在运行（http://localhost:13000）'
      } else if (err instanceof Error) {
        errorMessage = err.message
      }
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
  }, [])

  const downloadDocument = useCallback(() => {
    if (!result?.document) return

    // 添加一些元信息
    let content = result.document
    
    if (result.outline?.title) {
      content = `# ${result.outline.title}\n\n${content}`
    }
    
    // 添加质量指标
    if (result.quality_metrics) {
      content += `\n\n---\n\n**生成统计**\n`
      content += `- 总字数: ${result.quality_metrics.total_words}\n`
      content += `- 段落数: ${result.quality_metrics.total_sections}\n`
      content += `- 引用数: ${result.quality_metrics.references_count}\n`
    }

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    
    // 使用时间戳生成文件名
    const timestamp = new Date().toISOString().split('T')[0]
    const filename = result.outline?.title 
      ? `${result.outline.title.replace(/[^\w\s-]/g, '')}_${timestamp}.md`
      : `document_${timestamp}.md`
    
    a.download = filename
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

