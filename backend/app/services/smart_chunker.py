"""
智能文档分块服务
支持语义分块、动态chunk大小和内容类型感知分块
"""

import os
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from enum import Enum

# LangChain imports
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

logger = logging.getLogger(__name__)


class ChunkType(Enum):
    """文档块类型"""
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    TITLE = "title"
    LIST = "list"
    CODE = "code"
    MIXED = "mixed"


class SmartChunker:
    """智能文档分块器"""
    
    def __init__(self):
        # 初始化不同内容类型的分割器
        self.splitters = self._initialize_splitters()
        
        # 中文标点符号
        self.chinese_punctuation = r'[。！？；：，、]'
        
        # 代码标识符
        self.code_patterns = [
            r'def\s+\w+',  # Python函数
            r'class\s+\w+',  # Python类
            r'function\s+\w+',  # JavaScript函数
            r'public\s+\w+',  # Java方法
            r'private\s+\w+',  # Java方法
            r'#include',  # C/C++
            r'import\s+',  # 各种import
        ]
        
        # 表格标识符
        self.table_patterns = [
            r'\|.*\|',  # Markdown表格
            r'\s+\|\s+',  # 简单表格
            r'^\s*\w+\s+\w+\s+\w+',  # 空格分隔的表格
        ]
    
    def _initialize_splitters(self) -> Dict[str, RecursiveCharacterTextSplitter]:
        """初始化不同内容类型的分割器"""
        return {
            'default': RecursiveCharacterTextSplitter(
                chunk_size=500,  # 普通文本
                chunk_overlap=100,
                length_function=len,
                separators=["\n\n", "\n", "。", "！", "？", "；", "：", " ", ""]
            ),
            'table': RecursiveCharacterTextSplitter(
                chunk_size=2000,  # 表格保持较大chunk
                chunk_overlap=200,
                length_function=len,
                separators=["\n\n", "\n", ""]
            ),
            'code': RecursiveCharacterTextSplitter(
                chunk_size=800,  # 代码块
                chunk_overlap=150,
                length_function=len,
                separators=["\n\n", "\n", "def ", "class ", "function ", " ", ""]
            ),
            'title': RecursiveCharacterTextSplitter(
                chunk_size=300,  # 标题和短文本
                chunk_overlap=50,
                length_function=len,
                separators=["\n\n", "\n", ""]
            ),
            'list': RecursiveCharacterTextSplitter(
                chunk_size=600,  # 列表内容
                chunk_overlap=100,
                length_function=len,
                separators=["\n\n", "\n", "•", "1.", "2.", "3.", " ", ""]
            )
        }
    
    def _detect_content_type(self, content: str, metadata: Dict[str, Any]) -> ChunkType:
        """检测内容类型"""
        # 检查元数据中的类型信息
        chunk_type = metadata.get('chunk_type')
        if chunk_type:
            try:
                return ChunkType(chunk_type)
            except ValueError:
                pass
        
        # 检查是否有表格
        if metadata.get('has_table', False):
            return ChunkType.TABLE
        
        # 检查是否有图片
        if metadata.get('has_image', False):
            return ChunkType.IMAGE
        
        # 检查代码模式
        for pattern in self.code_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return ChunkType.CODE
        
        # 检查表格模式
        for pattern in self.table_patterns:
            if re.search(pattern, content, re.MULTILINE):
                return ChunkType.TABLE
        
        # 检查标题模式
        if self._is_title(content):
            return ChunkType.TITLE
        
        # 检查列表模式
        if self._is_list(content):
            return ChunkType.LIST
        
        return ChunkType.TEXT
    
    def _is_title(self, content: str) -> bool:
        """判断是否为标题"""
        lines = content.strip().split('\n')
        if len(lines) == 1:
            line = lines[0].strip()
            # 短文本且包含标题特征
            if len(line) < 100 and (
                line.startswith('#') or  # Markdown标题
                line.isupper() or  # 全大写
                re.match(r'^第[一二三四五六七八九十\d]+[章节条]', line) or  # 中文章节
                re.match(r'^\d+\.?\s+', line)  # 数字标题
            ):
                return True
        return False
    
    def _is_list(self, content: str) -> bool:
        """判断是否为列表"""
        lines = content.strip().split('\n')
        list_count = 0
        
        for line in lines:
            line = line.strip()
            if (
                re.match(r'^[•·▪▫]\s+', line) or  # 项目符号
                re.match(r'^\d+\.?\s+', line) or  # 数字列表
                re.match(r'^[a-zA-Z]\.?\s+', line) or  # 字母列表
                re.match(r'^[-*+]\s+', line)  # 其他符号
            ):
                list_count += 1
        
        # 如果超过一半的行是列表项，认为是列表
        return list_count > len(lines) * 0.5
    
    def _should_split(self, content: str, chunk_type: ChunkType) -> bool:
        """判断是否需要分割"""
        # 表格和图片通常不分割
        if chunk_type in [ChunkType.TABLE, ChunkType.IMAGE]:
            return False
        
        # 标题通常不分割
        if chunk_type == ChunkType.TITLE:
            return len(content) > 300
        
        # 代码块根据长度决定
        if chunk_type == ChunkType.CODE:
            return len(content) > 800
        
        # 普通文本根据长度决定
        return len(content) > 500
    
    def _split_content(self, content: str, chunk_type: ChunkType) -> List[str]:
        """根据内容类型分割内容"""
        splitter = self.splitters.get(chunk_type.value, self.splitters['default'])
        
        # 创建临时文档进行分割
        temp_doc = Document(page_content=content)
        chunks = splitter.split_documents([temp_doc])
        
        return [chunk.page_content for chunk in chunks]
    
    def _merge_small_chunks(self, chunks: List[Dict[str, Any]], min_size: int = 100) -> List[Dict[str, Any]]:
        """合并过小的chunk"""
        if not chunks:
            return chunks
        
        merged_chunks = []
        current_chunk = None
        
        for chunk in chunks:
            if len(chunk['content']) < min_size and current_chunk:
                # 合并到前一个chunk
                current_chunk['content'] += '\n\n' + chunk['content']
                current_chunk['metadata']['merged_chunks'] = current_chunk['metadata'].get('merged_chunks', 1) + 1
            else:
                # 保存前一个chunk
                if current_chunk:
                    merged_chunks.append(current_chunk)
                # 开始新的chunk
                current_chunk = chunk.copy()
        
        # 保存最后一个chunk
        if current_chunk:
            merged_chunks.append(current_chunk)
        
        return merged_chunks
    
    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """智能分块文档"""
        chunked_documents = []
        
        for doc in documents:
            content = doc.page_content
            metadata = doc.metadata.copy()
            
            # 检测内容类型
            chunk_type = self._detect_content_type(content, metadata)
            
            # 判断是否需要分割
            if not self._should_split(content, chunk_type):
                # 不分割，直接添加
                doc.metadata.update({
                    'chunk_type': chunk_type.value,
                    'chunk_index': 0,
                    'total_chunks': 1,
                    'splitter_used': 'none'
                })
                chunked_documents.append(doc)
            else:
                # 分割内容
                content_chunks = self._split_content(content, chunk_type)
                
                # 为每个chunk创建Document
                for i, chunk_content in enumerate(content_chunks):
                    chunk_doc = Document(
                        page_content=chunk_content,
                        metadata={
                            **metadata,
                            'chunk_type': chunk_type.value,
                            'chunk_index': i,
                            'total_chunks': len(content_chunks),
                            'splitter_used': chunk_type.value,
                            'original_length': len(content)
                        }
                    )
                    chunked_documents.append(chunk_doc)
        
        # 合并过小的chunk
        chunk_data = [
            {
                'content': doc.page_content,
                'metadata': doc.metadata
            }
            for doc in chunked_documents
        ]
        
        merged_data = self._merge_small_chunks(chunk_data)
        
        # 转换回Document格式
        final_documents = []
        for chunk_data in merged_data:
            doc = Document(
                page_content=chunk_data['content'],
                metadata=chunk_data['metadata']
            )
            final_documents.append(doc)
        
        logger.info(f"智能分块完成: {len(documents)} -> {len(final_documents)} 个片段")
        return final_documents
    
    def get_chunk_stats(self, documents: List[Document]) -> Dict[str, Any]:
        """获取分块统计信息"""
        if not documents:
            return {}
        
        chunk_types = {}
        chunk_sizes = []
        splitter_usage = {}
        
        for doc in documents:
            metadata = doc.metadata
            chunk_type = metadata.get('chunk_type', 'unknown')
            splitter = metadata.get('splitter_used', 'unknown')
            
            chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
            splitter_usage[splitter] = splitter_usage.get(splitter, 0) + 1
            chunk_sizes.append(len(doc.page_content))
        
        return {
            'total_chunks': len(documents),
            'chunk_types': chunk_types,
            'splitter_usage': splitter_usage,
            'avg_chunk_size': sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0,
            'min_chunk_size': min(chunk_sizes) if chunk_sizes else 0,
            'max_chunk_size': max(chunk_sizes) if chunk_sizes else 0
        }
