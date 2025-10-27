from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional
from enum import Enum

class TaskComplexity(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium" 
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"

class IntentAnalysis(BaseModel):
    """意图分析结果（结构化输出）"""
    task_type: Literal["document_generation", "data_analysis", "qa", "research", "mixed"]
    output_format: Literal["word", "pdf", "excel", "ppt", "markdown", "json"]
    complexity: TaskComplexity
    requires_global_search: bool
    requires_workspace_search: bool
    requires_web_search: bool
    key_topics: List[str] = Field(min_length=1)
    data_sources: List[str]
    quality_requirements: List[str]
    estimated_output_size: str
    needs_confirmation: bool
    confirmation_points: List[str] = Field(default_factory=list)
    
    @field_validator('key_topics')
    @classmethod
    def validate_topics(cls, v):
        if not v:
            raise ValueError("至少需要一个关键主题")
        return v

