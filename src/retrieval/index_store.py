# -*- coding: utf-8 -*-
"""Local BM25 and concept-graph index storage."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.retrieval.common import stable_doc_id, tokenize


@dataclass
class IndexedDoc:
    doc_id: str
    content: str
    metadata: dict[str, Any]
    tokens: list[str]


class KnowledgeIndexStore:
    """Manages per-KB local indexes under data/knowledge_bases/<kb_id>/indexes."""

    def __init__(self, base_dir: str | Path = "./data/knowledge_bases"):
        self.base_dir = Path(base_dir)
        self._cache: dict[tuple[str, str], tuple[tuple[int, int], Any]] = {}

    @staticmethod
    def _file_signature(path: Path) -> tuple[int, int] | None:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def _get_cached(self, kind: str, kb_id: str, path: Path) -> Any | None:
        signature = self._file_signature(path)
        if signature is None:
            self._cache.pop((kind, kb_id), None)
            return None
        cached = self._cache.get((kind, kb_id))
        if cached and cached[0] == signature:
            return cached[1]
        return None

    def _set_cached(self, kind: str, kb_id: str, path: Path, value: Any) -> Any:
        signature = self._file_signature(path)
        if signature is not None:
            self._cache[(kind, kb_id)] = (signature, value)
        return value

    def _invalidate_cache(self, kb_id: str) -> None:
        for key in [key for key in self._cache if key[1] == kb_id]:
            self._cache.pop(key, None)

    def _index_dir(self, kb_id: str, ensure: bool = False) -> Path:
        path = self.base_dir / kb_id / "indexes"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _docs_file(self, kb_id: str) -> Path:
        return self._index_dir(kb_id, ensure=True) / "docs.jsonl"

    def _bm25_stats_file(self, kb_id: str) -> Path:
        return self._index_dir(kb_id, ensure=True) / "bm25_stats.json"

    def _graph_file(self, kb_id: str) -> Path:
        return self._index_dir(kb_id, ensure=True) / "concept_graph.json"

    def load_docs(self, kb_id: str) -> list[IndexedDoc]:
        docs_file = self._docs_file(kb_id)
        if not docs_file.exists():
            self._cache.pop(("docs", kb_id), None)
            return []
        cached = self._get_cached("docs", kb_id, docs_file)
        if cached is not None:
            return cached
        docs: list[IndexedDoc] = []
        with open(docs_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                docs.append(
                    IndexedDoc(
                        doc_id=item["doc_id"],
                        content=item.get("content", ""),
                        metadata=item.get("metadata", {}),
                        tokens=item.get("tokens", []),
                    )
                )
        return self._set_cached("docs", kb_id, docs_file, docs)

    def upsert_chunks(self, kb_id: str, chunks: list[dict[str, Any]]) -> int:
        existing_docs = {doc.doc_id: doc for doc in self.load_docs(kb_id)}
        changed = 0
        for chunk in chunks:
            content = chunk.get("content", "")
            metadata = chunk.get("metadata", {}) or {}
            doc_id = stable_doc_id(content, metadata)
            tokens = tokenize(content)
            if not tokens:
                continue
            existing_docs[doc_id] = IndexedDoc(
                doc_id=doc_id,
                content=content,
                metadata=metadata,
                tokens=tokens,
            )
            changed += 1

        docs = list(existing_docs.values())
        docs_file = self._docs_file(kb_id)
        with open(docs_file, "w", encoding="utf-8") as f:
            for doc in docs:
                f.write(
                    json.dumps(
                        {
                            "doc_id": doc.doc_id,
                            "content": doc.content,
                            "metadata": doc.metadata,
                            "tokens": doc.tokens,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        self._rebuild_bm25_stats(kb_id, docs)
        self._rebuild_concept_graph(kb_id, docs)
        self._invalidate_cache(kb_id)
        return changed

    def delete_by_file_id(self, kb_id: str, file_id: str) -> int:
        if not file_id:
            return 0
        docs = self.load_docs(kb_id)
        kept = [doc for doc in docs if str(doc.metadata.get("file_id", "")) != str(file_id)]
        removed = len(docs) - len(kept)
        docs_file = self._docs_file(kb_id)
        with open(docs_file, "w", encoding="utf-8") as f:
            for doc in kept:
                f.write(
                    json.dumps(
                        {
                            "doc_id": doc.doc_id,
                            "content": doc.content,
                            "metadata": doc.metadata,
                            "tokens": doc.tokens,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        self._rebuild_bm25_stats(kb_id, kept)
        self._rebuild_concept_graph(kb_id, kept)
        self._invalidate_cache(kb_id)
        return removed

    def rebuild_from_chunks(self, kb_id: str, chunks: list[dict[str, Any]]) -> int:
        docs: dict[str, IndexedDoc] = {}
        for chunk in chunks:
            content = str(chunk.get("content", ""))
            metadata = dict(chunk.get("metadata", {}) or {})
            tokens = tokenize(content)
            if not tokens:
                continue
            doc_id = stable_doc_id(content, metadata)
            docs[doc_id] = IndexedDoc(
                doc_id=doc_id,
                content=content,
                metadata=metadata,
                tokens=tokens,
            )
        docs_file = self._docs_file(kb_id)
        with open(docs_file, "w", encoding="utf-8") as f:
            for doc in docs.values():
                f.write(
                    json.dumps(
                        {
                            "doc_id": doc.doc_id,
                            "content": doc.content,
                            "metadata": doc.metadata,
                            "tokens": doc.tokens,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        doc_rows = list(docs.values())
        self._rebuild_bm25_stats(kb_id, doc_rows)
        self._rebuild_concept_graph(kb_id, doc_rows)
        self._invalidate_cache(kb_id)
        return len(doc_rows)

    def _rebuild_bm25_stats(self, kb_id: str, docs: list[IndexedDoc]) -> None:
        df: dict[str, int] = defaultdict(int)
        doc_lens: dict[str, int] = {}
        for doc in docs:
            unique = set(doc.tokens)
            for token in unique:
                df[token] += 1
            doc_lens[doc.doc_id] = len(doc.tokens)

        avgdl = (sum(doc_lens.values()) / len(doc_lens)) if doc_lens else 0.0
        payload = {
            "doc_count": len(docs),
            "doc_lens": doc_lens,
            "avgdl": avgdl,
            "df": dict(df),
        }
        with open(self._bm25_stats_file(kb_id), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def load_bm25_stats(self, kb_id: str) -> dict[str, Any]:
        stats_file = self._bm25_stats_file(kb_id)
        if not stats_file.exists():
            self._cache.pop(("bm25", kb_id), None)
            return {"doc_count": 0, "doc_lens": {}, "avgdl": 0.0, "df": {}}
        cached = self._get_cached("bm25", kb_id, stats_file)
        if cached is not None:
            return cached
        with open(stats_file, encoding="utf-8") as f:
            return self._set_cached("bm25", kb_id, stats_file, json.load(f))

    def _rebuild_concept_graph(self, kb_id: str, docs: list[IndexedDoc]) -> None:
        edges: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        concept_docs: dict[str, set[str]] = defaultdict(set)
        for doc in docs:
            concepts = [t for t in set(doc.tokens) if len(t) >= 2]
            for concept in concepts:
                concept_docs[concept].add(doc.doc_id)
            for i, left in enumerate(concepts):
                for right in concepts[i + 1 : i + 24]:
                    edges[left][right] += 1
                    edges[right][left] += 1

        payload = {
            "edges": {k: dict(v) for k, v in edges.items()},
            "concept_docs": {k: sorted(v) for k, v in concept_docs.items()},
        }
        with open(self._graph_file(kb_id), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def load_graph(self, kb_id: str) -> dict[str, Any]:
        graph_file = self._graph_file(kb_id)
        if not graph_file.exists():
            self._cache.pop(("graph", kb_id), None)
            return {"edges": {}, "concept_docs": {}}
        cached = self._get_cached("graph", kb_id, graph_file)
        if cached is not None:
            return cached
        with open(graph_file, encoding="utf-8") as f:
            return self._set_cached("graph", kb_id, graph_file, json.load(f))
