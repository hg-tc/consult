"use client"

import { useMemo } from 'react'

interface MetadataPanelProps {
  metadata?: {
    intent?: string
    complexity?: string
    quality_score?: number
    iterations?: number
    processing_steps?: string[]
    retrieval_strategy?: string
  }
}

export function MetadataPanel({ metadata }: MetadataPanelProps) {
  const qualityColor = useMemo(() => {
    if (!metadata?.quality_score) return 'gray'
    const score = metadata.quality_score
    if (score >= 0.8) return 'green'
    if (score >= 0.6) return 'yellow'
    return 'red'
  }, [metadata?.quality_score])

  const qualityLabel = useMemo(() => {
    if (!metadata?.quality_score) return 'N/A'
    const score = metadata.quality_score
    if (score >= 0.8) return '优秀'
    if (score >= 0.6) return '良好'
    return '待改进'
  }, [metadata?.quality_score])

  if (!metadata) return null

  return (
    <div className="mt-4 p-4 bg-gray-50 rounded-lg border">
      <h3 className="font-semibold mb-3">处理信息</h3>
      
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* 意图类型 */}
        {metadata.intent && (
          <div>
            <div className="text-xs text-gray-500 mb-1">意图</div>
            <div className="font-medium capitalize">
              {metadata.intent.replace('_', ' ')}
            </div>
          </div>
        )}

        {/* 复杂度 */}
        {metadata.complexity && (
          <div>
            <div className="text-xs text-gray-500 mb-1">复杂度</div>
            <div className="font-medium capitalize">{metadata.complexity}</div>
          </div>
        )}

        {/* 质量分数 */}
        {metadata.quality_score !== undefined && (
          <div>
            <div className="text-xs text-gray-500 mb-1">质量分数</div>
            <div className="flex items-center gap-2">
              <div className={`font-medium text-${qualityColor}-600`}>
                {(metadata.quality_score * 100).toFixed(0)}%
              </div>
              <div className={`text-xs px-2 py-0.5 rounded bg-${qualityColor}-100 text-${qualityColor}-700`}>
                {qualityLabel}
              </div>
            </div>
          </div>
        )}

        {/* 改进次数 */}
        {metadata.iterations !== undefined && (
          <div>
            <div className="text-xs text-gray-500 mb-1">改进次数</div>
            <div className="font-medium">{metadata.iterations}</div>
          </div>
        )}
      </div>

      {/* 处理步骤 */}
      {metadata.processing_steps && metadata.processing_steps.length > 0 && (
        <div className="mt-4">
          <div className="text-xs text-gray-500 mb-2">处理步骤</div>
          <div className="flex flex-wrap gap-2">
            {metadata.processing_steps.map((step, index) => (
              <span
                key={index}
                className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs"
              >
                {step}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 检索策略 */}
      {metadata.retrieval_strategy && (
        <div className="mt-3">
          <div className="text-xs text-gray-500 mb-1">检索策略</div>
          <div className="text-sm font-medium">{metadata.retrieval_strategy}</div>
        </div>
      )}
    </div>
  )
}

