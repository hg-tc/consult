import logging
from typing import Dict, Any, List
from .base_agent import BaseProductionAgent

logger = logging.getLogger(__name__)

class ContentPlanningAgent(BaseProductionAgent):
    """内容规划 Agent - 生成大纲和结构"""
    
    def __init__(self, llm):
        super().__init__("ContentPlanning", llm, {})
    
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """基于搜索结果和需求生成内容大纲"""
        intent = state.get("intent")
        synthesized_info = state.get("synthesized_info", "")
        user_request = state.get("user_request", "")
        
        if not intent:
            logger.warning("意图不存在，无法规划内容")
            return {"content_outline": None}
        
        # 处理意图数据 - 兼容字典和对象
        output_format = intent.get("output_format", "word") if isinstance(intent, dict) else intent.output_format
        key_topics = intent.get("key_topics", []) if isinstance(intent, dict) else intent.key_topics
        
        # 生成大纲
        outline_prompt = f"""作为专业的内容规划专家，请根据以下信息制定文档大纲：

用户需求：{user_request}
文档类型：{output_format}
关键主题：{', '.join(key_topics)}

收集到的信息：
{synthesized_info[:2000]}

请生成一个结构化的文档大纲，包含：
1. 文档标题
2. 主要章节（至少3个）
3. 每个章节的要点
4. 预估字数分配

格式要求：
- 使用 Markdown 格式
- 层次清晰
- 逻辑严密
- 符合{output_format}文档的特点
"""
        
        try:
            response = await self.llm.ainvoke(outline_prompt)
            outline = response.content if hasattr(response, 'content') else str(response)
            
            logger.info("内容大纲生成成功")
            
            # 处理复杂度
            complexity = intent.get("complexity", "medium") if isinstance(intent, dict) else intent.complexity
            
            return {
                "content_outline": {
                    "structure": outline,
                    "chapters": self._extract_chapters(outline),
                    "estimated_words": self._estimate_word_count(complexity)
                }
            }
        except Exception as e:
            logger.error(f"内容规划失败: {e}")
            # 返回简单大纲
            return {
                "content_outline": {
                    "structure": f"# {user_request}\n\n## 概述\n\n## 详细内容\n\n## 总结\n",
                    "chapters": ["概述", "详细内容", "总结"],
                    "estimated_words": 1000
                }
            }
    
    def _extract_chapters(self, outline: str) -> List[str]:
        """从大纲中提取章节标题"""
        chapters = []
        for line in outline.split('\n'):
            line = line.strip()
            if line.startswith('#') and not line.startswith('##'):
                continue  # 跳过主标题
            if line.startswith('##'):
                chapter = line.replace('##', '').strip()
                if chapter:
                    chapters.append(chapter)
        
        return chapters[:10]  # 最多10个章节
    
    def _estimate_word_count(self, complexity) -> int:
        """根据复杂度预估字数"""
        estimates = {
            "simple": 500,
            "medium": 1000,
            "complex": 2000,
            "very_complex": 3000
        }
        return estimates.get(complexity.value if hasattr(complexity, 'value') else complexity, 1000)

class ContentGenerationAgent(BaseProductionAgent):
    """内容生成 Agent - 根据大纲生成内容"""
    
    def __init__(self, llm):
        super().__init__("ContentGeneration", llm, {})
    
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """基于大纲和搜索结果生成文档内容"""
        intent = state.get("intent")
        content_outline = state.get("content_outline", {})
        synthesized_info = state.get("synthesized_info", "")
        
        if not content_outline:
            logger.warning("内容大纲不存在")
            return {"draft_content": ""}
        
        # 处理意图数据
        output_format = "word"
        if intent:
            output_format = intent.get("output_format", "word") if isinstance(intent, dict) else intent.output_format
        
        # 生成内容
        generation_prompt = f"""作为专业的内容写作专家，请根据以下大纲和信息生成高质量的文档内容。

文档类型：{output_format}

文档大纲：
{content_outline.get('structure', '')}

参考资料：
{synthesized_info[:3000] if synthesized_info else '无参考资料，请基于常识生成内容'}

写作要求：
1. 严格遵循大纲结构，完整填写每一个章节
2. 每个章节都必须有实质性的内容，不能只是标题或简单描述
3. 内容要具体、专业、有深度，提供实际的信息和说明
4. 逻辑清晰、论证严密、语言流畅
5. 绝对不能使用占位符，如"这里是内容"、"待补充"、"具体内容如下"等
6. 不能只重复大纲中的条目，而是要展开详细说明
7. 字数要求：不少于{content_outline.get('estimated_words', 1000)}字
8. 确保每个章节都有具体内容，不能是空白或大纲

重要提醒：
- 必须生成完整的、可读的文档内容
- 每个章节都要有实质性内容，不能只有标题
- 禁止任何形式的占位符

请立即生成完整的文档内容（Markdown 格式，不要包含代码块标记）：
"""
        
        try:
            # 添加详细日志
            logger.info(f"开始生成内容，大纲字数: {len(content_outline.get('structure', ''))}")
            logger.info(f"参考资料长度: {len(synthesized_info) if synthesized_info else 0}")
            
            response = await self.llm.ainvoke(generation_prompt)
            draft_content = response.content if hasattr(response, 'content') else str(response)
            
            # 清理可能存在的代码块标记
            if draft_content.startswith("```markdown"):
                draft_content = draft_content.replace("```markdown", "").replace("```", "").strip()
            elif draft_content.startswith("```"):
                draft_content = draft_content.replace("```", "").strip()
            
            # 验证内容质量
            word_count = len(draft_content.split())
            logger.info(f"内容生成成功，字符数: {len(draft_content)}, 单词数: {word_count}")
            
            # 如果内容太短，记录警告
            if len(draft_content) < 500:
                logger.warning(f"生成的内容过短: {len(draft_content)} 字符")
            
            return {
                "draft_content": draft_content,
                "word_count": word_count
            }
        except Exception as e:
            logger.error(f"内容生成失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"draft_content": ""}

class RefinementAgent(BaseProductionAgent):
    """内容改进 Agent - 基于反馈改进内容"""
    
    def __init__(self, llm):
        super().__init__("Refinement", llm, {})
    
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """基于质量评估结果改进内容"""
        draft_content = state.get("draft_content", "")
        quality_metrics = state.get("quality_metrics")
        intent = state.get("intent")
        
        if not quality_metrics or not quality_metrics.improvement_suggestions:
            logger.info("无改进建议，跳过改进")
            return {"refined_content": draft_content}
        
        # 改进内容
        refinement_prompt = f"""你是内容改进专家。请根据以下反馈改进文档内容：

当前内容：
{draft_content[:4000]}

改进建议：
{chr(10).join('- ' + s for s in quality_metrics.improvement_suggestions[:5])}

质量评分：
- 相关性：{quality_metrics.relevance_score:.2f}
- 完整性：{quality_metrics.completeness_score:.2f}
- 准确性：{quality_metrics.accuracy_score:.2f}
- 可读性：{quality_metrics.readability_score:.2f}

请重点改进以下方面：
1. 解决具体指出的问题
2. 提升整体质量分数
3. 保持原有结构和逻辑
4. 不要改变核心内容

改进后的内容：
"""
        
        try:
            response = await self.llm.ainvoke(refinement_prompt)
            refined_content = response.content if hasattr(response, 'content') else str(response)
            
            logger.info("内容改进成功")
            
            return {
                "draft_content": refined_content,
                "refined": True
            }
        except Exception as e:
            logger.error(f"内容改进失败: {e}")
            return {"draft_content": draft_content, "refined": False}

class FormattingAgent(BaseProductionAgent):
    """格式化 Agent - 转换为目标格式"""
    
    def __init__(self, llm):
        super().__init__("Formatting", llm, {})
    
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """将内容格式化为目标文档格式"""
        intent = state.get("intent")
        draft_content = state.get("draft_content", "")
        
        # 详细日志
        logger.info("=== 进入格式化节点 ===")
        logger.info(f"从 state 中读取的 draft_content 长度: {len(draft_content) if draft_content else 0}")
        logger.info(f"draft_content 前50字符: {draft_content[:50] if draft_content else '空'}")
        
        if not intent:
            logger.error("intent 不存在")
            return {"final_document": None}
        
        # 处理意图数据
        output_format = intent.get("output_format", "markdown") if isinstance(intent, dict) else intent.output_format
        logger.info(f"输出格式: {output_format}")
        
        # 如果内容为空，尝试从 content_outline 获取
        if not draft_content or len(draft_content) < 50:
            logger.warning("draft_content 为空或太短，尝试从 content_outline 获取")
            content_outline = state.get("content_outline", {})
            if content_outline:
                structure = content_outline.get("structure", "")
                if structure:
                    draft_content = structure
                    logger.warning(f"使用 content_outline 作为内容，长度: {len(draft_content)}")
                else:
                    logger.error("content_outline.structure 为空")
            else:
                logger.error("content_outline 不存在")
        
        # 如果还是没有内容，返回错误
        if not draft_content or len(draft_content) < 50:
            logger.error("无法获取有效内容")
            return {"final_document": None}
        
        # 根据输出格式处理
        if output_format in ["word", "pdf"]:
            # 使用现有的文档生成器
            try:
                from app.services.document_generator_service import DocumentGeneratorService
                generator = DocumentGeneratorService()
                
                # 创建文档内容对象
                from app.services.content_aggregator import AggregatedContent
                sections = self._parse_markdown_sections(draft_content)
                
                aggregated = AggregatedContent(
                    title=sections[0]["title"] if sections else "文档",
                    outline=[],
                    sections=[],
                    references=[]
                )
                
                # 生成文档
                result = generator.generate_document(
                    aggregated.to_document_content(),
                    output_format
                )
                
                return {
                    "final_document": {
                        "content": draft_content,
                        "formatted": True,
                        "format": output_format
                    },
                    "output_file_path": result.get("file_path")
                }
            except Exception as e:
                logger.error(f"文档格式化失败: {e}")
                return {"final_document": None}
        
        else:
            # Markdown 等简单格式直接返回
            return {
                "final_document": {
                    "content": draft_content,
                    "formatted": True,
                    "format": output_format
                }
            }
    
    def _parse_markdown_sections(self, content: str) -> List[Dict[str, Any]]:
        """解析 Markdown 内容为章节"""
        sections = []
        current_section = None
        
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                title = line.lstrip('#').strip()
                
                if current_section:
                    sections.append(current_section)
                
                current_section = {
                    "title": title,
                    "level": level,
                    "content": ""
                }
            elif current_section:
                current_section["content"] += line + "\n"
        
        if current_section:
            sections.append(current_section)
        
        return sections

