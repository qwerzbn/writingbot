# -*- coding: utf-8 -*-
"""
Reranked RAG Pipeline
======================

Two-stage pipeline: retrieve (top-20) → rerank (top-3) → generate.
Provides significantly better context quality compared to NaivePipeline.
"""

from typing import Generator

from src.rag.pipeline import RAGPipeline, RAGResult
from src.rag.components.retriever import VectorRetriever
from src.rag.components.reranker import Reranker
from src.rag.components.context_builder import ContextBuilder
from src.rag.components.generator import LLMGenerator

from src.rag.pipelines import SYSTEM_PROMPT_TEMPLATE


class RerankedPipeline(RAGPipeline):
    """
    Two-stage RAG pipeline with Reranker.

    Flow: query → retrieve(top-20) → rerank(top-3) → build context → generate

    The Reranker uses cross-encoder models to deeply analyze query-document
    pairs, producing much more accurate relevance scores than vector similarity.
    """

    def __init__(
        self,
        vector_store,
        retrieval_top_k: int = 20,
        rerank_top_k: int = 3,
        reranker_provider: str | None = None,
        reranker_model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        max_context_length: int = 4000,
    ):
        super().__init__(name="reranked")
        self.retriever = VectorRetriever(vector_store, top_k=retrieval_top_k)
        self.reranker = Reranker(provider=reranker_provider, model=reranker_model)
        self.rerank_top_k = rerank_top_k
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
        """Execute reranked pipeline (non-streaming)."""
        # 1. Coarse retrieval (top-20)
        results = self.retriever.retrieve(question)

        # 2. Fine reranking (top-3)
        reranked = self.reranker.rerank(question, results, top_k=self.rerank_top_k)

        # 3. Build context
        context, sources = self.context_builder.build(reranked)

        # 4. Generate
        messages = self._build_messages(question, context, history)
        answer = self.generator.generate(messages)

        return RAGResult(answer=answer, sources=sources, context=context)

    def query_stream(
        self, question: str, history: list[dict] | None = None, **kwargs
    ) -> tuple[Generator[str, None, None], dict]:
        """Execute reranked pipeline with streaming."""
        # 1. Coarse retrieval (top-20)
        results = self.retriever.retrieve(question)

        # 2. Fine reranking (top-3)
        reranked = self.reranker.rerank(question, results, top_k=self.rerank_top_k)

        # 3. Build context
        context, sources = self.context_builder.build(reranked)

        # 4. Generate (streaming)
        messages = self._build_messages(question, context, history)
        stream = self.generator.generate_stream(messages)

        metadata = {"sources": sources, "context": context}
        return stream, metadata
