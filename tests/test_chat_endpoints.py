import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routers.chat as chat_router
from src.session import SessionManager


class _FakeChatOrchestrator:
    def __init__(self):
        self.sync_calls: list[dict] = []
        self.stream_calls: list[dict] = []
        self._runs: dict[str, dict] = {}

    def execute_sync(self, mode: str, payload: dict):
        assert mode == "chat_research"
        self.sync_calls.append(payload)
        has_kb = bool(payload.get("kb_id"))
        sources = [{"source": "paper.pdf", "page": 1, "paper_id": "p-1", "title": "Paper 1", "score": 0.9}] if has_kb else []
        return {
            "run_id": f"sync-{len(self.sync_calls)}",
            "trace_id": "trace-sync",
            "output": "RAG:answer" if has_kb else "LLM:answer",
            "sources": sources,
            "metadata": {
                "run_id": f"sync-{len(self.sync_calls)}",
                "trace_id": "trace-sync",
                "meta": {"paper_hits": 1 if has_kb else 0},
            },
        }

    def create_run(self, mode: str, payload: dict):
        assert mode == "chat_research"
        run_id = f"run-{len(self.stream_calls) + 1}"
        trace_id = f"trace-{len(self.stream_calls) + 1}"
        self._runs[run_id] = payload
        self.stream_calls.append({"run_id": run_id, "trace_id": trace_id, "payload": payload})
        return {"run_id": run_id, "trace_id": trace_id}

    def stream_run(self, run_id: str):
        payload = self._runs[run_id]
        has_kb = bool(payload.get("kb_id"))
        prefix = "RAG" if has_kb else "LLM"
        sources = [{"source": "paper.pdf", "page": 2, "paper_id": "p-1", "title": "Paper 1", "score": 0.88}] if has_kb else []
        yield {"type": "init", "run_id": run_id, "trace_id": f"trace-{run_id}", "mode": "chat_research"}
        yield {"type": "step", "step": "plan", "status": "done"}
        yield {"type": "chunk", "content": prefix}
        yield {"type": "chunk", "content": "-STREAM"}
        yield {"type": "sources", "data": sources}
        yield {
            "type": "done",
            "run_id": run_id,
            "trace_id": f"trace-{run_id}",
            "output": f"{prefix}-STREAM",
            "sources": sources,
            "meta": {"paper_hits": 1 if has_kb else 0},
        }


def _build_client(monkeypatch, tmp_path):
    session_manager = SessionManager(tmp_path / "sessions")
    fake_orchestrator = _FakeChatOrchestrator()

    chat_router._reset_runtime_state_for_tests()
    monkeypatch.setattr(chat_router, "get_session_manager", lambda: session_manager)
    monkeypatch.setattr(chat_router, "get_orchestrator_service", lambda: fake_orchestrator)

    app = FastAPI()
    app.include_router(chat_router.router, prefix="/api")
    return TestClient(app), session_manager, fake_orchestrator


class _FakeNoChunkOrchestrator(_FakeChatOrchestrator):
    def stream_run(self, run_id: str):
        payload = self._runs[run_id]
        has_kb = bool(payload.get("kb_id"))
        prefix = "RAG" if has_kb else "LLM"
        sources = [{"source": "paper.pdf", "page": 9, "paper_id": "p-1", "title": "Paper 1", "score": 0.76}] if has_kb else []
        yield {"type": "init", "run_id": run_id, "trace_id": f"trace-{run_id}", "mode": "chat_research"}
        yield {"type": "step", "step": "plan", "status": "done"}
        yield {"type": "step", "step": "synthesize", "status": "working", "agent_id": "academic_writer"}
        yield {
            "type": "done",
            "run_id": run_id,
            "trace_id": f"trace-{run_id}",
            "output": f"{prefix}-ONE-SHOT-OUTPUT",
            "sources": sources,
            "meta": {"paper_hits": 1 if has_kb else 0},
        }


def _build_client_with_orchestrator(monkeypatch, tmp_path, orchestrator):
    session_manager = SessionManager(tmp_path / "sessions")
    chat_router._reset_runtime_state_for_tests()
    monkeypatch.setattr(chat_router, "get_session_manager", lambda: session_manager)
    monkeypatch.setattr(chat_router, "get_orchestrator_service", lambda: orchestrator)

    app = FastAPI()
    app.include_router(chat_router.router, prefix="/api")
    return TestClient(app), session_manager


def test_empty_draft_not_persisted_and_message_persists(monkeypatch, tmp_path):
    client, _, _ = _build_client(monkeypatch, tmp_path)

    create_resp = client.post("/api/conversations", json={"title": "测试会话", "kb_id": "kb-1"})
    assert create_resp.status_code == 200
    created = create_resp.json()["data"]
    conv_id = created["id"]

    list_resp = client.get("/api/conversations")
    assert list_resp.status_code == 200
    rows = list_resp.json()["data"]
    assert all(row["id"] != conv_id for row in rows)

    get_resp = client.get(f"/api/conversations/{conv_id}")
    assert get_resp.status_code == 404

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
    assert body["message"]["content"] == "RAG:answer"
    assert body["sources"] and body["sources"][0]["source"] == "paper.pdf"

    detail_resp = client.get(f"/api/conversations/{conv_id}")
    detail = detail_resp.json()["data"]
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][1]["role"] == "assistant"
    assert detail["messages"][1]["sources"][0]["source"] == "paper.pdf"


def test_chat_non_stream_without_kb_passes_history_to_orchestrator(monkeypatch, tmp_path):
    client, _, fake_orch = _build_client(monkeypatch, tmp_path)

    first = client.post("/api/chat", json={"message": "你好"})
    assert first.status_code == 200
    conv_id = first.json()["data"]["conversation_id"]
    assert first.json()["data"]["sources"] == []

    second = client.post("/api/chat", json={"message": "继续", "conversation_id": conv_id})
    assert second.status_code == 200

    assert len(fake_orch.sync_calls) == 2
    first_call = fake_orch.sync_calls[0]
    second_call = fake_orch.sync_calls[1]

    assert first_call["history"] == []
    assert len(second_call["history"]) == 2
    assert second_call["history"][0]["role"] == "user"
    assert second_call["history"][1]["role"] == "assistant"
    assert second_call["history"][1]["content"] == "LLM:answer"


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
    assert '"kind": "progress"' in body
    assert '"step": "plan"' in body
    assert '"status": "done"' in body
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


def test_chat_stream_fallback_chunk_when_upstream_is_one_shot(monkeypatch, tmp_path):
    client, session_manager = _build_client_with_orchestrator(monkeypatch, tmp_path, _FakeNoChunkOrchestrator())

    resp = client.post("/api/chat/stream", json={"message": "fallback", "kb_id": "kb-1"})
    assert resp.status_code == 200

    body = resp.text
    assert '"type": "chunk"' in body
    assert '"kind": "content"' in body
    assert '"fallback_chunk_used": true' in body
    assert '"time_to_first_chunk_ms":' in body
    assert body.find('"kind": "progress"') < body.find('"kind": "content"') < body.find('"type": "done"')

    match = re.search(r'"conversation_id": "([^\"]+)"', body)
    assert match is not None
    conv_id = match.group(1)

    session = session_manager.get(conv_id)
    assert session is not None
    assert len(session.messages) == 2
    assert session.messages[1]["content"] == "RAG-ONE-SHOT-OUTPUT"


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


def test_chat_skill_ids_persist_to_session_default(monkeypatch, tmp_path):
    client, _, _ = _build_client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/chat",
        json={"message": "帮我总结方法", "kb_id": "kb-1", "skill_ids": ["/paper-summary"]},
    )
    assert resp.status_code == 200
    conv_id = resp.json()["data"]["conversation_id"]

    detail = client.get(f"/api/conversations/{conv_id}").json()["data"]
    assert detail["default_skill_ids"] == ["/paper-summary"]
    assert detail["messages"][0]["metadata"]["selected_skill_ids"] == ["/paper-summary"]
