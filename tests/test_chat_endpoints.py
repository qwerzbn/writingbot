import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routers.chat as chat_router
from src.session import SessionManager


class _FakeKBManager:
    def __init__(self, *args, **kwargs):
        pass

    def get_kb(self, kb_id: str):
        if kb_id == "kb-1":
            return {
                "collection_name": "col-1",
                "embedding_model": "fake-model",
                "embedding_provider": "fake-provider",
            }
        return None

    def get_vector_store_path(self, kb_id: str):
        return "/tmp/fake-vector-store"


class _FakeVectorStore:
    def __init__(self, *args, **kwargs):
        pass


class _FakeRAGEngine:
    def __init__(self, vector_store):
        self.vector_store = vector_store
        self.history = []

    def query(self, message: str, use_history: bool = True):
        return {
            "answer": f"RAG:{message}",
            "sources": [{"source": "paper.pdf", "page": 1, "score": 0.9}],
        }

    def query_stream(self, message: str, use_history: bool = True):
        yield "RAG"
        yield "-STREAM"
        return {"sources": [{"source": "paper.pdf", "page": 2, "score": 0.88}]}


class _FakeLLMClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, temperature=0.7, max_tokens=2000, **kwargs):
        self.calls.append(messages)
        return "LLM:answer"

    def chat_stream(self, messages, temperature=0.7, max_tokens=2000, **kwargs):
        self.calls.append(messages)
        yield "LLM"
        yield "-STREAM"


def _build_client(monkeypatch, tmp_path):
    session_manager = SessionManager(tmp_path / "sessions")
    fake_llm = _FakeLLMClient()

    chat_router._reset_runtime_state_for_tests()
    monkeypatch.setattr(chat_router, "get_session_manager", lambda: session_manager)
    monkeypatch.setattr(chat_router, "KnowledgeBaseManager", _FakeKBManager)
    monkeypatch.setattr(chat_router, "VectorStore", _FakeVectorStore)
    monkeypatch.setattr(chat_router, "RAGEngine", _FakeRAGEngine)
    monkeypatch.setattr(chat_router, "get_llm_client", lambda: fake_llm)

    app = FastAPI()
    app.include_router(chat_router.router, prefix="/api")
    return TestClient(app), session_manager, fake_llm


def test_empty_draft_not_persisted_and_message_persists(monkeypatch, tmp_path):
    client, _, _ = _build_client(monkeypatch, tmp_path)

    create_resp = client.post("/api/conversations", json={"title": "测试会话", "kb_id": "kb-1"})
    assert create_resp.status_code == 200
    created = create_resp.json()["data"]
    conv_id = created["id"]

    # Empty draft should not be stored.
    list_resp = client.get("/api/conversations")
    assert list_resp.status_code == 200
    rows = list_resp.json()["data"]
    assert all(row["id"] != conv_id for row in rows)

    get_resp = client.get(f"/api/conversations/{conv_id}")
    assert get_resp.status_code == 404

    # Once message is sent with the same conversation_id, it becomes persistent.
    chat_resp = client.post("/api/chat", json={"message": "开始", "conversation_id": conv_id, "kb_id": "kb-1"})
    assert chat_resp.status_code == 200
    assert chat_resp.json()["data"]["conversation_id"] == conv_id

    get_after_chat = client.get(f"/api/conversations/{conv_id}")
    assert get_after_chat.status_code == 200
    detail = get_after_chat.json()["data"]
    assert len(detail["messages"]) == 2

    delete_resp = client.delete(f"/api/conversations/{conv_id}")
    assert delete_resp.status_code == 200

    get_after_delete = client.get(f"/api/conversations/{conv_id}")
    assert get_after_delete.status_code == 404


def test_chat_non_stream_with_kb_persists_sources(monkeypatch, tmp_path):
    client, _, _ = _build_client(monkeypatch, tmp_path)

    resp = client.post("/api/chat", json={"message": "什么是RAG", "kb_id": "kb-1"})
    assert resp.status_code == 200

    body = resp.json()["data"]
    conv_id = body["conversation_id"]
    assert body["message"]["content"].startswith("RAG:")
    assert body["sources"] and body["sources"][0]["source"] == "paper.pdf"

    detail_resp = client.get(f"/api/conversations/{conv_id}")
    detail = detail_resp.json()["data"]
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][1]["role"] == "assistant"
    assert detail["messages"][1]["sources"][0]["source"] == "paper.pdf"


def test_chat_non_stream_without_kb_uses_llm_with_history(monkeypatch, tmp_path):
    client, _, fake_llm = _build_client(monkeypatch, tmp_path)

    first = client.post("/api/chat", json={"message": "你好"})
    assert first.status_code == 200
    conv_id = first.json()["data"]["conversation_id"]
    assert first.json()["data"]["sources"] == []

    second = client.post("/api/chat", json={"message": "继续", "conversation_id": conv_id})
    assert second.status_code == 200

    assert len(fake_llm.calls) == 2
    first_call = fake_llm.calls[0]
    second_call = fake_llm.calls[1]

    assert len(first_call) == 2  # system + user
    assert first_call[-1]["content"] == "你好"

    assert len(second_call) == 4  # system + history(user,assistant) + new user
    assert any(msg["role"] == "assistant" and msg["content"] == "LLM:answer" for msg in second_call)


def test_chat_non_stream_idempotency_replay(monkeypatch, tmp_path):
    client, _, _ = _build_client(monkeypatch, tmp_path)

    key = "idem-sync-1"
    first = client.post(
        "/api/chat",
        json={"message": "幂等测试", "kb_id": "kb-1", "idempotency_key": key},
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == 200
    conv_id = first.json()["data"]["conversation_id"]
    assert first.json()["data"].get("idempotent_replay") is None

    second = client.post(
        "/api/chat",
        json={"message": "幂等测试", "conversation_id": conv_id, "idempotency_key": key},
        headers={"Idempotency-Key": key},
    )
    assert second.status_code == 200
    assert second.json()["data"]["idempotent_replay"] is True

    detail = client.get(f"/api/conversations/{conv_id}").json()["data"]
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][1]["role"] == "assistant"


def test_chat_stream_event_order_and_persistence(monkeypatch, tmp_path):
    client, session_manager, _ = _build_client(monkeypatch, tmp_path)

    resp = client.post("/api/chat/stream", json={"message": "流式测试", "kb_id": "kb-1"})
    assert resp.status_code == 200

    body = resp.text
    assert '"type": "chunk"' in body
    assert '"type": "sources"' in body
    assert '"type": "done"' in body
    assert body.find('"type": "chunk"') < body.find('"type": "sources"') < body.find('"type": "done"')

    match = re.search(r'"conversation_id": "([^\"]+)"', body)
    assert match is not None
    conv_id = match.group(1)

    session = session_manager.get(conv_id)
    assert session is not None
    assert len(session.messages) == 2
    assert session.messages[1]["content"] == "RAG-STREAM"
    assert session.messages[1]["sources"][0]["page"] == 2


def test_chat_stream_idempotency_replay(monkeypatch, tmp_path):
    client, session_manager, _ = _build_client(monkeypatch, tmp_path)

    key = "idem-stream-1"
    first = client.post(
        "/api/chat/stream",
        json={"message": "流式幂等", "kb_id": "kb-1", "idempotency_key": key},
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == 200
    body1 = first.text
    match = re.search(r'"conversation_id": "([^\"]+)"', body1)
    assert match is not None
    conv_id = match.group(1)

    second = client.post(
        "/api/chat/stream",
        json={"message": "流式幂等", "conversation_id": conv_id, "idempotency_key": key},
        headers={"Idempotency-Key": key},
    )
    assert second.status_code == 200
    body2 = second.text
    assert '"idempotent_replay": true' in body2

    session = session_manager.get(conv_id)
    assert session is not None
    assert len(session.messages) == 2


def test_chat_metrics_endpoint(monkeypatch, tmp_path):
    client, _, _ = _build_client(monkeypatch, tmp_path)

    client.post("/api/chat", json={"message": "metrics", "kb_id": "kb-1"})
    resp = client.get("/api/chat/metrics")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["counters"]["requests_total"] >= 1
    assert "p95" in data["latency_ms"]


def test_chat_rate_limit(monkeypatch, tmp_path):
    client, _, _ = _build_client(monkeypatch, tmp_path)
    monkeypatch.setattr(chat_router, "_RATE_LIMIT_MAX_REQUESTS", 1)
    monkeypatch.setattr(chat_router, "_RATE_LIMIT_WINDOW_SECONDS", 60.0)
    chat_router._reset_runtime_state_for_tests()

    first = client.post("/api/chat", json={"message": "first", "kb_id": "kb-1"})
    assert first.status_code == 200
    second = client.post("/api/chat", json={"message": "second", "kb_id": "kb-1"})
    assert second.status_code == 429
