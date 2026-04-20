# -*- coding: utf-8 -*-
"""Legacy orchestrator facade backed by the canonical agent runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Generator

from src.agent_runtime.runtime import AgentRuntime, get_agent_runtime
from src.orchestrator.models import OrchestratorMode
from src.shared_capabilities.knowledge.evidence import augment_chart_evidence, normalize_paper_sources


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class OrchestratorService:
    """Compatibility facade that delegates execution to the canonical runtime."""

    def __init__(self, runtime: AgentRuntime | None = None):
        self._runtime = runtime or get_agent_runtime()
        self.run_store = self._runtime.run_store
        self.hybrid = self._runtime.hybrid
        self.metrics_file = self._runtime.metrics_file

    def create_run(self, mode: OrchestratorMode, payload: dict[str, Any]) -> dict[str, Any]:
        return self._runtime.create_run(mode=mode, payload=payload)

    def get_run(self, run_id: str):
        return self._runtime.get_run(run_id)

    def get_run_detail(self, run_id: str) -> dict[str, Any] | None:
        return self._runtime.get_run_detail(run_id)

    def execute_sync(self, mode: OrchestratorMode, payload: dict[str, Any]) -> dict[str, Any]:
        return self._runtime.execute_sync(mode=mode, payload=payload)

    def stream_run(self, run_id: str) -> Generator[dict[str, Any], None, None]:
        yield from self._runtime.stream_run(run_id)

    def run_research_workflow(
        self,
        topic: str,
        kb_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        return self._runtime.run_research_workflow(
            topic=topic,
            kb_id=kb_id,
            run_id=run_id,
            trace_id=trace_id,
        )

    def stream_research_workflow(
        self,
        topic: str,
        kb_id: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        yield from self._runtime.stream_research_workflow(topic=topic, kb_id=kb_id)

    def _augment_chart_evidence(
        self,
        kb_id: str,
        query: str,
        context: str,
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return augment_chart_evidence(
            kb_id=kb_id,
            query=query,
            context=context,
            sources=sources,
            data_dir=DATA_DIR / "knowledge_bases",
        )

    @staticmethod
    def _normalize_paper_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return normalize_paper_sources(sources)

    @staticmethod
    def _infer_evidence_status(bundle: dict[str, Any]) -> str:
        return AgentRuntime._infer_evidence_status(bundle)

    @staticmethod
    def _build_metrics_summary_from_store(run: Any) -> dict[str, Any]:
        return AgentRuntime._build_metrics_summary_from_store(run)

    def _append_run_log(
        self,
        run_id: str,
        trace_id: str,
        status: str,
        total_ms: int,
        mode: str,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        self._runtime._append_run_log(
            run_id=run_id,
            trace_id=trace_id,
            status=status,
            total_ms=total_ms,
            mode=mode,
            metrics=metrics,
        )


_orchestrator_service: OrchestratorService | None = None


def get_orchestrator_service() -> OrchestratorService:
    global _orchestrator_service
    if _orchestrator_service is None:
        _orchestrator_service = OrchestratorService()
    return _orchestrator_service
