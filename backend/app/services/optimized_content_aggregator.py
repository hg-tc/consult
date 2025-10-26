#!/usr/bin/env python3
"""
内容聚合器优化版本
减少LLM调用次数，提高性能
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class OptimizedAggregatedContent:
    """优化的聚合内容"""
    title: str
    outline: List[Dict[str, Any]]
    sections: List[Dict[str, Any]]
    references: List[str]
    metadata: Dict[str, Any] = None

class OptimizedContentAggregator:
    """优化的内容聚合器"""
    
    def __init__(self, rag_service, llm):
        self.rag_service = rag_service
        self.llm = llm
    
    async def aggregate_content_optimized(
        self, 
        intent,
        workspace_id: str,
        conversation_history: List[Dict],
        search_query: Optional[str] = None
    ) -> OptimizedAggregatedContent:
        """
        优化的内容聚合（单次LLM调用）
        """
        try:
            logger.info(f"开始优化内容聚合: {intent.title}")
            start_time = time.time()
            
            # 1. 检索相关文档
            documents_content = await self._retrieve_documents_optimized(
                workspace_id, 
                search_query or intent.inferred_query or intent.title
            )
            
            # 2. 提取对话内容
            conversation_content = self._extract_conversation_content(conversation_history)
            
            # 3. 单次LLM调用生成完整文档
            logger.info("使用单次LLM调用生成完整文档...")
            
            comprehensive_prompt = f"""基于以下信息，生成完整的{intent.doc_type.value}文档：

文档标题: {intent.title}
文档类型: {intent.doc_type.value}
内容来源: {intent.content_source}

检索到的文档内容:
{documents_content[:2000]}

对话历史信息:
{conversation_content[:800]}

请生成完整的文档内容，要求：
1. 内容准确、完整、专业
2. 结构清晰，逻辑性强
3. 适合{intent.doc_type.value}格式
4. 包含具体数据和案例
5. 内容长度适中（每章节500-1000字）

返回JSON格式：
{{
    "outline": [
        {{"title": "第一章 标题", "level": 1}},
        {{"title": "1.1 子标题", "level": 2}}
    ],
    "sections": [
        {{
            "title": "第一章 标题",
            "level": 1,
            "content": "详细内容...",
            "table_data": [["列1", "列2"], ["数据1", "数据2"]],
            "subsections": [
                {{"title": "1.1 子标题", "content": "子内容..."}}
            ]
        }}
    ],
    "references": ["参考文献1", "参考文献2"]
}}"""
            
            # 调用LLM生成内容
            response = await self.llm.ainvoke(comprehensive_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析响应
            try:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    content_data = json.loads(json_match.group())
                else:
                    raise ValueError("未找到有效的JSON响应")
            except Exception as e:
                logger.warning(f"解析LLM响应失败: {e}")
                # 使用fallback内容
                content_data = self._generate_fallback_content(intent, documents_content, conversation_content)
            
            # 构建结果
            duration = time.time() - start_time
            logger.info(f"内容聚合完成，耗时: {duration:.2f}秒")
            
            return OptimizedAggregatedContent(
                title=intent.title,
                outline=content_data.get('outline', []),
                sections=content_data.get('sections', []),
                references=content_data.get('references', []),
                metadata={
                    "generation_time": duration,
                    "content_source": intent.content_source,
                    "doc_type": intent.doc_type.value,
                    "optimized": True
                }
            )
            
        except Exception as e:
            logger.error(f"优化内容聚合失败: {e}")
            # 返回基础内容
            return OptimizedAggregatedContent(
                title=intent.title,
                outline=[{"title": intent.title, "level": 1}],
                sections=[{
                    "title": intent.title,
                    "level": 1,
                    "content": f"基于用户请求生成的内容：{intent.inferred_query or intent.title}",
                    "table_data": [],
                    "subsections": []
                }],
                references=[],
                metadata={"error": str(e), "optimized": True}
            )
    
    async def _retrieve_documents_optimized(self, workspace_id: str, query: str) -> str:
        """优化的文档检索"""
        try:
            # 使用RAG服务检索文档
            result = await self.rag_service.search_documents(workspace_id, query, top_k=5)
            
            if result:
                content_parts = []
                for doc in result:
                    content_parts.append(f"文档: {doc.get('title', '未知')}\n内容: {doc.get('content', '')[:500]}")
                
                return "\n\n".join(content_parts)
            else:
                return "未找到相关文档内容"
                
        except Exception as e:
            logger.warning(f"文档检索失败: {e}")
            return "文档检索失败"
    
    def _extract_conversation_content(self, conversation_history: List[Dict]) -> str:
        """提取对话内容"""
        if not conversation_history:
            return ""
        
        conversation_parts = []
        for msg in conversation_history[-5:]:  # 只取最近5条
            role = "用户" if msg.get('role') == 'user' else "助手"
            content = msg.get('content', '')
            conversation_parts.append(f"{role}: {content}")
        
        return "\n".join(conversation_parts)
    
    def _generate_fallback_content(self, intent, documents_content: str, conversation_content: str) -> Dict:
        """生成fallback内容"""
        return {
            "outline": [
                {"title": intent.title, "level": 1},
                {"title": "概述", "level": 2},
                {"title": "详细内容", "level": 2},
                {"title": "总结", "level": 2}
            ],
            "sections": [
                {
                    "title": intent.title,
                    "level": 1,
                    "content": f"这是关于{intent.title}的文档。基于检索到的内容：{documents_content[:500]}",
                    "table_data": [],
                    "subsections": []
                },
                {
                    "title": "概述",
                    "level": 2,
                    "content": f"本文档旨在提供关于{intent.title}的全面信息。",
                    "table_data": [],
                    "subsections": []
                },
                {
                    "title": "详细内容",
                    "level": 2,
                    "content": f"基于检索到的信息：{documents_content[:800]}",
                    "table_data": [],
                    "subsections": []
                },
                {
                    "title": "总结",
                    "level": 2,
                    "content": f"总结：{intent.title}是一个重要的主题，需要进一步研究和应用。",
                    "table_data": [],
                    "subsections": []
                }
            ],
            "references": ["相关文档资料", "网络搜索信息", "对话历史记录"]
        }
