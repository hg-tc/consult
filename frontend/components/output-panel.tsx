"use client"

import { useState, useEffect, useRef } from "react"
import { Send, Download, Play, MessageSquare, FileText, AlertCircle, FileIcon, Globe, Globe2 } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Loader2 } from "lucide-react"
import { useAgent } from "@/hooks/use-agent"
import { useWorkspaces } from "@/hooks/use-workspaces"
import { useGlobalSearch } from "@/hooks/use-global-search"
import { ReferenceList } from "@/components/reference-card"
import { DocumentViewerModal } from "@/components/document-viewer"
import { WorkflowProgress } from "@/components/workflow-progress"

interface Message {
  id: string
  role: "user" | "agent"
  content: string
  timestamp: string
  metadata?: {
    references?: Array<{
      document_id: string
      document_name: string
      chunk_id: string
      content: string
      page_number?: number
      similarity: number
      rank: number
      highlight?: string
      access_url: string
    }>
    file_generated?: boolean
    file_info?: {
      file_id: string
      filename: string
      file_type: string
      file_size: number
      download_url: string
    }
    intent_detected?: boolean
    intent_type?: string
    pending_confirmation?: boolean
    suggested_params?: any
    workflow_type?: string
    workflow_details?: any
    quality_score?: number
    [key: string]: any
  }
}

interface WorkflowStep {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'error'
  description?: string
  duration?: number
  details?: string
}

interface WorkflowProgress {
  workflowType: string
  currentStep: string
  steps: WorkflowStep[]
  progress: number
  startTime: number
  estimatedTime?: number
  sourceStats: {
    documents: number
    webResults: number
    conversationTurns: number
  }
  qualityScore?: number
  complexityAnalysis?: {
    level: 'simple' | 'medium' | 'complex'
    factors: string[]
  }
}

interface GeneratedFile {
  file_id: string
  filename: string
  file_type: 'word' | 'excel' | 'ppt'
  file_size: number
  created_at: string
  download_url: string
  title?: string
  source_query?: string
}

export function OutputPanel() {
  // 从 localStorage 加载工作区选择
  const [selectedWorkspace, setSelectedWorkspace] = useState<string | null>(() => {
    if (typeof window === 'undefined') return "1"
    return localStorage.getItem('output_panel_selected_workspace') || "1"
  })
  
  // 从 localStorage 加载搜索模式
  const [searchMode, setSearchMode] = useState<"workspace" | "global">(() => {
    if (typeof window === 'undefined') return "workspace"
    return (localStorage.getItem('output_panel_search_mode') as "workspace" | "global") || "workspace"
  })
  
  const { workspaces } = useWorkspaces()
  
  // 保存工作区选择
  useEffect(() => {
    if (selectedWorkspace) {
      localStorage.setItem('output_panel_selected_workspace', selectedWorkspace)
    }
  }, [selectedWorkspace])
  
  // 保存搜索模式
  useEffect(() => {
    localStorage.setItem('output_panel_search_mode', searchMode)
  }, [searchMode])

  const { messages, files, actions, isLoading, isError, isSending, sendMessage, downloadFile, executeAction, clearHistory } =
    useAgent(selectedWorkspace)
  
  const { searchGlobal, searchResults, isSearching, error: globalError, clearResults } = useGlobalSearch()

  const [input, setInput] = useState("")
  const [generatedFiles, setGeneratedFiles] = useState<GeneratedFile[]>([])
  const [enableWebSearch, setEnableWebSearch] = useState(false)  // 新增：联网搜索开关
  const [workflowProgress, setWorkflowProgress] = useState<WorkflowProgress | null>(null)
  const [showWorkflowProgress, setShowWorkflowProgress] = useState(false)
  const [viewerState, setViewerState] = useState<{
    isOpen: boolean
    documentId?: string
    highlight?: string
  }>({ isOpen: false })
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages.length])

  // 监听消息变化，更新工作流进度
  useEffect(() => {
    if (!showWorkflowProgress || !workflowProgress) return

    const lastMessage = messages[messages.length - 1]
    if (!lastMessage || lastMessage.role !== 'agent') return

    const metadata = lastMessage.metadata
    if (!metadata) return

    // 更新工作流类型
    if (metadata.workflow_type) {
      setWorkflowProgress(prev => prev ? {
        ...prev,
        workflowType: metadata.workflow_type
      } : null)
    }

    // 更新质量评分
    if (metadata.quality_score !== undefined) {
      setWorkflowProgress(prev => prev ? {
        ...prev,
        qualityScore: metadata.quality_score
      } : null)
    }

    // 更新复杂度分析
    if (metadata.workflow_details?.complexity_analysis) {
      setWorkflowProgress(prev => prev ? {
        ...prev,
        complexityAnalysis: metadata.workflow_details.complexity_analysis
      } : null)
    }

    // 更新来源统计
    if (metadata.references) {
      setWorkflowProgress(prev => prev ? {
        ...prev,
        sourceStats: {
          ...prev.sourceStats,
          documents: metadata.references?.length || 0
        }
      } : null)
    }

    // 如果消息完成，更新进度
    // 检查条件：
    // 1. intent_detected (复杂工作流)
    // 2. file_generated (文件生成)
    // 3. answer存在且intent_detected为false (普通问答)
    const isMessageComplete = metadata.intent_detected || 
                               metadata.file_generated || 
                               (metadata.answer && metadata.intent_detected === false)
    
    if (isMessageComplete) {
      setWorkflowProgress(prev => {
        if (!prev) return null
        
        const updatedSteps = prev.steps.map(step => {
          if (step.status === 'running') {
            return { ...step, status: 'completed' as const }
          }
          return step
        })

        const completedSteps = updatedSteps.filter(s => s.status === 'completed').length
        const progress = (completedSteps / updatedSteps.length) * 100

        return {
          ...prev,
          steps: updatedSteps,
          progress: Math.min(progress, 100),
          currentStep: 'completed'
        }
      })

      // 3秒后隐藏进度条
      setTimeout(() => {
        setShowWorkflowProgress(false)
        setWorkflowProgress(null)
      }, 3000)
    }
  }, [messages, showWorkflowProgress])

  // 处理Agent响应中的文件生成
  useEffect(() => {
    if (messages.length === 0) return
    
    const latestMessage = messages[messages.length - 1]
    if (latestMessage?.metadata?.file_generated && latestMessage.metadata.file_info) {
      const fileInfo = latestMessage.metadata.file_info
      
      // 检查是否已经存在相同的文件，避免重复添加
      setGeneratedFiles(prev => {
        const exists = prev.some(file => file.file_id === fileInfo.file_id)
        if (exists) {
          return prev
        }
        
        const newFile: GeneratedFile = {
          file_id: fileInfo.file_id,
          filename: fileInfo.filename,
          file_type: fileInfo.file_type as 'word' | 'excel' | 'ppt',
          file_size: fileInfo.file_size,
          created_at: new Date().toISOString(),
          download_url: fileInfo.download_url,
          title: latestMessage.content.split('：')[1] || fileInfo.filename,
          source_query: input
        }
        
        return [newFile, ...prev]
      })
    }
  }, [messages.length, messages[messages.length - 1]?.metadata?.file_generated])

  const handleDownloadFile = async (file: GeneratedFile) => {
    try {
      const response = await fetch(file.download_url)
      if (!response.ok) throw new Error('下载失败')
      
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = file.filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('文件下载失败:', error)
      alert('文件下载失败，请重试')
    }
  }

  const getFileIcon = (fileType: string) => {
    switch (fileType) {
      case 'word':
        return <FileText className="w-4 h-4 text-blue-600" />
      case 'excel':
        return <FileIcon className="w-4 h-4 text-green-600" />
      case 'ppt':
        return <FileIcon className="w-4 h-4 text-orange-600" />
      default:
        return <FileIcon className="w-4 h-4 text-gray-600" />
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const handleSendMessage = async () => {
    if (!input.trim()) return

    try {
      if (searchMode === "global") {
        // 全局搜索模式
        await searchGlobal(input, selectedWorkspace || undefined)
      } else {
        // 工作区模式 - 传递联网搜索参数
        if (!selectedWorkspace) return
        
        // 初始化工作流进度
        const initialProgress: WorkflowProgress = {
          workflowType: 'simple',
          currentStep: 'intent_recognition',
          steps: [
            { id: 'intent_recognition', name: '意图识别', status: 'running', description: '分析用户请求意图' },
            { id: 'information_gathering', name: '信息收集', status: 'pending', description: '检索相关文档和网络信息' },
            { id: 'content_generation', name: '内容生成', status: 'pending', description: '生成文档内容' },
            { id: 'quality_review', name: '质量审核', status: 'pending', description: '评估和优化内容质量' },
            { id: 'formatting', name: '格式化输出', status: 'pending', description: '生成最终文档' }
          ],
          progress: 0,
          startTime: Date.now(),
          sourceStats: {
            documents: 0,
            webResults: 0,
            conversationTurns: messages.length
          }
        }
        
        setWorkflowProgress(initialProgress)
        setShowWorkflowProgress(true)
        
        await sendMessage(input)
      }
      setInput("")
    } catch (error) {
      console.error("[v0] Send message error:", error)
      setShowWorkflowProgress(false)
    }
  }

  const handleDownload = async (fileId: string, filename: string) => {
    try {
      await downloadFile(fileId, filename)
    } catch (error) {
      console.error("[v0] Download error:", error)
    }
  }

  const handlePreviewReference = (reference: any) => {
    setViewerState({
      isOpen: true,
      documentId: reference.document_id,
      highlight: reference.highlight
    })
  }
  
  const handleCloseViewer = () => {
    setViewerState({ isOpen: false })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-foreground mb-2">输出与交互</h2>
          <p className="text-muted-foreground">与Agent对话交互或下载处理结果</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={searchMode} onValueChange={(value: "workspace" | "global") => setSearchMode(value)}>
            <SelectTrigger className="w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="workspace">工作区模式</SelectItem>
              <SelectItem value="global">全局搜索</SelectItem>
            </SelectContent>
          </Select>
          <Select value={selectedWorkspace || ""} onValueChange={setSelectedWorkspace}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="选择工作区" />
            </SelectTrigger>
            <SelectContent>
              {workspaces.map((workspace: any) => (
                <SelectItem key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {!selectedWorkspace && searchMode === "workspace" && (
        <Card className="p-8 bg-card/50 border-dashed border-2">
          <div className="text-center text-muted-foreground">
            <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>请先选择一个工作区以开始交互</p>
          </div>
        </Card>
      )}

      {(selectedWorkspace || searchMode === "global") && (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Chat Interface */}
          <Card className="p-6 bg-card border-border flex flex-col h-[600px]">
            <div className="flex items-center gap-2 mb-4 pb-4 border-b border-border">
              <MessageSquare className="w-5 h-5 text-primary" />
              <h3 className="font-medium text-foreground">
                {searchMode === "global" ? "全局搜索" : "Agent对话"}
              </h3>
              {searchMode === "global" && (
                <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded-full">
                  全局模式
                </span>
              )}
              {searchMode === "global" && searchResults && (
                <Button 
                  size="sm" 
                  variant="outline" 
                  onClick={clearResults}
                  className="ml-auto"
                >
                  清除结果
                </Button>
              )}
            </div>

            {isLoading && (
              <div className="flex-1 flex items-center justify-center">
                <Loader2 className="w-6 h-6 text-primary animate-spin" />
              </div>
            )}

            {isSearching && (
              <div className="flex-1 flex items-center justify-center">
                <div className="flex items-center gap-2 text-primary">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <p>全局搜索中...</p>
                </div>
              </div>
            )}

            {globalError && (
              <div className="flex-1 flex items-center justify-center">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertCircle className="w-5 h-5" />
                  <p>全局搜索失败: {globalError}</p>
                </div>
              </div>
            )}

            {!isLoading && !isError && !isSearching && !globalError && (
              <>
                {/* 工作流进度展示 */}
                {searchMode === "workspace" && (
                  <WorkflowProgress 
                    progress={workflowProgress} 
                    isVisible={showWorkflowProgress} 
                  />
                )}
                
                <div className="flex-1 overflow-y-auto space-y-4 mb-4">
                  {/* 显示全局搜索结果 */}
                  {searchMode === "global" && searchResults && (
                    <div className="space-y-4">
                      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <MessageSquare className="w-4 h-4 text-blue-600" />
                          <span className="text-sm font-medium text-blue-800">全局搜索结果</span>
                        </div>
                        <p className="text-sm text-blue-700 mb-3">{searchResults.answer}</p>
                        
                        {searchResults.references && searchResults.references.length > 0 && (
                          <div className="mt-3 pt-3 border-t border-blue-200">
                            <ReferenceList
                              references={searchResults.references.map((ref, index) => ({
                                document_id: ref.metadata.file_path,
                                document_name: ref.metadata.original_filename,
                                chunk_id: `global_${index}`,
                                content: ref.content_preview,
                                similarity: ref.similarity,
                                rank: index + 1,
                                access_url: `/api/global/documents/${ref.metadata.file_path}`
                              }))}
                              onPreview={handlePreviewReference}
                              maxDisplay={1}
                            />
                          </div>
                        )}
                        
                        <div className="mt-2 text-xs text-blue-600">
                          置信度: {(searchResults.confidence * 100).toFixed(1)}% | 
                          文档数: {searchResults.metadata.document_count}
                        </div>
                      </div>
                    </div>
                  )}
                  
                  {/* 显示工作区消息 */}
                  {searchMode === "workspace" && messages.map((message: Message) => (
                    <div
                      key={message.id}
                      className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[80%] rounded-lg p-3 ${
                          message.role === "user"
                            ? "bg-primary text-primary-foreground"
                            : "bg-secondary text-secondary-foreground"
                        }`}
                      >
                        <p className="text-sm leading-relaxed">{message.content}</p>
                        <span className="text-xs opacity-70 mt-1 block">{message.timestamp}</span>
                        
                        {/* 显示引用 */}
                        {message.role === "agent" && message.metadata?.references && (
                          <div className="mt-3 pt-3 border-t border-border/20">
                            <ReferenceList
                              references={message.metadata.references.map((ref: any) => ({
                                document_id: ref.metadata?.file_path || ref.chunk_id,
                                document_name: ref.metadata?.original_filename || "未知文档",
                                chunk_id: ref.chunk_id || ref.metadata?.file_path,
                                content: ref.content_preview || ref.content || "",
                                page_number: ref.metadata?.page_number,
                                similarity: ref.similarity || 0,
                                rank: ref.rank || 1,
                                highlight: ref.highlight,
                                source_type: ref.source_type,
                                workspace_id: ref.workspace_id,
                                access_url: ref.source_type === "global" 
                                  ? `/api/global/documents/${ref.chunk_id}/download`
                                  : `/api/workspaces/${ref.workspace_id}/documents/${ref.chunk_id}/download`
                              }))}
                              onPreview={handlePreviewReference}
                              maxDisplay={1}
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>

                {/* 生成文件展示区域 */}
                {generatedFiles.length > 0 && (
                  <Card className="p-4 bg-muted/50 mb-4">
                    <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      生成的文件
                    </h3>
                    
                    <div className="space-y-2">
                      {generatedFiles.map(file => (
                        <div key={file.file_id} className="flex items-center justify-between p-2 bg-background rounded">
                          <div className="flex items-center gap-2">
                            {getFileIcon(file.file_type)}
                            <div>
                              <p className="text-sm font-medium">{file.filename}</p>
                              <p className="text-xs text-muted-foreground">
                                {formatFileSize(file.file_size)} • {new Date(file.created_at).toLocaleDateString()}
                              </p>
                            </div>
                          </div>
                          
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleDownloadFile(file)}
                          >
                            <Download className="w-4 h-4" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}

                {/* 历史管理按钮（仅工作区模式） */}
                {searchMode === "workspace" && messages.length > 0 && (
                  <div className="flex items-center justify-between mb-2 px-1">
                    <span className="text-xs text-muted-foreground">
                      {messages.length} 条对话
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (confirm('确定要清除当前工作区的对话历史吗？')) {
                          clearHistory()
                        }
                      }}
                      className="h-7 text-xs"
                    >
                      清除历史
                    </Button>
                  </div>
                )}

                {/* 联网搜索开关 */}
                {searchMode === "workspace" && (
                  <div className="flex items-center gap-2 mb-3 p-3 bg-secondary/30 rounded-lg border border-border">
                    <Globe className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">联网搜索</span>
                    <Switch
                      checked={enableWebSearch}
                      onCheckedChange={setEnableWebSearch}
                      className="ml-auto"
                    />
                    {enableWebSearch && (
                      <span className="text-xs text-green-600 flex items-center gap-1">
                        <Globe2 className="w-3 h-3" />
                        已启用
                      </span>
                    )}
                  </div>
                )}

                <div className="flex gap-2">
                  <Textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSendMessage())}
                    placeholder={searchMode === "global" ? "输入问题搜索全局文档库..." : "输入消息与Agent交互..."}
                    className="resize-none"
                    rows={2}
                    disabled={isSending || isSearching}
                  />
                  <Button 
                    onClick={handleSendMessage} 
                    size="icon" 
                    className="h-auto" 
                    disabled={isSending || isSearching}
                  >
                    {(isSending || isSearching) ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  </Button>
                </div>
              </>
            )}
          </Card>

          {/* Output Files & Actions */}
          <div className="space-y-6">
            <Card className="p-6 bg-card border-border">
              <div className="flex items-center gap-2 mb-4">
                <FileText className="w-5 h-5 text-accent" />
                <h3 className="font-medium text-foreground">可下载文件</h3>
              </div>

              {files.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">暂无可下载文件</p>
              ) : (
                <div className="space-y-3">
                  {files.map((file: any) => (
                    <div
                      key={file.id}
                      className="flex items-center justify-between p-3 rounded-lg bg-secondary/50 border border-border"
                    >
                      <div>
                        <p className="font-medium text-foreground text-sm">{file.name}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {file.size} · {file.date}
                        </p>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => handleDownload(file.id, file.name)}>
                        <Download className="w-4 h-4 mr-2" />
                        下载
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card className="p-6 bg-card border-border">
              <div className="flex items-center gap-2 mb-4">
                <Play className="w-5 h-5 text-primary" />
                <h3 className="font-medium text-foreground">快速操作</h3>
              </div>

              {actions.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">暂无可用操作</p>
              ) : (
                <div className="grid gap-3">
                  {actions.map((action: any) => (
                    <Button
                      key={action.id}
                      className="w-full justify-start bg-transparent"
                      variant="outline"
                      onClick={() => executeAction(action.id)}
                    >
                      <Play className="w-4 h-4 mr-2" />
                      {action.name}
                    </Button>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </div>
      )}
      
      {/* 文档查看器模态框 */}
      <DocumentViewerModal
        isOpen={viewerState.isOpen}
        documentId={viewerState.documentId}
        highlight={viewerState.highlight}
        onClose={handleCloseViewer}
      />
    </div>
  )
}
