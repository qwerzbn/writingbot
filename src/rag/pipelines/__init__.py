# -*- coding: utf-8 -*-
"""
Naive RAG Pipeline
===================

Simple pipeline: retrieve → build context → generate.
This is the default pipeline matching the original RAGEngine behavior.
"""

from typing import Generator

from src.rag.pipeline import RAGPipeline, RAGResult
from src.rag.components.retriever import VectorRetriever
from src.rag.components.context_builder import ContextBuilder
from src.rag.components.generator import LLMGenerator


SYSTEM_PROMPT_TEMPLATE = """你是 WritingBot，一个专业的学术知识助手。

### 你的任务
根据下方【参考上下文】中的信息回答用户的问题。

### 回答规则
1. 基于参考上下文回答，不要编造未提供的信息
2. 如果上下文不足以回答，请明确告知用户
3. 使用清晰的结构化格式回答（标题、列表、重点加粗等）
4. 使用中文回答
5. 不要在回答中提及"上下文"、"参考资料"等元信息，直接回答问题
6. 不要输出来源引用标记，来源信息由系统自动展示

【参考上下文】
{context}
"""


class NaivePipeline(RAGPipeline):
    """
    Naive RAG pipeline: query → retrieve → build context → generate.

    This is the simplest pipeline, equivalent to the original RAGEngine.
    """

    def __init__(
        self,
        vector_store,
        top_k: int = 5,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        max_context_length: int = 4000,
    ):
        super().__init__(name="naive")
        self.retriever = VectorRetriever(vector_store, top_k=top_k)
        self.context_builder = ContextBuilder(max_context_length=max_context_length)
        self.generator = LLMGenerator(temperature=temperature, max_tokens=max_tokens)

    def _build_messages(
        self,
        question: str,
        context: str,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Build messages array for LLM."""
        system_content = SYSTEM_PROMPT_TEMPLATE.format(
            context=context if context else "(知识库中暂无相关文档)"
        )
        messages = [{"role": "system", "content": system_content}]

        if history:
            recent = history[-8:]
            for msg in recent:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": question})
        return messages

    def query(self, question: str, history: list[dict] | None = None, **kwargs) -> RAGResult:
        """Execute naive pipeline (non-streaming)."""
        # 1. Retrieve
        results = self.retriever.retrieve(question)

        # 2. Build context
        context, sources = self.context_builder.build(results)

        # 3. Generate
        messages = self._build_messages(question, context, history)
        answer = self.generator.generate(messages)

        return RAGResult(answer=answer, sources=sources, context=context)

    def query_stream(
        self, question: str, history: list[dict] | None = None, **kwargs
    ) -> tuple[Generator[str, None, None], dict]:
        """Execute naive pipeline with streaming."""
        # 1. Retrieve
        results = self.retriever.retrieve(question)

        # 2. Build context
        context, sources = self.context_builder.build(results)

        # 3. Generate (streaming)
        messages = self._build_messages(question, context, history)
        stream = self.generator.generate_stream(messages)

        metadata = {"sources": sources, "context": context}
        return stream, metadata
