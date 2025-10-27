import asyncio
import logging
from typing import List, Dict, Any
from .base_agent import BaseProductionAgent
from app.models.agent_models import SearchResult, AggregatedSearchResults

logger = logging.getLogger(__name__)

class GlobalDatabaseAgent(BaseProductionAgent):
    """全局数据库查询 Agent"""
    
    def __init__(self, llm, rag_service):
        super().__init__("GlobalDatabase", llm, {})
        self.rag_service = rag_service
        
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行全局数据库查询"""
        search_strategy = state.get("search_strategy")
        if not search_strategy:
            logger.warning("搜索策略不存在，跳过全局数据库查询")
            return {"global_results": []}
        
        results = []
        
        try:
            for query in search_strategy.global_queries:
                logger.info(f"查询全局数据库: {query}")
                
                rag_result = await self.rag_service.ask_question(
                    workspace_id="global",
                    question=query,
                    top_k=search_strategy.max_results_per_source
                )
                
                for ref in rag_result.get("references", []):
                    results.append(SearchResult(
                        content=ref.get("content_preview", ""),
                        source="global_db",
                        document_name=ref.get("metadata", {}).get("original_filename", ""),
                        relevance_score=ref.get("similarity", 0.0),
                        metadata=ref.get("metadata", {}),
                        chunk_id=ref.get("chunk_id")
                    ))
            
            logger.info(f"全局数据库查询完成，找到 {len(results)} 条结果")
        except Exception as e:
            logger.error(f"全局数据库查询失败: {e}")
        
        return {"global_results": results}

class WorkspaceDatabaseAgent(BaseProductionAgent):
    """工作区数据库查询 Agent"""
    
    def __init__(self, llm, rag_service):
        super().__init__("WorkspaceDatabase", llm, {})
        self.rag_service = rag_service
        
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行工作区数据库查询"""
        search_strategy = state.get("search_strategy")
        workspace_id = state.get("workspace_id")
        
        if not search_strategy or not workspace_id:
            logger.warning("搜索策略或工作区ID不存在")
            return {"workspace_results": []}
        
        results = []
        
        try:
            for query in search_strategy.workspace_queries:
                logger.info(f"查询工作区数据库 [{workspace_id}]: {query}")
                
                rag_result = await self.rag_service.ask_question(
                    workspace_id=workspace_id,
                    question=query,
                    top_k=search_strategy.max_results_per_source
                )
                
                for ref in rag_result.get("references", []):
                    results.append(SearchResult(
                        content=ref.get("content_preview", ""),
                        source="workspace_db",
                        document_name=ref.get("metadata", {}).get("original_filename", ""),
                        relevance_score=ref.get("similarity", 0.0),
                        metadata=ref.get("metadata", {}),
                        chunk_id=ref.get("chunk_id")
                    ))
            
            logger.info(f"工作区数据库查询完成，找到 {len(results)} 条结果")
        except Exception as e:
            logger.error(f"工作区数据库查询失败: {e}")
        
        return {"workspace_results": results}

class ParallelSearchOrchestrator:
    """并行搜索编排器"""
    
    def __init__(self, global_agent, workspace_agent, web_agent=None):
        self.global_agent = global_agent
        self.workspace_agent = workspace_agent
        self.web_agent = web_agent
        
    async def execute_parallel(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """并行执行所有搜索"""
        import time
        start_time = time.time()
        
        intent = state.get("intent")
        tasks = []
        
        # 处理意图数据 - 兼容字典和对象
        if isinstance(intent, dict):
            requires_global_search = intent.get("requires_global_search", False)
            requires_workspace_search = intent.get("requires_workspace_search", False)
        else:
            requires_global_search = intent.requires_global_search if hasattr(intent, 'requires_global_search') else False
            requires_workspace_search = intent.requires_workspace_search if hasattr(intent, 'requires_workspace_search') else False
        
        # 根据意图决定需要哪些搜索
        if intent and requires_global_search:
            tasks.append(self.global_agent.execute(state))
            
        if intent and requires_workspace_search:
            tasks.append(self.workspace_agent.execute(state))
        
        # 处理 web search
        if isinstance(intent, dict):
            requires_web_search = intent.get("requires_web_search", False)
        else:
            requires_web_search = intent.requires_web_search if hasattr(intent, 'requires_web_search') else False
            
        if intent and requires_web_search and self.web_agent:
            tasks.append(self.web_agent.execute(state))
        
        if not tasks:
            logger.warning("没有需要执行的搜索任务")
            aggregated = AggregatedSearchResults(
                global_results=[],
                workspace_results=[],
                web_results=[],
                total_sources=0,
                average_relevance=0.0,
                search_duration_ms=int((time.time() - start_time) * 1000),
                deduplication_applied=False
            )
            return {"search_results": aggregated}
        
        # 并行执行搜索
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 合并结果
        global_results = []
        workspace_results = []
        web_results = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"搜索任务 {i} 失败: {result}")
                continue
            
            global_results.extend(result.get("global_results", []))
            workspace_results.extend(result.get("workspace_results", []))
            web_results.extend(result.get("web_results", []))
        
        # 计算统计信息
        all_results = global_results + workspace_results + web_results
        avg_relevance = (
            sum(r.relevance_score for r in all_results) / len(all_results)
            if all_results else 0.0
        )
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        aggregated = AggregatedSearchResults(
            global_results=global_results,
            workspace_results=workspace_results,
            web_results=web_results,
            total_sources=len(all_results),
            average_relevance=avg_relevance,
            search_duration_ms=duration_ms,
            deduplication_applied=False
        )
        
        logger.info(
            f"并行搜索完成: 全局{len(global_results)}条, "
            f"工作区{len(workspace_results)}条, "
            f"网络{len(web_results)}条, "
            f"耗时{duration_ms}ms"
        )
        
        return {"search_results": aggregated}

