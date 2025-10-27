"""
多解析器策略服务
结合PyMuPDF、pdfplumber、unstructured等多种解析器
根据文档类型和内容选择最佳解析策略
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import fitz  # PyMuPDF
import pdfplumber
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.docx import partition_docx
from unstructured.partition.xlsx import partition_xlsx
from unstructured.partition.pptx import partition_pptx
from dataclasses import dataclass
import json
import time

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """解析结果"""
    content: str
    metadata: Dict[str, Any]
    elements: List[Dict[str, Any]]
    parser_used: str
    confidence: float
    processing_time: float
    quality_score: float


@dataclass
class DocumentInfo:
    """文档信息"""
    file_path: str
    file_type: str
    file_size: int
    page_count: int
    has_images: bool
    has_tables: bool
    has_text: bool
    complexity_score: float


class MultiParserStrategy:
    """多解析器策略"""
    
    def __init__(self):
        self.parsers = {
            'pymupdf': self._parse_with_pymupdf,
            'pdfplumber': self._parse_with_pdfplumber,
            'unstructured': self._parse_with_unstructured
        }
        
        # 解析器优先级配置
        self.parser_priority = {
            'pdf': ['unstructured', 'pdfplumber', 'pymupdf'],
            'docx': ['unstructured'],
            'xlsx': ['unstructured'],
            'pptx': ['unstructured'],
            'txt': ['unstructured']
        }
    
    def parse_document(self, file_path: str) -> ParseResult:
        """解析文档，使用最佳策略"""
        try:
            # 分析文档信息
            doc_info = self._analyze_document(file_path)
            logger.info(f"文档分析完成: {doc_info}")
            
            # 选择最佳解析器
            best_parser = self._select_best_parser(doc_info)
            logger.info(f"选择解析器: {best_parser}")
            
            # 执行解析
            result = self._execute_parser(best_parser, file_path, doc_info)
            
            # 后处理和质量评估
            result = self._post_process_result(result, doc_info)
            
            logger.info(f"解析完成: {result.parser_used}, 置信度: {result.confidence:.2f}")
            return result
            
        except Exception as e:
            logger.error(f"文档解析失败: {str(e)}")
            # 返回备用解析结果
            return self._fallback_parse(file_path)
    
    def _analyze_document(self, file_path: str) -> DocumentInfo:
        """分析文档信息"""
        try:
            path = Path(file_path)
            file_type = path.suffix.lower().lstrip('.')
            file_size = path.stat().st_size
            
            # 基础信息
            doc_info = DocumentInfo(
                file_path=file_path,
                file_type=file_type,
                file_size=file_size,
                page_count=0,
                has_images=False,
                has_tables=False,
                has_text=False,
                complexity_score=0.0
            )
            
            # 根据文件类型分析
            if file_type == 'pdf':
                doc_info = self._analyze_pdf(doc_info)
            elif file_type in ['docx', 'xlsx', 'pptx']:
                doc_info = self._analyze_office_doc(doc_info)
            elif file_type == 'txt':
                doc_info = self._analyze_text_file(doc_info)
            
            # 计算复杂度分数
            doc_info.complexity_score = self._calculate_complexity_score(doc_info)
            
            return doc_info
            
        except Exception as e:
            logger.error(f"文档分析失败: {str(e)}")
            return DocumentInfo(
                file_path=file_path,
                file_type='unknown',
                file_size=0,
                page_count=0,
                has_images=False,
                has_tables=False,
                has_text=False,
                complexity_score=0.5
            )
    
    def _analyze_pdf(self, doc_info: DocumentInfo) -> DocumentInfo:
        """分析PDF文档"""
        try:
            doc = fitz.open(doc_info.file_path)
            doc_info.page_count = len(doc)
            
            # 分析页面内容
            for page_num in range(min(3, len(doc))):  # 只分析前3页
                page = doc[page_num]
                
                # 检查文本
                text = page.get_text()
                if text.strip():
                    doc_info.has_text = True
                
                # 检查图片
                image_list = page.get_images()
                if image_list:
                    doc_info.has_images = True
                
                # 检查表格（简单检测）
                if 'table' in text.lower() or '|' in text:
                    doc_info.has_tables = True
            
            doc.close()
            
        except Exception as e:
            logger.error(f"PDF分析失败: {str(e)}")
        
        return doc_info
    
    def _analyze_office_doc(self, doc_info: DocumentInfo) -> DocumentInfo:
        """分析Office文档"""
        try:
            # 使用unstructured进行快速分析
            if doc_info.file_type == 'docx':
                elements = partition_docx(doc_info.file_path)
            elif doc_info.file_type == 'xlsx':
                elements = partition_xlsx(doc_info.file_path)
            elif doc_info.file_type == 'pptx':
                elements = partition_pptx(doc_info.file_path)
            else:
                return doc_info
            
            # 分析元素类型
            for element in elements[:10]:  # 只分析前10个元素
                if hasattr(element, 'text') and element.text.strip():
                    doc_info.has_text = True
                
                if element.category == 'Table':
                    doc_info.has_tables = True
                
                if element.category == 'Image':
                    doc_info.has_images = True
            
            # 估算页数
            doc_info.page_count = max(1, len(elements) // 10)
            
        except Exception as e:
            logger.error(f"Office文档分析失败: {str(e)}")
        
        return doc_info
    
    def _analyze_text_file(self, doc_info: DocumentInfo) -> DocumentInfo:
        """分析文本文件"""
        try:
            with open(doc_info.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            doc_info.has_text = bool(content.strip())
            doc_info.page_count = max(1, len(content) // 2000)  # 估算页数
            
        except Exception as e:
            logger.error(f"文本文件分析失败: {str(e)}")
        
        return doc_info
    
    def _calculate_complexity_score(self, doc_info: DocumentInfo) -> float:
        """计算文档复杂度分数"""
        score = 0.0
        
        # 基于文件大小
        if doc_info.file_size > 10 * 1024 * 1024:  # 10MB
            score += 0.3
        elif doc_info.file_size > 1 * 1024 * 1024:  # 1MB
            score += 0.2
        else:
            score += 0.1
        
        # 基于页数
        if doc_info.page_count > 50:
            score += 0.3
        elif doc_info.page_count > 10:
            score += 0.2
        else:
            score += 0.1
        
        # 基于内容类型
        if doc_info.has_images:
            score += 0.2
        if doc_info.has_tables:
            score += 0.2
        
        return min(score, 1.0)
    
    def _select_best_parser(self, doc_info: DocumentInfo) -> str:
        """选择最佳解析器"""
        file_type = doc_info.file_type
        
        # 获取该文件类型的解析器优先级
        priority_list = self.parser_priority.get(file_type, ['unstructured'])
        
        # 根据文档复杂度调整优先级
        if doc_info.complexity_score > 0.7:
            # 复杂文档优先使用unstructured
            if 'unstructured' in priority_list:
                return 'unstructured'
        
        # 返回第一个可用的解析器
        for parser in priority_list:
            if parser in self.parsers:
                return parser
        
        return 'unstructured'  # 默认解析器
    
    def _execute_parser(self, parser_name: str, file_path: str, doc_info: DocumentInfo) -> ParseResult:
        """执行解析器"""
        start_time = time.time()
        
        try:
            parser_func = self.parsers[parser_name]
            content, metadata, elements = parser_func(file_path)
            
            processing_time = time.time() - start_time
            
            return ParseResult(
                content=content,
                metadata=metadata,
                elements=elements,
                parser_used=parser_name,
                confidence=0.8,  # 基础置信度
                processing_time=processing_time,
                quality_score=0.0  # 稍后计算
            )
            
        except Exception as e:
            logger.error(f"解析器 {parser_name} 执行失败: {str(e)}")
            raise
    
    def _parse_with_pymupdf(self, file_path: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
        """使用PyMuPDF解析"""
        try:
            doc = fitz.open(file_path)
            content_parts = []
            metadata = {
                'page_count': len(doc),
                'title': doc.metadata.get('title', ''),
                'author': doc.metadata.get('author', ''),
                'subject': doc.metadata.get('subject', ''),
                'creator': doc.metadata.get('creator', '')
            }
            elements = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                content_parts.append(f"=== 第 {page_num + 1} 页 ===\n{text}")
                
                # 提取页面元素
                page_elements = {
                    'page': page_num + 1,
                    'text': text,
                    'images': len(page.get_images()),
                    'links': len(page.get_links())
                }
                elements.append(page_elements)
            
            doc.close()
            
            content = '\n\n'.join(content_parts)
            return content, metadata, elements
            
        except Exception as e:
            logger.error(f"PyMuPDF解析失败: {str(e)}")
            raise
    
    def _parse_with_pdfplumber(self, file_path: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
        """使用pdfplumber解析"""
        try:
            content_parts = []
            metadata = {}
            elements = []
            
            with pdfplumber.open(file_path) as pdf:
                metadata['page_count'] = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    content_parts.append(f"=== 第 {page_num + 1} 页 ===\n{text}")
                    
                    # 提取表格
                    tables = page.extract_tables()
                    if tables:
                        for i, table in enumerate(tables):
                            table_text = self._table_to_text(table)
                            content_parts.append(f"\n--- 表格 {i+1} ---\n{table_text}")
                    
                    # 页面元素
                    page_elements = {
                        'page': page_num + 1,
                        'text': text,
                        'tables': len(tables) if tables else 0,
                        'width': page.width,
                        'height': page.height
                    }
                    elements.append(page_elements)
            
            content = '\n\n'.join(content_parts)
            return content, metadata, elements
            
        except Exception as e:
            logger.error(f"pdfplumber解析失败: {str(e)}")
            raise
    
    def _parse_with_unstructured(self, file_path: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
        """使用unstructured解析"""
        try:
            file_type = Path(file_path).suffix.lower()
            
            if file_type == '.pdf':
                elements = partition_pdf(
                    file_path,
                    strategy="hi_res",
                    infer_table_structure=True,
                    extract_images_in_pdf=True,
                    languages=["chi_sim", "eng"]
                )
            elif file_type == '.docx':
                elements = partition_docx(file_path)
            elif file_type == '.xlsx':
                elements = partition_xlsx(file_path)
            elif file_type == '.pptx':
                elements = partition_pptx(file_path)
            else:
                # 默认文本处理
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return content, {}, []
            
            # 处理元素
            content_parts = []
            metadata = {
                'element_count': len(elements),
                'parser': 'unstructured'
            }
            element_list = []
            
            for element in elements:
                if hasattr(element, 'text') and element.text:
                    content_parts.append(element.text)
                
                element_info = {
                    'type': element.category,
                    'text': getattr(element, 'text', ''),
                    'metadata': getattr(element, 'metadata', {})
                }
                element_list.append(element_info)
            
            content = '\n\n'.join(content_parts)
            return content, metadata, element_list
            
        except Exception as e:
            logger.error(f"unstructured解析失败: {str(e)}")
            raise
    
    def _table_to_text(self, table: List[List[str]]) -> str:
        """将表格转换为文本"""
        if not table:
            return ""
        
        text_lines = []
        for row in table:
            line = " | ".join(str(cell) if cell else "" for cell in row)
            text_lines.append(line)
        
        return "\n".join(text_lines)
    
    def _post_process_result(self, result: ParseResult, doc_info: DocumentInfo) -> ParseResult:
        """后处理解析结果"""
        # 计算质量分数
        result.quality_score = self._calculate_quality_score(result, doc_info)
        
        # 调整置信度
        result.confidence = self._adjust_confidence(result, doc_info)
        
        # 清理内容
        result.content = self._clean_content(result.content)
        
        return result
    
    def _calculate_quality_score(self, result: ParseResult, doc_info: DocumentInfo) -> float:
        """计算质量分数"""
        score = 0.0
        
        # 基于内容长度
        if len(result.content) > 1000:
            score += 0.3
        elif len(result.content) > 100:
            score += 0.2
        else:
            score += 0.1
        
        # 基于元素数量
        if len(result.elements) > 10:
            score += 0.2
        elif len(result.elements) > 5:
            score += 0.1
        
        # 基于解析器性能
        if result.parser_used == 'unstructured':
            score += 0.3
        elif result.parser_used == 'pdfplumber':
            score += 0.2
        else:
            score += 0.1
        
        # 基于处理时间
        if result.processing_time < 5.0:
            score += 0.2
        elif result.processing_time < 10.0:
            score += 0.1
        
        return min(score, 1.0)
    
    def _adjust_confidence(self, result: ParseResult, doc_info: DocumentInfo) -> float:
        """调整置信度"""
        confidence = result.confidence
        
        # 基于质量分数调整
        confidence += result.quality_score * 0.2
        
        # 基于文档复杂度调整
        if doc_info.complexity_score > 0.7:
            confidence -= 0.1
        
        return max(0.0, min(confidence, 1.0))
    
    def _clean_content(self, content: str) -> str:
        """清理内容"""
        if not content:
            return ""
        
        # 移除多余的空白字符
        import re
        content = re.sub(r'\n\s*\n', '\n\n', content)
        content = re.sub(r'[ \t]+', ' ', content)
        
        return content.strip()
    
    def _fallback_parse(self, file_path: str) -> ParseResult:
        """备用解析"""
        try:
            # 尝试简单的文本读取
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return ParseResult(
                content=content,
                metadata={'fallback': True},
                elements=[],
                parser_used='fallback',
                confidence=0.3,
                processing_time=0.1,
                quality_score=0.1
            )
            
        except Exception as e:
            logger.error(f"备用解析也失败: {str(e)}")
            return ParseResult(
                content="",
                metadata={'error': str(e)},
                elements=[],
                parser_used='error',
                confidence=0.0,
                processing_time=0.0,
                quality_score=0.0
            )


# 测试函数
def test_multi_parser():
    """测试多解析器策略"""
    parser = MultiParserStrategy()
    
    # 测试文件
    test_file = "/root/consult/大数据作业2.docx"
    
    if os.path.exists(test_file):
        result = parser.parse_document(test_file)
        
        print(f"解析结果:")
        print(f"  解析器: {result.parser_used}")
        print(f"  置信度: {result.confidence:.2f}")
        print(f"  质量分数: {result.quality_score:.2f}")
        print(f"  处理时间: {result.processing_time:.2f}s")
        print(f"  内容长度: {len(result.content)}")
        print(f"  元素数量: {len(result.elements)}")
        print(f"  内容预览: {result.content[:200]}...")
    else:
        print("测试文件不存在")


if __name__ == "__main__":
    test_multi_parser()
