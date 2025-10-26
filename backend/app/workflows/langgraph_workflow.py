"""
LangGraph状态机工作流
使用LangGraph实现复杂的状态机工作流
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, TypedDict
from dataclasses import dataclass
import json

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

# 尝试导入LangGraph，如果失败则使用简化版本
try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.warning("LangGraph不可用，将使用简化版本")

class DocumentGenState(TypedDict):
    """文档生成状态"""
    intent: Dict[str, Any]
    plan: List[Dict[str, Any]]
    collected_info: List[Dict[str, Any]]
    draft_content: str
    quality_score: float
    final_document: Dict[str, Any]
    current_step: str
    error: Optional[str]
    iteration_count: int

class LangGraphWorkflow:
    """LangGraph状态机工作流"""
    
    def __init__(self, llm: BaseChatModel, rag_service, web_search_service):
        self.llm = llm
        self.rag_service = rag_service
        self.web_search_service = web_search_service
        self.max_iterations = 5
        
        if LANGGRAPH_AVAILABLE:
            self.graph = self._build_graph()
        else:
            self.graph = None
            logger.warning("使用简化版工作流")
    
    def _build_graph(self):
        """构建LangGraph状态图"""
        if not LANGGRAPH_AVAILABLE:
            return None
        
        try:
            # 创建状态图
            workflow = StateGraph(DocumentGenState)
            
            # 添加节点
            workflow.add_node("intent_recognition", self._intent_recognition_node)
            workflow.add_node("plan_generation", self._plan_generation_node)
            workflow.add_node("information_collection", self._information_collection_node)
            workflow.add_node("content_generation", self._content_generation_node)
            workflow.add_node("quality_assessment", self._quality_assessment_node)
            workflow.add_node("content_refinement", self._content_refinement_node)
            workflow.add_node("final_formatting", self._final_formatting_node)
            
            # 设置入口点
            workflow.set_entry_point("intent_recognition")
            
            # 添加边
            workflow.add_edge("intent_recognition", "plan_generation")
            workflow.add_edge("plan_generation", "information_collection")
            workflow.add_edge("information_collection", "content_generation")
            workflow.add_edge("content_generation", "quality_assessment")
            
            # 条件边
            workflow.add_conditional_edges(
                "quality_assessment",
                self._should_refine,
                {
                    "refine": "content_refinement",
                    "format": "final_formatting",
                    "end": END
                }
            )
            
            workflow.add_edge("content_refinement", "quality_assessment")
            workflow.add_edge("final_formatting", END)
            
            return workflow.compile()
            
        except Exception as e:
            logger.error(f"构建LangGraph失败: {e}")
            return None
    
    async def execute(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行LangGraph工作流
        
        Args:
            task_description: 任务描述
            requirements: 需求参数
            
        Returns:
            执行结果
        """
        logger.info(f"LangGraph工作流开始: {task_description}")
        
        try:
            if self.graph:
                # 使用LangGraph执行
                return await self._execute_with_langgraph(task_description, requirements)
            else:
                # 使用简化版本执行
                return await self._execute_simplified(task_description, requirements)
                
        except Exception as e:
            logger.error(f"LangGraph工作流失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "workflow_type": "langgraph"
            }
    
    async def _execute_with_langgraph(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """使用LangGraph执行"""
        try:
            # 初始化状态
            initial_state = DocumentGenState(
                intent={"description": task_description, "requirements": requirements},
                plan=[],
                collected_info=[],
                draft_content="",
                quality_score=0.0,
                final_document={},
                current_step="intent_recognition",
                error=None,
                iteration_count=0
            )
            
            # 执行图
            final_state = await self.graph.ainvoke(initial_state)
            
            return {
                "success": True,
                "task_description": task_description,
                "final_state": final_state,
                "workflow_type": "langgraph"
            }
            
        except Exception as e:
            logger.error(f"LangGraph执行失败: {e}")
            raise
    
    async def _execute_simplified(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """使用简化版本执行"""
        logger.info("使用简化版LangGraph工作流")
        
        try:
            # 初始化状态
            state = {
                "intent": {"description": task_description, "requirements": requirements},
                "plan": [],
                "collected_info": [],
                "draft_content": "",
                "quality_score": 0.0,
                "final_document": {},
                "current_step": "intent_recognition",
                "error": None,
                "iteration_count": 0
            }
            
            # 按顺序执行各个节点
            steps = [
                ("intent_recognition", self._intent_recognition_node),
                ("plan_generation", self._plan_generation_node),
                ("information_collection", self._information_collection_node),
                ("content_generation", self._content_generation_node),
                ("quality_assessment", self._quality_assessment_node),
                ("final_formatting", self._final_formatting_node)
            ]
            
            for step_name, step_func in steps:
                logger.info(f"执行步骤: {step_name}")
                state["current_step"] = step_name
                
                try:
                    state = await step_func(state)
                    state["iteration_count"] += 1
                except Exception as e:
                    logger.error(f"步骤 {step_name} 失败: {e}")
                    state["error"] = str(e)
                    break
            
            return {
                "success": state.get("error") is None,
                "task_description": task_description,
                "final_state": state,
                "workflow_type": "langgraph_simplified"
            }
            
        except Exception as e:
            logger.error(f"简化版执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "workflow_type": "langgraph_simplified"
            }
    
    async def _intent_recognition_node(self, state: DocumentGenState) -> DocumentGenState:
        """意图识别节点"""
        try:
            task_description = state["intent"]["description"]
            requirements = state["intent"]["requirements"]
            
            prompt = f"""分析以下任务意图：

任务描述: {task_description}
需求参数: {json.dumps(requirements, ensure_ascii=False)}

请分析：
1. 任务类型（文档生成、信息查询、分析报告等）
2. 文档类型偏好
3. 内容深度要求
4. 特殊要求

返回JSON格式：
{{
    "task_type": "文档生成",
    "doc_type": "word",
    "depth_level": "详细",
    "special_requirements": ["要求1", "要求2"],
    "complexity": "中等"
}}"""
            
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析响应
            try:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    intent_analysis = json.loads(json_match.group())
                else:
                    intent_analysis = {"task_type": "文档生成", "complexity": "中等"}
            except:
                intent_analysis = {"task_type": "文档生成", "complexity": "中等"}
            
            # 更新状态
            state["intent"].update(intent_analysis)
            
            logger.info(f"意图识别完成: {intent_analysis.get('task_type', '未知')}")
            return state
            
        except Exception as e:
            logger.error(f"意图识别失败: {e}")
            state["error"] = str(e)
            return state
    
    async def _plan_generation_node(self, state: DocumentGenState) -> DocumentGenState:
        """计划生成节点"""
        try:
            intent = state["intent"]
            task_description = intent["description"]
            
            prompt = f"""基于意图分析生成执行计划：

任务: {task_description}
任务类型: {intent.get('task_type', '文档生成')}
复杂度: {intent.get('complexity', '中等')}

请生成详细的执行计划，包含：
1. 信息收集策略
2. 内容生成方法
3. 质量保证措施
4. 输出格式要求

返回JSON格式：
{{
    "steps": [
        {{
            "name": "步骤名称",
            "description": "步骤描述",
            "method": "执行方法",
            "expected_output": "预期输出"
        }}
    ],
    "quality_criteria": ["标准1", "标准2"],
    "output_format": "word"
}}"""
            
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析响应
            try:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    plan_data = json.loads(json_match.group())
                    state["plan"] = plan_data.get("steps", [])
                else:
                    state["plan"] = [{"name": "信息收集", "description": "收集相关信息"}]
            except:
                state["plan"] = [{"name": "信息收集", "description": "收集相关信息"}]
            
            logger.info(f"计划生成完成，包含 {len(state['plan'])} 个步骤")
            return state
            
        except Exception as e:
            logger.error(f"计划生成失败: {e}")
            state["error"] = str(e)
            return state
    
    async def _information_collection_node(self, state: DocumentGenState) -> DocumentGenState:
        """信息收集节点"""
        try:
            task_description = state["intent"]["description"]
            enable_web_search = state["intent"]["requirements"].get("enable_web_search", False)
            
            collected_info = []
            
            # 1. 收集本地文档信息
            try:
                local_result = await self.rag_service.ask_question(
                    workspace_id="global",
                    question=task_description,
                    top_k=10
                )
                
                if local_result.get('references'):
                    collected_info.append({
                        "source": "local_documents",
                        "type": "document",
                        "data": local_result["references"],
                        "summary": local_result.get("answer", "")
                    })
                    logger.info(f"收集到 {len(local_result['references'])} 个本地文档")
                
            except Exception as e:
                logger.warning(f"本地文档收集失败: {e}")
            
            # 2. 收集网络信息（如果启用）
            if enable_web_search:
                try:
                    async with self.web_search_service as search_service:
                        web_results = await search_service.search_web(task_description, num_results=5)
                        
                        if web_results:
                            collected_info.append({
                                "source": "web_search",
                                "type": "web",
                                "data": [
                                    {
                                        "title": r.title,
                                        "url": r.url,
                                        "content": r.content or r.snippet,
                                        "relevance": r.relevance_score
                                    } for r in web_results
                                ],
                                "summary": f"网络搜索获得 {len(web_results)} 个结果"
                            })
                            logger.info(f"收集到 {len(web_results)} 个网络资源")
                
                except Exception as e:
                    logger.warning(f"网络搜索失败: {e}")
            
            state["collected_info"] = collected_info
            logger.info(f"信息收集完成，共 {len(collected_info)} 个来源")
            return state
            
        except Exception as e:
            logger.error(f"信息收集失败: {e}")
            state["error"] = str(e)
            return state
    
    async def _content_generation_node(self, state: DocumentGenState) -> DocumentGenState:
        """内容生成节点"""
        try:
            collected_info = state["collected_info"]
            intent = state["intent"]
            
            # 构建信息摘要
            info_summary = ""
            for info in collected_info:
                source = info["source"]
                data = info["data"]
                summary = info.get("summary", "")
                
                info_summary += f"\n{source.upper()}:\n{summary}\n"
                
                if isinstance(data, list) and data:
                    for i, item in enumerate(data[:3]):  # 只取前3个
                        if isinstance(item, dict):
                            content = item.get('content', '') or item.get('snippet', '')
                            if content:
                                info_summary += f"- {content[:200]}...\n"
            
            # 生成内容
            prompt = f"""基于收集的信息生成文档内容：

任务描述: {intent['description']}
文档类型: {intent.get('doc_type', 'word')}
复杂度: {intent.get('complexity', '中等')}

收集的信息:
{info_summary}

请生成结构化的文档内容，包含：
1. 清晰的章节结构
2. 详细的内容描述
3. 逻辑清晰的论述
4. 专业的语言表达

确保内容充实、准确、有价值。"""
            
            response = await self.llm.ainvoke(prompt)
            generated_content = response.content if hasattr(response, 'content') else str(response)
            
            state["draft_content"] = generated_content
            logger.info(f"内容生成完成，字数: {len(generated_content.split())}")
            return state
            
        except Exception as e:
            logger.error(f"内容生成失败: {e}")
            state["error"] = str(e)
            return state
    
    async def _quality_assessment_node(self, state: DocumentGenState) -> DocumentGenState:
        """质量评估节点"""
        try:
            content = state["draft_content"]
            
            prompt = f"""评估以下文档内容的质量：

{content}

请从以下维度评估（0-1分）：
1. 内容完整性
2. 逻辑连贯性
3. 信息密度
4. 格式规范性
5. 语言质量

返回JSON格式：
{{
    "completeness": 0.8,
    "coherence": 0.7,
    "information_density": 0.6,
    "format_quality": 0.9,
    "language_quality": 0.8,
    "overall_score": 0.76,
    "needs_improvement": true,
    "improvement_suggestions": ["建议1", "建议2"]
}}"""
            
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析响应
            try:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    quality_data = json.loads(json_match.group())
                    state["quality_score"] = quality_data.get("overall_score", 0.5)
                else:
                    state["quality_score"] = 0.7  # 默认分数
            except:
                state["quality_score"] = 0.7
            
            logger.info(f"质量评估完成，分数: {state['quality_score']}")
            return state
            
        except Exception as e:
            logger.error(f"质量评估失败: {e}")
            state["quality_score"] = 0.5
            return state
    
    async def _content_refinement_node(self, state: DocumentGenState) -> DocumentGenState:
        """内容改进节点"""
        try:
            content = state["draft_content"]
            quality_score = state["quality_score"]
            
            prompt = f"""改进以下文档内容：

当前内容:
{content}

当前质量分数: {quality_score}

请根据质量评估结果改进内容，提升：
1. 内容完整性
2. 逻辑连贯性
3. 信息密度
4. 格式规范性
5. 语言质量

生成改进后的内容。"""
            
            response = await self.llm.ainvoke(prompt)
            improved_content = response.content if hasattr(response, 'content') else str(response)
            
            state["draft_content"] = improved_content
            logger.info("内容改进完成")
            return state
            
        except Exception as e:
            logger.error(f"内容改进失败: {e}")
            return state
    
    async def _final_formatting_node(self, state: DocumentGenState) -> DocumentGenState:
        """最终格式化节点"""
        try:
            content = state["draft_content"]
            doc_type = state["intent"].get("doc_type", "word")
            
            # 格式化内容
            formatted_content = await self._format_content(content, doc_type)
            
            # 创建最终文档
            final_document = {
                "title": f"基于{state['intent']['description'][:20]}的文档",
                "content": formatted_content,
                "doc_type": doc_type,
                "word_count": len(formatted_content.split()),
                "quality_score": state["quality_score"],
                "sources": len(state["collected_info"]),
                "generated_at": asyncio.get_event_loop().time()
            }
            
            state["final_document"] = final_document
            logger.info(f"最终格式化完成，文档类型: {doc_type}")
            return state
            
        except Exception as e:
            logger.error(f"最终格式化失败: {e}")
            state["error"] = str(e)
            return state
    
    async def _format_content(self, content: str, doc_type: str) -> str:
        """格式化内容"""
        try:
            if doc_type.lower() == 'word':
                # Word格式：添加标题层级
                lines = content.split('\n')
                formatted_lines = []
                
                for line in lines:
                    line = line.strip()
                    if line:
                        # 检测标题
                        if (line.startswith('#') or 
                            '概述' in line or '分析' in line or '结论' in line or
                            '第一章' in line or '第二章' in line):
                            formatted_lines.append(f"# {line.replace('#', '').strip()}")
                        else:
                            formatted_lines.append(line)
                
                return '\n'.join(formatted_lines)
            
            elif doc_type.lower() == 'pdf':
                # PDF格式：添加更多结构
                return f"# 文档报告\n\n{content}\n\n---\n*生成时间: {asyncio.get_event_loop().time()}*"
            
            else:
                return content
                
        except Exception as e:
            logger.error(f"内容格式化失败: {e}")
            return content
    
    def _should_refine(self, state: DocumentGenState) -> str:
        """判断是否需要改进"""
        try:
            quality_score = state.get("quality_score", 0)
            iteration_count = state.get("iteration_count", 0)
            
            # 如果质量分数低于0.7且迭代次数少于最大次数，则改进
            if quality_score < 0.7 and iteration_count < self.max_iterations:
                return "refine"
            elif quality_score >= 0.7:
                return "format"
            else:
                return "end"  # 达到最大迭代次数，结束
                
        except Exception as e:
            logger.error(f"判断是否需要改进失败: {e}")
            return "end"
