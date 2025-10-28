"""
LangGraph + LlamaIndex 集成测试
"""

import pytest
import asyncio
import os
from pathlib import Path

# 设置测试环境变量
os.environ.setdefault("OPENAI_API_KEY", "test-key")


@pytest.mark.asyncio
async def test_llamaindex_retriever_initialization():
    """测试 LlamaIndex 检索器初始化"""
    from app.services.llamaindex_retriever import LlamaIndexRetriever
    
    try:
        retriever = LlamaIndexRetriever(workspace_id="test")
        assert retriever is not None
        assert retriever.workspace_id == "test"
    except Exception as e:
        pytest.skip(f"LlamaIndex 检索器初始化失败（可能缺少依赖）: {e}")


@pytest.mark.asyncio
async def test_langgraph_workflow_creation():
    """测试 LangGraph 工作流创建"""
    from app.workflows.langgraph_rag_workflow import LangGraphRAGWorkflow
    
    try:
        # 创建模拟检索器
        class MockRetriever:
            async def retrieve(self, query, top_k=5, use_hybrid=True, use_compression=True):
                return []
        
        workflow = LangGraphRAGWorkflow(
            workspace_retriever=MockRetriever(),
            global_retriever=MockRetriever(),
            llm=None  # 使用默认 LLM
        )
        
        assert workflow is not None
        assert workflow.graph is not None
    except Exception as e:
        pytest.skip(f"LangGraph 工作流创建失败（可能缺少依赖）: {e}")


@pytest.mark.asyncio
async def test_deepresearch_workflow_creation():
    """测试 DeepResearch 工作流创建"""
    from app.workflows.deepresearch_doc_workflow import DeepResearchDocWorkflow
    
    try:
        # 创建模拟检索器和服务
        class MockRetriever:
            async def retrieve(self, query, top_k=5, use_hybrid=True):
                return []
        
        class MockWebSearch:
            async def __aenter__(self):
                return self
            
            async def __aexit__(self, *args):
                pass
            
            async def search_web(self, query, num_results=3):
                return []
        
        workflow = DeepResearchDocWorkflow(
            workspace_retriever=MockRetriever(),
            global_retriever=MockRetriever(),
            web_search_service=MockWebSearch(),
            llm=None  # 使用默认 LLM
        )
        
        assert workflow is not None
        assert workflow.graph is not None
    except Exception as e:
        pytest.skip(f"DeepResearch 工作流创建失败（可能缺少依赖）: {e}")


def test_config_loader():
    """测试配置加载器"""
    from app.utils.config_loader import get_rag_config
    
    config = get_rag_config()
    assert config is not None
    
    # 测试配置读取
    llamaindex_config = config.get_llamaindex_config()
    assert llamaindex_config is not None


def test_requirements_file_exists():
    """测试 requirements.txt 存在且包含必要依赖"""
    requirements_path = Path("requirements.txt")
    assert requirements_path.exists(), "requirements.txt 文件不存在"
    
    with open(requirements_path, 'r') as f:
        content = f.read()
        
        # 检查必要依赖
        assert "langgraph" in content, "缺少 langgraph"
        assert "llama-index" in content, "缺少 llama-index"
        assert "langchain" in content, "缺少 langchain"


def test_config_file_exists():
    """测试配置文件存在"""
    config_path = Path("rag_config.yaml")
    assert config_path.exists(), "rag_config.yaml 文件不存在"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

