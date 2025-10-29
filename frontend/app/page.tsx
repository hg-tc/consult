"use client"

import { useState, useEffect } from "react"
import { Navigation } from "@/components/navigation"
import { DatabasePanel } from "@/components/database-panel"
import { WorkspacePanel } from "@/components/workspace-panel"
import { StatusPanel } from "@/components/enhanced-status-panel"
import { AppSquare } from "@/components/app-square"
import { useSearchParams } from "next/navigation"

export default function Home() {
  const searchParams = useSearchParams()
  const [activeTab, setActiveTab] = useState("apps")

  useEffect(() => {
    // 从 URL 参数读取 tab（用于从应用页面导航回来）
    const tab = searchParams?.get("tab")
    if (tab && ["apps", "database", "workspace", "status"].includes(tab)) {
      setActiveTab(tab)
    }
  }, [searchParams])

  const renderContent = () => {
    switch (activeTab) {
      case "apps":
        return <AppSquare />
      case "database":
        return <DatabasePanel />
      case "workspace":
        return <WorkspacePanel />
      case "status":
        return <StatusPanel />
      default:
        return (
          <div className="text-center">
            <p className="text-lg text-muted-foreground mb-4">
              系统正在运行中...
            </p>
            <p className="text-sm text-muted-foreground">
              当前活动标签: {activeTab}
            </p>
          </div>
        )
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <Navigation activeTab={activeTab} onTabChange={setActiveTab} />
      
      <div className="container mx-auto px-4 py-8">
        {activeTab === "apps" ? (
          <>
            <h1 className="text-3xl font-bold text-center mb-2">
              应用广场
            </h1>
            <p className="text-center text-muted-foreground mb-8">
              选择应用开始使用 AI 功能
            </p>
          </>
        ) : (
          <h1 className="text-3xl font-bold text-center mb-8">
            AI咨询平台
          </h1>
        )}
        
        {renderContent()}
      </div>
    </div>
  )
}