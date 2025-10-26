"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { 
  CheckCircle, 
  Clock, 
  Search, 
  FileText, 
  Brain, 
  Globe, 
  Database,
  AlertCircle,
  Loader2,
  BarChart3,
  Users,
  Zap
} from "lucide-react"

interface WorkflowStep {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'error'
  description?: string
  duration?: number
  details?: string
}

interface WorkflowProgress {
  workflowType: string
  currentStep: string
  steps: WorkflowStep[]
  progress: number
  startTime: number
  estimatedTime?: number
  sourceStats: {
    documents: number
    webResults: number
    conversationTurns: number
  }
  qualityScore?: number
  complexityAnalysis?: {
    level: 'simple' | 'medium' | 'complex'
    factors: string[]
  }
}

interface WorkflowProgressProps {
  progress?: WorkflowProgress | null
  isVisible: boolean
}

const WORKFLOW_ICONS = {
  simple: FileText,
  plan_execute: BarChart3,
  multi_agent: Users,
  react: Brain,
  langgraph: Zap
}

const STEP_ICONS = {
  intent_recognition: Brain,
  planning: BarChart3,
  information_gathering: Search,
  content_generation: FileText,
  quality_review: CheckCircle,
  formatting: FileText,
  web_search: Globe,
  document_search: Database,
  multi_agent_coordination: Users,
  react_reasoning: Brain
}

const STEP_STATUS_COLORS = {
  pending: "bg-gray-100 text-gray-600",
  running: "bg-blue-100 text-blue-600",
  completed: "bg-green-100 text-green-600",
  error: "bg-red-100 text-red-600"
}

const COMPLEXITY_COLORS = {
  simple: "bg-green-100 text-green-700",
  medium: "bg-yellow-100 text-yellow-700", 
  complex: "bg-red-100 text-red-700"
}

export function WorkflowProgress({ progress, isVisible }: WorkflowProgressProps) {
  const [elapsedTime, setElapsedTime] = useState(0)

  useEffect(() => {
    if (!progress || !isVisible) return

    const interval = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - progress.startTime) / 1000))
    }, 1000)

    return () => clearInterval(interval)
  }, [progress, isVisible])

  if (!progress || !isVisible) return null

  const WorkflowIcon = WORKFLOW_ICONS[progress.workflowType as keyof typeof WORKFLOW_ICONS] || FileText

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const getStepIcon = (stepId: string) => {
    const Icon = STEP_ICONS[stepId as keyof typeof STEP_ICONS] || Clock
    return <Icon className="w-4 h-4" />
  }

  const getStepStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-green-600" />
      case 'running':
        return <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-600" />
      default:
        return <Clock className="w-4 h-4 text-gray-400" />
    }
  }

  return (
    <Card className="w-full mb-4 border-l-4 border-l-blue-500">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <WorkflowIcon className="w-5 h-5 text-blue-600" />
            工作流进度
            <Badge variant="outline" className="ml-2">
              {progress.workflowType.replace('_', ' ').toUpperCase()}
            </Badge>
          </CardTitle>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span>已用时: {formatTime(elapsedTime)}</span>
            {progress.estimatedTime && (
              <span>预计: {formatTime(progress.estimatedTime)}</span>
            )}
          </div>
        </div>
        
        {/* 进度条 */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>总体进度</span>
            <span>{progress.progress}%</span>
          </div>
          <Progress value={progress.progress} className="h-2" />
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* 当前步骤 */}
        <div className="flex items-center gap-3 p-3 bg-blue-50 rounded-lg">
          <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />
          <div>
            <div className="font-medium text-blue-900">
              当前步骤: {progress.steps.find(s => s.id === progress.currentStep)?.name || progress.currentStep}
            </div>
            <div className="text-sm text-blue-700">
              {progress.steps.find(s => s.id === progress.currentStep)?.description}
            </div>
          </div>
        </div>

        {/* 步骤列表 */}
        <div className="space-y-2">
          <h4 className="font-medium text-sm text-foreground">执行步骤</h4>
          {progress.steps.map((step, index) => (
            <div 
              key={step.id} 
              className={`flex items-center gap-3 p-2 rounded-lg transition-colors ${
                step.status === 'running' ? 'bg-blue-50' : 
                step.status === 'completed' ? 'bg-green-50' :
                step.status === 'error' ? 'bg-red-50' : 'bg-gray-50'
              }`}
            >
              <div className="flex items-center gap-2">
                {getStepIcon(step.id)}
                {getStepStatusIcon(step.status)}
              </div>
              
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm text-foreground">{step.name}</span>
                  <Badge 
                    variant="secondary" 
                    className={`text-xs ${STEP_STATUS_COLORS[step.status]}`}
                  >
                    {step.status === 'running' ? '进行中' :
                     step.status === 'completed' ? '已完成' :
                     step.status === 'error' ? '错误' : '等待中'}
                  </Badge>
                </div>
                {step.description && (
                  <div className="text-xs text-gray-700 mt-1">
                    {step.description}
                  </div>
                )}
                {step.duration && step.status === 'completed' && (
                  <div className="text-xs text-green-600 mt-1">
                    耗时: {formatTime(step.duration)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* 信息来源统计 */}
        <div className="grid grid-cols-3 gap-3">
          <div className="text-center p-3 bg-gray-50 rounded-lg">
            <Database className="w-5 h-5 mx-auto text-blue-600 mb-1" />
            <div className="text-lg font-semibold">{progress.sourceStats.documents}</div>
            <div className="text-xs text-muted-foreground">本地文档</div>
          </div>
          <div className="text-center p-3 bg-gray-50 rounded-lg">
            <Globe className="w-5 h-5 mx-auto text-green-600 mb-1" />
            <div className="text-lg font-semibold">{progress.sourceStats.webResults}</div>
            <div className="text-xs text-muted-foreground">网络资源</div>
          </div>
          <div className="text-center p-3 bg-gray-50 rounded-lg">
            <FileText className="w-5 h-5 mx-auto text-purple-600 mb-1" />
            <div className="text-lg font-semibold">{progress.sourceStats.conversationTurns}</div>
            <div className="text-xs text-muted-foreground">对话轮次</div>
          </div>
        </div>

        {/* 复杂度分析 */}
        {progress.complexityAnalysis && (
          <div className="p-3 bg-gray-50 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <BarChart3 className="w-4 h-4 text-muted-foreground" />
              <span className="font-medium text-sm">任务复杂度分析</span>
              <Badge 
                variant="secondary" 
                className={`text-xs ${COMPLEXITY_COLORS[progress.complexityAnalysis.level]}`}
              >
                {progress.complexityAnalysis.level.toUpperCase()}
              </Badge>
            </div>
            <div className="text-xs text-muted-foreground">
              影响因素: {progress.complexityAnalysis.factors.join(', ')}
            </div>
          </div>
        )}

        {/* 质量评分 */}
        {progress.qualityScore !== undefined && (
          <div className="p-3 bg-gray-50 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="w-4 h-4 text-muted-foreground" />
              <span className="font-medium text-sm">内容质量评分</span>
            </div>
            <div className="flex items-center gap-2">
              <Progress value={progress.qualityScore * 100} className="flex-1 h-2" />
              <span className="text-sm font-medium">
                {(progress.qualityScore * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
