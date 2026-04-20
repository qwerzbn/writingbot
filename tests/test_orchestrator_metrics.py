from __future__ import annotations

from src.agent_runtime.runtime import AgentRuntime
from src.orchestrator.service import OrchestratorService
from src.shared_capabilities.retrieval.search_backend import SearchBackend

from tests.test_agent_runtime import _responses_for


def test_orchestrator_facade_exposes_runtime_metrics(monkeypatch):
    runtime = AgentRuntime()
    monkeypatch.setattr(
        runtime,
        "_research_backend",
        lambda payload: SearchBackend.from_responses(_responses_for(str(payload.get("topic") or ""))),
    )

    service = OrchestratorService(runtime=runtime)
    result = service.execute_sync("research", {"topic": "metrics topic"})

    metrics = result["metadata"]["metrics"]
    assert metrics["retry_count"] == 0
    assert metrics["failure_count"] == 0
    assert metrics["source_count"] > 0
    assert metrics["evidence_status"] == "sufficient"


def test_orchestrator_run_detail_keeps_legacy_paper_workflow_alias(monkeypatch):
    runtime = AgentRuntime()
    monkeypatch.setattr(
        runtime,
        "_research_backend",
        lambda payload: SearchBackend.from_responses(_responses_for(str(payload.get("topic") or ""))),
    )

    service = OrchestratorService(runtime=runtime)
    run = service.create_run("research", {"topic": "detail topic"})
    list(service.stream_run(run["run_id"]))
    detail = service.get_run_detail(run["run_id"])

    assert detail is not None
    assert detail["result"]["paper_workflow"]["control_flags"]["current_stage"] == "complete"
    assert detail["metrics"]["source_count"] > 0
