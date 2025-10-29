import os
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI


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


class QuestionnaireBuilderWorkflow:
    def __init__(self, workspace_retriever, global_retriever, web_search_service, llm=None):
        self.workspace_retriever = workspace_retriever
        self.global_retriever = global_retriever
        self.web_search_service = web_search_service
        if llm is None:
            api_key = os.getenv('THIRD_PARTY_API_KEY') or os.getenv('OPENAI_API_KEY')
            api_base = os.getenv('THIRD_PARTY_API_BASE') or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
            self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, openai_api_key=api_key, openai_api_base=api_base)
        else:
            self.llm = llm

        self.graph = self._build_graph()
        self.checkpointer = MemorySaver()
        self.compiled_graph = self.graph.compile(checkpointer=self.checkpointer)

    async def run(self, request: Dict[str, Any]) -> Dict[str, Any]:
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

        return {
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
        }

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
                hits[proj] = proj_hits
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
        graph.add_node("generate_outline_and_questions", generate_outline_and_questions)
        graph.add_node("finalize", finalize)

        graph.set_entry_point("validate_input")
        graph.add_edge("validate_input", "collect_client_context")
        graph.add_edge("collect_client_context", "retrieve_policy_and_cases")
        graph.add_edge("retrieve_policy_and_cases", "resolve_company_open_data")
        graph.add_edge("resolve_company_open_data", "normalize_criteria")
        graph.add_edge("normalize_criteria", "generate_outline_and_questions")
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


