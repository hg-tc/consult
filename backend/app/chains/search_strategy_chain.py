from langchain_core.prompts import ChatPromptTemplate

def create_search_strategy_chain(llm):
    """创建搜索策略链"""
    from app.models.agent_models import SearchStrategy
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是搜索策略专家。根据意图分析制定最优搜索策略。
        
策略要点：
1. 为每个数据源生成精准的查询关键词
2. 评估搜索深度需求
3. 决定是否并行执行
4. 预估所需结果数量

返回 JSON 格式的搜索策略。"""),
        ("user", """意图分析: {intent}
关键主题: {key_topics}
数据源: {data_sources}

请制定详细的搜索策略。""")
    ])
    
    return prompt | llm.with_structured_output(SearchStrategy)

