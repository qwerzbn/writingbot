from __future__ import annotations

from pathlib import Path

import src.orchestrator.service as orchestrator_service
from src.orchestrator.models import RunExecutionContext
from src.orchestrator.run_store import RunStore


class _StubChatAgent:
    def process(
        self,
        question: str,
        evidence_text: str = "",
        skill_directive: str = "",
        chat_history: list[dict[str, str]] | None = None,
        stream: bool = False,
    ) -> dict:
        assert stream is True
        assert "ARC" in question
        assert evidence_text
        return {
            "messages": [{"role": "user", "content": question}],
            "stream": iter(["第一段回答。", "第二段回答。"]),
        }


class _StubService(orchestrator_service.OrchestratorService):
    def __init__(self, tmp_path: Path):
        self.run_store = RunStore(ttl_hours=2)
        self.hybrid = None
        self.research_agent = None
        self.co_writer_agent = None
        self.metrics_file = tmp_path / "orchestrator_runs.jsonl"
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

    def _record_model_call(self, ctx, stage, messages, output) -> None:  # noqa: D401
        ctx.metadata.setdefault("model_calls", []).append(
            {"stage": stage, "message_count": len(messages), "output_length": len(output)}
        )


def test_chat_research_synthesize_uses_concrete_chat_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator_service, "ChatAgent", _StubChatAgent)
    monkeypatch.setattr(orchestrator_service, "resolve_skill_chain", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        orchestrator_service,
        "run_research_skill_chain",
        lambda **kwargs: (["围绕运行架构图解释。"], [], {"skill_success_rate": 1.0, "paper_hits": 1}),
    )

    service = _StubService(tmp_path)
    run_data = service.create_run(mode="chat_research", payload={"message": "请解释ARC的运行架构图", "kb_id": "kb-1"})
    run = service.run_store.get_run(run_data["run_id"])
    assert run is not None

    ctx = RunExecutionContext(
        run=run,
        context="这里是本地论文证据。",
        sources=[{"source": "paper.pdf", "page": 1, "content": "证据"}],
        chat_history=[{"role": "user", "content": "上一轮问题"}],
        message="请解释ARC的运行架构图",
        selected_skill_ids=[],
    )

    events = list(service._step_synthesize(ctx))

    chunks = [event["content"] for event in events if event.get("type") == "chunk"]
    assert chunks == ["第一段回答。", "第二段回答。"]
    assert ctx.generated_text == "第一段回答。第二段回答。"
    assert ctx.metadata["skill_success_rate"] == 1.0
