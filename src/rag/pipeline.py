# -*- coding: utf-8 -*-
"""
RAG Pipeline Base
==================

Abstract base class for RAG pipelines.
Pipelines orchestrate retrieval and generation components.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generator


@dataclass
class RAGResult:
    """Result of a RAG pipeline execution."""
    answer: str = ""
    sources: list[dict] = field(default_factory=list)
    context: str = ""
    metadata: dict = field(default_factory=dict)


class RAGPipeline(ABC):
    """
    Abstract base class for RAG pipelines.

    A pipeline defines the full flow from query to answer:
    query → [rewrite] → retrieve → [rerank] → generate
    """

    def __init__(self, name: str = "base"):
        self.name = name

    @abstractmethod
    def query(self, question: str, **kwargs) -> RAGResult:
        """
        Execute the pipeline (non-streaming).

        Args:
            question: User query
            **kwargs: Additional arguments

        Returns:
            RAGResult with answer, sources, and context
        """

    @abstractmethod
    def query_stream(self, question: str, **kwargs) -> tuple[Generator[str, None, None], dict]:
        """
        Execute the pipeline with streaming.

        Args:
            question: User query
            **kwargs: Additional arguments

        Returns:
            Tuple of (text chunk generator, metadata dict with sources)
        """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
