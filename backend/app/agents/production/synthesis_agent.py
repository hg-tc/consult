import logging
from typing import List, Dict, Any
from .base_agent import BaseProductionAgent
from app.models.agent_models import SearchResult

logger = logging.getLogger(__name__)

class InformationSynthesisAgent(BaseProductionAgent):
    """信息综合 Agent - 去重、排序、提取关键信息"""
    
    def __init__(self, llm):
        super().__init__("InformationSynthesis", llm, {})
    
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        1. 去重（基于内容相似度）
        2. 按相关性排序
        3. 提取关键信息点
        4. 识别信息缺口
        """
        search_results = state.get("search_results")
        if not search_results:
            logger.warning("搜索结果不存在")
            return {"synthesized_info": "", "key_sources": []}
        
        # 合并所有搜索结果
        all_results = (
            search_results.global_results + 
            search_results.workspace_results + 
            search_results.web_results
        )
        
        # 去重逻辑
        deduplicated = self._deduplicate_results(all_results)
        
        # 按相关性排序
        sorted_results = sorted(
            deduplicated, 
            key=lambda x: x.relevance_score, 
            reverse=True
        )
        
        # 保留前20条最相关的结果
        top_results = sorted_results[:20]
        
        # 使用 LLM 提取关键信息
        try:
            synthesis = await self._extract_key_information(top_results, state)
        except Exception as e:
            logger.error(f"信息提取失败: {e}")
            # 回退到简单汇总
            synthesis = self._simple_synthesis(top_results)
        
        return {
            "synthesized_info": synthesis,
            "key_sources": top_results,
            "total_unique_results": len(deduplicated),
            "original_results_count": len(all_results)
        }
    
    def _deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """基于内容相似度去重"""
        if len(results) <= 1:
            return results
        
        deduplicated = []
        seen_contents = set()
        
        for result in results:
            # 简化的去重逻辑：基于内容前100个字符
            content_key = result.content[:100].strip().lower()
            
            if content_key not in seen_contents:
                seen_contents.add(content_key)
                deduplicated.append(result)
        
        logger.info(f"去重完成: {len(results)} -> {len(deduplicated)}")
        return deduplicated
    
    async def _extract_key_information(
        self, 
        results: List[SearchResult], 
        state: Dict[str, Any]
    ) -> str:
        """使用 LLM 提取关键信息"""
        intent = state.get("intent")
        user_request = state.get("user_request", "")
        
        # 格式化搜索结果
        formatted_results = self._format_results(results)
        
        prompt = f"""分析以下搜索结果，提取关键信息：

用户需求：{user_request}
相关主题：{', '.join(intent.key_topics) if intent else ''}

搜索结果：
{formatted_results}

请提取：
1. 核心事实和数据
2. 主要观点和结论
3. 关键引用和来源
4. 信息缺口比如无（如有）

要求：
- 信息准确、有依据
- 结构清晰、逻辑严密
- 重点关注与用户需求相关的内容
"""
        
        response = await self.llm.ainvoke(prompt)
        content = response.content if hasattr(response, 'content') else str(response)
        
        return content
    
    def _format_results(self, results: List[SearchResult]) -> str:
        """格式化搜索结果用于 LLM 分析"""
        formatted = []
        
        for i, result in enumerate(results, 1):
            formatted.append(f"""
[结果 {i}] 来源：{result.document_name} | 相关性：{result.relevance_score:.2f}
{result.content[:500]}
---
""")
        
        return "\n".join(formatted)
    
    def _simple_synthesis(self, results: List[SearchResult]) -> str:
        """简单汇总（不使用 LLM）"""
        synthesis = f"共找到 {len(results)} 个相关文档片段：\n\n"
        
        for i, result in enumerate(results[:10], 1):
            synthesis += f"{i}. [{result.document_name}] {result.content[:200]}...\n\n"
        
        return synthesis

