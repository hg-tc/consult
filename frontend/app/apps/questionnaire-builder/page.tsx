"use client"

import { useState, useRef, useEffect, useMemo } from 'react'
import { getClientId } from '@/lib/client-id'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Loader2, FileText, Download, ArrowLeft, CheckCircle2, Info } from 'lucide-react'
import { useRouter } from 'next/navigation'

export default function QuestionnaireBuilderPage() {
  const router = useRouter()
  const STORAGE_PREFIX = 'questionnaire_builder_'
  
  // 从 localStorage 加载表单数据
  const [workspaceId, setWorkspaceId] = useState<string>(() => {
    if (typeof window === 'undefined') return ""
    return localStorage.getItem(`${STORAGE_PREFIX}workspaceId`) || ""
  })
  const [companyName, setCompanyName] = useState<string>(() => {
    if (typeof window === 'undefined') return ""
    return localStorage.getItem(`${STORAGE_PREFIX}companyName`) || ""
  })
  const [targetProjects, setTargetProjects] = useState<string>(() => {
    if (typeof window === 'undefined') return ""
    return localStorage.getItem(`${STORAGE_PREFIX}targetProjects`) || ""
  })
  const [knownInfo, setKnownInfo] = useState<string>(() => {
    if (typeof window === 'undefined') return ""
    return localStorage.getItem(`${STORAGE_PREFIX}knownInfo`) || ""
  })

  // 从 localStorage 加载已完成的结果（如果有taskId且已完成）
  // 如果没有taskId，说明是中断的任务，不显示结果
  const [result, setResult] = useState<any>(() => {
    if (typeof window === 'undefined') return null
    try {
      const savedResult = localStorage.getItem(`${STORAGE_PREFIX}result`)
      const savedTaskId = localStorage.getItem(`${STORAGE_PREFIX}taskId`)
      // 只有在有taskId时才恢复结果（说明是已完成的任务）
      // 如果没有taskId，说明任务可能被中断了，不显示旧结果
      if (savedResult && savedTaskId) {
        return JSON.parse(savedResult)
      }
      return null
    } catch (e) {
      return null
    }
  })

  // 所有状态初始化为空值，确保页面加载时是干净的状态
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentStage, setCurrentStage] = useState<string | null>(null)
  const [stageDescription, setStageDescription] = useState<string>("")
  const [completedStages, setCompletedStages] = useState<Set<string>>(new Set())
  // 从 localStorage 恢复taskId（用于恢复正在进行的任务或已完成的任务）
  const [taskId, setTaskId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null
    const saved = localStorage.getItem(`${STORAGE_PREFIX}taskId`)
    return saved || null
  })
  const [taskProgress, setTaskProgress] = useState<number>(0) // 从后端返回的progress更新这个值
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  
  // 页面加载时，检查并恢复任务状态（只在组件挂载时执行一次）
  useEffect(() => {
    // 从localStorage读取taskId（直接从存储读取，不依赖state，避免循环依赖）
    const savedTaskId = localStorage.getItem(`${STORAGE_PREFIX}taskId`)
    const savedResult = localStorage.getItem(`${STORAGE_PREFIX}result`)
    
    // 如果有taskId，检查任务状态并恢复
    if (savedTaskId) {
      const checkTask = async () => {
        try {
          const response = await fetch(`/api/apps/questionnaire-builder/result/${savedTaskId}`)
          if (response.ok) {
            const data = await response.json()
            if (data.status === 'completed') {
              // 任务已完成，显示结果
              const completedResult = {
                final_analysis: data.final_analysis,
                final_md: data.final_md,
              }
              setResult(completedResult)
              setLoading(false)
              // 保存结果和taskId到localStorage和state，这样刷新后还能看到
              setTaskId(savedTaskId)
              localStorage.setItem(`${STORAGE_PREFIX}result`, JSON.stringify(completedResult))
              localStorage.setItem(`${STORAGE_PREFIX}taskId`, savedTaskId)
            } else if (data.status === 'processing' || data.status === 'pending') {
              // 任务还在进行中，恢复轮询和进度显示
              setTaskId(savedTaskId)
              setLoading(true)
              setStageDescription(data.message || "任务处理中...")
              if (data.details?.stage) {
                setCurrentStage(data.details.stage)
              }
              if (data.progress !== undefined) {
                setTaskProgress(data.progress)
              }
            } else if (data.status === 'failed') {
              // 任务已失败，清除所有状态（中断的任务）
              setTaskId(null)
              setResult(null)
              setLoading(false)
              localStorage.removeItem(`${STORAGE_PREFIX}taskId`)
              localStorage.removeItem(`${STORAGE_PREFIX}result`)
              setError(data.error_message || '任务执行失败')
            }
          } else if (response.status === 404) {
            // 任务不存在（可能是过期或被清理），清除所有状态（中断的任务）
            setTaskId(null)
            setResult(null)
            setLoading(false)
            localStorage.removeItem(`${STORAGE_PREFIX}taskId`)
            localStorage.removeItem(`${STORAGE_PREFIX}result`)
          }
        } catch (e) {
          console.error('恢复任务状态失败:', e)
          // 出错时清除所有状态（中断的任务）
          setTaskId(null)
          setResult(null)
          setLoading(false)
          localStorage.removeItem(`${STORAGE_PREFIX}taskId`)
          localStorage.removeItem(`${STORAGE_PREFIX}result`)
        }
      }
      // 延迟执行，避免阻塞初始渲染
      setTimeout(checkTask, 100)
    } else {
      // 如果没有taskId，但有result，说明可能是中断的任务，清除结果
      if (savedResult) {
        setResult(null)
        localStorage.removeItem(`${STORAGE_PREFIX}result`)
      }
    }
  }, []) // 只在组件挂载时执行一次

  // 保存表单数据到 localStorage
  useEffect(() => {
    if (workspaceId) localStorage.setItem(`${STORAGE_PREFIX}workspaceId`, workspaceId)
  }, [workspaceId])
  
  useEffect(() => {
    if (companyName) localStorage.setItem(`${STORAGE_PREFIX}companyName`, companyName)
  }, [companyName])
  
  useEffect(() => {
    if (targetProjects) localStorage.setItem(`${STORAGE_PREFIX}targetProjects`, targetProjects)
  }, [targetProjects])
  
  useEffect(() => {
    if (knownInfo) localStorage.setItem(`${STORAGE_PREFIX}knownInfo`, knownInfo)
  }, [knownInfo])

  // 保存结果到 localStorage（仅当有对应的taskId时）
  // 这样可以确保刷新后还能看到已完成的任务结果
  useEffect(() => {
    if (result && taskId) {
      try {
        localStorage.setItem(`${STORAGE_PREFIX}result`, JSON.stringify(result))
      } catch (e) {
        console.error('[QuestionnaireBuilder] 保存结果失败:', e)
      }
    }
  }, [result, taskId])

  // 保存taskId到localStorage，用于恢复任务状态
  useEffect(() => {
    if (taskId) {
      localStorage.setItem(`${STORAGE_PREFIX}taskId`, taskId)
    } else {
      // 如果taskId被清除，也清除localStorage
      localStorage.removeItem(`${STORAGE_PREFIX}taskId`)
    }
  }, [taskId])

  // 定义所有阶段
  const STAGES = [
    { id: 'db_search', name: '数据库检索', description: '正在从内部数据库检索政策信息' },
    { id: 'web_search', name: '网络检索', description: '正在从互联网搜索相关政策信息' },
    { id: 'summery', name: '信息汇总', description: '正在汇总检索到的信息' },
    { id: 'judger', name: '信息判断', description: '正在判断信息完整性' },
    { id: 'person_info_web_search', name: '人员信息检索', description: '正在检索相关人员信息' },
    { id: 'analysis', name: '分析生成', description: '正在生成分析报告' },
    { id: 'query', name: '问卷细化', description: '正在细化问卷问题' },
  ]

  const currentStageIdx = useMemo(() => {
    if (!currentStage) return -1
    const idx = STAGES.findIndex(s => s.id === currentStage)
    return idx >= 0 ? idx : -1
  }, [currentStage])

  const progressPercent = useMemo(() => {
    // 如果正在轮询任务，使用任务返回的progress
    if (loading && taskId && taskProgress > 0) {
      return taskProgress
    }
    // 否则使用基于阶段的进度计算
    if (currentStageIdx < 0) return 0
    const base = Math.floor((completedStages.size / STAGES.length) * 100)
    if (currentStage && !completedStages.has(currentStage)) {
      return Math.min(95, base + 5)
    }
    return Math.min(100, base)
  }, [currentStageIdx, completedStages, currentStage, loading, taskId, taskProgress])

  // 轮询任务状态
  useEffect(() => {
    if (!taskId || !loading) {
      // 清除轮询
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
      }
      return
    }

    const pollTaskStatus = async () => {
      try {
        const response = await fetch(`/api/apps/questionnaire-builder/result/${taskId}`)
        if (!response.ok) {
          if (response.status === 404) {
            // 任务不存在（可能是过期或被清理），清除所有状态（中断的任务）
            setLoading(false)
            setTaskId(null)
            setResult(null)
            localStorage.removeItem(`${STORAGE_PREFIX}taskId`)
            localStorage.removeItem(`${STORAGE_PREFIX}result`)
            setError("任务不存在，请重新生成")
            if (pollingIntervalRef.current) {
              clearInterval(pollingIntervalRef.current)
              pollingIntervalRef.current = null
            }
            return
          }
          throw new Error(`HTTP ${response.status}`)
        }
        
        const data = await response.json()
        
        if (data.status === 'completed') {
          // 任务完成，保存结果并停止轮询
          const newResult = {
            final_analysis: data.final_analysis,
            final_md: data.final_md,
          }
          setResult(newResult)
          setLoading(false)
          setCurrentStage(null)
          setStageDescription('问卷生成完成')
          // 保留taskId，这样刷新后还能看到结果
          // 只有在用户点击"生成问卷"时才会清除taskId
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
          }
        } else if (data.status === 'failed') {
          // 任务失败，清除所有状态（中断的任务）
          setLoading(false)
          setTaskId(null)
          setResult(null)
          localStorage.removeItem(`${STORAGE_PREFIX}taskId`)
          localStorage.removeItem(`${STORAGE_PREFIX}result`)
          setError(data.error_message || '任务执行失败')
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
          }
        } else {
          // 更新进度信息（处理中或等待中）
          if (data.message) {
            setStageDescription(data.message)
          }
          
          // 从details中获取stage信息
          if (data.details?.stage) {
            setCurrentStage(data.details.stage)
          }
          
          // 根据progress百分比更新进度和已完成阶段
          if (data.progress !== undefined) {
            // 更新任务进度值
            setTaskProgress(data.progress)
            
            // 根据progress百分比判断完成了哪些阶段
            const progressRatio = data.progress / 100
            const completedCount = Math.floor(progressRatio * STAGES.length)
            const newCompletedStages = new Set<string>()
            
            // 标记已完成阶段
            for (let i = 0; i < completedCount && i < STAGES.length; i++) {
              newCompletedStages.add(STAGES[i].id)
            }
            setCompletedStages(newCompletedStages)
          }
        }
      } catch (err) {
        console.error('轮询任务状态失败:', err)
        // 不中断轮询，继续尝试
      }
    }

    // 立即执行一次
    pollTaskStatus()
    
    // 每3秒轮询一次
    pollingIntervalRef.current = setInterval(pollTaskStatus, 3000)

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
      }
    }
  }, [taskId, loading, STAGES])

  const handleGenerate = async () => {
    // 点击生成问卷时，清除所有旧状态和任务数据（包括localStorage）
    setError(null)
    setResult(null)
    setCurrentStage(null)
    setStageDescription("")
    setCompletedStages(new Set())
    setTaskProgress(0)
    setTaskId(null)
    localStorage.removeItem(`${STORAGE_PREFIX}result`)
    localStorage.removeItem(`${STORAGE_PREFIX}taskId`)
    
    const projects = targetProjects
      .split("\n")
      .map(p => p.trim())
      .filter(Boolean)

    if (projects.length === 0) {
      setError("申请项目为必填，请至少填写一个项目（每行一个）")
      return
    }

    setLoading(true)
    try {
      // 获取客户端ID，确保不同设备的对话记忆隔离
      const clientId = getClientId()
      
      const payload = {
        workspace_id: workspaceId || undefined,
        company_name: companyName || undefined,
        target_projects: projects,
        known_info: knownInfo ? safeJsonParse(knownInfo) : undefined,
        client_id: clientId,  // 添加客户端ID，后端会用它来隔离不同设备的对话记忆
      }
      // 使用AbortController设置超时，但设置为30分钟（1800000ms），远大于后端超时时间
      // 这样可以避免前端提前超时，让真正的超时由Nginx或后端控制
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 1800000) // 30分钟超时
      
      try {
        const resp = await fetch("/api/apps/questionnaire-builder/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: controller.signal,  // 添加signal支持超时控制
        })
        
        clearTimeout(timeoutId)  // 请求完成，清除超时
      
        // 检查响应类型，避免解析HTML错误页面
        const contentType = resp.headers.get("content-type") || ""
        if (!contentType.includes("application/json")) {
          const text = await resp.text()
          throw new Error(`服务器错误（${resp.status}）: ${text.substring(0, 200)}`)
        }
        
        const data = await resp.json()
        if (!resp.ok) {
          throw new Error(data.detail || data.message || `生成失败（${resp.status}）`)
        }
        // 后台任务模式：返回task_id，启动轮询
        if (data.task_id) {
          setTaskId(data.task_id)
          setStageDescription(data.message || "任务已提交，正在处理...")
          // 保持loading=true，让轮询useEffect继续工作
          // 不要在这里设置setLoading(false)，轮询会自动处理
        } else {
          // 兼容旧格式（同步返回结果）
          setResult(data)
          setLoading(false)
        }
      } catch (fetchError: any) {
        clearTimeout(timeoutId)  // 确保清除超时
        throw fetchError
      }
    } catch (e: any) {
      // 处理超时和其他错误
      setLoading(false) // 发生错误时停止loading
      if (e.name === "AbortError") {
        setError("请求超时（超过30分钟），问卷生成时间过长，请稍后重试或减少申请项目数量")
      } else if (e.message.includes("504") || e.message.includes("Gateway Timeout")) {
        setError("服务器网关超时，可能是Nginx或后端服务超时，请稍后重试")
      } else {
        setError(e.message || "生成失败")
      }
    }
    // 注意：如果成功获取了task_id，不要在这里设置setLoading(false)
    // 让轮询useEffect继续工作，直到任务完成或失败
  }

  const downloadDocument = (content: string, filename: string) => {
    if (!content) return
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      {/* 头部导航 */}
      <div className="mb-6 max-w-5xl mx-auto">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/")}
          className="mb-4"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          返回应用广场
        </Button>
        <h1 className="text-3xl font-bold mb-2">问卷生成</h1>
        <p className="text-muted-foreground">
          根据申请项目与客户画像，结合内部与互联网公开信息，生成政策问卷与材料清单
        </p>
      </div>

      <div className="space-y-6 max-w-5xl mx-auto">
        {/* 配置面板 */}
        <Card className="p-6">
          <div className="space-y-4">
            {/* 工作区 */}
            <div>
              <Label htmlFor="workspace-id">工作区（可选）</Label>
              <Input
                id="workspace-id"
                value={workspaceId}
                onChange={e => setWorkspaceId(e.target.value)}
                placeholder="如：global 或具体工作区ID"
                disabled={loading}
                className="mt-2"
              />
            </div>

            {/* 公司名称 */}
            <div>
              <Label htmlFor="company-name">公司名称/统一社会信用代码（可选）</Label>
              <Input
                id="company-name"
                value={companyName}
                onChange={e => setCompanyName(e.target.value)}
                placeholder="用于抓取公开信息"
                disabled={loading}
                className="mt-2"
              />
            </div>

            {/* 申请项目 */}
            <div>
              <Label htmlFor="target-projects">申请项目（必填，每行一个）*</Label>
              <Textarea
                id="target-projects"
                value={targetProjects}
                onChange={e => setTargetProjects(e.target.value)}
                placeholder={`示例：
前海人才配租房申请
前海科创企业场地补贴
前海港人创业资助`}
                rows={6}
                disabled={loading}
                className="mt-2"
              />
            </div>

            {/* 已知信息 */}
            <div>
              <Label htmlFor="known-info">其他已知信息（可选，JSON）</Label>
              <Textarea
                id="known-info"
                value={knownInfo}
                onChange={e => setKnownInfo(e.target.value)}
                placeholder='{"region":"前海","employees":120,"has_lease":true}'
                rows={4}
                disabled={loading}
                className="mt-2"
              />
              <p className="text-xs text-muted-foreground mt-1">
                可填主体画像/经营指标/场地/人才/历史记录/意向/现有材料等键值
              </p>
            </div>

            {/* 生成按钮 */}
            <Button
              onClick={handleGenerate}
              disabled={loading || !targetProjects.trim()}
              className="w-full"
              size="lg"
              type="button"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  生成中...
                </>
              ) : (
                <>
                  <FileText className="w-4 h-4 mr-2" />
                  生成问卷
                </>
              )}
            </Button>
            {error && <div className="text-sm text-destructive">{error}</div>}
          </div>
        </Card>

        {/* 错误提示 */}
        {error && (
          <Card className="p-4 border-destructive bg-destructive/10">
            <p className="text-destructive">{error}</p>
          </Card>
        )}

        {/* 生成进度 */}
        {loading && (
          <Card className="p-6 border-primary bg-primary/10">
            <div className="flex items-center gap-2 mb-4">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
              <span className="font-medium">正在生成问卷...</span>
            </div>
            
            {/* 温馨提示 */}
            <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg">
              <div className="flex items-start gap-2">
                <Info className="w-4 h-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-blue-900 dark:text-blue-100">
                  <p className="font-medium mb-1">温馨提示</p>
                  <p className="leading-relaxed">
                    问卷生成预计需要 <span className="font-semibold">5-10分钟</span>，您可以离开当前页面，结果会自动保存。刷新页面后仍可查看生成进度和结果。
                  </p>
                </div>
              </div>
            </div>
            
            {/* 进度条 */}
            <div className="mb-4">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm text-muted-foreground">总体进度</span>
                <span className="text-sm font-medium">{progressPercent}%</span>
              </div>
              <div className="w-full bg-muted rounded-full h-2">
                <div 
                  className="bg-primary h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

            {/* 当前阶段或状态描述 */}
            {(currentStage || stageDescription) && (
              <div className="mb-4 p-3 bg-background rounded-md border">
                <div className="flex items-center gap-2 mb-1">
                  <Loader2 className="w-4 h-4 animate-spin text-primary" />
                  <span className="text-sm font-medium">
                    {currentStage 
                      ? (STAGES.find(s => s.id === currentStage)?.name || currentStage)
                      : "处理中..."}
                  </span>
                </div>
                {stageDescription && (
                  <p className="text-xs text-muted-foreground ml-6">
                    {stageDescription}
                  </p>
                )}
              </div>
            )}

            {/* 阶段列表 */}
            <div className="space-y-2">
              {STAGES.map((stage, idx) => {
                const isCompleted = completedStages.has(stage.id)
                const isCurrent = currentStage === stage.id
                const isPending = !isCompleted && !isCurrent
                
                return (
                  <div 
                    key={stage.id}
                    className={`flex items-center gap-2 text-sm p-2 rounded ${
                      isCurrent ? 'bg-primary/10 border border-primary/20' : ''
                    }`}
                  >
                    {isCompleted ? (
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                    ) : isCurrent ? (
                      <Loader2 className="w-4 h-4 animate-spin text-primary" />
                    ) : (
                      <div className="w-4 h-4 rounded-full border-2 border-muted-foreground/30" />
                    )}
                    <span className={isCompleted ? 'text-muted-foreground line-through' : isCurrent ? 'font-medium' : 'text-muted-foreground'}>
                      {stage.name}
                    </span>
                  </div>
                )
              })}
            </div>
          </Card>
        )}

        {/* 结果展示 */}
        {result && (
          <div className="space-y-6">
            {/* 成功提示 */}
            <Card className="p-4 border-green-200 bg-green-50">
              <h3 className="font-semibold text-green-900 mb-2">✅ 生成完成</h3>
              <p className="text-sm text-green-700">
                已生成完整的评估报告和问卷，包含申报条件、材料清单和进一步核实问题
              </p>
            </Card>

            {/* 第一个文档：final_analysis - 分析结果 */}
            {result.final_analysis && (
              <Card className="p-4">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="font-semibold">📊 分析结果</h3>
                  <Button 
                    onClick={() => downloadDocument(result.final_analysis, 'analysis-result.md')} 
                    variant="outline" 
                    size="sm"
                  >
                    <Download className="w-4 h-4 mr-2" />
                    下载文档
                  </Button>
                </div>
                <div className="prose max-w-none">
                  <pre className="whitespace-pre-wrap text-sm bg-muted p-4 rounded max-h-[80vh] overflow-auto break-words">
                    {result.final_analysis}
                  </pre>
                </div>
              </Card>
            )}

            {/* 第二个文档：final_md - 问卷 */}
            {result.final_md && (
              <Card className="p-4">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="font-semibold">📄 评估报告与问卷</h3>
                  <Button 
                    onClick={() => downloadDocument(result.final_md, 'questionnaire-report.md')} 
                    variant="outline" 
                    size="sm"
                  >
                    <Download className="w-4 h-4 mr-2" />
                    下载文档
                  </Button>
                </div>
                <div className="prose max-w-none">
                  <pre className="whitespace-pre-wrap text-sm bg-muted p-4 rounded max-h-[80vh] overflow-auto break-words">
                    {result.final_md}
                  </pre>
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function safeJsonParse(text: string): any {
  try {
    return JSON.parse(text)
  } catch {
    return { raw: text }
  }
}