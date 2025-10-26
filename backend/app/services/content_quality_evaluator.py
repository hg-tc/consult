"""
内容质量评估器
评估文档内容的完整性、连贯性、信息密度等维度
"""

import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import json

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

class QualityDimension(Enum):
    """质量维度"""
    COMPLETENESS = "completeness"  # 完整性
    COHERENCE = "coherence"  # 连贯性
    INFORMATION_DENSITY = "information_density"  # 信息密度
    FORMAT_QUALITY = "format_quality"  # 格式质量
    LANGUAGE_QUALITY = "language_quality"  # 语言质量
    ACCURACY = "accuracy"  # 准确性
    RELEVANCE = "relevance"  # 相关性

@dataclass
class QualityScore:
    """质量评分"""
    dimension: QualityDimension
    score: float  # 0-1
    explanation: str
    suggestions: List[str]

@dataclass
class OverallQualityAssessment:
    """整体质量评估"""
    scores: Dict[QualityDimension, QualityScore]
    overall_score: float
    grade: str  # A, B, C, D, F
    summary: str
    improvement_priority: List[QualityDimension]
    needs_refinement: bool

class ContentQualityEvaluator:
    """内容质量评估器"""
    
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.quality_threshold = 0.7  # 质量阈值
        
        # 质量评估提示词模板
        self.evaluation_prompt = """请评估以下文档内容的质量：

文档内容：
{content}

任务要求：
{requirements}

请从以下维度进行详细评估（0-1分）：

1. **内容完整性** (completeness)
   - 是否覆盖了所有必要要点
   - 是否有遗漏的重要信息
   - 结构是否完整

2. **逻辑连贯性** (coherence)
   - 章节间逻辑关系是否清晰
   - 论述是否前后一致
   - 是否有逻辑跳跃

3. **信息密度** (information_density)
   - 信息是否充实
   - 是否有冗余内容
   - 是否有空洞表述

4. **格式规范性** (format_quality)
   - 标题层级是否清晰
   - 段落结构是否合理
   - 格式是否规范

5. **语言质量** (language_quality)
   - 表达是否专业
   - 用词是否准确
   - 语法是否正确

6. **内容准确性** (accuracy)
   - 信息是否准确
   - 数据是否可靠
   - 引用是否正确

7. **相关性** (relevance)
   - 内容是否切题
   - 是否满足用户需求
   - 是否有偏离主题

请返回JSON格式的评估结果：
{{
    "scores": {{
        "completeness": {{
            "score": 0.8,
            "explanation": "内容基本完整，但缺少...",
            "suggestions": ["建议1", "建议2"]
        }},
        "coherence": {{
            "score": 0.7,
            "explanation": "逻辑基本清晰，但...",
            "suggestions": ["建议1"]
        }},
        "information_density": {{
            "score": 0.6,
            "explanation": "信息密度一般，存在...",
            "suggestions": ["建议1", "建议2"]
        }},
        "format_quality": {{
            "score": 0.9,
            "explanation": "格式规范，结构清晰",
            "suggestions": []
        }},
        "language_quality": {{
            "score": 0.8,
            "explanation": "语言表达专业",
            "suggestions": ["建议1"]
        }},
        "accuracy": {{
            "score": 0.7,
            "explanation": "信息基本准确",
            "suggestions": ["建议1"]
        }},
        "relevance": {{
            "score": 0.8,
            "explanation": "内容切题",
            "suggestions": []
        }}
    }},
    "overall_score": 0.76,
    "grade": "B",
    "summary": "整体质量良好，但在信息密度和逻辑连贯性方面需要改进",
    "improvement_priority": ["information_density", "coherence"],
    "needs_refinement": true
}}"""
    
    async def evaluate_content(self, content: str, requirements: Dict[str, Any] = None) -> OverallQualityAssessment:
        """
        评估内容质量
        
        Args:
            content: 文档内容
            requirements: 任务要求
            
        Returns:
            质量评估结果
        """
        logger.info("开始内容质量评估")
        
        try:
            # 1. LLM评估
            llm_assessment = await self._llm_evaluate(content, requirements or {})
            
            # 2. 规则评估
            rule_assessment = self._rule_based_evaluate(content, requirements or {})
            
            # 3. 综合评估
            final_assessment = self._combine_assessments(llm_assessment, rule_assessment)
            
            logger.info(f"质量评估完成，总分: {final_assessment.overall_score:.2f}")
            return final_assessment
            
        except Exception as e:
            logger.error(f"内容质量评估失败: {e}")
            return self._get_default_assessment()
    
    async def _llm_evaluate(self, content: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """使用LLM进行评估"""
        try:
            requirements_text = json.dumps(requirements, ensure_ascii=False, indent=2)
            
            prompt = self.evaluation_prompt.format(
                content=content[:3000],  # 限制长度
                requirements=requirements_text
            )
            
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析JSON响应
            try:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            except Exception as e:
                logger.warning(f"LLM评估响应解析失败: {e}")
            
            # 返回默认评估
            return self._get_default_llm_assessment()
            
        except Exception as e:
            logger.error(f"LLM评估失败: {e}")
            return self._get_default_llm_assessment()
    
    def _rule_based_evaluate(self, content: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """基于规则的评估"""
        try:
            scores = {}
            
            # 1. 完整性评估
            completeness_score = self._evaluate_completeness(content, requirements)
            scores["completeness"] = completeness_score
            
            # 2. 格式质量评估
            format_score = self._evaluate_format_quality(content)
            scores["format_quality"] = format_score
            
            # 3. 信息密度评估
            density_score = self._evaluate_information_density(content)
            scores["information_density"] = density_score
            
            # 4. 语言质量评估
            language_score = self._evaluate_language_quality(content)
            scores["language_quality"] = language_score
            
            return scores
            
        except Exception as e:
            logger.error(f"规则评估失败: {e}")
            return {}
    
    def _evaluate_completeness(self, content: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """评估完整性"""
        try:
            # 检查基本结构
            has_title = bool(re.search(r'^#\s+.+', content, re.MULTILINE))
            has_sections = len(re.findall(r'^#+\s+.+', content, re.MULTILINE)) >= 2
            has_content = len(content.strip()) > 100
            
            # 检查关键词覆盖
            doc_type = requirements.get('doc_type', 'word')
            required_elements = self._get_required_elements(doc_type)
            
            coverage_score = 0
            for element in required_elements:
                if element.lower() in content.lower():
                    coverage_score += 1
            
            coverage_score = coverage_score / len(required_elements) if required_elements else 0
            
            # 综合评分
            structure_score = (has_title + has_sections + has_content) / 3
            final_score = (structure_score + coverage_score) / 2
            
            suggestions = []
            if not has_title:
                suggestions.append("添加文档标题")
            if not has_sections:
                suggestions.append("增加章节结构")
            if coverage_score < 0.5:
                suggestions.append("补充必要内容要点")
            
            return {
                "score": final_score,
                "explanation": f"结构完整性: {structure_score:.2f}, 内容覆盖度: {coverage_score:.2f}",
                "suggestions": suggestions
            }
            
        except Exception as e:
            logger.error(f"完整性评估失败: {e}")
            return {"score": 0.5, "explanation": "评估失败", "suggestions": []}
    
    def _evaluate_format_quality(self, content: str) -> Dict[str, Any]:
        """评估格式质量"""
        try:
            lines = content.split('\n')
            
            # 检查标题层级
            headings = [line for line in lines if re.match(r'^#+\s+', line)]
            heading_score = min(1.0, len(headings) / 3)  # 至少3个标题
            
            # 检查段落结构
            paragraphs = [line for line in lines if line.strip() and not re.match(r'^#+\s+', line)]
            paragraph_score = min(1.0, len(paragraphs) / 5)  # 至少5个段落
            
            # 检查格式一致性
            consistent_formatting = len(set(re.findall(r'^#+\s+', content, re.MULTILINE))) <= 2
            consistency_score = 1.0 if consistent_formatting else 0.5
            
            final_score = (heading_score + paragraph_score + consistency_score) / 3
            
            suggestions = []
            if heading_score < 0.7:
                suggestions.append("增加标题层级")
            if paragraph_score < 0.7:
                suggestions.append("增加段落内容")
            if not consistent_formatting:
                suggestions.append("统一格式风格")
            
            return {
                "score": final_score,
                "explanation": f"标题结构: {heading_score:.2f}, 段落结构: {paragraph_score:.2f}, 格式一致性: {consistency_score:.2f}",
                "suggestions": suggestions
            }
            
        except Exception as e:
            logger.error(f"格式质量评估失败: {e}")
            return {"score": 0.5, "explanation": "评估失败", "suggestions": []}
    
    def _evaluate_information_density(self, content: str) -> Dict[str, Any]:
        """评估信息密度"""
        try:
            # 计算基本信息指标
            word_count = len(content.split())
            char_count = len(content)
            
            # 检查具体信息（数字、日期、专有名词等）
            numbers = len(re.findall(r'\d+', content))
            dates = len(re.findall(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', content))
            proper_nouns = len(re.findall(r'[A-Z][a-z]+', content))
            
            # 检查列表和结构化内容
            lists = len(re.findall(r'^\s*[-*+]\s+', content, re.MULTILINE))
            tables = len(re.findall(r'\|.*\|', content))
            
            # 计算信息密度
            specific_info_score = min(1.0, (numbers + dates + proper_nouns) / max(word_count / 100, 1))
            structure_score = min(1.0, (lists + tables) / max(word_count / 200, 1))
            
            final_score = (specific_info_score + structure_score) / 2
            
            suggestions = []
            if specific_info_score < 0.3:
                suggestions.append("增加具体数据和事实")
            if structure_score < 0.3:
                suggestions.append("增加列表和结构化内容")
            if word_count < 500:
                suggestions.append("增加内容长度")
            
            return {
                "score": final_score,
                "explanation": f"具体信息密度: {specific_info_score:.2f}, 结构化程度: {structure_score:.2f}",
                "suggestions": suggestions
            }
            
        except Exception as e:
            logger.error(f"信息密度评估失败: {e}")
            return {"score": 0.5, "explanation": "评估失败", "suggestions": []}
    
    def _evaluate_language_quality(self, content: str) -> Dict[str, Any]:
        """评估语言质量"""
        try:
            # 检查句子长度分布
            sentences = re.split(r'[.!?]+', content)
            avg_sentence_length = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
            
            # 检查词汇多样性
            words = content.lower().split()
            unique_words = len(set(words))
            vocabulary_score = min(1.0, unique_words / max(len(words) * 0.3, 1))
            
            # 检查专业术语使用
            professional_terms = len(re.findall(r'\b(分析|评估|研究|报告|数据|结果|结论|建议)\b', content))
            terminology_score = min(1.0, professional_terms / max(len(words) / 50, 1))
            
            # 检查语言流畅性（简单指标）
            fluency_score = 1.0 if 10 <= avg_sentence_length <= 25 else 0.7
            
            final_score = (vocabulary_score + terminology_score + fluency_score) / 3
            
            suggestions = []
            if vocabulary_score < 0.5:
                suggestions.append("增加词汇多样性")
            if terminology_score < 0.3:
                suggestions.append("使用更多专业术语")
            if avg_sentence_length < 10 or avg_sentence_length > 30:
                suggestions.append("调整句子长度")
            
            return {
                "score": final_score,
                "explanation": f"词汇多样性: {vocabulary_score:.2f}, 专业术语: {terminology_score:.2f}, 流畅性: {fluency_score:.2f}",
                "suggestions": suggestions
            }
            
        except Exception as e:
            logger.error(f"语言质量评估失败: {e}")
            return {"score": 0.5, "explanation": "评估失败", "suggestions": []}
    
    def _get_required_elements(self, doc_type: str) -> List[str]:
        """获取文档类型必需元素"""
        elements_map = {
            "word": ["概述", "分析", "结论", "建议"],
            "pdf": ["摘要", "引言", "方法", "结果", "讨论", "结论"],
            "excel": ["数据", "分析", "图表", "总结"],
            "ppt": ["概述", "要点", "案例", "总结"]
        }
        return elements_map.get(doc_type.lower(), ["概述", "分析", "结论"])
    
    def _combine_assessments(self, llm_assessment: Dict[str, Any], rule_assessment: Dict[str, Any]) -> OverallQualityAssessment:
        """综合评估结果"""
        try:
            scores = {}
            
            # 合并LLM和规则评估结果
            for dimension in QualityDimension:
                dimension_name = dimension.value
                
                llm_score = llm_assessment.get("scores", {}).get(dimension_name, {})
                rule_score = rule_assessment.get(dimension_name, {})
                
                # 加权平均（LLM权重0.7，规则权重0.3）
                llm_score_val = llm_score.get("score", 0.5)
                rule_score_val = rule_score.get("score", 0.5)
                final_score = llm_score_val * 0.7 + rule_score_val * 0.3
                
                # 合并建议
                suggestions = list(set(
                    llm_score.get("suggestions", []) + 
                    rule_score.get("suggestions", [])
                ))
                
                scores[dimension] = QualityScore(
                    dimension=dimension,
                    score=final_score,
                    explanation=llm_score.get("explanation", rule_score.get("explanation", "")),
                    suggestions=suggestions
                )
            
            # 计算总分
            overall_score = sum(score.score for score in scores.values()) / len(scores)
            
            # 确定等级
            grade = self._calculate_grade(overall_score)
            
            # 确定改进优先级
            improvement_priority = sorted(
                scores.keys(),
                key=lambda d: scores[d].score
            )[:3]  # 取分数最低的3个维度
            
            # 是否需要改进
            needs_refinement = overall_score < self.quality_threshold
            
            return OverallQualityAssessment(
                scores=scores,
                overall_score=overall_score,
                grade=grade,
                summary=llm_assessment.get("summary", f"整体质量评分: {overall_score:.2f}"),
                improvement_priority=improvement_priority,
                needs_refinement=needs_refinement
            )
            
        except Exception as e:
            logger.error(f"综合评估失败: {e}")
            return self._get_default_assessment()
    
    def _calculate_grade(self, score: float) -> str:
        """计算等级"""
        if score >= 0.9:
            return "A"
        elif score >= 0.8:
            return "B"
        elif score >= 0.7:
            return "C"
        elif score >= 0.6:
            return "D"
        else:
            return "F"
    
    def _get_default_assessment(self) -> OverallQualityAssessment:
        """获取默认评估结果"""
        scores = {}
        for dimension in QualityDimension:
            scores[dimension] = QualityScore(
                dimension=dimension,
                score=0.5,
                explanation="评估失败，使用默认值",
                suggestions=["需要人工审核"]
            )
        
        return OverallQualityAssessment(
            scores=scores,
            overall_score=0.5,
            grade="C",
            summary="评估失败，需要人工审核",
            improvement_priority=list(QualityDimension)[:3],
            needs_refinement=True
        )
    
    def _get_default_llm_assessment(self) -> Dict[str, Any]:
        """获取默认LLM评估结果"""
        return {
            "scores": {
                dim.value: {
                    "score": 0.7,
                    "explanation": "LLM评估失败，使用默认值",
                    "suggestions": []
                } for dim in QualityDimension
            },
            "overall_score": 0.7,
            "grade": "C",
            "summary": "LLM评估失败",
            "improvement_priority": ["completeness", "coherence"],
            "needs_refinement": False
        }
    
    def get_evaluation_report(self, assessment: OverallQualityAssessment) -> str:
        """生成评估报告"""
        try:
            report = f"""
# 内容质量评估报告

## 总体评分
- **总分**: {assessment.overall_score:.2f}/1.0
- **等级**: {assessment.grade}
- **是否需要改进**: {'是' if assessment.needs_refinement else '否'}

## 详细评分

"""
            
            for dimension, score in assessment.scores.items():
                report += f"### {dimension.value.replace('_', ' ').title()}\n"
                report += f"- **分数**: {score.score:.2f}/1.0\n"
                report += f"- **说明**: {score.explanation}\n"
                if score.suggestions:
                    report += f"- **改进建议**: {', '.join(score.suggestions)}\n"
                report += "\n"
            
            if assessment.improvement_priority:
                report += f"## 改进优先级\n"
                for i, dimension in enumerate(assessment.improvement_priority, 1):
                    report += f"{i}. {dimension.value.replace('_', ' ').title()}\n"
            
            report += f"\n## 总结\n{assessment.summary}\n"
            
            return report
            
        except Exception as e:
            logger.error(f"生成评估报告失败: {e}")
            return f"评估报告生成失败: {str(e)}"
