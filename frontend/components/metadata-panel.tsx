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
  const qualityColorConfig = useMemo(() => {
    if (!metadata?.quality_score) return { text: 'text-gray-600', bg: 'bg-gray-100', textColor: 'text-gray-700' }
    const score = metadata.quality_score
    if (score >= 0.8) return { text: 'text-green-600', bg: 'bg-green-100', textColor: 'text-green-700' }
    if (score >= 0.6) return { text: 'text-yellow-600', bg: 'bg-yellow-100', textColor: 'text-yellow-700' }
    return { text: 'text-red-600', bg: 'bg-red-100', textColor: 'text-red-700' }
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
    <div className="mt-4 p-4 bg-muted/50 rounded-lg border border-border">
      <h3 className="font-semibold mb-3 text-foreground">处理信息</h3>
      
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* 意图类型 */}
        {metadata.intent && (
          <div>
            <div className="text-xs text-muted-foreground mb-1">意图</div>
            <div className="font-medium capitalize text-foreground">
              {metadata.intent.replace('_', ' ')}
            </div>
          </div>
        )}

        {/* 复杂度 */}
        {metadata.complexity && (
          <div>
            <div className="text-xs text-muted-foreground mb-1">复杂度</div>
            <div className="font-medium capitalize text-foreground">{metadata.complexity}</div>
          </div>
        )}

        {/* 质量分数 */}
        {metadata.quality_score !== undefined && (
          <div>
            <div className="text-xs text-muted-foreground mb-1">质量分数</div>
            <div className="flex items-center gap-2">
              <div className={`font-medium ${qualityColorConfig.text}`}>
                {(metadata.quality_score * 100).toFixed(0)}%
              </div>
              <div className={`text-xs px-2 py-0.5 rounded ${qualityColorConfig.bg} ${qualityColorConfig.textColor}`}>
                {qualityLabel}
              </div>
            </div>
          </div>
        )}

        {/* 改进次数 */}
        {metadata.iterations !== undefined && (
          <div>
            <div className="text-xs text-muted-foreground mb-1">改进次数</div>
            <div className="font-medium text-foreground">{metadata.iterations}</div>
          </div>
        )}
      </div>

      {/* 处理步骤 */}
      {metadata.processing_steps && metadata.processing_steps.length > 0 && (
        <div className="mt-4">
          <div className="text-xs text-muted-foreground mb-2">处理步骤</div>
          <div className="flex flex-wrap gap-2">
            {metadata.processing_steps.map((step, index) => (
              <span
                key={index}
                className="px-2 py-1 bg-primary/10 text-primary rounded text-xs font-medium"
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
          <div className="text-xs text-muted-foreground mb-1">检索策略</div>
          <div className="text-sm font-medium text-foreground">{metadata.retrieval_strategy}</div>
        </div>
      )}
    </div>
  )
}

