"use client"

// 处理状态监控的自定义Hook
import { useEffect, useState } from "react"
import useSWR from "swr"
import { statusApi, StatusWebSocket } from "@/lib/api-client"

export function useStatus() {
  const [ws] = useState(() => {
    if (typeof window !== "undefined" && process.env.NEXT_PUBLIC_WS_URL) {
      return new StatusWebSocket()
    }
    return null
  })

  const { data, error, mutate } = useSWR("/status", () => statusApi.getStatuses(), {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    fallbackData: { statuses: [] },
  })

  useEffect(() => {
    if (!ws) {
      return
    }

    ws.connect()

    // 监听状态更新
    const handleStatusUpdate = (data: any) => {
      mutate()
    }

    ws.on("status_update", handleStatusUpdate)

    return () => {
      ws.off("status_update", handleStatusUpdate)
      ws.disconnect()
    }
  }, [ws])

  const startProcessing = async (workspaceId: string) => {
    await statusApi.startProcessing(workspaceId)
    await mutate()
  }

  const stopProcessing = async (workspaceId: string) => {
    await statusApi.stopProcessing(workspaceId)
    await mutate()
  }

  return {
    statuses: data?.statuses || [],
    isLoading: !error && !data,
    isError: error,
    isWebSocketConnected: ws?.isConnected() || false,
    startProcessing,
    stopProcessing,
    refresh: mutate,
  }
}
