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
            return []
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
        return docs

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
        return changed

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
            return {"doc_count": 0, "doc_lens": {}, "avgdl": 0.0, "df": {}}
        with open(stats_file, encoding="utf-8") as f:
            return json.load(f)

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
            return {"edges": {}, "concept_docs": {}}
        with open(graph_file, encoding="utf-8") as f:
            return json.load(f)
