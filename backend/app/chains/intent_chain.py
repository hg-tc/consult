from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_openai import ChatOpenAI
import os

def create_intent_analysis_chain(llm):
    """创建意图分析链（结构化输出）"""
    from app.models.agent_models import IntentAnalysis
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是专业的任务分析专家。分析用户请求，提取关键信息。
        
重点关注：
1. 任务类型和复杂度
2. 需要查询的数据源（全局数据库、工作区数据库、互联网）
3. 输出格式要求
4. 质量标准

必须返回严格的 JSON 格式。"""),
        ("user", """用户请求: {user_request}
工作区ID: {workspace_id}
对话历史: {conversation_history}

请分析并返回结构化的意图信息。""")
    ])
    
    # 使用 with_structured_output 获取结构化输出
    chain = prompt | llm.with_structured_output(IntentAnalysis)
    
    return chain

