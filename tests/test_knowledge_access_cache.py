from __future__ import annotations

from pathlib import Path

from src.shared_capabilities.knowledge import access


def test_get_vector_store_reuses_kb_scoped_instance(monkeypatch, tmp_path):
    created: list[dict[str, str]] = []

    class FakeKBManager:
        def __init__(self, root: Path):
            self.root = root

        def get_kb(self, kb_id: str):
            return {
                "collection_name": f"collection-{kb_id}",
                "embedding_model": "embedding-model",
                "embedding_provider": "embedding-provider",
            }

        def get_vector_store_path(self, kb_id: str) -> Path:
            return self.root / kb_id / "vector"

    class FakeVectorStore:
        def __init__(
            self,
            *,
            persist_dir: str,
            collection_name: str,
            embedding_model: str,
            embedding_provider: str,
        ):
            created.append(
                {
                    "persist_dir": persist_dir,
                    "collection_name": collection_name,
                    "embedding_model": embedding_model,
                    "embedding_provider": embedding_provider,
                }
            )

    monkeypatch.setattr("src.knowledge.kb_manager.KnowledgeBaseManager", FakeKBManager)
    monkeypatch.setattr("src.knowledge.vector_store.VectorStore", FakeVectorStore)
    access.clear_vector_store_cache()

    first = access.get_vector_store("kb-1", data_dir=tmp_path)
    second = access.get_vector_store("kb-1", data_dir=tmp_path)

    assert first is second
    assert len(created) == 1
