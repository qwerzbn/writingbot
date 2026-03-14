from pathlib import Path

from src.orchestrator.run_store import RunStore
from src.orchestrator.service import OrchestratorService


class _StubService(OrchestratorService):
    def __init__(self, tmp_path: Path):
        self.run_store = RunStore(ttl_hours=2)
        self.hybrid = None
        self.research_agent = None
        self.co_writer_agent = None
        self.metrics_file = tmp_path / "orchestrator_runs.jsonl"
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        self._retrieve_attempts = 0

    def _step_plan(self, ctx):
        ctx.plan = "- q1"
        ctx.confidence = 0.7
        if False:
            yield None

    def _step_retrieve(self, ctx):
        self._retrieve_attempts += 1
        if self._retrieve_attempts == 1:
            raise RuntimeError("temporary retrieval failure")
        ctx.sources = [{"source": "paper.pdf", "page": 1, "content": "evidence"}]
        ctx.evidence = ctx.sources
        ctx.metadata["empty_evidence_rate"] = 0.0
        yield {"type": "sources", "data": ctx.sources}

    def _step_synthesize(self, ctx):
        ctx.generated_text = "answer [1]"
        self._record_model_call(
            ctx,
            stage="synthesize",
            messages=[{"role": "user", "content": "question"}],
            output=ctx.generated_text,
        )
        yield {"type": "chunk", "content": ctx.generated_text}

    def _step_critique(self, ctx):
        ctx.metadata["citation_missing_fix"] = 0
        if False:
            yield None

    def _step_finalize(self, ctx):
        if False:
            yield None


def test_done_event_contains_run_metrics(tmp_path):
    service = _StubService(tmp_path)
    run = service.create_run(mode="research", payload={"topic": "hi"})
    events = list(service.stream_run(run["run_id"]))
    done = [event for event in events if event.get("type") == "done"][-1]

    metrics = done["metrics"]
    assert metrics["retry_count"] == 1
    assert metrics["failure_count"] == 1
    assert metrics["retry_rate"] > 0
    assert metrics["failure_rate"] > 0
    assert metrics["source_count"] == 1
    assert metrics["evidence_status"] == "unknown"
    assert metrics["model_cost"]["calls"] == 1
    assert "retrieve" in metrics["stage_timings_ms"]


def test_run_log_persists_metrics_payload(tmp_path):
    service = _StubService(tmp_path)
    run = service.create_run(mode="research", payload={"topic": "rag"})
    list(service.stream_run(run["run_id"]))

    payload = service.metrics_file.read_text(encoding="utf-8").strip()
    assert '"metrics"' in payload
    assert '"retry_count": 1' in payload
    assert '"model_cost"' in payload


def test_infer_evidence_status_distinguishes_no_match_and_filtered():
    assert OrchestratorService._infer_evidence_status({"sources": [{"source": "a"}], "buckets": []}) == "ok"
    assert OrchestratorService._infer_evidence_status({"sources": [], "buckets": []}) == "no_match"
    assert OrchestratorService._infer_evidence_status(
        {
            "sources": [],
            "buckets": [
                {
                    "result": {
                        "recalls": {"vector": [{"doc_id": "1"}], "bm25": [], "graph": []},
                        "judge": [{"doc_id": "1", "judge_keep": False}],
                    }
                }
            ],
        }
    ) == "filtered_out"
