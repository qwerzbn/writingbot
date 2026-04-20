from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field

from src.retrieval.common import (
    build_text_evidence_excerpt,
    clean_source_title,
    format_page_locator,
    normalize_source_metadata,
)


class SearchCandidate(BaseModel):
    candidate_id: str
    source_id: str
    source_title: str
    locator: str
    snippet: str
    source_type: str = "paper"
    relevance_score: float = 0.0
    quality_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    candidates: list[SearchCandidate] = Field(default_factory=list)
    error: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)


class SearchBackend:
    def __init__(
        self,
        *,
        kb_id: str | None = None,
        vector_store: Any = None,
        retrieval_service: Any = None,
        availability_error: str | None = None,
        static_responses: dict[str, SearchResponse | list[SearchCandidate]] | None = None,
    ):
        self.kb_id = kb_id
        self.vector_store = vector_store
        self.retrieval_service = retrieval_service
        self.availability_error = availability_error
        self.static_responses = static_responses or {}

    @classmethod
    def disabled(cls, error: str = "search backend unavailable") -> "SearchBackend":
        return cls(availability_error=error)

    @classmethod
    def from_responses(
        cls,
        responses: dict[str, SearchResponse | list[SearchCandidate]],
    ) -> "SearchBackend":
        return cls(static_responses=responses)

    @classmethod
    def from_kb(cls, kb_id: str | None, data_dir: Any = None) -> "SearchBackend":
        if not kb_id:
            return cls.disabled("kb_id is required")
        try:
            from src.shared_capabilities.knowledge.access import get_vector_store

            vector_store = get_vector_store(kb_id, data_dir=data_dir)
            if vector_store is None:
                return cls.disabled(f"KB not found: {kb_id}")
            return cls(kb_id=kb_id, vector_store=vector_store)
        except Exception as exc:
            return cls.disabled(str(exc))

    @classmethod
    def from_vector_store(cls, vector_store: Any, kb_id: str = "legacy-vector-store") -> "SearchBackend":
        if not vector_store:
            return cls.disabled("vector_store is required")
        return cls(kb_id=kb_id, vector_store=vector_store)

    def search(self, query: str, top_k: int) -> SearchResponse:
        query = str(query or "").strip()
        if query in self.static_responses:
            row = self.static_responses[query]
            if isinstance(row, SearchResponse):
                return row
            return SearchResponse(query=query, candidates=list(row))
        if not query:
            return SearchResponse(query=query, error="empty query")
        if self.availability_error:
            return SearchResponse(query=query, error=self.availability_error)
        if not self.kb_id or self.vector_store is None:
            return SearchResponse(query=query, error="backend is missing kb or vector store")

        if self.retrieval_service is None:
            from src.retrieval.hybrid import HybridRetrievalService

            self.retrieval_service = HybridRetrievalService()

        try:
            result = self.retrieval_service.retrieve(
                kb_id=self.kb_id,
                vector_store=self.vector_store,
                query=query,
                top_k=top_k,
            )
        except Exception as exc:
            return SearchResponse(query=query, error=str(exc))

        rows = result.get("judge") or result.get("rerank") or result.get("fusion") or []
        candidates = [self._normalize_row(row, query) for row in rows]
        return SearchResponse(
            query=query,
            candidates=candidates,
            stats={
                "recall_count": sum(
                    len(result.get("recalls", {}).get(name, []) or [])
                    for name in ("vector", "bm25", "graph")
                ),
                "judged_count": len(rows),
            },
        )

    def _normalize_row(self, row: dict[str, Any], query: str) -> SearchCandidate:
        metadata = normalize_source_metadata(row.get("metadata", {}) or {})
        content = str(row.get("content", "") or "")
        source_id = str(
            metadata.get("paper_id")
            or metadata.get("file_id")
            or metadata.get("source")
            or row.get("doc_id")
            or "unknown-source"
        )
        source_title = clean_source_title(metadata.get("title") or metadata.get("source") or source_id)
        locator = format_page_locator(
            metadata.get("page"),
            metadata.get("line_start"),
            metadata.get("line_end"),
        )
        snippet = build_text_evidence_excerpt(content, metadata=metadata, query=query, limit=320) or content[:320]
        source_type = str(metadata.get("asset_type") or metadata.get("chunk_type") or "paper")
        if source_type not in {"paper", "section", "figure", "table"}:
            source_type = "other"
        relevance_score = float(
            row.get("relevance", row.get("rerank_score", row.get("fusion_score", 0.0))) or 0.0
        )
        factual_risk = float(row.get("factual_risk", 0.0) or 0.0)
        quality_score = max(0.0, min(1.0, 1.0 - factual_risk))
        candidate_seed = f"{source_id}|{locator}|{snippet}"
        candidate_id = str(row.get("doc_id") or hashlib.sha1(candidate_seed.encode("utf-8")).hexdigest()[:12])
        return SearchCandidate(
            candidate_id=candidate_id,
            source_id=source_id,
            source_title=source_title,
            locator=locator,
            snippet=snippet,
            source_type=source_type,
            relevance_score=relevance_score,
            quality_score=quality_score,
            metadata=metadata,
        )
