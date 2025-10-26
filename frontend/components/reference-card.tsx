"use client"

import React, { useState } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ExternalLink, FileText, Download, Eye } from "lucide-react"

interface Reference {
  document_id: string
  document_name: string
  chunk_id: string
  content: string
  page_number?: number
  similarity: number
  rank: number
  highlight?: string
  access_url: string
  source_type?: string
  workspace_id?: string
}

interface ReferenceCardProps {
  reference: Reference
  onPreview?: (reference: Reference) => void
  onDownload?: (reference: Reference) => void
}

export function ReferenceCard({ reference, onPreview, onDownload }: ReferenceCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  
  const handlePreview = () => {
    if (onPreview) {
      onPreview(reference)
    } else {
      // 默认行为：在新窗口打开预览
      const apiPath = reference.source_type === 'global' 
        ? `/api/global/documents/${reference.document_id}/preview`
        : `/api/workspaces/${reference.workspace_id}/documents/${reference.document_id}/preview`
      window.open(`${apiPath}?highlight=${encodeURIComponent(reference.highlight || '')}`, '_blank')
    }
  }
  
  const handleDownload = () => {
    if (onDownload) {
      onDownload(reference)
    } else {
      // 默认行为：下载文档
      const apiPath = reference.source_type === 'global' 
        ? `/api/global/documents/${reference.document_id}/download`
        : `/api/workspaces/${reference.workspace_id}/documents/${reference.document_id}/download`
      window.open(apiPath, '_blank')
    }
  }
  
  const getSimilarityColor = (similarity: number) => {
    if (similarity >= 0.8) return "bg-green-100 text-green-800"
    if (similarity >= 0.6) return "bg-yellow-100 text-yellow-800"
    return "bg-red-100 text-red-800"
  }
  
  return (
    <Card className="p-1.5 bg-card border-border hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between mb-1">
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          <FileText className="w-3 h-3 text-primary flex-shrink-0" />
          <h4 className="font-medium text-foreground text-xs truncate">
            {reference.document_name}
          </h4>
          {reference.source_type && (
            <Badge 
              variant={reference.source_type === "global" ? "default" : "outline"} 
              className="text-xs px-1 py-0 h-3"
            >
              {reference.source_type === "global" ? "全局" : "工作区"}
            </Badge>
          )}
        </div>
        
        <div className="flex items-center gap-1 ml-2">
          <Badge 
            className={`text-xs px-1 py-0 h-3 ${getSimilarityColor(reference.similarity)}`}
          >
            {Math.round(reference.similarity * 100)}%
          </Badge>
        </div>
      </div>
      
      <div className="mb-1">
        <p className="text-xs text-muted-foreground leading-tight line-clamp-2">
          {isExpanded ? reference.content : `${reference.content.substring(0, 100)}...`}
        </p>
        {reference.content.length > 100 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsExpanded(!isExpanded)}
            className="h-3 px-1 text-xs mt-0.5"
          >
            {isExpanded ? "收起" : "展开"}
          </Button>
        )}
      </div>
      
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          {reference.page_number && (
            <span className="text-xs text-muted-foreground">
              第 {reference.page_number} 页
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={handlePreview}
            className="h-5 w-5 p-0"
            title="预览文档"
          >
            <Eye className="w-2.5 h-2.5" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDownload}
            className="h-5 w-5 p-0"
            title="下载文档"
          >
            <Download className="w-2.5 h-2.5" />
          </Button>
        </div>
      </div>
    </Card>
  )
}

interface ReferenceListProps {
  references: Reference[]
  onPreview?: (reference: Reference) => void
  onDownload?: (reference: Reference) => void
  maxDisplay?: number
}

export function ReferenceList({ 
  references, 
  onPreview, 
  onDownload, 
  maxDisplay = 1  // 默认只显示1条
}: ReferenceListProps) {
  const [showAll, setShowAll] = useState(false)
  
  // 去重逻辑：同一文件只保留排名最高的引用
  const deduplicatedReferences = references.reduce((acc, ref) => {
    const key = `${ref.document_name}-${ref.source_type || 'unknown'}`
    if (!acc[key] || ref.rank < acc[key].rank) {
      acc[key] = ref
    }
    return acc
  }, {} as Record<string, Reference>)
  
  const uniqueReferences = Object.values(deduplicatedReferences)
  const displayedReferences = showAll ? uniqueReferences : uniqueReferences.slice(0, maxDisplay)
  const hasMore = uniqueReferences.length > maxDisplay
  
  if (!references || references.length === 0) {
    return null
  }
  
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium text-muted-foreground">
          引用 ({uniqueReferences.length})
        </h3>
        {hasMore && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowAll(!showAll)}
            className="h-4 px-2 text-xs"
          >
            {showAll ? "收起" : `显示全部 ${uniqueReferences.length} 个`}
          </Button>
        )}
      </div>
      
      <div className="space-y-0.5">
        {displayedReferences.map((reference, index) => (
          <ReferenceCard
            key={`${reference.document_id}-${reference.chunk_id}-${index}`}
            reference={reference}
            onPreview={onPreview}
            onDownload={onDownload}
          />
        ))}
      </div>
      
      {hasMore && showAll && (
        <div className="text-center pt-0.5">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowAll(false)}
            className="h-4 px-2 text-xs"
          >
            收起引用
          </Button>
        </div>
      )}
    </div>
  )
}