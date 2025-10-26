"""
内容聚合服务
从RAG检索结果和对话历史中提取并结构化内容
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ContentSection:
    """内容章节"""
    title: str
    content: str
    table_data: Optional[List[List[str]]] = None
    subsections: Optional[List['ContentSection']] = None


@dataclass
class AggregatedContent:
    """聚合后的内容"""
    title: str
    outline: List[str]
    sections: List[ContentSection]
    references: List[Dict]
    
    def to_document_content(self):
        """转换为DocumentContent格式（兼容现有生成器）"""
        from app.services.document_generator_service import DocumentContent
        
        # 构建文档内容
        content_text = f"# {self.title}\n\n"
        
        for section in self.sections:
            content_text += f"## {section.title}\n\n"
            content_text += f"{section.content}\n\n"
            
            if section.table_data:
                content_text += "| " + " | ".join(["列1", "列2", "列3"]) + " |\n"
                content_text += "| " + " | ".join(["---", "---", "---"]) + " |\n"
                for row in section.table_data:
                    content_text += "| " + " | ".join(row) + " |\n"
                content_text += "\n"
        
        return DocumentContent(
            title=self.title,
            sections=[
                {
                    'title': section.title,
                    'content': section.content,
                    'table_data': section.table_data
                }
                for section in self.sections
            ],
            metadata={
                "outline": self.outline,
                "references": self.references
            }
        )


class ContentAggregator:
    """内容聚合器"""
    
    def __init__(self, rag_service, llm):
        self.rag_service = rag_service
        self.llm = llm
        self.outline_prompt = """基于以下信息，生成一个结构化的文档大纲：

文档标题: {title}
文档类型: {doc_type}
内容来源: {content_source}

检索到的文档内容:
{documents_content}

对话历史关键信息:
{conversation_content}

请生成一个清晰的文档大纲，包含：
1. 主要章节标题
2. 每个章节的简要描述
3. 建议的内容组织方式

以JSON格式返回：
{{
    "outline": ["章节1", "章节2", "章节3"],
    "sections": [
        {{
            "title": "章节1",
            "description": "章节描述",
            "content_type": "text/table/mixed"
        }}
    ]
}}"""

        self.content_prompt = """基于以下大纲和内容，生成详细的文档内容：

文档标题: {title}
文档类型: {doc_type}
章节: {section_title}

检索到的相关内容:
{relevant_content}

对话历史信息:
{conversation_content}

请生成该章节的详细内容，要求：
1. 内容准确、完整
2. 逻辑清晰
3. 适合{doc_type}格式
4. 如果有数据，可以组织成表格形式

返回格式：
{{
    "content": "详细内容文本",
    "table_data": [["行1列1", "行1列2"], ["行2列1", "行2列2"]],
    "subsections": ["子章节1", "子章节2"]
}}"""

    async def aggregate_content(
        self, 
        intent,
        workspace_id: str,
        conversation_history: List[Dict],
        search_query: Optional[str] = None
    ) -> AggregatedContent:
        """
        聚合内容（优化版：减少LLM调用次数）
        
        Args:
            intent: 意图识别结果
            workspace_id: 工作区ID
            conversation_history: 对话历史
            search_query: 搜索查询
            
        Returns:
            AggregatedContent: 聚合后的内容
        """
        try:
            logger.info(f"开始内容聚合: {intent.title}")
            start_time = time.time()
            
            # 1. 基于意图检索相关文档
            documents_content = ""
            references = []
            
            if intent.content_source in ['documents', 'mixed']:
                docs = await self._retrieve_documents(
                    workspace_id, 
                    search_query or intent.inferred_query or intent.title
                )
                
                if docs:
                    # 增强文档内容提取
                    for i, doc in enumerate(docs):
                        doc_name = doc.get('document_name', f'文档{i+1}')
                        doc_content = doc.get('content', '') or doc.get('content_preview', '')
                        similarity = doc.get('similarity', 0)
                        
                        documents_content += f"📄 文档{i+1}: {doc_name} (相似度: {similarity:.2f})\n"
                        documents_content += f"📝 内容: {doc_content}\n"
                        
                        # 添加元数据信息
                        if doc.get('metadata'):
                            metadata = doc['metadata']
                            if metadata.get('page_number'):
                                documents_content += f"📖 页码: {metadata['page_number']}\n"
                            if metadata.get('file_type'):
                                documents_content += f"📁 类型: {metadata['file_type']}\n"
                        
                        documents_content += "\n" + "="*50 + "\n\n"
                    
                    references = docs
                    logger.info(f"成功检索到 {len(docs)} 个相关文档用于内容生成")
            
            # 2. 提取对话历史关键信息
            conversation_content = ""
            if intent.content_source in ['conversation', 'mixed']:
                conversation_content = await self._extract_key_points(conversation_history)
            
            # 3. 两阶段生成：先生成详细大纲，再生成具体内容
            logger.info("开始两阶段文档生成...")
            
            # 阶段1：生成详细大纲
            detailed_outline = await self._generate_detailed_outline(
                intent, documents_content, conversation_content
            )
            logger.info(f"大纲生成完成，包含 {len(detailed_outline.get('sections', []))} 个章节")
            
            # 阶段2：根据大纲生成具体内容
            sections = await self._generate_content_from_outline(
                intent, detailed_outline, documents_content, conversation_content
            )
            logger.info(f"内容生成完成，共 {len(sections)} 个章节")
            
            return AggregatedContent(
                title=intent.title,
                outline=detailed_outline.get('outline', []),
                sections=sections,
                references=references
            )
            
        except Exception as e:
            logger.error(f"内容聚合失败: {e}")
            # 返回增强的基础内容
            fallback_content = self._generate_fallback_content(intent, documents_content, conversation_content)
            return AggregatedContent(
                title=intent.title,
                outline=fallback_content.get('outline', [intent.title]),
                sections=fallback_content.get('sections', [ContentSection(
                    title=intent.title,
                    content=f"基于用户请求生成的内容：{intent.inferred_query or intent.title}"
                )]),
                references=[]
            )
    
    async def _generate_detailed_outline(self, intent, documents_content: str, conversation_content: str) -> Dict:
        """阶段1：生成详细大纲"""
        try:
            doc_type_guidance = self._get_document_type_guidance(intent.doc_type.value)
            structure_guidance = self._get_content_structure_guidance(intent.doc_type.value)
            
            outline_prompt = f"""你是一位专业的文档结构设计师，请为以下需求设计一个详细的大纲：

📋 **文档基本信息**
- 标题: {intent.title}
- 类型: {intent.doc_type.value.upper()}
- 内容来源: {intent.content_source}

{doc_type_guidance}

📚 **参考内容** (请基于以下信息设计大纲):
{documents_content[:3000] if documents_content else '无相关参考内容'}

💬 **用户需求信息**:
{conversation_content[:1000] if conversation_content else '无对话历史'}

{structure_guidance}

🎯 **大纲设计要求**:
1. 根据用户具体需求定制章节结构
2. 每个章节都要有明确的目的和价值
3. 章节之间要有逻辑递进关系
4. 包含具体的子章节和要点
5. 适合{intent.doc_type.value}文档的特点

📝 **返回格式** (严格JSON):
{{
    "outline": ["章节1", "章节2", "章节3", "章节4"],
    "sections": [
        {{
            "title": "章节1",
            "description": "章节的详细描述和目的",
            "subsections": ["子章节1.1", "子章节1.2", "子章节1.3"],
            "key_points": ["要点1", "要点2", "要点3"],
            "content_type": "text/table/mixed",
            "estimated_length": "300-500字"
        }},
        {{
            "title": "章节2",
            "description": "章节的详细描述和目的",
            "subsections": ["子章节2.1", "子章节2.2"],
            "key_points": ["要点1", "要点2"],
            "content_type": "text",
            "estimated_length": "400-600字"
        }}
    ]
}}

请确保大纲结构合理、内容充实、符合用户需求。"""
            
            response = await self.llm.ainvoke(outline_prompt)
            
            # 处理响应
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # 解析JSON响应
            import json
            # 清理响应内容
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            
        except Exception as e:
            logger.error(f"生成详细大纲失败: {e}")
        
        # 回退到基础大纲
        return {
            "outline": ["概述", "详细分析", "结论与建议"],
            "sections": [
                {
                    "title": "概述",
                    "description": "文档概述和背景介绍",
                    "subsections": ["背景", "目标", "范围"],
                    "key_points": ["问题背景", "解决目标"],
                    "content_type": "text",
                    "estimated_length": "300-400字"
                },
                {
                    "title": "详细分析",
                    "description": "深入分析和具体内容",
                    "subsections": ["现状分析", "问题识别", "解决方案"],
                    "key_points": ["数据分析", "问题分析", "方案设计"],
                    "content_type": "mixed",
                    "estimated_length": "500-700字"
                },
                {
                    "title": "结论与建议",
                    "description": "总结和建议措施",
                    "subsections": ["主要发现", "建议措施", "后续行动"],
                    "key_points": ["关键结论", "实施建议"],
                    "content_type": "text",
                    "estimated_length": "300-500字"
                }
            ]
        }
    
    async def _generate_content_from_outline(self, intent, outline: Dict, documents_content: str, conversation_content: str) -> List[ContentSection]:
        """阶段2：根据大纲生成具体内容"""
        sections = []
        
        for section_info in outline.get('sections', []):
            try:
                logger.info(f"正在生成章节: {section_info.get('title', '未知')}")
                
                # 为每个章节生成详细内容
                content = await self._generate_section_content(
                    intent, section_info, documents_content, conversation_content
                )
                sections.append(content)
                
            except Exception as e:
                logger.error(f"生成章节内容失败: {e}")
                # 添加基础章节内容
                sections.append(ContentSection(
                    title=section_info.get('title', '未知章节'),
                    content=f"# {section_info.get('title', '未知章节')}\n\n{section_info.get('description', '章节内容')}"
                ))
        
        return sections
    
    async def _generate_section_content(self, intent, section_info: Dict, documents_content: str, conversation_content: str) -> ContentSection:
        """为单个章节生成详细内容"""
        try:
            section_prompt = f"""你是一位专业的内容撰写专家，请根据以下大纲信息生成详细的章节内容：

📋 **章节信息**
- 标题: {section_info.get('title', '')}
- 描述: {section_info.get('description', '')}
- 子章节: {', '.join(section_info.get('subsections', []))}
- 关键要点: {', '.join(section_info.get('key_points', []))}
- 内容类型: {section_info.get('content_type', 'text')}
- 预计长度: {section_info.get('estimated_length', '300-500字')}

📚 **参考内容** (请充分利用):
{documents_content[:2000] if documents_content else '无相关参考内容'}

💬 **用户需求信息**:
{conversation_content[:800] if conversation_content else '无对话历史'}

🎯 **内容要求**:
1. 严格按照章节大纲结构组织内容
2. 包含所有关键要点和子章节
3. 内容专业、准确、有深度
4. 语言表达清晰、逻辑性强
5. 充分利用参考内容和用户需求
6. 达到预计长度要求
7. 适合{intent.doc_type.value}文档格式

📝 **返回格式** (严格JSON):
{{
    "content": "详细的章节内容，包含所有子章节和要点...",
    "table_data": [["表头1", "表头2"], ["数据1", "数据2"]],
    "subsections": ["子章节1", "子章节2"]
}}

请确保内容充实、专业、有价值。"""
            
            response = await self.llm.ainvoke(section_prompt)
            
            # 处理响应
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            logger.info(f"LLM响应 (章节: {section_info.get('title', '')}): {response_text[:200]}...")
            
            # 解析JSON响应
            import json
            # 清理响应内容
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                try:
                    content_data = json.loads(json_str)
                    logger.info(f"成功解析JSON，内容长度: {len(content_data.get('content', ''))}")
                    
                    return ContentSection(
                        title=section_info.get('title', ''),
                        content=content_data.get('content', ''),
                        table_data=content_data.get('table_data'),
                        subsections=content_data.get('subsections')
                    )
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {e}, JSON内容: {json_str[:100]}...")
            else:
                logger.error(f"未找到JSON格式，响应内容: {response_text[:200]}...")
            
        except Exception as e:
            logger.error(f"生成章节内容失败: {e}")
        
        # 回退到基础内容
        fallback_content = f"""# {section_info.get('title', '未知章节')}

## 概述
{section_info.get('description', '章节描述')}

## 主要内容
{documents_content[:300] if documents_content else '暂无相关参考内容'}

## 关键要点
{chr(10).join([f"- {point}" for point in section_info.get('key_points', [])])}

## 总结
基于以上分析，我们可以得出相关结论和建议。"""
        
        return ContentSection(
            title=section_info.get('title', '未知章节'),
            content=fallback_content,
            table_data=None,
            subsections=section_info.get('subsections', [])
        )

    async def _generate_complete_document(self, intent, documents_content: str, conversation_content: str) -> Dict:
        """使用增强的LLM调用生成高质量完整文档"""
        try:
            # 构建增强的提示词
            doc_type_guidance = self._get_document_type_guidance(intent.doc_type.value)
            content_structure = self._get_content_structure_guidance(intent.doc_type.value)
            
            prompt = f"""你是一位专业的文档撰写专家，请为以下请求生成高质量的文档内容：

📋 **文档基本信息**
- 标题: {intent.title}
- 类型: {intent.doc_type.value.upper()}
- 内容来源: {intent.content_source}

{doc_type_guidance}

📚 **参考内容** (请充分利用以下信息):
{documents_content[:4000] if documents_content else '无相关参考内容'}

💬 **对话历史关键信息**:
{conversation_content[:1500] if conversation_content else '无对话历史'}

{content_structure}

🎯 **质量要求**:
1. 内容必须准确、专业、有深度
2. 逻辑清晰，结构合理
3. 每个章节至少300-500字
4. 包含具体的数据、案例或分析
5. 语言表达专业且易懂
6. 符合{intent.doc_type.value}文档的标准格式

📝 **返回格式** (严格JSON):
{{
    "outline": ["章节1", "章节2", "章节3", "章节4"],
    "sections": [
        {{
            "title": "章节1",
            "content": "详细的章节内容，包含具体信息、数据、分析等，至少300字..."
        }},
        {{
            "title": "章节2", 
            "content": "详细的章节内容，包含具体信息、数据、分析等，至少300字..."
        }}
    ]
}}

请确保生成的内容专业、详细、有价值，避免空洞的表述。"""
            
            response = await self.llm.ainvoke(prompt)
            
            # 处理响应
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # 解析JSON响应
            import json
            # 清理响应内容
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            
        except Exception as e:
            logger.error(f"生成完整文档失败: {e}")
        
            # 回退到简单内容
            return {
                "outline": [intent.title],
                "sections": [{
                    "title": intent.title,
                    "content": f"基于用户请求生成的内容：{intent.inferred_query or intent.title}\n\n{documents_content[:500] if documents_content else ''}"
                }]
            }
    
    def _get_document_type_guidance(self, doc_type: str) -> str:
        """获取文档类型指导"""
        guidance_map = {
            "word": """
📄 **Word文档指导**:
- 适合报告、分析文档、说明文档等
- 需要清晰的章节结构和层次
- 可以包含表格、图表说明
- 语言正式、专业
- 建议包含：概述、详细分析、结论、建议等章节""",
            
            "excel": """
📊 **Excel文档指导**:
- 适合数据报告、财务分析、统计报告等
- 重点突出数据分析和表格展示
- 每个章节可以对应一个工作表
- 包含数据解读和分析
- 建议包含：数据概览、详细分析、趋势分析、结论等章节""",
            
            "ppt": """
🎯 **PPT文档指导**:
- 适合演示文稿、汇报材料、培训资料等
- 内容简洁明了，重点突出
- 每页内容不宜过多
- 语言生动，适合口头表达
- 建议包含：概述、核心内容、案例分析、总结等章节""",
            
            "pdf": """
📋 **PDF文档指导**:
- 适合正式报告、技术文档、白皮书等
- 内容完整、结构严谨
- 可以包含图表、附录
- 语言专业、准确
- 建议包含：摘要、正文、结论、参考文献等章节"""
        }
        return guidance_map.get(doc_type, guidance_map["word"])
    
    def _get_content_structure_guidance(self, doc_type: str) -> str:
        """获取内容结构指导"""
        structure_map = {
            "word": """
🏗️ **Word文档结构建议**:
1. **概述/引言** - 介绍背景、目的、范围
2. **现状分析** - 当前情况、问题识别
3. **详细分析** - 深入分析、数据支撑
4. **解决方案** - 建议措施、实施计划
5. **结论与建议** - 总结要点、后续行动""",
            
            "excel": """
📈 **Excel文档结构建议**:
1. **数据概览** - 总体数据、关键指标
2. **分类分析** - 按类别、时间、地区等分析
3. **趋势分析** - 变化趋势、预测分析
4. **对比分析** - 同期对比、目标对比
5. **结论与建议** - 数据洞察、行动建议""",
            
            "ppt": """
🎨 **PPT文档结构建议**:
1. **开场/背景** - 问题背景、重要性
2. **核心内容** - 主要观点、关键信息
3. **案例分析** - 具体案例、实例说明
4. **行动方案** - 具体措施、实施步骤
5. **总结/展望** - 要点回顾、未来规划""",
            
            "pdf": """
📑 **PDF文档结构建议**:
1. **执行摘要** - 核心要点、主要结论
2. **背景介绍** - 问题背景、研究范围
3. **方法论** - 分析方法、数据来源
4. **详细分析** - 深入分析、证据支撑
5. **结论与建议** - 研究发现、政策建议"""
        }
        return structure_map.get(doc_type, structure_map["word"])
    
    def _generate_fallback_content(self, intent, documents_content: str, conversation_content: str) -> Dict:
        """生成回退内容"""
        try:
            # 基于可用内容生成基础结构
            outline = [
                "概述",
                "详细分析", 
                "结论与建议"
            ]
            
            sections = []
            
            # 概述章节
            overview_content = f"""
# {intent.title}

## 概述
本文档基于用户需求"{intent.inferred_query or intent.title}"生成。

## 背景
{document_content[:300] if (doc_content := documents_content) else '暂无相关背景信息'}

## 目标
根据用户需求，本文档旨在提供相关分析和建议。
"""
            
            sections.append(ContentSection(
                title="概述",
                content=overview_content.strip()
            ))
            
            # 详细分析章节
            analysis_content = f"""
## 详细分析

### 相关文档信息
{document_content[:500] if (doc_content := documents_content) else '暂无相关文档信息'}

### 对话历史要点
{conversation_content[:300] if conversation_content else '暂无对话历史'}

### 分析要点
基于以上信息，我们可以得出以下分析要点：
1. 用户关注的核心问题
2. 相关数据和事实
3. 可能的解决方案
"""
            
            sections.append(ContentSection(
                title="详细分析",
                content=analysis_content.strip()
            ))
            
            # 结论章节
            conclusion_content = f"""
## 结论与建议

### 主要发现
基于分析，我们发现以下关键点：
- 用户需求明确
- 相关资源可用
- 需要进一步行动

### 建议措施
1. 继续深入分析相关数据
2. 制定具体的实施计划
3. 定期评估和调整

### 后续行动
建议用户根据具体需求进一步完善相关内容。
"""
            
            sections.append(ContentSection(
                title="结论与建议",
                content=conclusion_content.strip()
            ))
            
            return {
                "outline": outline,
                "sections": sections
            }
            
        except Exception as e:
            logger.error(f"生成回退内容失败: {e}")
            return {
                "outline": [intent.title],
                "sections": [ContentSection(
                    title=intent.title,
                    content=f"基于用户请求生成的内容：{intent.inferred_query or intent.title}"
                )]
            }
    
    async def _enhance_content_quality(
        self, 
        intent, 
        initial_content: Dict, 
        documents_content: str, 
        conversation_content: str
    ) -> Dict:
        """增强内容质量（第二轮）"""
        try:
            logger.info("开始第二轮内容质量增强...")
            
            # 分析初始内容的质量
            quality_analysis = await self._analyze_content_quality(initial_content)
            
            # 基于质量分析进行内容扩展
            enhanced_sections = []
            for section in initial_content.get('sections', []):
                enhanced_section = await self._expand_section_content(
                    section, quality_analysis, documents_content, conversation_content
                )
                enhanced_sections.append(enhanced_section)
            
            return {
                "outline": initial_content.get('outline', []),
                "sections": enhanced_sections,
                "quality_analysis": quality_analysis
            }
            
        except Exception as e:
            logger.error(f"内容质量增强失败: {e}")
            return initial_content
    
    async def _analyze_content_quality(self, content: Dict) -> Dict:
        """分析内容质量"""
        try:
            sections = content.get('sections', [])
            
            quality_metrics = {
                "total_sections": len(sections),
                "avg_content_length": 0,
                "needs_expansion": [],
                "missing_elements": []
            }
            
            total_length = 0
            for i, section in enumerate(sections):
                content_length = len(section.get('content', ''))
                total_length += content_length
                
                # 检查是否需要扩展
                if content_length < 800:  # 少于800字需要扩展
                    quality_metrics["needs_expansion"].append(i)
                
                # 检查缺失元素
                content_text = section.get('content', '').lower()
                if '数据' not in content_text and '分析' not in content_text:
                    quality_metrics["missing_elements"].append(f"section_{i}_data")
                if '案例' not in content_text and '例子' not in content_text:
                    quality_metrics["missing_elements"].append(f"section_{i}_examples")
            
            quality_metrics["avg_content_length"] = total_length / max(len(sections), 1)
            
            return quality_metrics
            
        except Exception as e:
            logger.error(f"内容质量分析失败: {e}")
            return {"needs_expansion": [], "missing_elements": []}
    
    async def _expand_section_content(
        self, 
        section: Dict, 
        quality_analysis: Dict, 
        documents_content: str, 
        conversation_content: str
    ) -> Dict:
        """扩展章节内容"""
        try:
            section_index = quality_analysis.get("needs_expansion", [])
            if not section_index:
                return section
            
            # 构建扩展提示
            expansion_prompt = f"""请扩展以下章节内容，使其更加详细和专业：

章节标题: {section.get('title', '')}
当前内容: {section.get('content', '')}

参考信息:
{documents_content[:2000]}

对话历史:
{conversation_content[:1000]}

请生成扩展后的内容，要求：
1. 内容长度至少800-1200字
2. 包含具体的数据和分析
3. 添加相关案例和例子
4. 保持逻辑清晰和专业性
5. 如果可能，生成表格数据

返回JSON格式：
{{
    "expanded_content": "扩展后的详细内容...",
    "table_data": [
        ["列1", "列2", "列3"],
        ["数据1", "数据2", "数据3"]
    ],
    "subsections": [
        {{
            "title": "子章节标题",
            "content": "子章节内容"
        }}
    ]
}}"""
            
            response = await self.llm.ainvoke(expansion_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析扩展结果
            try:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    expanded_data = json.loads(json_match.group())
                    
                    return {
                        "title": section.get('title', ''),
                        "content": expanded_data.get('expanded_content', section.get('content', '')),
                        "table_data": expanded_data.get('table_data'),
                        "subsections": expanded_data.get('subsections', [])
                    }
            except Exception as e:
                logger.warning(f"解析扩展结果失败: {e}")
            
            # 如果解析失败，返回原内容
            return section
            
        except Exception as e:
            logger.error(f"扩展章节内容失败: {e}")
            return section
    
    async def _extract_structured_data_and_optimize(
        self, 
        intent, 
        enhanced_content: Dict, 
        documents_content: str, 
        conversation_content: str
    ) -> Dict:
        """提取结构化数据并最终优化（第三轮）"""
        try:
            logger.info("开始第三轮结构化数据提取和优化...")
            
            # 提取结构化数据
            structured_data = await self._extract_tables_and_charts(enhanced_content, documents_content)
            
            # 优化内容结构
            optimized_sections = []
            for section in enhanced_content.get('sections', []):
                optimized_section = await self._optimize_section_structure(section, structured_data)
                optimized_sections.append(optimized_section)
            
            return {
                "outline": enhanced_content.get('outline', []),
                "sections": optimized_sections,
                "structured_data": structured_data
            }
            
        except Exception as e:
            logger.error(f"结构化数据提取和优化失败: {e}")
            return enhanced_content
    
    async def _extract_tables_and_charts(self, content: Dict, documents_content: str) -> Dict:
        """提取表格和图表数据"""
        try:
            extraction_prompt = f"""基于以下内容，提取和生成结构化数据：

文档内容: {content}

参考信息: {documents_content[:1500]}

请分析内容并生成：
1. 数据表格（如果有数值数据）
2. 对比表格（如果有比较内容）
3. 流程图或步骤图（如果有流程描述）
4. 时间线（如果有时间相关内容）

返回JSON格式：
{{
    "tables": [
        {{
            "title": "表格标题",
            "headers": ["列1", "列2", "列3"],
            "data": [
                ["行1列1", "行1列2", "行1列3"],
                ["行2列1", "行2列2", "行2列3"]
            ]
        }}
    ],
    "charts": [
        {{
            "type": "bar|line|pie",
            "title": "图表标题",
            "data": {{"labels": ["标签1", "标签2"], "values": [10, 20]}}
        }}
    ],
    "timelines": [
        {{
            "title": "时间线标题",
            "events": [
                {{"date": "2024-01", "event": "事件描述"}},
                {{"date": "2024-02", "event": "事件描述"}}
            ]
        }}
    ]
}}"""
            
            response = await self.llm.ainvoke(extraction_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析结构化数据
            try:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            except Exception as e:
                logger.warning(f"解析结构化数据失败: {e}")
            
            return {"tables": [], "charts": [], "timelines": []}
            
        except Exception as e:
            logger.error(f"提取结构化数据失败: {e}")
            return {"tables": [], "charts": [], "timelines": []}
    
    async def _optimize_section_structure(self, section: Dict, structured_data: Dict) -> Dict:
        """优化章节结构"""
        try:
            # 将结构化数据整合到章节中
            optimized_section = section.copy()
            
            # 添加相关表格
            if structured_data.get('tables'):
                for table in structured_data['tables']:
                    if table.get('title') and table.get('title').lower() in section.get('title', '').lower():
                        optimized_section['table_data'] = table.get('data', [])
                        break
            
            # 优化内容格式
            content = optimized_section.get('content', '')
            
            # 添加数据引用
            if structured_data.get('tables'):
                content += "\n\n### 相关数据表格\n"
                for table in structured_data['tables'][:2]:  # 最多添加2个表格
                    content += f"\n**{table.get('title', '数据表格')}**\n"
                    content += "| " + " | ".join(table.get('headers', [])) + " |\n"
                    content += "| " + " | ".join(["---"] * len(table.get('headers', []))) + " |\n"
                    for row in table.get('data', []):
                        content += "| " + " | ".join(row) + " |\n"
                    content += "\n"
            
            optimized_section['content'] = content
            
            return optimized_section
            
        except Exception as e:
            logger.error(f"优化章节结构失败: {e}")
            return section

    async def _retrieve_documents(self, workspace_id: str, query: str) -> List[Dict]:
        """检索相关文档"""
        try:
            # 使用RAG服务检索文档，增加检索数量
            response = await self.rag_service.ask_question(
                workspace_id=workspace_id,
                question=query,
                top_k=15  # 增加检索数量以获得更多内容
            )
            
            references = response.get('references', [])
            
            # 增强文档内容，确保有足够的信息
            enhanced_refs = []
            for ref in references:
                enhanced_ref = ref.copy()
                # 确保有足够的内容
                if len(enhanced_ref.get('content', '')) < 100:
                    enhanced_ref['content'] = enhanced_ref.get('content_preview', '') or enhanced_ref.get('content', '')
                enhanced_refs.append(enhanced_ref)
            
            return enhanced_refs
            
        except Exception as e:
            logger.error(f"文档检索失败: {e}")
            return []
    
    async def _extract_key_points(self, conversation_history: List[Dict]) -> str:
        """提取对话历史关键信息"""
        if not conversation_history:
            return ""
        
        # 构建对话历史字符串
        history_text = ""
        for msg in conversation_history[-10:]:  # 只取最近10条
            role = "用户" if msg.get('role') == 'user' else "助手"
            content = msg.get('content', '')
            history_text += f"{role}: {content}\n"
        
        # 使用LLM提取关键信息
        try:
            extract_prompt = f"""请从以下对话历史中提取关键信息，用于高质量文档生成：

对话历史:
{history_text}

请详细提取以下信息：
1. **用户的具体需求和目标** - 用户想要什么？
2. **讨论的核心问题和话题** - 主要关注什么？
3. **重要的数据、案例、事实** - 有什么具体信息？
4. **用户的偏好和要求** - 有什么特殊要求？
5. **关键观点和结论** - 达成了什么共识？
6. **需要强调的重点** - 什么最重要？

请以结构化的方式整理这些信息，确保对生成专业文档有价值。"""
            
            response = await self.llm.ainvoke(extract_prompt)
            return response if isinstance(response, str) else str(response)
            
        except Exception as e:
            logger.error(f"提取对话关键信息失败: {e}")
            return history_text
    
    async def _generate_outline(self, intent, documents_content: str, conversation_content: str) -> Dict:
        """生成文档大纲"""
        try:
            prompt = self.outline_prompt.format(
                title=intent.title,
                doc_type=intent.doc_type.value,
                content_source=intent.content_source,
                documents_content=documents_content[:2000],  # 限制长度
                conversation_content=conversation_content[:1000]
            )
            
            response = await self.llm.ainvoke(prompt)
            
            # 处理不同类型的响应
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # 解析JSON响应
            import json
            # 清理响应内容，移除可能的markdown代码块标记
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            
        except Exception as e:
            logger.error(f"生成大纲失败: {e}")
        
        # 回退到简单大纲
        return {
            "outline": [intent.title],
            "sections": [{
                "title": intent.title,
                "description": "主要内容",
                "content_type": "text"
            }]
        }
    
    async def _fill_section_content(self, intent, section_info: Dict, documents_content: str, conversation_content: str) -> ContentSection:
        """填充章节详细内容"""
        try:
            prompt = self.content_prompt.format(
                title=intent.title,
                doc_type=intent.doc_type.value,
                section_title=section_info.get('title', ''),
                relevant_content=documents_content[:1500],
                conversation_content=conversation_content[:800]
            )
            
            response = await self.llm.ainvoke(prompt)
            
            # 处理不同类型的响应
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # 解析JSON响应
            import json
            # 清理响应内容，移除可能的markdown代码块标记
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                content_data = json.loads(json_str)
                
                return ContentSection(
                    title=section_info.get('title', ''),
                    content=content_data.get('content', ''),
                    table_data=content_data.get('table_data'),
                    subsections=content_data.get('subsections')
                )
            
        except Exception as e:
            logger.error(f"填充章节内容失败: {e}")
            # 直接使用文本内容，不解析JSON
            if hasattr(response, 'content'):
                content_text = response.content
            elif 'response_text' in locals():
                content_text = response_text
            else:
                content_text = f"这是{section_info.get('title', '')}的内容。"
            
            return ContentSection(
                title=section_info.get('title', ''),
                content=content_text,
                table_data=None
            )
        
        # 回退到简单内容
        return ContentSection(
            title=section_info.get('title', ''),
            content=f"这是{section_info.get('title', '')}的内容。",
            table_data=None
        )
