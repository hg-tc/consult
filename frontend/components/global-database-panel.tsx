"use client"

import { useState, useEffect } from "react"
import { Upload, Database, Globe, Users, Settings, Search } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useGlobalDocuments } from "@/hooks/use-global-documents"

interface GlobalDocument {
  id: string
  filename: string
  original_filename: string
  file_size: number
  status: string
  created_at: string
}

interface Workspace {
  id: string
  name: string
  description: string
  status: string
  document_count: number
  created_at: string
}

export function GlobalDatabasePanel() {
  const [activeTab, setActiveTab] = useState("documents")
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>("")
  const [searchQuery, setSearchQuery] = useState("")
  
  // 使用统一的全局文档Hook
  const { data, isLoading, isError, isUploading, uploadDocument, deleteDocument, downloadDocument } = useGlobalDocuments()
  const documents = data?.documents || []

  // 加载数据
  useEffect(() => {
    loadWorkspaces()
  }, [])

  const loadWorkspaces = async () => {
    try {
      const response = await fetch('/api/global/workspaces')
      const data = await response.json()
      setWorkspaces(data.workspaces || [])
      if (data.workspaces?.length > 0) {
        setSelectedWorkspace(data.workspaces[0].id)
      }
    } catch (error) {
      console.error('加载工作区失败:', error)
    }
  }

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    try {
      // 使用统一的uploadDocument函数
      const result = await uploadDocument(file)
      console.log('上传成功:', result)
      
      // 显示成功消息
      alert(`文件 ${file.name} 上传成功！正在后台处理中，请到"处理状态"页面查看进度。`)
    } catch (error) {
      console.error('上传失败:', error)
      alert('上传失败，请重试')
    }
  }

  const handleGlobalSearch = async () => {
    if (!searchQuery.trim()) return

    try {
      const response = await fetch('/api/global/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          query: searchQuery,
          workspace_id: selectedWorkspace || null,
          top_k: 5
        })
      })

      if (response.ok) {
        const result = await response.json()
        console.log('搜索结果:', result)
        // 这里可以显示搜索结果
      }
    } catch (error) {
      console.error('搜索失败:', error)
    }
  }

  const handleGlobalChat = async () => {
    if (!searchQuery.trim()) return

    try {
      const response = await fetch('/api/global/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          question: searchQuery,
          workspace_id: selectedWorkspace || null,
          top_k: 5
        })
      })

      if (response.ok) {
        const result = await response.json()
        console.log('问答结果:', result)
        // 这里可以显示问答结果
      }
    } catch (error) {
      console.error('问答失败:', error)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-foreground mb-2">全局数据库管理</h2>
          <p className="text-muted-foreground">管理公共文档库和工作区</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={selectedWorkspace} onValueChange={setSelectedWorkspace}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="选择工作区" />
            </SelectTrigger>
            <SelectContent>
              {workspaces.map((workspace) => (
                <SelectItem key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="documents" className="flex items-center gap-2">
            <Database className="w-4 h-4" />
            文档库
          </TabsTrigger>
          <TabsTrigger value="workspaces" className="flex items-center gap-2">
            <Users className="w-4 h-4" />
            工作区
          </TabsTrigger>
          <TabsTrigger value="search" className="flex items-center gap-2">
            <Search className="w-4 h-4" />
            搜索
          </TabsTrigger>
          <TabsTrigger value="settings" className="flex items-center gap-2">
            <Settings className="w-4 h-4" />
            设置
          </TabsTrigger>
        </TabsList>

        <TabsContent value="documents" className="space-y-4">
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">全局文档库</h3>
              <div className="flex items-center gap-2">
                <input
                  type="file"
                  id="file-upload"
                  className="hidden"
                  accept=".pdf,.docx,.doc,.txt,.md,.zip,.rar"
                  onChange={handleFileUpload}
                />
                <Button asChild>
                  <label htmlFor="file-upload" className="cursor-pointer">
                    <Upload className="w-4 h-4 mr-2" />
                    上传文档
                  </label>
                </Button>
              </div>
            </div>

            {isUploading && (
              <div className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-muted-foreground">上传中...</span>
                </div>
                <div className="w-full bg-secondary rounded-full h-2">
                  <div className="bg-primary h-2 rounded-full animate-pulse" />
                </div>
              </div>
            )}

            <div className="space-y-2">
              {documents.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Globe className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>暂无全局文档</p>
                  <p className="text-sm">上传文档到全局文档库，所有工作区都可以访问</p>
                </div>
              ) : (
                documents.map((doc) => (
                  <div key={doc.id} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="flex items-center gap-3">
                      <Database className="w-5 h-5 text-muted-foreground" />
                      <div>
                        <p className="font-medium">{doc.original_filename}</p>
                        <p className="text-sm text-muted-foreground">
                          {(doc.file_size / 1024 / 1024).toFixed(2)} MB • {doc.status}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {new Date(doc.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="workspaces" className="space-y-4">
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">工作区管理</h3>
              <Button>
                <Users className="w-4 h-4 mr-2" />
                创建工作区
              </Button>
            </div>

            <div className="space-y-2">
              {workspaces.map((workspace) => (
                <div key={workspace.id} className="flex items-center justify-between p-3 border rounded-lg">
                  <div className="flex items-center gap-3">
                    <Users className="w-5 h-5 text-muted-foreground" />
                    <div>
                      <p className="font-medium">{workspace.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {workspace.description} • {workspace.document_count} 个文档
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-1 text-xs rounded-full ${
                      workspace.status === 'active' 
                        ? 'bg-green-100 text-green-800' 
                        : 'bg-gray-100 text-gray-800'
                    }`}>
                      {workspace.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="search" className="space-y-4">
          <Card className="p-6">
            <h3 className="text-lg font-semibold mb-4">全局搜索</h3>
            
            <div className="space-y-4">
              <div className="flex gap-2">
                <Input
                  placeholder="搜索全局文档库..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleGlobalSearch()}
                />
                <Button onClick={handleGlobalSearch}>
                  <Search className="w-4 h-4 mr-2" />
                  搜索
                </Button>
              </div>

              <div className="flex gap-2">
                <Input
                  placeholder="向AI提问..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleGlobalChat()}
                />
                <Button onClick={handleGlobalChat}>
                  <Globe className="w-4 h-4 mr-2" />
                  问答
                </Button>
              </div>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="settings" className="space-y-4">
          <Card className="p-6">
            <h3 className="text-lg font-semibold mb-4">全局设置</h3>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium">默认工作区</label>
                <Select value={selectedWorkspace} onValueChange={setSelectedWorkspace}>
                  <SelectTrigger className="w-full mt-1">
                    <SelectValue placeholder="选择默认工作区" />
                  </SelectTrigger>
                  <SelectContent>
                    {workspaces.map((workspace) => (
                      <SelectItem key={workspace.id} value={workspace.id}>
                        {workspace.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
