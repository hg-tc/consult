"use client"

import { useState, useEffect } from 'react'
import { useDeepResearchDoc } from '@/hooks/use-deepresearch-doc'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Loader2, Download, FileText, ArrowLeft } from 'lucide-react'
import { useRouter } from 'next/navigation'

export default function DocumentGeneratorPage() {
  const router = useRouter()
  const STORAGE_PREFIX = 'document_generator_'
  
  // 从 localStorage 加载表单数据
  const [taskDescription, setTaskDescription] = useState(() => {
    if (typeof window === 'undefined') return ''
    return localStorage.getItem(`${STORAGE_PREFIX}taskDescription`) || ''
  })
  const [targetWords, setTargetWords] = useState(() => {
    if (typeof window === 'undefined') return 5000
    const saved = localStorage.getItem(`${STORAGE_PREFIX}targetWords`)
    return saved ? parseInt(saved, 10) : 5000
  })
  const [writingStyle, setWritingStyle] = useState(() => {
    if (typeof window === 'undefined') return '专业、严谨、客观'
    return localStorage.getItem(`${STORAGE_PREFIX}writingStyle`) || '专业、严谨、客观'
  })
  
  const { 
    generateDocument, 
    loading, 
    result, 
    error,
    downloadDocument 
  } = useDeepResearchDoc()

  // 保存表单数据到 localStorage
  useEffect(() => {
    if (taskDescription) {
      localStorage.setItem(`${STORAGE_PREFIX}taskDescription`, taskDescription)
    }
  }, [taskDescription])

  useEffect(() => {
    localStorage.setItem(`${STORAGE_PREFIX}targetWords`, targetWords.toString())
  }, [targetWords])

  useEffect(() => {
    localStorage.setItem(`${STORAGE_PREFIX}writingStyle`, writingStyle)
  }, [writingStyle])

  const handleGenerate = async () => {
    if (!taskDescription.trim()) return
    
    await generateDocument(taskDescription, 'global', {
      target_words: targetWords,
      writing_style: writingStyle
    })
  }

  return (
    <div className="space-y-6">
      {/* 头部导航 */}
      <div className="mb-6 max-w-5xl mx-auto">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/")}
          className="mb-4"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          返回应用广场
        </Button>
        <h1 className="text-3xl font-bold mb-2">文档生成</h1>
        <p className="text-muted-foreground">
          基于 DeepResearch 技术，生成高质量的长文档（2-5万字）
        </p>
      </div>

      <div className="space-y-6 max-w-5xl mx-auto">
        {/* 配置面板 */}
      <Card className="p-6">
        <div className="space-y-4">
          {/* 任务描述 */}
          <div>
            <Label htmlFor="task-description">任务描述 *</Label>
            <Textarea
              id="task-description"
              value={taskDescription}
              onChange={(e) => setTaskDescription(e.target.value)}
              placeholder="例如：写一份关于人工智能在医疗领域应用的调研报告"
              rows={3}
              disabled={loading}
              className="mt-2"
            />
          </div>

          {/* 字数要求 */}
          <div>
            <Label htmlFor="target-words">目标字数</Label>
            <Input
              id="target-words"
              type="number"
              value={targetWords}
              onChange={(e) => setTargetWords(Number(e.target.value))}
              min={1000}
              max={50000}
              step={1000}
              disabled={loading}
              className="mt-2"
            />
            <p className="text-xs text-muted-foreground mt-1">
              建议范围：5000-20000 字
            </p>
          </div>

          {/* 写作风格 */}
          <div>
            <Label htmlFor="writing-style">写作风格</Label>
            <Select value={writingStyle} onValueChange={setWritingStyle} disabled={loading}>
              <SelectTrigger className="mt-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="⚡ 精炼">⚡ 精炼</SelectItem>
                <SelectItem value="🛡️ 专业">🛡️ 专业</SelectItem>
                <SelectItem value="📝 中正">📝 中正</SelectItem>
                <SelectItem value="💬 具象">💬 具象</SelectItem>
                <SelectItem value="⏱️ 提速">⏱️ 提速</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* 生成按钮 */}
          <Button
            onClick={handleGenerate}
            disabled={loading || !taskDescription.trim()}
            className="w-full"
            size="lg"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                生成中...
              </>
            ) : (
              <>
                <FileText className="w-4 h-4 mr-2" />
                开始生成文档
              </>
            )}
          </Button>
        </div>
      </Card>

      {/* 错误提示 */}
      {error && (
        <Card className="p-4 border-destructive bg-destructive/10">
          <p className="text-destructive">{error}</p>
        </Card>
      )}

      {/* 生成进度 */}
      {loading && (
        <Card className="p-6 border-primary bg-primary/10">
          <div className="flex items-center gap-2 mb-2">
            <Loader2 className="w-5 h-5 animate-spin text-primary" />
            <span className="font-medium">正在生成...</span>
          </div>
          <p className="text-sm text-muted-foreground">
            这可能需要几分钟时间，请耐心等待
          </p>
        </Card>
      )}

      {/* 结果展示 */}
      {result && (
        <div className="space-y-4">
          {/* 质量指标 */}
          <Card className="p-4 border-green-200 bg-green-50">
            <h3 className="font-semibold text-green-900 mb-2">✅ 生成完成</h3>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-green-600">字数: </span>
                <span className="font-medium text-green-600">{result.quality_metrics?.total_words || 0}</span>
              </div>
              <div>
                <span className="text-green-600">段落: </span>
                <span className="font-medium text-green-600">{result.quality_metrics?.total_sections || 0}</span>
              </div>
              <div>
                <span className="text-green-600">引用: </span>
                <span className="font-medium text-green-600">{result.quality_metrics?.references_count || 0}</span>
              </div>
            </div>
          </Card>

          {/* 大纲 */}
          {result.outline && (
            <Card className="p-4">
              <h3 className="font-semibold mb-2">📋 文档大纲</h3>
              <div className="text-sm text-muted-foreground">
                {result.outline.title || JSON.stringify(result.outline)}
              </div>
            </Card>
          )}

          {/* 参考文献 */}
          {result.references && result.references.length > 0 && (
            <Card className="p-4">
              <h3 className="font-semibold mb-2">📚 参考文献</h3>
              <ol className="list-decimal list-inside space-y-1 text-sm">
                {result.references.map((ref: any, idx: number) => (
                  <li key={idx} className="text-muted-foreground">
                    {ref.source || ref.title || JSON.stringify(ref)}
                  </li>
                ))}
              </ol>
            </Card>
          )}

          {/* 文档内容 */}
          <Card className="p-4">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-semibold">📄 文档内容</h3>
              <Button onClick={downloadDocument} variant="outline" size="sm">
                <Download className="w-4 h-4 mr-2" />
                下载文档
              </Button>
            </div>
            <div className="prose max-w-none">
              <pre className="whitespace-pre-wrap text-sm bg-muted p-4 rounded max-h-96 overflow-auto">
                {result.document}
              </pre>
            </div>
          </Card>
        </div>
      )}
      </div>
    </div>
  )
}

