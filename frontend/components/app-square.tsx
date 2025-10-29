"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { FileText, Brain, Search, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface AppConfig {
  id: string
  name: string
  description: string
  icon: string
  route: string
  status: string
  version: string
  category?: string
}

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  FileText,
  Brain,
}

export function AppSquare() {
  const router = useRouter()
  const [apps, setApps] = useState<AppConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  useEffect(() => {
    // 加载应用配置
    const loadApps = async () => {
      try {
        // 尝试从 public 目录加载配置
        const response = await fetch("/apps/apps.config.json")
        if (response.ok) {
          const data = await response.json()
          setApps(data.apps || [])
        } else {
          // 如果文件不存在，使用默认配置
          throw new Error("Config file not found")
        }
      } catch (error) {
        // 如果加载失败，使用默认配置
        console.warn("加载应用配置失败，使用默认配置:", error)
        const defaultApps: AppConfig[] = [
          {
            id: "document-generator",
            name: "文档生成",
            description: "基于 DeepResearch 技术的长文档生成应用",
            icon: "FileText",
            route: "/apps/document-generator",
            status: "active",
            version: "1.0.0",
            category: "内容生成"
          },
          {
            id: "langgraph-chat",
            name: "智能问答",
            description: "基于 LangGraph 的智能 RAG 问答系统",
            icon: "Brain",
            route: "/apps/langgraph-chat",
            status: "active",
            version: "1.0.0",
            category: "智能对话"
          }
        ]
        setApps(defaultApps)
      } finally {
        setLoading(false)
      }
    }

    loadApps()
  }, [])

  // 过滤应用
  const filteredApps = apps.filter(app => {
    const matchesSearch = app.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         app.description.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesCategory = !selectedCategory || app.category === selectedCategory
    return matchesSearch && matchesCategory && app.status === "active"
  })

  // 获取所有分类
  const categories = Array.from(new Set(apps.map(app => app.category).filter(Boolean)))

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 搜索和筛选 */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
          <Input
            placeholder="搜索应用..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        {categories.length > 0 && (
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => setSelectedCategory(null)}
              className={cn(
                "px-4 py-2 rounded-md text-sm transition-colors",
                !selectedCategory
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
              )}
            >
              全部
            </button>
            {categories.map((category) => (
              <button
                key={category as string}
                onClick={() => setSelectedCategory((category as string) || null)}
                className={cn(
                  "px-4 py-2 rounded-md text-sm transition-colors",
                  selectedCategory === category
                    ? "bg-primary text-primary-foreground"
                    : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                )}
              >
                {category as string}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 应用卡片网格 */}
      {filteredApps.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <p>没有找到匹配的应用</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredApps.map((app) => {
            const Icon = iconMap[app.icon] || FileText
            return (
              <Card
                key={app.id}
                className="p-6 cursor-pointer hover:shadow-lg transition-shadow border-border hover:border-primary/50"
                onClick={() => router.push(app.route)}
              >
                <div className="space-y-4">
                  <div className="flex items-start justify-between">
                    <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center">
                      <Icon className="w-6 h-6 text-primary" />
                    </div>
                    <Badge variant={app.status === "active" ? "default" : "secondary"}>
                      {app.status === "active" ? "可用" : "维护中"}
                    </Badge>
                  </div>
                  
                  <div>
                    <h3 className="text-lg font-semibold mb-2">{app.name}</h3>
                    <p className="text-sm text-foreground line-clamp-2">
                      {app.description}
                    </p>
                  </div>
                  
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    {app.category && (
                      <span className="bg-secondary px-2 py-1 rounded">
                        {app.category}
                      </span>
                    )}
                    <span>v{app.version}</span>
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}

