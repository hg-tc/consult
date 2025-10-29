"use client"

import { Navigation } from "@/components/navigation"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useEffect, useState } from "react"

export default function AppsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [activeTab, setActiveTab] = useState("apps")

  useEffect(() => {
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


