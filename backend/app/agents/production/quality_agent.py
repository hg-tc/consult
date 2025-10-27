import logging
from typing import Dict, Any
from .base_agent import BaseProductionAgent
from app.models.agent_models import QualityMetrics

logger = logging.getLogger(__name__)

class QualityAssuranceAgent(BaseProductionAgent):
    """质量保证 Agent - 混合模式（规则+LLM）"""
    
    def __init__(self, llm, quality_chain, config: dict = None):
        super().__init__("QualityAssurance", llm, config or {})
        self.quality_chain = quality_chain
        self.quality_threshold = config.get("quality_threshold", 0.85) if config else 0.85
    
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        两阶段质量检查：
        1. 规则检查（快速）
        2. LLM 评分（精准）
        """
        logger.info("=== 进入质量评估节点 ===")
        
        content = state.get("draft_content", "")
        intent = state.get("intent")
        
        logger.info(f"从 state 中读取的 draft_content 长度: {len(content) if content else 0}")
        logger.info(f"draft_content 前50字符: {content[:50] if content else '空'}")
        logger.info(f"intent 存在: {intent is not None}")
        
        if not content:
            logger.warning("draft_content 为空，尝试从其他字段获取")
            # 尝试从其他字段获取内容
            content_outline = state.get("content_outline", {})
            if isinstance(content_outline, dict):
                structure = content_outline.get("structure", "")
                if structure:
                    logger.warning("使用 content_outline 作为内容")
                    content = structure
                else:
                    logger.error("无法找到任何内容")
            else:
                logger.error("content_outline 格式不正确")
        
        if not content or not intent:
            logger.warning("内容或意图不存在，返回默认质量分数")
            # 返回一个默认的质量指标，避免 None 错误
            return {
                "quality_metrics": QualityMetrics(
                    relevance_score=0.5,
                    completeness_score=0.5,
                    accuracy_score=0.5,
                    readability_score=0.5,
                    format_compliance_score=0.5,
                    overall_score=0.5,
                    improvement_suggestions=["内容或意图不存在"],
                    critical_issues=[],
                    meets_threshold=False,
                    requires_human_review=True
                )
            }
        
        # 阶段1: 规则检查
        logger.info(f"开始规则检查，内容长度: {len(content)}")
        rule_check = self._rule_based_check(content, intent)
        logger.info(f"规则检查结果: passed={rule_check['passed']}, issues={len(rule_check.get('issues', []))}")
        
        if not rule_check["passed"]:
            logger.info("规则检查未通过，返回改进建议")
            return {
                "quality_metrics": QualityMetrics(
                    relevance_score=0.5,
                    completeness_score=0.5,
                    accuracy_score=0.5,
                    readability_score=0.5,
                    format_compliance_score=0.5,
                    overall_score=0.5,
                    improvement_suggestions=rule_check.get("issues", []),
                    meets_threshold=False,
                    requires_human_review=False
                )
            }
        
        # 阶段2: LLM 评分
        try:
            # 处理意图数据
            key_topics = intent.get("key_topics", []) if isinstance(intent, dict) else intent.key_topics
            output_format = intent.get("output_format", "word") if isinstance(intent, dict) else intent.output_format
            quality_requirements = intent.get("quality_requirements", []) if isinstance(intent, dict) else intent.quality_requirements
            
            logger.info("开始 LLM 质量评分")
            quality_metrics = await self.quality_chain.ainvoke({
                "title": key_topics[0] if key_topics else "文档",
                "output_format": output_format,
                "requirements": quality_requirements,
                "content": content[:5000]  # 限制长度
            })
            
            # 判断是否需要人工审核
            quality_metrics.requires_human_review = (
                quality_metrics.overall_score < self.quality_threshold and
                state.get("iteration_count", 0) >= 3
            )
            
            logger.info(f"质量评估完成，总分: {quality_metrics.overall_score}")
            logger.info("=== 质量评估节点完成 ===")
            
            return {"quality_metrics": quality_metrics}
            
        except Exception as e:
            logger.error(f"LLM 质量评分失败: {e}")
            # 回退到规则检查结果
            return {
                "quality_metrics": QualityMetrics(
                    relevance_score=0.7,
                    completeness_score=0.7,
                    accuracy_score=0.7,
                    readability_score=0.7,
                    format_compliance_score=0.8,
                    overall_score=0.72,
                    improvement_suggestions=["质量评分暂时不可用"],
                    meets_threshold=False,
                    requires_human_review=False
                )
            }
    
    def _rule_based_check(self, content: str, intent) -> Dict[str, Any]:
        """基于规则的快速检查"""
        issues = []
        
        # 检查1: 内容长度
        min_length = 100
        if intent:
            # 兼容 dict 和对象
            estimated_output_size = intent.get("estimated_output_size", "中") if isinstance(intent, dict) else intent.estimated_output_size if hasattr(intent, 'estimated_output_size') else "中"
            
            if estimated_output_size:
                # 根据预估长度调整最小长度要求
                if "短" in estimated_output_size:
                    min_length = 100
                elif "中" in estimated_output_size:
                    min_length = 500
                else:
                    min_length = 1000
        
        if len(content) < min_length:
            issues.append(f"内容过短，当前 {len(content)} 字，建议至少 {min_length} 字")
        
        # 检查2: 关键词覆盖
        key_topics = intent.get("key_topics", []) if isinstance(intent, dict) else intent.key_topics if hasattr(intent, 'key_topics') else []
        if intent and key_topics:
            missing_topics = []
            content_lower = content.lower()
            
            for topic in key_topics:
                if topic.lower() not in content_lower:
                    missing_topics.append(topic)
            
            if missing_topics:
                issues.append(f"缺少关键主题: {', '.join(missing_topics[:3])}")
        
        # 检查3: 格式合规
        output_format = intent.get("output_format", "word") if isinstance(intent, dict) else intent.output_format if intent else "word"
        if intent and output_format == "word":
            if "##" not in content and "#" not in content:
                issues.append("缺少标题结构，建议使用 Markdown 标题格式")
        
        # 检查4: 基本结构
        if len(content.split('\n')) < 3:
            issues.append("内容结构过于简单，建议添加段落分隔")
        
        return {
            "passed": len(issues) == 0,
            "issues": issues
        }

