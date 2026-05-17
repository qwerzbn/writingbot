# -*- coding: utf-8 -*-
"""Document reranking for retrieval pipelines."""

from __future__ import annotations

import os
from typing import Any


class Reranker:
    """Re-rank retrieved documents using an external, local, or disabled provider."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.provider = (provider or os.getenv("RERANKER_PROVIDER", "none")).strip().lower()
        self.model = model or os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
        self.api_key = api_key or os.getenv("RERANKER_API_KEY") or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("RERANKER_BASE_URL") or os.getenv("LLM_BASE_URL")
        self._cross_encoder = None

    def rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        if not documents:
            return []
        if len(documents) <= top_k or self.provider in {"", "none", "disabled", "off"}:
            return documents[:top_k]
        if self.provider == "dashscope":
            return self._rerank_dashscope(query, documents, top_k)
        if self.provider == "local":
            return self._rerank_local(query, documents, top_k)
        return documents[:top_k]

    def _rerank_dashscope(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            return documents[:top_k]

        import requests

        base = self.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if base.endswith("/v1"):
            base = base[:-3]

        payload = {
            "model": self.model,
            "input": {
                "query": query,
                "documents": [doc.get("content", doc.get("text", "")) for doc in documents],
            },
            "parameters": {"top_n": top_k, "return_documents": False},
        }
        try:
            resp = requests.post(
                f"{base}/api/v1/services/rerank/text-reranking/text-reranking",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            if resp.status_code != 200:
                return documents[:top_k]
            results = resp.json().get("output", {}).get("results", [])
            reranked: list[dict[str, Any]] = []
            for item in results:
                idx = int(item.get("index", 0) or 0)
                if idx < len(documents):
                    reranked.append({**documents[idx], "rerank_score": item.get("relevance_score", 0)})
            return reranked or documents[:top_k]
        except Exception:
            return documents[:top_k]

    def _rerank_local(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        try:
            if self._cross_encoder is None:
                from sentence_transformers import CrossEncoder

                self._cross_encoder = CrossEncoder(self.model)
            doc_texts = [doc.get("content", doc.get("text", "")) for doc in documents]
            scores = self._cross_encoder.predict([(query, text) for text in doc_texts])
        except Exception:
            return documents[:top_k]

        scored_docs = []
        for doc, score in zip(documents, scores):
            scored_docs.append({**doc, "rerank_score": float(score)})
        scored_docs.sort(key=lambda item: item["rerank_score"], reverse=True)
        return scored_docs[:top_k]
