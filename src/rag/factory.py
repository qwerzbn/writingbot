# -*- coding: utf-8 -*-
"""
RAG Pipeline Factory
=====================

Creates RAG pipeline instances based on configuration.
"""

from typing import Any


def create_pipeline(
    pipeline_type: str,
    vector_store: Any,
    **kwargs,
):
    """
    Create a RAG pipeline instance.

    Args:
        pipeline_type: Pipeline type ('naive' or future types)
        vector_store: VectorStore instance
        **kwargs: Additional pipeline configuration

    Returns:
        RAGPipeline instance
    """
    if pipeline_type == "naive":
        from src.rag.pipelines import NaivePipeline
        return NaivePipeline(vector_store=vector_store, **kwargs)
    else:
        raise ValueError(f"Unknown pipeline type: {pipeline_type}. Available: ['naive']")
