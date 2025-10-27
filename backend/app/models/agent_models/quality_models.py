from pydantic import BaseModel, Field, field_validator
from typing import List

class QualityMetrics(BaseModel):
    """5维质量评估"""
    relevance_score: float = Field(ge=0.0, le=1.0)
    completeness_score: float = Field(ge=0.0, le=1.0)
    accuracy_score: float = Field(ge=0.0, le=1.0)
    readability_score: float = Field(ge=0.0, le=1.0)
    format_compliance_score: float = Field(ge=0.0, le=1.0)
    overall_score: float = Field(ge=0.0, le=1.0)
    improvement_suggestions: List[str]
    critical_issues: List[str] = Field(default_factory=list)
    meets_threshold: bool
    requires_human_review: bool = False
    
    @field_validator('overall_score', mode='before')
    @classmethod
    def calculate_overall(cls, v, info):
        if isinstance(v, (int, float)) and v > 0:
            return v
        # 自动计算综合评分
        scores = [
            info.data.get('relevance_score', 0),
            info.data.get('completeness_score', 0),
            info.data.get('accuracy_score', 0),
            info.data.get('readability_score', 0),
            info.data.get('format_compliance_score', 0)
        ]
        return sum(scores) / len(scores)

