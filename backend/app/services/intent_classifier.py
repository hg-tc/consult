"""
意图识别服务
使用LLM分析用户输入，识别文件生成意图
"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# 使用统一的DocumentType定义
from app.services.document_generator_service import DocumentType


@dataclass
class IntentResult:
    """意图识别结果"""
    is_generation_intent: bool
    doc_type: DocumentType
    content_source: str  # documents/conversation/mixed
    title: str
    inferred_query: Optional[str]
    needs_confirmation: bool
    confirmation_message: Optional[str]
    extracted_params: Dict[str, Any]
    confidence: float = 0.0


class IntentClassifier:
    """意图分类器"""
    
    def __init__(self, llm):
        self.llm = llm
        self.intent_prompt = """你是一个智能助手，需要分析用户输入，判断用户是否想要生成文件。

用户输入: {user_input}
对话历史: {history}

请分析并判断以下内容：
1. 是否需要生成文件? (yes/no)
2. 文件类型? (word/excel/ppt/unknown)
3. 内容来源? (documents/conversation/mixed)
4. 建议的文档标题?
5. 是否需要确认? (yes/no)
6. 如果需要确认，确认问题是什么?
7. 推断的搜索查询词?
8. 置信度 (0.0-1.0)

请严格按照以下JSON格式返回：
{{
    "is_generation_intent": true/false,
    "doc_type": "word/excel/ppt/unknown",
    "content_source": "documents/conversation/mixed",
    "title": "建议的文档标题",
    "needs_confirmation": true/false,
    "confirmation_message": "确认问题（如果需要确认）",
    "inferred_query": "推断的搜索查询词",
    "confidence": 0.8,
    "extracted_params": {{
        "sections": ["章节1", "章节2"],
        "format": "详细格式要求",
        "style": "文档风格"
    }}
}}

重要规则：
- 如果用户说"帮我生成"、"做个报告"、"整理一下"、"总结成文档"、"生成文件"等，判断为需要生成文件
- 如果用户明确提到"Word"、"Excel"、"PPT"、"表格"、"幻灯片"等，确定文件类型
- 如果用户提到具体文档名或"根据XX文档"，内容来源为documents
- 如果用户说"把我们刚才讨论的"，内容来源为conversation
- **关键：只有在以下情况下才设置needs_confirmation为true：**
  1. 用户意图极其模糊，无法判断是否要生成文件
  2. 用户同时提到多种文件类型，无法确定具体类型
  3. 用户使用了"可能"、"也许"、"考虑"等不确定词汇
- **默认文件类型为Word，除非用户明确指定其他类型**
- **如果用户明确表达了生成意图，即使没有指定文件类型，也不要要求确认，直接使用Word类型**"""

    async def classify_intent(self, user_input: str, history: List[Dict]) -> IntentResult:
        """
        分析用户输入，识别文件生成意图（优化版）
        
        Args:
            user_input: 用户输入
            history: 对话历史
            
        Returns:
            IntentResult: 意图识别结果
        """
        try:
            logger.info(f"开始意图识别: {user_input[:50]}...")
            
            # 首先尝试快速关键词匹配
            quick_result = self._quick_keyword_classification(user_input)
            logger.info(f"快速识别结果: 置信度={quick_result.confidence}, 生成意图={quick_result.is_generation_intent}")
            
            if quick_result.confidence > 0.7:  # 降低阈值，提高快速识别命中率
                logger.info(f"快速意图识别成功: {quick_result.doc_type}")
                return quick_result
            
            # 如果快速识别置信度不够，再使用LLM（但设置超时）
            logger.info("快速识别置信度不足，使用LLM分析...")
            return await self._llm_classification_with_timeout(user_input, history)
            
        except Exception as e:
            logger.error(f"意图识别失败: {e}")
            return self._fallback_classification(user_input)
    
    def _quick_keyword_classification(self, user_input: str) -> IntentResult:
        """快速关键词匹配意图识别"""
        user_input_lower = user_input.lower()
        
        # 检查是否包含生成意图关键词（扩展版）
        generation_keywords = [
            '生成', '制作', '创建', '整理', '总结', '报告', '文档',
            '帮我做', '帮我写', '帮我整理', '帮我生成', '做个', '写个',
            '制作一个', '创建一个', '生成一个', '写一份', '做一份',
            '帮我', '请帮我', '能否帮我', '可以帮我', '麻烦帮我',
            '输出', '导出', '保存为', '转换为', '变成', '弄成'
        ]
        
        is_generation = any(keyword in user_input_lower for keyword in generation_keywords)
        
        if not is_generation:
            return IntentResult(
                is_generation_intent=False,
                doc_type=DocumentType.UNKNOWN,
                content_source='mixed',
                title="",
                inferred_query=user_input,
                needs_confirmation=False,
                confirmation_message="",
                extracted_params={},
                confidence=0.9
            )
        
        # 检查文件类型，默认为Word
        doc_type = DocumentType.WORD  # 默认使用Word
        if any(word in user_input_lower for word in ['excel', 'xlsx', '表格', '数据表']):
            doc_type = DocumentType.EXCEL
        elif any(word in user_input_lower for word in ['ppt', 'pptx', '幻灯片', '演示']):
            doc_type = DocumentType.PPT
        
        # 检查内容来源
        content_source = 'mixed'
        if any(word in user_input_lower for word in ['根据', '基于', '文档', '文件']):
            content_source = 'documents'
        elif any(word in user_input_lower for word in ['刚才', '讨论', '对话', '聊天']):
            content_source = 'conversation'
        
        return IntentResult(
            is_generation_intent=True,
            doc_type=doc_type,
            content_source=content_source,
            title=user_input[:50],
            inferred_query=user_input,
            needs_confirmation=False,
            confirmation_message="",
            extracted_params={},
            confidence=0.9
        )
    
    async def _llm_classification_with_timeout(self, user_input: str, history: List[Dict]) -> IntentResult:
        """带超时的LLM意图识别"""
        try:
            import asyncio
            
            # 设置5秒超时
            result = await asyncio.wait_for(
                self._llm_classification(user_input, history),
                timeout=5.0
            )
            return result
            
        except asyncio.TimeoutError:
            logger.warning("LLM意图识别超时，使用快速分类结果")
            return self._fallback_classification(user_input)
        except Exception as e:
            logger.error(f"LLM意图识别失败: {e}")
            return self._fallback_classification(user_input)
    
    async def _llm_classification(self, user_input: str, history: List[Dict]) -> IntentResult:
        """LLM意图识别（备用方案）"""
        try:
            # 构建对话历史字符串
            history_str = ""
            if history:
                history_lines = []
                for msg in history[-5:]:  # 只取最近5条消息
                    role = "用户" if msg.get('role') == 'user' else "助手"
                    content = msg.get('content', '')
                    history_lines.append(f"{role}: {content}")
                history_str = "\n".join(history_lines)
            
            # 构建提示
            prompt = self.intent_prompt.format(
                user_input=user_input,
                history=history_str
            )
            
            # 调用LLM
            response = await self.llm.ainvoke(prompt)
            
            # 处理不同类型的响应
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # 解析JSON响应
            try:
                # 清理响应内容，移除可能的markdown代码块标记
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]
                response_text = response_text.strip()
                
                # 提取JSON部分
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = response_text[json_start:json_end]
                    result_data = json.loads(json_str)
                else:
                    raise ValueError("未找到有效的JSON响应")
                
                # 构建IntentResult
                doc_type_str = result_data.get('doc_type', 'unknown').lower()
                if doc_type_str == 'unknown':
                    doc_type_str = 'word'  # 默认为Word文档
                doc_type = DocumentType(doc_type_str)
                
                return IntentResult(
                    is_generation_intent=result_data.get('is_generation_intent', False),
                    doc_type=doc_type,
                    content_source=result_data.get('content_source', 'mixed'),
                    title=result_data.get('title', '未命名文档'),
                    inferred_query=result_data.get('inferred_query'),
                    needs_confirmation=False,  # 强制不要求确认，让Agent更智能
                    confirmation_message="",
                    extracted_params=result_data.get('extracted_params', {}),
                    confidence=result_data.get('confidence', 0.5)
                )
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"解析LLM响应失败: {e}, 响应: {response_text}")
                # 回退到简单关键词匹配
                return self._fallback_classification(user_input)
                
        except Exception as e:
            logger.error(f"LLM意图识别失败: {e}")
            return self._fallback_classification(user_input)
    
    def _fallback_classification(self, user_input: str) -> IntentResult:
        """回退到关键词匹配的意图识别"""
        user_input_lower = user_input.lower()
        
        # 检查是否包含生成意图关键词
        generation_keywords = [
            '生成', '制作', '创建', '整理', '总结', '报告', '文档',
            '帮我做', '帮我写', '帮我整理', '帮我生成'
        ]
        
        is_generation = any(keyword in user_input_lower for keyword in generation_keywords)
        
        # 检查文件类型，默认为Word
        doc_type = DocumentType.WORD  # 默认使用Word
        if any(word in user_input_lower for word in ['excel', 'xlsx', '表格', '数据表']):
            doc_type = DocumentType.EXCEL
        elif any(word in user_input_lower for word in ['ppt', 'pptx', '幻灯片', '演示']):
            doc_type = DocumentType.PPT
        
        # 检查内容来源
        content_source = 'mixed'
        if any(word in user_input_lower for word in ['根据', '基于', '文档', '文件']):
            content_source = 'documents'
        elif any(word in user_input_lower for word in ['刚才', '讨论', '对话', '聊天']):
            content_source = 'conversation'
        
        return IntentResult(
            is_generation_intent=is_generation,
            doc_type=doc_type,
            content_source=content_source,
            title="用户请求的文档",
            inferred_query=user_input,
            needs_confirmation=False,  # 减少确认提示，默认使用Word
            confirmation_message="",
            extracted_params={},
            confidence=0.3
        )
    
    def get_doc_type_display(self, doc_type: DocumentType) -> str:
        """获取文档类型的中文显示名称"""
        type_map = {
            DocumentType.WORD: "Word文档",
            DocumentType.EXCEL: "Excel表格",
            DocumentType.PPT: "PPT演示文稿",
            DocumentType.UNKNOWN: "文档"
        }
        return type_map.get(doc_type, "文档")
