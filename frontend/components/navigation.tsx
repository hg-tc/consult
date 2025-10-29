"use client"

import { Database, FolderKanban, Activity, FileText, Brain } from "lucide-react"
import { cn } from "@/lib/utils"

interface NavigationProps {
  activeTab: string
  onTabChange: (tab: string) => void
}

export function Navigation({ activeTab, onTabChange }: NavigationProps) {
  const tabs = [
    { id: "database", label: "数据库管理", icon: Database },
    { id: "workspace", label: "工作区", icon: FolderKanban },
    { id: "status", label: "处理状态", icon: Activity },
    { id: "langgraph", label: "智能问答", icon: Brain },
    { id: "doc-generator", label: "文档生成", icon: FileText },
  ]

  return (
    <nav className="border-b border-border bg-card">
      <div className="container mx-auto px-6">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary">
              <div className="w-4 h-4 border-2 border-primary-foreground rounded" />
            </div>
            <h1 className="text-xl font-semibold text-foreground">Agent Service Platform</h1>
          </div>

          <div className="flex gap-1">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => onTabChange(tab.id)}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                    activeTab === tab.id
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-secondary",
                  )}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </nav>
  )
}
