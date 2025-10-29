"use client"

import { useState, useRef, useEffect } from 'react'
import { useLangGraphChat } from '@/hooks/use-langgraph-chat'
import { MetadataPanel } from './metadata-panel'
import { WorkflowSelector, WorkflowType } from './workflow-selector'
import { Card } from './ui/card'
import { Button } from './ui/button'
import { Textarea } from './ui/textarea'
import { ScrollArea } from './ui/scroll-area'
import { Send, Loader2, User, Bot, RefreshCw, FileText, ChevronDown, ChevronUp } from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  metadata?: any
}

export function LangGraphChatPanel() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [workflow, setWorkflow] = useState<WorkflowType>('langgraph')
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
      <div>
        <h2 className="text-2xl font-bold mb-4">智能问答</h2>
        <p className="text-gray-600 mb-6">
          基于 LangGraph 的智能问答系统，支持自适应路由、多跳推理和质量保证
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* 对话区域 */}
        <Card className="lg:col-span-2 flex flex-col h-[600px]">
          <div className="p-4 border-b flex items-center justify-between">
            <div>
              <h3 className="font-semibold">智能对话</h3>
              <p className="text-sm text-gray-500">
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
                <div className="text-center py-12 text-gray-500">
                  <Bot className="w-12 h-12 mx-auto mb-4 text-gray-400" />
                  <p>开始一个新的对话</p>
                  <p className="text-sm mt-2">支持简单问答、复杂推理等多种场景</p>
                </div>
              ) : (
                messages.map((msg, idx) => (
                  <MessageBubble key={idx} message={msg} />
                ))
              )}
              {loading && (
                <div className="flex items-center gap-2 text-gray-500">
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
                  <div className="text-gray-500 mb-1">当前工作流</div>
                  <div className="font-medium">LangGraph 智能问答</div>
                </div>
                <div className="text-sm">
                  <div className="text-gray-500 mb-1">对话轮数</div>
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
                  <h4 className="text-sm font-semibold mb-2">引用来源 ({result.sources.length})</h4>
                  <div className="space-y-2 max-h-[400px] overflow-y-auto">
                    {result.sources.map((source, idx) => (
                      <SourceItem key={idx} source={source} />
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
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}
    </div>
  )
}

function SourceItem({ source }: { source: any }) {
  const [isExpanded, setIsExpanded] = useState<boolean>(false)

  // 兼容新旧格式
  const filename = typeof source === 'string' ? source : source.filename || `文档${source.index || ''}`
  const content = source.content || ''
  const fullContent = source.full_content || content
  const score = source.score || 0
  const isObject = typeof source === 'object'

  return (
    <div className="text-xs bg-gray-100 rounded border border-gray-200">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-2 py-2 flex items-center justify-between hover:bg-gray-200 transition-colors"
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <FileText className="w-3 h-3 shrink-0 text-black" />
          <span className="font-medium text-black truncate">{filename}</span>
          {isObject && score > 0 && (
            <span className="text-black shrink-0">({score})</span>
          )}
        </div>
        {isObject && fullContent && (
          isExpanded ? (
            <ChevronUp className="w-3 h-3 shrink-0" />
          ) : (
            <ChevronDown className="w-3 h-3 shrink-0" />
          )
        )}
      </button>
      
      {isExpanded && isObject && fullContent && (
        <div className="px-2 pb-2 pt-1 border-t border-gray-300">
          <div className="text-black whitespace-pre-wrap bg-white p-2 rounded text-xs">
            {fullContent}
          </div>
        </div>
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
          ? 'bg-primary text-white' 
          : 'bg-gray-100 text-gray-900'
      }`}>
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        {message.metadata && message.role === 'assistant' && (
          <div className="mt-2 pt-2 border-t border-gray-300">
            <MetadataPanel metadata={message.metadata} />
          </div>
        )}
      </div>
      {message.role === 'user' && (
        <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center shrink-0">
          <User className="w-5 h-5 text-gray-600" />
        </div>
      )}
    </div>
  )
}

