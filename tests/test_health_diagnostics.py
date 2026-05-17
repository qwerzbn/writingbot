from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app


def test_health_reports_external_dependency_degraded_paths(monkeypatch):
    monkeypatch.setenv("RERANKER_PROVIDER", "none")

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    diagnostics = response.json()["data"]["dependencies"]
    assert set(diagnostics) >= {"llm", "reranker", "fastwrite"}
    assert diagnostics["reranker"]["status"] == "disabled"
    assert "enabled" in diagnostics["llm"]
    assert "available" in diagnostics["fastwrite"]
