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


SYSTEM_PROMPT_TEMPLATE = """你是一个智能知识库助手 WritingBot。

你的任务是根据提供的上下文回答用户的问题。

### 核心原则
1. **优先使用上下文**：如果提供的【参考上下文】包含回答问题所需的信息，请主要依据上下文回答，并引用来源。
2. **灵活应对**：如果【参考上下文】为空或与问题完全无关（例如用户只是打招呼、问你是谁、或询问通用知识），请**忽略上下文**，利用你自己的知识进行自然、流畅的对话。
3. **诚实原则**：如果知识库中没有相关信息，且问题是关于特定私有知识的，请明确告知用户知识库中未找到相关内容。

### 回复格式
- 使用中文回答。
- 引用来源格式：[来源: 文件名, 第X页]。
- 保持语气专业、乐于助人。

---
【参考上下文】开始：
{context}
【参考上下文】结束
---

请根据以上原则回答用户的问题。"""


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
            context=context if context else "(知识库中暂无文档)"
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
