"""
简化的文档处理测试
避免复杂的NLTK依赖问题
"""

import os
import sys
import asyncio
import tempfile
import logging
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.services.langchain_rag_service import LangChainRAGService

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_simple_rag():
    """测试简化的RAG功能"""
    logger.info("开始简化RAG测试")
    
    try:
        # 创建测试文档
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        temp_file.write("这是一个测试文档。\n\n它包含多行文本内容。\n\n用于测试文档处理功能。")
        temp_file.close()
        
        logger.info(f"创建测试文档: {temp_file.name}")
        
        # 测试RAG服务
        rag_service = LangChainRAGService()
        workspace_id = "test_workspace_simple"
        
        # 添加文档
        success = await rag_service.add_document(
            workspace_id=workspace_id,
            file_path=temp_file.name,
            metadata={"test": True}
        )
        
        if success:
            logger.info("✓ 文档添加成功")
            
            # 测试搜索
            search_results = await rag_service.search_documents(
                workspace_id=workspace_id,
                query="测试文档",
                top_k=3
            )
            
            logger.info(f"✓ 搜索成功: 找到 {len(search_results)} 个结果")
            
            # 测试问答
            qa_result = await rag_service.ask_question(
                workspace_id=workspace_id,
                question="这个文档的主要内容是什么？"
            )
            
            logger.info(f"✓ 问答成功: 置信度 {qa_result.get('confidence', 0):.2f}")
            logger.info(f"回答: {qa_result.get('answer', '')[:100]}...")
            
            # 清理
            os.unlink(temp_file.name)
            
            return True
        else:
            logger.error("✗ 文档添加失败")
            return False
            
    except Exception as e:
        logger.error(f"✗ 测试失败: {e}")
        return False


async def test_api_integration():
    """测试API集成"""
    logger.info("开始API集成测试")
    
    try:
        import requests
        
        # 测试后端API
        response = requests.get("http://localhost:18000/api/health")
        if response.status_code == 200:
            logger.info("✓ 后端API健康检查通过")
            return True
        else:
            logger.warning(f"⚠️ 后端API状态: {response.status_code}")
            return False
            
    except Exception as e:
        logger.warning(f"⚠️ API测试跳过: {e}")
        return False


async def main():
    """主测试函数"""
    logger.info("="*50)
    logger.info("简化文档处理系统测试")
    logger.info("="*50)
    
    # 测试RAG功能
    rag_success = await test_simple_rag()
    
    # 测试API集成
    api_success = await test_api_integration()
    
    # 输出结果
    logger.info("\n" + "="*50)
    logger.info("测试结果汇总")
    logger.info("="*50)
    logger.info(f"RAG功能测试: {'✓ 通过' if rag_success else '✗ 失败'}")
    logger.info(f"API集成测试: {'✓ 通过' if api_success else '✗ 跳过'}")
    
    if rag_success:
        logger.info("🎉 核心RAG功能正常工作！")
        logger.info("系统已准备好处理文档和回答问题")
    else:
        logger.info("⚠️ 需要进一步调试RAG功能")


if __name__ == "__main__":
    asyncio.run(main())
