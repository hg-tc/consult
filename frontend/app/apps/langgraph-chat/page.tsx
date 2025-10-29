"use client"

import { useState, useRef, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useLangGraphChat } from '@/hooks/use-langgraph-chat'
import { MetadataPanel } from '@/components/metadata-panel'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Send, Loader2, User, Bot, RefreshCw, ArrowLeft } from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  metadata?: any
}

export default function LangGraphChatPage() {
  const router = useRouter()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  const { sendMessage, loading, result, error, clearResult } = useLangGraphChat()

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (result) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: result.answer,
        timestamp: new Date(),
        metadata: result.metadata
      }])
    }
  }, [result])

  const handleSend = async () => {
    if (!input.trim() || loading) return

    const userMessage: Message = {
      role: 'user',
      content: input,
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    clearResult()

    await sendMessage(input)
  }

  const clearMessages = () => {
    setMessages([])
    clearResult()
  }

  return (
    <div className="space-y-6">
      {/* 头部导航 */}
      <div className="mb-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/")}
          className="mb-4"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          返回应用广场
        </Button>
        <h1 className="text-3xl font-bold mb-2">智能问答</h1>
        <p className="text-muted-foreground">
          基于 LangGraph 的智能问答系统，支持自适应路由、多跳推理和质量保证
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3 max-w-7xl mx-auto">
        {/* 对话区域 */}
        <Card className="lg:col-span-2 flex flex-col h-[600px]">
          <div className="p-4 border-b flex items-center justify-between">
            <div>
              <h3 className="font-semibold">智能对话</h3>
              <p className="text-sm text-muted-foreground">
                支持简单问答、复杂推理和多跳查询
              </p>
            </div>
            {messages.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={clearMessages}
              >
                <RefreshCw className="w-4 h-4 mr-2" />
                清空对话
              </Button>
            )}
          </div>

          <ScrollArea className="flex-1 p-4">
            <div className="space-y-4">
              {messages.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Bot className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>开始一个新的对话</p>
                  <p className="text-sm mt-2">支持简单问答、复杂推理等多种场景</p>
                </div>
              ) : (
                messages.map((msg, idx) => (
                  <MessageBubble key={idx} message={msg} />
                ))
              )}
              {loading && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span className="text-sm">正在思考...</span>
                </div>
              )}
              <div ref={scrollRef} />
            </div>
          </ScrollArea>

          <div className="p-4 border-t">
            <div className="flex gap-2">
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSend()
                  }
                }}
                placeholder="输入您的问题..."
                className="min-h-[60px] resize-none"
                disabled={loading}
              />
              <Button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                size="icon"
                className="h-[60px] w-[60px] shrink-0"
              >
                {loading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Send className="w-5 h-5" />
                )}
              </Button>
            </div>
          </div>
        </Card>

        {/* 元数据面板 */}
        <div className="lg:col-span-1">
          <div className="sticky top-6">
            <Card className="p-4">
              <h3 className="font-semibold mb-3">系统信息</h3>
              <div className="space-y-3">
                <div className="text-sm">
                  <div className="text-muted-foreground mb-1">当前工作流</div>
                  <div className="font-medium">LangGraph 智能问答</div>
                </div>
                <div className="text-sm">
                  <div className="text-muted-foreground mb-1">对话轮数</div>
                  <div className="font-medium">{messages.filter(m => m.role === 'user').length}</div>
                </div>
              </div>

              {/* 元数据展示 */}
              {result?.metadata && (
                <div className="mt-4">
                  <MetadataPanel metadata={result.metadata} />
                </div>
              )}

              {/* 引用来源 */}
              {result?.sources && result.sources.length > 0 && (
                <div className="mt-4">
                  <h4 className="text-sm font-semibold mb-2">引用来源</h4>
                  <div className="space-y-1">
                    {result.sources.map((source: any, idx: number) => (
                      <div key={idx} className="text-xs bg-muted px-2 py-1 rounded">
                        {typeof source === 'string' ? source : (source?.content || source?.title || JSON.stringify(source))}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          </div>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <Card className="p-4 border-destructive bg-destructive/10">
          <p className="text-destructive">{error}</p>
        </Card>
      )}
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  return (
    <div className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
      {message.role === 'assistant' && (
        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
          <Bot className="w-5 h-5 text-primary" />
        </div>
      )}
      <div className={`max-w-[80%] rounded-lg p-3 ${
        message.role === 'user' 
          ? 'bg-primary text-primary-foreground' 
          : 'bg-muted text-foreground'
      }`}>
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        {message.metadata && message.role === 'assistant' && (
          <div className="mt-2 pt-2 border-t">
            <MetadataPanel metadata={message.metadata} />
          </div>
        )}
      </div>
      {message.role === 'user' && (
        <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center shrink-0">
          <User className="w-5 h-5 text-muted-foreground" />
        </div>
      )}
    </div>
  )
}

