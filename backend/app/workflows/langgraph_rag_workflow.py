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
    intent: str  # "greeting" | "simple_qa" | "complex_reasoning" | "document_generation"
    complexity: str  # "low" | "medium" | "high"
    requires_multi_hop: bool
    needs_retrieval: bool  # 是否需要检索文档
    
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
            # 从环境变量读取模型名称，默认使用 gpt-4o
            model_name = os.getenv('LLM_MODEL', 'gpt-4o-2024-08-06')
            self.llm = ChatOpenAI(
                model=model_name,
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
    
    def _sanitize_docs(self, docs: list) -> list:
        """清理文档列表，确保所有值都可以被 msgpack 序列化"""
        if not docs:
            return []
        
        sanitized = []
        for doc in docs:
            sanitized_doc = {}
            for key, value in doc.items():
                if key == 'score':
                    # 确保 score 是 float 类型
                    if hasattr(value, 'item'):
                        sanitized_doc[key] = float(value.item())
                    else:
                        sanitized_doc[key] = float(value)
                elif isinstance(value, dict):
                    # 递归清理 metadata 等字典
                    sanitized_doc[key] = {k: self._sanitize_value(v) for k, v in value.items()}
                else:
                    sanitized_doc[key] = self._sanitize_value(value)
            sanitized.append(sanitized_doc)
        return sanitized
    
    def _sanitize_value(self, value):
        """清理单个值，转换 numpy 类型"""
        import numpy as np
        if isinstance(value, (np.integer, np.floating)):
            return value.item()
        elif isinstance(value, np.ndarray):
            return value.tolist()
        elif isinstance(value, dict):
            return {k: self._sanitize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._sanitize_value(v) for v in value]
        else:
            return value
    
    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 状态图"""
        workflow = StateGraph(RAGState)
        
        # 添加节点
        workflow.add_node("intent_analysis", self._intent_analysis_node)
        workflow.add_node("simple_retrieval", self._simple_retrieval_node)
        workflow.add_node("complex_retrieval", self._complex_retrieval_node)
        workflow.add_node("multi_hop_reasoning", self._multi_hop_reasoning_node)
        workflow.add_node("direct_answer", self._direct_answer_node)
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
                "no_retrieval": "direct_answer",  # 不需要检索，直接回答（包括问候和文档生成提示）
                "simple": "simple_retrieval",
                "complex": "complex_retrieval"
            }
        )
        
        # 直接回答后跳过检索和质量检查
        workflow.add_edge("direct_answer", "finalize")
        
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
1. 意图类型: 
   - greeting (问候、闲聊，如"你好"、"谢谢"、"再见"等)
   - simple_qa (简单问答，需要检索文档)
   - complex_reasoning (复杂推理，需要多步检索和推理)
   - document_generation (文档生成)

2. 是否需要检索文档:
   - 对于问候语、闲聊、通用问题，返回 needs_retrieval: false
   - 对于需要从文档中查找答案的问题，返回 needs_retrieval: true

3. 复杂度: low / medium / high (仅在需要检索时有效)

4. 是否需要多步推理: true / false (仅在需要检索时有效)

示例:
- 问题:"你好" → intent: "greeting", needs_retrieval: false
- 问题:"idea-gp是什么" → intent: "simple_qa", needs_retrieval: true, complexity: "low"
- 问题:"比较A和B的区别" → intent: "complex_reasoning", needs_retrieval: true, complexity: "high", requires_multi_hop: true

仅返回JSON: {{"intent": "...", "needs_retrieval": true/false, "complexity": "...", "requires_multi_hop": true/false}}
"""
        
        response = await self.llm.ainvoke(prompt)
        
        try:
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                state["intent"] = analysis.get("intent", "simple_qa")
                needs_retrieval = analysis.get("needs_retrieval", True)
                state["complexity"] = analysis.get("complexity", "medium")
                state["requires_multi_hop"] = analysis.get("requires_multi_hop", False)
                
                # 保存是否需要检索的标志
                state["needs_retrieval"] = needs_retrieval
                
                # 如果是问候语且不需要检索，复杂度设为low
                if not needs_retrieval:
                    state["complexity"] = "low"
            else:
                state["intent"] = "simple_qa"
                state["complexity"] = "low"
                state["requires_multi_hop"] = False
                state["needs_retrieval"] = True
        except Exception as e:
            logger.error(f"意图识别解析失败: {e}")
            state["intent"] = "simple_qa"
            state["complexity"] = "low"
            state["requires_multi_hop"] = False
            state["needs_retrieval"] = True
        
        state["processing_steps"].append("intent_analysis")
        logger.info(f"意图: {state['intent']}, 复杂度: {state['complexity']}, 需要检索: {state.get('needs_retrieval', True)}")
        
        return state
    
    async def _route_strategy_node(self, state: RAGState) -> RAGState:
        """节点2: 路由策略（可选，用于更细粒度控制）"""
        # 根据意图和复杂度决定检索策略
        if state["complexity"] == "low":
            state["retrieval_strategy"] = "workspace_only"
        elif state["complexity"] == "medium":
            state["retrieval_strategy"] = "hybrid"
        else:
            state["retrieval_strategy"] = "comprehensive"
        
        return state
    
    async def _direct_answer_node(self, state: RAGState) -> RAGState:
        """直接回答节点（不需要检索）"""
        question = state["question"]
        intent = state.get("intent", "")
        
        # 如果是文档生成意图，给出特殊提示
        if intent == "document_generation":
            prompt = f"""用户想要生成文档。

用户请求: {question}

请用友好、专业的语气告诉用户：

您当前使用的是"智能问答"功能，主要用于回答问题和查询文档内容。

如需生成长文档（如报告、方案、文档等），请按以下步骤操作：
1. 切换到系统顶部的"长文档生成"界面
2. 在长文档生成界面中，您可以：
   - 指定任务描述和目标字数
   - 选择合适的写作风格
   - 生成高质量的长文档（通常2-5万字）

长文档生成功能基于 DeepResearch 技术，会自动检索资料、组织内容并生成专业文档。

请简洁友好地给出上述提示（约100-150字）。
"""
        else:
            # 普通问候或闲聊
            prompt = f"""你是友好的AI助手。回答用户的以下问题，要求简洁友好：

问题: {question}

请给出简洁友好的回答。如果问题涉及文档查询、技术细节或需要检索的信息，请礼貌地说明需要具体查询相关文档。
"""
        
        response = await self.llm.ainvoke(prompt)
        state["draft_answer"] = response.content
        state["sources_used"] = []
        state["processing_steps"].append("direct_answer")
        
        logger.info(f"直接回答，跳过检索 (意图: {intent})")
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
        
        state["workspace_docs"] = self._sanitize_docs(workspace_docs) if not isinstance(workspace_docs, Exception) else []
        state["global_docs"] = self._sanitize_docs(global_docs) if not isinstance(global_docs, Exception) else []
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
        
        state["workspace_docs"] = self._sanitize_docs(all_docs[:10])
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
                    state["workspace_docs"].extend(self._sanitize_docs(result))
        
        state["processing_steps"].append("multi_hop_reasoning")
        logger.info(f"多跳推理: {len(sub_questions)}个子问题")
        
        return state
    
    async def _answer_generation_node(self, state: RAGState) -> RAGState:
        """节点6: 答案生成"""
        question = state["question"]
        all_docs = state["workspace_docs"] + state["global_docs"]
        
        # 构建上下文（包含文档元数据）
        context = "\n\n---\n\n".join([
            f"【文档{i+1}】(相关度: {d['score']:.2f})\n" +
            (f"来源: {d.get('metadata', {}).get('original_filename', d.get('metadata', {}).get('filename', '未知文档'))}\n" if d.get('metadata', {}).get('original_filename') or d.get('metadata', {}).get('filename') else "") +
            f"内容:\n{d['content']}"
            for i, d in enumerate(all_docs[:5])
        ])
        
        answer_prompt = f"""基于以下上下文回答问题：

上下文:
{context}

问题: {question}

**重要要求**:
1. **理解数据结构** - 特别注意表格数据中的层级关系
2. **理解问题语义** - 仔细理解用户问题的真正意图，不要机械地列举所有文档
3. **判断相关性** - 只使用与问题真正相关的文档内容，忽略不相关的细节
4. **优先使用高质量内容** - 优先使用相关度高（score高）且语义匹配的内容
5. **引用具体文档** - 明确指出信息来源，如"根据文档1..."、"文档2显示..."
6. 回答准确、详细
7. 如果信息不足，明确说明

**特别注意**：
- 如果某些文档只包含辅助信息（如开支明细、预算清单等），但与核心问题无关，不要硬性包含
- 优先回答直接回答问题的内容，次要信息可以忽略
- 确保回答聚焦于用户真正关心的问题

回答:
"""
        
        response = await self.llm.ainvoke(answer_prompt)
        state["draft_answer"] = response.content
        
        # 构建详细的引用来源信息
        state["sources_used"] = []
        for i, doc in enumerate(all_docs[:5]):
            metadata = doc.get('metadata', {})
            
            # 尝试多种可能的字段名
            filename = (
                metadata.get('original_filename') or 
                metadata.get('filename') or 
                metadata.get('file_name') or
                metadata.get('document_name') or
                f'文档{i+1}'
            )
            
            source = {
                "index": i + 1,
                "filename": filename,
                "content": doc['content'][:200] + "..." if len(doc['content']) > 200 else doc['content'],
                "full_content": doc['content'],
                "score": round(doc['score'], 2),
                "metadata": metadata
            }
            state["sources_used"].append(source)
        
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
        needs_retrieval = state.get("needs_retrieval", True)
        
        # 文档生成意图也走直接回答（会提示使用专门功能）
        if intent == "document_generation":
            return "no_retrieval"
        
        # 如果不需要检索（如问候语），直接回答
        if not needs_retrieval:
            return "no_retrieval"
        
        if intent == "complex_reasoning":
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
            needs_retrieval=True,
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

