"""
DeepResearch 风格长文档生成工作流
采用分段-并行检索-独立生成-合并架构
"""

from typing import TypedDict, List, Dict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
import os
import asyncio
import logging
import json
import re

logger = logging.getLogger(__name__)

# 状态定义
class DocGenState(TypedDict):
    """长文档生成状态"""
    # 输入
    task_description: str
    workspace_id: str
    doc_requirements: Dict  # 字数要求、风格等
    
    # 规划层
    outline: Dict  # 3-6级目录结构，20-50个段落标题
    total_sections: int
    estimated_length: int
    
    # 段落缓存（避免重复检索）
    section_buffer: Dict[str, Dict]  # {section_id: {title, content, sources}}
    
    # 检索层（并行）
    retrieval_tasks: List[Dict]  # 每段的检索任务
    retrieval_results: Dict[str, List[Dict]]  # {section_id: [docs]}
    
    # 生成层（并行）
    section_drafts: Dict[str, str]  # {section_id: draft_content}
    section_metadata: Dict[str, Dict]  # {section_id: {word_count, sources}}
    
    # 合并与后编辑
    merged_draft: str
    conflicts: List[Dict]  # 逻辑跳跃、数字冲突等
    final_document: str
    
    # 质量控制
    quality_metrics: Dict
    references: List[Dict]
    
    # 元数据
    processing_steps: List[str]
    current_step: str
    error: str

class DeepResearchDocWorkflow:
    """DeepResearch 风格长文档生成工作流"""
    
    def __init__(self, workspace_retriever, global_retriever, web_search_service, llm=None):
        self.workspace_retriever = workspace_retriever
        self.global_retriever = global_retriever
        self.web_search_service = web_search_service
        if llm is None:
            api_key = os.getenv('THIRD_PARTY_API_KEY') or os.getenv('OPENAI_API_KEY')
            api_base = os.getenv('THIRD_PARTY_API_BASE') or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
            # 从环境变量读取模型名称，默认使用 gpt-4o
            model_name = os.getenv('LLM_MODEL', 'gpt-4o-2024-08-06')
            self.llm = ChatOpenAI(
                model=model_name,
                temperature=0.3,
                openai_api_key=api_key,
                openai_api_base=api_base
            )
        else:
            self.llm = llm
        
        self.graph = self._build_graph()
        self.checkpointer = MemorySaver()
        self.compiled_graph = self.graph.compile(checkpointer=self.checkpointer)
    
    def _build_graph(self) -> StateGraph:
        """构建文档生成状态图"""
        workflow = StateGraph(DocGenState)
        
        # 节点
        workflow.add_node("outline_planning", self._outline_planning_node)
        workflow.add_node("parallel_retrieval", self._parallel_retrieval_node)
        workflow.add_node("parallel_generation", self._parallel_generation_node)
        workflow.add_node("merge_sections", self._merge_sections_node)
        workflow.add_node("final_polish", self._final_polish_node)
        
        # 流程
        workflow.set_entry_point("outline_planning")
        workflow.add_edge("outline_planning", "parallel_retrieval")
        workflow.add_edge("parallel_retrieval", "parallel_generation")
        workflow.add_edge("parallel_generation", "merge_sections")
        workflow.add_edge("merge_sections", "final_polish")
        workflow.add_edge("final_polish", END)
        
        return workflow
    
    async def _outline_planning_node(self, state: DocGenState) -> DocGenState:
        """节点1: 提纲规划 - 智能理解用户意图"""
        task_desc = state["task_description"]
        requirements = state["doc_requirements"]
        target_words = requirements.get("target_words", 5000)
        
        prompt = f"""请仔细分析以下任务，深度理解用户意图并生成合适的文档结构。

任务描述: {task_desc}
目标字数: {target_words}

**第一步：自我提问并深度理解（关键步骤）**

请主动思考并回答以下问题：

1. **关于任务背景的理解**
   - 用户提到的关键概念是什么？（如"前海十二条"、"入驻条件"等）
   - 对于这些关键概念，我需要知道什么？
   - 例如：如果说"前海十二条"，它具体指什么内容？每条政策的具体要求是什么？

2. **关于输出类型的理解**
   - 用户想要什么类型的内容？（问卷、报告、说明文档等）
   - 为什么这样理解？

3. **关于用途和受众**
   - 这个内容用于什么目的？
   - 谁会使用它？

4. **关于格式的要求**
   - 最合适的结构应该是什么样的？
   - 为什么这个结构能最好地服务用户需求？

**第二步：生成文档大纲框架**

基于你的理解，生成分层次的文档大纲。先给出整体框架，再细化：
- **问卷类**：先有评估框架（如哪些维度需要评估），再细化为具体问题和选项
- **报告类**：先有章节主题（如哪些方面需要分析），再细化为具体内容
- 每层都有明确的主题和目标

**返回JSON格式:**
{{
    "understanding": {{
        "intent_type": "你认为用户想要生成的类型",
        "reasoning": "你为什么这样理解（1-2句话）",
        "purpose": "这个输出用于什么目的",
        "target_audience": "目标受众是谁",
        "output_format": "预期的格式特点（如：每道题目包含选项/段落式说明/条目式清单等）"
    }},
    "structure": {{
        "title": "文档/问卷标题",
        "sections": [
            {{"id": "part_1", "level": 1, "title": "一级主题（框架性）", "notes": "说明这一部分的整体目标"}},
            {{"id": "part_1_1", "level": 2, "title": "二级主题（细化）", "notes": "具体要涵盖的内容"}},
            {{"id": "part_1_2", "level": 2, "title": "二级主题（细化）", "notes": "具体要涵盖的内容"}},
            {{"id": "part_2", "level": 1, "title": "一级主题（框架性）", "notes": "说明这一部分的整体目标"}},
            ...
        ]
    }}
}}"""
        
        response = await self.llm.ainvoke(prompt)
        
        try:
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                outline = json.loads(json_match.group())
                state["outline"] = outline
                all_sections = self._flatten_sections(outline.get("structure", {}).get("sections", []))
                state["total_sections"] = len(all_sections)
            else:
                state["outline"] = {"title": task_desc, "structure": {"sections": []}}
                state["total_sections"] = 0
        except Exception as e:
            logger.error(f"提纲解析失败: {e}")
            state["outline"] = {"title": task_desc, "structure": {"sections": []}}
            state["total_sections"] = 0
        
        state["processing_steps"].append("outline_planning")
        logger.info(f"提纲生成完成，共 {state['total_sections']} 个段落")
        
        return state
    
    def _flatten_sections(self, sections: List[Dict]) -> List[Dict]:
        """扁平化嵌套的段落结构"""
        result = []
        for section in sections:
            result.append(section)
        return result
    
    async def _parallel_retrieval_node(self, state: DocGenState) -> DocGenState:
        """节点2: 并行检索（每段独立检索）"""
        outline = state["outline"]
        # 适应新的结构格式
        if "structure" in outline:
            all_sections = self._flatten_sections(outline.get("structure", {}).get("sections", []))
        else:
            all_sections = self._flatten_sections(outline.get("sections", []))
        
        async def retrieve_for_section(section):
            section_id = section["id"]
            query = section["title"]
            
            # 并行：工作区 + 全局
            workspace_task = self.workspace_retriever.retrieve(query, top_k=3, use_hybrid=True)
            global_task = self.global_retriever.retrieve(query, top_k=3, use_hybrid=True)
            
            workspace_docs, global_docs = await asyncio.gather(
                workspace_task, global_task, return_exceptions=True
            )
            
            all_docs = []
            if not isinstance(workspace_docs, Exception):
                all_docs.extend(workspace_docs)
            if not isinstance(global_docs, Exception):
                all_docs.extend(global_docs)
            
            return {section_id: all_docs[:5]}
        
        results = await asyncio.gather(*[retrieve_for_section(s) for s in all_sections])
        
        retrieval_results = {}
        for result in results:
            retrieval_results.update(result)
        
        state["retrieval_results"] = retrieval_results
        state["processing_steps"].append("parallel_retrieval")
        logger.info(f"并行检索完成，共 {len(retrieval_results)} 个段落")
        
        return state
    
    async def _parallel_generation_node(self, state: DocGenState) -> DocGenState:
        """节点3: 并行生成（每段独立生成500-800字）"""
        outline = state["outline"]
        # 适应新的结构格式
        if "structure" in outline:
            all_sections = self._flatten_sections(outline.get("structure", {}).get("sections", []))
        else:
            all_sections = self._flatten_sections(outline.get("sections", []))
        retrieval_results = state["retrieval_results"]
        writing_style = state["doc_requirements"].get("writing_style", "专业、严谨、客观")
        
        async def generate_section(section):
            section_id = section["id"]
            section_title = section["title"]
            docs = retrieval_results.get(section_id, [])
            
            context = "\n\n".join([
                f"参考资料{i+1}:\n{doc['content'][:500]}"
                for i, doc in enumerate(docs[:3])
            ])
            
            # 获取用户理解和期望格式
            understanding = outline.get("understanding", {})
            intent_type = understanding.get("intent_type", "文档")
            output_format = understanding.get("output_format", "段落式说明")
            notes = section.get("notes", "")
            
            # 根据层次和类型生成内容
            level = section.get("level", 1)
            
            # 一级框架：生成整体思路说明
            if level == 1:
                prompt = f"""生成框架性说明：

主题：{section_title}
目标：{notes}

参考资料:
{context}

请生成一个框架性说明（150-200字），解释这一部分的整体思路和目标：
"""
            elif "问卷" in intent_type or "问题" in output_format or "选项" in output_format:
                # 问卷题
                # 问卷格式 - 基于理解动态生成
                prompt = f"""基于用户需求生成问卷内容：

用户需要的类型：{intent_type}
期望的格式：{output_format}
当前部分：{section_title}
补充说明：{notes}

参考资料:
{context}

请理解用户的真实需求，生成：
1. 一道具体、可操作的题目（能有效评估相关条件）
2. 3-5个选项或判断标准
3. 确保题目和选项符合用户使用场景

输出格式：
**题目**：[具体题目]

**选项**：
A. [选项A]
B. [选项B]  
C. [选项C]

或

**判断标准**：
- 符合条件：...
- 不符合条件：...
"""
            elif "表格" in intent_type or "清单" in intent_type:
                # 表格格式 - 基于理解
                prompt = f"""基于用户需求生成内容：

用户需要的类型：{intent_type}
期望的格式：{output_format}
当前字段：{section_title}
补充说明：{notes}

参考资料:
{context}

生成简洁明了的字段或条目说明，便于填写和使用。
"""
            else:
                # 普通文档格式 - 基于理解
                prompt = f"""基于用户需求生成文档内容：

用户需要的类型：{intent_type}
期望的格式：{output_format}
段落标题: {section_title}
补充说明: {notes}
写作风格: {writing_style}

参考资料:
{context}

要求:
1. 围绕标题写作（500-800字），聚焦本段内容
2. 不要写总结或过渡，确保内容专业有价值
3. 基于参考资料，语言{writing_style}

段落内容:
"""
            
            response = await self.llm.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            metadata = {
                "word_count": len(content),
                "sources": [doc["metadata"].get("filename", doc["metadata"].get("url", "")) for doc in docs]
            }
            
            return {
                "section_id": section_id,
                "content": content,
                "metadata": metadata
            }
        
        generation_results = await asyncio.gather(*[generate_section(s) for s in all_sections])
        
        section_drafts = {}
        section_metadata = {}
        for result in generation_results:
            sid = result["section_id"]
            section_drafts[sid] = result["content"]
            section_metadata[sid] = result["metadata"]
        
        state["section_drafts"] = section_drafts
        state["section_metadata"] = section_metadata
        state["processing_steps"].append("parallel_generation")
        
        return state
    
    async def _merge_sections_node(self, state: DocGenState) -> DocGenState:
        """节点4: 合并段落"""
        outline = state["outline"]
        # 适应新的结构格式
        if "structure" in outline:
            all_sections = self._flatten_sections(outline.get("structure", {}).get("sections", []))
            doc_title = outline.get("structure", {}).get("title", outline.get("understanding", {}).get("intent_type", "文档"))
        else:
            all_sections = self._flatten_sections(outline.get("sections", []))
            doc_title = outline.get("title", "文档")
        
        section_drafts = state["section_drafts"]
        
        merged_parts = [f"# {doc_title}\n\n"]
        
        for section in all_sections:
            sid = section["id"]
            title = section["title"]
            level = section.get("level", 1)
            content = section_drafts.get(sid, "")
            
            prefix = "#" * level
            merged_parts.append(f"{prefix} {title}\n\n{content}\n\n")
        
        state["merged_draft"] = "".join(merged_parts)
        state["processing_steps"].append("merge_sections")
        
        return state
    
    async def _final_polish_node(self, state: DocGenState) -> DocGenState:
        """节点5: 最终润色"""
        merged_draft = state["merged_draft"]
        section_metadata = state["section_metadata"]
        
        # 收集所有引用
        all_sources = set()
        for metadata in section_metadata.values():
            all_sources.update(metadata.get("sources", []))
        
        references = []
        for i, source in enumerate(sorted(all_sources), 1):
            if source:
                references.append({"id": i, "source": source})
        
        if references:
            ref_section = "\n\n## 参考文献\n\n"
            for ref in references:
                ref_section += f"{ref['id']}. {ref['source']}\n"
            merged_draft += ref_section
        
        state["final_document"] = merged_draft
        state["references"] = references
        
        state["quality_metrics"] = {
            "total_words": len(merged_draft),
            "total_sections": state["total_sections"],
            "references_count": len(references)
        }
        
        state["processing_steps"].append("final_polish")
        logger.info("文档生成完成")
        
        return state
    
    async def run(self, task_description: str, workspace_id: str = "global", doc_requirements: Dict = None) -> Dict:
        """执行文档生成工作流"""
        if doc_requirements is None:
            doc_requirements = {"target_words": 5000, "writing_style": "专业"}
        
        initial_state = DocGenState(
            task_description=task_description,
            workspace_id=workspace_id,
            doc_requirements=doc_requirements,
            outline={},
            total_sections=0,
            estimated_length=0,
            section_buffer={},
            retrieval_tasks=[],
            retrieval_results={},
            section_drafts={},
            section_metadata={},
            merged_draft="",
            conflicts=[],
            final_document="",
            quality_metrics={},
            references=[],
            processing_steps=[],
            current_step="",
            error=""
        )
        
        final_state = await self.compiled_graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": "doc_gen"}}
        )
        
        # 提取大纲结构便于前端展示
        outline_data = final_state["outline"]
        if "structure" in outline_data:
            outline = outline_data["structure"]
        else:
            outline = {
                "title": outline_data.get("title", "文档"),
                "sections": outline_data.get("sections", [])
            }
        
        return {
            "document": final_state["final_document"],
            "quality_metrics": final_state["quality_metrics"],
            "references": final_state.get("references", []),
            "outline": outline,
            "processing_steps": final_state["processing_steps"]
        }

