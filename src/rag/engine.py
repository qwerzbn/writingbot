# -*- coding: utf-8 -*-
"""
RAG Engine - Backward-Compatible Wrapper
==========================================

Wraps the new pipeline-based RAG system with the old RAGEngine API
for backward compatibility. New code should use pipelines directly.

Original monolithic engine has been refactored into:
- src/rag/pipeline.py      — RAGPipeline base class
- src/rag/pipelines/        — Concrete pipelines (NaivePipeline)
- src/rag/components/       — Pluggable components
- src/rag/factory.py        — Pipeline factory
"""

from typing import Dict, Any, Generator, List, Optional

from src.rag.factory import create_pipeline


class RAGEngine:
    """
    Backward-compatible RAG Engine wrapper.

    Uses NaivePipeline internally but provides the same API
    as the original engine for existing code that depends on it.
    """

    def __init__(self,
                 vector_store,
                 llm_api_key: Optional[str] = None,
                 llm_base_url: Optional[str] = None,
                 llm_model: Optional[str] = None):
        """Initialize RAG engine (pipeline-based)."""
        self.vector_store = vector_store

        # Create pipeline
        self._pipeline = create_pipeline("naive", vector_store)

        # History (kept for backward compat, not used by pipeline)
        self.history: List[Dict[str, str]] = []

    def _retrieve_context(self, question: str, top_k: int = 5) -> tuple[str, List[Dict]]:
        """Retrieve context (backward compat)."""
        from src.rag.components.retriever import VectorRetriever
        from src.rag.components.context_builder import ContextBuilder

        retriever = VectorRetriever(self.vector_store, top_k=top_k)
        builder = ContextBuilder()

        results = retriever.retrieve(question)
        return builder.build(results)

    def query(self,
              question: str,
              top_k: int = 5,
              use_history: bool = True) -> Dict[str, Any]:
        """Non-streaming query."""
        history = self.history if use_history else None
        result = self._pipeline.query(question, history=history)

        if use_history:
            self.history.append({"role": "user", "content": question})
            self.history.append({"role": "assistant", "content": result.answer})

        return {
            "answer": result.answer,
            "sources": result.sources,
            "context": result.context,
        }

    def query_stream(self,
                     question: str,
                     top_k: int = 5,
                     use_history: bool = True) -> Generator[str, None, Dict[str, Any]]:
        """Streaming query - yields text chunks."""
        history = self.history if use_history else None
        stream, metadata = self._pipeline.query_stream(question, history=history)

        full_response = ""
        for chunk in stream:
            full_response += chunk
            yield chunk

        if use_history:
            self.history.append({"role": "user", "content": question})
            self.history.append({"role": "assistant", "content": full_response})

        return {"sources": metadata.get("sources", []), "context": metadata.get("context", "")}

    def clear_history(self):
        """Clear conversation history."""
        self.history = []

    def get_history(self) -> List[Dict[str, str]]:
        """Get conversation history."""
        return self.history.copy()
