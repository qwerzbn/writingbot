# -*- coding: utf-8 -*-
"""Hybrid retrieval pipeline: Vector + BM25 + Concept Graph."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from src.rag.components.reranker import Reranker
from src.retrieval.common import estimate_tokens, safe_norm, stable_doc_id, tokenize
from src.retrieval.index_store import IndexedDoc, KnowledgeIndexStore


class VectorRetriever:
    def __init__(self, top_k: int = 12):
        self.top_k = top_k

    def retrieve(self, vector_store: Any, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        if not vector_store or not query.strip():
            return []
        rows = vector_store.search(query, top_k=top_k or self.top_k)
        results: list[dict[str, Any]] = []
        for row in rows:
            content = row.get("content", "")
            metadata = row.get("metadata", {}) or {}
            results.append(
                {
                    "doc_id": stable_doc_id(content, metadata),
                    "content": content,
                    "metadata": metadata,
                    "vector_score": float(row.get("score", 0.0)),
                }
            )
        return results


class BM25Retriever:
    def __init__(self, index_store: KnowledgeIndexStore, top_k: int = 12, k1: float = 1.5, b: float = 0.75):
        self.index_store = index_store
        self.top_k = top_k
        self.k1 = k1
        self.b = b

    def retrieve(self, kb_id: str, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        docs = self.index_store.load_docs(kb_id)
        stats = self.index_store.load_bm25_stats(kb_id)
        if not docs:
            return []

        query_terms = tokenize(query)
        if not query_terms:
            return []

        n_docs = max(1, int(stats.get("doc_count", len(docs))))
        avgdl = float(stats.get("avgdl", 0.0) or 1.0)
        df = stats.get("df", {})
        doc_lens = stats.get("doc_lens", {})

        scored: list[tuple[IndexedDoc, float]] = []
        for doc in docs:
            tf: dict[str, int] = defaultdict(int)
            for tok in doc.tokens:
                tf[tok] += 1
            dl = float(doc_lens.get(doc.doc_id, len(doc.tokens)) or len(doc.tokens) or 1)

            score = 0.0
            for term in query_terms:
                if term not in tf:
                    continue
                term_df = float(df.get(term, 0))
                idf = math.log(1 + (n_docs - term_df + 0.5) / (term_df + 0.5))
                freq = tf[term]
                denom = freq + self.k1 * (1 - self.b + self.b * dl / avgdl)
                score += idf * ((freq * (self.k1 + 1)) / max(1e-8, denom))

            if score > 0:
                scored.append((doc, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        k = top_k or self.top_k
        return [
            {
                "doc_id": doc.doc_id,
                "content": doc.content,
                "metadata": doc.metadata,
                "bm25_score": score,
            }
            for doc, score in scored[:k]
        ]


class GraphRetriever:
    def __init__(self, index_store: KnowledgeIndexStore, top_k: int = 12):
        self.index_store = index_store
        self.top_k = top_k

    def retrieve(self, kb_id: str, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        graph = self.index_store.load_graph(kb_id)
        docs = {doc.doc_id: doc for doc in self.index_store.load_docs(kb_id)}
        edges = graph.get("edges", {})
        concept_docs = graph.get("concept_docs", {})
        if not docs or not concept_docs:
            return []

        terms = tokenize(query)
        if not terms:
            return []

        score_by_doc: dict[str, float] = defaultdict(float)
        for term in terms:
            for doc_id in concept_docs.get(term, []):
                score_by_doc[doc_id] += 1.0

            # Expand one-hop concepts for soft matches.
            neighbors = edges.get(term, {})
            for neighbor, w in sorted(neighbors.items(), key=lambda x: x[1], reverse=True)[:10]:
                for doc_id in concept_docs.get(neighbor, []):
                    score_by_doc[doc_id] += min(1.0, float(w) / 10.0)

        ranked = sorted(score_by_doc.items(), key=lambda x: x[1], reverse=True)
        k = top_k or self.top_k
        results: list[dict[str, Any]] = []
        for doc_id, score in ranked[:k]:
            doc = docs.get(doc_id)
            if not doc:
                continue
            results.append(
                {
                    "doc_id": doc_id,
                    "content": doc.content,
                    "metadata": doc.metadata,
                    "graph_score": score,
                }
            )
        return results


class EvidenceJudge:
    """Lightweight evidence quality judge."""

    def judge(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        judged: list[dict[str, Any]] = []
        for item in candidates:
            content = item.get("content", "")
            metadata = item.get("metadata", {}) or {}
            fusion_score = float(item.get("fusion_score", 0.0))
            has_source = bool(metadata.get("source"))
            has_page = metadata.get("page") is not None
            length_ok = len(content) >= 80

            relevance = min(1.0, max(0.0, fusion_score))
            risk = 0.2
            if not has_source:
                risk += 0.25
            if not has_page:
                risk += 0.15
            if not length_ok:
                risk += 0.25
            if relevance < 0.35:
                risk += 0.2

            row = {
                **item,
                "relevance": round(relevance, 4),
                "factual_risk": round(min(1.0, risk), 4),
                "judge_keep": relevance >= 0.35 and risk <= 0.7,
            }
            judged.append(row)

        judged.sort(key=lambda x: (x["judge_keep"], x["relevance"]), reverse=True)
        return judged


class HybridRetrievalService:
    """Composable retrieval service used by API and orchestrator."""

    def __init__(self, index_store: KnowledgeIndexStore | None = None):
        self.index_store = index_store or KnowledgeIndexStore()
        self.vector = VectorRetriever()
        self.bm25 = BM25Retriever(self.index_store)
        self.graph = GraphRetriever(self.index_store)
        self.reranker = Reranker()
        self.judge = EvidenceJudge()

    def split_sub_questions(self, query: str, max_parts: int = 3) -> list[str]:
        chunks = [q.strip(" -•\n\t") for q in query.replace("？", "?").split("?") if q.strip()]
        if len(chunks) <= 1:
            return [query.strip()]
        return chunks[:max_parts]

    def retrieve(
        self,
        kb_id: str,
        vector_store: Any,
        query: str,
        top_k: int = 8,
        weights: tuple[float, float, float] = (0.5, 0.3, 0.2),
    ) -> dict[str, Any]:
        vector_rows = self.vector.retrieve(vector_store, query, top_k=max(top_k * 2, 10))
        # Bootstrap local indexes lazily for existing KBs created before hybrid retrieval.
        if not self.index_store.load_docs(kb_id) and vector_rows:
            bootstrap_chunks = [
                {
                    "content": row.get("content", ""),
                    "metadata": row.get("metadata", {}) or {},
                }
                for row in vector_rows
            ]
            self.index_store.upsert_chunks(kb_id, bootstrap_chunks)
        bm25_rows = self.bm25.retrieve(kb_id, query, top_k=max(top_k * 2, 10))
        graph_rows = self.graph.retrieve(kb_id, query, top_k=max(top_k * 2, 10))

        fused = self._fuse_rrf(vector_rows, bm25_rows, graph_rows, weights=weights, top_k=max(top_k * 3, 24))
        reranked = self._rerank(query, fused, top_k=max(top_k * 2, 10))
        judged = self.judge.judge(reranked)
        kept = [r for r in judged if r.get("judge_keep")][:top_k]

        context, sources = self.build_context(kept, token_budget=6000)

        return {
            "query": query,
            "recalls": {
                "vector": vector_rows,
                "bm25": bm25_rows,
                "graph": graph_rows,
            },
            "fusion": fused,
            "rerank": reranked,
            "judge": judged,
            "context_window": {
                "token_budget": 6000,
                "used_tokens": estimate_tokens(context),
                "context": context,
            },
            "sources": sources,
            "weights": {
                "vector": weights[0],
                "bm25": weights[1],
                "graph": weights[2],
            },
        }

    def retrieve_by_sub_questions(
        self,
        kb_id: str,
        vector_store: Any,
        query: str,
        token_budget: int = 6000,
    ) -> dict[str, Any]:
        sub_questions = self.split_sub_questions(query)
        bucket_rows: list[dict[str, Any]] = []
        all_kept: list[dict[str, Any]] = []
        for sq in sub_questions:
            row = self.retrieve(kb_id=kb_id, vector_store=vector_store, query=sq, top_k=6)
            kept = [r for r in row["judge"] if r.get("judge_keep")][:6]
            bucket_rows.append({"sub_question": sq, "result": row, "kept": kept})
            all_kept.extend(kept)

        dedup: dict[str, dict[str, Any]] = {}
        for item in all_kept:
            dedup[item["doc_id"]] = item

        ranked = sorted(dedup.values(), key=lambda x: x.get("relevance", 0.0), reverse=True)
        context, sources = self.build_context(ranked, token_budget=token_budget)
        return {
            "sub_questions": sub_questions,
            "buckets": bucket_rows,
            "context": context,
            "sources": sources,
        }

    def _fuse_rrf(
        self,
        vector_rows: list[dict[str, Any]],
        bm25_rows: list[dict[str, Any]],
        graph_rows: list[dict[str, Any]],
        weights: tuple[float, float, float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        rrf_k = 60
        rank_map: dict[str, dict[str, int]] = defaultdict(dict)
        rows_map: dict[str, dict[str, Any]] = {}

        for name, rows in (("vector", vector_rows), ("bm25", bm25_rows), ("graph", graph_rows)):
            for rank, row in enumerate(rows, start=1):
                doc_id = row["doc_id"]
                rank_map[doc_id][name] = rank
                rows_map.setdefault(doc_id, row)

        fused: list[dict[str, Any]] = []
        for doc_id, ranks in rank_map.items():
            base = rows_map[doc_id]
            v_score = weights[0] * (1.0 / (rrf_k + ranks.get("vector", 10_000)))
            b_score = weights[1] * (1.0 / (rrf_k + ranks.get("bm25", 10_000)))
            g_score = weights[2] * (1.0 / (rrf_k + ranks.get("graph", 10_000)))
            fusion_score = v_score + b_score + g_score
            fused.append(
                {
                    "doc_id": doc_id,
                    "content": base.get("content", ""),
                    "metadata": base.get("metadata", {}),
                    "fusion_score": fusion_score,
                    "vector_rank": ranks.get("vector"),
                    "bm25_rank": ranks.get("bm25"),
                    "graph_rank": ranks.get("graph"),
                }
            )

        fused.sort(key=lambda x: x["fusion_score"], reverse=True)
        raw_scores = [r["fusion_score"] for r in fused]
        normalized = safe_norm(raw_scores)
        for row, score in zip(fused, normalized):
            row["fusion_score"] = round(score, 6)
        return fused[:top_k]

    def _rerank(self, query: str, rows: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        if not rows:
            return []
        docs = [{"content": r.get("content", ""), "metadata": r.get("metadata", {}), **r} for r in rows]
        try:
            reranked = self.reranker.rerank(query, docs, top_k=top_k)
            normalized = safe_norm([float(x.get("rerank_score", x.get("fusion_score", 0.0))) for x in reranked])
            output: list[dict[str, Any]] = []
            for row, score in zip(reranked, normalized):
                output.append({**row, "rerank_score": round(score, 6)})
            return output
        except Exception:
            # Fallback to fusion score when reranker unavailable.
            rows = sorted(rows, key=lambda x: x.get("fusion_score", 0.0), reverse=True)[:top_k]
            for row in rows:
                row["rerank_score"] = row.get("fusion_score", 0.0)
            return rows

    def build_context(self, rows: list[dict[str, Any]], token_budget: int = 6000) -> tuple[str, list[dict[str, Any]]]:
        used = 0
        parts: list[str] = []
        sources: list[dict[str, Any]] = []
        for i, row in enumerate(rows, start=1):
            content = row.get("content", "")
            meta = row.get("metadata", {}) or {}
            chunk_tokens = estimate_tokens(content)
            if used + chunk_tokens > token_budget:
                break
            used += chunk_tokens
            parts.append(f"[{i}] {content}")
            sources.append(
                {
                    "id": row.get("doc_id"),
                    "source": meta.get("source", "Unknown"),
                    "page": meta.get("page", "?"),
                    "file_id": meta.get("file_id"),
                    "paper_id": meta.get("paper_id") or meta.get("file_id") or row.get("doc_id"),
                    "title": meta.get("title") or meta.get("source", "Unknown"),
                    "authors": meta.get("authors", []),
                    "year": meta.get("year"),
                    "venue": meta.get("venue"),
                    "doi": meta.get("doi"),
                    "section": meta.get("section"),
                    "chunk_type": meta.get("chunk_type") or meta.get("type"),
                    "content": content[:220],
                    "score": row.get("relevance", row.get("rerank_score", row.get("fusion_score", 0.0))),
                    "relevance": row.get("relevance", 0.0),
                    "factual_risk": row.get("factual_risk", 0.0),
                }
            )
        return "\n\n".join(parts), sources
