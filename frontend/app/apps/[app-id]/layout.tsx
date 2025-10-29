"use client"

import { Navigation } from "@/components/navigation"
import { usePathname, useRouter } from "next/navigation"
import { useState, useEffect } from "react"

export default function AppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const router = useRouter()
  const [activeTab, setActiveTab] = useState("apps")

  useEffect(() => {
    // 从路径判断当前应该激活的标签
    if (pathname?.startsWith("/apps")) {
      setActiveTab("apps")
    } else if (pathname?.includes("database")) {
      setActiveTab("database")
    } else if (pathname?.includes("workspace")) {
      setActiveTab("workspace")
    } else if (pathname?.includes("status")) {
      setActiveTab("status")
    }
  }, [pathname])

  const handleTabChange = (tab: string) => {
    setActiveTab(tab)
    // 导航到主页面对应的标签
    if (tab === "apps") {
      router.push("/")
    } else {
      router.push(`/?tab=${tab}`)
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <Navigation activeTab={activeTab} onTabChange={handleTabChange} />
      <div className="container mx-auto px-4 py-8">
        {children}
      </div>
    </div>
  )
}

