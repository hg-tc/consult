import os
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

class QBState(TypedDict):
    request: Dict[str, Any]
    workspace_id: str
    company_name: Optional[str]
    target_projects: List[str]
    known_info: Dict[str, Any]

    client_profile: Dict[str, Any]
    policy_hits: Dict[str, List[Dict[str, Any]]]
    company_open_data: Dict[str, Any]
    criteria: List[Dict[str, Any]]
    gaps: List[Dict[str, Any]]
    outline: Dict[str, Any]
    questions: List[Dict[str, Any]]
    rules: List[Dict[str, Any]]
    scoring: Dict[str, Any]
    required_documents: List[Dict[str, Any]]
    success_rate_by_project: Dict[str, Any]
    sources: List[Dict[str, Any]]
    per_item_sources: Dict[str, List[Dict[str, Any]]]
    # Phase 1 additions
    policy_corpus: Dict[str, List[Dict[str, Any]]]
    normalized_requirements: List[Dict[str, Any]]
    phase1_outline_md: str
    phase1_full_md: str
    # Phase 2 additions
    applicant_findings: Dict[str, Any]
    assessment_report_md: str
    # Phase 3 additions
    questionnaire_outline: Dict[str, Any]
    questionnaire_sections: List[Dict[str, Any]]
    questionnaire_items: List[Dict[str, Any]]


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
            self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, openai_api_key=api_key, openai_api_base=api_base)
        else:
            self.llm = llm

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
            "client_profile": {},
            "policy_hits": {},
            "company_open_data": {},
            "criteria": [],
            "gaps": [],
            "outline": {},
            "questions": [],
            "rules": [],
            "scoring": {},
            "required_documents": [],
            "success_rate_by_project": {},
            "sources": [],
            "per_item_sources": {},
            # Phase 1 defaults
            "policy_corpus": {"official_docs": [], "case_docs": []},
            "normalized_requirements": [],
            "phase1_outline_md": "",
            "phase1_full_md": "",
            # Phase 2 defaults
            "applicant_findings": {"facts": [], "matches": []},
            "assessment_report_md": "",
            # Phase 3 defaults
            "questionnaire_outline": {},
            "questionnaire_sections": [],
            "questionnaire_items": [],
        }
        # LangGraph MemorySaver 需要提供 configurable.thread_id
        thread_id = (
            str(initial.get("workspace_id") or "global")
            + ":"
            + (initial.get("company_name") or "")
            + ":"
            + ("|".join(initial.get("target_projects", [])[:3]))
        ) or str(uuid.uuid4())
        result: QBState = await self.compiled_graph.ainvoke(
            initial,
            {"configurable": {"thread_id": thread_id}}
        )
        # 生成带引用尾注的 Markdown（简单脚注样式）
        outline_md = result["outline"].get("markdown", "")
        if result.get("sources"):
            footers: List[str] = ["\n\n---\n\n参考来源：\n"]
            for idx, s in enumerate(result["sources"], start=1):
                title = s.get("title") or s.get("file_name") or s.get("doc_id") or "来源"
                url = s.get("url") or s.get("original_path") or s.get("path") or ""
                domain = s.get("domain") or ""
                footers.append(f"[{idx}] {title} {('(' + domain + ')') if domain else ''} {url}")
            outline_md = outline_md + "\n" + "\n".join(footers)

        response: Dict[str, Any] = {
            "questionnaire": {
                "target_projects": result["target_projects"],
                "outline": result["outline"],
                "sections": result["outline"].get("sections", []),
                "questions": result["questions"],
                "rules": result["rules"],
                "required_documents": result["required_documents"],
                "scoring": result["scoring"],
            },
            "outline_markdown": outline_md,
            "success_rate_by_project": result["success_rate_by_project"],
            "risk_notes": result.get("gaps", []),
            "sources": result["sources"],
            "per_item_sources": result["per_item_sources"],
            # Phase extras
            "phase1_outline_md": result.get("phase1_outline_md", ""),
            "phase1_full_md": result.get("phase1_full_md", ""),
            "normalized_requirements": result.get("normalized_requirements", []),
            "assessment_report_md": result.get("assessment_report_md", ""),
            "questionnaire_outline": result.get("questionnaire_outline", {}),
            "questionnaire_items": result.get("questionnaire_items", []),
        }

        if phase == "1":
            keys = [
                "phase1_outline_md",
                "phase1_full_md",
                "normalized_requirements",
                "sources",
                "per_item_sources",
            ]
            return {k: response[k] for k in keys}
        if phase == "2":
            keys = [
                "assessment_report_md",
                "normalized_requirements",
                "sources",
                "per_item_sources",
            ]
            return {k: response[k] for k in keys}
        if phase == "3":
            keys = [
                "questionnaire_outline",
                "questionnaire_items",
                "sources",
                "per_item_sources",
            ]
            return {k: response[k] for k in keys}
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

        async def retrieve_policy_and_cases(state: QBState) -> QBState:
            sources: List[Dict[str, Any]] = state["sources"]
            hits: Dict[str, List[Dict[str, Any]]] = {}
            for proj in state["target_projects"]:
                q_variants = [
                    f"{proj} 申请条件", f"{proj} 材料清单", f"{proj} 资格要求", f"{proj} 申报指引"
                ]
                proj_hits: List[Dict[str, Any]] = []
                # 内部检索（全局）
                for q in q_variants:
                    results = await self.global_retriever.retrieve(query=q, top_k=5, use_hybrid=True, use_compression=True)
                    for r in results:
                        proj_hits.append({"type": "db", **r})
                        src_id = r.get("document_id") or r.get("node_id") or r.get("id")
                        sources.append({"id": f"db::{src_id}", "type": "db", **r})
                # 工作区检索
                for q in q_variants:
                    results = await self.workspace_retriever.retrieve(query=q, top_k=5, use_hybrid=True, use_compression=True)
                    for r in results:
                        proj_hits.append({"type": "db", **r})
                        src_id = r.get("document_id") or r.get("node_id") or r.get("id")
                        sources.append({"id": f"db::{src_id}", "type": "db", **r})
                # 互联网检索
                for q in q_variants:
                    # 使用上下文管理器确保会话建立
                    async with self.web_search_service as ws:
                        web = await ws.search_web(q, num_results=5)
                    for w in web:
                        entry = {"title": w.title, "url": w.url, "snippet": w.snippet, "source_type": getattr(w, 'source_type', 'web')}
                        proj_hits.append({"type": "web", **entry})
                        sources.append({"id": f"web::{w.url}", "type": "web", **entry})
                # 粗分官方/案例，并过滤低相关来源
                official = []
                cases = []
                for h in proj_hits:
                    title = (h.get("title") or h.get("text") or "").lower()
                    url = (h.get("url") or "").lower()
                    # 简单降噪：忽略百科/泛资讯在官方集合
                    is_official = (
                        any(k in title for k in ["通知", "指引", "实施", "细则", "办事", "指南"]) or
                        any(k in url for k in ["gov.cn", ".gov.cn", "gov.hk", "qh.gov", "sz.gov.cn"]) or
                        any(k in title for k in ["管理局", "印发", "办法", "规定"]) or
                        any(k in url for k in ["/zwgk/", "/xxgk/"])
                    ) and not any(b in url for b in ["baike.baidu.com", "baike.so.com"]) and not any(b in title for b in ["百科", "新闻", "解读"])

                    is_noise = any(b in url for b in ["baike.baidu.com", "zhihu.com", "sohu.com/news", "toutiao", "weibo.com"]) and not is_official

                    if is_noise:
                        continue

                    if is_official:
                        official.append(h)
                    else:
                        cases.append(h)
                hits[proj] = proj_hits
                state["policy_corpus"]["official_docs"] += official
                state["policy_corpus"]["case_docs"] += cases
            # 去重
            state["policy_hits"] = hits
            state["sources"] = self._dedupe_sources(sources)
            return state

        async def resolve_company_open_data(state: QBState) -> QBState:
            company = state.get("company_name")
            if not company:
                return state
            async with self.web_search_service as ws:
                web = await ws.search_web(f"{company} 公司 经营 范围 注册 资本 人员 规模", num_results=8)
            state["company_open_data"] = {"raw": [{"title": w.title, "url": w.url, "snippet": w.snippet} for w in web]}
            # 索引引用
            sources = state["sources"]
            for w in web:
                sources.append({"id": f"web::{w.url}", "type": "web", "title": w.title, "url": w.url, "snippet": w.snippet})
            state["sources"] = self._dedupe_sources(sources)
            return state

        async def normalize_criteria(state: QBState) -> QBState:
            # 这里简化：将命中的片段粗略映射为条件/材料条目，由 LLM 后续细化
            criteria: List[Dict[str, Any]] = []
            per_item_sources: Dict[str, List[Dict[str, Any]]] = {}
            for proj, items in state["policy_hits"].items():
                for idx, it in enumerate(items):
                    crit_id = f"{proj}::hit::{idx}"
                    criteria.append({
                        "id": crit_id,
                        "name": it.get("title") or it.get("text", "条件/材料"),
                        "type": "text",
                        "applicable_projects": [proj],
                    })
                    per_item_sources[crit_id] = [{"source_id": (it.get("id") or it.get("url") or crit_id)}]
            state["criteria"] = criteria
            # 合并引用
            state["per_item_sources"].update(per_item_sources)
            # 由 criteria 精简生成 normalized_requirements（占位）
            normalized: List[Dict[str, Any]] = []
            for c in criteria:
                normalized.append({
                    "id": c["id"],
                    "type": "condition",
                    "name": c.get("name", "条件/材料"),
                    "description": c.get("name", ""),
                    "applicable_projects": c.get("applicable_projects", []),
                    "source_refs": state["per_item_sources"].get(c["id"], []),
                })
            state["normalized_requirements"] = normalized
            return state

        async def phase1_outline_first(state: QBState) -> QBState:
            sections = [
                {"id": "scope", "title": "适用范围与对象"},
                {"id": "eligibility", "title": "资格条件（硬性/加分）"},
                {"id": "thresholds", "title": "门槛与阈值（地域/规模/时段等）"},
                {"id": "materials", "title": "材料清单与格式要求"},
                {"id": "process", "title": "办理流程与时间节点"},
                {"id": "variants", "title": "不同情形与常见变体"},
                {"id": "policies", "title": "政策依据与版本"},
            ]
            md = (
                "# 申报条件判断与理解（大纲）\n"
                "- 适用范围与对象\n"
                "- 资格条件（硬性/加分）\n"
                "- 门槛与阈值（地域/规模/时段等）\n"
                "- 材料清单与格式要求\n"
                "- 办理流程与时间节点\n"
                "- 不同情形与常见变体\n"
                "- 政策依据与版本"
            )
            state["phase1_outline_md"] = md
            state["outline"] = {"markdown": md, "sections": sections}
            return state

        async def phase1_expand_sections(state: QBState) -> QBState:
            # 基于 policy_corpus 与 normalized_requirements 生成更丰富的条目
            def pick_points(hits: List[Dict[str, Any]], keywords: List[str], limit: int = 12) -> List[str]:
                points: List[str] = []
                for h in hits:
                    title = (h.get("title") or h.get("text") or "").strip()
                    snip = (h.get("snippet") or h.get("text") or "").strip()
                    blob = (title + "\n" + snip).lower()
                    if any(k in blob for k in keywords):
                        brief = title or snip[:60]
                        if brief:
                            points.append(brief)
                    if len(points) >= limit:
                        break
                return points

            official = state.get("policy_corpus", {}).get("official_docs", [])
            cases = state.get("policy_corpus", {}).get("case_docs", [])
            reqs = state.get("normalized_requirements", [])

            # 分类关键词
            kw_scope = ["适用范围", "对象", "面向", "企业", "个人", "在前海", "在本市"]
            kw_elig = ["条件", "资格", "须", "应", "需满足", "不得", "要求"]
            kw_thr = ["累计", "不少于", "不超过", "≥", "≤", "达到", "门槛", "阈值", "时间节点", "期内"]
            kw_mat = ["材料", "清单", "证明", "复印件", "原件", "表格", "模板", "盖章"]
            kw_proc = ["流程", "步骤", "受理", "审核", "公示", "发放", "办理", "时限"]
            kw_var = ["情形", "视同", "变更", "变体", "例外", "特殊", "豁免"]

            # 提炼
            pts_scope = pick_points(official + cases, kw_scope, limit=10)
            pts_elig = [
                f"{i+1}. {r.get('name','要点')}" for i, r in enumerate(reqs[:20])
            ]
            if not pts_elig:
                pts_elig = pick_points(official, kw_elig, limit=12)
            pts_thr = pick_points(official, kw_thr, limit=10)
            pts_mat = pick_points(official, kw_mat, limit=12)
            pts_proc = pick_points(official, kw_proc, limit=8)
            pts_var = pick_points(official + cases, kw_var, limit=8)

            lines: List[str] = ["# 申报条件判断与理解（完整）"]
            if pts_scope:
                lines.append("\n## 适用范围与对象\n")
                for p in pts_scope:
                    lines.append(f"- {p}")
            if pts_elig:
                lines.append("\n## 资格条件（硬性/加分）\n")
                for p in pts_elig:
                    lines.append(f"- {p}")
            if pts_thr:
                lines.append("\n## 门槛与阈值（地域/规模/时段等）\n")
                for p in pts_thr:
                    lines.append(f"- {p}")
            if pts_mat:
                lines.append("\n## 材料清单与格式要求\n")
                for p in pts_mat:
                    lines.append(f"- {p}")
            if pts_proc:
                lines.append("\n## 办理流程与时间节点\n")
                for p in pts_proc:
                    lines.append(f"- {p}")
            if pts_var:
                lines.append("\n## 不同情形与常见变体\n")
                for p in pts_var:
                    lines.append(f"- {p}")

            # 政策依据（列出前若干官方来源）
            if official:
                lines.append("\n## 政策依据与版本\n")
                for i, h in enumerate(official[:10], start=1):
                    title = (h.get("title") or h.get("text") or "来源").strip()
                    url = (h.get("url") or "").strip()
                    lines.append(f"{i}. {title} {(' '+url) if url else ''}")

            state["phase1_full_md"] = "\n".join(lines)
            return state

        async def phase1_critic_and_aggregate(state: QBState) -> QBState:
            if not state.get("normalized_requirements") and state.get("criteria"):
                norm: List[Dict[str, Any]] = []
                for c in state["criteria"]:
                    norm.append({
                        "id": c["id"],
                        "type": "condition",
                        "name": c.get("name", "条件/材料"),
                        "description": c.get("name", ""),
                        "applicable_projects": c.get("applicable_projects", []),
                        "source_refs": state["per_item_sources"].get(c["id"], []),
                    })
                state["normalized_requirements"] = norm
            return state

        async def phase2_collect_applicant_web(state: QBState) -> QBState:
            company = state.get("company_name")
            if not company:
                return state
            async with self.web_search_service as ws:
                web = await ws.search_web(f"{company} 注册资本 员工人数 社保 纳税 场地 处罚 证书", num_results=8)
            facts = [{"title": w.title, "url": w.url, "snippet": w.snippet} for w in web]
            state["applicant_findings"] = {"facts": facts}
            srcs = state["sources"]
            for w in web:
                srcs.append({"id": f"web::{w.url}", "type": "web", "title": w.title, "url": w.url, "snippet": w.snippet})
            state["sources"] = self._dedupe_sources(srcs)
            return state

        async def phase2_assess_and_report(state: QBState) -> QBState:
            matches = []
            for r in state.get("normalized_requirements", []):
                matches.append({"req_id": r["id"], "status": "unknown", "rationale": "待人工/问卷补充", "needed_evidence": []})
            state["applicant_findings"]["matches"] = matches
            lines = [
                "# 主体符合性评估（初稿）",
                "\n## 概览",
                f"- 满足：0 项\n- 不满足：0 项\n- 未知：{len(matches)} 项",
                "\n## 需补证清单\n- 将在问卷阶段补充采集",
            ]
            state["assessment_report_md"] = "\n".join(lines)
            return state

        async def phase3_generate_questionnaire_outline(state: QBState) -> QBState:
            outline = {
                "markdown": "# 问卷大纲\n- 主体资质\n- 经营指标\n- 场地材料\n- 佐证上传",
                "sections": [
                    {"id": "basic", "title": "主体资质"},
                    {"id": "biz", "title": "经营指标"},
                    {"id": "site", "title": "场地材料"},
                    {"id": "evidence", "title": "佐证上传"},
                ],
            }
            state["questionnaire_outline"] = outline
            state["questionnaire_sections"] = outline["sections"]
            return state

        async def phase3_deep_research_sections(state: QBState) -> QBState:
            items: List[Dict[str, Any]] = []
            for r in state.get("normalized_requirements", [])[:20]:
                items.append({
                    "id": f"ask::{r['id']}",
                    "section": "basic",
                    "text": f"关于 “{r.get('name','要求')}” 的具体情况？",
                    "type": "text",
                    "applicable_projects": r.get("applicable_projects", []),
                    "source_refs": r.get("source_refs", []),
                })
            state["questionnaire_items"] = items
            return state

        async def generate_outline_and_questions(state: QBState) -> QBState:
            # 提示 LLM 产出结构化大纲与题目（此处放置占位结构）
            outline = {
                "markdown": "# 问卷大纲\n- 主体资质\n- 经营指标\n- 场地信息\n- 人员社保\n- 财税合规\n- 历史补贴\n- 材料上传",
                "sections": [
                    {"id": "basic", "title": "主体资质"},
                    {"id": "biz", "title": "经营指标"},
                    {"id": "site", "title": "场地信息"},
                    {"id": "staff", "title": "人员与社保"},
                ],
            }
            questions = [
                {"id": "q_basic_region", "section": "basic", "text": "公司注册地位于何处？", "type": "enum", "options": ["前海", "深圳", "广东", "外省", "香港", "海外"], "applicable_projects": state["target_projects"]},
                {"id": "q_biz_revenue", "section": "biz", "text": "近一年营业收入（万元）", "type": "numeric", "applicable_projects": state["target_projects"]},
                {"id": "q_site_lease", "section": "site", "text": "是否在前海有合法租赁场地？", "type": "single", "options": ["是", "否"], "applicable_projects": state["target_projects"]},
            ]
            state["outline"] = outline
            state["questions"] = questions
            state["required_documents"] = [{"name": "营业执照", "applicable_projects": state["target_projects"], "mandatory": True}]
            state["rules"] = []
            state["scoring"] = {}
            state["success_rate_by_project"] = {p: {"range": "中等", "reasons": []} for p in state["target_projects"]}
            return state

        async def finalize(state: QBState) -> QBState:
            return state

        graph.add_node("validate_input", validate_input)
        graph.add_node("collect_client_context", collect_client_context)
        graph.add_node("retrieve_policy_and_cases", retrieve_policy_and_cases)
        graph.add_node("resolve_company_open_data", resolve_company_open_data)
        graph.add_node("normalize_criteria", normalize_criteria)
        # Phase 1
        graph.add_node("phase1_outline_first", phase1_outline_first)
        graph.add_node("phase1_expand_sections", phase1_expand_sections)
        graph.add_node("phase1_critic_and_aggregate", phase1_critic_and_aggregate)
        # Phase 2
        graph.add_node("phase2_collect_applicant_web", phase2_collect_applicant_web)
        graph.add_node("phase2_assess_and_report", phase2_assess_and_report)
        # Phase 3
        graph.add_node("phase3_generate_questionnaire_outline", phase3_generate_questionnaire_outline)
        graph.add_node("phase3_deep_research_sections", phase3_deep_research_sections)
        graph.add_node("generate_outline_and_questions", generate_outline_and_questions)
        graph.add_node("finalize", finalize)

        graph.set_entry_point("validate_input")
        graph.add_edge("validate_input", "collect_client_context")
        graph.add_edge("collect_client_context", "retrieve_policy_and_cases")
        graph.add_edge("retrieve_policy_and_cases", "resolve_company_open_data")
        graph.add_edge("resolve_company_open_data", "normalize_criteria")
        # Phase 1 chain
        graph.add_edge("normalize_criteria", "phase1_outline_first")
        graph.add_edge("phase1_outline_first", "phase1_expand_sections")
        graph.add_edge("phase1_expand_sections", "phase1_critic_and_aggregate")
        # Phase 2 chain
        graph.add_edge("phase1_critic_and_aggregate", "phase2_collect_applicant_web")
        graph.add_edge("phase2_collect_applicant_web", "phase2_assess_and_report")
        # Phase 3 chain
        graph.add_edge("phase2_assess_and_report", "phase3_generate_questionnaire_outline")
        graph.add_edge("phase3_generate_questionnaire_outline", "phase3_deep_research_sections")
        graph.add_edge("phase3_deep_research_sections", "generate_outline_and_questions")
        graph.add_edge("generate_outline_and_questions", "finalize")

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


