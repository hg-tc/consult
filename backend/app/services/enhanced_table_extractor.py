"""
增强表格提取服务
使用pdfplumber + 语义理解来提取和解析表格内容
"""

import os
import logging
import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import re
import json
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TableInfo:
    """表格信息"""
    page_num: int
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    rows: int
    cols: int
    content: str
    structured_data: Optional[List[List[str]]] = None
    table_type: str = "unknown"  # financial, data, comparison, etc.
    confidence: float = 0.0


class EnhancedTableExtractor:
    """增强表格提取器"""
    
    def __init__(self):
        self.table_patterns = {
            'financial': [
                r'金额|金额|收入|支出|利润|成本|费用|资产|负债',
                r'元|万元|亿元|美元|人民币',
                r'预算|决算|财务|会计'
            ],
            'data': [
                r'数据|统计|指标|数值|数量|比例|百分比',
                r'排名|序号|编号|ID|代码'
            ],
            'comparison': [
                r'对比|比较|差异|变化|增长|下降',
                r'vs|对比|比较|差异'
            ],
            'schedule': [
                r'时间|日期|计划|安排|进度|阶段',
                r'年|月|日|周|季度'
            ]
        }
    
    def extract_tables_from_pdf(self, pdf_path: str) -> List[TableInfo]:
        """从PDF中提取表格"""
        tables = []
        
        try:
            # 使用pdfplumber提取表格
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_tables = self._extract_tables_from_page(page, page_num)
                    tables.extend(page_tables)
            
            # 使用PyMuPDF作为备用方案
            if not tables:
                tables = self._extract_tables_with_pymupdf(pdf_path)
            
            # 后处理和语义分析
            tables = self._enhance_table_analysis(tables)
            
            logger.info(f"从 {pdf_path} 提取到 {len(tables)} 个表格")
            return tables
            
        except Exception as e:
            logger.error(f"表格提取失败: {str(e)}")
            return []
    
    def _extract_tables_from_page(self, page, page_num: int) -> List[TableInfo]:
        """从单页提取表格"""
        tables = []
        
        try:
            # 提取表格
            page_tables = page.extract_tables()
            
            for i, table in enumerate(page_tables):
                if not table or len(table) < 2:
                    continue
                
                # 清理表格数据
                cleaned_table = self._clean_table_data(table)
                if not cleaned_table:
                    continue
                
                # 获取表格边界框
                bbox = self._get_table_bbox(page, i)
                
                # 创建表格信息
                table_info = TableInfo(
                    page_num=page_num,
                    bbox=bbox,
                    rows=len(cleaned_table),
                    cols=len(cleaned_table[0]) if cleaned_table else 0,
                    content=self._table_to_text(cleaned_table),
                    structured_data=cleaned_table
                )
                
                tables.append(table_info)
                
        except Exception as e:
            logger.error(f"页面 {page_num} 表格提取失败: {str(e)}")
        
        return tables
    
    def _extract_tables_with_pymupdf(self, pdf_path: str) -> List[TableInfo]:
        """使用PyMuPDF提取表格（备用方案）"""
        tables = []
        
        try:
            doc = fitz.open(pdf_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # 查找表格
                tables_found = page.find_tables()
                
                for table_idx, table in enumerate(tables_found):
                    try:
                        # 提取表格数据
                        table_data = table.extract()
                        
                        if not table_data or len(table_data) < 2:
                            continue
                        
                        # 清理数据
                        cleaned_table = self._clean_table_data(table_data)
                        if not cleaned_table:
                            continue
                        
                        # 获取边界框
                        bbox = table.bbox
                        
                        table_info = TableInfo(
                            page_num=page_num,
                            bbox=bbox,
                            rows=len(cleaned_table),
                            cols=len(cleaned_table[0]) if cleaned_table else 0,
                            content=self._table_to_text(cleaned_table),
                            structured_data=cleaned_table
                        )
                        
                        tables.append(table_info)
                        
                    except Exception as e:
                        logger.error(f"PyMuPDF表格提取失败: {str(e)}")
            
            doc.close()
            
        except Exception as e:
            logger.error(f"PyMuPDF表格提取失败: {str(e)}")
        
        return tables
    
    def _clean_table_data(self, table_data: List[List[str]]) -> List[List[str]]:
        """清理表格数据"""
        cleaned = []
        
        for row in table_data:
            if not row:
                continue
            
            # 清理每个单元格
            cleaned_row = []
            for cell in row:
                if cell is None:
                    cleaned_row.append("")
                else:
                    # 清理文本
                    cell_text = str(cell).strip()
                    # 移除多余的空白字符
                    cell_text = re.sub(r'\s+', ' ', cell_text)
                    cleaned_row.append(cell_text)
            
            # 过滤空行
            if any(cell.strip() for cell in cleaned_row):
                cleaned.append(cleaned_row)
        
        return cleaned
    
    def _get_table_bbox(self, page, table_idx: int) -> Tuple[float, float, float, float]:
        """获取表格边界框"""
        try:
            # 尝试从pdfplumber获取表格边界框
            tables = page.find_tables()
            if table_idx < len(tables):
                return tables[table_idx].bbox
        except:
            pass
        
        # 默认返回页面边界
        return (0, 0, page.width, page.height)
    
    def _table_to_text(self, table_data: List[List[str]]) -> str:
        """将表格转换为文本"""
        if not table_data:
            return ""
        
        text_lines = []
        for row in table_data:
            # 用制表符分隔单元格
            line = "\t".join(str(cell) for cell in row)
            text_lines.append(line)
        
        return "\n".join(text_lines)
    
    def _enhance_table_analysis(self, tables: List[TableInfo]) -> List[TableInfo]:
        """增强表格分析"""
        for table in tables:
            # 分析表格类型
            table.table_type = self._classify_table_type(table.content)
            
            # 计算置信度
            table.confidence = self._calculate_table_confidence(table)
            
            # 增强结构化数据
            table.structured_data = self._enhance_structured_data(table.structured_data)
        
        return tables
    
    def _classify_table_type(self, content: str) -> str:
        """分类表格类型"""
        content_lower = content.lower()
        
        for table_type, patterns in self.table_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content_lower):
                    return table_type
        
        return "unknown"
    
    def _calculate_table_confidence(self, table: TableInfo) -> float:
        """计算表格置信度"""
        confidence = 0.0
        
        # 基于行列数
        if table.rows >= 2 and table.cols >= 2:
            confidence += 0.3
        
        # 基于内容完整性
        if table.content and len(table.content.strip()) > 10:
            confidence += 0.3
        
        # 基于表格类型识别
        if table.table_type != "unknown":
            confidence += 0.2
        
        # 基于结构化数据质量
        if table.structured_data and len(table.structured_data) >= 2:
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    def _enhance_structured_data(self, data: List[List[str]]) -> List[List[str]]:
        """增强结构化数据"""
        if not data:
            return data
        
        enhanced = []
        
        for row in data:
            enhanced_row = []
            for cell in row:
                # 清理和标准化单元格内容
                cell_text = str(cell).strip()
                
                # 处理数字
                if self._is_numeric(cell_text):
                    cell_text = self._normalize_number(cell_text)
                
                # 处理日期
                elif self._is_date(cell_text):
                    cell_text = self._normalize_date(cell_text)
                
                enhanced_row.append(cell_text)
            
            enhanced.append(enhanced_row)
        
        return enhanced
    
    def _is_numeric(self, text: str) -> bool:
        """判断是否为数字"""
        try:
            # 移除常见的数字格式符号
            cleaned = re.sub(r'[,\s%￥$]', '', text)
            float(cleaned)
            return True
        except:
            return False
    
    def _is_date(self, text: str) -> bool:
        """判断是否为日期"""
        date_patterns = [
            r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',
            r'\d{4}年\d{1,2}月\d{1,2}日',
            r'\d{1,2}[-/]\d{1,2}[-/]\d{4}'
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, text):
                return True
        
        return False
    
    def _normalize_number(self, text: str) -> str:
        """标准化数字格式"""
        # 移除千分位分隔符
        cleaned = re.sub(r',', '', text)
        
        # 处理中文数字单位
        unit_map = {
            '万': '0000',
            '亿': '00000000',
            '千': '000'
        }
        
        for unit, multiplier in unit_map.items():
            if unit in cleaned:
                cleaned = cleaned.replace(unit, multiplier)
        
        return cleaned
    
    def _normalize_date(self, text: str) -> str:
        """标准化日期格式"""
        # 统一日期格式为 YYYY-MM-DD
        date_patterns = [
            (r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', r'\1-\2-\3'),
            (r'(\d{4})年(\d{1,2})月(\d{1,2})日', r'\1-\2-\3'),
            (r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', r'\3-\1-\2')
        ]
        
        for pattern, replacement in date_patterns:
            text = re.sub(pattern, replacement, text)
        
        return text
    
    def export_tables_to_json(self, tables: List[TableInfo], output_path: str):
        """导出表格为JSON格式"""
        try:
            export_data = []
            
            for table in tables:
                table_data = {
                    'page_num': table.page_num,
                    'bbox': table.bbox,
                    'rows': table.rows,
                    'cols': table.cols,
                    'content': table.content,
                    'structured_data': table.structured_data,
                    'table_type': table.table_type,
                    'confidence': table.confidence
                }
                export_data.append(table_data)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"表格数据已导出到: {output_path}")
            
        except Exception as e:
            logger.error(f"表格导出失败: {str(e)}")
    
    def export_tables_to_excel(self, tables: List[TableInfo], output_path: str):
        """导出表格为Excel格式"""
        try:
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                for i, table in enumerate(tables):
                    if table.structured_data:
                        # 创建DataFrame
                        df = pd.DataFrame(table.structured_data)
                        
                        # 使用第一行作为列名（如果合适）
                        if len(df) > 1:
                            df.columns = df.iloc[0]
                            df = df.drop(0)
                        
                        # 写入Excel
                        sheet_name = f"Table_{i+1}_Page_{table.page_num}"
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            logger.info(f"表格数据已导出到: {output_path}")
            
        except Exception as e:
            logger.error(f"Excel导出失败: {str(e)}")


# 测试函数
def test_table_extraction():
    """测试表格提取功能"""
    extractor = EnhancedTableExtractor()
    
    # 测试PDF文件
    test_pdf = "/root/consult/大数据作业2.docx"  # 使用现有文件
    
    if os.path.exists(test_pdf):
        tables = extractor.extract_tables_from_pdf(test_pdf)
        
        print(f"提取到 {len(tables)} 个表格:")
        for i, table in enumerate(tables):
            print(f"表格 {i+1}:")
            print(f"  页面: {table.page_num}")
            print(f"  类型: {table.table_type}")
            print(f"  置信度: {table.confidence:.2f}")
            print(f"  内容预览: {table.content[:100]}...")
            print()
    else:
        print("测试文件不存在")


if __name__ == "__main__":
    test_table_extraction()
