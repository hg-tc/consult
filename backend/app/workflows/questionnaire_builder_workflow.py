import os
import uuid
from typing import Any, Dict, List, Optional, TypedDict, Annotated
from dataclasses import asdict
from operator import add

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool as tool_dec, tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AnyMessage, ToolMessage, HumanMessage, AIMessage, SystemMessage
from langchain.agents import create_agent
from app.utils.progress_broker import get_progress_broker
import time
import asyncio


from operator import add
from dataclasses import asdict

import logging
logger = logging.getLogger(__name__)

class QBState(TypedDict):
    request: Dict[str, Any]
    workspace_id: str
    company_name: Optional[str]
    target_projects: List[str]
    known_info: Dict[str, Any]
    global_db_out: str
    messages: Annotated[list[AnyMessage], add]
    type: str
    retry_count: int
    max_retries: int
    md: str
    analysis: str


class QuestionnaireBuilderWorkflow:
    def __init__(self, workspace_retriever, global_retriever, web_search_service, llm=None):
        logger.debug("Initializing QuestionnaireBuilderWorkflow")
        self.workspace_retriever = workspace_retriever
        self.global_retriever = global_retriever
        self.web_search_service = web_search_service
        if llm is None:
            logger.debug("No LLM provided")
            from app.core.config import settings
            api_key = os.getenv('THIRD_PARTY_API_KEY') or os.getenv('OPENAI_API_KEY')
            api_base = os.getenv('THIRD_PARTY_API_BASE') or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
            self.llm = ChatOpenAI(model=settings.LLM_MODEL_NAME_QUESTIONNAIRE, temperature=0.2, openai_api_key=api_key, openai_api_base=api_base).with_config({"stream": False})
        else:
            # 统一禁用流式，避免 usage_metadata None 聚合问题
            self.llm = llm.with_config({"stream": False}) if hasattr(llm, "with_config") else llm

        self.graph = self._build_graph()
        self.checkpointer = MemorySaver()
        self.compiled_graph = self.graph.compile(checkpointer=self.checkpointer)

    async def run(self, request: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
        initial: QBState = {
            "request": request,
            "workspace_id": (request.get("workspace_id") or "global"),
            "company_name": request.get("company_name"),
            "target_projects": request.get("target_projects", []),
            "known_info": request.get("known_info", {}),
            "global_db_out": "",
            "type": "",
            "messages": [],
            "retry_count": int(request.get("retry_count", 0)),
            "max_retries": int(request.get("max_retries", 1)),
            "md": "",
            "analysis": "",
        }
        
        workspace_id = initial.get("workspace_id") or "global"
        
        # 获取task_id，如果存在则使用task_queue更新进度
        task_id = request.get("task_id")
        task_queue = None
        if task_id:
            from app.services.task_queue import get_task_queue
            task_queue = get_task_queue()
        
        # 定义节点阶段信息和进度映射
        node_stages = {
            "db_search": {"name": "数据库检索", "description": "正在从内部数据库检索政策信息", "progress": 15},
            "web_search": {"name": "网络检索", "description": "正在从互联网搜索相关政策信息", "progress": 25},
            "summery": {"name": "信息汇总", "description": "正在汇总检索到的信息", "progress": 35},
            "judger": {"name": "信息判断", "description": "正在判断信息完整性", "progress": 45},
            "person_info_web_search": {"name": "人员信息检索", "description": "正在检索相关人员信息", "progress": 55},
            "analysis": {"name": "分析生成", "description": "正在生成分析报告", "progress": 75},
            "query": {"name": "问卷细化", "description": "正在细化问卷问题", "progress": 90},
        }
        # 获取client_id（用于thread_id生成）
        client_id = request.get("client_id", "")
        
        base_thread_id = (
            str(initial.get("workspace_id") or "global")
            + ":"
            + (initial.get("company_name") or "")
            + ":"
            + ("|".join(initial.get("target_projects", [])[:3]))
        ) or str(uuid.uuid4())
        
        # 如果有客户端ID，添加到thread_id前缀，实现用户隔离
        if client_id:
            thread_id = f"{client_id}:{base_thread_id}"
        else:
            thread_id = base_thread_id
        # LangSmith / LangGraph 追踪：设置 run_name、tags 与 metadata 便于按工作流过滤
        # 注意：recursion_limit 必须在 config 的顶层，不能放在 configurable 中
        # 根据 LangGraph 文档，recursion_limit 应该是 config 的直接属性
        config = {
            "recursion_limit": 200,  # 增加递归限制，避免复杂工作流超出默认的25次限制（必须在顶层）
            "run_name": "questionnaire_builder",
            "tags": [
                "workflow:questionnaire_builder",
                f"workspace:{initial.get('workspace_id')}",
                *[f"project:{p}" for p in (initial.get("target_projects") or [])[:5]],
            ],
            "metadata": {
                "company_name": initial.get("company_name") or "",
            },
            "configurable": {"thread_id": thread_id},
        }
        logger.debug(f"工作流配置创建完成: recursion_limit={config.get('recursion_limit')}")
        
        # 使用流式执行，监控节点执行状态，并累积最终结果
        previous_node = None
        accumulated_state = dict(initial)  # 从初始状态开始累积
        
        # 使用流式执行监控进度，同时累积状态更新
        # 确保 recursion_limit 被正确传递
        logger.debug(f"执行配置: recursion_limit={config.get('recursion_limit')}")
        async for event in self.compiled_graph.astream(initial, config):
            # LangGraph astream 返回的格式是 {node_name: node_output}
            for node_name, node_output in event.items():
                if node_name in node_stages and task_queue:
                    stage_info = node_stages[node_name]
                    # 通过task_queue更新进度（不使用ProgressBroker，因为是后台任务）
                    task_queue.update_task_progress(
                        task_id=task_id,
                        stage=None,  # 使用None保持默认stage
                        progress=stage_info["progress"],
                        message=stage_info["description"],
                        details={"stage": node_name, "name": stage_info["name"]}
                    )
                    logger.debug(f"[progress] {stage_info['name']}: {stage_info['description']}")
                
                # 累积状态更新（节点输出会更新部分状态字段）
                if isinstance(node_output, dict):
                    accumulated_state.update(node_output)
        
        # 更新最终进度
        if task_queue and task_id:
            task_queue.update_task_progress(
                task_id=task_id,
                stage=None,
                progress=95,
                message="正在生成最终结果...",
            )
        
        # 使用累积的状态作为最终结果
        # 确保两个关键字段都存在，如果缺少则重新获取完整状态
        if not accumulated_state.get("analysis") or not accumulated_state.get("md"):
            logger.debug("累积状态不完整，重新获取完整状态")
            # 确保配置中包含 recursion_limit
            logger.debug(f"调用 ainvoke，recursion_limit={config.get('recursion_limit')}")
            result = await self.compiled_graph.ainvoke(initial, config)
        else:
            result = accumulated_state
        
        # 从最终消息中提取分析结果
        final_analysis = result.get("analysis")
        final_md = result.get("md")
        
        # 只返回两个字段：报告和问卷
        logger.debug(f"问卷生成完成，返回结果")
        return {
            "final_md": final_md,
            "final_analysis": final_analysis
        }

    def _build_graph(self) -> StateGraph:
        
        @tool
        def search_global_db(query: str) -> str:
            """从全局数据库中检索相关数据，全局数据库包含各类政策信息与过去的申请案例，输入具体检索内容"""
            snippets: List[str] = []
            # 全局检索（同步包装）
            try:
                logger.debug(f"[db_search_tool] 开始全局检索: query={query}")
                g_results = asyncio.run(self.global_retriever.retrieve(query=query, top_k=6, use_hybrid=True, use_compression=True))
                logger.debug(f"[db_search_tool] 全局检索返回 {len(g_results)} 条结果")
                for r in g_results:
                    title = r.get("title") or r.get("name") or r.get("document_id") or "片段"
                    text = r.get("text") or r.get("content") or ""
                    snippets.append(f"[GLOBAL] {title}: {text[:300]}")
            except Exception as e:
                logger.debug(f"[db_search_tool] 全局检索失败: {e}")
            return "\n".join(snippets[:12]) or "未找到有效片段"
        
        @tool
        def search_web(query: str) -> str:
            """从网络中检索相关数据；输入中文查询，返回若干条标题与链接摘要"""
            lines: List[str] = []
            try:
                # 如果服务是异步实现，这里用 asyncio.run 同步封装
                results = asyncio.run(self.web_search_service.search_web(query=query, num_results=6))
            except Exception as e:
                logger.debug(f"[web_search_tool] 网络搜索失败: {e}")
                return "(网络搜索失败)"
            if not results:
                return "(未找到结果)"
            for idx, r in enumerate(results[:8], 1):
                d = asdict(r)
                title = d.get("title") or r.get("name") or r.get("snippet_title") or "未知标题"
                url = d.get("url") or r.get("link") or r.get("source_url") or ""
                snippet = d.get("snippet") or r.get("content") or r.get("desc") or ""
                lines.append(f"[{idx}] {title}\n{url}\n{snippet[:200]}")
            return "\n\n".join(lines)


        def db_search_node(state: QBState) -> QBState:

            logger.debug(f"db_search_node")
            tp = ", ".join(state.get("target_projects") or [])
            known = state.get("known_info") 

            react_system_text = (
                "你是中国政策与补贴申报顾问。用户希望申请以下项目：{target_projects}\n"
                "已知信息（可能不完整）：\n{known_info}\n\n"
                "目标：输出面向实操的‘申报条件综述’。\n"
                "执行方式（严格遵守）：\n"
                "1) 如信息不足，循环调用 search_global_db 检索相关片段并综合要点；\n"
                "2) 每轮检索后判断是否仍存在关键空缺（资格/门槛/材料/流程/时间/例外情形）；\n"
                "3) 若仍有空缺，则继续调用 search_global_db；若已覆盖充分则停止循环；\n"
                "4) 最多调用工具 2 次，达到上限后必须仅输出 OK 并停止；\n"
                "检索内容都需要标明出处，具体哪一个文件"
                # "5) 完成后仅输出 OK 作为结束信号（禁止提前总结）。\n\n"
                "注意：优先引用明确口径与阈值，并标注来源类别。"
                
            ).format(
                target_projects=tp or "未指定",
                known_info=known or "无",
            )

            agent = create_agent(
                model=self.llm,
                    tools=[search_global_db],
                    system_prompt=react_system_text,
                )
            message_content = state.get("messages")

            # 安全地提取消息内容
            def get_content(msg):
                if msg is None:
                    return ""
                if isinstance(msg, dict):
                    return msg.get("content", "")
                if hasattr(msg, "content"):
                    return getattr(msg, "content", "")
                if isinstance(msg, list) and len(msg) > 0:
                    return get_content(msg[0])
                return str(msg) if msg else ""
            logger.debug(f"[db_search_tool] 调用开始检索")
            if message_content is not None and len(message_content) > 1:
                res_msg = agent.invoke({"messages": [{"role": "user", "content": "根据这些项目生成条件要求总览,已知总结结果：" + \
                get_content(message_content[-2]) + "，判断结果" + get_content(message_content[-1])}]})
            else:
                res_msg = agent.invoke({"messages": [{"role": "user", "content": "根据这些项目生成条件要求总览"}]})
            prev_msgs = res_msg.get("messages") or []
            logger.debug(f"[db_search_tool] 模型检索完成")
            return {"messages": prev_msgs}
        
        def web_search_node(state: QBState) -> QBState:
            """
            使用网络搜索工具对指定项目进行外部信息检索，返回若干检索要点。
            仅返回增量键以满足 LangGraph 的合并规则。
            """
            logger.debug("[web_search_node] start")
            tp = ", ".join(state.get("target_projects") or [])
            known = state.get("known_info") or {}
            known_blob = "\n".join([f"- {k}: {v}" for k, v in list(known.items())[:12]]) if isinstance(known, dict) else str(known)

            system_text = (
                "你是网络检索与情报整合助手。请围绕‘{target_projects}’项目，为企业用户提供申报所需的具体政策文件和实用要点。\n"
                "检索与迭代规则（严格遵守）：\n"
                "1) 首先，请根据数据库中返回的政策文件名称，优先生成高质量中文检索词（3-8条），每条尽可能包含政策文件全名/简称、项目关键词及相关单位/地区/年份/文号。例如：“{target_projects} 申报政策文件名+申报条件”、“文件名+资格门槛+地名”等，务必重点覆盖：申报条件、资格门槛、材料清单、办理流程、关键时间节点、例外情形、资金标准等；如有政策文件全名或文号，优先使用；如无则结合常见公开文件类型与通用项目表述，补足关键词。\n"
                "2) 强调优先从政府公开网站（如各级政府官网、部门官网、政务公开专栏、政策公告栏、gov.cn 域名等）进行检索，尤其关注官方政策文件、通知与内部编号；可以先检索官网公告或政策通知具体发布位置，再轻细分栏目与主管部门。每轮请使用检索词调用 search_web 工具获取结果；优先来源顺序：官网/官媒（gov.cn/部门官网/平台）、政策文件与指南、地方主管部门、企查查/企信宝等工商信息、招股书/年报/公告、主流媒体；尽量附原始链接。\n"
                "3) 每轮检索后自检信息空缺（上述各类要点及是否涉及具体政策文件、明确阈值、关键口径、例外情形），若仍有信息缺失，请结合数据库给出的政策文件名/编号等，生成更细化的新检索词（加入文件名、实体、年份、地区、文号等），再进行下一轮，最多迭代 8 次。\n"
                "4) 达到 2 次迭代上限后，须仅输出：OK，并停止检索和输出；\n"
                "5) 输出要求：先分轮次列出‘检索词与命中概览’（每轮/关键词命中及链接），再给出‘要点汇总’（分：资格门槛/材料/流程/时间/例外/资金标准），每点务必标注对应来源编号，并指明政策文件名称和出处；信息充分时，最后单独输出一行：OK。\n"
                "注意事项：严禁泛化与编造，所有要点须有明确政策来源、文本引用或权威出处；可合并同源内容；对工商主体类信息建议引用企查查、企信宝等公开渠道，标注身份字段需谨慎。\n\n"
                "已知背景（供参考，可能不完整）：\n{known_info}"
            ).format(target_projects=tp or "未指定", known_info=known_blob or "无")

            agent = create_agent(
                model=self.llm,
                tools=[search_web],
                system_prompt=system_text,
            )

            # 生成一次性检索提示（也可根据需要改为多轮）
            message_content = state.get("messages")
            def get_content(msg):
                if msg is None:
                    return ""
                if isinstance(msg, dict):
                    return msg.get("content", "")
                if hasattr(msg, "content"):
                    return getattr(msg, "content", "")
                if isinstance(msg, list) and len(msg) > 0:
                    return get_content(msg[0])
                return str(msg) if msg else ""
            logger.debug(f"[db_search_tool] 调用开始检索")
            if message_content is not None and len(message_content) > 1:
                res_msg = agent.invoke({"messages": [{"role": "user", "content": "请检索并汇总要点，给出链接与简要摘录,已知总结结果：" + \
                get_content(message_content[-2]) + "，判断结果" + get_content(message_content[-1])}]})
            else:
                res_msg = agent.invoke({"messages": [{"role": "user", "content": "请检索并汇总要点，给出链接与简要摘录"}]})
            prev_msgs = res_msg.get("messages") or []

            return {"messages": [prev_msgs]}


        def summery_node(state: QBState) -> QBState:

            logger.debug(f"[summery_node] 开始总结")

            prompt = (
                "你是政策要求材料总结助手。用户希望申请以下项目：{target_projects}\n"
                "已知信息（可能不完整）：\n{known_info}\n\n"
                "你已经从数据库或网络中检索到了相关信息，请你基于这些信息，系统性、详细地总结申报条件要求和必要材料，涵盖但不限于以下方面：资格要求、申报门槛、必需材料、办理流程、关键时间节点、常见例外等。\n"
                "请充分整合所有获取到的政策条款、申报文件、案例等数据，对每项条件尽量详细具体，必要时举例说明，并按类别或逻辑结构清晰归纳，帮助用户快速把握核心要点和潜在难点。\n"
                "总结时，请注意精炼信息，去除无效和重复的内容与消息，只保留和申请条件及材料相关的有效内容。\n"
                "在总结后，请进一步思考和指出：\n"
                "1）根据当前信息，还有哪些可能的申报条件、材料或案例尚未被覆盖，建议检索哪些内容以补全信息？\n"
                "2）请列出你的补全建议点和你的分析思路，帮助后续继续完善。\n"
                "尽量细化到每个条件的具体内容要求。"
                "每一条相关总结都需要标明出处，具体哪一个文件说了需要哪些条件和申报材料"
                "具体条件和材料要求不要模糊不清或泛泛而谈，如资质与信用要求指导其是否具备高新/专精特新/小巨人等资质、是否存在行政处罚/失信记录，这种总结就是不好的，需要补充高新，专精特新，小巨人等资质具体要求什么条件"
                "不要捏造事实，如不清楚具体细节，说明待进一步网络/数据库检索，实在找不到相关要求，就说明自己推断"

            )

            # 直接从 QBState 获取 ToolMessage

            msgs = state.get("messages") or []
            tool_texts = [m.content for m in msgs if isinstance(m, ToolMessage)]
            tool_blob = "\n\n".join(tool_texts) if tool_texts else "（无工具输出）"
            prompts = [
                SystemMessage(content=prompt),
                HumanMessage(content=tool_blob),
            ]
            res_msg = self.llm.invoke(prompts)
            logger.debug(f"[summery_node] 总结完成")
            return {"messages": [res_msg]}
        
        def Judger_node(state: QBState) -> QBState:
            """
            根据总结信息，判断是否需要进行检索，如果要检索具体哪些方案还要检索；受 max_retries 控制。
            """
            logger.debug(f"[Judger_node] 开始判断")
            # 已达最大次数则直接放弃检索
            retry_count = int(state.get("retry_count") or 0)
            max_retries = int(state.get("max_retries") or 0)
            logger.debug(f"retry_count: {retry_count}, max_retries: {max_retries}")
            if retry_count >= max_retries and max_retries > 0:
                logger.debug(f"[Judger_node] 已达最大重检索次数: {retry_count}/{max_retries}")
                return {"type": "放弃检索"}

            prompt = (
                "你是申报条件判定助手。用户希望申请以下项目：{target_projects}\n"
                "已知信息（可能不完整）：\n{known_info}\n\n"
                "你已经获得了对申报条件与材料的总结（见下文），请根据这些内容判断：\n"
                "你的回答前四个字必须为“库中检索”或“网络检索”或“放弃检索”，用于直接表示是否还需要进一步检索信息；\n"
                "之后再给出具体建议方案和理由，但务必保证前四个字为“库中检索”或“网络检索”或“放弃检索”并直接作答；\n"
                "例如：\n"
                "库中检索，需要进一步检索学历要求、财务指标明细，因为…\n"
                "放弃检索，所有关键信息均已覆盖，无需补充。\n"
                "网络检索，需要进一步检索学历要求、财务指标明细，因为…\n"
                "请严格遵循：前四个字只能为“库中检索”或“网络检索”或“放弃检索”。"
                "若需要检索, 请列出需检索的具体方案（如：学历要求、财务指标明细等）及你的判定理由。\n"
                "每一条相关总结都需要标明出处，具体哪一个文件说了需要哪些条件和申报材料"
                "具体条件和材料要求不要模糊不清或泛泛而谈，如资质与信用要求指导其是否具备高新/专精特新/小巨人等资质、是否存在行政处罚/失信记录，这种总结就是不好的，需要补充高新，专精特新，小巨人等资质具体要求什么条件"
                "不要捏造事实，如不清楚具体细节，说明待进一步网络/数据库检索，实在找不到相关要求，就说明自己推断"
            ).format(
                target_projects=state.get("target_projects") or "未指定",
                known_info=state.get("known_info") or "无"
            )

            logger.debug("总结结果" + state.get("messages")[-1].content)

            prompts = [
                SystemMessage(content=prompt),
                HumanMessage(content=state.get("messages")[-1].content),
            ]
            res_msg = self.llm.invoke(prompts)
            logger.debug("[Judger_node] 模型判断完成")
            # 取前3字作为动作标记
            type_now = res_msg.content[0:4]
            logger.debug(f"[Judger_node] 判断结果 {type_now}")
            # 若需要再次检索，则递增 retry_count
            if type_now in ("库中检索", "网络检索"):
                return {"messages": [res_msg], "type": type_now, "retry_count": retry_count + 1}
            else:
                return {"messages": [res_msg], "type": type_now}
        
        def person_info_web_search_node(state: QBState) -> QBState:
            """
            使用网络搜索工具对指定项目进行外部信息检索，返回若干检索要点。
            仅返回增量键以满足 LangGraph 的合并规则。
            """
            logger.debug("[web_search_node] start")
            company_name = ", ".join(state.get("company_name") or [])
            known = state.get("known_info") or {}
            known_blob = "\n".join([f"- {k}: {v}" for k, v in list(known.items())[:12]]) if isinstance(known, dict) else str(known)

            system_text = (
                "你是“主体信息核验”检索助手。任务：围绕以下“公司/个人”实体，检索公开渠道并给出可佐证材料与链接，验证其是否满足相关政策申报所需的主体条件与记录。\n"
                "检索与迭代规则（严格执行）：\n"
                "1) 先生成一批中文检索词（3-8条），覆盖：企业基础信息（名称/统一社会信用代码/注册地/高管股东）、资格资质/行政许可、行政处罚/信用记录、司法文书/裁判/执行、知识产权、公告/年报/招股书/招投标、主流媒体报道等；必要时加入实体/地区/年份/文号限定。\n"
                "2) 每轮按检索词调用 search_web 获取结果；优先来源顺序：政府/主管部门官网与平台（gov.cn、地方政务、信用平台、司法/裁判文书网）> 政策文件/公告/年报/招股书/招投标/公示 > 工商主体公开库（企查查、企信宝等）> 主流媒体/权威行业平台；尽量提供原始链接。\n"
                "3) 每轮完成后自检覆盖度：上述要点是否覆盖？是否有明确口径/阈值/例外？若仍有空缺，则生成更精准的新检索词（含实体/地区/年份/文号/关键词）并进行下一轮；最多迭代 8 次。\n"
                "4) 达到 2 次上限后，必须仅输出：OK，并停止检索与输出。\n"
                "输出格式（严格遵循）：\n"
                "- 检索词与命中概览（按轮次/关键词列出命中与链接，1-2 行要点）\n"
                "- 证据要点汇总（分项：基础信息、资格/许可、处罚/信用、司法/裁判、知识产权、公告/年报/招股/招投标、媒体报道等），每点后标注来源编号\n"
                "- 若信息已充分，请在最后单独一行仅输出：OK\n"
                "约束：严禁编造；尽量引用来源原文口径；同源重复合并；对个人敏感信息需最小化披露；如无公开记录，明确说明“未检出”；中文输出。\n\n"
                "已知背景（供参考，可能不完整）：\n{known_info}\n"
                "主体名称：\n{company_name}（如为公司/个人，请在检索词中加入其名称/别名/代码/地区等）"
                "每一条相关总结都需要标明出处，具体哪一个文件或网页说了需要哪些条件和申报材料"
                "具体条件和材料要求不要模糊不清或泛泛而谈，如直接说申请人具备高新/专精特新/小巨人等资质，这种总结就是不好的，需要补充申请人具体有什么相关经历"
                "不要捏造事实，如不清楚具体细节，说明待进一步网络/数据库检索，实在找不到相关要求，就说明自己推断"
            ).format(company_name=company_name or "未指定", known_info=known_blob or "无")

            agent = create_agent(
                model=self.llm,
                tools=[search_web],
                system_prompt=system_text,
            )

            # 生成一次性检索提示（也可根据需要改为多轮）
            message_content = state.get("messages")
            def get_content(msg):
                if msg is None:
                    return ""
                if isinstance(msg, dict):
                    return msg.get("content", "")
                if hasattr(msg, "content"):
                    return getattr(msg, "content", "")
                if isinstance(msg, list) and len(msg) > 0:
                    return get_content(msg[0])
                return str(msg) if msg else ""
            logger.debug(f"[web_search_tool] 调用开始检索")

            retry_count = int(state.get("retry_count") or 0)
            max_retries = int(state.get("max_retries") or 0)
            logger.debug(f"retry_count: {retry_count}, max_retries: {max_retries}")
            message_list = []
            if retry_count >= max_retries and max_retries > 0:
                message_list = [message_content[-1],message_content[-3]]
                res_msg = agent.invoke({"messages": [{"role": "user", "content": "请检索并汇总要点，给出链接与简要摘录,已知总结结果：" + \
                get_content(message_content[-1]) + "，数据库和网络检索已达最大字数，最后一次检索建议：" + get_content(message_content[-3])}]})
            elif message_content is not None and len(message_content) > 1:
                message_list = [message_content[-2],message_content[-1]]
                res_msg = agent.invoke({"messages": [{"role": "user", "content": "请检索并汇总要点，给出链接与简要摘录,已知总结结果：" + \
                get_content(message_content[-2]) + "，判断结果" + get_content(message_content[-1])}]})
            else:
                res_msg = agent.invoke({"messages": [{"role": "user", "content": "请检索并汇总要点，给出链接与简要摘录"}]})
            prev_msgs = res_msg.get("messages") or []

            return {"messages": message_list + [prev_msgs]}
        
        def analysis_node(state: QBState) -> QBState:

            logger.debug(f"[analysis_node] 开始分析")

            prompt = (
                "你是“申报可行性评估”专家，面向具体申请人（公司/个人）与目标政策。\n"
                "目标：基于已检索/整理的信息，给出申请成功可能性的系统评估与改进建议，并产出一份进一步核实问卷大纲。\n\n"

                "工作流程（严格遵循）：\n"
                "1) 要求与材料大纲：\n"
                "   - 资格条件（主体/行业/规模/资质/信用/地域/时间窗口）\n"
                "   - 硬性门槛（营收/投资/纳税/研发/人员/社保/不良记录等阈值）\n"
                "   - 佐证材料（营业执照、财务报表、纳税/社保证明、合同、专利/商标、获奖/荣誉等）\n"
                "   - 流程与关键时间点（申报节点、审核、异议、公示、发放）\n"
                "   - 例外情形与排除条款\n"
                "   为每条在括号中标注来源编号（若有）。\n\n"

                "2) 匹配与证据：将申请人信息与要求逐条比对，分组输出：\n"
                "   - 已满足（列证据点与来源编号）\n"
                "   - 基本满足但需补充（缺失/证据弱项）\n"
                "   - 未满足（关键差距）\n"
                "   - 不确定/模糊（待核实）\n\n"

                "3) 评分与结论：\n"
                "   - 从适配度(40)、合规与信用(20)、材料完备度(20)、流程与时间把控(10)、风险与不确定性(10) 五维度打分并给总分（0-100）。\n"
                "   - 给出一句话结论（可行/存在较大不确定/暂不具备），以及三条内的优先行动建议。\n\n"

                "4) 进一步核实问卷：用于向申请人收集关键信息与材料链接（可复制到表单）。\n"
                "   - 每个问题包含：提问、所需证据/证明、说明（为什么需要/判定依据）、期望格式（文件/截图/链接/编号）。\n"
                "   - 优先覆盖“不确定/模糊”和“基本满足但需补充”的条目，按优先级排序。\n"
                "   - 至少给出 8-15 个相关问题方向，禁用长篇开放题，尽量结构化，与政策要求有对应关系。\n\n"

                "每一条相关总结都需要标明出处，具体哪一个文件或网页说了需要哪些条件和申报材料，哪里说明申请人是否符合条件"
                "具体条件和材料要求不要模糊不清或泛泛而谈，如直接说申请人具备高新/专精特新/小巨人等资质，这种总结就是不好的，需要补充申请人具体有什么相关经历"
                "约束：不得编造；如无来源请标注“无明确来源”；仅提炼必要细节；可引用先前‘检索命中’与‘总结’的来源编号。"
                "直接生成结果，不要再向我提问"
            )

            # 直接从 QBState 获取 ToolMessage

            msgs = state.get("messages") or []
            texts = [msg.content for msg in msgs[-1]]+[msgs[-2].content, msgs[-3].content]
            blob = "\n\n".join(texts) if texts else "（无工具输出）"


            agent = create_agent(
                model=self.llm,
                tools=[],  # 或不传，视你的封装实现而定
                system_prompt=prompt,
            )
            res_msg = agent.invoke(HumanMessage(content=blob))
            logger.debug(f"[analysis_node] 分析完成")
            res_list = res_msg.get("messages")

            
            return {"analysis": res_list[0].content}

        def query_node(state: QBState) -> QBState:

            logger.debug(f"[query_node] 开始分析")

            prompt = (
                "你是一个专业的问卷设计师，负责将申报材料的大纲细化为具体可提问的问题。请严格按照以下要求完成："
                "## 任务要求:"
                "1. **判断必需性**：请根据已有信息，智能判断哪些信息用户已知，无需重复提问，仅针对未知或不完整的信息设计问题。"
                "2. **条目关联**：每个设计的问题，都要明确标注该问题与哪个申请条目或材料要求直接相关，例如“关联条目：申报条件-公司注册时间”"
                "3. **细化程度**：将每个需要询问的大纲条目扩展为3-5个具体问题，确保覆盖所有关键维度。"
                "4. **问题类型**：涵盖开放式和封闭式（选择题）两类问题。"
                "5. **覆盖范围**：问题应涵盖（但不限于）："
                "- 公司基本信息"
                "- 业务模式"
                "- 其它业务相关维度"
                "6. **问题质量**："
                "- 问题应清晰明确，避免歧义"
                "- 给出必要的背景说明"
                "- 对专业术语提供简要解释"
                "7. **格式要求**："
                "- 使用Markdown列表格式输出"
                "- 每个问题必须以“（关联条目：xxx）”结尾，说明该问题具体对应的大纲或申报材料要求"
                "- 已知信息可用备注形式在对应条目后补充“（已知，无需提问）”，无需再次列为问题"
                "## 输出示例"
                "```markdown"
                "### 公司基本信息"
                "1. **公司注册名称**：请提供公司的法定注册名称（关联条目：公司注册信息）"
                "2. **成立时间**：公司成立于哪一年？（关联条目：申报条件-成立时长）"
                "3. **主营业务**：请描述公司的主要业务范围（关联条目：主营业务要求）"
                "- 补充说明：包括核心产品/服务"
                "4. **组织架构**：公司目前有多少个部门？"
                "- 选项：A. 1-5个 B. 6-10个 C. 10个以上（关联条目：组织结构/部门设置）"
                "（如某项信息已知，直接标注“（已知，无需提问）”而不在问题列表中显示）"
                "```"
                "直接生成结果，不要再向我提问"
            )

            # 直接从 QBState 获取 ToolMessage

            source = state.get("analysis")
            agent = create_agent(
                model=self.llm,
                tools=[],  # 或不传，视你的封装实现而定
                system_prompt=prompt,
            )
            res_msg = agent.invoke(HumanMessage(content=source))
            logger.debug(f"[query_node] 问卷细化完成")
            res_list = res_msg.get("messages")
            # for i, msg in enumerate(res_list):
            #     print(f"res_list[{i}]:", msg)
            
            return {"md": res_list[0].content}
        
        



        def router_func(state: QBState):
            if state["type"] == "库中检索":
                return "db_search"
            elif state["type"] == "网络检索":
                return "web_search"
            else:
                return "person_info_web_search"
            
        graph = StateGraph(QBState)      
        graph.add_node("db_search", db_search_node)
        graph.add_node("web_search", web_search_node)
        graph.add_node("summery", summery_node)
        graph.add_node("judger", Judger_node)
        graph.add_node("person_info_web_search", person_info_web_search_node)
        graph.add_node("analysis", analysis_node)
        graph.add_node("query", query_node)


        graph.add_edge(START, "db_search")
        graph.add_edge("db_search", "summery")
        graph.add_edge("summery", "judger")
        graph.add_edge("web_search", "summery")
        graph.add_edge("summery", "judger")
        graph.add_conditional_edges("judger", router_func, ["db_search","web_search","person_info_web_search"])
        graph.add_edge("person_info_web_search", "analysis")
        graph.add_edge("analysis", "query")
        graph.add_edge("query", END)

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


