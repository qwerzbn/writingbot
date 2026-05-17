from __future__ import annotations

import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routers.knowledge as knowledge_router
from src.knowledge.kb_manager import KnowledgeBaseManager
from src.knowledge.vector_store import get_embedding_function


class _FakeEmbeddingRows:
    def __init__(self, rows: list[list[float]]):
        self._rows = rows

    def tolist(self) -> list[list[float]]:
        return self._rows


def test_bge_m3_sentence_transformer_embedding_reports_real_backend(monkeypatch):
    class FakeSentenceTransformer:
        def __init__(self, model: str):
            self.model = model

        def encode(self, texts, show_progress_bar=False):
            return _FakeEmbeddingRows([[0.1] * 1024 for _ in texts])

    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    embed_fn = get_embedding_function("sentence-transformers", "BAAI/bge-m3")

    assert embed_fn(["test"])[0] == [0.1] * 1024
    assert getattr(embed_fn, "embedding_backend") == "sentence-transformers"
    assert getattr(embed_fn, "embedding_model") == "BAAI/bge-m3"
    assert getattr(embed_fn, "embedding_dimension") == 1024
    assert getattr(embed_fn, "is_fallback") is False


def test_sentence_transformer_failure_raises_without_explicit_fallback(monkeypatch):
    class BrokenSentenceTransformer:
        def __init__(self, model: str):
            raise RuntimeError("torch mismatch")

    fake_module = types.SimpleNamespace(SentenceTransformer=BrokenSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    monkeypatch.delenv("ALLOW_HASHING_EMBEDDING_FALLBACK", raising=False)

    with pytest.raises(RuntimeError, match="Unable to load sentence-transformers embedding model"):
        get_embedding_function("sentence-transformers", "BAAI/bge-m3")


def test_hashing_fallback_requires_explicit_environment_flag(monkeypatch):
    class BrokenSentenceTransformer:
        def __init__(self, model: str):
            raise RuntimeError("torch mismatch")

    fake_module = types.SimpleNamespace(SentenceTransformer=BrokenSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    monkeypatch.setenv("ALLOW_HASHING_EMBEDDING_FALLBACK", "true")

    embed_fn = get_embedding_function("sentence-transformers", "BAAI/bge-m3")

    assert len(embed_fn(["test"])[0]) == 1024
    assert getattr(embed_fn, "embedding_backend") == "hashing"
    assert getattr(embed_fn, "embedding_model") == "BAAI/bge-m3"
    assert getattr(embed_fn, "embedding_dimension") == 1024
    assert getattr(embed_fn, "is_fallback") is True


def test_new_knowledge_bases_default_to_bge_m3(tmp_path):
    manager = KnowledgeBaseManager(tmp_path / "knowledge_bases")

    kb = manager.create_kb("Agent")

    assert kb["embedding_provider"] == "sentence-transformers"
    assert kb["embedding_model"] == "BAAI/bge-m3"


def test_kb_api_defaults_to_bge_m3(monkeypatch):
    captured: dict[str, str] = {}

    class FakeKBManager:
        def create_kb(self, name: str, embedding_model: str, embedding_provider: str, description: str):
            captured.update(
                {
                    "name": name,
                    "embedding_model": embedding_model,
                    "embedding_provider": embedding_provider,
                    "description": description,
                }
            )
            return {"id": "kb-1", **captured}

    monkeypatch.setattr(knowledge_router, "get_kb_manager", lambda: FakeKBManager())

    app = FastAPI()
    app.include_router(knowledge_router.router, prefix="/api")
    client = TestClient(app)

    resp = client.post("/api/kbs", json={"name": "Agent"})

    assert resp.status_code == 200
    assert captured["embedding_provider"] == "sentence-transformers"
    assert captured["embedding_model"] == "BAAI/bge-m3"


def test_embedding_test_endpoint_rejects_fallback(monkeypatch):
    def fake_get_embedding_function(*args, **kwargs):
        def embed(texts):
            return [[0.1] * 1024 for _ in texts]

        embed.embedding_backend = "hashing"
        embed.embedding_model = "BAAI/bge-m3"
        embed.embedding_dimension = 1024
        embed.is_fallback = True
        return embed

    monkeypatch.setattr("src.knowledge.vector_store.get_embedding_function", fake_get_embedding_function)

    app = FastAPI()
    app.include_router(knowledge_router.router, prefix="/api")
    client = TestClient(app)

    resp = client.post(
        "/api/embedding/test",
        json={"embedding_provider": "sentence-transformers", "embedding_model": "BAAI/bge-m3"},
    )

    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "fallback" in resp.json()["error"].lower()
