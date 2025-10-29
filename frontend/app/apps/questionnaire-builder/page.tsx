"use client"

import { useState } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Loader2, FileText } from "lucide-react"

interface SourceRef { source_id: string; rationale?: string }

export default function QuestionnaireBuilderPage() {
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

  const downloadJson = () => {
    if (!result) return
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "questionnaire.json"
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div className="mb-6 max-w-5xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">问卷生成</h1>
        <p className="text-muted-foreground">
          根据申请项目与客户画像，结合内部与互联网公开信息，生成政策问卷与材料清单（附引用）
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2 max-w-5xl mx-auto">
        <Card className="p-6 space-y-4">
          <div>
            <Label>工作区（可选）</Label>
            <Input value={workspaceId} onChange={e => setWorkspaceId(e.target.value)} placeholder="如：global 或具体工作区ID" />
          </div>
          <div>
            <Label>公司名称/统一社会信用代码（可选）</Label>
            <Input value={companyName} onChange={e => setCompanyName(e.target.value)} placeholder="用于抓取公开信息" />
          </div>
          <div>
            <Label>申请项目（必填，每行一个）</Label>
            <Textarea rows={6} value={targetProjects} onChange={e => setTargetProjects(e.target.value)} placeholder={`示例：\n前海人才配租房申请\n前海科创企业场地补贴\n前海港人创业资助`} />
          </div>
          <div>
            <Label>其他已知信息（可选，JSON）</Label>
            <Textarea rows={6} value={knownInfo} onChange={e => setKnownInfo(e.target.value)} placeholder='{"region":"前海","employees":120,"has_lease":true}' />
            <p className="text-xs text-muted-foreground mt-1">可填主体画像/经营指标/场地/人才/历史记录/意向/现有材料等键值</p>
          </div>
          <Button onClick={handleGenerate} disabled={loading} className="w-full">
            {loading ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 生成中...</>) : (<><FileText className="w-4 h-4 mr-2" /> 生成问卷</>)}
          </Button>
          {error && <div className="text-sm text-destructive">{error}</div>}
        </Card>

        <Card className="p-6">
          <h3 className="font-semibold mb-3">结果预览</h3>
          {!result ? (
            <p className="text-sm text-muted-foreground">填写左侧表单并点击“生成问卷”</p>
          ) : (
            <div className="space-y-3">
              <div>
                <h4 className="font-medium">成功率（按项目）</h4>
                <div className="text-sm text-muted-foreground">
                  {Object.entries(result.success_rate_by_project || {}).map(([proj, v]: any) => (
                    <div key={proj}>{proj}: {(v as any).range || "-"}</div>
                  ))}
                </div>
              </div>
              {/* 按项目查看相关题目与材料（示例渲染前 3 项） */}
              <div>
                <h4 className="font-medium">按项目查看（示例）</h4>
                <div className="space-y-3">
                  {(result.questionnaire?.target_projects || []).slice(0, 3).map((proj: string) => (
                    <Card key={proj} className="p-3">
                      <div className="font-semibold mb-2">{proj}</div>
                      <div className="text-xs text-muted-foreground mb-2">相关题目（示例最多10条）：</div>
                      <ul className="list-disc pl-5 text-sm space-y-1">
                        {(result.questionnaire?.questions || [])
                          .filter((q: any) => !q.applicable_projects || q.applicable_projects.includes(proj))
                          .slice(0, 10)
                          .map((q: any) => (
                            <li key={q.id} className="truncate" title={q.text}>{q.text}</li>
                          ))}
                      </ul>
                      <div className="text-xs text-muted-foreground mt-3">所需材料（示例）：</div>
                      <ul className="list-disc pl-5 text-sm">
                        {(result.questionnaire?.required_documents || [])
                          .filter((d: any) => !d.applicable_projects || (d.applicable_projects || []).includes(proj))
                          .slice(0, 5)
                          .map((d: any, i: number) => (
                            <li key={i}>{d.name} {d.mandatory ? '(必需)' : ''}</li>
                          ))}
                      </ul>
                    </Card>
                  ))}
                </div>
              </div>
              <div>
                <h4 className="font-medium">大纲</h4>
                <pre className="text-xs whitespace-pre-wrap bg-muted p-3 rounded max-h-64 overflow-auto">{result.outline_markdown || ""}</pre>
              </div>
              <div>
                <h4 className="font-medium">题目（部分）</h4>
                <pre className="text-xs whitespace-pre-wrap bg-muted p-3 rounded max-h-64 overflow-auto">{JSON.stringify(result.questionnaire?.questions?.slice(0, 10) || [], null, 2)}</pre>
              </div>
              {/* 引用展示 */}
              <div>
                <h4 className="font-medium">引用来源（合并去重）</h4>
                <div className="text-xs bg-muted p-3 rounded max-h-64 overflow-auto space-y-1">
                  {(result.sources || []).map((s: any, idx: number) => (
                    <div key={idx} className="truncate" title={s.url || s.original_path || ''}>
                      [{idx + 1}] {(s.title || s.file_name || s.doc_id || '来源')} {(s.domain ? `(${s.domain})` : '')} {(s.url || s.original_path || '')}
                    </div>
                  ))}
                </div>
              </div>
              {/* 逐题引用（示例显示前10个条目） */}
              <div>
                <h4 className="font-medium">逐项引用（示例）</h4>
                <div className="text-xs bg-muted p-3 rounded max-h-64 overflow-auto space-y-2">
                  {Object.entries(result.per_item_sources || {}).slice(0, 10).map(([itemId, refs]: any) => (
                    <div key={itemId}>
                      <div className="font-semibold truncate">{itemId}</div>
                      {(refs || []).map((r: any, i: number) => (
                        <div key={i} className="truncate">- {r.source_id} {r.rationale ? `(${r.rationale})` : ''}</div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={downloadJson}>下载 JSON</Button>
                <Button variant="outline" onClick={() => downloadText(result.outline_markdown || '', 'outline.md')}>下载 Markdown</Button>
              </div>
            </div>
          )}
        </Card>
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

function downloadText(text: string, filename: string) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}


