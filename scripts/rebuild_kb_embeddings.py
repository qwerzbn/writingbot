#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Rebuild a knowledge base Chroma vector store with the configured embedding model."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge.kb_manager import KnowledgeBaseManager
from src.knowledge.vector_store import VectorStore


class EmbeddingRebuildError(RuntimeError):
    """Raised when a KB embedding rebuild cannot be completed safely."""


def load_chunks_from_index(kb_dir: Path) -> list[dict[str, Any]]:
    docs_file = kb_dir / "indexes" / "docs.jsonl"
    if not docs_file.exists():
        raise EmbeddingRebuildError(f"Index docs not found: {docs_file}")

    chunks: list[dict[str, Any]] = []
    with docs_file.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EmbeddingRebuildError(f"Invalid JSON in {docs_file}:{line_no}") from exc
            content = str(row.get("content") or "")
            if not content:
                continue
            chunks.append({"content": content, "metadata": dict(row.get("metadata") or {})})

    if not chunks:
        raise EmbeddingRebuildError(f"No chunks found in {docs_file}")
    return chunks


def backup_vector_store(vector_store_path: Path) -> Path | None:
    if not vector_store_path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = vector_store_path.with_name(f"{vector_store_path.name}.backup-{timestamp}")
    shutil.move(str(vector_store_path), str(backup_path))
    return backup_path


def restore_vector_store_backup(vector_store_path: Path, backup_path: Path | None) -> None:
    if backup_path is None or not backup_path.exists():
        return
    if vector_store_path.exists():
        shutil.rmtree(vector_store_path)
    shutil.move(str(backup_path), str(vector_store_path))


def validate_rebuilt_store(
    vector_store: VectorStore,
    *,
    expected_count: int,
    require_dimension: int | None,
) -> dict[str, Any]:
    stats = vector_store.get_stats()
    if getattr(vector_store, "embedding_is_fallback", False):
        raise EmbeddingRebuildError(
            f"Embedding fallback is active (backend={getattr(vector_store, 'embedding_backend', 'unknown')})"
        )
    actual_count = int(stats.get("document_count", 0))
    if actual_count != expected_count:
        raise EmbeddingRebuildError(f"Expected {expected_count} vectors, found {actual_count}")
    actual_dimension = getattr(vector_store, "embedding_dimension", None)
    if require_dimension is not None and actual_dimension != require_dimension:
        raise EmbeddingRebuildError(f"Expected embedding dimension {require_dimension}, found {actual_dimension}")
    return stats


def rebuild_kb_embeddings(
    *,
    kb_id: str,
    data_dir: Path,
    require_model: str | None,
    require_dimension: int | None,
    backup: bool,
) -> dict[str, Any]:
    manager = KnowledgeBaseManager(data_dir / "knowledge_bases")
    kb = manager.get_kb(kb_id)
    if not kb:
        raise EmbeddingRebuildError(f"KB not found: {kb_id}")

    provider = str(kb.get("embedding_provider") or "sentence-transformers")
    model = str(kb.get("embedding_model") or "BAAI/bge-m3")
    if require_model and model != require_model:
        raise EmbeddingRebuildError(f"KB uses embedding model {model!r}, expected {require_model!r}")

    kb_dir = manager.get_kb_path(kb_id)
    chunks = load_chunks_from_index(kb_dir)
    vector_store_path = manager.get_vector_store_path(kb_id)
    backup_path = backup_vector_store(vector_store_path) if backup else None
    vector_store_path.mkdir(parents=True, exist_ok=True)

    try:
        vector_store = VectorStore(
            persist_dir=str(vector_store_path),
            collection_name=str(kb["collection_name"]),
            embedding_model=model,
            embedding_provider=provider,
        )
        vector_store.clear()
        added = vector_store.add_chunks(chunks)
        if added != len(chunks):
            raise EmbeddingRebuildError(f"Expected to add {len(chunks)} chunks, added {added}")
        stats = validate_rebuilt_store(
            vector_store,
            expected_count=len(chunks),
            require_dimension=require_dimension,
        )
        return {
            "kb_id": kb_id,
            "embedding_provider": provider,
            "embedding_model": model,
            "chunks": len(chunks),
            "backup_path": str(backup_path) if backup_path else None,
            "stats": stats,
        }
    except Exception:
        restore_vector_store_backup(vector_store_path, backup_path)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb-id", required=True, help="Knowledge base id to rebuild")
    parser.add_argument("--data-dir", default=str(PROJECT_ROOT / "data"), help="WritingBot data directory")
    parser.add_argument("--require-model", default=None, help="Fail if the KB is not configured with this model")
    parser.add_argument("--require-dimension", type=int, default=1024, help="Fail if embedding dimension differs")
    parser.add_argument("--no-backup", action="store_true", help="Delete/recreate vector_store without backup")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = rebuild_kb_embeddings(
            kb_id=args.kb_id,
            data_dir=Path(args.data_dir),
            require_model=args.require_model,
            require_dimension=args.require_dimension,
            backup=not args.no_backup,
        )
    except Exception as exc:
        print(f"[rebuild-kb-embeddings] failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
