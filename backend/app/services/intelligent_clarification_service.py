"""
智能澄清服务 - 基于现代AI实践的动态询问系统
"""

import logging
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ClarificationType(Enum):
    """澄清类型"""
    AMBIGUOUS_INTENT = "ambiguous_intent"      # 意图模糊
    MISSING_CONTEXT = "missing_context"        # 缺少上下文
    UNCLEAR_REQUIREMENTS = "unclear_requirements"  # 需求不明确
    TECHNICAL_CONSTRAINTS = "technical_constraints"  # 技术约束
    QUALITY_EXPECTATIONS = "quality_expectations"  # 质量期望

@dataclass
class ClarificationQuestion:
    """澄清问题"""
    type: ClarificationType
    question: str
    options: List[str] = None
    context: str = ""
    priority: int = 1  # 1-5, 5最高

@dataclass
class ClarificationResult:
    """澄清结果"""
    needs_clarification: bool
    questions: List[ClarificationQuestion]
    confidence: float
    suggested_action: str

class IntelligentClarificationService:
    """智能澄清服务"""
    
    def __init__(self, llm):
        self.llm = llm
        self.clarification_patterns = self._load_clarification_patterns()
    
    def _load_clarification_patterns(self) -> Dict[str, List[str]]:
        """加载澄清模式"""
        return {
            "ambiguous_intent": [
                "您希望生成什么类型的文档？",
                "这个文档的主要用途是什么？",
                "您更关注内容的哪个方面？"
            ],
            "missing_context": [
                "您希望基于哪些信息来生成文档？",
                "是否有特定的参考文档或数据？",
                "您希望包含哪些关键信息？"
            ],
            "unclear_requirements": [
                "您对文档的格式有什么特殊要求吗？",
                "您希望文档的详细程度如何？",
                "是否有特定的结构或章节要求？"
            ],
            "technical_constraints": [
                "您希望文档包含图表或表格吗？",
                "是否需要特定的数据可视化？",
                "您对文档长度有什么要求？"
            ],
            "quality_expectations": [
                "您希望文档达到什么质量水平？",
                "是否需要专业术语或通俗易懂？",
                "您对文档的准确性有什么要求？"
            ]
        }
    
    async def analyze_user_request(self, user_input: str, context: Dict[str, Any] = None) -> ClarificationResult:
        """分析用户请求，确定是否需要澄清"""
        try:
            # 构建分析提示
            analysis_prompt = self._build_analysis_prompt(user_input, context or {})
            
            # 调用LLM分析
            response = await self.llm.ainvoke(analysis_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析分析结果
            analysis_result = self._parse_analysis_response(response_text)
            
            # 生成澄清问题
            clarification_questions = self._generate_clarification_questions(analysis_result)
            
            return ClarificationResult(
                needs_clarification=len(clarification_questions) > 0,
                questions=clarification_questions,
                confidence=analysis_result.get('confidence', 0.5),
                suggested_action=analysis_result.get('suggested_action', 'proceed')
            )
            
        except Exception as e:
            logger.error(f"澄清分析失败: {e}")
            return ClarificationResult(
                needs_clarification=False,
                questions=[],
                confidence=0.0,
                suggested_action="proceed"
            )
    
    def _build_analysis_prompt(self, user_input: str, context: Dict[str, Any]) -> str:
        """构建分析提示"""
        return f"""你是一个智能助手，需要分析用户请求的清晰度和完整性。

用户请求: {user_input}
上下文信息: {json.dumps(context, ensure_ascii=False, indent=2)}

请分析以下方面：
1. 意图清晰度 (0-1)
2. 上下文完整性 (0-1) 
3. 需求明确性 (0-1)
4. 技术约束明确性 (0-1)
5. 质量期望明确性 (0-1)

对于每个评分低于0.7的方面，请指出具体的不明确之处。

请以JSON格式返回：
{{
    "intent_clarity": 0.8,
    "context_completeness": 0.6,
    "requirements_clarity": 0.7,
    "technical_constraints": 0.5,
    "quality_expectations": 0.4,
    "confidence": 0.6,
    "unclear_aspects": [
        {{
            "aspect": "technical_constraints",
            "description": "用户没有明确是否需要图表或表格",
            "impact": "可能影响文档生成的质量和格式"
        }}
    ],
    "suggested_action": "ask_clarification" 或 "proceed"
}}"""
    
    def _parse_analysis_response(self, response_text: str) -> Dict[str, Any]:
        """解析分析响应"""
        try:
            # 提取JSON部分
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
        except Exception as e:
            logger.warning(f"解析分析响应失败: {e}")
        
        return {"confidence": 0.5, "suggested_action": "proceed"}
    
    def _generate_clarification_questions(self, analysis_result: Dict[str, Any]) -> List[ClarificationQuestion]:
        """生成澄清问题"""
        questions = []
        unclear_aspects = analysis_result.get('unclear_aspects', [])
        
        for aspect in unclear_aspects:
            aspect_type = aspect.get('aspect', '')
            description = aspect.get('description', '')
            
            # 根据不明确方面生成问题
            if aspect_type in self.clarification_patterns:
                pattern_questions = self.clarification_patterns[aspect_type]
                for question_text in pattern_questions:
                    questions.append(ClarificationQuestion(
                        type=ClarificationType(aspect_type),
                        question=question_text,
                        context=description,
                        priority=self._calculate_priority(aspect_type)
                    ))
        
        # 按优先级排序
        questions.sort(key=lambda x: x.priority, reverse=True)
        return questions[:3]  # 最多返回3个问题
    
    def _calculate_priority(self, aspect_type: str) -> int:
        """计算问题优先级"""
        priority_map = {
            "ambiguous_intent": 5,
            "missing_context": 4,
            "unclear_requirements": 3,
            "technical_constraints": 2,
            "quality_expectations": 1
        }
        return priority_map.get(aspect_type, 1)
    
    async def process_clarification_response(self, 
                                          original_request: str, 
                                          clarification_response: Dict[str, str]) -> Dict[str, Any]:
        """处理澄清响应，生成增强的请求"""
        try:
            # 构建增强请求
            enhanced_prompt = f"""基于原始请求和澄清信息，生成一个完整、明确的文档生成请求。

原始请求: {original_request}
澄清信息: {json.dumps(clarification_response, ensure_ascii=False, indent=2)}

请生成一个结构化的文档生成请求，包含：
1. 明确的文档类型和格式
2. 具体的内容要求
3. 技术约束和质量期望
4. 参考信息源

返回JSON格式：
{{
    "enhanced_request": "增强后的请求描述",
    "document_type": "word/excel/ppt",
    "content_requirements": ["要求1", "要求2"],
    "technical_constraints": ["约束1", "约束2"],
    "quality_expectations": "质量期望描述",
    "reference_sources": ["来源1", "来源2"]
}}"""
            
            response = await self.llm.ainvoke(enhanced_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析增强请求
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
                
        except Exception as e:
            logger.error(f"处理澄清响应失败: {e}")
        
        return {"enhanced_request": original_request}
