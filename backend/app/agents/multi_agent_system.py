"""
Multi-Agent协作系统
专业化Agent：ResearchAgent、WriterAgent、ReviewerAgent、CoordinatorAgent
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
    RESEARCHER = "researcher"
    WRITER = "writer"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"

@dataclass
class Task:
    """任务"""
    id: str
    description: str
    assigned_agent: AgentRole
    status: str  # pending, in_progress, completed, failed
    result: Optional[Any] = None
    metadata: Dict[str, Any] = None

@dataclass
class Message:
    """Agent间消息"""
    from_agent: AgentRole
    to_agent: AgentRole
    content: str
    message_type: str  # task_assignment, result, feedback, coordination
    metadata: Dict[str, Any] = None

class BaseAgent:
    """基础Agent类"""
    
    def __init__(self, role: AgentRole, llm: BaseChatModel):
        self.role = role
        self.llm = llm
        self.message_queue = asyncio.Queue()
        self.task_history = []
        
    async def process_message(self, message: Message) -> Optional[Message]:
        """处理消息"""
        raise NotImplementedError
    
    async def execute_task(self, task: Task) -> Any:
        """执行任务"""
        raise NotImplementedError

class ResearchAgent(BaseAgent):
    """研究Agent - 负责信息收集"""
    
    def __init__(self, llm: BaseChatModel, rag_service, web_search_service):
        super().__init__(AgentRole.RESEARCHER, llm)
        self.rag_service = rag_service
        self.web_search_service = web_search_service
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """处理研究任务消息"""
        if message.message_type == "task_assignment":
            task = Task(
                id=f"research_{len(self.task_history)}",
                description=message.content,
                assigned_agent=self.role,
                status="in_progress"
            )
            
            try:
                result = await self.execute_task(task)
                task.status = "completed"
                task.result = result
                self.task_history.append(task)
                
                return Message(
                    from_agent=self.role,
                    to_agent=AgentRole.COORDINATOR,
                    content=f"研究完成: {result}",
                    message_type="result",
                    metadata={"task_id": task.id, "result": result}
                )
            except Exception as e:
                task.status = "failed"
                logger.error(f"研究任务失败: {e}")
                return Message(
                    from_agent=self.role,
                    to_agent=AgentRole.COORDINATOR,
                    content=f"研究失败: {str(e)}",
                    message_type="result",
                    metadata={"task_id": task.id, "error": str(e)}
                )
        
        return None
    
    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """执行研究任务"""
        query = task.description
        
        # 1. 搜索本地文档
        local_results = await self._search_local_documents(query)
        
        # 2. 搜索网络资源
        web_results = await self._search_web_resources(query)
        
        # 3. 整合和评估信息
        integrated_info = await self._integrate_information(local_results, web_results, query)
        
        return {
            "query": query,
            "local_results": local_results,
            "web_results": web_results,
            "integrated_info": integrated_info,
            "summary": await self._generate_research_summary(integrated_info)
        }
    
    async def _search_local_documents(self, query: str) -> List[Dict]:
        """搜索本地文档"""
        try:
            result = await self.rag_service.ask_question(
                workspace_id="global",
                question=query,
                top_k=10
            )
            
            references = result.get('references', [])
            return [{
                'source': 'local_document',
                'title': ref.get('document_name', '未知文档'),
                'content': ref.get('content', ''),
                'relevance': ref.get('similarity', 0),
                'metadata': ref.get('metadata', {})
            } for ref in references]
            
        except Exception as e:
            logger.error(f"本地文档搜索失败: {e}")
            return []
    
    async def _search_web_resources(self, query: str) -> List[Dict]:
        """搜索网络资源"""
        try:
            async with self.web_search_service as search_service:
                results = await search_service.search_web(query, num_results=5)
                
                return [{
                    'source': 'web',
                    'title': result.title,
                    'content': result.content or result.snippet,
                    'url': result.url,
                    'relevance': result.relevance_score,
                    'metadata': {'url': result.url}
                } for result in results if result.content]
                
        except Exception as e:
            logger.error(f"网络搜索失败: {e}")
            return []
    
    async def _integrate_information(self, local_results: List[Dict], web_results: List[Dict], query: str) -> Dict[str, Any]:
        """整合信息"""
        try:
            # 使用LLM整合和评估信息
            local_summary = "\n".join([f"- {r['title']}: {r['content'][:200]}..." for r in local_results[:3]])
            web_summary = "\n".join([f"- {r['title']}: {r['content'][:200]}..." for r in web_results[:3]])
            
            prompt = f"""基于以下信息，为查询"{query}"生成综合研究结果：

本地文档信息:
{local_summary}

网络资源信息:
{web_summary}

请整合这些信息，生成：
1. 关键发现和要点
2. 信息可信度评估
3. 信息缺口分析
4. 进一步研究建议

格式化为JSON：
{{
    "key_findings": ["要点1", "要点2"],
    "credibility_assessment": "可信度评估",
    "information_gaps": ["缺口1", "缺口2"],
    "further_research": ["建议1", "建议2"]
}}"""
            
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 尝试解析JSON
            try:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            except:
                pass
            
            return {
                "key_findings": ["信息整合完成"],
                "credibility_assessment": "需要人工验证",
                "information_gaps": [],
                "further_research": [],
                "raw_response": response_text
            }
            
        except Exception as e:
            logger.error(f"信息整合失败: {e}")
            return {"error": str(e)}
    
    async def _generate_research_summary(self, integrated_info: Dict[str, Any]) -> str:
        """生成研究摘要"""
        try:
            key_findings = integrated_info.get('key_findings', [])
            credibility = integrated_info.get('credibility_assessment', '未知')
            
            summary = f"研究摘要:\n"
            summary += f"关键发现: {len(key_findings)} 个要点\n"
            summary += f"可信度: {credibility}\n"
            summary += f"信息完整性: {'良好' if len(key_findings) >= 3 else '需要补充'}"
            
            return summary
            
        except Exception as e:
            logger.error(f"生成研究摘要失败: {e}")
            return f"研究摘要生成失败: {str(e)}"

class WriterAgent(BaseAgent):
    """写作Agent - 负责内容生成"""
    
    def __init__(self, llm: BaseChatModel):
        super().__init__(AgentRole.WRITER, llm)
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """处理写作任务消息"""
        if message.message_type == "task_assignment":
            task = Task(
                id=f"write_{len(self.task_history)}",
                description=message.content,
                assigned_agent=self.role,
                status="in_progress"
            )
            
            try:
                result = await self.execute_task(task)
                task.status = "completed"
                task.result = result
                self.task_history.append(task)
                
                return Message(
                    from_agent=self.role,
                    to_agent=AgentRole.REVIEWER,
                    content=f"写作完成: {result}",
                    message_type="result",
                    metadata={"task_id": task.id, "result": result}
                )
            except Exception as e:
                task.status = "failed"
                logger.error(f"写作任务失败: {e}")
                return Message(
                    from_agent=self.role,
                    to_agent=AgentRole.COORDINATOR,
                    content=f"写作失败: {str(e)}",
                    message_type="result",
                    metadata={"task_id": task.id, "error": str(e)}
                )
        
        return None
    
    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """执行写作任务"""
        # 解析任务描述
        task_data = json.loads(task.description) if isinstance(task.description, str) else task.description
        
        research_info = task_data.get('research_info', {})
        writing_requirements = task_data.get('requirements', {})
        
        # 生成文档大纲
        outline = await self._generate_outline(research_info, writing_requirements)
        
        # 生成详细内容
        content = await self._generate_content(outline, research_info, writing_requirements)
        
        return {
            "outline": outline,
            "content": content,
            "word_count": len(content.split()),
            "structure_quality": await self._assess_structure_quality(content)
        }
    
    async def _generate_outline(self, research_info: Dict, requirements: Dict) -> List[Dict]:
        """生成文档大纲"""
        try:
            key_findings = research_info.get('key_findings', [])
            doc_type = requirements.get('doc_type', 'word')
            
            prompt = f"""基于研究信息生成文档大纲：

研究要点: {key_findings}
文档类型: {doc_type}

请生成详细的文档大纲，包含：
1. 主要章节
2. 子章节
3. 每个章节的预期内容长度
4. 章节间的逻辑关系

返回JSON格式：
{{
    "sections": [
        {{
            "title": "章节标题",
            "subsections": ["子章节1", "子章节2"],
            "expected_length": "500-800字",
            "key_points": ["要点1", "要点2"]
        }}
    ]
}}"""
            
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析JSON
            try:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group()).get('sections', [])
            except:
                pass
            
            # 默认大纲
            return [
                {
                    "title": "概述",
                    "subsections": ["背景", "目标"],
                    "expected_length": "300-500字",
                    "key_points": key_findings[:2]
                },
                {
                    "title": "详细分析",
                    "subsections": ["现状分析", "问题识别"],
                    "expected_length": "600-800字",
                    "key_points": key_findings[2:] if len(key_findings) > 2 else key_findings
                }
            ]
            
        except Exception as e:
            logger.error(f"生成大纲失败: {e}")
            return []
    
    async def _generate_content(self, outline: List[Dict], research_info: Dict, requirements: Dict) -> str:
        """生成详细内容"""
        try:
            content_parts = []
            
            for section in outline:
                section_content = await self._generate_section_content(section, research_info)
                content_parts.append(f"# {section['title']}\n\n{section_content}\n")
            
            return "\n".join(content_parts)
            
        except Exception as e:
            logger.error(f"生成内容失败: {e}")
            return f"内容生成失败: {str(e)}"
    
    async def _generate_section_content(self, section: Dict, research_info: Dict) -> str:
        """生成章节内容"""
        try:
            key_points = section.get('key_points', [])
            expected_length = section.get('expected_length', '500字')
            
            prompt = f"""为章节"{section['title']}"生成详细内容：

关键要点: {key_points}
预期长度: {expected_length}
研究信息: {research_info.get('summary', '')}

请生成专业、详细、有逻辑的内容。"""
            
            response = await self.llm.ainvoke(prompt)
            if hasattr(response, 'content'):
                return response.content
            else:
                return str(response)
                
        except Exception as e:
            logger.error(f"生成章节内容失败: {e}")
            return f"章节内容生成失败: {str(e)}"
    
    async def _assess_structure_quality(self, content: str) -> float:
        """评估结构质量"""
        try:
            # 简单的结构质量评估
            lines = content.split('\n')
            headings = [line for line in lines if line.startswith('#')]
            paragraphs = [line for line in lines if line.strip() and not line.startswith('#')]
            
            # 基于标题数量和段落数量的简单评分
            structure_score = min(1.0, len(headings) * 0.2 + len(paragraphs) * 0.01)
            return structure_score
            
        except Exception as e:
            logger.error(f"评估结构质量失败: {e}")
            return 0.5

class ReviewerAgent(BaseAgent):
    """审核Agent - 负责质量审核和改进"""
    
    def __init__(self, llm: BaseChatModel):
        super().__init__(AgentRole.REVIEWER, llm)
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """处理审核任务消息"""
        if message.message_type == "result" and message.from_agent == AgentRole.WRITER:
            task = Task(
                id=f"review_{len(self.task_history)}",
                description=message.content,
                assigned_agent=self.role,
                status="in_progress"
            )
            
            try:
                result = await self.execute_task(task)
                task.status = "completed"
                task.result = result
                self.task_history.append(task)
                
                return Message(
                    from_agent=self.role,
                    to_agent=AgentRole.COORDINATOR,
                    content=f"审核完成: {result}",
                    message_type="result",
                    metadata={"task_id": task.id, "result": result}
                )
            except Exception as e:
                task.status = "failed"
                logger.error(f"审核任务失败: {e}")
                return Message(
                    from_agent=self.role,
                    to_agent=AgentRole.COORDINATOR,
                    content=f"审核失败: {str(e)}",
                    message_type="result",
                    metadata={"task_id": task.id, "error": str(e)}
                )
        
        return None
    
    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """执行审核任务"""
        # 解析写作结果
        writing_result = task.result if isinstance(task.result, dict) else {}
        content = writing_result.get('content', '')
        
        # 质量评估
        quality_assessment = await self._assess_content_quality(content)
        
        # 生成改进建议
        improvement_suggestions = await self._generate_improvement_suggestions(content, quality_assessment)
        
        # 决定是否需要改进
        needs_improvement = quality_assessment.get('overall_score', 0) < 0.7
        
        return {
            "quality_assessment": quality_assessment,
            "improvement_suggestions": improvement_suggestions,
            "needs_improvement": needs_improvement,
            "final_content": content if not needs_improvement else await self._improve_content(content, improvement_suggestions)
        }
    
    async def _assess_content_quality(self, content: str) -> Dict[str, Any]:
        """评估内容质量"""
        try:
            prompt = f"""请评估以下文档内容的质量：

{content}

请从以下维度评估（0-1分）：
1. 内容完整性 - 是否覆盖了所有必要要点
2. 逻辑连贯性 - 章节间逻辑是否清晰
3. 信息密度 - 信息是否充实
4. 格式规范性 - 结构是否规范
5. 语言质量 - 表达是否专业

返回JSON格式：
{{
    "completeness": 0.8,
    "coherence": 0.7,
    "information_density": 0.6,
    "format_quality": 0.9,
    "language_quality": 0.8,
    "overall_score": 0.76,
    "comments": "总体评价和建议"
}}"""
            
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析JSON
            try:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            except:
                pass
            
            # 默认评估
            return {
                "completeness": 0.7,
                "coherence": 0.7,
                "information_density": 0.7,
                "format_quality": 0.7,
                "language_quality": 0.7,
                "overall_score": 0.7,
                "comments": "需要进一步改进"
            }
            
        except Exception as e:
            logger.error(f"评估内容质量失败: {e}")
            return {"overall_score": 0.5, "error": str(e)}
    
    async def _generate_improvement_suggestions(self, content: str, quality_assessment: Dict) -> List[str]:
        """生成改进建议"""
        try:
            low_scores = []
            for key, score in quality_assessment.items():
                if isinstance(score, (int, float)) and score < 0.7:
                    low_scores.append(key)
            
            if not low_scores:
                return ["内容质量良好，无需改进"]
            
            suggestions = []
            if "completeness" in low_scores:
                suggestions.append("增加更多细节和具体案例")
            if "coherence" in low_scores:
                suggestions.append("改善章节间的逻辑连接")
            if "information_density" in low_scores:
                suggestions.append("增加数据支撑和分析")
            if "format_quality" in low_scores:
                suggestions.append("优化文档结构和格式")
            if "language_quality" in low_scores:
                suggestions.append("改进语言表达和用词")
            
            return suggestions
            
        except Exception as e:
            logger.error(f"生成改进建议失败: {e}")
            return ["需要人工审核"]
    
    async def _improve_content(self, content: str, suggestions: List[str]) -> str:
        """改进内容"""
        try:
            suggestions_text = "\n".join([f"- {s}" for s in suggestions])
            
            prompt = f"""请根据以下建议改进文档内容：

原文：
{content}

改进建议：
{suggestions_text}

请生成改进后的内容，保持原有结构但提升质量。"""
            
            response = await self.llm.ainvoke(prompt)
            if hasattr(response, 'content'):
                return response.content
            else:
                return str(response)
                
        except Exception as e:
            logger.error(f"改进内容失败: {e}")
            return content  # 返回原内容

class CoordinatorAgent(BaseAgent):
    """协调Agent - 协调各Agent工作"""
    
    def __init__(self, llm: BaseChatModel):
        super().__init__(AgentRole.COORDINATOR, llm)
        self.agents = {}
        self.task_queue = asyncio.Queue()
        self.results = {}
    
    def register_agent(self, agent: BaseAgent):
        """注册Agent"""
        self.agents[agent.role] = agent
    
    async def coordinate_task(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """协调任务执行"""
        logger.info(f"Coordinator开始协调任务: {task_description}")
        
        try:
            # 1. 分配研究任务
            research_task = f"研究任务: {task_description}"
            research_message = Message(
                from_agent=self.role,
                to_agent=AgentRole.RESEARCHER,
                content=research_task,
                message_type="task_assignment"
            )
            
            research_result = await self._send_message_and_wait_response(research_message)
            
            if not research_result:
                return {"error": "研究任务失败"}
            
            # 2. 分配写作任务
            writing_task = {
                "research_info": research_result.get('metadata', {}).get('result', {}),
                "requirements": requirements
            }
            
            writing_message = Message(
                from_agent=self.role,
                to_agent=AgentRole.WRITER,
                content=json.dumps(writing_task),
                message_type="task_assignment"
            )
            
            writing_result = await self._send_message_and_wait_response(writing_message)
            
            if not writing_result:
                return {"error": "写作任务失败"}
            
            # 3. 等待审核结果
            review_result = await self._wait_for_review_result()
            
            # 4. 整合最终结果
            final_result = {
                "task_description": task_description,
                "research_result": research_result,
                "writing_result": writing_result,
                "review_result": review_result,
                "success": True
            }
            
            return final_result
            
        except Exception as e:
            logger.error(f"协调任务失败: {e}")
            return {"error": str(e), "success": False}
    
    async def _send_message_and_wait_response(self, message: Message) -> Optional[Message]:
        """发送消息并等待响应"""
        try:
            target_agent = self.agents.get(message.to_agent)
            if not target_agent:
                logger.error(f"未找到目标Agent: {message.to_agent}")
                return None
            
            # 发送消息
            response = await target_agent.process_message(message)
            
            # 等待响应
            if response:
                return response
            
            return None
            
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return None
    
    async def _wait_for_review_result(self) -> Optional[Message]:
        """等待审核结果"""
        # 这里简化处理，实际应该实现更复杂的等待机制
        await asyncio.sleep(1)  # 模拟等待
        return None

class MultiAgentSystem:
    """多Agent系统"""
    
    def __init__(self, llm: BaseChatModel, rag_service, web_search_service):
        self.llm = llm
        self.rag_service = rag_service
        self.web_search_service = web_search_service
        
        # 初始化各Agent
        self.research_agent = ResearchAgent(llm, rag_service, web_search_service)
        self.writer_agent = WriterAgent(llm)
        self.reviewer_agent = ReviewerAgent(llm)
        self.coordinator_agent = CoordinatorAgent(llm)
        
        # 注册Agent
        self.coordinator_agent.register_agent(self.research_agent)
        self.coordinator_agent.register_agent(self.writer_agent)
        self.coordinator_agent.register_agent(self.reviewer_agent)
    
    async def execute_task(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务"""
        return await self.coordinator_agent.coordinate_task(task_description, requirements)
