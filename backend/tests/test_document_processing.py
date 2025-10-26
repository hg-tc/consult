"""
文档处理系统测试套件
测试各种文件格式的处理能力
"""

import os
import sys
import asyncio
import tempfile
import logging
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.services.enhanced_document_processor import EnhancedDocumentProcessor, ProcessedDocument
from app.services.ocr_service import OCRService
from app.services.document_quality_checker import DocumentQualityChecker, QualityLevel
from app.services.langchain_rag_service import LangChainRAGService

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DocumentProcessingTester:
    """文档处理测试器"""
    
    def __init__(self):
        self.processor = EnhancedDocumentProcessor()
        self.ocr_service = OCRService()
        self.quality_checker = DocumentQualityChecker()
        self.rag_service = LangChainRAGService()
        
        # 测试结果
        self.test_results = []
    
    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("开始文档处理系统测试")
        
        # 1. 测试基础文档处理
        await self.test_basic_document_processing()
        
        # 2. 测试OCR功能
        await self.test_ocr_functionality()
        
        # 3. 测试质量检查
        await self.test_quality_checking()
        
        # 4. 测试RAG集成
        await self.test_rag_integration()
        
        # 5. 性能测试
        await self.test_performance()
        
        # 输出测试结果
        self.print_test_results()
    
    async def test_basic_document_processing(self):
        """测试基础文档处理"""
        logger.info("测试基础文档处理...")
        
        # 创建测试文档
        test_docs = await self.create_test_documents()
        
        for doc_info in test_docs:
            try:
                processed_doc = await self.processor.process_document(doc_info['path'])
                
                result = {
                    'test': 'basic_processing',
                    'file_type': doc_info['type'],
                    'success': True,
                    'chunks': len(processed_doc.chunks),
                    'quality_score': processed_doc.quality_score,
                    'processing_time': processed_doc.processing_time
                }
                
                logger.info(f"✓ {doc_info['type']} 处理成功: {len(processed_doc.chunks)} 块, 质量分数: {processed_doc.quality_score:.2f}")
                
            except Exception as e:
                result = {
                    'test': 'basic_processing',
                    'file_type': doc_info['type'],
                    'success': False,
                    'error': str(e)
                }
                logger.error(f"✗ {doc_info['type']} 处理失败: {e}")
            
            self.test_results.append(result)
    
    async def test_ocr_functionality(self):
        """测试OCR功能"""
        logger.info("测试OCR功能...")
        
        if not self.ocr_service.is_available():
            logger.warning("OCR服务不可用，跳过OCR测试")
            return
        
        # 创建测试图片
        test_image = await self.create_test_image()
        
        try:
            text = await self.ocr_service.extract_text_from_image(test_image)
            
            result = {
                'test': 'ocr_functionality',
                'success': True,
                'extracted_text_length': len(text),
                'has_text': bool(text.strip())
            }
            
            logger.info(f"✓ OCR测试成功: 提取文字长度 {len(text)}")
            
        except Exception as e:
            result = {
                'test': 'ocr_functionality',
                'success': False,
                'error': str(e)
            }
            logger.error(f"✗ OCR测试失败: {e}")
        
        self.test_results.append(result)
    
    async def test_quality_checking(self):
        """测试质量检查"""
        logger.info("测试质量检查...")
        
        # 创建测试文档
        test_docs = await self.create_test_documents()
        
        for doc_info in test_docs[:2]:  # 只测试前两个文档
            try:
                processed_doc = await self.processor.process_document(doc_info['path'])
                quality_report = self.quality_checker.check_document(processed_doc)
                
                result = {
                    'test': 'quality_checking',
                    'file_type': doc_info['type'],
                    'success': True,
                    'overall_score': quality_report.overall_score,
                    'quality_level': quality_report.quality_level.value,
                    'issues_count': len(quality_report.issues),
                    'recommendations_count': len(quality_report.recommendations)
                }
                
                logger.info(f"✓ 质量检查成功: {doc_info['type']}, 分数: {quality_report.overall_score:.2f}, 等级: {quality_report.quality_level.value}")
                
            except Exception as e:
                result = {
                    'test': 'quality_checking',
                    'file_type': doc_info['type'],
                    'success': False,
                    'error': str(e)
                }
                logger.error(f"✗ 质量检查失败: {e}")
            
            self.test_results.append(result)
    
    async def test_rag_integration(self):
        """测试RAG集成"""
        logger.info("测试RAG集成...")
        
        try:
            # 创建测试文档
            test_docs = await self.create_test_documents()
            test_doc = test_docs[0]  # 使用第一个测试文档
            
            # 添加到RAG系统
            workspace_id = "test_workspace"
            success = await self.rag_service.add_document(
                workspace_id=workspace_id,
                file_path=test_doc['path'],
                metadata={"test": True}
            )
            
            if success:
                # 测试搜索
                search_results = await self.rag_service.search_documents(
                    workspace_id=workspace_id,
                    query="测试查询",
                    top_k=3
                )
                
                # 测试问答
                qa_result = await self.rag_service.ask_question(
                    workspace_id=workspace_id,
                    question="这个文档的主要内容是什么？"
                )
                
                result = {
                    'test': 'rag_integration',
                    'success': True,
                    'document_added': success,
                    'search_results_count': len(search_results),
                    'qa_answer_length': len(qa_result.get('answer', '')),
                    'qa_confidence': qa_result.get('confidence', 0)
                }
                
                logger.info(f"✓ RAG集成测试成功: 搜索到 {len(search_results)} 个结果, 问答置信度: {qa_result.get('confidence', 0):.2f}")
                
            else:
                result = {
                    'test': 'rag_integration',
                    'success': False,
                    'error': '文档添加失败'
                }
                logger.error("✗ RAG集成测试失败: 文档添加失败")
            
        except Exception as e:
            result = {
                'test': 'rag_integration',
                'success': False,
                'error': str(e)
            }
            logger.error(f"✗ RAG集成测试失败: {e}")
        
        self.test_results.append(result)
    
    async def test_performance(self):
        """性能测试"""
        logger.info("测试性能...")
        
        try:
            # 创建大文档进行性能测试
            large_doc = await self.create_large_test_document()
            
            start_time = asyncio.get_event_loop().time()
            processed_doc = await self.processor.process_document(large_doc)
            end_time = asyncio.get_event_loop().time()
            
            processing_time = end_time - start_time
            
            result = {
                'test': 'performance',
                'success': True,
                'processing_time': processing_time,
                'chunks_count': len(processed_doc.chunks),
                'throughput': len(processed_doc.chunks) / processing_time if processing_time > 0 else 0
            }
            
            logger.info(f"✓ 性能测试成功: 处理时间 {processing_time:.2f}s, 吞吐量 {result['throughput']:.2f} 块/秒")
            
        except Exception as e:
            result = {
                'test': 'performance',
                'success': False,
                'error': str(e)
            }
            logger.error(f"✗ 性能测试失败: {e}")
        
        self.test_results.append(result)
    
    async def create_test_documents(self) -> List[Dict[str, Any]]:
        """创建测试文档"""
        test_docs = []
        
        # 创建临时目录
        temp_dir = Path(tempfile.mkdtemp())
        
        # 1. 文本文档
        txt_file = temp_dir / "test.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("这是一个测试文档。\n\n它包含多行文本内容。\n\n用于测试文档处理功能。")
        test_docs.append({'path': str(txt_file), 'type': 'txt'})
        
        # 2. Markdown文档
        md_file = temp_dir / "test.md"
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write("# 测试标题\n\n这是一个**测试**文档。\n\n## 子标题\n\n- 列表项1\n- 列表项2\n\n普通文本内容。")
        test_docs.append({'path': str(md_file), 'type': 'md'})
        
        return test_docs
    
    async def create_test_image(self) -> str:
        """创建测试图片"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # 创建测试图片
            img = Image.new('RGB', (400, 200), color='white')
            draw = ImageDraw.Draw(img)
            
            # 添加文字
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
            except:
                font = ImageFont.load_default()
            
            draw.text((50, 50), "Test OCR Text", fill='black', font=font)
            draw.text((50, 100), "测试OCR文字", fill='black', font=font)
            
            # 保存到临时文件
            temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            img.save(temp_file.name)
            temp_file.close()
            
            return temp_file.name
            
        except Exception as e:
            logger.warning(f"创建测试图片失败: {e}")
            return ""
    
    async def create_large_test_document(self) -> str:
        """创建大型测试文档"""
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        
        # 生成大量文本内容
        content = []
        for i in range(100):
            content.append(f"这是第 {i+1} 段测试内容。" * 10)
        
        temp_file.write('\n\n'.join(content))
        temp_file.close()
        
        return temp_file.name
    
    def print_test_results(self):
        """打印测试结果"""
        logger.info("\n" + "="*50)
        logger.info("文档处理系统测试结果")
        logger.info("="*50)
        
        # 按测试类型分组
        test_groups = {}
        for result in self.test_results:
            test_type = result['test']
            if test_type not in test_groups:
                test_groups[test_type] = []
            test_groups[test_type].append(result)
        
        # 打印每个测试组的结果
        for test_type, results in test_groups.items():
            logger.info(f"\n{test_type.upper()} 测试:")
            success_count = sum(1 for r in results if r['success'])
            total_count = len(results)
            
            logger.info(f"  成功率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
            
            for result in results:
                if result['success']:
                    logger.info(f"  ✓ {result.get('file_type', '')} 成功")
                else:
                    logger.info(f"  ✗ {result.get('file_type', '')} 失败: {result.get('error', '')}")
        
        # 总体统计
        total_success = sum(1 for r in self.test_results if r['success'])
        total_tests = len(self.test_results)
        
        logger.info(f"\n总体结果: {total_success}/{total_tests} ({total_success/total_tests*100:.1f}%)")
        
        if total_success == total_tests:
            logger.info("🎉 所有测试通过！")
        else:
            logger.info("⚠️  部分测试失败，需要检查")


async def main():
    """主函数"""
    tester = DocumentProcessingTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
