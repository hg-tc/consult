"""
问答服务
基于文档内容的大模型问答系统，支持引用和上下文管理
"""

import json
import logging
from typing import Dict, List, Any, Optional, AsyncGenerator
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import LLMService
from app.services.vector_service import VectorService
from app.utils.import_with_timeout import import_symbol_with_timeout
LlamaIndexRetriever = import_symbol_with_timeout(
    "app.services.llamaindex_retriever", "LlamaIndexRetriever", timeout_seconds=5.0
)
from app.services.context_service import ContextService

logger = logging.getLogger(__name__)


@dataclass
class QAResult:
    """问答结果"""
    answer: str
    references: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    confidence: float
    metadata: Dict[str, Any]


class QAService:
    """问答服务"""

    def __init__(self):
        self.llm_service = LLMService()
        self.vector_service = VectorService()
        self.context_service = ContextService()

    async def ask_question(
        self,
        workspace_id: str,
        question: str,
        conversation_id: str = None,
        model_provider: str = "openai",
        max_references: int = 5,
        db: AsyncSession = None,
        **kwargs
    ) -> QAResult:
        """
        回答问题

        Args:
            workspace_id: 工作区ID
            question: 问题内容
            conversation_id: 对话ID（用于上下文管理）
            model_provider: 模型提供商
            max_references: 最大引用数量
            db: 数据库会话
            **kwargs: 其他参数

        Returns:
            QAResult对象
        """
        try:
            # Debug 入参：记录 question 类型与预览
            try:
                q_preview = str(question)
                if q_preview is None:
                    q_preview = "<None>"
                if len(q_preview) > 300:
                    q_preview = q_preview[:300] + "...<truncated>"
                logger.debug(
                    f"[qa_service.ask_question.debug] workspace_id={workspace_id}, type(question)={type(question)}, question_preview={q_preview}"
                )
            except Exception as _dbg_err:
                logger.warning(f"ask_question 入参调试信息记录失败: {_dbg_err}")
            # 1. 获取工作区上下文
            if db:
                workspace_context = await self.context_service.get_workspace_context(
                    workspace_id=workspace_id, db=db
                )

                # 获取对话上下文（如果有对话ID）
                conversation_context = None
                if conversation_id:
                    conversation_context = await self.context_service.get_conversation_context(
                        conversation_id=conversation_id, db=db
                    )

            # 2. 使用 LlamaIndex 检索相关文档片段
            retriever = LlamaIndexRetriever.get_instance(workspace_id)
            retrieved = await retriever.retrieve(
                query=question,
                top_k=max_references * 2,
                use_hybrid=True,
                use_compression=True
            )
            # 统一结构为下游兼容格式
            relevant_chunks = []
            for item in retrieved:
                relevant_chunks.append({
                    "content": item.get("content", ""),
                    "metadata": item.get("metadata", {}),
                    "similarity": float(item.get("score", 0.0))
                })

            if not relevant_chunks:
                return QAResult(
                    answer="抱歉，我在知识库中没有找到相关信息来回答您的问题。",
                    references=[],
                    sources=[],
                    confidence=0.0,
                    metadata={"reason": "no_relevant_docs"}
                )

            # 3. 筛选和排序引用
            filtered_references = self._filter_and_rank_references(
                question, relevant_chunks, max_references
            )

            # 4. 构建增强的上下文提示
            context_prompt = self._build_enhanced_context_prompt(
                question,
                filtered_references,
                workspace_context if db else None,
                conversation_context
            )

            # 5. 调用大模型生成答案
            messages = [
                {
                    "role": "system",
                    "content": self._get_enhanced_system_prompt(workspace_context if db else None)
                },
                {
                    "role": "user",
                    "content": context_prompt
                }
            ]

            llm_response = await self.llm_service.chat(
                messages=messages,
                provider=model_provider,
                **kwargs
            )

            # 5. 提取引用信息
            references_info = self._extract_references_from_answer(
                llm_response["content"], filtered_references
            )

            # 6. 计算置信度
            confidence = self._calculate_confidence(
                question, llm_response["content"], filtered_references
            )

            return QAResult(
                answer=llm_response["content"],
                references=references_info,
                sources=filtered_references,
                confidence=confidence,
                metadata={
                    "model": llm_response.get("model"),
                    "usage": llm_response.get("usage"),
                    "retrieved_chunks": len(relevant_chunks),
                    "used_references": len(filtered_references)
                }
            )

        except Exception as e:
            logger.error(f"问答失败: {str(e)}")
            raise

    def _filter_and_rank_references(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
        max_refs: int
    ) -> List[Dict[str, Any]]:
        """筛选和排序引用"""
        # 简单的基于相似度的排序
        sorted_chunks = sorted(chunks, key=lambda x: x['similarity'], reverse=True)

        # 去重（基于文档ID）
        seen_docs = set()
        filtered = []

        for chunk in sorted_chunks:
            doc_id = chunk['metadata'].get('document_id')
            if doc_id and doc_id not in seen_docs:
                filtered.append(chunk)
                seen_docs.add(doc_id)
                if len(filtered) >= max_refs:
                    break

        return filtered

    def _build_context_prompt(
        self,
        question: str,
        references: List[Dict[str, Any]]
    ) -> str:
        """构建上下文提示"""
        context_parts = []

        # 添加引用文档内容
        for i, ref in enumerate(references, 1):
            context_parts.append(f"文档片段 {i}:\n{ref['content']}")

        # 构建完整提示
        context = "\n\n".join(context_parts)

        prompt = f"""基于以下文档内容，请回答用户的问题。如果文档中没有相关信息，请说明无法回答。

文档内容：
{context}

用户问题：{question}

请提供准确、详细的回答。如果答案基于特定文档片段，请在回答中引用该片段。"""

        return prompt

    def _build_enhanced_context_prompt(
        self,
        question: str,
        references: List[Dict[str, Any]],
        workspace_context = None,
        conversation_context = None
    ) -> str:
        """构建增强的上下文提示"""
        context_parts = []

        # 添加工作区上下文（如果有）
        if workspace_context:
            context_parts.append(f"工作区信息: {workspace_context.workspace_name}")

            if workspace_context.settings:
                context_parts.append(f"工作区设置: {workspace_context.settings}")

            # 添加活跃文档信息
            if workspace_context.active_documents:
                active_docs = [f"- {doc['filename']}" for doc in workspace_context.active_documents[:3]]
                context_parts.append(f"最近活跃文档: {'; '.join(active_docs)}")

        # 添加对话上下文（如果有）
        if conversation_context and conversation_context.get('recent_messages'):
            recent_msgs = conversation_context['recent_messages']
            if recent_msgs:
                context_parts.append("对话历史:")
                for msg in recent_msgs[-2:]:  # 只包含最近2条消息
                    role = "用户" if msg['role'] == 'user' else "助手"
                    context_parts.append(f"{role}: {msg['content'][:100]}...")

        # 添加引用文档内容
        if references:
            context_parts.append("相关文档片段:")
            for i, ref in enumerate(references, 1):
                context_parts.append(f"片段 {i}: {ref['content']}")

        # 构建完整提示
        context = "\n\n".join(context_parts)

        prompt = f"""基于以下上下文信息，请回答用户的问题。

上下文信息：
{context}

用户问题：{question}

请提供准确、详细的回答。如果答案基于特定文档片段，请在回答中引用该片段。如果没有足够信息，请说明无法回答。"""

        return prompt

    def _get_enhanced_system_prompt(self, workspace_context = None) -> str:
        """获取增强的系统提示词"""
        base_prompt = """你是一个专业的AI助手，负责回答用户关于文档和工作区的问题。

你的能力包括：
1. 基于上传的文档内容回答问题
2. 引用具体的文档片段来支持答案
3. 理解工作区的上下文和设置
4. 提供准确、详细且有帮助的回答

回答指南：
- 始终基于提供的文档内容和上下文信息
- 如果文档中有相关信息，要明确引用来源
- 如果没有足够信息，要诚实说明无法回答
- 回答要自然、专业且易于理解
- 考虑用户的具体需求和工作区上下文

请记住，你只能使用提供的上下文信息，不能添加外部知识。"""

        if workspace_context:
            workspace_info = f"当前工作区：{workspace_context.workspace_name}"
            if workspace_context.settings:
                workspace_info += f"，设置：{workspace_context.settings}"
            base_prompt = base_prompt.replace(
                "你是一个专业的AI助手，负责回答用户关于文档和工作区的问题。",
                f"你是一个专业的AI助手，负责回答用户关于文档和工作区的问题。\n{workspace_info}"
            )

        return base_prompt

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是一个专业的文档问答助手。请基于提供的文档内容回答用户问题。

要求：
1. 回答要准确、简洁、有条理
2. 如果文档中有相关信息，要引用具体内容
3. 如果文档中没有相关信息，要诚实说明
4. 回答要自然流畅，避免机械化表达
5. 保持专业性和客观性

请记住，你的回答应该基于提供的文档内容，不要添加外部知识。"""

    def _extract_references_from_answer(
        self,
        answer: str,
        references: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """从答案中提取引用信息"""
        # 简单的引用提取逻辑
        # 在实际应用中可能需要更复杂的NLP处理
        extracted_refs = []

        for ref in references:
            # 检查答案中是否提到了引用内容的关键词
            ref_content = ref['content'][:100].lower()  # 取前100个字符
            if ref_content in answer.lower():
                extracted_refs.append({
                    'chunk_index': ref['metadata'].get('chunk_index'),
                    'document_id': ref['metadata'].get('document_id'),
                    'content_preview': ref['content'][:200] + "...",
                    'similarity': ref['similarity']
                })

        return extracted_refs

    def _calculate_confidence(
        self,
        question: str,
        answer: str,
        references: List[Dict[str, Any]]
    ) -> float:
        """计算答案置信度"""
        if not references:
            return 0.0

        # 基于引用相似度和数量计算置信度
        avg_similarity = sum(ref['similarity'] for ref in references) / len(references)
        reference_count = len(references)

        # 简单的置信度计算公式
        confidence = min(0.9, avg_similarity * 0.8 + min(reference_count / 5, 1.0) * 0.2)

        return round(confidence, 2)

    async def ask_streaming(
        self,
        workspace_id: str,
        question: str,
        conversation_id: str = None,
        model_provider: str = "openai",
        db: AsyncSession = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式问答（用于实时回答）

        Yields:
            包含答案片段和元数据的字典
        """
        try:
            # 1. 获取工作区上下文
            if db:
                workspace_context = await self.context_service.get_workspace_context(
                    workspace_id=workspace_id, db=db
                )

                # 获取对话上下文（如果有对话ID）
                conversation_context = None
                if conversation_id:
                    conversation_context = await self.context_service.get_conversation_context(
                        conversation_id=conversation_id, db=db
                    )

            # 2. 检索相关文档
            relevant_chunks = await self.vector_service.search_similar(
                workspace_id=workspace_id,
                query=question,
                top_k=5,
                threshold=0.5
            )

            if not relevant_chunks:
                yield {
                    "type": "answer",
                    "content": "抱歉，我在知识库中没有找到相关信息来回答您的问题。",
                    "done": True
                }
                return

            # 3. 构建增强的上下文
            context_prompt = self._build_enhanced_context_prompt(
                question,
                relevant_chunks,
                workspace_context if db else None,
                conversation_context
            )

            # 4. 调用流式大模型API
            messages = [
                {"role": "system", "content": self._get_enhanced_system_prompt(workspace_context if db else None)},
                {"role": "user", "content": context_prompt}
            ]

            async for chunk in self.llm_service.chat(
                messages=messages,
                provider=model_provider,
                stream=True,
                **kwargs
            ):
                yield {
                    "type": "answer",
                    "content": chunk,
                    "done": False
                }

            # 发送完成信号
            yield {
                "type": "answer",
                "content": "",
                "done": True,
                "references": [
                    {
                        "chunk_index": ref['metadata'].get('chunk_index'),
                        "document_id": ref['metadata'].get('document_id'),
                        "similarity": ref['similarity']
                    }
                    for ref in relevant_chunks[:3]  # 只返回前3个引用
                ]
            }

        except Exception as e:
            logger.error(f"流式问答失败: {str(e)}")
            yield {
                "type": "error",
                "content": f"问答过程中出现错误: {str(e)}",
                "done": True
            }
