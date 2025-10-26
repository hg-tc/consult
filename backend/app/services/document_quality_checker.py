"""
文档质量检查器
检查文档处理的完整性和准确性
"""

import logging
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from .enhanced_document_processor import ProcessedDocument, DocumentChunk, ChunkType

logger = logging.getLogger(__name__)


class QualityLevel(Enum):
    """质量等级"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


@dataclass
class QualityIssue:
    """质量问题"""
    issue_type: str
    severity: str  # critical, warning, info
    description: str
    suggestion: str
    affected_chunks: List[int] = None


@dataclass
class QualityReport:
    """质量报告"""
    overall_score: float
    quality_level: QualityLevel
    issues: List[QualityIssue]
    recommendations: List[str]
    detailed_metrics: Dict[str, Any]


class DocumentQualityChecker:
    """文档质量检查器"""
    
    def __init__(self):
        self.min_chunk_length = 10
        self.max_chunk_length = 2000
        self.min_quality_score = 0.5
    
    def check_document(self, processed_doc: ProcessedDocument) -> QualityReport:
        """
        检查文档质量
        
        Args:
            processed_doc: 处理后的文档
            
        Returns:
            QualityReport: 质量报告
        """
        issues = []
        metrics = {}
        
        # 1. 检查文本提取完整性
        text_issues, text_metrics = self._check_text_extraction(processed_doc)
        issues.extend(text_issues)
        metrics.update(text_metrics)
        
        # 2. 验证表格识别准确性
        table_issues, table_metrics = self._check_table_extraction(processed_doc)
        issues.extend(table_issues)
        metrics.update(table_metrics)
        
        # 3. 评估OCR质量
        ocr_issues, ocr_metrics = self._check_ocr_quality(processed_doc)
        issues.extend(ocr_issues)
        metrics.update(ocr_metrics)
        
        # 4. 检查分块合理性
        chunk_issues, chunk_metrics = self._check_chunking_quality(processed_doc)
        issues.extend(chunk_issues)
        metrics.update(chunk_metrics)
        
        # 5. 计算总体质量分数
        overall_score = self._calculate_overall_score(metrics, issues)
        quality_level = self._determine_quality_level(overall_score)
        
        # 6. 生成建议
        recommendations = self._generate_recommendations(issues, metrics)
        
        return QualityReport(
            overall_score=overall_score,
            quality_level=quality_level,
            issues=issues,
            recommendations=recommendations,
            detailed_metrics=metrics
        )
    
    def _check_text_extraction(self, processed_doc: ProcessedDocument) -> Tuple[List[QualityIssue], Dict[str, Any]]:
        """检查文本提取质量"""
        issues = []
        metrics = {}
        
        total_chunks = len(processed_doc.chunks)
        text_chunks = [chunk for chunk in processed_doc.chunks if chunk.chunk_type == ChunkType.TEXT]
        
        metrics['total_chunks'] = total_chunks
        metrics['text_chunks'] = len(text_chunks)
        
        if total_chunks == 0:
            issues.append(QualityIssue(
                issue_type="no_content",
                severity="critical",
                description="文档没有提取到任何内容",
                suggestion="检查文件是否损坏或格式是否支持"
            ))
            return issues, metrics
        
        # 检查空内容块
        empty_chunks = [i for i, chunk in enumerate(processed_doc.chunks) 
                       if not chunk.content.strip()]
        
        if empty_chunks:
            issues.append(QualityIssue(
                issue_type="empty_chunks",
                severity="warning",
                description=f"发现 {len(empty_chunks)} 个空内容块",
                suggestion="检查文档内容或调整提取参数",
                affected_chunks=empty_chunks
            ))
        
        # 检查内容长度
        short_chunks = [i for i, chunk in enumerate(processed_doc.chunks)
                       if len(chunk.content.strip()) < self.min_chunk_length]
        
        if short_chunks:
            issues.append(QualityIssue(
                issue_type="short_chunks",
                severity="info",
                description=f"发现 {len(short_chunks)} 个过短的内容块",
                suggestion="考虑合并短块或调整分块策略",
                affected_chunks=short_chunks
            ))
        
        # 计算文本覆盖率
        total_text_length = sum(len(chunk.content) for chunk in text_chunks)
        metrics['total_text_length'] = total_text_length
        metrics['avg_chunk_length'] = total_text_length / len(text_chunks) if text_chunks else 0
        
        return issues, metrics
    
    def _check_table_extraction(self, processed_doc: ProcessedDocument) -> Tuple[List[QualityIssue], Dict[str, Any]]:
        """检查表格提取质量"""
        issues = []
        metrics = {}
        
        table_chunks = [chunk for chunk in processed_doc.chunks if chunk.has_table]
        metrics['table_chunks'] = len(table_chunks)
        
        if table_chunks:
            # 检查表格内容质量
            for i, chunk in enumerate(table_chunks):
                if '[表格数据]' not in chunk.content:
                    issues.append(QualityIssue(
                        issue_type="table_format",
                        severity="warning",
                        description=f"表格块 {i} 格式不正确",
                        suggestion="检查表格提取逻辑",
                        affected_chunks=[i]
                    ))
                
                # 检查表格内容长度
                if len(chunk.content) < 20:
                    issues.append(QualityIssue(
                        issue_type="table_content",
                        severity="warning",
                        description=f"表格块 {i} 内容过少",
                        suggestion="检查表格识别准确性",
                        affected_chunks=[i]
                    ))
        
        return issues, metrics
    
    def _check_ocr_quality(self, processed_doc: ProcessedDocument) -> Tuple[List[QualityIssue], Dict[str, Any]]:
        """检查OCR质量"""
        issues = []
        metrics = {}
        
        # 检查是否有OCR处理的痕迹
        ocr_indicators = ['[图片内容]', 'OCR', '扫描']
        ocr_chunks = []
        
        for i, chunk in enumerate(processed_doc.chunks):
            if any(indicator in chunk.content for indicator in ocr_indicators):
                ocr_chunks.append(i)
        
        metrics['ocr_chunks'] = len(ocr_chunks)
        
        if ocr_chunks:
            # 检查OCR内容质量
            for i in ocr_chunks:
                chunk = processed_doc.chunks[i]
                
                # 检查OCR文字的可读性
                if self._is_poor_ocr_quality(chunk.content):
                    issues.append(QualityIssue(
                        issue_type="ocr_quality",
                        severity="warning",
                        description=f"OCR块 {i} 质量较差",
                        suggestion="考虑重新OCR或手动校正",
                        affected_chunks=[i]
                    ))
        
        return issues, metrics
    
    def _check_chunking_quality(self, processed_doc: ProcessedDocument) -> Tuple[List[QualityIssue], Dict[str, Any]]:
        """检查分块质量"""
        issues = []
        metrics = {}
        
        chunks = processed_doc.chunks
        metrics['total_chunks'] = len(chunks)
        
        if not chunks:
            return issues, metrics
        
        # 检查分块大小分布
        chunk_lengths = [len(chunk.content) for chunk in chunks]
        metrics['min_chunk_length'] = min(chunk_lengths)
        metrics['max_chunk_length'] = max(chunk_lengths)
        metrics['avg_chunk_length'] = sum(chunk_lengths) / len(chunk_lengths)
        
        # 检查过长或过短的块
        oversized_chunks = [i for i, length in enumerate(chunk_lengths) 
                           if length > self.max_chunk_length]
        
        if oversized_chunks:
            issues.append(QualityIssue(
                issue_type="oversized_chunks",
                severity="warning",
                description=f"发现 {len(oversized_chunks)} 个过长的块",
                suggestion="考虑进一步分割长块",
                affected_chunks=oversized_chunks
            ))
        
        # 检查分块类型分布
        chunk_types = {}
        for chunk in chunks:
            chunk_type = chunk.chunk_type.value
            chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
        
        metrics['chunk_type_distribution'] = chunk_types
        
        # 检查是否有混合类型块
        mixed_chunks = [i for i, chunk in enumerate(chunks) 
                       if chunk.chunk_type == ChunkType.MIXED]
        
        if mixed_chunks:
            issues.append(QualityIssue(
                issue_type="mixed_chunks",
                severity="info",
                description=f"发现 {len(mixed_chunks)} 个混合类型块",
                suggestion="考虑优化分块策略",
                affected_chunks=mixed_chunks
            ))
        
        return issues, metrics
    
    def _is_poor_ocr_quality(self, content: str) -> bool:
        """判断OCR质量是否较差"""
        if not content:
            return True
        
        # 检查常见OCR错误模式
        poor_quality_indicators = [
            len(content) < 10,  # 内容过短
            content.count('?') > len(content) * 0.1,  # 问号过多
            content.count('*') > len(content) * 0.05,  # 星号过多
            len(set(content)) < 5,  # 字符种类过少
        ]
        
        return any(poor_quality_indicators)
    
    def _calculate_overall_score(self, metrics: Dict[str, Any], issues: List[QualityIssue]) -> float:
        """计算总体质量分数"""
        base_score = 1.0
        
        # 根据问题严重程度扣分
        for issue in issues:
            if issue.severity == "critical":
                base_score -= 0.3
            elif issue.severity == "warning":
                base_score -= 0.1
            elif issue.severity == "info":
                base_score -= 0.05
        
        # 根据指标调整分数
        if metrics.get('total_chunks', 0) == 0:
            base_score = 0.0
        elif metrics.get('avg_chunk_length', 0) < 20:
            base_score -= 0.1
        
        # 确保分数在0-1之间
        return max(0.0, min(1.0, base_score))
    
    def _determine_quality_level(self, score: float) -> QualityLevel:
        """确定质量等级"""
        if score >= 0.9:
            return QualityLevel.EXCELLENT
        elif score >= 0.7:
            return QualityLevel.GOOD
        elif score >= 0.5:
            return QualityLevel.FAIR
        else:
            return QualityLevel.POOR
    
    def _generate_recommendations(self, issues: List[QualityIssue], metrics: Dict[str, Any]) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        # 基于问题生成建议
        critical_issues = [issue for issue in issues if issue.severity == "critical"]
        if critical_issues:
            recommendations.append("存在严重问题，需要立即处理")
        
        warning_issues = [issue for issue in issues if issue.severity == "warning"]
        if warning_issues:
            recommendations.append("存在警告问题，建议优化处理参数")
        
        # 基于指标生成建议
        if metrics.get('avg_chunk_length', 0) < 50:
            recommendations.append("平均块长度较短，考虑调整分块策略")
        
        if metrics.get('table_chunks', 0) == 0 and metrics.get('ocr_chunks', 0) == 0:
            recommendations.append("未检测到表格或图片内容，检查文档类型")
        
        if metrics.get('total_text_length', 0) < 100:
            recommendations.append("提取的文本内容较少，检查文档是否为空或损坏")
        
        # 通用建议
        if not recommendations:
            recommendations.append("文档质量良好，无需特别优化")
        
        return recommendations
    
    def get_quality_summary(self, report: QualityReport) -> str:
        """获取质量摘要"""
        summary = f"文档质量报告\n"
        summary += f"总体分数: {report.overall_score:.2f}\n"
        summary += f"质量等级: {report.quality_level.value}\n"
        summary += f"问题数量: {len(report.issues)}\n"
        summary += f"建议数量: {len(report.recommendations)}\n"
        
        if report.issues:
            summary += "\n主要问题:\n"
            for issue in report.issues[:3]:  # 只显示前3个问题
                summary += f"- {issue.description}\n"
        
        if report.recommendations:
            summary += "\n建议:\n"
            for rec in report.recommendations[:3]:  # 只显示前3个建议
                summary += f"- {rec}\n"
        
        return summary
