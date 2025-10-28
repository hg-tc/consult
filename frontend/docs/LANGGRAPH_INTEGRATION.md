# LangGraph + DeepResearch 前端集成方案

## 🎯 需要集成的功能

基于后端已实现的 API，前端需要集成以下新功能：

### 1. LangGraph 智能问答 ✅
**API**: `POST /api/chat/langgraph`

**功能特点**：
- 自动意图识别
- 自适应路由（简单/复杂/多跳推理）
- 质量保证（自动改进）
- 返回处理步骤元数据

### 2. DeepResearch 长文档生成 ✅
**API**: `POST /api/document/generate-deepresearch`

**功能特点**：
- 分段并行生成（2-5万字）
- 支持提纲展示
- 质量指标显示
- 参考文献列表

## 📋 集成任务清单

### 任务1: 添加工作流选择器组件

**文件**: `frontend/components/workflow-selector.tsx`

```tsx
import { useState } from 'react'

type WorkflowType = 'simple' | 'langgraph' | 'deepresearch'

interface WorkflowSelectorProps {
  onSelect: (workflow: WorkflowType) => void
  selected: WorkflowType
}

export function WorkflowSelector({ onSelect, selected }: WorkflowSelectorProps) {
  const workflows = [
    {
      id: 'simple' as WorkflowType,
      name: '简单问答',
      description: '适用于简单快速的问题'
    },
    {
      id: 'langgraph' as WorkflowType,
      name: '智能问答',
      description: '自动适配复杂问题，支持多跳推理'
    },
    {
      id: 'deepresearch' as WorkflowType,
      name: '长文档生成',
      description: '生成高质量的长文档（2-5万字）'
    }
  ]

  return (
    <div className="flex gap-2">
      {workflows.map(workflow => (
        <button
          key={workflow.id}
          onClick={() => onSelect(workflow.id)}
          classNameกรุ={`px-4 py-2 rounded ${selected === workflow.id ? 'bg-primary text-white' : 'bg-gray-200'}`}
        >
          <div className="font-medium">{workflow.name}</div>
          <div className="text-xs">{workflow.description}</div>
        </button>
      ))}
    </div>
  )
}
```

### 任务2: 创建 LangGraph API Hook

**文件**: `frontend/hooks/use-langgraph-chat.ts`

```tsx
import { useState, useCallback } from 'react'

export function useLangGraphChat() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  const sendMessage = useCallback(async (
    question: string,
    workspaceId: string = 'global'
  ) => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch('/api/chat/langgraph', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          workspace_id: workspaceId
        })
      })

      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.error || '请求失败')
      }

      setResult(data)
      return data
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '请求失败'
      setError(errorMessage)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  return { sendMessage, loading, result, error }
}
```

### 任务3: 创建 DeepResearch API Hook

**文件**: `frontend/hooks/use-deepresearch-doc.ts`

```tsx
import { useState, useCallback } from 'react'

interface DocRequirements {
  target_words?: number
  writing_style?: string
}

export function useDeepResearchDoc() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  const generateDocument = useCallback(async (
    taskDescription: string,
    workspaceId: string = 'global',
    docRequirements: DocRequirements = {}
  ) => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch('/api/document/generate-deepresearch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.error || '生成失败')
      }

      setResult(data)
      return data
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '生成失败'
      setError(errorMessage)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  return { generateDocument, loading, result, error }
}
```

### 任务4: 更新聊天界面组件

**文件**: `frontend/components/agent/agent-chat-interface.tsx`

主要修改：
1. 添加工作流选择器
2. 根据选择的工作流调用不同的 API
3. 显示处理步骤和元数据
4. 显示质量指标

### 任务5: 创建文档生成界面

**文件**: `frontend/components/document-generator-panel.tsx`

主要功能：
1. 输入任务描述
2. 配置文档要求（字数、风格）
3. 显示生成进度
4. 展示最终文档
5. 显示质量指标和参考文献
6. 支持下载

### 任务6: 更新 API Client

**文件**: `frontend/lib/api-client.ts`

添加新 API 方法：
```typescript
export const langgraphApi = {
  chat: async (question: string, workspaceId: string) => {
    return fetchApi("/chat/langgraph", {
      method: "POST",
      body: JSON.stringify({ question, workspace_id: workspaceId })
    })
  }
}

export const deepresearchApi = {
  generate: async (taskDescription: string, workspaceId: string, requirements: any) => {
    return fetchApi("/document/generate-deepresearch", {
      method: "POST",
      body: JSON.stringify({
        task_description: taskDescription,
        workspace_id: workspaceId,
        doc_requirements: requirements
      })
    })
  }
}
```

### 任务7: 添加元数据展示组件

**文件**: `frontend/components/metadata-panel.tsx`

显示：
- 意图类型
- 复杂度
- 质量分数
- 处理步骤
- 引用来源

## 🎨 UI/UX 建议

### 工作流选择
- 添加到聊天界面顶部作为切换按钮
- 使用图标和简短描述
- 选中状态高亮显示

### 处理进度
- LangGraph: 显示当前处理的节点（意图分析、检索、生成等）
- DeepResearch: 显示段落生成进度（第 X/50 段）

### 结果展示
- LangGraph: 显示答案 + 质量分数 + 处理步骤
- DeepResearch: 显示文档 + 大纲 + 质量指标 + 参考文献

### 质量指标可视化
- 使用进度条显示质量分数
- 使用颜色编码（绿色 > 0.8，黄色 > 0.6，红色 < 0.6）

## 🔄 集成优先级

### 第一阶段（核心功能）
1. ✅ 创建 API Hooks
2. ✅ 添加工作流选择器
3. ✅ 更新聊天界面支持 LangGraph

### 第二阶段（增强功能）
4. ✅ 创建文档生成界面
5. ✅ 添加元数据展示
6. ✅ 添加质量指标可视化

### 第三阶段（优化体验）
7. ✅ 添加处理进度提示
8. ✅ 优化错误处理
9. ✅ 添加性能监控

## 📝 使用示例

### LangGraph 智能问答
```typescript
const { sendMessage, loading, result } = useLangGraphChat()

const handleSubmit = async () => {
  const response = await sendMessage("什么是人工智能？", "global")
  
  // 响应结构：
  // {
  //   answer: "人工智能是...",
  //   sources: ["文档1", "文档2"],
  //   metadata: {
  //     intent: "simple_qa",
  //     complexity: "medium",
  //     quality_score: 0.92,
  //     processing_steps: ["intent_analysis", "simple_retrieval", "answer_generation"]
  //   }
  // }
}
```

### DeepResearch 文档生成
```typescript
const { generateDocument, loading, result } = useDeepResearchDoc()

const handleGenerate = async () => {
  const response = await generateDocument(
    "写一份关于深度学习的调研报告",
    "global",
    { target_words: 5000, writing_style: "专业" }
  )
  
  // 响应结构：
  // {
  //   document: "完整文档内容...",
  //   quality_metrics: { total_words: 5234, total_sections: 30 },
  //   references: [{id: 1, source: "文档1"}, ...],
  //   outline: { title: "深度学习调研报告", sections: [...] }
  // }
}
```

## ✅ 集成检查清单

- [ ] API Hooks 创建完成
- [ ] 工作流选择器组件
- [ ] 聊天界面支持 LangGraph
- [ ] 文档生成界面
- [ ] 元数据展示组件
- [ ] API Client 更新
- [ ] 错误处理完善
- [ ] 用户体验优化

## 📚 参考文档

- [后端 API 文档](../backend/docs/LANGGRAPH_IMPLEMENTATION.md)
- [实施总结](../backend/docs/IMPLEMENTATION_SUMMARY.md)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)

