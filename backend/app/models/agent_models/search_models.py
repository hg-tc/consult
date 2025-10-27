from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class SearchStrategy(BaseModel):
    """搜索策略"""
    global_queries: List[str] = Field(default_factory=list)
    workspace_queries: List[str] = Field(default_factory=list)
    web_queries: List[str] = Field(default_factory=list)
    search_depth: Literal["shallow", "normal", "deep"] = "normal"
    max_results_per_source: int = Field(default=10, ge=1, le=50)
    parallel_execution: bool = True

class SearchResult(BaseModel):
    """搜索结果片段"""
    content: str
    source: Literal["global_db", "workspace_db", "web"]
    document_name: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)
    chunk_id: Optional[str] = None

class AggregatedSearchResults(BaseModel):
    """聚合搜索结果"""
    global_results: List[SearchResult]
    workspace_results: List[SearchResult]
    web_results: List[SearchResult]
    total_sources: int
    average_relevance: float
    search_duration_ms: int
    deduplication_applied: bool

