"use client"

import { useState } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { AgentChatInterface } from "@/components/agent/agent-chat-interface"
import { Card } from "@/components/ui/card"

export default function AgentPage() {
  const [selectedWorkspace, setSelectedWorkspace] = useState("global")

  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">智能 Agent 系统</h1>
          <p className="text-muted-foreground mt-1">
            基于 LangChain 的生产级多 Agent 协作平台
          </p>
        </div>
      </div>

      {/* 主要内容区 */}
      <Tabs defaultValue="chat" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3 lg:w-[400px]">
          <TabsTrigger value="chat">对话</TabsTrigger>
          <TabsTrigger value="library">文档库</TabsTrigger>
          <TabsTrigger value="history">历史记录</TabsTrigger>
        </TabsList>

        <TabsContent value="chat" className="space-y-6">
          <AgentChatInterface workspaceId={selectedWorkspace} />
        </TabsContent>

        <TabsContent value="library">
          <Card className="p-6">
            <p className="text-muted-foreground">文档库功能开发中...</p>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card className="p-6">
            <p className="text-muted-foreground">历史记录功能开发中...</p>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

