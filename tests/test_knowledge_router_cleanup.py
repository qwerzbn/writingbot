from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers import knowledge as knowledge_router
from src.knowledge.kb_manager import KnowledgeBaseManager
from src.retrieval import KnowledgeIndexStore


class _FakeVectorStore:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks

    def delete_by_file_id(self, file_id: str) -> int:
        before = len(self.chunks)
        self.chunks = [row for row in self.chunks if str(row.get("metadata", {}).get("file_id", "")) != str(file_id)]
        return before - len(self.chunks)

    def repair_missing_file_id(self, file_id: str, source_name: str) -> int:
        repaired = 0
        for row in self.chunks:
            meta = row.setdefault("metadata", {})
            if str(meta.get("source", "")) != str(source_name):
                continue
            if str(meta.get("file_id", "")).strip():
                continue
            meta["file_id"] = str(file_id)
            repaired += 1
        return repaired

    def list_all_chunks(self) -> list[dict]:
        return list(self.chunks)


def _build_client(kb_manager: KnowledgeBaseManager, vector_store: _FakeVectorStore, data_dir: Path) -> TestClient:
    app = FastAPI()
    app.include_router(knowledge_router.router, prefix="/api")
    knowledge_router.DATA_DIR = data_dir
    knowledge_router._kb_manager = kb_manager
    knowledge_router.get_kb_manager = lambda: kb_manager
    knowledge_router.get_vector_store = lambda kb_id: vector_store
    return TestClient(app)


def test_delete_file_cleans_metadata_raw_vector_and_indexes(tmp_path):
    data_dir = tmp_path / "data"
    kb_manager = KnowledgeBaseManager(data_dir / "knowledge_bases")
    kb = kb_manager.create_kb("cleanup-kb")
    kb_id = str(kb["id"])
    file_id = "file-1"
    file_path = kb_manager.get_raw_path(kb_id) / "file-1_demo.pdf"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4")

    kb_manager.add_file(
        kb_id,
        {
            "id": file_id,
            "name": "demo.pdf",
            "path": str(file_path),
            "size": file_path.stat().st_size,
            "uploaded_at": "2026-04-06T09:00:00",
            "blocks": 1,
            "chunks": 1,
        },
    )

    index_store = KnowledgeIndexStore(data_dir / "knowledge_bases")
    index_store.upsert_chunks(
        kb_id,
        [
            {"content": "chunk a", "metadata": {"source": "demo.pdf", "file_id": file_id}},
            {"content": "chunk b", "metadata": {"source": "keep.pdf", "file_id": "file-2"}},
        ],
    )

    vector_store = _FakeVectorStore(
        [
            {"id": "a", "content": "chunk a", "metadata": {"source": "demo.pdf", "file_id": file_id}},
            {"id": "b", "content": "chunk b", "metadata": {"source": "keep.pdf", "file_id": "file-2"}},
        ]
    )
    client = _build_client(kb_manager, vector_store, data_dir)

    resp = client.delete(f"/api/kbs/{kb_id}/files/{file_id}")
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["metadata_deleted"] is True
    assert payload["raw_deleted"] is True
    assert payload["vector_deleted"] == 1
    assert payload["index_deleted"] == 1

    kb_after = kb_manager.get_kb(kb_id)
    assert kb_after is not None
    assert not any(str(row.get("id")) == file_id for row in kb_after.get("files", []))
    assert not file_path.exists()

    remaining_docs = index_store.load_docs(kb_id)
    assert all(str(doc.metadata.get("file_id", "")) != file_id for doc in remaining_docs)


def test_repair_indexes_backfills_file_id_and_rebuilds_docs(tmp_path):
    data_dir = tmp_path / "data"
    kb_manager = KnowledgeBaseManager(data_dir / "knowledge_bases")
    kb = kb_manager.create_kb("repair-kb")
    kb_id = str(kb["id"])
    file_id = "file-repair"
    kb_manager.add_file(
        kb_id,
        {
            "id": file_id,
            "name": "repair.pdf",
            "path": str(kb_manager.get_raw_path(kb_id) / "repair.pdf"),
            "size": 123,
            "uploaded_at": "2026-04-06T09:10:00",
            "blocks": 1,
            "chunks": 1,
        },
    )

    vector_store = _FakeVectorStore(
        [
            {"id": "c1", "content": "repair chunk", "metadata": {"source": "repair.pdf"}},
            {"id": "c2", "content": "keep chunk", "metadata": {"source": "keep.pdf", "file_id": "file-keep"}},
        ]
    )
    client = _build_client(kb_manager, vector_store, data_dir)

    resp = client.post(f"/api/kbs/{kb_id}/repair-indexes")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["repaired_vectors"] == 1
    assert data["reindexed_docs"] >= 2

    docs = KnowledgeIndexStore(data_dir / "knowledge_bases").load_docs(kb_id)
    repaired_doc = next((doc for doc in docs if doc.content == "repair chunk"), None)
    assert repaired_doc is not None
    assert repaired_doc.metadata.get("file_id") == file_id
