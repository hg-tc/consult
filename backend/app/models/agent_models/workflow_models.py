from typing import TypedDict, Annotated, Optional, List
import operator

# 导入其他模型
from .intent_models import IntentAnalysis
from .search_models import SearchStrategy, AggregatedSearchResults
from .quality_models import QualityMetrics

class AgentState(TypedDict):
    """LangGraph 状态定义"""
    # 输入
    user_request: str
    workspace_id: str
    conversation_history: List[dict]
    
    # 意图分析
    intent: Optional[IntentAnalysis]
    
    # 搜索阶段
    search_strategy: Optional[SearchStrategy]
    search_results: Optional[AggregatedSearchResults]
    
    # 内容规划
    content_outline: Optional[dict]
    
    # 生成阶段
    draft_content: str
    generated_sections: List[dict]
    
    # 质量评估
    quality_metrics: Optional[QualityMetrics]
    iteration_count: int
    
    # 人机交互
    pending_confirmation: Optional[dict]
    user_feedback: Optional[str]
    
    # 最终输出
    final_document: Optional[dict]
    output_file_path: Optional[str]
    
    # 元数据
    current_step: str
    error: Optional[str]
    messages: Annotated[List[str], operator.add]

