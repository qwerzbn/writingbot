# -*- coding: utf-8 -*-
"""
Retriever Component
====================

Retrieves relevant documents from a vector store.
"""

from typing import Any


class VectorRetriever:
    """Retrieves documents using vector similarity search."""

    def __init__(self, vector_store: Any, top_k: int = 5):
        """
        Args:
            vector_store: VectorStore instance
            top_k: Number of results to retrieve
        """
        self.vector_store = vector_store
        self.top_k = top_k

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict]:
        """
        Retrieve relevant documents.

        Args:
            query: Search query
            top_k: Override default top_k

        Returns:
            List of result dicts with 'content', 'metadata', 'score'
        """
        k = top_k or self.top_k
        return self.vector_store.search(query, top_k=k)
