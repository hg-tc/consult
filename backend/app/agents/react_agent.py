"""
ReAct Agent实现
推理-行动循环，集成工具使用
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import re

from langchain_core.tools import tool as tool_dec
from langchain.schema import BaseMessage, HumanMessage, AIMessage
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

class ActionType(Enum):
    """动作类型"""
    SEARCH_DOCUMENTS = "search_documents"
    SEARCH_WEB = "search_web"
    CALCULATE = "calculate"
    GENERATE_CONTENT = "generate_content"
    FINISH = "finish"

@dataclass
class Action:
    """动作"""
    action_type: ActionType
    action_input: Dict[str, Any]
    reasoning: str

@dataclass
class Observation:
    """观察结果"""
    content: str
    success: bool
    metadata: Dict[str, Any] = None

class ReActAgent:
    """ReAct Agent - 推理-行动循环"""
    
    def __init__(self, llm: BaseChatModel, rag_service, web_search_service):
        self.llm = llm
        self.rag_service = rag_service
        self.web_search_service = web_search_service
        self.max_iterations = 10
        self.conversation_history = []
        
        # 初始化工具
        self.tools = self._initialize_tools()
        
    def _initialize_tools(self) -> List[Any]:
        """初始化工具集"""
        # 使用 langchain_core.tools.tool 装饰器在运行时创建工具，包装实例方法
        @tool_dec(name="search_documents", description="搜索本地文档库，获取相关文档内容")
        async def search_documents(query: str) -> str:
            return await self._search_documents_tool(query)

        @tool_dec(name="search_web", description="搜索互联网，获取最新信息和资料")
        async def search_web(query: str) -> str:
            return await self._search_web_tool(query)

        @tool_dec(name="calculate", description="执行数学计算")
        def calculate(expression: str) -> str:
            return self._calculate_tool(expression)

        @tool_dec(name="generate_content", description="基于收集的信息生成文档内容")
        async def generate_content(prompt: str) -> str:
            return await self._generate_content_tool(prompt)

        return [search_documents, search_web, calculate, generate_content]
    
    async def _search_documents_tool(self, query: str) -> str:
        """文档搜索工具"""
        try:
            result = await self.rag_service.ask_question(
                workspace_id="global",
                question=query,
                top_k=5
            )
            
            if result.get('references'):
                content = f"找到 {len(result['references'])} 个相关文档:\n"
                for i, ref in enumerate(result['references'][:3]):
                    content += f"{i+1}. {ref.get('document_name', '未知文档')}: {ref.get('content', '')[:200]}...\n"
                return content
            else:
                return "未找到相关文档"
                
        except Exception as e:
            logger.error(f"文档搜索失败: {e}")
            return f"文档搜索失败: {str(e)}"
    
    async def _search_web_tool(self, query: str) -> str:
        """网络搜索工具"""
        try:
            async with self.web_search_service as search_service:
                results = await search_service.search_web(query, num_results=3)
                
                if results:
                    content = f"网络搜索找到 {len(results)} 个结果:\n"
                    for i, result in enumerate(results):
                        content += f"{i+1}. {result.title}: {result.snippet}\n"
                        if result.content:
                            content += f"   内容: {result.content[:200]}...\n"
                    return content
                else:
                    return "网络搜索未找到相关结果"
                    
        except Exception as e:
            logger.error(f"网络搜索失败: {e}")
            return f"网络搜索失败: {str(e)}"
    
    def _calculate_tool(self, expression: str) -> str:
        """计算工具"""
        try:
            # 简单的数学计算（安全版本）
            allowed_chars = set('0123456789+-*/().')
            if not all(c in allowed_chars for c in expression):
                return "表达式包含不允许的字符"
            
            result = eval(expression)
            return f"计算结果: {expression} = {result}"
            
        except Exception as e:
            return f"计算失败: {str(e)}"
    
    async def _generate_content_tool(self, prompt: str) -> str:
        """内容生成工具"""
        try:
            response = await self.llm.ainvoke(prompt)
            if hasattr(response, 'content'):
                return response.content
            else:
                return str(response)
                
        except Exception as e:
            logger.error(f"内容生成失败: {e}")
            return f"内容生成失败: {str(e)}"
    
    async def run(self, task: str, workspace_id: str = "global") -> Dict[str, Any]:
        """
        运行ReAct循环
        
        Args:
            task: 任务描述
            workspace_id: 工作区ID
            
        Returns:
            执行结果
        """
        logger.info(f"ReAct Agent开始执行任务: {task}")
        
        # 初始化状态
        self.conversation_history = []
        collected_info = []
        iterations = 0
        
        # 初始思考
        initial_thought = await self._think(f"任务: {task}\n\n我需要分析这个任务，制定执行计划。")
        logger.info(f"初始思考: {initial_thought}")
        
        while iterations < self.max_iterations:
            iterations += 1
            logger.info(f"ReAct循环第 {iterations} 次迭代")
            
            # 1. 思考阶段
            thought = await self._think(f"当前任务: {task}\n已收集信息: {len(collected_info)} 条\n\n我需要决定下一步行动。")
            
            # 2. 行动阶段
            action = await self._act(thought, task)
            
            if action.action_type == ActionType.FINISH:
                logger.info("ReAct Agent决定完成任务")
                break
            
            # 3. 观察阶段
            observation = await self._observe(action)
            
            # 记录到历史
            self.conversation_history.append({
                'iteration': iterations,
                'thought': thought,
                'action': action.__dict__,
                'observation': observation.__dict__
            })
            
            # 收集有用信息
            if observation.success and observation.content:
                collected_info.append({
                    'source': action.action_type.value,
                    'content': observation.content,
                    'metadata': observation.metadata or {}
                })
            
            # 检查是否完成任务
            if await self._should_finish(collected_info, task):
                logger.info("ReAct Agent判断信息收集充分，准备生成最终结果")
                break
        
        # 生成最终结果
        final_result = await self._generate_final_result(task, collected_info)
        
        return {
            'success': True,
            'result': final_result,
            'iterations': iterations,
            'collected_info': collected_info,
            'conversation_history': self.conversation_history
        }
    
    async def _think(self, context: str) -> str:
        """思考阶段"""
        try:
            prompt = f"""你是一个智能助手，需要分析当前情况并思考下一步行动。

{context}

请分析当前情况，考虑：
1. 任务目标是什么？
2. 已经收集了哪些信息？
3. 还需要什么信息？
4. 下一步应该采取什么行动？

请简洁地表达你的思考过程。"""
            
            response = await self.llm.ainvoke(prompt)
            if hasattr(response, 'content'):
                return response.content
            else:
                return str(response)
                
        except Exception as e:
            logger.error(f"思考阶段失败: {e}")
            return f"思考失败: {str(e)}"
    
    async def _act(self, thought: str, task: str) -> Action:
        """行动阶段"""
        try:
            # 构建工具描述
            tools_desc = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])
            
            prompt = f"""基于你的思考，决定下一步行动。

思考: {thought}

可用工具:
{tools_desc}

请选择最合适的工具并说明理由。格式：
工具名称: [工具名]
理由: [选择理由]
参数: [工具参数]

如果信息收集充分，请选择 "finish" 工具。"""
            
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析响应
            action_type, action_input, reasoning = self._parse_action_response(response_text)
            
            return Action(
                action_type=action_type,
                action_input=action_input,
                reasoning=reasoning
            )
            
        except Exception as e:
            logger.error(f"行动阶段失败: {e}")
            return Action(
                action_type=ActionType.FINISH,
                action_input={},
                reasoning=f"行动解析失败: {str(e)}"
            )
    
    def _parse_action_response(self, response: str) -> Tuple[ActionType, Dict[str, Any], str]:
        """解析行动响应"""
        try:
            # 提取工具名称
            tool_match = re.search(r'工具名称:\s*(\w+)', response)
            tool_name = tool_match.group(1) if tool_match else "finish"
            
            # 提取理由
            reason_match = re.search(r'理由:\s*(.+)', response)
            reasoning = reason_match.group(1) if reason_match else "未提供理由"
            
            # 提取参数
            param_match = re.search(r'参数:\s*(.+)', response)
            param_text = param_match.group(1) if param_match else ""
            
            # 映射工具名称到动作类型
            action_type_map = {
                'search_documents': ActionType.SEARCH_DOCUMENTS,
                'search_web': ActionType.SEARCH_WEB,
                'calculate': ActionType.CALCULATE,
                'generate_content': ActionType.GENERATE_CONTENT,
                'finish': ActionType.FINISH
            }
            
            action_type = action_type_map.get(tool_name, ActionType.FINISH)
            
            # 构建动作输入
            action_input = {'query': param_text.strip()} if param_text.strip() else {}
            
            return action_type, action_input, reasoning
            
        except Exception as e:
            logger.error(f"解析行动响应失败: {e}")
            return ActionType.FINISH, {}, f"解析失败: {str(e)}"
    
    async def _observe(self, action: Action) -> Observation:
        """观察阶段"""
        try:
            # 根据动作类型执行相应工具
            if action.action_type == ActionType.SEARCH_DOCUMENTS:
                result = await self._search_documents_tool(action.action_input.get('query', ''))
                return Observation(
                    content=result,
                    success=True,
                    metadata={'tool': 'search_documents'}
                )
                
            elif action.action_type == ActionType.SEARCH_WEB:
                result = await self._search_web_tool(action.action_input.get('query', ''))
                return Observation(
                    content=result,
                    success=True,
                    metadata={'tool': 'search_web'}
                )
                
            elif action.action_type == ActionType.CALCULATE:
                result = self._calculate_tool(action.action_input.get('query', ''))
                return Observation(
                    content=result,
                    success=True,
                    metadata={'tool': 'calculate'}
                )
                
            elif action.action_type == ActionType.GENERATE_CONTENT:
                result = await self._generate_content_tool(action.action_input.get('query', ''))
                return Observation(
                    content=result,
                    success=True,
                    metadata={'tool': 'generate_content'}
                )
                
            else:  # FINISH
                return Observation(
                    content="任务完成",
                    success=True,
                    metadata={'tool': 'finish'}
                )
                
        except Exception as e:
            logger.error(f"观察阶段失败: {e}")
            return Observation(
                content=f"执行失败: {str(e)}",
                success=False,
                metadata={'error': str(e)}
            )
    
    async def _should_finish(self, collected_info: List[Dict], task: str) -> bool:
        """判断是否应该完成任务"""
        try:
            if len(collected_info) >= 5:  # 收集了足够的信息
                return True
            
            # 使用LLM判断信息是否充分
            info_summary = "\n".join([f"- {info['source']}: {info['content'][:100]}..." for info in collected_info])
            
            prompt = f"""任务: {task}

已收集信息:
{info_summary}

这些信息是否足够完成任务？请回答 "是" 或 "否"。"""
            
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            return "是" in response_text or "足够" in response_text
            
        except Exception as e:
            logger.error(f"判断是否完成失败: {e}")
            return len(collected_info) >= 3  # 默认阈值
    
    async def _generate_final_result(self, task: str, collected_info: List[Dict]) -> str:
        """生成最终结果"""
        try:
            # 整理收集的信息
            info_by_source = {}
            for info in collected_info:
                source = info['source']
                if source not in info_by_source:
                    info_by_source[source] = []
                info_by_source[source].append(info['content'])
            
            # 构建信息摘要
            info_summary = ""
            for source, contents in info_by_source.items():
                info_summary += f"\n{source.upper()}:\n"
                for content in contents:
                    info_summary += f"- {content[:200]}...\n"
            
            prompt = f"""任务: {task}

基于以下收集的信息，生成完整的回答:

{info_summary}

请生成一个完整、准确、有逻辑的回答，整合所有相关信息。"""
            
            response = await self.llm.ainvoke(prompt)
            if hasattr(response, 'content'):
                return response.content
            else:
                return str(response)
                
        except Exception as e:
            logger.error(f"生成最终结果失败: {e}")
            return f"生成结果失败: {str(e)}"
