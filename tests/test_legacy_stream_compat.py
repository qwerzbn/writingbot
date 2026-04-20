from dataclasses import dataclass, field

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routers.co_writer as co_writer_router
import src.api.routers.research as research_router


@dataclass
class _Run:
    result: dict = field(default_factory=dict)


class _FakeOrchestrator:
    def __init__(self, events: list[dict], run_result: dict | None = None, fail_stream_run: bool = False):
        self._events = events
        self._run = _Run(result=run_result or {})
        self._fail_stream_run = fail_stream_run

    def create_run(self, mode: str, payload: dict):
        return {"run_id": "run-1", "trace_id": "trace-1", "mode": mode, "payload": payload}

    def stream_research_workflow(self, topic: str, kb_id: str | None = None):
        for ev in self._events:
            yield ev

    def stream_run(self, run_id: str):
        if self._fail_stream_run:
            raise AssertionError("research stream router should use stream_research_workflow directly")
        for ev in self._events:
            yield ev

    def get_run(self, run_id: str):
        return self._run


def test_research_stream_compat_header_and_plan(monkeypatch):
    fake = _FakeOrchestrator(
        events=[
            {"type": "plan", "content": "- background\n- methods"},
            {"type": "chunk", "content": "report body"},
            {"type": "done", "meta": {"coverage_status": "partial"}},
        ],
        run_result={"plan": "- background\n- methods"},
        fail_stream_run=True,
    )
    monkeypatch.setattr(research_router, "get_orchestrator_service", lambda: fake)

    app = FastAPI()
    app.include_router(research_router.router, prefix="/api")
    client = TestClient(app)

    resp = client.post("/api/research/stream", json={"topic": "RAG"})
    assert resp.status_code == 200
    assert resp.headers.get("x-orchestrated") == "true"
    body = resp.text
    assert '"type": "plan"' in body
    assert '"type": "chunk"' in body
    assert '"type": "done"' in body


def test_co_writer_stream_compat_header(monkeypatch):
    fake = _FakeOrchestrator(
        events=[
            {"type": "chunk", "content": "rewrite-1"},
            {"type": "sources", "data": [{"source": "s1", "page": 1}]},
            {"type": "done"},
        ]
    )
    monkeypatch.setattr(co_writer_router, "get_orchestrator_service", lambda: fake)

    app = FastAPI()
    app.include_router(co_writer_router.router, prefix="/api")
    client = TestClient(app)

    resp = client.post("/api/co-writer/edit/stream", json={"text": "abc"})
    assert resp.status_code == 200
    assert resp.headers.get("x-orchestrated") == "true"
    body = resp.text
    assert '"type": "chunk"' in body
    assert '"type": "sources"' in body
    assert '"type": "done"' in body
