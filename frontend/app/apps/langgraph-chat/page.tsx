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
  sources?: string[]
}

export default function LangGraphChatPage() {
  const router = useRouter()
  const STORAGE_KEY_MESSAGES = 'langgraph_chat_messages'
  
  // 从 localStorage 加载消息历史
  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window === 'undefined') return []
    try {
      const saved = localStorage.getItem(STORAGE_KEY_MESSAGES)
      if (saved) {
        const parsed = JSON.parse(saved)
        // 将 timestamp 字符串转换为 Date 对象
        return parsed.map((msg: any) => ({
          ...msg,
          timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date()
        }))
      }
    } catch (e) {
      console.error('[LangGraphChatPage] 加载消息失败:', e)
    }
    return []
  })
  
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  const { sendMessage, loading, result, error, clearResult, clearConversation, threadId } = useLangGraphChat()

  // 保存消息到 localStorage
  useEffect(() => {
    if (messages.length > 0) {
      try {
        localStorage.setItem(STORAGE_KEY_MESSAGES, JSON.stringify(messages))
      } catch (e) {
        console.error('[LangGraphChatPage] 保存消息失败:', e)
      }
    }
  }, [messages])

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (result) {
      // 调试：打印 sources 数据
      console.log('收到结果:', result)
      console.log('sources:', result.sources, '类型:', typeof result.sources, '长度:', result.sources?.length)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: result.answer,
        timestamp: new Date(),
        metadata: result.metadata,
        sources: result.sources || []
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
    // 清除 localStorage
    try {
      localStorage.removeItem(STORAGE_KEY_MESSAGES)
    } catch (e) {
      console.error('[LangGraphChatPage] 清除消息缓存失败:', e)
    }
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
        <Card className="lg:col-span-2 flex flex-col h-[800px] overflow-hidden">
          <div className="p-4 border-b flex items-center justify-between shrink-0">
            <div>
              <h3 className="font-semibold">智能对话</h3>
              <p className="text-sm text-muted-foreground">
                支持简单问答、复杂推理和多跳查询
              </p>
            </div>
            {messages.length > 0 && (
              <div className="flex gap-2">
                {threadId && (
                  <div className="text-xs text-muted-foreground flex items-center">
                    对话ID: {threadId.slice(0, 8)}...
                  </div>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    clearMessages()
                    clearConversation()
                  }}
                >
                  <RefreshCw className="w-4 h-4 mr-2" />
                  清空对话
                </Button>
              </div>
            )}
          </div>

          <ScrollArea className="flex-1 p-4 min-h-0">
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

          <div className="p-4 border-t shrink-0">
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
                  <h4 className="text-sm font-semibold mb-2 text-foreground">引用来源</h4>
                  <div className="space-y-1">
                    {result.sources.map((source: any, idx: number) => {
                      const filename = typeof source === 'string' 
                        ? source 
                        : (source?.filename || source?.original_filename || source?.content || source?.title || '未知文件')
                      return (
                        <div 
                          key={idx} 
                          className="text-xs bg-muted px-2 py-1 rounded text-foreground font-medium flex items-center gap-1"
                        >
                          <span className="text-muted-foreground">📄</span>
                          <span className="truncate" title={filename}>{filename}</span>
                        </div>
                      )
                    })}
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
        <div className="max-h-[500px] overflow-y-auto">
          <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
        </div>
        {message.sources && Array.isArray(message.sources) && message.sources.length > 0 && message.role === 'assistant' && (
          <div className="mt-2 pt-2 border-t border-border/50">
            <div className="text-xs text-muted-foreground mb-1.5 font-semibold">📚 引用来源 ({message.sources.length})</div>
            <div className="flex flex-wrap gap-1.5">
              {message.sources
                .filter((source: any) => {
                  // 过滤空字符串和无效值
                  if (!source) return false
                  const str = typeof source === 'string' ? source : String(source)
                  return str.trim().length > 0
                })
                .map((source: any, idx: number) => {
                  const filename = typeof source === 'string' 
                    ? source.trim()
                    : (source?.filename || source?.original_filename || source?.file_name || source?.title || source?.doc_id || source?.document_id || source?.name || source?.document_name || '未知文件')
                  // 确保不是空字符串
                  const displayName = filename && filename.trim() ? filename.trim() : `来源 ${idx + 1}`
                  console.log(`[MessageBubble] 显示来源 ${idx}:`, { source, filename, displayName, type: typeof source })
                  return (
                    <span
                      key={idx}
                      className="text-xs bg-primary/10 text-primary px-2.5 py-1 rounded-md font-medium break-all hover:bg-primary/20 transition-colors cursor-pointer"
                      title={`点击查看: ${displayName}`}
                    >
                      📄 {displayName}
                    </span>
                  )
                })}
            </div>
          </div>
        )}
        {message.role === 'assistant' && (!message.sources || !Array.isArray(message.sources) || message.sources.length === 0) && (
          <div className="mt-2 pt-2 border-t border-border/50">
            <div className="text-xs text-muted-foreground italic">
              暂无引用来源
              {(() => {
                console.log('[MessageBubble] 无引用来源:', { hasSources: !!message.sources, isArray: Array.isArray(message.sources), length: message.sources?.length })
                return null
              })()}
            </div>
          </div>
        )}
        {message.metadata && message.role === 'assistant' && (
          <div className="mt-2 pt-2 border-t border-border/50">
            <div className="bg-background/50 rounded-lg -m-1 p-2">
              <MetadataPanel metadata={message.metadata} />
            </div>
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

