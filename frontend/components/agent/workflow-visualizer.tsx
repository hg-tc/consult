"use client"

import { useEffect, useState } from "react"
import { Card } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { 
  Search, 
  Lightbulb, 
  Database, 
  Globe, 
  Layers, 
  FileText, 
  CheckCircle, 
  XCircle,
  Loader2,
  AlertCircle
} from "lucide-react"

interface WorkflowStep {
  id: string
  name: string
  status: "pending" | "running" | "completed" | "failed" | "skipped"
  startTime?: number
  endTime?: number
  progress?: number
  message?: string
  icon: string
}

interface WorkflowVisualizerProps {
  currentStep: string
  steps: WorkflowStep[]
  overallProgress: number
}

export function WorkflowVisualizer({ 
  currentStep, 
  steps, 
  overallProgress 
}: WorkflowVisualizerProps) {
  return (
    <Card className="p-6">
      <div className="space-y-6">
        {/* 整体进度 */}
        <div>
          <div className="flex justify-between mb-2">
            <h3 className="text-lg font-semibold">工作流进度</h3>
            <span className="text-sm text-muted-foreground">
              {overallProgress}%
            </span>
          </div>
          <Progress value={overallProgress} className="h-2" />
        </div>

        {/* 步骤列表 */}
        <div className="space-y-3">
          {steps.map((step, index) => (
            <WorkflowStepCard 
              key={step.id}
              step={step}
              isActive={step.id === currentStep}
              index={index}
            />
          ))}
        </div>
      </div>
    </Card>
  )
}

function WorkflowStepCard({ 
  step, 
  isActive, 
  index 
}: { 
  step: WorkflowStep
  isActive: boolean
  index: number
}) {
  const Icon = getIcon(step.icon)
  
  const getStatusColor = () => {
    switch (step.status) {
      case "completed": return "text-green-500"
      case "running": return "text-blue-500"
      case "failed": return "text-red-500"
      case "skipped": return "text-gray-400"
      default: return "text-gray-300"
    }
  }

  const getStatusIcon = () => {
    switch (step.status) {
      case "completed": return <CheckCircle className="w-5 h-5 text-green-500" />
      case "running": return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
      case "failed": return <XCircle className="w-5 h-5 text-red-500" />
      default: return null
    }
  }

  return (
    <div 
      className={`
        flex items-center gap-4 p-4 rounded-lg border transition-all
        ${isActive ? "border-primary bg-primary/5" : "border-border"}
      `}
    >
      {/* 步骤序号 */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
        <span className="text-sm font-medium">{index + 1}</span>
      </div>

      {/* 图标 */}
      <Icon className={`w-6 h-6 ${getStatusColor()}`} />

      {/* 步骤信息 */}
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <h4 className="font-medium">{step.name}</h4>
          {step.status === "running" && step.progress !== undefined && (
            <Badge variant="outline" className="text-xs">
              {step.progress}%
            </Badge>
          )}
        </div>
        {step.message && (
          <p className="text-sm text-muted-foreground mt-1">
            {step.message}
          </p>
        )}
        {step.status === "running" && step.progress !== undefined && (
          <Progress value={step.progress} className="h-1 mt-2" />
        )}
      </div>

      {/* 状态图标 */}
      {getStatusIcon()}
    </div>
  )
}

function getIcon(iconName: string) {
  const icons: Record<string, any> = {
    Search,
    Lightbulb,
    Database,
    Globe,
    Layers,
    FileText,
    AlertCircle
  }
  return icons[iconName] || FileText
}

