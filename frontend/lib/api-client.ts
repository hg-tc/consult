// API客户端配置和通用请求方法

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:13000/api"

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

async function fetchApi<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`

  // 创建AbortController用于超时控制
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 180000) // 3分钟超时

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: "Request failed" }))
      throw new ApiError(response.status, error.message || "Request failed")
    }

    return response.json()
  } catch (error: unknown) {
    clearTimeout(timeoutId)
    const errObj = error as any
    if (errObj && errObj.name === 'AbortError') {
      throw new ApiError(408, "Request timeout")
    }
    throw error
  }
}

// 全局文档相关API（用于数据库管理页面）
export const globalDocumentApi = {
  // 上传文档到全局数据库
  async uploadDocument(file: File, hierarchyPath?: string) {
    console.log("[v0] uploadGlobalDocument API called with:", {
      fileName: file.name,
      fileSize: file.size,
      fileType: file.type
    })
    
    const formData = new FormData()
    formData.append("file", file)
    if (hierarchyPath) {
      formData.append("hierarchy_path", hierarchyPath)
    }

    console.log("[v0] FormData contents:")
    for (let [key, value] of formData.entries()) {
      console.log(`  ${key}:`, value)
    }

    const response = await fetch(`${API_BASE_URL}/global/documents/upload`, {
      method: "POST",
      body: formData,
      // 不要设置Content-Type，让浏览器自动设置multipart/form-data
    })

    console.log("[v0] Upload response:", {
      status: response.status,
      statusText: response.statusText,
      headers: Object.fromEntries(response.headers.entries())
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error("[v0] Upload failed:", response.status, errorText)
      throw new ApiError(response.status, `Document upload failed: ${errorText}`)
    }

    const result = await response.json()
    console.log("[v0] Upload result:", result)
    return result
  },

  // 获取全局文档列表
  async getDocuments() {
    return fetchApi<{ documents: any[] }>(`/global/documents`)
  },

  // 删除全局文档
  async deleteDocument(id: string) {
    return fetchApi(`/global/documents/${id}`, { method: "DELETE" })
  },

  // 下载全局文档
  async downloadDocument(id: string) {
    const response = await fetch(`${API_BASE_URL}/global/documents/${id}/download`)
    if (!response.ok) {
      throw new ApiError(response.status, "Document download failed")
    }
    return response.blob()
  },
}

// 工作区文档相关API（用于工作区管理页面）
export const workspaceDocumentApi = {
  // 上传文档到工作区
  async uploadDocument(workspaceId: string, file: File) {
    const formData = new FormData()
    formData.append("file", file)

    const response = await fetch(`${API_BASE_URL}/workspaces/${workspaceId}/documents/upload`, {
      method: "POST",
      body: formData,
    })

    if (!response.ok) {
      throw new ApiError(response.status, "Document upload failed")
    }

    return response.json()
  },

  // 获取工作区文档列表
  async getDocuments(workspaceId: string) {
    return fetchApi(`/workspaces/${workspaceId}/documents`)
  },

  // 删除工作区文档
  async deleteDocument(workspaceId: string, id: string) {
    return fetchApi(`/workspaces/${workspaceId}/documents/${id}`, { method: "DELETE" })
  },

  // 下载工作区文档
  async downloadDocument(workspaceId: string, id: string) {
    const response = await fetch(`${API_BASE_URL}/workspaces/${workspaceId}/documents/${id}/download`)
    if (!response.ok) {
      throw new ApiError(response.status, "Document download failed")
    }
    return response.blob()
  },
}

// 文档相关API（保持向后兼容）
export const documentApi = {
  // 上传文档文件
  async uploadDocument(file: File, workspaceId: string = "1") {
    console.log("[v0] uploadDocument API called with:", {
      fileName: file.name,
      fileSize: file.size,
      fileType: file.type,
      workspaceId: workspaceId
    })
    
    const formData = new FormData()
    formData.append("file", file)
    formData.append("workspace_id", workspaceId)

    console.log("[v0] FormData contents:")
    for (let [key, value] of formData.entries()) {
      console.log(`  ${key}:`, value)
    }

    const response = await fetch(`${API_BASE_URL}/documents/upload`, {
      method: "POST",
      body: formData,
      // 不要设置Content-Type，让浏览器自动设置multipart/form-data
    })

    console.log("[v0] Upload response:", {
      status: response.status,
      statusText: response.statusText,
      headers: Object.fromEntries(response.headers.entries())
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error("[v0] Upload failed:", response.status, errorText)
      throw new ApiError(response.status, `Document upload failed: ${errorText}`)
    }

    const result = await response.json()
    console.log("[v0] Upload result:", result)
    return result
  },

  // 获取文档列表
  async getDocuments(workspaceId?: string) {
    const params = workspaceId ? `?workspace_id=${workspaceId}` : ''
    return fetchApi(`/documents${params}`)
  },

  // 删除文档
  async deleteDocument(id: string) {
    return fetchApi(`/documents/${id}`, { method: "DELETE" })
  },

  // 对文档进行向量化
  async vectorizeDocument(id: string) {
    return fetchApi(`/documents/${id}/vectorize`, { method: "POST" })
  },

  // 获取数据库内容
  async getDatabaseContent(limit = 100, offset = 0) {
    return fetchApi(`/database/content?limit=${limit}&offset=${offset}`)
  },

  // 删除数据库
  async deleteDatabase(id: string) {
    return fetchApi(`/database/${id}`, { method: "DELETE" })
  },
}

// 工作区相关API
export const workspaceApi = {
  // 获取所有工作区
  async getWorkspaces() {
    return fetchApi("/workspaces")
  },

  // 创建工作区
  async createWorkspace(name: string) {
    return fetchApi("/workspaces", {
      method: "POST",
      body: JSON.stringify({ name }),
    })
  },

  // 更新工作区名称
  async updateWorkspace(id: string, name: string) {
    return fetchApi(`/workspaces/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    })
  },

  // 删除工作区
  async deleteWorkspace(id: string) {
    return fetchApi(`/workspaces/${id}`, { method: "DELETE" })
  },

  // 上传工作区文件
  async uploadFile(workspaceId: string, file: File) {
    const formData = new FormData()
    formData.append("file", file)

    const response = await fetch(`${API_BASE_URL}/workspaces/${workspaceId}/files`, {
      method: "POST",
      body: formData,
    })

    if (!response.ok) {
      throw new ApiError(response.status, "File upload failed")
    }

    return response.json()
  },

  // 获取工作区文件列表
  async getFiles(workspaceId: string) {
    return fetchApi(`/workspaces/${workspaceId}/files`)
  },

  // 删除工作区文件
  async deleteFile(workspaceId: string, fileId: string) {
    return fetchApi(`/workspaces/${workspaceId}/files/${fileId}`, {
      method: "DELETE",
    })
  },
}

// 处理状态相关API
export const statusApi = {
  // 获取所有工作区的处理状态
  async getStatuses() {
    return fetchApi("/status")
  },

  // 获取特定工作区的处理状态
  async getWorkspaceStatus(workspaceId: string) {
    return fetchApi(`/status/${workspaceId}`)
  },

  // 启动处理任务
  async startProcessing(workspaceId: string) {
    return fetchApi(`/status/${workspaceId}/start`, {
      method: "POST",
    })
  },

  // 停止处理任务
  async stopProcessing(workspaceId: string) {
    return fetchApi(`/status/${workspaceId}/stop`, {
      method: "POST",
    })
  },
}

// Agent交互相关API
export const agentApi = {
  // 发送消息给Agent（支持对话历史）
  async sendMessage(workspaceId: string, message: string, history?: Array<{role: string, content: string}>) {
    return fetchApi("/agent/chat", {
      method: "POST",
      body: JSON.stringify({ 
        workspace_id: workspaceId, 
        message,
        history: history || []  // 新增：发送对话历史
      }),
    })
  },

  // 获取聊天历史
  async getChatHistory(workspaceId: string) {
    return fetchApi(`/agent/chat/${workspaceId}`)
  },

  // 下载输出文件
  async downloadFile(fileId: string) {
    const response = await fetch(`${API_BASE_URL}/agent/files/${fileId}`)
    if (!response.ok) {
      throw new ApiError(response.status, "File download failed")
    }
    return response.blob()
  },

  // 获取可用的应用操作
  async getAvailableActions(workspaceId: string) {
    return fetchApi(`/agent/actions/${workspaceId}`)
  },

  // 执行特定应用操作
  async executeAction(workspaceId: string, actionId: string, params?: any) {
    return fetchApi("/agent/execute", {
      method: "POST",
      body: JSON.stringify({ workspaceId, actionId, params }),
    })
  },
}

// LangGraph 智能问答 API
export const langgraphApi = {
  async chat(question: string, workspaceId: string = 'global') {
    return fetchApi("/chat/langgraph", {
      method: "POST",
      body: JSON.stringify({ 
        question,
        workspace_id: workspaceId
      })
    })
  }
}

// DeepResearch 文档生成 API
export const deepresearchApi = {
  async generateDocument(
    taskDescription: string, 
    workspaceId: string = 'global',
    docRequirements: {
      target_words?: number
      writing_style?: string
    } = {}
  ) {
    return fetchApi("/document/generate-deepresearch", {
      method: "POST",
      body: JSON.stringify({
        task_description: taskDescription,
        workspace_id: workspaceId,
        doc_requirements: {
          target_words: 5000,
          writing_style: '专业、严谨、客观',
          ...docRequirements
        }
      })
    })
  }
}

// WebSocket连接用于实时状态更新
export class StatusWebSocket {
  private ws: WebSocket | null = null
  private reconnectTimeout: NodeJS.Timeout | null = null
  private listeners: Map<string, Set<(data: any) => void>> = new Map()
  private reconnectAttempts = 0
  private maxReconnectAttempts = 3
  private isManuallyDisconnected = false

  connect() {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL

    if (!wsUrl) {
      console.log("[v0] WebSocket URL not configured, skipping connection")
      return
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log("[v0] WebSocket max reconnection attempts reached, giving up")
      return
    }

    if (this.isManuallyDisconnected) {
      return
    }

    try {
      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        this.reconnectAttempts = 0
        if (this.reconnectTimeout) {
          clearTimeout(this.reconnectTimeout)
          this.reconnectTimeout = null
        }
      }

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          const listeners = this.listeners.get(data.type)
          if (listeners) {
            listeners.forEach((callback) => callback(data))
          }
        } catch (error) {
          console.error("[v0] WebSocket message parse error:", error)
        }
      }

      this.ws.onerror = () => {}

      this.ws.onclose = () => {
        if (!this.isManuallyDisconnected && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++
          this.reconnectTimeout = setTimeout(() => this.connect(), 5000)
        }
      }
    } catch (error) {
      console.error("[v0] WebSocket connection failed:", error)
    }
  }

  disconnect() {
    this.isManuallyDisconnected = true
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN
  }

  on(event: string, callback: (data: any) => void) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)!.add(callback)
  }

  off(event: string, callback: (data: any) => void) {
    const listeners = this.listeners.get(event)
    if (listeners) {
      listeners.delete(callback)
    }
  }

  send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }
}
