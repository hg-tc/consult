"""
LangGraph 智能 RAG 工作流
基于状态机和条件路由的智能编排层
"""

from typing import TypedDict, Dict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
import os
import logging
import asyncio
import json
import re

logger = logging.getLogger(__name__)

# 定义状态
class RAGState(TypedDict):
    """RAG 工作流状态"""
    # 输入
    question: str
    workspace_id: str
    conversation_history: list
    
    # 意图识别
    intent: str  # "simple_qa" | "complex_reasoning" | "document_generation"
    complexity: str  # "low" | "medium" | "high"
    requires_multi_hop: bool
    
    # 检索结果
    workspace_docs: list
    global_docs: list
    web_results: list
    
    # 生成
    draft_answer: str
    final_answer: str
    
    # 质量控制
    quality_score: float
    needs_refinement: bool
    iteration_count: int
    
    # 元数据
    retrieval_strategy: str
    sources_used: list
    processing_steps: list

class LangGraphRAGWorkflow:
    """基于 LangGraph 的智能 RAG 工作流"""
    
    def __init__(self, workspace_retriever, global_retriever, llm=None):
        self.workspace_retriever = workspace_retriever
        self.global_retriever = global_retriever
        if llm is None:
            api_key = os.getenv('THIRD_PARTY_API_KEY') or os.getenv('OPENAI_API_KEY')
            api_base = os.getenv('THIRD_PARTY_API_BASE') or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
            self.llm = ChatOpenAI(
                model="gpt-3.5-turbo",
                temperature=0.1,
                openai_api_key=api_key,
                openai_api_base=api_base
            )
        else:
            self.llm = llm
        
        # 构建状态图
        self.graph = self._build_graph()
        
        # 配置检查点（支持断点续传）
        self.checkpointer = MemorySaver()
        self.compiled_graph = self.graph.compile(checkpointer=self.checkpointer)
    
    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 状态图"""
        workflow = StateGraph(RAGState)
        
        # 添加节点
        workflow.add_node("intent_analysis", self._intent_analysis_node)
        workflow.add_node("simple_retrieval", self._simple_retrieval_node)
        workflow.add_node("complex_retrieval", self._complex_retrieval_node)
        workflow.add_node("multi_hop_reasoning", self._multi_hop_reasoning_node)
        workflow.add_node("answer_generation", self._answer_generation_node)
        workflow.add_node("quality_check", self._quality_check_node)
        workflow.add_node("answer_refinement", self._answer_refinement_node)
        workflow.add_node("finalize", self._finalize_node)
        
        # 设置入口
        workflow.set_entry_point("intent_analysis")
        
        # 意图识别后路由
        workflow.add_conditional_edges(
            "intent_analysis",
            self._route_by_intent,
            {
                "simple": "simple_retrieval",
                "complex": "complex_retrieval",
                "generation": END  # 文档生成走另一个流程
            }
        )
        
        # 简单检索后生成答案
        workflow.add_edge("simple_retrieval", "answer_generation")
        
        # 复杂检索需要判断是否多跳推理
        workflow.add_conditional_edges(
            "complex_retrieval",
            self._needs_multi_hop,
            {
                "yes": "multi_hop_reasoning",
                "no": "answer_generation"
            }
        )
        
        # 多跳推理后生成答案
        workflow.add_edge("multi_hop_reasoning", "answer_generation")
        
        # 答案生成后质量检查
        workflow.add_edge("answer_generation", "quality_check")
        
        # 质量检查后条件路由
        workflow.add_conditional_edges(
            "quality_check",
            self._needs_refinement,
            {
                "yes": "answer_refinement",
                "no": "finalize"
            }
        )
        
        # 改进后再次质量检查
        workflow.add_edge("answer_refinement", "quality_check")
        
        # 最终化后结束
        workflow.add_edge("finalize", END)
        
        return workflow
    
    async def _intent_analysis_node(self, state: RAGState) -> RAGState:
        """节点1: 意图识别"""
        question = state["question"]
        
        prompt = f"""分析以下问题的意图和复杂度：

问题: {question}

判断:
1. 意图类型: simple_qa (简单问答) / complex_reasoning (复杂推理) / document_generation (文档生成)
2. 复杂度: low / medium / high
3. 是否需要多步推理: true / false

仅返回JSON: {{"intent": "...", "complexity": "...", "requires_multi_hop": true/false}}
"""
        
        response = await self.llm.ainvoke(prompt)
        
        try:
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                state["intent"] = analysis.get("intent", "simple_qa")
                state["complexity"] = analysis.get("complexity", "medium")
                state["requires_multi_hop"] = analysis.get("requires_multi_hop", False)
            else:
                state["intent"] = "simple_qa"
                state["complexity"] = "low"
                state["requires_multi_hop"] = False
        except:
            state["intent"] = "simple_qa"
            state["complexity"] = "low"
            state["requires_multi_hop"] = False
        
        # 根据复杂度设置检索策略
        if state["complexity"] == "low":
            state["retrieval_strategy"] = "workspace_only"
        elif state["complexity"] == "medium":
            state["retrieval_strategy"] = "hybrid"
        else:
            state["retrieval_strategy"] = "comprehensive"
        
        state["processing_steps"].append("intent_analysis")
        logger.info(f"意图: {state['intent']}, 复杂度: {state['complexity']}, 策略: {state['retrieval_strategy']}")
        
        return state
    
    async def _simple_retrieval_node(self, state: RAGState) -> RAGState:
        """节点3: 简单检索（单次检索）"""
        question = state["question"]
        workspace_id = state["workspace_id"]
        
        # 并行检索工作区和全局
        workspace_task = self.workspace_retriever.retrieve(
            question, top_k=5, use_hybrid=True, use_compression=True
        )
        global_task = self.global_retriever.retrieve(
            question, top_k=5, use_hybrid=True, use_compression=True
        )
        
        workspace_docs, global_docs = await asyncio.gather(
            workspace_task, global_task, return_exceptions=True
        )
        
        state["workspace_docs"] = workspace_docs if not isinstance(workspace_docs, Exception) else []
        state["global_docs"] = global_docs if not isinstance(global_docs, Exception) else []
        state["processing_steps"].append("simple_retrieval")
        
        logger.info(f"简单检索: 工作区{len(state['workspace_docs'])}个，全局{len(state['global_docs'])}个")
        
        return state
    
    async def _complex_retrieval_node(self, state: RAGState) -> RAGState:
        """节点4: 复杂检索（多次检索+查询扩展）"""
        question = state["question"]
        
        # 1. 查询扩展
        expansion_prompt = f"生成3个与'{question}'语义相关的查询变体，返回JSON数组: [...]"
        response = await self.llm.ainvoke(expansion_prompt)
        
        try:
            json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
            queries = json.loads(json_match.group()) if json_match else [question]
        except:
            queries = [question]
        
        # 2. 并行检索所有查询
        tasks = []
        for q in queries:
            tasks.append(self.workspace_retriever.retrieve(q, top_k=3, use_hybrid=True))
            tasks.append(self.global_retriever.retrieve(q, top_k=3, use_hybrid=True))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 3. 合并去重
        all_docs = []
        seen_ids = set()
        for result in results:
            if not isinstance(result, Exception):
                for doc in result:
                    if doc['node_id'] not in seen_ids:
                        seen_ids.add(doc['node_id'])
                        all_docs.append(doc)
        
        # 按分数排序
        all_docs.sort(key=lambda x: x['score'], reverse=True)
        
        state["workspace_docs"] = all_docs[:10]
        state["global_docs"] = []  # 已合并
        state["processing_steps"].append("complex_retrieval")
        
        logger.info(f"复杂检索: 共{len(all_docs)}个文档")
        
        return state
    
    async def _multi_hop_reasoning_node(self, state: RAGState) -> RAGState:
        """节点5: 多跳推理"""
        question = state["question"]
        docs = state["workspace_docs"] + state["global_docs"]
        
        # 第一跳：从初始文档生成子问题
        context1 = "\n".join([d['content'][:200] for d in docs[:5]])
        
        sub_question_prompt = f"""基于以下上下文和问题，生成1-2个需要进一步查询的子问题：

问题: {question}
上下文: {context1}

子问题（JSON数组）: [...]
"""
        
        response = await self.llm.ainvoke(sub_question_prompt)
        
        try:
            json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
            sub_questions = json.loads(json_match.group()) if json_match else []
        except:
            sub_questions = []
        
        # 第二跳：检索子问题
        if sub_questions:
            tasks = [
                self.workspace_retriever.retrieve(sq, top_k=3, use_hybrid=True)
                for sq in sub_questions
            ]
            sub_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in sub_results:
                if not isinstance(result, Exception):
                    state["workspace_docs"].extend(result)
        
        state["processing_steps"].append("multi_hop_reasoning")
        logger.info(f"多跳推理: {len(sub_questions)}个子问题")
        
        return state
    
    async def _answer_generation_node(self, state: RAGState) -> RAGState:
        """节点6: 答案生成"""
        question = state["question"]
        all_docs = state["workspace_docs"] + state["global_docs"]
        
        # 构建上下文
        context = "\n\n---\n\n".join([
            f"文档{i+1} (相关度: {d['score']:.2f}):\n{d['content']}"
            for i, d in enumerate(all_docs[:5])
        ])
        
        answer_prompt = f"""基于以下上下文回答问题：

上下文:
{context}

问题: {question}

要求:
1. 回答准确、详细
2. 引用具体文档
3. 如果信息不足，明确说明

回答:
"""
        
        response = await self.llm.ainvoke(answer_prompt)
        state["draft_answer"] = response.content
        state["sources_used"] = [d['metadata'].get('filename', '') for d in all_docs[:5]]
        state["processing_steps"].append("answer_generation")
        
        return state
    
    async def _quality_check_node(self, state: RAGState) -> RAGState:
        """节点7: 质量检查"""
        question = state["question"]
        answer = state["draft_answer"]
        
        quality_prompt = f"""评估以下答案的质量（0-1分）：

问题: {question}
答案: {answer}

评分JSON: {{"score": 0.0-1.0, "needs_improvement": true/false, "issues": ["..."]}}
"""
        
        response = await self.llm.ainvoke(quality_prompt)
        
        try:
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                quality = json.loads(json_match.group())
                state["quality_score"] = quality.get("score", 0.7)
                state["needs_refinement"] = quality.get("needs_improvement", False)
            else:
                state["quality_score"] = 0.7
                state["needs_refinement"] = False
        except:
            state["quality_score"] = 0.7
            state["needs_refinement"] = False
        
        state["iteration_count"] += 1
        state["processing_steps"].append("quality_check")
        
        logger.info(f"质量分数: {state['quality_score']}")
        
        return state
    
    async def _answer_refinement_node(self, state: RAGState) -> RAGState:
        """节点8: 答案改进"""
        draft = state["draft_answer"]
        
        refinement_prompt = f"""改进以下答案，使其更准确、完整、清晰：

原答案: {draft}

改进后的答案:
"""
        
        response = await self.llm.ainvoke(refinement_prompt)
        state["draft_answer"] = response.content
        state["processing_steps"].append("answer_refinement")
        
        return state
    
    async def _finalize_node(self, state: RAGState) -> RAGState:
        """节点9: 最终化"""
        state["final_answer"] = state["draft_answer"]
        state["processing_steps"].append("finalize")
        
        return state
    
    # 条件路由函数
    def _route_by_intent(self, state: RAGState) -> str:
        """根据意图路由"""
        intent = state.get("intent", "simple_qa")
        if intent == "document_generation":
            return "generation"
        elif intent == "complex_reasoning":
            return "complex"
        else:
            return "simple"
    
    def _needs_multi_hop(self, state: RAGState) -> str:
        """判断是否需要多跳推理"""
        return "yes" if state.get("requires_multi_hop", False) else "no"
    
    def _needs_refinement(self, state: RAGState) -> str:
        """判断是否需要改进答案"""
        quality_score = state.get("quality_score", 0)
        iteration_count = state.get("iteration_count", 0)
        needs_refinement = state.get("needs_refinement", False)
        
        if needs_refinement and quality_score < 0.8 and iteration_count < 2:
            return "yes"
        else:
            return "no"
    
    async def run(self, question: str, workspace_id: str = "global") -> Dict:
        """执行工作流"""
        initial_state = RAGState(
            question=question,
            workspace_id=workspace_id,
            conversation_history=[],
            intent="",
            complexity="",
            requires_multi_hop=False,
            workspace_docs=[],
            global_docs=[],
            web_results=[],
            draft_answer="",
            final_answer="",
            quality_score=0.0,
            needs_refinement=False,
            iteration_count=0,
            retrieval_strategy="",
            sources_used=[],
            processing_steps=[]
        )
        
        final_state = await self.compiled_graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": "1"}}
        )
        
        return {
            "answer": final_state["final_answer"],
            "sources": final_state["sources_used"],
            "metadata": {
                "intent": final_state["intent"],
                "complexity": final_state["complexity"],
                "quality_score": final_state["quality_score"],
                "iterations": final_state["iteration_count"],
                "processing_steps": final_state["processing_steps"],
                "retrieval_strategy": final_state["retrieval_strategy"]
            }
        }

