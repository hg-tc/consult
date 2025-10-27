"""
生产级 LangGraph 工作流
集成所有 Agent，实现完整的文档生成流程
"""

import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, List
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# 导入状态模型
from app.models.agent_models import AgentState
from app.models.agent_models import IntentAnalysis, QualityMetrics

# 导入 Agent
from app.agents.production import (
    GlobalDatabaseAgent,
    WorkspaceDatabaseAgent,
    ParallelSearchOrchestrator,
    InformationSynthesisAgent,
    QualityAssuranceAgent,
    ContentPlanningAgent,
    ContentGenerationAgent,
    RefinementAgent,
    FormattingAgent
)

# 导入链
from app.chains import (
    create_intent_analysis_chain,
    create_search_strategy_chain,
    create_quality_assessment_chain
)

logger = logging.getLogger(__name__)

class ProductionWorkflow:
    """生产级 LangGraph 工作流"""
    
    def __init__(self, llm: BaseChatModel, rag_service, web_search_service=None):
        self.llm = llm
        self.rag_service = rag_service
        self.web_search_service = web_search_service
        
        # 先初始化链
        self.intent_chain = create_intent_analysis_chain(llm)
        self.search_strategy_chain = create_search_strategy_chain(llm)
        self.quality_chain = create_quality_assessment_chain(llm)
        
        # 然后初始化所有 Agent
        self.agents = self._initialize_agents()
        
        # 构建工作流图
        self.graph = self._build_workflow_graph()
        
        # 配置检查点（支持中断恢复）
        self.checkpointer = MemorySaver()
        self.compiled_graph = self.graph.compile(
            checkpointer=self.checkpointer,
            debug=True
        )
    
    def _initialize_agents(self) -> Dict[str, Any]:
        """初始化所有 Agent"""
        global_agent = GlobalDatabaseAgent(self.llm, self.rag_service)
        workspace_agent = WorkspaceDatabaseAgent(self.llm, self.rag_service)
        
        parallel_search = ParallelSearchOrchestrator(
            global_agent, 
            workspace_agent, 
            web_agent=None  # 暂时不使用网络搜索
        )
        
        return {
            "parallel_search": parallel_search,
            "synthesis": InformationSynthesisAgent(self.llm),
            "planning": ContentPlanningAgent(self.llm),
            "generation": ContentGenerationAgent(self.llm),
            "quality": QualityAssuranceAgent(self.llm, self.quality_chain),
            "refinement": RefinementAgent(self.llm),
            "formatting": FormattingAgent(self.llm)
        }
    
    def _build_workflow_graph(self):
        """构建 LangGraph 状态图"""
        workflow = StateGraph(AgentState)
        
        # 添加所有节点
        workflow.add_node("intent_analysis", self._intent_analysis_node)
        workflow.add_node("search_strategy", self._search_strategy_node)
        workflow.add_node("parallel_search", self._parallel_search_node)
        workflow.add_node("information_synthesis", self._synthesis_node)
        workflow.add_node("content_planning", self._planning_node)
        workflow.add_node("content_generation", self._generation_node)
        workflow.add_node("quality_assessment", self._quality_node)
        workflow.add_node("content_refinement", self._refinement_node)
        workflow.add_node("final_formatting", self._formatting_node)
        
        # 设置入口
        workflow.set_entry_point("intent_analysis")
        
        # 添加边
        workflow.add_edge("intent_analysis", "search_strategy")
        workflow.add_edge("search_strategy", "parallel_search")
        workflow.add_edge("parallel_search", "information_synthesis")
        workflow.add_edge("information_synthesis", "content_planning")
        workflow.add_edge("content_planning", "content_generation")
        workflow.add_edge("content_generation", "quality_assessment")
        
        # 条件边
        workflow.add_conditional_edges(
            "quality_assessment",
            self._quality_routing,
            {
                "pass": "final_formatting",
                "refine": "content_refinement",
                "replan": "content_planning",
                "force_end": "final_formatting"
            }
        )
        
        workflow.add_edge("content_refinement", "content_generation")
        
        # final_formatting 后直接结束，避免循环
        workflow.add_edge("final_formatting", END)
        
        return workflow
    
    def _quality_routing(self, state: AgentState) -> str:
        """质量评估后的路由决策"""
        logger.info("=== 进入质量路由决策 ===")
        
        metrics = state.get("quality_metrics")
        iteration = state.get("iteration_count", 0)
        draft_content = state.get("draft_content", "")
        content_outline = state.get("content_outline", {})
        
        logger.info(f"迭代次数: {iteration}")
        logger.info(f"draft_content 长度: {len(draft_content) if draft_content else 0}")
        logger.info(f"metrics: {metrics.overall_score if metrics and hasattr(metrics, 'overall_score') else 'None'}")
        
        if not metrics:
            logger.warning("质量指标不存在，强制结束")
            return "force_end"
        
        # 如果内容为空或太短
        if not draft_content or len(draft_content) < 50:
            logger.warning(f"内容太短或为空({len(draft_content)})")
            
            # 如果有大纲，尝试重新生成
            if content_outline and iteration < 2:
                logger.warning("尝试重新生成内容")
                return "replan"
            else:
                logger.warning("强制结束")
                return "force_end"
        
        # 迭代次数过多，强制结束（优先级最高）
        if iteration >= 2:  # 减少到2次，更快停止
            logger.warning(f"迭代次数过多({iteration})，强制结束")
            return "force_end"
        
        # 优秀，直接格式化
        if metrics.overall_score >= 0.85:
            logger.info("质量达标，直接格式化")
            return "pass"
        
        # 质量太差，重新规划（仅限第一次迭代）
        if metrics.overall_score < 0.6 and iteration == 0:
            logger.warning(f"质量太差({metrics.overall_score})，重新规划")
            return "replan"
        
        # 无论质量如何，强制结束（避免无限循环）
        logger.warning(f"迭代次数 {iteration}，强制结束，当前质量: {metrics.overall_score:.2f}")
        return "force_end"
    
    async def _intent_analysis_node(self, state: AgentState) -> AgentState:
        """意图分析节点"""
        try:
            result = await self.intent_chain.ainvoke({
                "user_request": state["user_request"],
                "workspace_id": state["workspace_id"],
                "conversation_history": state.get("conversation_history", [])
            })
            
            # 处理返回结果 - 可能是 IntentAnalysis 对象或字典
            intent_data = result
            if not isinstance(intent_data, dict):
                from app.models.agent_models import IntentAnalysis
                # 如果是 Pydantic 对象，转换为字典
                intent_data = intent_data.dict() if hasattr(intent_data, 'dict') else intent_data.model_dump() if hasattr(intent_data, 'model_dump') else {"error": "Invalid intent format"}
            
            # 确保 intent 字段正确
            if "intent_analysis" in intent_data:
                state["intent"] = intent_data["intent_analysis"]
            elif "task_type" in intent_data or "complexity" in intent_data:
                state["intent"] = intent_data
            else:
                state["intent"] = intent_data
            
            state["current_step"] = "intent_analyzed"
            state["messages"].append("✓ 意图分析完成")
            
            logger.info(f"意图分析完成: {state['intent']}")
        except Exception as e:
            logger.error(f"意图分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            state["error"] = str(e)
        
        return state
    
    async def _search_strategy_node(self, state: AgentState) -> AgentState:
        """搜索策略节点"""
        try:
            intent = state.get("intent")
            if not intent:
                raise ValueError("意图不存在")
            
            # 处理意图数据 - 如果是字典就直接用，如果是对象就转换
            if isinstance(intent, dict):
                intent_dict = intent
                key_topics = intent.get("key_topics", [])
                data_sources = intent.get("data_sources", [])
            else:
                intent_dict = intent.model_dump() if hasattr(intent, 'model_dump') else intent.dict()
                key_topics = intent.key_topics if hasattr(intent, 'key_topics') else []
                data_sources = intent.data_sources if hasattr(intent, 'data_sources') else []
            
            result = await self.search_strategy_chain.ainvoke({
                "intent": intent_dict,
                "key_topics": key_topics,
                "data_sources": data_sources
            })
            
            state["search_strategy"] = result
            state["current_step"] = "strategy_determined"
            state["messages"].append("✓ 搜索策略确定")
            
            logger.info("搜索策略确定完成")
        except Exception as e:
            logger.error(f"搜索策略失败: {e}")
            state["error"] = str(e)
        
        return state
    
    async def _parallel_search_node(self, state: AgentState) -> AgentState:
        """并行搜索节点"""
        try:
            result = await self.agents["parallel_search"].execute_parallel(state)
            state["search_results"] = result["search_results"]
            state["current_step"] = "search_completed"
            
            results = result["search_results"]
            state["messages"].append(
                f"✓ 搜索完成: 全局{len(results.global_results)}条, "
                f"工作区{len(results.workspace_results)}条"
            )
        except Exception as e:
            logger.error(f"并行搜索失败: {e}")
            state["error"] = str(e)
        
        return state
    
    async def _synthesis_node(self, state: AgentState) -> AgentState:
        """信息综合节点"""
        try:
            result = await self.agents["synthesis"].execute(state)
            state["synthesized_info"] = result["synthesized_info"]
            state["current_step"] = "synthesized"
            state["messages"].append("✓ 信息综合完成")
        except Exception as e:
            logger.error(f"信息综合失败: {e}")
            state["error"] = str(e)
        
        return state
    
    async def _planning_node(self, state: AgentState) -> AgentState:
        """内容规划节点"""
        try:
            # 增加迭代计数（如果这是重新规划）
            if state.get("current_step") in ["quality_assessed", "refined"]:
                state["iteration_count"] = state.get("iteration_count", 0) + 1
                logger.info(f"重新规划，迭代次数: {state['iteration_count']}")
            
            result = await self.agents["planning"].execute(state)
            state["content_outline"] = result["content_outline"]
            state["current_step"] = "planned"
            state["messages"].append("✓ 内容规划完成")
        except Exception as e:
            logger.error(f"内容规划失败: {e}")
            state["error"] = str(e)
        
        return state
    
    async def _generation_node(self, state: AgentState) -> AgentState:
        """内容生成节点"""
        try:
            logger.info("=== 进入内容生成节点 ===")
            logger.info(f"当前 state 中的 draft_content 长度: {len(state.get('draft_content', ''))}")
            
            result = await self.agents["generation"].execute(state)
            draft_content = result.get("draft_content", "")
            
            logger.info(f"Agent 返回的 draft_content 长度: {len(draft_content)}")
            logger.info(f"draft_content 前100字符: {draft_content[:100] if draft_content else '空'}")
            
            # 确保保存到 state
            state["draft_content"] = draft_content
            state["current_step"] = "generated"
            
            # 验证保存结果
            logger.info(f"保存后的 state['draft_content'] 长度: {len(state.get('draft_content', ''))}")
            
            word_count = len(draft_content.split()) if draft_content else 0
            state["messages"].append(f"✓ 内容生成完成 ({len(draft_content)}字符, {word_count}字)")
            
            logger.info("=== 内容生成节点完成 ===")
        except Exception as e:
            logger.error(f"内容生成失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            state["error"] = str(e)
        
        return state
    
    async def _quality_node(self, state: AgentState) -> AgentState:
        """质量评估节点"""
        try:
            result = await self.agents["quality"].execute(state)
            state["quality_metrics"] = result["quality_metrics"]
            state["current_step"] = "quality_assessed"
            
            metrics = result["quality_metrics"]
            if metrics and hasattr(metrics, 'overall_score'):
                state["messages"].append(
                    f"✓ 质量评估: {metrics.overall_score:.2f}"
                )
            else:
                state["messages"].append("✓ 质量评估: 默认评分")
        except Exception as e:
            logger.error(f"质量评估失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            state["error"] = str(e)
        
        return state
    
    async def _refinement_node(self, state: AgentState) -> AgentState:
        """内容改进节点"""
        try:
            state["iteration_count"] = state.get("iteration_count", 0) + 1
            
            result = await self.agents["refinement"].execute(state)
            state["draft_content"] = result["draft_content"]
            state["current_step"] = "refined"
            state["messages"].append(
                f"✓ 内容改进完成 (迭代 {state['iteration_count']})"
            )
        except Exception as e:
            logger.error(f"内容改进失败: {e}")
            state["error"] = str(e)
        
        return state
    
    async def _formatting_node(self, state: AgentState) -> AgentState:
        """最终格式化节点"""
        try:
            result = await self.agents["formatting"].execute(state)
            state["final_document"] = result.get("final_document")
            state["output_file_path"] = result.get("output_file_path")
            state["current_step"] = "formatted"
            state["messages"].append("✓ 格式化完成")
        except Exception as e:
            logger.error(f"格式化失败: {e}")
            state["error"] = str(e)
        
        return state
    
    async def execute(
        self, 
        user_request: str, 
        workspace_id: str, 
        conversation_history: List[dict] = None
    ) -> Dict[str, Any]:
        """执行完整工作流"""
        # 初始化状态
        initial_state = {
            "user_request": user_request,
            "workspace_id": workspace_id,
            "conversation_history": conversation_history or [],
            "iteration_count": 0,
            "messages": [],
            "current_step": "start",
            "draft_content": "",
            "generated_sections": [],
            "error": None,
            "intent": None,
            "search_strategy": None,
            "search_results": None,
            "synthesized_info": "",
            "content_outline": None,
            "quality_metrics": None,
            "pending_confirmation": None,
            "user_feedback": None,
            "final_document": None,
            "output_file_path": None
        }
        
        # 执行工作流
        try:
            final_state = await self.compiled_graph.ainvoke(
                initial_state,
                config={
                    "configurable": {"thread_id": str(uuid.uuid4())},
                    "recursion_limit": 10  # 限制递归次数，避免无限循环
                }
            )
            
            return {
                "success": final_state.get("final_document") is not None,
                "document": final_state.get("final_document"),
                "final_document": final_state.get("final_document"),  # 兼容字段
                "result": {
                    "final_document": final_state.get("final_document"),
                    "final_state": final_state
                },
                "output_path": final_state.get("output_file_path"),
                "quality_score": (
                    final_state["quality_metrics"].overall_score 
                    if final_state.get("quality_metrics") else 0.0
                ),
                "iterations": final_state.get("iteration_count", 0),
                "execution_log": final_state.get("messages", []),
                "error": final_state.get("error")
            }
        except Exception as e:
            logger.error(f"工作流执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_log": initial_state.get("messages", [])
            }

