"""
工作流调度器
根据任务复杂度自动选择合适的工作流
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from enum import Enum
import json

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

class WorkflowType(Enum):
    """工作流类型"""
    SIMPLE = "simple"  # 简单两阶段生成
    PLAN_EXECUTE = "plan_execute"  # Plan-and-Execute
    MULTI_AGENT = "multi_agent"  # Multi-Agent协作
    INTELLIGENT_MULTI_AGENT = "intelligent_multi_agent"  # 智能Multi-Agent协作
    REACT = "react"  # ReAct Agent
    LANGGRAPH = "langgraph"  # LangGraph状态机

class WorkflowOrchestrator:
    """工作流调度器"""
    
    def __init__(self, llm: BaseChatModel, rag_service, web_search_service):
        self.llm = llm
        self.rag_service = rag_service
        self.web_search_service = web_search_service
        
        # 工作流超时配置
        self.workflow_timeout = 120  # 2分钟超时
        self.intent_recognition_timeout = 10  # 10秒超时
        
        # 导入工作流类
        self._import_workflows()
        
        # 初始化智能澄清服务
        try:
            from app.services.intelligent_clarification_service import IntelligentClarificationService
            self.clarification_service = IntelligentClarificationService(llm)
        except ImportError:
            logger.warning("智能澄清服务不可用")
            self.clarification_service = None
        
        # 工作流实例缓存
        self._workflow_instances = {}
        
    def _import_workflows(self):
        """导入工作流类"""
        try:
            # 导入现有工作流
            from app.services.content_aggregator import ContentAggregator
            from app.services.document_generator_service import DocumentGeneratorService
            
            # 导入新工作流
            from app.agents.react_agent import ReActAgent
            from app.agents.multi_agent_system import MultiAgentSystem
            from app.agents.intelligent_multi_agent_system import IntelligentMultiAgentSystem
            from app.workflows.plan_execute_workflow import PlanAndExecuteWorkflow
            from app.workflows.langgraph_workflow import LangGraphWorkflow
            
            self.ContentAggregator = ContentAggregator
            self.DocumentGeneratorService = DocumentGeneratorService
            self.ReActAgent = ReActAgent
            self.MultiAgentSystem = MultiAgentSystem
            self.IntelligentMultiAgentSystem = IntelligentMultiAgentSystem
            self.PlanAndExecuteWorkflow = PlanAndExecuteWorkflow
            self.LangGraphWorkflow = LangGraphWorkflow
            
            logger.info("所有工作流类导入成功")
            
        except ImportError as e:
            logger.error(f"工作流类导入失败: {e}")
            # 设置默认值
            self.ContentAggregator = None
            self.DocumentGeneratorService = None
            self.ReActAgent = None
            self.MultiAgentSystem = None
            self.IntelligentMultiAgentSystem = None
            self.PlanAndExecuteWorkflow = None
            self.LangGraphWorkflow = None
    
    async def execute_task(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行任务，自动选择合适的工作流
        
        Args:
            task_description: 任务描述
            requirements: 需求参数
            
        Returns:
            执行结果
        """
        logger.info(f"工作流调度器开始处理任务: {task_description}")
        
        try:
            # 1. 分析任务复杂度
            complexity = await self._analyze_task_complexity(task_description, requirements)
            logger.info(f"任务复杂度分析: {complexity}")
            
            # 2. 选择工作流
            workflow_type = self._select_workflow(complexity, requirements)
            logger.info(f"选择工作流: {workflow_type}")
            
            # 3. 执行工作流
            result = await self._execute_workflow(workflow_type, task_description, requirements)
            
            # 4. 添加元数据
            result["workflow_type"] = workflow_type.value
            result["complexity_analysis"] = complexity
            result["task_description"] = task_description
            
            return result
            
        except Exception as e:
            logger.error(f"工作流调度器执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "workflow_type": "error",
                "task_description": task_description
            }
    
    async def _analyze_task_complexity(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """分析任务复杂度"""
        try:
            enable_web_search = requirements.get("enable_web_search", False)
            doc_type = requirements.get("doc_type", "word")
            
            prompt = f"""分析以下任务的复杂度：

任务描述: {task_description}
文档类型: {doc_type}
启用网络搜索: {enable_web_search}

请从以下维度评估复杂度（1-5分）：
1. 信息需求复杂度（需要多少不同来源的信息）
2. 内容生成复杂度（需要多深的分析和推理）
3. 协作需求复杂度（是否需要多个专业角色）
4. 质量控制复杂度（需要多少轮审核和改进）
5. 时间敏感性（是否需要实时信息）

返回JSON格式：
{{
    "information_complexity": 3,
    "content_complexity": 4,
    "collaboration_complexity": 2,
    "quality_complexity": 3,
    "time_sensitivity": 2,
    "overall_complexity": "中等",
    "recommended_workflow": "plan_execute",
    "reasoning": "选择理由"
}}"""
            
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析响应
            try:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    complexity_data = json.loads(json_match.group())
                else:
                    complexity_data = self._get_default_complexity()
            except:
                complexity_data = self._get_default_complexity()
            
            return complexity_data
            
        except Exception as e:
            logger.error(f"任务复杂度分析失败: {e}")
            return self._get_default_complexity()
    
    def _get_default_complexity(self) -> Dict[str, Any]:
        """获取默认复杂度"""
        return {
            "information_complexity": 3,
            "content_complexity": 3,
            "collaboration_complexity": 2,
            "quality_complexity": 3,
            "time_sensitivity": 2,
            "overall_complexity": "中等",
            "recommended_workflow": "plan_execute",
            "reasoning": "默认中等复杂度"
        }
    
    def _select_workflow(self, complexity: Dict[str, Any], requirements: Dict[str, Any]) -> WorkflowType:
        """选择工作流"""
        try:
            overall_complexity = complexity.get("overall_complexity", "中等")
            information_complexity = complexity.get("information_complexity", 3)
            content_complexity = complexity.get("content_complexity", 3)
            collaboration_complexity = complexity.get("collaboration_complexity", 2)
            enable_web_search = requirements.get("enable_web_search", False)
            
            # 决策逻辑
            if overall_complexity == "简单" and information_complexity <= 2 and content_complexity <= 2:
                return WorkflowType.SIMPLE
            
            elif overall_complexity == "中等" and collaboration_complexity <= 2:
                return WorkflowType.PLAN_EXECUTE
            
            elif overall_complexity == "复杂" and collaboration_complexity >= 3:
                # 优先使用智能多Agent系统
                if self.IntelligentMultiAgentSystem:
                    return WorkflowType.INTELLIGENT_MULTI_AGENT
                else:
                    return WorkflowType.MULTI_AGENT
            
            elif enable_web_search and information_complexity >= 4:
                return WorkflowType.REACT
            
            elif overall_complexity == "复杂" and content_complexity >= 4:
                return WorkflowType.LANGGRAPH
            
            else:
                # 默认选择
                return WorkflowType.PLAN_EXECUTE
                
        except Exception as e:
            logger.error(f"工作流选择失败: {e}")
            return WorkflowType.SIMPLE
    
    async def _execute_workflow(self, workflow_type: WorkflowType, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """执行工作流（带超时控制）"""
        try:
            import asyncio
            
            # 设置工作流超时
            result = await asyncio.wait_for(
                self._execute_workflow_internal(workflow_type, task_description, requirements),
                timeout=self.workflow_timeout
            )
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"工作流执行超时: {workflow_type.value}")
            return {
                "success": False,
                "error": f"工作流执行超时 ({self.workflow_timeout}秒)",
                "workflow_type": workflow_type.value
            }
        except Exception as e:
            logger.error(f"执行工作流 {workflow_type} 失败: {e}")
            # 回退到简单工作流
            return await self._execute_simple_workflow(task_description, requirements)
    
    async def _execute_workflow_internal(self, workflow_type: WorkflowType, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """内部工作流执行方法"""
        if workflow_type == WorkflowType.SIMPLE:
            return await self._execute_simple_workflow(task_description, requirements)
        
        elif workflow_type == WorkflowType.PLAN_EXECUTE:
            return await self._execute_plan_execute_workflow(task_description, requirements)
        
        elif workflow_type == WorkflowType.MULTI_AGENT:
            return await self._execute_multi_agent_workflow(task_description, requirements)
        
        elif workflow_type == WorkflowType.INTELLIGENT_MULTI_AGENT:
            return await self._execute_intelligent_multi_agent_workflow(task_description, requirements)
        
        elif workflow_type == WorkflowType.REACT:
            return await self._execute_react_workflow(task_description, requirements)
        
        elif workflow_type == WorkflowType.LANGGRAPH:
            return await self._execute_langgraph_workflow(task_description, requirements)
        
        else:
            raise ValueError(f"未知的工作流类型: {workflow_type}")
    
    async def _execute_simple_workflow(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """执行简单工作流（现有两阶段生成）"""
        try:
            if not self.ContentAggregator or not self.DocumentGeneratorService:
                raise ImportError("简单工作流组件不可用")
            
            # 使用现有的两阶段生成
            from app.services.intent_classifier import IntentClassifier, IntentResult
            from app.services.document_generator_service import DocumentType
            
            # 创建意图
            intent = IntentResult(
                is_generation_intent=True,
                doc_type=DocumentType(requirements.get('doc_type', 'word')),
                content_source='mixed',
                title=task_description[:50],
                inferred_query=task_description,
                needs_confirmation=False,
                confirmation_message=None,
                extracted_params=requirements,
                confidence=0.9
            )
            
            # 内容聚合
            content_aggregator = self.ContentAggregator(self.rag_service, self.llm)
            aggregated_content = await content_aggregator.aggregate_content(
                intent, "global", []
            )
            
            # 文档生成
            doc_generator = self.DocumentGeneratorService()
            result = doc_generator.generate_document(
                aggregated_content.to_document_content(),
                intent.doc_type
            )
            
            return {
                "success": result.get('success', False),
                "result": result,
                "aggregated_content": aggregated_content
            }
            
        except Exception as e:
            logger.error(f"简单工作流执行失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _execute_plan_execute_workflow(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """执行Plan-and-Execute工作流"""
        try:
            if not self.PlanAndExecuteWorkflow:
                raise ImportError("Plan-and-Execute工作流不可用")
            
            workflow = self.PlanAndExecuteWorkflow(self.llm, self.rag_service, self.web_search_service)
            result = await workflow.execute(task_description, requirements)
            
            return result
            
        except Exception as e:
            logger.error(f"Plan-and-Execute工作流执行失败: {e}")
            raise
    
    async def _execute_multi_agent_workflow(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """执行Multi-Agent工作流"""
        try:
            if not self.MultiAgentSystem:
                raise ImportError("Multi-Agent工作流不可用")
            
            multi_agent = self.MultiAgentSystem(self.llm, self.rag_service, self.web_search_service)
            result = await multi_agent.execute_task(task_description, requirements)
            
            return result
            
        except Exception as e:
            logger.error(f"Multi-Agent工作流执行失败: {e}")
            raise
    
    async def _execute_intelligent_multi_agent_workflow(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """执行智能Multi-Agent工作流"""
        try:
            if not self.IntelligentMultiAgentSystem:
                raise ImportError("智能Multi-Agent工作流不可用")
            
            intelligent_multi_agent = self.IntelligentMultiAgentSystem(self.llm, self.rag_service, self.web_search_service)
            result = await intelligent_multi_agent.execute_task(task_description, requirements)
            
            return result
            
        except Exception as e:
            logger.error(f"智能Multi-Agent工作流执行失败: {e}")
            raise
    
    async def _execute_react_workflow(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """执行ReAct工作流"""
        try:
            if not self.ReActAgent:
                raise ImportError("ReAct工作流不可用")
            
            react_agent = self.ReActAgent(self.llm, self.rag_service, self.web_search_service)
            result = await react_agent.run(task_description, "global")
            
            return result
            
        except Exception as e:
            logger.error(f"ReAct工作流执行失败: {e}")
            raise
    
    async def _execute_langgraph_workflow(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """执行LangGraph工作流"""
        try:
            if not self.LangGraphWorkflow:
                raise ImportError("LangGraph工作流不可用")
            
            langgraph_workflow = self.LangGraphWorkflow(self.llm, self.rag_service, self.web_search_service)
            result = await langgraph_workflow.execute(task_description, requirements)
            
            return result
            
        except Exception as e:
            logger.error(f"LangGraph工作流执行失败: {e}")
            raise
    
    def get_workflow_info(self) -> Dict[str, Any]:
        """获取工作流信息"""
        return {
            "available_workflows": [
                {
                    "type": "simple",
                    "name": "简单两阶段生成",
                    "description": "适用于简单任务，直接生成文档",
                    "complexity": "低"
                },
                {
                    "type": "plan_execute",
                    "name": "计划执行工作流",
                    "description": "先生成计划，再逐步执行",
                    "complexity": "中等"
                },
                {
                    "type": "multi_agent",
                    "name": "多Agent协作",
                    "description": "多个专业化Agent协作完成任务",
                    "complexity": "高"
                },
                {
                    "type": "react",
                    "name": "ReAct推理行动",
                    "description": "推理-行动循环，适合研究型任务",
                    "complexity": "高"
                },
                {
                    "type": "langgraph",
                    "name": "LangGraph状态机",
                    "description": "复杂状态机工作流，支持条件路由",
                    "complexity": "高"
                }
            ],
            "workflow_selection_criteria": {
                "simple": "简单任务，信息需求低",
                "plan_execute": "中等复杂度，需要结构化执行",
                "multi_agent": "复杂任务，需要多角色协作",
                "react": "研究型任务，需要动态推理",
                "langgraph": "复杂任务，需要状态管理"
            }
        }
