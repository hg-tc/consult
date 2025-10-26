"""
Plan-and-Execute工作流
两阶段流程：计划生成 + 逐步执行
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import json
import re

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class ExecutionStep:
    """执行步骤"""
    id: str
    title: str
    description: str
    action_type: str  # search, generate, analyze, format
    parameters: Dict[str, Any]
    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    dependencies: List[str] = None  # 依赖的步骤ID

@dataclass
class ExecutionPlan:
    """执行计划"""
    task_description: str
    steps: List[ExecutionStep]
    estimated_duration: str
    success_criteria: List[str]
    fallback_strategy: str

class PlanAndExecuteWorkflow:
    """Plan-and-Execute工作流"""
    
    def __init__(self, llm: BaseChatModel, rag_service, web_search_service):
        self.llm = llm
        self.rag_service = rag_service
        self.web_search_service = web_search_service
        self.execution_history = []
        
    async def execute(self, task_description: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行Plan-and-Execute工作流
        
        Args:
            task_description: 任务描述
            requirements: 需求参数
            
        Returns:
            执行结果
        """
        logger.info(f"Plan-and-Execute工作流开始: {task_description}")
        
        try:
            # Phase 1: 计划生成
            plan = await self._generate_plan(task_description, requirements)
            logger.info(f"生成执行计划，包含 {len(plan.steps)} 个步骤")
            
            # Phase 2: 计划执行
            execution_result = await self._execute_plan(plan)
            
            return {
                "success": True,
                "task_description": task_description,
                "plan": plan,
                "execution_result": execution_result,
                "workflow_type": "plan_and_execute"
            }
            
        except Exception as e:
            logger.error(f"Plan-and-Execute工作流失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "workflow_type": "plan_and_execute"
            }
    
    async def _generate_plan(self, task_description: str, requirements: Dict[str, Any]) -> ExecutionPlan:
        """生成执行计划"""
        try:
            doc_type = requirements.get('doc_type', 'word')
            enable_web_search = requirements.get('enable_web_search', False)
            
            prompt = f"""请为以下任务生成详细的执行计划：

任务描述: {task_description}
文档类型: {doc_type}
启用网络搜索: {enable_web_search}

请生成一个分步骤的执行计划，包含以下信息：
1. 每个步骤的标题和描述
2. 步骤类型（search_local, search_web, analyze, generate, format）
3. 步骤参数
4. 步骤间的依赖关系
5. 预计执行时间
6. 成功标准
7. 失败时的备用策略

返回JSON格式：
{{
    "steps": [
        {{
            "id": "step_1",
            "title": "步骤标题",
            "description": "详细描述",
            "action_type": "search_local",
            "parameters": {{"query": "搜索查询"}},
            "dependencies": []
        }}
    ],
    "estimated_duration": "预计时间",
    "success_criteria": ["标准1", "标准2"],
    "fallback_strategy": "备用策略"
}}"""
            
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析JSON响应
            plan_data = self._parse_plan_response(response_text)
            
            # 创建执行计划对象
            steps = []
            for step_data in plan_data.get('steps', []):
                step = ExecutionStep(
                    id=step_data.get('id', f"step_{len(steps)}"),
                    title=step_data.get('title', '未命名步骤'),
                    description=step_data.get('description', ''),
                    action_type=step_data.get('action_type', 'unknown'),
                    parameters=step_data.get('parameters', {}),
                    dependencies=step_data.get('dependencies', [])
                )
                steps.append(step)
            
            plan = ExecutionPlan(
                task_description=task_description,
                steps=steps,
                estimated_duration=plan_data.get('estimated_duration', '未知'),
                success_criteria=plan_data.get('success_criteria', []),
                fallback_strategy=plan_data.get('fallback_strategy', '重试')
            )
            
            return plan
            
        except Exception as e:
            logger.error(f"生成执行计划失败: {e}")
            # 返回默认计划
            return self._generate_default_plan(task_description, requirements)
    
    def _parse_plan_response(self, response_text: str) -> Dict[str, Any]:
        """解析计划响应"""
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"解析计划响应失败: {e}")
        
        # 返回默认计划数据
        return {
            "steps": [
                {
                    "id": "step_1",
                    "title": "信息收集",
                    "description": "收集相关文档和网络信息",
                    "action_type": "search_local",
                    "parameters": {"query": "相关主题"},
                    "dependencies": []
                },
                {
                    "id": "step_2",
                    "title": "内容生成",
                    "description": "基于收集的信息生成文档内容",
                    "action_type": "generate",
                    "parameters": {"format": "structured"},
                    "dependencies": ["step_1"]
                }
            ],
            "estimated_duration": "5-10分钟",
            "success_criteria": ["内容完整", "格式正确"],
            "fallback_strategy": "使用基础模板"
        }
    
    def _generate_default_plan(self, task_description: str, requirements: Dict[str, Any]) -> ExecutionPlan:
        """生成默认执行计划"""
        steps = [
            ExecutionStep(
                id="step_1",
                title="收集信息",
                description="搜索相关文档内容",
                action_type="search_local",
                parameters={"query": task_description},
                dependencies=[]
            ),
            ExecutionStep(
                id="step_2", 
                title="生成文档",
                description="基于收集的信息生成文档内容",
                action_type="generate",
                parameters={"format": requirements.get('doc_type', 'word')},
                dependencies=["step_1"]
            )
        ]
        
        return ExecutionPlan(
            task_description=task_description,
            steps=steps,
            estimated_duration="2-3分钟",
            success_criteria=["成功收集相关信息", "生成结构化的文档内容"],
            fallback_strategy="使用基础模板重试"
        )
    
    async def _execute_plan(self, plan: ExecutionPlan) -> Dict[str, Any]:
        """执行计划"""
        logger.info(f"开始执行计划，共 {len(plan.steps)} 个步骤")
        
        execution_results = {}
        completed_steps = set()
        
        # 按依赖关系执行步骤
        while len(completed_steps) < len(plan.steps):
            # 找到可以执行的步骤（依赖已满足）
            executable_steps = []
            for step in plan.steps:
                if step.id not in completed_steps:
                    dependencies_met = all(dep in completed_steps for dep in (step.dependencies or []))
                    if dependencies_met:
                        executable_steps.append(step)
            
            if not executable_steps:
                logger.error("没有可执行的步骤，可能存在循环依赖")
                break
            
            # 并发执行可执行的步骤
            tasks = []
            for step in executable_steps:
                task = asyncio.create_task(self._execute_step(step, execution_results))
                tasks.append(task)
            
            # 等待所有任务完成
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            for i, result in enumerate(results):
                step = executable_steps[i]
                if isinstance(result, Exception):
                    step.status = StepStatus.FAILED
                    step.error = str(result)
                    logger.error(f"步骤 {step.id} 执行失败: {result}")
                else:
                    step.status = StepStatus.COMPLETED
                    step.result = result
                    completed_steps.add(step.id)
                    execution_results[step.id] = result
                    logger.info(f"步骤 {step.id} 执行完成")
        
        # 检查是否所有步骤都完成
        success = len(completed_steps) == len(plan.steps)
        
        return {
            "success": success,
            "completed_steps": list(completed_steps),
            "step_results": execution_results,
            "plan": plan
        }
    
    async def _execute_step(self, step: ExecutionStep, context: Dict[str, Any]) -> Any:
        """执行单个步骤"""
        logger.info(f"执行步骤: {step.title}")
        
        try:
            step.status = StepStatus.IN_PROGRESS
            
            if step.action_type == "search_local":
                return await self._execute_search_local(step, context)
            elif step.action_type == "search_web":
                return await self._execute_search_web(step, context)
            elif step.action_type == "analyze":
                return await self._execute_analyze(step, context)
            elif step.action_type == "generate":
                return await self._execute_generate(step, context)
            elif step.action_type == "format":
                return await self._execute_format(step, context)
            else:
                raise ValueError(f"未知的动作类型: {step.action_type}")
                
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            logger.error(f"步骤 {step.id} 执行失败: {e}")
            raise
    
    async def _execute_search_local(self, step: ExecutionStep, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行本地搜索"""
        query = step.parameters.get('query', '')
        
        try:
            result = await self.rag_service.ask_question(
                workspace_id="global",
                question=query,
                top_k=10
            )
            
            return {
                "action_type": "search_local",
                "query": query,
                "results": result.get('references', []),
                "answer": result.get('answer', ''),
                "count": len(result.get('references', []))
            }
            
        except Exception as e:
            logger.error(f"本地搜索失败: {e}")
            return {"error": str(e), "action_type": "search_local"}
    
    async def _execute_search_web(self, step: ExecutionStep, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行网络搜索"""
        query = step.parameters.get('query', '')
        
        try:
            async with self.web_search_service as search_service:
                results = await search_service.search_web(query, num_results=5)
                
                return {
                    "action_type": "search_web",
                    "query": query,
                    "results": [
                        {
                            "title": r.title,
                            "url": r.url,
                            "content": r.content or r.snippet,
                            "relevance": r.relevance_score
                        } for r in results
                    ],
                    "count": len(results)
                }
                
        except Exception as e:
            logger.error(f"网络搜索失败: {e}")
            return {"error": str(e), "action_type": "search_web"}
    
    async def _execute_analyze(self, step: ExecutionStep, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行分析"""
        sources = step.parameters.get('sources', [])
        
        try:
            # 收集相关步骤的结果
            source_data = []
            for source_id in sources:
                if source_id in context:
                    source_data.append(context[source_id])
            
            # 使用LLM进行分析
            analysis_prompt = f"""请分析以下收集的信息：

{json.dumps(source_data, ensure_ascii=False, indent=2)}

请提供：
1. 关键发现和要点
2. 信息可信度评估
3. 信息缺口分析
4. 进一步建议

请以结构化的方式组织分析结果。"""
            
            response = await self.llm.ainvoke(analysis_prompt)
            analysis_result = response.content if hasattr(response, 'content') else str(response)
            
            return {
                "action_type": "analyze",
                "sources": sources,
                "analysis": analysis_result,
                "source_count": len(source_data)
            }
            
        except Exception as e:
            logger.error(f"分析失败: {e}")
            return {"error": str(e), "action_type": "analyze"}
    
    async def _execute_generate(self, step: ExecutionStep, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行内容生成"""
        format_type = step.parameters.get('format', 'word')
        
        try:
            # 收集分析结果
            analysis_data = None
            for step_id, result in context.items():
                if isinstance(result, dict) and result.get('action_type') == 'analyze':
                    analysis_data = result
                    break
            
            if not analysis_data:
                analysis_data = {"analysis": "无分析数据"}
            
            # 生成内容
            generation_prompt = f"""基于以下分析结果生成文档内容：

{analysis_data.get('analysis', '')}

文档类型: {format_type}

请生成结构化的文档内容，包含：
1. 清晰的章节结构
2. 详细的内容描述
3. 逻辑清晰的论述
4. 专业的语言表达

请确保内容充实、准确、有价值。"""
            
            response = await self.llm.ainvoke(generation_prompt)
            generated_content = response.content if hasattr(response, 'content') else str(response)
            
            return {
                "action_type": "generate",
                "format": format_type,
                "content": generated_content,
                "word_count": len(generated_content.split()),
                "analysis_source": analysis_data
            }
            
        except Exception as e:
            logger.error(f"内容生成失败: {e}")
            return {"error": str(e), "action_type": "generate"}
    
    async def _execute_format(self, step: ExecutionStep, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行格式化"""
        output_format = step.parameters.get('output_format', 'word')
        
        try:
            # 收集生成的内容
            generated_data = None
            for step_id, result in context.items():
                if isinstance(result, dict) and result.get('action_type') == 'generate':
                    generated_data = result
                    break
            
            if not generated_data:
                return {"error": "没有生成的内容可格式化", "action_type": "format"}
            
            content = generated_data.get('content', '')
            
            # 格式化内容
            formatted_content = await self._format_content(content, output_format)
            
            return {
                "action_type": "format",
                "output_format": output_format,
                "formatted_content": formatted_content,
                "original_content": content,
                "formatting_applied": True
            }
            
        except Exception as e:
            logger.error(f"格式化失败: {e}")
            return {"error": str(e), "action_type": "format"}
    
    async def _format_content(self, content: str, output_format: str) -> str:
        """格式化内容"""
        try:
            if output_format.lower() == 'word':
                # Word格式：添加标题层级
                lines = content.split('\n')
                formatted_lines = []
                
                for line in lines:
                    line = line.strip()
                    if line:
                        # 检测标题（简单规则）
                        if line.startswith('#') or '概述' in line or '分析' in line or '结论' in line:
                            formatted_lines.append(f"# {line.replace('#', '').strip()}")
                        else:
                            formatted_lines.append(line)
                
                return '\n'.join(formatted_lines)
            
            elif output_format.lower() == 'pdf':
                # PDF格式：添加更多结构
                return f"# 文档报告\n\n{content}\n\n---\n*生成时间: {asyncio.get_event_loop().time()}*"
            
            else:
                return content
                
        except Exception as e:
            logger.error(f"内容格式化失败: {e}")
            return content
