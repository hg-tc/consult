"use client"

import { useState, useRef, useEffect } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Send, Loader2, User, Bot } from "lucide-react"
import { WorkflowVisualizer } from "./workflow-visualizer"

interface Message {
  role: "user" | "agent" | "system"
  content: string
  timestamp: Date
  metadata?: any
}

interface WorkflowState {
  currentStep: string
  steps: any[]
  progress: number
  status: string
}

interface AgentChatInterfaceProps {
  workspaceId: string
}

export function AgentChatInterface({ workspaceId }: AgentChatInterfaceProps) {
  const [input, setInput] = useState("")
  const [messages, setMessages] = useState<Message[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [workflowState, setWorkflowState] = useState<WorkflowState | null>(null)
  const [streamingContent, setStreamingContent] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || isGenerating) return
    
    const userMessage: Message = {
      role: "user",
      content: input,
      timestamp: new Date()
    }
    
    setMessages(prev => [...prev, userMessage])
    setInput("")
    setIsGenerating(true)
    
    // TODO: 实现实际的 WebSocket 连接
    // 这里只是模拟
    setTimeout(() => {
      const agentMessage: Message = {
        role: "agent",
        content: "这是一个测试回复。实际的 WebSocket 实现将在这里。",
        timestamp: new Date()
      }
      setMessages(prev => [...prev, agentMessage])
      setIsGenerating(false)
    }, 1000)
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* 对话区域 */}
      <Card className="lg:col-span-2 flex flex-col h-[600px]">
        <div className="p-4 border-b">
          <h2 className="text-lg font-semibold">智能 Agent 对话</h2>
          <p className="text-sm text-muted-foreground">
            支持文档生成、数据分析、问答等多种任务
          </p>
        </div>

        <ScrollArea className="flex-1 p-4">
          <div className="space-y-4">
            {messages.map((msg, idx) => (
              <MessageBubble key={idx} message={msg} />
            ))}
            <div ref={scrollRef} />
          </div>
        </ScrollArea>

        <div className="p-4 border-t">
          <div className="flex gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder="输入您的需求，如：生成季度报告、分析销售数据..."
              className="min-h-[60px] resize-none"
              disabled={isGenerating}
            />
            <Button 
              onClick={handleSend}
              disabled={isGenerating || !input.trim()}
              size="icon"
              className="h-[60px] w-[60px]"
            >
              {isGenerating ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </Button>
          </div>
        </div>
      </Card>

      {/* 工作流可视化 */}
      <div className="lg:col-span-1">
        {workflowState && (
          <WorkflowVisualizer
            currentStep={workflowState.currentStep}
            steps={workflowState.steps}
            overallProgress={workflowState.progress}
          />
        )}
      </div>
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user"
  
  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div className={`
        flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center
        ${isUser ? "bg-primary text-primary-foreground" : "bg-muted"}
      `}>
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>
      
      <div className={`
        flex-1 rounded-lg p-3 
        ${isUser ? "bg-primary text-primary-foreground" : "bg-muted"}
      `}>
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        <span className="text-xs opacity-70 mt-2 block">
          {message.timestamp.toLocaleTimeString("zh-CN")}
        </span>
      </div>
    </div>
  )
}

