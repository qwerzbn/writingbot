# -*- coding: utf-8 -*-
"""
Reranker Component
===================

Re-ranks retrieved documents using cross-encoder models for more precise
relevance scoring. Supports DashScope API and local cross-encoder models.

Two-stage retrieval:
1. Coarse retrieval (vector similarity) → top-20 candidates
2. Fine reranking (cross-encoder) → top-3 most relevant
"""

import os
from typing import List, Dict, Any, Optional


class Reranker:
    """
    Re-ranks documents using cross-encoder deep semantic matching.
    
    Supported providers:
    - dashscope: Uses DashScope gte-rerank API (recommended, zero deployment)
    - local: Uses sentence-transformers CrossEncoder (offline, needs ~1GB model)
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.provider = provider or os.getenv("RERANKER_PROVIDER", "local")
        self.model = model or os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
        self.api_key = api_key or os.getenv("RERANKER_API_KEY") or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("RERANKER_BASE_URL") or os.getenv("LLM_BASE_URL")

        self._cross_encoder = None  # Lazy-loaded for local provider

        print(f"Reranker initialized: provider={self.provider}, model={self.model}")

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Re-rank retrieved documents by relevance to the query.

        Args:
            query: User question
            documents: List of retrieval results with 'content' and 'metadata'
            top_k: Number of top results to return after reranking

        Returns:
            Top-k documents sorted by reranker score (most relevant first)
        """
        if not documents:
            return []

        if len(documents) <= top_k:
            # Not enough documents to rerank meaningfully
            return documents

        if self.provider == "dashscope":
            return self._rerank_dashscope(query, documents, top_k)
        elif self.provider == "local":
            return self._rerank_local(query, documents, top_k)
        else:
            raise ValueError(f"Unknown reranker provider: {self.provider}")

    def _rerank_dashscope(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Rerank using DashScope API (OpenAI-compatible)."""
        from openai import OpenAI

        if not self.api_key:
            raise ValueError("DashScope reranker requires LLM_API_KEY in .env")

        # DashScope uses a custom rerank endpoint via the chat completions workaround
        # We'll use the dedicated rerank approach via HTTP
        import requests

        # DashScope rerank API
        base = self.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        # Strip /v1 suffix for the rerank endpoint
        if base.endswith("/v1"):
            base = base[:-3]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Prepare documents for the API
        doc_texts = [doc.get("content", doc.get("text", "")) for doc in documents]

        payload = {
            "model": self.model,
            "input": {
                "query": query,
                "documents": doc_texts,
            },
            "parameters": {
                "top_n": top_k,
                "return_documents": False,
            },
        }

        try:
            resp = requests.post(
                f"{base}/api/v1/services/rerank/text-reranking/text-reranking",
                headers=headers,
                json=payload,
                timeout=30,
            )

            if resp.status_code != 200:
                print(f"[Reranker] DashScope API error: {resp.status_code} {resp.text}")
                # Fallback: return original top-k
                return documents[:top_k]

            data = resp.json()
            results = data.get("output", {}).get("results", [])

            # Map back to original documents using index
            reranked = []
            for item in results:
                idx = item.get("index", 0)
                if idx < len(documents):
                    doc = documents[idx].copy()
                    doc["rerank_score"] = item.get("relevance_score", 0)
                    reranked.append(doc)

            print(f"[Reranker] DashScope reranked {len(documents)} → {len(reranked)} docs")
            for i, doc in enumerate(reranked):
                source = doc.get("metadata", {}).get("source", "?")
                score = doc.get("rerank_score", 0)
                print(f"  [{i+1}] score={score:.4f} source={source}")

            return reranked

        except Exception as e:
            print(f"[Reranker] DashScope error: {e}, falling back to top-k")
            return documents[:top_k]

    def _rerank_local(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Rerank using local CrossEncoder model."""
        if self._cross_encoder is None:
            from sentence_transformers import CrossEncoder
            print(f"[Reranker] Loading local model: {self.model}")
            self._cross_encoder = CrossEncoder(self.model)

        # Prepare query-document pairs
        doc_texts = [doc.get("content", doc.get("text", "")) for doc in documents]
        pairs = [(query, text) for text in doc_texts]

        # Score all pairs
        scores = self._cross_encoder.predict(pairs)

        # Attach scores and sort
        scored_docs = []
        for i, (doc, score) in enumerate(zip(documents, scores)):
            doc_copy = doc.copy()
            doc_copy["rerank_score"] = float(score)
            scored_docs.append(doc_copy)

        scored_docs.sort(key=lambda x: x["rerank_score"], reverse=True)

        reranked = scored_docs[:top_k]

        print(f"[Reranker] Local reranked {len(documents)} → {len(reranked)} docs")
        for i, doc in enumerate(reranked):
            source = doc.get("metadata", {}).get("source", "?")
            score = doc.get("rerank_score", 0)
            print(f"  [{i+1}] score={score:.4f} source={source}")

        return reranked
