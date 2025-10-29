"use client"

import { useParams, useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { Loader2, ArrowLeft } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"

// 动态导入应用组件
const appComponents: Record<string, React.ComponentType> = {
  "document-generator": require("@/app/apps/document-generator/page").default,
  "langgraph-chat": require("@/app/apps/langgraph-chat/page").default,
}

interface AppConfig {
  id: string
  name: string
  description: string
  route: string
  status: string
}

export default function AppPage() {
  const params = useParams()
  const router = useRouter()
  const appId = params["app-id"] as string
  const [appConfig, setAppConfig] = useState<AppConfig | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // 加载应用配置
    const loadAppConfig = async () => {
      try {
        // 从 public 目录加载配置
        const response = await fetch("/apps/apps.config.json")
        if (response.ok) {
          const data = await response.json()
          const app = data.apps?.find((a: AppConfig) => a.id === appId)
          if (app) {
            setAppConfig(app)
          }
        }
      } catch (error) {
        console.error("加载应用配置失败:", error)
      } finally {
        setLoading(false)
      }
    }

    if (appId) {
      loadAppConfig()
    }
  }, [appId])

  // 获取应用组件
  const AppComponent = appComponents[appId]

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!appConfig) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Card className="p-6 text-center">
          <h2 className="text-2xl font-bold mb-4">应用未找到</h2>
          <p className="text-muted-foreground mb-4">应用 ID: {appId}</p>
          <Button onClick={() => router.push("/")}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            返回应用广场
          </Button>
        </Card>
      </div>
    )
  }

  if (!AppComponent) {
    return (
      <div className="max-w-5xl mx-auto">
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => router.push("/")}
                className="mb-4"
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                返回应用广场
              </Button>
              <h2 className="text-2xl font-bold">{appConfig.name}</h2>
              <p className="text-muted-foreground">{appConfig.description}</p>
            </div>
          </div>
          <div className="text-center py-12 text-muted-foreground">
            <p>应用组件未找到，请检查应用是否已正确配置</p>
          </div>
        </Card>
      </div>
    )
  }

  return <AppComponent />
}

