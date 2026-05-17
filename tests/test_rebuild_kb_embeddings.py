from __future__ import annotations

import json

import pytest

from scripts.rebuild_kb_embeddings import (
    EmbeddingRebuildError,
    load_chunks_from_index,
    validate_rebuilt_store,
)


def test_load_chunks_from_index_reads_content_and_metadata(tmp_path):
    kb_dir = tmp_path / "kb-1"
    index_dir = kb_dir / "indexes"
    index_dir.mkdir(parents=True)
    docs_file = index_dir / "docs.jsonl"
    docs_file.write_text(
        json.dumps(
            {
                "doc_id": "doc-1",
                "content": "AgentGuard evidence",
                "metadata": {"source": "AgentGuard.pdf", "page": 1},
                "tokens": ["agentguard"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    chunks = load_chunks_from_index(kb_dir)

    assert chunks == [
        {
            "content": "AgentGuard evidence",
            "metadata": {"source": "AgentGuard.pdf", "page": 1},
        }
    ]


def test_validate_rebuilt_store_rejects_hashing_fallback():
    class FallbackStore:
        embedding_is_fallback = True
        embedding_backend = "hashing"
        embedding_dimension = 1024

        def get_stats(self):
            return {"document_count": 734}

    with pytest.raises(EmbeddingRebuildError, match="fallback"):
        validate_rebuilt_store(FallbackStore(), expected_count=734, require_dimension=1024)
