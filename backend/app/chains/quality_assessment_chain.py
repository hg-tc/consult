from langchain_core.prompts import ChatPromptTemplate

def create_quality_assessment_chain(llm):
    """创建质量评估链（5维度评分）"""
    from app.models.agent_models import QualityMetrics
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是严格的质量审核专家。从5个维度评估内容：

1. **相关性** (0-1): 内容是否与用户需求高度相关
2. **完整性** (0-1): 是否覆盖所有要点，无遗漏
3. **准确性** (0-1): 信息是否准确无误，有依据
4. **可读性** (0-1): 语言是否流畅、结构是否清晰
5. **格式合规** (0-1): 是否符合目标格式要求

评分标准：
- 0.9-1.0: 优秀
- 0.8-0.9: 良好
- 0.7-0.8: 合格
- <0.7: 需改进

必须给出具体的改进建议。"""),
        ("user", """评估内容:
标题: {title}
格式: {output_format}
要求: {requirements}

内容:
{content}

请严格评分，不达标必须明确指出。""")
    ])
    
    return prompt | llm.with_structured_output(QualityMetrics)

