"use client"

import { useState, useEffect, useCallback, useRef } from "react"

interface Message {
  role: "user" | "agent" | "system"
  content: string
  timestamp: Date
  metadata?: any
}

interface WorkflowState {
  currentStep: string
  steps: any[]
  progress: number
  status: string
}

export function useAgentChat(workspaceId: string) {
  const STORAGE_KEY = `agent_chat_messages_${workspaceId}`
  
  // 从 localStorage 加载消息历史
  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window === 'undefined') return []
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        return parsed.map((msg: any) => ({
          ...msg,
          timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date()
        }))
      }
    } catch (e) {
      console.error('[useAgentChat] 加载消息失败:', e)
    }
    return []
  })
  
  const [isGenerating, setIsGenerating] = useState(false)
  const [workflowState, setWorkflowState] = useState<WorkflowState | null>(null)
  const [streamingContent, setStreamingContent] = useState("")
  const wsRef = useRef<WebSocket | null>(null)

  // 保存消息到 localStorage
  useEffect(() => {
    if (messages.length > 0) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(messages))
      } catch (e) {
        console.error('[useAgentChat] 保存消息失败:', e)
      }
    }
  }, [messages, STORAGE_KEY])

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  const handleWebSocketMessage = useCallback((data: any) => {
    switch (data.type) {
      case "token":
        // 流式输出 token
        setStreamingContent(prev => prev + data.content)
        break

      case "stage_start":
        // 工作流阶段开始
        setWorkflowState(prev => ({
          ...prev!,
          currentStep: data.stage,
          steps: updateStepStatus(prev?.steps || [], data.stage, "running")
        }))
        break

      case "stage_complete":
        // 工作流阶段完成
        setWorkflowState(prev => ({
          ...prev!,
          steps: updateStepStatus(prev?.steps || [], data.stage, "completed"),
          progress: data.progress
        }))
        break

      case "complete":
        // 生成完成
        setIsGenerating(false)
        if (streamingContent) {
          addMessage("agent", streamingContent)
          setStreamingContent("")
        }
        break

      case "error":
        // 错误处理
        setIsGenerating(false)
        addMessage("system", `错误: ${data.error}`)
        break
    }
  }, [streamingContent])

  const sendMessage = useCallback(async (content: string) => {
    addMessage("user", content)
    setIsGenerating(true)

    // 连接到 WebSocket
    const ws = new WebSocket(
      `ws://${window.location.host}/api/v1/production-agent/ws/generate`
    )

    ws.onopen = () => {
      console.log("WebSocket connected")
      
      // 发送请求
      ws.send(JSON.stringify({
        user_request: content,
        workspace_id: workspaceId,
        conversation_history: messages
      }))
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      handleWebSocketMessage(data)
    }

    ws.onerror = (error) => {
      console.error("WebSocket error:", error)
      setIsGenerating(false)
    }

    ws.onclose = () => {
      console.log("WebSocket disconnected")
      setIsGenerating(false)
    }

    wsRef.current = ws
  }, [workspaceId, messages, handleWebSocketMessage])

  const confirmAction = useCallback((feedback: string, options: string[]) => {
    // TODO: 实现确认功能
    console.log("Confirm action:", { feedback, options })
  }, [])

  const addMessage = useCallback((role: Message["role"], content: string) => {
    setMessages(prev => [...prev, {
      role,
      content,
      timestamp: new Date()
    }])
  }, [])

  return {
    messages,
    isGenerating,
    workflowState,
    streamingContent,
    sendMessage,
    confirmAction
  }
}

function updateStepStatus(steps: any[], stepId: string, status: string) {
  return steps.map(step => 
    step.id === stepId ? { ...step, status } : step
  )
}

