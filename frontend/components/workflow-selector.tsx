"use client"

import { useState } from 'react'

export type WorkflowType = 'simple' | 'langgraph' | 'deepresearch'

interface Workflow {
  id: WorkflowType
  name: string
  description: string
  icon: string
}

interface WorkflowSelectorProps {
  onSelect: (workflow: WorkflowType) => void
  selected: WorkflowType
  disabled?: boolean
}

const workflows: Workflow[] = [
  {
    id: 'simple',
    name: '简单问答',
    description: '适用于简单快速的问题',
    icon: '⚡'
  },
  {
    id: 'langgraph',
    name: '智能问答',
    description: '自动适配复杂问题，支持多跳推理',
    icon: '🧠'
  },
  {
    id: 'deepresearch',
    name: '长文档生成',
    description: '生成高质量的长文档（2-5万字）',
    icon: '📄'
  }
]

export function WorkflowSelector({ onSelect, selected, disabled }: WorkflowSelectorProps) {
  return (
    <div className="flex gap-3 mb-4 flex-wrap">
      {workflows.map(workflow => (
        <button
          key={workflow.id}
          onClick={() => !disabled && onSelect(workflow.id)}
          disabled={disabled}
          className={`
            px-4 py-3 rounded-lg border-2 transition-all min-w-[140px]
            ${selected === workflow.id 
              ? 'border-primary bg-primary/10 text-primary' 
              : 'border-gray-300 bg-white hover:border-gray-400'
            }
            ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="text-2xl">{workflow.icon}</span>
            <div className="font-semibold text-sm">{workflow.name}</div>
          </div>
          <div className="text-xs text-gray-600 text-left">{workflow.description}</div>
        </button>
      ))}
    </div>
  )
}

