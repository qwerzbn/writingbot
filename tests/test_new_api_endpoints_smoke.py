from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routers.evaluation as evaluation_router
import src.api.routers.orchestrator as orchestrator_router
import src.api.routers.retrieval as retrieval_router


class _FakeOrchestrator:
    def __init__(self):
        self._run = {
            "run_id": "run-123",
            "trace_id": "trace-123",
            "mode": "research",
            "payload": {},
            "status": "pending",
            "result": {},
        }

    def create_run(self, mode: str, payload: dict):
        self._run.update({"mode": mode, "payload": payload})
        return {"run_id": self._run["run_id"], "trace_id": self._run["trace_id"]}

    def get_run(self, run_id: str):
        if run_id != self._run["run_id"]:
            return None
        return self._run

    def get_run_detail(self, run_id: str):
        if run_id != self._run["run_id"]:
            return None
        return {
            "run_id": self._run["run_id"],
            "trace_id": self._run["trace_id"],
            "mode": self._run["mode"],
            "status": "done",
            "created_at": "2026-01-01T00:00:00",
            "expires_at": "2026-01-01T02:00:00",
            "result": {
                "output": "hello",
                "sources": [{"source": "a.pdf", "page": 1}],
                "metrics": {"source_count": 1, "evidence_status": "ok"},
                "paper_workflow": {"control_flags": {"current_stage": "complete"}},
            },
            "metrics": {"source_count": 1, "evidence_status": "ok"},
        }

    def stream_run(self, run_id: str):
        if run_id != self._run["run_id"]:
            yield {"type": "error", "error": "run not found"}
            return
        yield {"type": "init", "run_id": run_id, "trace_id": self._run["trace_id"], "mode": self._run["mode"]}
        yield {"type": "step", "step": "plan", "status": "done"}
        yield {"type": "chunk", "content": "hello"}
        yield {"type": "sources", "data": [{"source": "a.pdf", "page": 1}]}
        yield {"type": "done", "run_id": run_id, "trace_id": self._run["trace_id"], "output": "hello"}


class _FakeKBManager:
    def __init__(self, *args, **kwargs):
        pass

    def get_kb(self, kb_id: str):
        return {"collection_name": "col", "embedding_model": "m", "embedding_provider": "p"}

    def get_vector_store_path(self, kb_id: str):
        return "/tmp/fake-vector-store"


class _FakeVectorStore:
    def __init__(self, *args, **kwargs):
        pass


class _FakeHybrid:
    def retrieve(self, kb_id: str, vector_store, query: str, top_k: int):
        return {
            "query": query,
            "recalls": {"vector": [], "bm25": [], "graph": []},
            "fusion": [],
            "rerank": [],
            "judge": [],
            "context_window": {"token_budget": 6000, "used_tokens": 0, "context": ""},
            "sources": [{"source": "a.pdf", "page": 1, "score": 0.9}],
            "weights": {"vector": 0.5, "bm25": 0.3, "graph": 0.2},
        }


class _FakeEvalService:
    class _Job:
        id = "job-1"
        status = "pending"
        created_at = "2026-01-01T00:00:00"

    def create_job(self):
        return self._Job()

    def run_async(self, job_id: str) -> None:
        return None

    def load_report(self, job_id: str):
        if job_id != "job-1":
            return None
        return {"id": "job-1", "status": "done", "summary": {"Citation Precision": 0.9, "Faithfulness": 0.9}}

    def latest_report_summary(self):
        return {
            "id": "job-1",
            "status": "pass",
            "summary": {"Citation Precision": 0.9, "Faithfulness": 0.9},
            "gate": {"Citation Precision >= 0.85": True, "Faithfulness >= 0.80": True},
        }

    def list_reports(self, limit: int = 10):
        return [self.latest_report_summary()]


def test_orchestrator_run_and_stream_endpoints(monkeypatch):
    fake = _FakeOrchestrator()
    monkeypatch.setattr(orchestrator_router, "get_orchestrator_service", lambda: fake)

    app = FastAPI()
    app.include_router(orchestrator_router.router, prefix="/api")
    client = TestClient(app)

    run_resp = client.post("/api/orchestrator/run", json={"mode": "research", "payload": {"topic": "hi"}})
    assert run_resp.status_code == 200
    run_data = run_resp.json()["data"]
    assert run_data["run_id"] == "run-123"
    assert run_data["trace_id"] == "trace-123"

    stream_resp = client.get("/api/orchestrator/stream/run-123")
    assert stream_resp.status_code == 200
    body = stream_resp.text
    # Ensure normalized event envelope is present in stream payload.
    assert '"type": "init"' in body
    assert '"type": "step"' in body
    assert '"type": "chunk"' in body
    assert '"type": "sources"' in body
    assert '"type": "done"' in body

    detail_resp = client.get("/api/orchestrator/run/run-123")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["metrics"]["source_count"] == 1
    assert detail["result"]["paper_workflow"]["control_flags"]["current_stage"] == "complete"

    chat_resp = client.post(
        "/api/orchestrator/run",
        json={"mode": "chat_research", "payload": {"message": "解释这篇论文", "kb_id": "kb-1"}},
    )
    assert chat_resp.status_code == 200


def test_retrieval_hybrid_endpoint(monkeypatch):
    monkeypatch.setattr(retrieval_router, "get_kb_manager", lambda: _FakeKBManager())
    monkeypatch.setattr(retrieval_router, "get_vector_store", lambda kb_id: _FakeVectorStore())
    monkeypatch.setattr(retrieval_router, "HybridRetrievalService", _FakeHybrid)

    app = FastAPI()
    app.include_router(retrieval_router.router, prefix="/api")
    client = TestClient(app)

    resp = client.post("/api/retrieval/hybrid", json={"query": "rag", "kb_id": "kb-1", "top_k": 5})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "recalls" in data
    assert "fusion" in data
    assert "rerank" in data
    assert "judge" in data
    assert "context_window" in data
    assert data["weights"] == {"vector": 0.5, "bm25": 0.3, "graph": 0.2}


def test_evaluation_run_and_report_endpoints(monkeypatch):
    monkeypatch.setattr(evaluation_router, "get_evaluation_service", lambda: _FakeEvalService())

    app = FastAPI()
    app.include_router(evaluation_router.router, prefix="/api")
    client = TestClient(app)

    run_resp = client.post("/api/evaluation/run")
    assert run_resp.status_code == 200
    run_data = run_resp.json()["data"]
    assert run_data["id"] == "job-1"

    report_resp = client.get("/api/evaluation/report/job-1")
    assert report_resp.status_code == 200
    report = report_resp.json()["data"]
    assert report["summary"]["Citation Precision"] >= 0.85
    assert report["summary"]["Faithfulness"] >= 0.8

    latest_resp = client.get("/api/evaluation/report/latest")
    assert latest_resp.status_code == 200
    assert latest_resp.json()["data"]["status"] == "pass"

    list_resp = client.get("/api/evaluation/reports")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]) == 1
