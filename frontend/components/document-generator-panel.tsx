"use client"

import { useState } from 'react'
import { useDeepResearchDoc } from '@/hooks/use-deepresearch-doc'
import { WorkflowSelector, WorkflowType } from './workflow-selector'

export function DocumentGeneratorPanel() {
  const [workflow, setWorkflow] = useState<WorkflowType>('deepresearch')
  const [taskDescription, setTaskDescription] = useState('')
  const [targetWords, setTargetWords] = useState(5000)
  const [writingStyle, setWritingStyle] = useState('专业、严谨、客观')
  const [copied, setCopied] = useState(false)
  
  const { 
    generateDocument, 
    loading, 
    result, 
    error,
    downloadDocument 
  } = useDeepResearchDoc()

  const handleGenerate = async () => {
    if (!taskDescription.trim()) return
    
    await generateDocument(taskDescription, 'global', {
      target_words: targetWords,
      writing_style: writingStyle
    })
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold mb-4">长文档生成</h2>
        <p className="text-gray-600 mb-6">
          基于 DeepResearch 技术，生成高质量的长文档（2-5万字）
        </p>
      </div>

      {/* 配置面板 */}
      <div className="bg-white p-6 rounded-lg border shadow-sm">
        <div className="space-y-4">
          {/* 任务描述 */}
          <div>
            <label className="block text-sm font-medium mb-2">
              任务描述 *
            </label>
            <textarea
              value={taskDescription}
              onChange={(e) => setTaskDescription(e.target.value)}
              placeholder="例如：写一份关于人工智能在医疗领域应用的调研报告"
              rows={3}
              className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
              disabled={loading}
            />
          </div>

          {/* 字数要求 */}
          <div>
            <label className="block text-sm font-medium mb-2">
              目标字数
            </label>
            <input
              type="number"
              value={targetWords}
              onChange={(e) => setTargetWords(Number(e.target.value))}
              min={1000}
              max={50000}
              step={1000}
              className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
              disabled={loading}
            />
            <div className="mt-1 text-xs text-gray-500">
              建议范围：5000-20000 字
            </div>
          </div>

          {/* 写作风格 */}
          <div>
            <label className="block text-sm font-medium mb-2">
              写作风格
            </label>
            <select
              value={writingStyle}
              onChange={(e) => setWritingStyle(e.target.value)}
              className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
              disabled={loading}
            >
              <option value="⚡ 精炼">⚡ 精炼</option>
              <option value="🛡️ 专业">🛡️ 专业</option>
              <option value="📝 中正">📝 中正</option>
              <option value="💬 具象">💬 具象</option>
              <option value="⏱️ 提速">⏱️ 提速</option>
            </select>
          </div>

          {/* 生成按钮 */}
          <button
            onClick={handleGenerate}
            disabled={loading || !taskDescription.trim()}
            className="w-full px-4 py-3 bg-primary text-white rounded-md hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? '生成中...' : '开始生成文档'}
          </button>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* 生成进度 */}
      {loading && (
        <div className="bg-blue-50 border border-blue-200 p-4 rounded">
          <div className="flex items-center gap-2 mb-2">
            <div className="animate-spin h-4 w-4 border-2 border-blue-600 border-t-transparent rounded-full"></div>
            <span className="text-blue-700 font-medium">正在生成...</span>
          </div>
          <p className="text-sm text-blue-600 mb-3">
            这可能需要几分钟时间，请耐心等待
          </p>
          {/* 进度步骤 */}
          <div className="space-y-2">
            {[
              { step: 'outline_planning', label: '📝 生成提纲' },
              { step: 'parallel_retrieval', label: '🔍 并行检索' },
              { step: 'parallel_generation', label: '✍️ 并行生成' },
              { step: 'merge_sections', label: '🔗 合并段落' },
              { step: 'final_polish', label: '✨ 最终润色' }
            ].map((phase, idx) => (
              <div key={idx} className="flex items-center gap-2 text-sm">
                <div className="w-4 h-4 rounded-full bg-blue-200 flex items-center justify-center">
                  <div className="w-2 h-2 rounded-full bg-blue-600 animate-pulse"></div>
                </div>
                <span className="text-blue-700">{phase.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 结果展示 */}
      {result && (
        <div className="space-y-4">
          {/* 质量指标 */}
          <div className="bg-green-50 border border-green-200 p-4 rounded">
            <h3 className="font-semibold text-green-900 mb-2">✅ 生成完成</h3>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-green-600">字数: </span>
                <span className="font-medium">{result.quality_metrics.total_words}</span>
              </div>
              <div>
                <span className="text-green-600">段落: </span>
                <span className="font-medium">{result.quality_metrics.total_sections}</span>
              </div>
              <div>
                <span className="text-green-600">引用: </span>
                <span className="font-medium">{result.quality_metrics.references_count}</span>
              </div>
            </div>
          </div>

          {/* 大纲 */}
          {result.outline && (
            <div className="bg-white p-4 rounded-lg border">
              <h3 className="font-semibold mb-3">📋 文档大纲</h3>
              <div className="text-lg font-medium mb-3 text-gray-800">
                {result.outline.title}
              </div>
              {result.outline.sections && result.outline.sections.length > 0 && (
                <div className="border-t pt-3">
                  <div className="space-y-1">
                    {result.outline.sections.map((section: any, idx: number) => (
                      <div key={idx} className="text-sm" style={{ paddingLeft: `${(section.level - 1) * 16}px` }}>
                        <span className="text-gray-600">•</span>
                        <span className="ml-2 text-gray-700">{section.title}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 参考文献 */}
          {result.references && result.references.length > 0 && (
            <div className="bg-white p-4 rounded-lg border">
              <h3 className="font-semibold mb-2">📚 参考文献</h3>
              <ol className="list-decimal list-inside space-y-1 text-sm">
                {result.references.map(ref => (
                  <li key={ref.id} className="text-gray-700">
                    {ref.source}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* 处理步骤 */}
          {result.processing_steps && result.processing_steps.length > 0 && (
            <div className="bg-white p-4 rounded-lg border">
              <h3 className="font-semibold mb-3">⚙️ 处理步骤</h3>
              <div className="space-y-2">
                {result.processing_steps.map((step, idx) => (
                  <div key={idx} className="flex items-center gap-2 text-sm">
                    <div className="w-5 h-5 rounded-full bg-green-100 flex items-center justify-center">
                      <span className="text-xs text-green-600">✓</span>
                    </div>
                    <span className="text-gray-700 capitalize">
                      {step.replace(/_/g, ' ')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 文档内容 */}
          <div className="bg-white p-4 rounded-lg border">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-semibold">📄 文档内容</h3>
              <div className="flex gap-2">
                <button
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(result.document)
                      setCopied(true)
                      setTimeout(() => setCopied(false), 2000)
                    } catch (err) {
                      console.error('复制失败:', err)
                    }
                  }}
                  className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors"
                >
                  {copied ? '✓ 已复制' : '复制内容'}
                </button>
                <button
                  onClick={downloadDocument}
                  className="px-3 py-1 text-sm bg-primary text-white rounded hover:bg-primary/90 transition-colors"
                >
                  下载文档
                </button>
              </div>
            </div>
            <div className="prose max-w-none">
              <div className="bg-gray-50 p-4 rounded max-h-[600px] overflow-auto border border-gray-200">
                <pre className="whitespace-pre-wrap text-sm text-gray-800 font-sans leading-relaxed">
                  {result.document}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

