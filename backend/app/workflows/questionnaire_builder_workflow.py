import os
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool as tool_dec
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_agent
from app.utils.progress_broker import get_progress_broker
import time
import asyncio

import logging
logger = logging.getLogger(__name__)

class QBState(TypedDict):
    request: Dict[str, Any]
    workspace_id: str
    company_name: Optional[str]
    target_projects: List[str]
    known_info: Dict[str, Any]
    # 检索与聚合
    sources: List[Dict[str, Any]]
    tmp_hits: Dict[str, List[Dict[str, Any]]]
    policy_corpus: Dict[str, List[Dict[str, Any]]]
    policy_hits: Dict[str, List[Dict[str, Any]]]
    # 控制
    retry_counters: Dict[str, int]
    needs_more_data: bool
    # ReAct 输出与问卷
    policy: Dict[str, Any]
    network_info: Dict[str, Any]
    assessment_overview: Dict[str, Any]
    assessment_report_md: str
    questionnaire: Dict[str, Any]


class QuestionnaireBuilderWorkflow:
    def __init__(self, workspace_retriever, global_retriever, web_search_service, llm=None):
        logger.info("Initializing QuestionnaireBuilderWorkflow")
        self.workspace_retriever = workspace_retriever
        self.global_retriever = global_retriever
        self.web_search_service = web_search_service
        if llm is None:
            logger.info("No LLM provided")
            api_key = os.getenv('THIRD_PARTY_API_KEY') or os.getenv('OPENAI_API_KEY')
            api_base = os.getenv('THIRD_PARTY_API_BASE') or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
            self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, openai_api_key=api_key, openai_api_base=api_base).with_config({"stream": False})
        else:
            # 统一禁用流式，避免 usage_metadata None 聚合问题
            self.llm = llm.with_config({"stream": False}) if hasattr(llm, "with_config") else llm

        self.graph = self._build_graph()
        self.checkpointer = MemorySaver()
        self.compiled_graph = self.graph.compile(checkpointer=self.checkpointer)

    async def run(self, request: Dict[str, Any], phase: Optional[str] = None) -> Dict[str, Any]:
        initial: QBState = {
            "request": request,
            "workspace_id": (request.get("workspace_id") or "global"),
            "company_name": request.get("company_name"),
            "target_projects": request.get("target_projects", []),
            "known_info": request.get("known_info", {}),
            "policy_hits": {},
            "sources": [],
            "policy_corpus": {"official_docs": [], "case_docs": []},
            "assessment_report_md": "",
            "retry_counters": {},
            "needs_more_data": False,
            "tmp_hits": {},
            "policy": {},
            "network_info": {"queries": [], "results": []},
            "assessment_overview": {},
            "questionnaire": {},
        }
        # LangGraph MemorySaver 需要提供 configurable.thread_id
        thread_id = (
            str(initial.get("workspace_id") or "global")
            + ":"
            + (initial.get("company_name") or "")
            + ":"
            + ("|".join(initial.get("target_projects", [])[:3]))
        ) or str(uuid.uuid4())
        # LangSmith / LangGraph 追踪：设置 run_name、tags 与 metadata 便于按工作流过滤
        config = {
            "run_name": "questionnaire_builder",
            "tags": [
                "workflow:questionnaire_builder",
                f"workspace:{initial.get('workspace_id')}",
                *[f"project:{p}" for p in (initial.get("target_projects") or [])[:5]],
            ],
            "metadata": {
                "company_name": initial.get("company_name") or "",
                "phase": (phase or "all"),
            },
            "configurable": {"thread_id": thread_id},
        }
        result: QBState = await self.compiled_graph.ainvoke(initial, {**config, "recursion_limit": 40, "stream": False})
        response: Dict[str, Any] = {
            "assessment_overview_md": (result.get("assessment_overview") or {}).get("overview_md", ""),
            "questionnaire_md": (result.get("questionnaire") or {}).get("generated_md", ""),
            "policy": result.get("policy", {}),
            "network_info": result.get("network_info", {}),
            "sources": result.get("sources", []),
        }

        # 相位裁剪已移除，直接返回
        return response

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(QBState)

        async def validate_input(state: QBState) -> QBState:
            projects = [p.strip() for p in state["target_projects"] if str(p).strip()]
            if not projects:
                raise ValueError("target_projects 不能为空")
            state["target_projects"] = list(dict.fromkeys(projects))
            return state

        async def collect_client_context(state: QBState) -> QBState:
            # 尝试从工作区文档构建画像（高层摘要，由 LLM 生成）
            profile = state["known_info"].copy()
            # 这里可扩展：从 retriever 搜索 workspace 文档做简述
            state["client_profile"] = profile
            return state

        async def retrieve_internal_db(state: QBState) -> QBState:
            sources: List[Dict[str, Any]] = state["sources"]
            tmp_hits: Dict[str, List[Dict[str, Any]]] = state.get("tmp_hits", {})
            for proj in state["target_projects"]:
                q_variants = [f"{proj} 申请条件", f"{proj} 材料清单", f"{proj} 资格要求", f"{proj} 申报指引"]
                for q in q_variants:
                    results = await self.global_retriever.retrieve(query=q, top_k=5, use_hybrid=True, use_compression=True)
                    for r in results:
                        tmp_hits.setdefault(proj, []).append({"type": "db", **r})
                        src_id = r.get("document_id") or r.get("node_id") or r.get("id")
                        sources.append({"id": f"db::{src_id}", "type": "db", **r})
            state["tmp_hits"] = tmp_hits
            state["sources"] = self._dedupe_sources(sources)
            return state

        async def retrieve_workspace_db(state: QBState) -> QBState:
            sources: List[Dict[str, Any]] = state["sources"]
            tmp_hits: Dict[str, List[Dict[str, Any]]] = state.get("tmp_hits", {})
            for proj in state["target_projects"]:
                q_variants = [f"{proj} 申请条件", f"{proj} 材料清单", f"{proj} 资格要求", f"{proj} 申报指引"]
                for q in q_variants:
                    results = await self.workspace_retriever.retrieve(query=q, top_k=5, use_hybrid=True, use_compression=True)
                    for r in results:
                        tmp_hits.setdefault(proj, []).append({"type": "db", **r})
                        src_id = r.get("document_id") or r.get("node_id") or r.get("id")
                        sources.append({"id": f"db::{src_id}", "type": "db", **r})
            state["tmp_hits"] = tmp_hits
            state["sources"] = self._dedupe_sources(sources)
            return state

        async def web_search_collect(state: QBState) -> QBState:
            """基于公司与 policy 的多轮 ReAct 检索：动态生成查询→检索→校验，累计到 network_info。"""
            broker = get_progress_broker()
            ws = state.get("workspace_id") or "global"
            company = state.get("company_name") or ""
            await broker.publish("questionnaire-builder", ws, {"stage": "web_search_collect", "status": "start", "company_name": company, "ts": time.time()})
            sources: List[Dict[str, Any]] = state["sources"]
            tmp_hits: Dict[str, List[Dict[str, Any]]] = state.get("tmp_hits", {})
            company = state.get("company_name") or ""
            policy_text = (state.get("policy") or {}).get("policy_text", "")

            # 累积容器（闭包可修改）
            state.setdefault("network_info", {}).setdefault("queries", [])
            state.setdefault("network_info", {}).setdefault("results", [])
            queries_acc: List[str] = list(state["network_info"]["queries"])
            aggregated: List[Dict[str, Any]] = list(state["network_info"]["results"])

            # 工具1：生成下一批查询（<=3）
            async def _gen_queries(instruction: str) -> str:
                tpl_text = (
                    "你是检索词生成器。请为‘下一轮’生成3到5条中文查询（每行一条）。\n"
                    "企业：{company}\n政策要点（可截断）：{policy}\n"
                    "规则：\n"
                    "- 优先触达官方来源关键词（通知/指南/实施/细则/zwgk/xxgk）。\n"
                    "- 覆盖企业信息源（企查查/爱企查/启信宝/天眼查 + 企业名）。\n"
                    "- 可使用引号与 site: 约束（示例：\\\"办理流程\\\" site:sz.gov.cn）。\n"
                    "- 聚焦阈值/时间点/材料格式等关键口径；避免与已用查询重复。"
                )
                rendered = tpl_text.format(company=company or "未提供", policy=(policy_text[:1200] or "无"))
                txt = await self.llm.ainvoke(rendered)
                return str(getattr(txt, "content", txt))

            @tool_dec(name="gen_queries", description="生成下一批检索查询（<=3），每行一条，中文")
            async def gen_queries(instruction: str) -> str:
                return await _gen_queries(instruction)

            # 工具2：执行单条检索并累计结果
            async def _web_search_once(q: str) -> str:
                q = (q or "").strip()
                if not q:
                    return "空查询"
                queries_acc.append(q)
                async with self.web_search_service as ws:
                    web = await ws.search_web(q, num_results=6)
                added = 0
                for w in web:
                    entry = {"title": w.title, "url": w.url, "snippet": w.snippet, "source_type": getattr(w, 'source_type', 'web'), "query": q}
                    # 去重（按 URL）
                    if not any(e.get("url") == entry["url"] for e in aggregated):
                        aggregated.append(entry)
                        tmp_hits.setdefault("web", []).append({"type": "web", **entry})
                        sources.append({"id": f"web::{w.url}", "type": "web", **entry})
                        added += 1
                return f"added={added}"

            @tool_dec(name="web_search", description="对给定中文查询执行一次互联网检索并累计结果，返回新增条数")
            async def web_search(q: str) -> str:
                return await _web_search_once(q)

            # 工具3：在本地累计结果中检索（验证/补洞）
            async def _lookup_local(query: str) -> str:
                q = (query or "").lower()
                lines: List[str] = []
                for e in aggregated[:300]:
                    blob = f"{e.get('title','')}\n{e.get('snippet','')}\n{e.get('url','')}".lower()
                    if all(k.strip() in blob for k in q.split() if k.strip()):
                        lines.append(f"- {e.get('title','来源')} | {e.get('url','')}\n  {e.get('snippet','')[:220]}")
                        if len(lines) >= 10:
                            break
                return "\n".join(lines) or "无匹配片段"

            @tool_dec(name="lookup_local", description="在已累计的结果集中按关键词检索匹配片段，帮助验证覆盖情况")
            async def lookup_local(query: str) -> str:
                return await _lookup_local(query)

            # ReAct 提示（1.0.2）：使用 messages_modifier（system + {messages} 占位）
            loop_system = (
                "多轮检索任务：为企业（{company}）基于政策要点进行覆盖式检索。\n"
                "目标覆盖：官方来源、企业信息侧关键要点、条件/门槛/材料/流程/时间等关键口径。\n"
                "流程：每轮先调用 gen_queries 生成≤3条，再对每条用 web_search 检索；必要时用 lookup_local 验证。\n"
                "终止：覆盖充分且最近一轮无新增时输出 ‘OK’ 作为 Final Answer。仅输出动作/OK，不输出总结。"
            )
            loop_messages = ChatPromptTemplate.from_messages([
                ("system", loop_system.format(company=company or "未提供")),
                ("placeholder", "{messages}")
            ])

            loop_agent = create_agent(
                model=self.llm,
                tools=[gen_queries, web_search, lookup_local],
                prompt=loop_messages,
            )
            # 直接调用 agent（非流式）
            await loop_agent.ainvoke({
                "messages": [{"role": "user", "content": "开始执行覆盖式检索，按流程进行。"}]
            }, config={"stream": False})

            # 写回去重后的 queries / results
            # 去重 queries（保序）
            seen_q = set()
            dedup_q = []
            for q in queries_acc:
                if q not in seen_q:
                    seen_q.add(q)
                    dedup_q.append(q)
            state["network_info"]["queries"] = dedup_q
            # 去重 results（按 URL 保序）
            seen_u = set()
            dedup_res = []
            for e in aggregated:
                u = e.get("url")
                if u and u not in seen_u:
                    seen_u.add(u)
                    dedup_res.append(e)
            state["network_info"]["results"] = dedup_res

            # 递增重试计数
            rc = state.get("retry_counters", {})
            rc["web_search"] = rc.get("web_search", 0) + 1
            state["retry_counters"] = rc
            state["tmp_hits"] = tmp_hits
            state["sources"] = self._dedupe_sources(sources)
            await broker.publish("questionnaire-builder", ws, {"stage": "web_search_collect", "status": "end", "company_name": company, "ts": time.time()})
            return state

        async def triage_and_filter(state: QBState) -> QBState:
            # 将 tmp_hits 归并为 policy_hits，同步生成官方/案例集合
            broker = get_progress_broker()
            ws = state.get("workspace_id") or "global"
            company = state.get("company_name") or ""
            await broker.publish("questionnaire-builder", ws, {"stage": "triage_and_filter", "status": "start", "company_name": company, "ts": time.time()})
            tmp_hits: Dict[str, List[Dict[str, Any]]] = state.get("tmp_hits", {})
            hits: Dict[str, List[Dict[str, Any]]] = {}
            official_docs: List[Dict[str, Any]] = []
            case_docs: List[Dict[str, Any]] = []
            needs_more = False
            for proj, items in tmp_hits.items():
                proj_hits: List[Dict[str, Any]] = []
                official = []
                cases = []
                for h in items:
                    title = (h.get("title") or h.get("text") or "").lower()
                    url = (h.get("url") or "").lower()
                    is_official = (
                        any(k in title for k in ["通知", "指引", "实施", "细则", "办事", "指南"]) or
                        any(k in url for k in ["gov.cn", ".gov.cn", "gov.hk", "qh.gov", "sz.gov.cn"]) or
                        any(k in title for k in ["管理局", "印发", "办法", "规定"]) or
                        any(k in url for k in ["/zwgk/", "/xxgk/"])
                    ) and not any(b in url for b in ["baike.baidu.com", "baike.so.com"]) and not any(b in title for b in ["百科", "新闻", "解读"])
                    is_noise = any(b in url for b in ["baike.baidu.com", "zhihu.com", "sohu.com/news", "toutiao", "weibo.com"]) and not is_official
                    if is_noise:
                        continue
                    proj_hits.append(h)
                    if is_official:
                        official.append(h)
                    else:
                        cases.append(h)
                hits[proj] = proj_hits
                official_docs += official
                case_docs += cases
                # 简单信号：若官方来源过少则需要更多数据
                if len(official) < 3:
                    needs_more = True
            state["policy_hits"] = hits
            state["policy_corpus"]["official_docs"] += official_docs
            state["policy_corpus"]["case_docs"] += case_docs
            # 是否继续循环 Web 搜索（最多 2 次）
            retries = state.get("retry_counters", {}).get("web_search", 0)
            state["needs_more_data"] = needs_more and retries < 2
            await broker.publish("questionnaire-builder", ws, {"stage": "triage_and_filter", "status": "end", "company_name": company, "ts": time.time()})
            return state

        # 文档生成 Agent：基于 policy + network_info 评估申请概况
        async def doc_assessment_agent(state: QBState) -> QBState:
            broker = get_progress_broker()
            ws = state.get("workspace_id") or "global"
            company = state.get("company_name") or ""
            await broker.publish("questionnaire-builder", ws, {"stage": "doc_assessment", "status": "start", "company_name": company, "ts": time.time()})
            policy_text = (state.get("policy") or {}).get("policy_text", "")
            results: List[Dict[str, Any]] = (state.get("network_info") or {}).get("results", [])

            # 本地查找工具：在抓取结果中查证条件相关线索
            async def _lookup_local(q: str) -> str:
                ql = (q or "").lower()
                lines: List[str] = []
                for e in results[:400]:
                    blob = f"{e.get('title','')}\n{e.get('snippet','')}\n{e.get('url','')}".lower()
                    if all(k.strip() in blob for k in ql.split() if k.strip()):
                        lines.append(f"- {e.get('title','来源')} | {e.get('url','')}\n  {e.get('snippet','')[:240]}")
                        if len(lines) >= 12:
                            break
                return "\n".join(lines) or "无匹配片段"

            @tool_dec(name="lookup_local", description="在已抓取结果中按关键词检索相关片段（用于验证条件是否满足）")
            async def lookup_tool(q: str) -> str:
                return await _lookup_local(q)

            assess_system = (
                "你是政策申报评估助手。请基于“政策要点”与已抓取的网络结果，生成一份完整且详尽的中文 Markdown 报告，用于评估申请概况。\n\n"
                "报告必须包含并按以下结构输出（仅输出报告，不展示思考过程）：\n"
                "# 申请概况总览\n- 企业：{company}\n- 评估范围：目标项目与相关政策\n- 一句话总体判断（是否具备申报潜力及风险级别）\n\n"
                "# 需要满足的条件（分类清单）\n- 将条件按 类别/门槛/材料/流程/时间 等分类分条列出，尽量来源于政策要点\n\n"
                "# 已满足的条件与证据\n- 对每条已满足条件，给出证据要点（可引用 lookup_local 返回的片段摘要），标注来源链接\n\n"
                "# 未满足的条件\n- 分条列出当前不满足的条件及其差距说明\n\n"
                "# 未知/待补充信息\n- 分条列出需要补充核实的信息点（将用于后续问卷）\n\n"
                "# 官方来源与参考\n- 汇总可识别的官方来源条目（标题 + 链接）\n\n"
                "# 建议与后续行动\n- 给出下一步补证/优化建议、优先级、可行动检查项\n\n"
                "输入背景：\n企业：{company}\n政策要点（可截断）：{policy}\n\n"
                "可用工具：\n{tools}\n工具名称：{tool_names}"
            )
            assess_messages = ChatPromptTemplate.from_messages([
                ("system", assess_system.format(company=company or "未提供", policy=(policy_text[:1500] or "无"))),
                ("placeholder", "{messages}")
            ])

            agent = create_agent(
                model=self.llm,
                tools=[lookup_tool],
                prompt=assess_messages,
            )
            res_msg = await agent.ainvoke({
                "messages": [{"role": "user", "content": "依据上述要求产出完整评估报告。"}]
            }, config={"stream": False})
            output = getattr(res_msg, "content", "") or ""
            state["assessment_overview"] = {"overview_md": output}
            # 同步便于外部读取
            state["assessment_report_md"] = output or state.get("assessment_report_md", "")
            await broker.publish("questionnaire-builder", ws, {"stage": "doc_assessment", "status": "end", "company_name": company, "ts": time.time()})
            return state

        async def questionnaire_from_assessment(state: QBState) -> QBState:
            """基于评估概况与未知要点生成调查问卷（Markdown），使用离线模板。"""
            broker = get_progress_broker()
            ws = state.get("workspace_id") or "global"
            company = state.get("company_name") or ""
            await broker.publish("questionnaire-builder", ws, {"stage": "questionnaire", "status": "start", "company_name": company, "ts": time.time()})
            try:
                from pathlib import Path
                prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "assessment_to_questionnaire.md"
                with open(prompt_path, "r", encoding="utf-8") as f:
                    tpl_text = f.read()
            except Exception:
                tpl_text = (
                    "你是一名政策申报问卷设计专家。请根据评估概况生成问卷（Markdown）。\n"
                    "企业：{company}\n项目：{projects}\n\n评估：\n{assessment_overview_md}"
                )

            company = state.get("company_name") or ""
            projects = ", ".join(state.get("target_projects") or [])
            overview_md = (state.get("assessment_overview") or {}).get("overview_md", "")

            # 默认：优先使用 LangChain Hub 在线 Prompt（质量更高），失败时回退到离线模板
            use_hub = os.getenv("USE_LC_HUB", "true").lower() in {"1", "true", "yes", "on"}
            hub_prompt_name = os.getenv("LANGCHAIN_HUB_PROMPT", "rlm/questionnaire-generator")
            rendered = None
            if use_hub:
                try:
                    from langchain import hub
                    hp = hub.pull(hub_prompt_name)
                    # 尝试格式化（不同 Hub 资产可能有不同接口，这里做兜底）
                    try:
                        rendered = hp.format(company=company or "未提供", projects=projects or "未指定", assessment_overview_md=overview_md or "")
                    except Exception:
                        rendered = await hp.ainvoke({
                            "company": company or "未提供",
                            "projects": projects or "未指定",
                            "assessment_overview_md": overview_md or "",
                        })
                except Exception:
                    rendered = None

            if rendered is None:
                try:
                    rendered = tpl_text.format(
                        company=company or "未提供",
                        projects=projects or "未指定",
                        assessment_overview_md=overview_md or "",
                    )
                except Exception:
                    rendered = f"企业：{company or '未提供'}\n项目：{projects or '未指定'}\n\n评估：\n{overview_md or ''}"
            resp = await self.llm.ainvoke(rendered)
            questionnaire_md = str(getattr(resp, "content", resp))
            state.setdefault("questionnaire", {})
            state["questionnaire"]["generated_md"] = questionnaire_md
            # 同步便于 API 返回
            state["questionnaire_outline"] = state.get("questionnaire_outline") or {}
            state["phase1_outline_md"] = state.get("phase1_outline_md", "")
            await broker.publish("questionnaire-builder", ws, {"stage": "questionnaire", "status": "end", "company_name": company, "ts": time.time()})
            return state

        # 已移除未使用节点：resolve_company_open_data 等


        # ============== ReAct 节点：面向条件的长文描述（基于全局/工作区检索迭代完善） ==============
        async def react_requirements_synthesis(state: QBState) -> QBState:
            broker = get_progress_broker()
            ws = state.get("workspace_id") or "global"
            company = state.get("company_name") or ""
            await broker.publish("questionnaire-builder", ws, {"stage": "react_requirements_synthesis", "status": "start", "company_name": company, "ts": time.time()})
            # 工具：统一封装全局与工作区检索
            async def _db_search_tool(query: str) -> str:
                snippets: List[str] = []
                # 全局检索
                try:
                    g_results = await self.global_retriever.retrieve(query=query, top_k=6, use_hybrid=True, use_compression=True)
                    for r in g_results:
                        title = r.get("title") or r.get("name") or r.get("document_id") or "片段"
                        text = r.get("text") or r.get("content") or ""
                        snippets.append(f"[GLOBAL] {title}: {text[:300]}")
                except Exception:
                    pass
                # 工作区检索
                try:
                    w_results = await self.workspace_retriever.retrieve(query=query, top_k=6, use_hybrid=True, use_compression=True)
                    for r in w_results:
                        title = r.get("title") or r.get("name") or r.get("document_id") or "片段"
                        text = r.get("text") or r.get("content") or ""
                        snippets.append(f"[WORKSPACE] {title}: {text[:300]}")
                except Exception:
                    pass
                return "\n".join(snippets[:12]) or "未找到有效片段"

            # LangChain 工具（异步）
            @tool_dec(name="db_search", description="查询全局与工作区数据库以获取与项目要求/条件相关的片段，输入中文查询，输出若干要点片段")
            async def db_tool(q: str) -> str:
                return await _db_search_tool(q)

            # ReAct 提示词
            tp = ", ".join(state.get("target_projects") or [])
            known = state.get("known_info") or {}
            known_blob = "\n".join([f"- {k}: {v}" for k, v in list(known.items())[:12]])
            react_template = (
                "你是中国政策与补贴申报顾问。用户希望申请以下项目：{target_projects}\n"
                "已知信息（可能不完整）：\n{known_info}\n\n"
                "请采用 ReAct（Reason+Act）多轮检索与核对，仅在需要时调用工具。目标：输出面向实操的“申报条件综述”。\n"
                "执行要点：\n"
                "- 列出待确认类别：资格/门槛（含数值/阈值）/材料/流程/时间/例外情形。\n"
                "- 分类别逐轮补齐要点：优先引用明确口径、阈值与出处。\n"
                "- 对地域/规模/时段等差异情形，明确分支与条件。\n"
                "- 注意区分官方来源与一般解读。\n\n"
                "可用工具：\n{tools}\n工具名称：{tool_names}\n\n"
                "问题：{input}\n\n"
                "{agent_scratchpad}"
            )
            react_system = react_template.format(
                target_projects=tp or "未指定",
                known_info=known_blob or "无",
                tools="{tools}",  # 由 prebuilt 注入
                tool_names="{tool_names}",
                input="{input}",
                agent_scratchpad="{agent_scratchpad}",
            )
            react_messages = ChatPromptTemplate.from_messages([
                ("system", react_system),
                ("placeholder", "{messages}")
            ])

            agent = create_agent(
                model=self.llm,
                tools=[db_tool],
                prompt=react_messages,
            )

            res_msg = await agent.ainvoke({
                "messages": [{"role": "user", "content": "根据这些项目生成条件要求总览。"}]
            }, config={"stream": False})
            output_text = getattr(res_msg, "content", "") or ""
            if output_text:
                # 不生成 markdown，写入 policy，供后续节点使用
                state["policy"] = {
                    "policy_text": output_text,
                    "projects": state.get("target_projects", []),
                }
            await broker.publish("questionnaire-builder", ws, {"stage": "react_requirements_synthesis", "status": "end", "company_name": company, "ts": time.time()})
            return state


        graph.set_entry_point("validate_input")
        # 注册在用节点（确保均已添加）
        graph.add_node("validate_input", validate_input)
        graph.add_node("react_requirements_synthesis", react_requirements_synthesis)
        graph.add_node("web_search_collect", web_search_collect)
        graph.add_node("triage_and_filter", triage_and_filter)
        graph.add_node("doc_assessment_agent", doc_assessment_agent)
        graph.add_node("questionnaire_from_assessment", questionnaire_from_assessment)
        
        # ReAct 路径：校验 → 条件综合（policy）→ 基于 policy+公司信息生成检索词并检索
        graph.add_edge("validate_input", "react_requirements_synthesis")
        graph.add_edge("react_requirements_synthesis", "web_search_collect")
        # 检索后可回到 triage_and_filter 进入后续链路，或直接 finalize（此处接入原管线）
        graph.add_edge("web_search_collect", "triage_and_filter")

        # 条件边：需要更多数据则进入 Web 搜索节点，否则进入后续流程
        graph.add_conditional_edges(
            "triage_and_filter",
            lambda s: "web" if s.get("needs_more_data") else "next",
            {"web": "web_search_collect", "next": "doc_assessment_agent"}
        )
        
        graph.add_edge("doc_assessment_agent", "questionnaire_from_assessment")
        graph.add_edge("questionnaire_from_assessment", END)


        return graph

    @staticmethod
    def _dedupe_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        deduped = []
        for s in sources:
            key = s.get("id") or s.get("url") or s.get("document_id") or s.get("node_id")
            if key and key not in seen:
                seen.add(key)
                deduped.append(s)
        return deduped


