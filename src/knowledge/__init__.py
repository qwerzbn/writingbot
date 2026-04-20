"""Lazy knowledge package exports."""

from __future__ import annotations

from typing import Any

__all__ = [
    "KnowledgeBaseManager",
    "VectorStore",
    "KnowledgeAsset",
    "ChartInterpretation",
    "is_chart_query",
    "normalize_ref_label",
]


def __getattr__(name: str) -> Any:
    if name == "KnowledgeBaseManager":
        from src.knowledge.kb_manager import KnowledgeBaseManager

        return KnowledgeBaseManager
    if name == "VectorStore":
        from src.knowledge.vector_store import VectorStore

        return VectorStore
    if name in {"KnowledgeAsset", "ChartInterpretation", "is_chart_query", "normalize_ref_label"}:
        from src.knowledge.assets import (
            ChartInterpretation,
            KnowledgeAsset,
            is_chart_query,
            normalize_ref_label,
        )

        mapping = {
            "KnowledgeAsset": KnowledgeAsset,
            "ChartInterpretation": ChartInterpretation,
            "is_chart_query": is_chart_query,
            "normalize_ref_label": normalize_ref_label,
        }
        return mapping[name]
    raise AttributeError(name)
