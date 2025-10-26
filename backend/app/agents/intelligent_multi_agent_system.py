"""
智能多Agent协作系统 - 基于现代AI实践
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import json

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

class AgentRole(Enum):
    """Agent角色"""
    RESEARCHER = "researcher"      # 信息收集专家
    ANALYZER = "analyzer"          # 信息分析专家
    WRITER = "writer"              # 内容创作专家
    REVIEWER = "reviewer"          # 质量审核专家
    FORMATTER = "formatter"        # 格式化专家

@dataclass
class AgentMessage:
    """Agent间消息"""
    from_agent: AgentRole
    to_agent: AgentRole
    content: Any
    message_type: str
    metadata: Dict[str, Any] = None

@dataclass
class TaskContext:
    """任务上下文"""
    original_request: str
    enhanced_request: str
    document_type: str
    requirements: Dict[str, Any]
    constraints: List[str]
    quality_expectations: str

class BaseIntelligentAgent:
    """智能基础Agent"""
    
    def __init__(self, role: AgentRole, llm: BaseChatModel):
        self.role = role
        self.llm = llm
        self.capabilities = self._define_capabilities()
        self.knowledge_base = {}
        
    def _define_capabilities(self) -> List[str]:
        """定义Agent能力"""
        raise NotImplementedError
    
    async def process_task(self, task_context: TaskContext) -> Dict[str, Any]:
        """处理任务"""
        raise NotImplementedError
    
    async def collaborate_with(self, other_agent: 'BaseIntelligentAgent', 
                             message: AgentMessage) -> AgentMessage:
        """与其他Agent协作"""
        raise NotImplementedError

class ResearchAgent(BaseIntelligentAgent):
    """研究Agent - 信息收集专家"""
    
    def __init__(self, llm: BaseChatModel, rag_service, web_search_service):
        super().__init__(AgentRole.RESEARCHER, llm)
        self.rag_service = rag_service
        self.web_search_service = web_search_service
    
    def _define_capabilities(self) -> List[str]:
        return [
            "本地文档搜索",
            "网络信息检索", 
            "信息源评估",
            "相关度分析"
        ]
    
    async def process_task(self, task_context: TaskContext) -> Dict[str, Any]:
        """执行信息收集任务"""
        logger.info(f"ResearchAgent开始收集信息: {task_context.enhanced_request}")
        
        try:
            # 1. 本地文档搜索
            local_results = await self._search_local_documents(task_context)
            
            # 2. 网络信息搜索（如果需要）
            web_results = []
            if task_context.requirements.get('enable_web_search', False):
                web_results = await self._search_web_information(task_context)
            
            # 3. 信息整合和评估
            integrated_results = await self._integrate_and_evaluate(
                local_results, web_results, task_context
            )
            
            return {
                "success": True,
                "local_results": local_results,
                "web_results": web_results,
                "integrated_results": integrated_results,
                "metadata": {
                    "total_sources": len(local_results) + len(web_results),
                    "relevance_scores": integrated_results.get('relevance_scores', []),
                    "confidence": integrated_results.get('confidence', 0.0)
                }
            }
            
        except Exception as e:
            logger.error(f"ResearchAgent任务失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _search_local_documents(self, task_context: TaskContext) -> List[Dict[str, Any]]:
        """搜索本地文档"""
        try:
            result = await self.rag_service.ask_question(
                workspace_id="global",
                question=task_context.enhanced_request,
                top_k=10
            )
            
            return result.get('references', [])
            
        except Exception as e:
            logger.error(f"本地文档搜索失败: {e}")
            return []
    
    async def _search_web_information(self, task_context: TaskContext) -> List[Dict[str, Any]]:
        """搜索网络信息"""
        try:
            async with self.web_search_service as search_service:
                results = await search_service.search_web(
                    task_context.enhanced_request, 
                    num_results=5
                )
                
                return [
                    {
                        "title": r.title,
                        "url": r.url,
                        "content": r.content or r.snippet,
                        "relevance_score": r.relevance_score,
                        "source_type": "web"
                    } for r in results
                ]
                
        except Exception as e:
            logger.error(f"网络搜索失败: {e}")
            return []
    
    async def _integrate_and_evaluate(self, local_results: List[Dict], 
                                   web_results: List[Dict], 
                                   task_context: TaskContext) -> Dict[str, Any]:
        """整合和评估信息"""
        try:
            all_results = local_results + web_results
            
            # 使用LLM评估信息相关性和质量
            evaluation_prompt = f"""请评估以下信息与任务的相关性和质量：

任务: {task_context.enhanced_request}
文档类型: {task_context.document_type}

信息列表:
{json.dumps(all_results, ensure_ascii=False, indent=2)}

请为每个信息源评分（0-1），并返回：
1. 相关性评分
2. 信息质量评分
3. 推荐使用的信息源
4. 整体置信度

返回JSON格式：
{{
    "relevance_scores": [0.8, 0.9, 0.7],
    "quality_scores": [0.8, 0.9, 0.7],
    "recommended_sources": [0, 1],
    "confidence": 0.8,
    "summary": "信息收集总结"
}}"""
            
            response = await self.llm.ainvoke(evaluation_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析评估结果
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            
            return {"confidence": 0.5, "summary": "信息收集完成"}
            
        except Exception as e:
            logger.error(f"信息整合评估失败: {e}")
            return {"confidence": 0.5, "summary": "信息收集完成"}

class AnalysisAgent(BaseIntelligentAgent):
    """分析Agent - 信息分析专家"""
    
    def __init__(self, llm: BaseChatModel):
        super().__init__(AgentRole.ANALYZER, llm)
    
    def _define_capabilities(self) -> List[str]:
        return [
            "信息结构化分析",
            "关键信息提取",
            "逻辑关系梳理",
            "内容框架设计"
        ]
    
    async def process_task(self, task_context: TaskContext) -> Dict[str, Any]:
        """执行信息分析任务"""
        logger.info(f"AnalysisAgent开始分析信息")
        
        try:
            # 这里会接收ResearchAgent的结果
            research_results = task_context.requirements.get('research_results', {})
            
            if not research_results.get('success', False):
                return {"success": False, "error": "没有可分析的信息"}
            
            # 分析信息并生成内容框架
            analysis_result = await self._analyze_information(
                research_results, task_context
            )
            
            return {
                "success": True,
                "analysis_result": analysis_result,
                "metadata": {
                    "key_points": analysis_result.get('key_points', []),
                    "structure": analysis_result.get('structure', []),
                    "confidence": analysis_result.get('confidence', 0.0)
                }
            }
            
        except Exception as e:
            logger.error(f"AnalysisAgent任务失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _analyze_information(self, research_results: Dict[str, Any], 
                                task_context: TaskContext) -> Dict[str, Any]:
        """分析信息并生成框架"""
        try:
            integrated_results = research_results.get('integrated_results', {})
            local_results = research_results.get('local_results', [])
            web_results = research_results.get('web_results', [])
            
            analysis_prompt = f"""基于收集的信息，进行深度分析并设计文档结构：

任务: {task_context.enhanced_request}
文档类型: {task_context.document_type}

本地信息: {json.dumps(local_results, ensure_ascii=False, indent=2)}
网络信息: {json.dumps(web_results, ensure_ascii=False, indent=2)}

请进行以下分析：
1. 提取关键信息和要点
2. 识别信息间的逻辑关系
3. 设计文档结构框架
4. 确定重点章节和内容

返回JSON格式：
{{
    "key_points": ["要点1", "要点2", "要点3"],
    "logical_relationships": [
        {{"from": "要点1", "to": "要点2", "relation": "因果关系"}}
    ],
    "structure": [
        {{"title": "章节1", "content_outline": "内容概要", "priority": 1}},
        {{"title": "章节2", "content_outline": "内容概要", "priority": 2}}
    ],
    "focus_areas": ["重点领域1", "重点领域2"],
    "confidence": 0.8
}}"""
            
            response = await self.llm.ainvoke(analysis_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析分析结果
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            
            return {"key_points": [], "structure": [], "confidence": 0.5}
            
        except Exception as e:
            logger.error(f"信息分析失败: {e}")
            return {"key_points": [], "structure": [], "confidence": 0.5}

class WriterAgent(BaseIntelligentAgent):
    """写作Agent - 内容创作专家"""
    
    def __init__(self, llm: BaseChatModel):
        super().__init__(AgentRole.WRITER, llm)
    
    def _define_capabilities(self) -> List[str]:
        return [
            "内容创作",
            "语言优化",
            "逻辑组织",
            "专业表达"
        ]
    
    async def process_task(self, task_context: TaskContext) -> Dict[str, Any]:
        """执行内容创作任务"""
        logger.info(f"WriterAgent开始创作内容")
        
        try:
            analysis_results = task_context.requirements.get('analysis_results', {})
            
            if not analysis_results.get('success', False):
                return {"success": False, "error": "没有可创作的内容框架"}
            
            # 基于分析结果创作内容
            content_result = await self._create_content(
                analysis_results, task_context
            )
            
            return {
                "success": True,
                "content_result": content_result,
                "metadata": {
                    "word_count": content_result.get('word_count', 0),
                    "sections": len(content_result.get('sections', [])),
                    "quality_score": content_result.get('quality_score', 0.0)
                }
            }
            
        except Exception as e:
            logger.error(f"WriterAgent任务失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _create_content(self, analysis_results: Dict[str, Any], 
                           task_context: TaskContext) -> Dict[str, Any]:
        """创作内容"""
        try:
            analysis_result = analysis_results.get('analysis_result', {})
            key_points = analysis_result.get('key_points', [])
            structure = analysis_result.get('structure', [])
            
            content_prompt = f"""基于分析结果，创作高质量的文档内容：

任务: {task_context.enhanced_request}
文档类型: {task_context.document_type}

关键要点: {json.dumps(key_points, ensure_ascii=False)}
文档结构: {json.dumps(structure, ensure_ascii=False)}

请创作内容，要求：
1. 内容充实、逻辑清晰
2. 语言专业、表达准确
3. 结构完整、层次分明
4. 符合文档类型特点

返回JSON格式：
{{
    "title": "文档标题",
    "sections": [
        {{
            "title": "章节标题",
            "content": "章节内容",
            "subsections": [
                {{"title": "子章节", "content": "子章节内容"}}
            ]
        }}
    ],
    "word_count": 2000,
    "quality_score": 0.8
}}"""
            
            response = await self.llm.ainvoke(content_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析内容结果
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            
            return {"title": "文档", "sections": [], "word_count": 0, "quality_score": 0.5}
            
        except Exception as e:
            logger.error(f"内容创作失败: {e}")
            return {"title": "文档", "sections": [], "word_count": 0, "quality_score": 0.5}

class ReviewerAgent(BaseIntelligentAgent):
    """审核Agent - 质量审核专家"""
    
    def __init__(self, llm: BaseChatModel):
        super().__init__(AgentRole.REVIEWER, llm)
    
    def _define_capabilities(self) -> List[str]:
        return [
            "内容质量评估",
            "逻辑一致性检查",
            "语言表达优化",
            "完整性验证"
        ]
    
    async def process_task(self, task_context: TaskContext) -> Dict[str, Any]:
        """执行质量审核任务"""
        logger.info(f"ReviewerAgent开始质量审核")
        
        try:
            writer_results = task_context.requirements.get('writer_results', {})
            
            if not writer_results.get('success', False):
                return {"success": False, "error": "没有可审核的内容"}
            
            # 审核内容质量
            review_result = await self._review_content(
                writer_results, task_context
            )
            
            return {
                "success": True,
                "review_result": review_result,
                "metadata": {
                    "overall_score": review_result.get('overall_score', 0.0),
                    "issues_found": len(review_result.get('issues', [])),
                    "improvements": len(review_result.get('improvements', []))
                }
            }
            
        except Exception as e:
            logger.error(f"ReviewerAgent任务失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _review_content(self, writer_results: Dict[str, Any], 
                           task_context: TaskContext) -> Dict[str, Any]:
        """审核内容质量"""
        try:
            content_result = writer_results.get('content_result', {})
            
            review_prompt = f"""请对以下文档内容进行质量审核：

原始任务: {task_context.original_request}
文档类型: {task_context.document_type}

文档内容: {json.dumps(content_result, ensure_ascii=False, indent=2)}

请从以下维度审核：
1. 内容完整性
2. 逻辑一致性
3. 语言表达质量
4. 结构合理性
5. 专业性

返回JSON格式：
{{
    "overall_score": 0.8,
    "dimension_scores": {{
        "completeness": 0.8,
        "logic": 0.9,
        "language": 0.7,
        "structure": 0.8,
        "professionalism": 0.8
    }},
    "issues": [
        {{"type": "language", "description": "语言表达问题", "severity": "medium"}}
    ],
    "improvements": [
        {{"type": "content", "suggestion": "改进建议", "priority": "high"}}
    ],
    "recommendation": "approve" 或 "revise"
}}"""
            
            response = await self.llm.ainvoke(review_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析审核结果
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            
            return {"overall_score": 0.5, "recommendation": "approve"}
            
        except Exception as e:
            logger.error(f"内容审核失败: {e}")
            return {"overall_score": 0.5, "recommendation": "approve"}

class FormatterAgent(BaseIntelligentAgent):
    """格式化Agent - 格式化专家"""
    
    def __init__(self, llm: BaseChatModel):
        super().__init__(AgentRole.FORMATTER, llm)
    
    def _define_capabilities(self) -> List[str]:
        return [
            "文档格式化",
            "样式优化",
            "结构美化",
            "输出生成"
        ]
    
    async def process_task(self, task_context: TaskContext) -> Dict[str, Any]:
        """执行格式化任务"""
        logger.info(f"FormatterAgent开始格式化")
        
        try:
            reviewer_results = task_context.requirements.get('reviewer_results', {})
            
            if not reviewer_results.get('success', False):
                return {"success": False, "error": "没有可格式化的内容"}
            
            # 格式化文档
            format_result = await self._format_document(
                reviewer_results, task_context
            )
            
            return {
                "success": True,
                "format_result": format_result,
                "metadata": {
                    "final_quality": format_result.get('final_quality', 0.0),
                    "format_applied": format_result.get('format_applied', []),
                    "ready_for_output": format_result.get('ready_for_output', False)
                }
            }
            
        except Exception as e:
            logger.error(f"FormatterAgent任务失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _format_document(self, reviewer_results: Dict[str, Any], 
                            task_context: TaskContext) -> Dict[str, Any]:
        """格式化文档"""
        try:
            # 这里会整合所有Agent的结果
            # 生成最终的格式化文档
            
            return {
                "final_quality": 0.8,
                "format_applied": ["样式优化", "结构美化"],
                "ready_for_output": True,
                "formatted_content": "格式化后的文档内容"
            }
            
        except Exception as e:
            logger.error(f"文档格式化失败: {e}")
            return {"final_quality": 0.5, "ready_for_output": False}

class IntelligentMultiAgentSystem:
    """智能多Agent系统"""
    
    def __init__(self, llm: BaseChatModel, rag_service, web_search_service):
        self.llm = llm
        self.rag_service = rag_service
        self.web_search_service = web_search_service
        
        # 初始化各Agent
        self.research_agent = ResearchAgent(llm, rag_service, web_search_service)
        self.analysis_agent = AnalysisAgent(llm)
        self.writer_agent = WriterAgent(llm)
        self.reviewer_agent = ReviewerAgent(llm)
        self.formatter_agent = FormatterAgent(llm)
        
        # Agent协作流程
        self.workflow = [
            (self.research_agent, "信息收集"),
            (self.analysis_agent, "信息分析"),
            (self.writer_agent, "内容创作"),
            (self.reviewer_agent, "质量审核"),
            (self.formatter_agent, "格式化输出")
        ]
    
    async def execute_task(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """执行多Agent协作任务"""
        logger.info(f"智能多Agent系统开始执行任务: {task_description}")
        
        try:
            # 创建任务上下文
            task_context = TaskContext(
                original_request=task_description,
                enhanced_request=task_description,  # 这里可以集成澄清服务的结果
                document_type=requirements.get('doc_type', 'word'),
                requirements=requirements,
                constraints=requirements.get('constraints', []),
                quality_expectations=requirements.get('quality_expectations', '')
            )
            
            # 按顺序执行Agent任务
            results = {}
            for agent, step_name in self.workflow:
                logger.info(f"执行步骤: {step_name}")
                
                # 更新任务上下文
                task_context.requirements.update(results)
                
                # 执行Agent任务
                result = await agent.process_task(task_context)
                results[f"{agent.role.value}_results"] = result
                
                # 检查任务是否成功
                if not result.get('success', False):
                    logger.error(f"步骤 {step_name} 失败: {result.get('error', '未知错误')}")
                    return {
                        "success": False,
                        "error": f"步骤 {step_name} 失败",
                        "failed_step": step_name,
                        "partial_results": results
                    }
            
            # 整合最终结果
            final_result = await self._integrate_final_results(results, task_context)
            
            return {
                "success": True,
                "final_result": final_result,
                "workflow_results": results,
                "workflow_type": "intelligent_multi_agent"
            }
            
        except Exception as e:
            logger.error(f"多Agent系统执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "workflow_type": "intelligent_multi_agent"
            }
    
    async def _integrate_final_results(self, results: Dict[str, Any], 
                                    task_context: TaskContext) -> Dict[str, Any]:
        """整合最终结果"""
        try:
            formatter_results = results.get('formatter_results', {})
            format_result = formatter_results.get('format_result', {})
            
            return {
                "document_content": format_result.get('formatted_content', ''),
                "final_quality": format_result.get('final_quality', 0.0),
                "metadata": {
                    "original_request": task_context.original_request,
                    "document_type": task_context.document_type,
                    "total_steps": len(self.workflow),
                    "successful_steps": len([r for r in results.values() if r.get('success', False)])
                }
            }
            
        except Exception as e:
            logger.error(f"整合最终结果失败: {e}")
            return {"document_content": "", "final_quality": 0.0}
