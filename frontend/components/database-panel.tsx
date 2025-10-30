"use client"

import type React from "react"

import { useState, useRef, useEffect } from "react"
import { Upload, Database, Check, Trash2, AlertCircle, Loader2, Download } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { useGlobalDocuments } from "@/hooks/use-global-documents"
import { VirtualScroll } from "@/components/ui/virtual-scroll"
import { LazyLoad } from "@/components/ui/lazy-load"
import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"

export function DatabasePanel() {
  const { data, isLoading, isError, isUploading, uploadDocument, deleteDocument, downloadDocument } = useGlobalDocuments()
  const [uploadStatus, setUploadStatus] = useState<"idle" | "success" | "error">("idle")
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set())
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dirInputRef = useRef<HTMLInputElement>(null)

  // 确保事件处理器在客户端正确绑定
  useEffect(() => {
    const input = fileInputRef.current
    if (input) {
      const handleChange = async (e: Event) => {
        const target = e.target as HTMLInputElement
        const files = target.files
        if (!files || files.length === 0) {
          console.log("[v0] No files selected")
          return
        }

        console.log("[v0] Files selected:", files.length, "files")
        try {
          setUploadStatus("idle")
          console.log("[v0] Starting upload...")
          
          // 逐个上传文件
          for (const file of Array.from(files)) {
            console.log("[v0] Uploading file:", file.name, "size:", file.size)
            await uploadDocument(file)
          }
          
          setUploadStatus("success")
          setTimeout(() => setUploadStatus("idle"), 3000)
        } catch (error) {
          console.error("[v0] Document upload error:", error)
          setUploadStatus("error")
          setTimeout(() => setUploadStatus("idle"), 3000)
        }
        // 清空input，避免重复上传同一个文件
        target.value = ''
      }

      input.addEventListener('change', handleChange)
      return () => input.removeEventListener('change', handleChange)
    }
  }, [uploadDocument])


  // 目录选择上传（保留层级）
  useEffect(() => {
    const input = dirInputRef.current
    if (input) {
      const handleChange = async (e: Event) => {
        const target = e.target as HTMLInputElement
        const files = target.files
        if (!files || files.length === 0) {
          console.log("[v0] No directory selected")
          return
        }

        console.log("[v0] Directory selected:", files.length, "files")
        try {
          setUploadStatus("idle")
          console.log("[v0] Starting directory upload...")

          // 逐个上传文件，传递 webkitRelativePath 作为层级信息
          for (const file of Array.from(files)) {
            const anyFile = file as File & { webkitRelativePath?: string }
            const relPath = anyFile.webkitRelativePath || file.name
            console.log("[v0] Uploading file from directory:", relPath, "size:", file.size)
            await uploadDocument(file, relPath)
          }

          setUploadStatus("success")
          setTimeout(() => setUploadStatus("idle"), 3000)
        } catch (error) {
          console.error("[v0] Directory upload error:", error)
          setUploadStatus("error")
          setTimeout(() => setUploadStatus("idle"), 3000)
        }
        // 清空input，避免重复触发
        target.value = ''
      }

      input.addEventListener('change', handleChange)
      return () => input.removeEventListener('change', handleChange)
    }
  }, [uploadDocument])



  const handleDelete = async (id: string) => {
    console.log("[v0] handleGlobalDelete called with id:", id)
    setDeletingIds(prev => new Set(prev).add(id))
    try {
      console.log("[v0] Calling global deleteDocument...")
      await deleteDocument(id)
      console.log("[v0] Global document deleted successfully:", id)
    } catch (error) {
      console.error("[v0] Global document delete error:", error)
      // 可以添加用户友好的错误提示
    } finally {
      setDeletingIds(prev => {
        const newSet = new Set(prev)
        newSet.delete(id)
        return newSet
      })
    }
  }

  const handleDownload = async (id: string, filename: string) => {
    try {
      await downloadDocument(id, filename)
      console.log("[v0] Global document downloaded successfully:", filename)
    } catch (error) {
      console.error("[v0] Global document download error:", error)
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case "completed":
        return "已完成"
      case "processing":
        return "处理中"
      case "vectorizing":
        return "向量化中"
      case "vectorization_failed":
        return "向量化失败"
      case "failed":
        return "处理失败"
      default:
        return status
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-foreground mb-2">全局数据库管理</h2>
        <p className="text-muted-foreground">管理全局共享文档库，这些文档可以被所有工作区的Agent访问，支持多种办公文档格式</p>
        {!isLoading && !isError && (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-sm text-muted-foreground">当前文档数量：</span>
            <span className="text-sm font-medium text-primary">{data.length}</span>
          </div>
        )}
      </div>

      <Card className="p-8 border-dashed border-2 border-border bg-card/50">
        <div className="flex flex-col items-center justify-center gap-4">
          <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
            <Database className="w-8 h-8 text-primary" />
          </div>

          <div className="text-center">
            <h3 className="text-lg font-medium text-foreground mb-1">上传到全局数据库</h3>
            <p className="text-sm text-muted-foreground">支持 PDF, Word, Excel, PowerPoint, TXT, MD, ZIP, RAR 和图片格式（JPG, PNG, GIF 等）</p>
            {!isLoading && !isError && (
              <p className="text-xs text-muted-foreground mt-1">
                当前已有 {data.length} 个全局共享文档
              </p>
            )}
          </div>

          <div className="relative">
            <label htmlFor="database-upload">
              <Button
                className="cursor-pointer"
                disabled={isUploading}
                onClick={() => {
                  console.log("[v0] Upload button clicked")
                  // 点击按钮时触发文件选择
                  const input = document.getElementById('database-upload') as HTMLInputElement
                  if (input) {
                    console.log("[v0] Input element found, triggering click")
                    input.click()
                  } else {
                    console.error("[v0] Input element not found!")
                  }
                }}
              >
                {isUploading ? (
                  <>
                    <Spinner className="w-4 h-4 mr-2" />
                    上传中...
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4 mr-2" />
                    选择文件（可多选）
                  </>
                )}
              </Button>
            </label>
            <input
              ref={fileInputRef}
              id="database-upload"
              type="file"
              className="hidden"
              accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.md,.zip,.rar,.jpg,.jpeg,.png,.gif,.bmp,.tiff"
              multiple
              disabled={isUploading}
            />
          </div>

          <div className="relative">
            <label htmlFor="directory-upload">
              <Button
                className="cursor-pointer"
                variant="outline"
                disabled={isUploading}
                onClick={() => {
                  console.log("[v0] Directory Upload button clicked")
                  const input = document.getElementById('directory-upload') as HTMLInputElement
                  if (input) {
                    input.click()
                  }
                }}
              >
                {isUploading ? (
                  <>
                    <Spinner className="w-4 h-4 mr-2" />
                    上传中...
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4 mr-2" />
                    选择文件夹（保留层级）
                  </>
                )}
              </Button>
            </label>
            <input
              ref={dirInputRef}
              id="directory-upload"
              type="file"
              className="hidden"
              // 目录选择：Chrome/Edge 支持
              // @ts-ignore
              webkitdirectory=""
              // FireFox 尚不支持；会被忽略
              multiple
              disabled={isUploading}
            />
          </div>

          {uploadStatus === "success" && (
            <div className="flex items-center gap-2 text-sm text-accent">
              <Check className="w-4 h-4" />
              上传成功，正在后台处理中...
            </div>
          )}

          {uploadStatus === "error" && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="w-4 h-4" />
              上传失败，请重试
            </div>
          )}

          {isUploading && (
            <div className="flex items-center gap-2 text-sm text-blue-600">
              <Spinner className="w-4 h-4" />
              上传中...
            </div>
          )}
        </div>
      </Card>

      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Spinner className="w-6 h-6 text-primary" />
        </div>
      )}

      {isError && (
        <Card className="p-6 bg-destructive/10 border-destructive">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="w-5 h-5" />
            <p>加载数据库内容失败，请刷新页面重试</p>
          </div>
        </Card>
      )}

      {!isLoading && !isError && data.length > 0 && (
        <div>
          <h3 className="text-lg font-medium text-foreground mb-4">
            全局共享文档 
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              ({data.length} 个文档)
            </span>
          </h3>
          {/* 使用虚拟滚动优化大列表 */}
          <VirtualScroll
            items={data}
            itemHeight={120}
            containerHeight={600}
            className="border border-border rounded-lg"
            renderItem={(item: any, index: number) => (
              <LazyLoad
                key={item.id}
                fallback={
                  <div className="p-4 bg-card border-border animate-pulse">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-muted rounded-lg" />
                      <div className="flex-1 space-y-2">
                        <div className="h-4 bg-muted rounded w-3/4" />
                        <div className="h-3 bg-muted rounded w-1/2" />
                      </div>
                    </div>
                  </div>
                }
              >
                <Card className="p-4 bg-card border-border">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                        <Database className="w-5 h-5 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium text-foreground truncate">
                          {item.original_filename}
                          {item.chunk_count && item.chunk_count > 1 && (
                            <span className="ml-2 text-xs text-muted-foreground bg-gray-100 px-2 py-1 rounded">
                              {item.chunk_count} 个块
                            </span>
                          )}
                        </h4>
                        {/* 显示层级信息 */}
                        {item.hierarchy_path && item.hierarchy_path !== item.original_filename && (
                          <p className="text-xs text-muted-foreground truncate mt-0.5" title={item.hierarchy_path}>
                            📁 {item.hierarchy_path}
                          </p>
                        )}
                        <div className="flex items-center gap-4 text-sm text-muted-foreground mt-1 flex-wrap">
                          <span>{item.file_type?.toUpperCase()} · {(item.file_size / 1024 / 1024).toFixed(2)} MB</span>
                          <span>状态: {getStatusText(item.status)}</span>
                          {item.is_vectorized && (
                            <span className="text-green-600">已向量化 ({item.vector_count} 块)</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDownload(item.id, item.filename)}
                      >
                        <Download className="w-3 h-3 mr-1" />
                        下载
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive"
                        onClick={() => {
                          console.log("[v0] Global delete button clicked for id:", item.id)
                          handleDelete(item.id)
                        }}
                        disabled={deletingIds.has(item.id)}
                      >
                        {deletingIds.has(item.id) ? (
                          <Spinner className="w-4 h-4" />
                        ) : (
                          <Trash2 className="w-4 h-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                </Card>
              </LazyLoad>
            )}
          />
        </div>
      )}

    </div>
  )
}
