"use client"

import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Loader2, FileText, Download, ArrowLeft } from 'lucide-react'
import { useRouter } from 'next/navigation'

export default function QuestionnaireBuilderPage() {
  const router = useRouter()
  const [workspaceId, setWorkspaceId] = useState<string>("")
  const [companyName, setCompanyName] = useState<string>("")
  const [targetProjects, setTargetProjects] = useState<string>("")
  const [knownInfo, setKnownInfo] = useState<string>("")

  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  const handleGenerate = async () => {
    setError(null)
    setResult(null)
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
      const payload = {
        workspace_id: workspaceId || undefined,
        company_name: companyName || undefined,
        target_projects: projects,
        known_info: knownInfo ? safeJsonParse(knownInfo) : undefined,
      }
      const resp = await fetch("/api/apps/questionnaire-builder/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || "生成失败")
      setResult(data)
    } catch (e: any) {
      setError(e.message || "生成失败")
    } finally {
      setLoading(false)
    }
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
            <div className="flex items-center gap-2 mb-2">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
              <span className="font-medium">正在生成...</span>
            </div>
            <p className="text-sm text-muted-foreground">
              这可能需要几分钟时间，请耐心等待
            </p>
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