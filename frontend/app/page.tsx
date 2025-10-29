"use client"

import { useState } from "react"
import { Navigation } from "@/components/navigation"
import { DatabasePanel } from "@/components/database-panel"
import { WorkspacePanel } from "@/components/workspace-panel"
import { StatusPanel } from "@/components/enhanced-status-panel"
import { DocumentGeneratorPanel } from "@/components/document-generator-panel"
import { LangGraphChatPanel } from "@/components/langgraph-chat-panel"

export default function Home() {
  const [activeTab, setActiveTab] = useState("database")

  const renderContent = () => {
    switch (activeTab) {
      case "database":
        return <DatabasePanel />
      case "workspace":
        return <WorkspacePanel />
      case "status":
        return <StatusPanel />
      case "langgraph":
        return <LangGraphChatPanel />
      case "doc-generator":
        return <DocumentGeneratorPanel />
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
        <h1 className="text-3xl font-bold text-center mb-8">
          AI咨询平台
        </h1>
        
        {renderContent()}
      </div>
    </div>
  )
}