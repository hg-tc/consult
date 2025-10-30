"use client"

import { useEffect, useMemo, useState } from "react"
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
  const [phase, setPhase] = useState<string>('all')
  const [answers, setAnswers] = useState<string>("")
  const [uploadMsg, setUploadMsg] = useState<string>("")
  const [activeStep, setActiveStep] = useState<'1'|'2'|'3'|'all'>('all')
  const [historyKey, setHistoryKey] = useState<string>("")
  const historyList = useMemo(()=>getHistoryList(workspaceId), [workspaceId, result])
  const [reviseInstruction, setReviseInstruction] = useState<string>("")
  const [reviseMsg, setReviseMsg] = useState<string>("")
  const [collapseRefs, setCollapseRefs] = useState<boolean>(false)

  useEffect(()=>{
    setHistoryKey("")
  }, [workspaceId])

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
        phase: phase === 'all' ? undefined : phase,
      }
      const resp = await fetch("/api/apps/questionnaire-builder/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || "生成失败")
      setResult(data)
      saveHistory(workspaceId || 'global', {
        ts: Date.now(),
        companyName,
        targetProjects: projects,
        phase: phase === 'all' ? 'all' : phase,
        result: data,
      })
    } catch (e: any) {
      setError(e.message || "生成失败")
    } finally {
      setLoading(false)
    }
  }

  const uploadAnswers = async () => {
    setUploadMsg("")
    try {
      const resp = await fetch("/api/apps/questionnaire-builder/upload-answers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId || undefined, answers: safeJsonParse(answers || "{}") })
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || "上传失败")
      setUploadMsg("上传成功")
    } catch (e: any) {
      setUploadMsg(e.message || "上传失败")
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

  const loadFromHistory = () => {
    if (!workspaceId || !historyKey) return
    const item = getHistoryItem(workspaceId, historyKey)
    if (item) setResult(item.result)
  }

  const reviseReport = async () => {
    setReviseMsg("")
    try {
      const original = result?.assessment_report_md || ''
      if (!original) {
        setReviseMsg('无可修订的报告')
        return
      }
      const resp = await fetch('/api/apps/questionnaire-builder/revise-report', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ original, instruction: reviseInstruction || '' })
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || '修订失败')
      setResult({ ...result, assessment_report_md: data.revised_report_md })
      setReviseMsg('修订成功')
    } catch (e:any) {
      setReviseMsg(e.message || '修订失败')
    }
  }

  function downloadRequirementsCsv(items: any[]) {
    try {
      const headers = ['id','type','name','applicable_projects_count','source_refs_count']
      const rows = items.map((r:any)=> [
        JSON.stringify(r.id||''),
        JSON.stringify(r.type||''),
        JSON.stringify(r.name||''),
        (Array.isArray(r.applicable_projects)? r.applicable_projects.length: 0),
        (Array.isArray(r.source_refs)? r.source_refs.length: 0),
      ].join(','))
      const csv = [headers.join(','), ...rows].join('\n')
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'normalized_requirements.csv'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {}
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
            <Textarea rows={6} value={targetProjects} onChange={e => setTargetProjects(e.target.value)} placeholder={`示例：
前海人才配租房申请
前海科创企业场地补贴
前海港人创业资助`} />
          </div>
          <div>
            <Label>其他已知信息（可选，JSON）</Label>
            <Textarea rows={6} value={knownInfo} onChange={e => setKnownInfo(e.target.value)} placeholder='{"region":"前海","employees":120,"has_lease":true}' />
            <p className="text-xs text-muted-foreground mt-1">可填主体画像/经营指标/场地/人才/历史记录/意向/现有材料等键值</p>
          </div>
          <div>
            <Label>运行阶段</Label>
            <div className="flex gap-2 text-sm">
              {['all','1','2','3'].map(p => (
                <Button key={p} type="button" variant={phase===p? 'default':'outline'} onClick={()=>{setPhase(p); setActiveStep(p as any)}}>{p==='all'?'全部':`阶段${p}`}</Button>
              ))}
            </div>
          </div>
          <div>
            <Label>历史记录（按工作区）</Label>
            <div className="flex gap-2">
              <select className="border rounded px-2 py-2 text-sm w-full" value={historyKey} onChange={e=>setHistoryKey(e.target.value)}>
                <option value="">选择一条历史记录</option>
                {historyList.map(h => (
                  <option key={h.key} value={h.key}>{new Date(h.ts).toLocaleString()} · {h.companyName || '-'} · {Array.isArray(h.targetProjects)? h.targetProjects.slice(0,2).join('|'): ''} · 阶段{h.phase}</option>
                ))}
              </select>
              <Button type="button" variant="outline" onClick={loadFromHistory}>加载</Button>
            </div>
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
              <div className="flex items-center gap-3 text-sm">
                {([
                  {id:'1', name:'阶段一'},
                  {id:'2', name:'阶段二'},
                  {id:'3', name:'阶段三'},
                ] as const).map(s => (
                  <button key={s.id} className={`px-3 py-1 rounded border ${activeStep===s.id? 'bg-primary text-primary-foreground':'bg-background'}`} onClick={()=>setActiveStep(s.id)}>{s.name}</button>
                ))}
                <div className="opacity-60">当前：{activeStep==='all'?'全部':`阶段${activeStep}`}</div>
              </div>
              {/* 阶段一：大纲与完整文档 */}
              {(result.phase1_outline_md || result.phase1_full_md) && (
                <div>
                  <div className="flex items-center justify-between">
                    <h4 className="font-medium">阶段一 · 条件判断与理解</h4>
                    <div className="flex items-center gap-2 text-xs">
                      <button className="px-2 py-1 border rounded" onClick={()=>setActiveStep('1')}>定位</button>
                    </div>
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    <div>
                      <div className="text-xs text-muted-foreground mb-2">大纲</div>
                      <div className="relative">
                        <pre className="text-xs whitespace-pre-wrap bg-muted p-3 rounded max-h-64 overflow-auto border">{result.phase1_outline_md || ''}</pre>
                        <button className="absolute top-2 right-2 text-xs px-2 py-1 border rounded bg-background" onClick={()=>navigator.clipboard.writeText(result.phase1_outline_md || '')}>复制</button>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground mb-2">完整文档</div>
                      <div className="relative">
                        <pre className="text-xs whitespace-pre-wrap bg-muted p-3 rounded max-h-64 overflow-auto border">{result.phase1_full_md || ''}</pre>
                        <button className="absolute top-2 right-2 text-xs px-2 py-1 border rounded bg-background" onClick={()=>navigator.clipboard.writeText(result.phase1_full_md || '')}>复制</button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
              {Array.isArray(result.normalized_requirements) && result.normalized_requirements.length>0 && (
                <div>
                  <h4 className="font-medium">阶段一 · 规范化要件（部分）</h4>
                  <div className="overflow-auto border rounded">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-muted text-left">
                          <th className="p-2">名称</th>
                          <th className="p-2">类型</th>
                          <th className="p-2">适用项目</th>
                          <th className="p-2">引用数</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.normalized_requirements.slice(0,20).map((r:any, i:number)=> (
                          <tr key={i} className="border-t">
                            <td className="p-2 whitespace-nowrap">{r.name}</td>
                            <td className="p-2">{r.type}</td>
                            <td className="p-2">{(r.applicable_projects||[]).join(',')}</td>
                            <td className="p-2">{(r.source_refs||[]).length}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              {/* 阶段二：主体评估报告 */}
              {result.assessment_report_md && (
                <div>
                  <div className="flex items-center justify-between">
                    <h4 className="font-medium">阶段二 · 主体符合性评估</h4>
                    <div className="text-xs opacity-70">可提交修订</div>
                  </div>
                  <div className="relative">
                    <pre className="text-xs whitespace-pre-wrap bg-muted p-3 rounded max-h-64 overflow-auto border">{result.assessment_report_md}</pre>
                    <button className="absolute top-2 right-2 text-xs px-2 py-1 border rounded bg-background" onClick={()=>navigator.clipboard.writeText(result.assessment_report_md || '')}>复制</button>
                  </div>
                  <div className="mt-2">
                    <Label>报告修订指令（可选）</Label>
                    <Textarea rows={3} value={reviseInstruction} onChange={e=>setReviseInstruction(e.target.value)} placeholder="例如：补充材料清单中的加盖公章要求；优化概览中的统计描述" />
                    <div className="mt-2 flex gap-2 items-center">
                      <Button type="button" variant="secondary" onClick={reviseReport}>提交修订</Button>
                      {reviseMsg && <span className="text-xs text-muted-foreground">{reviseMsg}</span>}
                    </div>
                  </div>
                </div>
              )}
              <div>
                <h4 className="font-medium">成功率（按项目）</h4>
                <div className="text-sm text-muted-foreground">
                  {Object.entries(result.success_rate_by_project || {}).map(([proj, v]: any) => (
                    <div key={proj}>{proj}: {(v as any).range || "-"}</div>
                  ))}
                </div>
              </div>
              {/* 分节卡片：按问卷 section 展示题目 */}
              <div>
                <div className="flex items-center justify-between">
                  <h4 className="font-medium">按分节查看题目</h4>
                  <div className="flex gap-2 text-xs">
                    <Button type="button" variant="outline" onClick={()=>downloadQuestionsJson(result.questionnaire?.questions||[])}>下载题目JSON</Button>
                  </div>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {Object.entries(groupBySection(result.questionnaire?.questions || [])).map(([sec, items]: any) => (
                    <Card key={sec} className="p-3">
                      <div className="font-semibold mb-2">{sec || '未分组'}</div>
                      <ul className="list-disc pl-5 text-sm space-y-1">
                        {(items as any[]).slice(0, 12).map((q: any) => (
                          <li key={q.id} className="truncate" title={q.text}>{q.text}</li>
                        ))}
                      </ul>
                    </Card>
                  ))}
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <h4 className="font-medium">大纲</h4>
                  <div className="text-xs opacity-70">附参考来源脚注</div>
                </div>
                <div className="relative">
                  <pre className="text-xs whitespace-pre-wrap bg-muted p-3 rounded max-h-64 overflow-auto border">{result.outline_markdown || ""}</pre>
                  <button className="absolute top-2 right-2 text-xs px-2 py-1 border rounded bg-background" onClick={()=>navigator.clipboard.writeText(result.outline_markdown || '')}>复制</button>
                </div>
              </div>
              <div>
                <h4 className="font-medium">题目（部分）</h4>
                <pre className="text-xs whitespace-pre-wrap bg-muted p-3 rounded max-h-64 overflow-auto">{JSON.stringify(result.questionnaire?.questions?.slice(0, 10) || [], null, 2)}</pre>
              </div>
              {Array.isArray(result.questionnaire?.required_documents) && result.questionnaire.required_documents.length>0 && (
                <div>
                  <div className="flex items-center justify-between">
                    <h4 className="font-medium">材料清单</h4>
                    <div className="flex gap-2 text-xs">
                      <Button type="button" variant="outline" onClick={()=>downloadMaterialsCsv(result.questionnaire.required_documents||[])}>下载材料CSV</Button>
                    </div>
                  </div>
                  <ul className="list-disc pl-5 text-sm">
                    {(result.questionnaire.required_documents||[]).slice(0,30).map((d:any, i:number)=> (
                      <li key={i}>{d.name} {d.mandatory? '(必需)':''}</li>
                    ))}
                  </ul>
                </div>
              )}
              {Array.isArray(result.questionnaire_items) && result.questionnaire_items.length>0 && (
                <div>
                  <h4 className="font-medium">阶段三 · 问卷（部分）</h4>
                  <div className="text-xs bg-muted p-3 rounded max-h-64 overflow-auto">
                    {Object.entries(groupBySection(result.questionnaire_items)).map(([sec, items]: any)=> (
                      <div key={sec} className="mb-2">
                        <div className="font-semibold">{sec || '未分组'}</div>
                        <ul className="list-disc pl-5">
                          {(items as any[]).slice(0,8).map((it:any)=> (
                            <li key={it.id}>{it.text}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              )}
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
              {/* 逐项引用（可折叠） */}
              <div>
                <div className="flex items-center justify-between">
                  <h4 className="font-medium">逐项引用</h4>
                  <button className="text-xs px-2 py-1 border rounded" onClick={()=>setCollapseRefs(v=>!v)}>{collapseRefs? '展开':'折叠'}</button>
                </div>
                {!collapseRefs && (
                  <div className="text-xs bg-muted p-3 rounded max-h-64 overflow-auto space-y-2">
                    {Object.entries(result.per_item_sources || {}).slice(0, 20).map(([itemId, refs]: any) => (
                      <div key={itemId}>
                        <div className="font-semibold truncate">{itemId}</div>
                        {(refs || []).map((r: any, i: number) => (
                          <div key={i} className="truncate">- {r.source_id} {r.rationale ? `(${r.rationale})` : ''}</div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex flex-col gap-3">
                <div className="flex gap-2">
                  <Button variant="outline" onClick={downloadJson}>下载 JSON</Button>
                  <Button variant="outline" onClick={() => downloadText(result.outline_markdown || '', 'outline.md')}>下载 Markdown</Button>
                </div>
                <div>
                  <Label>上传答卷（JSON 或文本）</Label>
                  <Textarea rows={4} value={answers} onChange={e=>setAnswers(e.target.value)} placeholder='{"q_basic_region":"前海", ...}' />
                  <div className="mt-2 flex gap-2">
                    <Button type="button" variant="secondary" onClick={uploadAnswers}>上传</Button>
                    {uploadMsg && <span className="text-xs text-muted-foreground">{uploadMsg}</span>}
                  </div>
                </div>
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

// 历史：localStorage 基于工作区ID
function saveHistory(workspaceId: string, payload: any) {
  try {
    const key = `qb_history:${workspaceId}`
    const list = JSON.parse(localStorage.getItem(key) || '[]')
    const itemKey = `${payload.ts}`
    const item = { key: itemKey, ...payload }
    const next = [item, ...list].slice(0, 20)
    localStorage.setItem(key, JSON.stringify(next))
  } catch {}
}

function groupBySection(items: any[]) {
  const map: Record<string, any[]> = {}
  for (const it of items || []) {
    const k = it.section || 'default'
    if (!map[k]) map[k] = []
    map[k].push(it)
  }
  return map
}

function downloadQuestionsJson(items: any[]) {
  try {
    const blob = new Blob([JSON.stringify(items || [], null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'questions.json'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch {}
}

function downloadMaterialsCsv(items: any[]) {
  try {
    const headers = ['name','mandatory','applicable_projects_count']
    const rows = (items || []).map((d:any)=> [
      JSON.stringify(d.name||''),
      d.mandatory? '1':'0',
      Array.isArray(d.applicable_projects)? d.applicable_projects.length: 0,
    ].join(','))
    const csv = [headers.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'materials.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch {}
}

function getHistoryList(workspaceId: string) {
  try {
    if (!workspaceId) return [] as any[]
    const key = `qb_history:${workspaceId}`
    return JSON.parse(localStorage.getItem(key) || '[]')
  } catch { return [] as any[] }
}

function getHistoryItem(workspaceId: string, itemKey: string) {
  try {
    if (!workspaceId || !itemKey) return null
    const key = `qb_history:${workspaceId}`
    const list = JSON.parse(localStorage.getItem(key) || '[]')
    return list.find((x: any)=> x.key === itemKey) || null
  } catch { return null }
}


