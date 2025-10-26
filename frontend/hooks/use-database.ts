"use client"

// 数据库操作的自定义Hook
import { useState } from "react"
import useSWR from "swr"
import { databaseApi } from "@/lib/api-client"

export function useDatabase() {
  const [isUploading, setIsUploading] = useState(false)

  const { data, error, mutate } = useSWR("/database/content", () => databaseApi.getDatabaseContent())

  const uploadDatabase = async (file: File) => {
    setIsUploading(true)
    try {
      const result = await databaseApi.uploadDatabase(file)
      await mutate()
      return result
    } finally {
      setIsUploading(false)
    }
  }

  const deleteDatabase = async (id: string) => {
    await databaseApi.deleteDatabase(id)
    await mutate()
  }

  return {
    data: data?.data || [],
    isLoading: !error && !data,
    isError: error,
    isUploading,
    uploadDatabase,
    deleteDatabase,
    refresh: mutate,
  }
}
