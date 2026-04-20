from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from src.agent_runtime.events import (
    build_done_event,
    build_error_event,
    build_init_event,
    build_metric_event,
    build_step_event,
)
from src.agent_runtime.state import (
    ContentMode,
    ResearchState,
    ReviewResult,
    RuntimeMode,
    RuntimeState,
    model_to_dict,
    new_content_state,
    new_research_state,
)
from src.agent_runtime.store import RunRecord, RunStore
from src.agent_runtime.validators import assert_only_owned_fields_mutated
from src.agent_workflows.content import ContentAgent, ContentExecution
from src.agent_workflows.research import PlannerAgent, ReportAgent, ReviewerAgent, SearchAgent
from src.retrieval import HybridRetrievalService
from src.retrieval.common import estimate_tokens
from src.services.llm import get_llm_config
from src.shared_capabilities.knowledge.evidence import augment_chart_evidence, normalize_paper_sources
from src.shared_capabilities.llm import llm_identity
from src.shared_capabilities.rendering.report import bind_paragraph_evidence, ensure_inference_tag
from src.shared_capabilities.retrieval import SearchBackend
from src.skills import resolve_skill_chain, run_research_skill_chain


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

LEGACY_STAGE_MAP = {
    "planning": "plan",
    "searching": "retrieve",
    "reporting": "synthesize",
    "reviewing": "critique",
    "content_generation": "synthesize",
}
LEGACY_AGENT_MAP = {
    "planning": "planning_agent",
    "searching": "search_agent",
    "reporting": "report_agent",
    "reviewing": "reviewer_agent",
    "content_generation": "content_agent",
}

PLANNER_OWNED_PATHS = {
    "research.goal",
    "research.subquestions",
    "research.search_plan",
    "research.report_outline",
    "research.repair_focus_subquestion_ids",
}
SEARCH_OWNED_PATHS = {
    "research.subquestions",
    "research.evidence_store",
    "research.coverage_status",
    "research.unresolved_gaps",
}
REPORT_OWNED_PATHS = {"research.final_report"}
REVIEWER_OWNED_PATHS = {"research.review_result"}


class AgentRuntime:
    """Canonical runtime for research and content workflows."""

    def __init__(self) -> None:
        self.run_store = RunStore(ttl_hours=2)
        self.hybrid = HybridRetrievalService()
        self.planner = PlannerAgent()
        self.reporter = ReportAgent()
        self.reviewer = ReviewerAgent()
        self.content_agent = ContentAgent()
        self.metrics_file = DATA_DIR / "metrics" / "orchestrator_runs.jsonl"
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

    def create_run(self, mode: RuntimeMode, payload: dict[str, Any]) -> dict[str, Any]:
        run = self.run_store.create_run(mode=mode, payload=payload)
        return {"run_id": run.run_id, "trace_id": run.trace_id}

    def get_run(self, run_id: str) -> RunRecord | None:
        return self.run_store.get_run(run_id)

    def get_run_detail(self, run_id: str) -> dict[str, Any] | None:
        run = self.run_store.get_run(run_id)
        if run is None:
            return None
        metrics = run.result.get("metrics") or self._build_metrics_summary_from_store(run)
        return {
            "run_id": run.run_id,
            "trace_id": run.trace_id,
            "mode": run.mode,
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "expires_at": run.expires_at.isoformat(),
            "result": run.result,
            "metrics": metrics,
        }

    def run_research_workflow(
        self,
        topic: str,
        kb_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {"topic": topic, "kb_id": kb_id}
        if not run_id or not trace_id:
            created = self.create_run(mode="research", payload=payload)
            run_id = created["run_id"]
            trace_id = created["trace_id"]
        result = self._execute_existing_run(run_id)
        result["run_id"] = run_id
        result["trace_id"] = trace_id
        return result

    def stream_research_workflow(
        self,
        topic: str,
        kb_id: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        created = self.create_run(mode="research", payload={"topic": topic, "kb_id": kb_id})
        plan_sent = False
        for event in self.stream_run(created["run_id"]):
            etype = event.get("type")
            if etype == "done":
                if not plan_sent and event.get("plan"):
                    yield {"type": "plan", "content": event.get("plan", "")}
                yield {
                    "type": "done",
                    "run_id": event.get("run_id"),
                    "trace_id": event.get("trace_id"),
                    "output": event.get("output", ""),
                    "sources": event.get("sources", []),
                    "plan": event.get("plan", ""),
                    "meta": event.get("meta", {}),
                }
            elif etype == "sources":
                yield {
                    "type": "sources",
                    "data": event.get("data", []),
                    "meta": event.get("meta", {}),
                    "run_id": event.get("run_id"),
                    "trace_id": event.get("trace_id"),
                }
            elif etype == "chunk":
                yield {
                    "type": "chunk",
                    "content": event.get("content", ""),
                    "run_id": event.get("run_id"),
                    "trace_id": event.get("trace_id"),
                }
            elif etype == "step" and event.get("step") == "plan" and event.get("status") == "done" and not plan_sent:
                run = self.get_run(created["run_id"])
                if run and (run.result or {}).get("plan"):
                    yield {
                        "type": "plan",
                        "content": run.result.get("plan", ""),
                        "run_id": created["run_id"],
                        "trace_id": created["trace_id"],
                    }
                    plan_sent = True

    def execute_sync(self, mode: RuntimeMode, payload: dict[str, Any]) -> dict[str, Any]:
        run = self.create_run(mode=mode, payload=payload)
        result = self._execute_existing_run(run["run_id"])
        result["run_id"] = run["run_id"]
        result["trace_id"] = run["trace_id"]
        return result

    def prepare_content_execution(
        self,
        mode: ContentMode,
        payload: dict[str, Any],
        *,
        stream: bool,
    ) -> ContentExecution:
        state, _, _ = self._prepare_content_state(mode, payload)
        execution = self.content_agent.execute(state, stream=stream)
        state.diagnostics.metrics["messages"] = list(execution.messages)
        if stream:
            return execution
        state.content.output_text = execution.content or ""
        state.content.output_sources = list(state.content.evidence_bundle)
        if mode == "chat":
            state.content.output_text = self._postprocess_chat_output(
                state.content.output_text,
                state.content.output_sources,
            )
        execution.content = state.content.output_text
        return execution

    def stream_run(self, run_id: str) -> Generator[dict[str, Any], None, None]:
        run = self.run_store.get_run(run_id)
        if run is None:
            yield build_error_event(f"run not found: {run_id}")
            return

        started_at = time.time()
        self.run_store.set_status(run_id, "running")
        yield build_init_event(run.run_id, run.trace_id, run.mode)

        try:
            generator = self._stream_research_run(run) if run.mode == "research" else self._stream_content_run(run)
            for event in generator:
                yield event
        except Exception as exc:  # noqa: BLE001
            self.run_store.set_status(run.run_id, "failed")
            run.result.update({"error": str(exc)})
            self._append_run_log(
                run_id=run.run_id,
                trace_id=run.trace_id,
                status="failed",
                total_ms=int((time.time() - started_at) * 1000),
                mode=run.mode,
                metrics=run.result.get("metrics"),
            )
            yield build_error_event(str(exc), trace_id=run.trace_id)
            return

        self._append_run_log(
            run_id=run.run_id,
            trace_id=run.trace_id,
            status=run.status,
            total_ms=int((time.time() - started_at) * 1000),
            mode=run.mode,
            metrics=run.result.get("metrics"),
        )

    def _execute_existing_run(self, run_id: str) -> dict[str, Any]:
        output = ""
        sources: list[dict[str, Any]] = []
        final_event: dict[str, Any] = {}
        for event in self.stream_run(run_id):
            etype = event.get("type")
            if etype == "chunk":
                output += str(event.get("content") or "")
            elif etype == "sources":
                data = event.get("data")
                if isinstance(data, list):
                    sources = data
            elif etype == "done":
                final_event = event
            elif etype == "error":
                raise RuntimeError(str(event.get("error") or "runtime execution failed"))

        run = self.run_store.get_run(run_id)
        if run is None:
            raise RuntimeError(f"run not found after execution: {run_id}")

        metadata = {
            "run_id": run.run_id,
            "trace_id": run.trace_id,
            "metrics": run.result.get("metrics", {}),
            "runtime_state": run.result.get("runtime_state"),
            "paper_workflow": run.result.get("paper_workflow"),
            "meta": run.result.get("meta", {}),
            "plan": run.result.get("plan", final_event.get("plan", "")),
        }
        return {
            "run_id": run.run_id,
            "trace_id": run.trace_id,
            "output": final_event.get("output", run.result.get("output", output)),
            "sources": final_event.get("sources", run.result.get("sources", sources)),
            "plan": final_event.get("plan", run.result.get("plan", "")),
            "state": run.result.get("state"),
            "metadata": metadata,
        }

    def _stream_research_run(self, run: RunRecord) -> Generator[dict[str, Any], None, None]:
        payload = run.payload or {}
        topic = str(payload.get("topic") or "").strip()
        backend = self._research_backend(payload)
        search_agent = SearchAgent(backend)
        state = new_research_state(topic)
        for field_name in (
            "max_search_rounds",
            "max_queries_per_round",
            "max_results_per_query",
            "max_replans",
            "max_repair_passes",
        ):
            if payload.get(field_name) is not None:
                setattr(state.control, field_name, int(payload[field_name]))
        timings: dict[str, int] = {}

        yield self._step_event("planning", "working", run, attempt=1)
        state, plan_duration = self._run_planner(state)
        timings["plan"] = plan_duration
        run.result["plan"] = self._render_plan(state.research)
        yield self._step_event("planning", "done", run, attempt=1, duration_ms=plan_duration)

        while not state.control.report_ready:
            if state.control.current_search_round >= state.control.max_search_rounds:
                state.control.search_budget_exhausted = True
                state.control.report_ready = True
                self._mark_budget_exhausted(state)
                break

            round_index = state.control.current_search_round + 1
            yield self._step_event("searching", "working", run, attempt=round_index)
            search_started = time.perf_counter()
            before = state.model_copy(deep=True)
            outcome = search_agent.run(state, round_index=round_index)
            assert_only_owned_fields_mutated(
                before,
                state,
                owner="SearchAgent",
                allowed_paths=SEARCH_OWNED_PATHS,
            )
            duration_ms = max(0, int((time.perf_counter() - search_started) * 1000))
            timings["retrieve"] = timings.get("retrieve", 0) + duration_ms
            state.control.current_search_round = outcome.round_index
            state.control.search_budget_exhausted = bool(outcome.budget_exhausted) or (
                state.control.current_search_round >= state.control.max_search_rounds
            )
            if state.control.search_budget_exhausted:
                self._mark_budget_exhausted(state)
            state.control.report_ready = bool(outcome.report_ready or state.research.coverage_status.ready_for_report)
            state.diagnostics.stage_history.append(
                {
                    "stage": "searching",
                    "attempt": round_index,
                    "duration_ms": duration_ms,
                    "new_items": outcome.new_items,
                    "results_retrieved": outcome.results_retrieved,
                }
            )
            yield self._step_event("searching", "done", run, attempt=round_index, duration_ms=duration_ms)
            yield build_metric_event(
                "step_retrieve_ms",
                duration_ms,
                "ms",
                step="retrieve",
                attempt=round_index,
                trace_id=run.trace_id,
            )

            if state.control.report_ready:
                break

            if outcome.replan_requested and state.control.replans_used < state.control.max_replans:
                state.control.replans_used += 1
                state.research.repair_focus_subquestion_ids = list(outcome.focus_subquestion_ids)
                yield self._step_event(
                    "planning",
                    "working",
                    run,
                    attempt=state.control.replans_used + 1,
                    message="replanning",
                )
                state, duration_ms = self._run_planner(state)
                timings["plan"] = timings.get("plan", 0) + duration_ms
                yield self._step_event(
                    "planning",
                    "done",
                    run,
                    attempt=state.control.replans_used + 1,
                    duration_ms=duration_ms,
                    message="replanned",
                )

            if state.control.current_search_round >= state.control.max_search_rounds:
                state.control.search_budget_exhausted = True
                state.control.report_ready = True
                self._mark_budget_exhausted(state)

        yield self._step_event("reporting", "working", run, attempt=1)
        report_started = time.perf_counter()
        state = self._run_reporter(state)
        report_duration = max(0, int((time.perf_counter() - report_started) * 1000))
        timings["synthesize"] = report_duration
        yield self._step_event("reporting", "done", run, attempt=1, duration_ms=report_duration)

        repair_notes: list[str] = []
        review_attempt = 1
        while True:
            yield self._step_event("reviewing", "working", run, attempt=review_attempt)
            review_started = time.perf_counter()
            state = self._run_reviewer(state)
            review_duration = max(0, int((time.perf_counter() - review_started) * 1000))
            timings["critique"] = timings.get("critique", 0) + review_duration
            yield self._step_event("reviewing", "done", run, attempt=review_attempt, duration_ms=review_duration)

            review = state.research.review_result or ReviewResult()
            if not review.blocking or state.control.repair_passes_used >= state.control.max_repair_passes:
                break

            state.control.repair_passes_used += 1
            repair_notes = [issue.message for issue in review.issues]
            if review.repair_action == "report_repair":
                yield self._step_event(
                    "reporting",
                    "working",
                    run,
                    attempt=state.control.repair_passes_used + 1,
                    message="repairing report",
                )
                state = self._run_reporter(state, repair_notes=repair_notes)
                yield self._step_event(
                    "reporting",
                    "done",
                    run,
                    attempt=state.control.repair_passes_used + 1,
                    message="report repaired",
                )
                review_attempt += 1
                continue

            if review.repair_action == "search_repair":
                focus_ids = review.missing_high_priority_subquestions or [
                    entry.subquestion_id
                    for entry in state.research.coverage_status.subquestions
                    if entry.status != "covered"
                ]
                state.research.repair_focus_subquestion_ids = list(focus_ids)
                yield self._step_event(
                    "planning",
                    "working",
                    run,
                    attempt=state.control.repair_passes_used + 1,
                    message="repair replanning",
                )
                state, duration_ms = self._run_planner(state)
                timings["plan"] = timings.get("plan", 0) + duration_ms
                yield self._step_event(
                    "planning",
                    "done",
                    run,
                    attempt=state.control.repair_passes_used + 1,
                    duration_ms=duration_ms,
                    message="repair plan ready",
                )

                if state.control.current_search_round < state.control.max_search_rounds:
                    repair_round = state.control.current_search_round + 1
                    yield self._step_event("searching", "working", run, attempt=repair_round, message="repair search")
                    before = state.model_copy(deep=True)
                    outcome = search_agent.run(state, round_index=repair_round)
                    assert_only_owned_fields_mutated(
                        before,
                        state,
                        owner="SearchAgent",
                        allowed_paths=SEARCH_OWNED_PATHS,
                    )
                    state.control.current_search_round = outcome.round_index
                    state.control.search_budget_exhausted = bool(outcome.budget_exhausted) or (
                        state.control.current_search_round >= state.control.max_search_rounds
                    )
                    state.control.report_ready = True
                    if state.control.search_budget_exhausted:
                        self._mark_budget_exhausted(state)
                    yield self._step_event("searching", "done", run, attempt=repair_round, message="repair search done")
                else:
                    state.control.search_budget_exhausted = True
                    state.control.report_ready = True
                    self._mark_budget_exhausted(state)

                yield self._step_event(
                    "reporting",
                    "working",
                    run,
                    attempt=state.control.repair_passes_used + 1,
                    message="rebuilding report",
                )
                state = self._run_reporter(state, repair_notes=repair_notes)
                yield self._step_event(
                    "reporting",
                    "done",
                    run,
                    attempt=state.control.repair_passes_used + 1,
                    message="repair report ready",
                )
                review_attempt += 1
                continue

            break

        state.control.current_stage = "complete"
        final_report = state.research.final_report
        output = final_report.rendered_markdown if final_report else ""
        sources = self._research_sources(state.research)
        meta = self._research_meta(state)
        metrics = self._research_metrics(state, sources, timings)
        result_payload = {
            "output": output,
            "sources": sources,
            "plan": self._render_plan(state.research),
            "metrics": metrics,
            "runtime_state": model_to_dict(state),
            "paper_workflow": self._legacy_paper_workflow(state),
            "meta": meta,
            "state": state,
        }
        self.run_store.set_result(run.run_id, result_payload)
        self.run_store.set_status(run.run_id, "done")
        yield {
            "type": "sources",
            "run_id": run.run_id,
            "trace_id": run.trace_id,
            "data": sources,
            "meta": meta,
        }
        for chunk in self._chunk_text(output, size=220):
            yield {"type": "chunk", "run_id": run.run_id, "trace_id": run.trace_id, "content": chunk}
        yield build_done_event(
            run_id=run.run_id,
            trace_id=run.trace_id,
            output=output,
            sources=sources,
            plan=result_payload["plan"],
            metrics=metrics,
            meta=meta,
        )

    def _stream_content_run(self, run: RunRecord) -> Generator[dict[str, Any], None, None]:
        payload = run.payload or {}
        mode = "chat" if run.mode == "chat_research" else str(payload.get("action") or "rewrite")
        state, evidence_meta, skill_meta = self._prepare_content_state(mode, payload)
        timings: dict[str, int] = {}

        yield self._step_event("planning", "working", run, attempt=1)
        yield self._step_event("planning", "done", run, attempt=1, duration_ms=1)
        if state.content and state.content.output_sources:
            yield self._step_event("searching", "working", run, attempt=1)
            yield self._step_event("searching", "done", run, attempt=1, duration_ms=1)

        yield self._step_event("content_generation", "working", run, attempt=1)
        synth_started = time.perf_counter()
        execution = self.content_agent.execute(state, stream=False)
        state.diagnostics.metrics["messages"] = list(execution.messages)
        content = execution.content or ""
        if state.content is None:
            raise ValueError("content state is required")
        if state.content.mode == "chat":
            content = self._postprocess_chat_output(content, state.content.output_sources)
        state.content.output_text = content
        duration_ms = max(0, int((time.perf_counter() - synth_started) * 1000))
        timings["synthesize"] = duration_ms
        yield self._step_event("content_generation", "done", run, attempt=1, duration_ms=duration_ms)

        yield self._step_event("reviewing", "working", run, attempt=1)
        critique_started = time.perf_counter()
        review_meta = self._content_review(state)
        critique_duration = max(0, int((time.perf_counter() - critique_started) * 1000))
        timings["critique"] = critique_duration
        yield self._step_event("reviewing", "done", run, attempt=1, duration_ms=critique_duration)

        identity = llm_identity()
        metrics = self._content_metrics(
            state=state,
            timings=timings,
            evidence_meta=evidence_meta,
            skill_meta=skill_meta,
            review_meta=review_meta,
            identity=identity,
        )
        meta = {
            "paper_hits": skill_meta.get("paper_hits", 0),
            "citation_coverage": review_meta.get("citation_coverage", 0.0),
            "skill_success_rate": skill_meta.get("skill_success_rate", 0.0),
            "inference_ratio": review_meta.get("inference_ratio", 0.0),
            "evidence_status": evidence_meta.get("evidence_status", "unknown"),
            "asset_hits": evidence_meta.get("asset_hits", 0),
        }
        result_payload = {
            "output": state.content.output_text,
            "sources": list(state.content.output_sources),
            "plan": "",
            "metrics": metrics,
            "runtime_state": model_to_dict(state),
            "paper_workflow": self._legacy_paper_workflow(state),
            "meta": meta,
            "state": state,
        }
        self.run_store.set_result(run.run_id, result_payload)
        self.run_store.set_status(run.run_id, "done")

        for chunk in self._chunk_text(state.content.output_text, size=180):
            yield {"type": "chunk", "run_id": run.run_id, "trace_id": run.trace_id, "content": chunk}
        if state.content.output_sources:
            yield {
                "type": "sources",
                "run_id": run.run_id,
                "trace_id": run.trace_id,
                "data": list(state.content.output_sources),
                "meta": meta,
            }
        yield build_done_event(
            run_id=run.run_id,
            trace_id=run.trace_id,
            output=state.content.output_text,
            sources=list(state.content.output_sources),
            metrics=metrics,
            meta=meta,
        )

    def _prepare_content_state(
        self,
        mode: str,
        payload: dict[str, Any],
    ) -> tuple[RuntimeState, dict[str, Any], dict[str, Any]]:
        if mode == "chat":
            user_input = str(payload.get("message") or "").strip()
            history = list(payload.get("history") or [])
            state = new_content_state(user_input, mode="chat", history=history)
            bundle = self._retrieve_content_bundle(
                query=user_input,
                kb_id=payload.get("kb_id"),
                top_k=int(payload.get("top_k") or 8),
            )
            skill_meta = self._resolve_chat_skill_meta(
                skill_ids=list(payload.get("skill_ids") or []),
                has_kb=bool(payload.get("kb_id")),
                sources=bundle.get("sources", []),
            )
            state.content.context_text = str(bundle.get("context") or "")
            state.content.output_sources = list(bundle.get("sources", []))
            state.content.evidence_bundle = list(bundle.get("sources", []))
            state.content.skill_directive = "\n".join(skill_meta.get("instructions", []))
            return state, bundle, skill_meta

        action = str(mode or payload.get("action") or "rewrite").strip().lower()
        if action not in {"rewrite", "expand", "shorten", "polish"}:
            action = "rewrite"
        text = str(payload.get("text") or "").strip()
        instruction = str(payload.get("instruction") or "").strip()
        state = new_content_state(text, mode=action, instruction=instruction)
        include_evidence = bool(payload.get("include_evidence", True))
        bundle = (
            self._retrieve_content_bundle(
                query=instruction or text[:400],
                kb_id=payload.get("kb_id"),
                top_k=int(payload.get("top_k") or 5),
            )
            if include_evidence
            else {"sources": [], "context": "", "asset_hits": 0, "evidence_status": "unknown"}
        )
        state.content.evidence_bundle = list(bundle.get("sources", []))
        state.content.output_sources = list(bundle.get("sources", []))
        return state, bundle, {"instructions": [], "runs": [], "skill_success_rate": 0.0, "paper_hits": 0}

    def _retrieve_content_bundle(
        self,
        *,
        query: str,
        kb_id: str | None,
        top_k: int,
    ) -> dict[str, Any]:
        query = str(query or "").strip()
        if not query or not kb_id:
            return {"sources": [], "context": "", "asset_hits": 0, "evidence_status": "no_match"}

        backend = SearchBackend.from_kb(kb_id, data_dir=DATA_DIR / "knowledge_bases")
        if backend.vector_store is None:
            return {"sources": [], "context": "", "asset_hits": 0, "evidence_status": "no_match"}

        result = self.hybrid.retrieve(
            kb_id=kb_id,
            vector_store=backend.vector_store,
            query=query,
            top_k=top_k,
        )
        augmented = augment_chart_evidence(
            kb_id=kb_id,
            query=query,
            context=result.get("context_window", {}).get("context", ""),
            sources=result.get("sources", []) or [],
            data_dir=DATA_DIR / "knowledge_bases",
        )
        sources = augmented.get("sources")
        if not isinstance(sources, list):
            sources = normalize_paper_sources(result.get("sources", []) or [])
        evidence_status = self._infer_evidence_status(
            {"sources": sources, "buckets": [{"result": result}]},
        )
        return {
            "query": query,
            "context": str(augmented.get("context") or result.get("context_window", {}).get("context", "")),
            "sources": list(sources),
            "asset_hits": int(augmented.get("asset_hits") or 0),
            "evidence_status": evidence_status,
        }

    def _resolve_chat_skill_meta(
        self,
        *,
        skill_ids: list[str],
        has_kb: bool,
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        skills = resolve_skill_chain(skill_ids, domain="research")
        instructions, runs, metrics = run_research_skill_chain(
            skills=skills,
            has_kb=has_kb,
            sources=sources,
        )
        return {
            "instructions": instructions,
            "runs": runs,
            "skill_success_rate": metrics.get("skill_success_rate", 0.0),
            "paper_hits": metrics.get("paper_hits", 0),
        }

    def _run_planner(self, state: RuntimeState) -> tuple[RuntimeState, int]:
        before = state.model_copy(deep=True)
        started = time.perf_counter()
        state = self.planner.run(state)
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        assert_only_owned_fields_mutated(
            before,
            state,
            owner="PlannerAgent",
            allowed_paths=PLANNER_OWNED_PATHS,
        )
        state.control.current_stage = "searching"
        state.diagnostics.stage_history.append({"stage": "planning", "duration_ms": duration_ms})
        return state, duration_ms

    def _run_reporter(self, state: RuntimeState, *, repair_notes: list[str] | None = None) -> RuntimeState:
        before = state.model_copy(deep=True)
        state = self.reporter.run(state, repair_notes=repair_notes)
        assert_only_owned_fields_mutated(
            before,
            state,
            owner="ReportAgent",
            allowed_paths=REPORT_OWNED_PATHS,
        )
        state.control.current_stage = "reviewing"
        return state

    def _run_reviewer(self, state: RuntimeState) -> RuntimeState:
        before = state.model_copy(deep=True)
        state = self.reviewer.run(state)
        assert_only_owned_fields_mutated(
            before,
            state,
            owner="ReviewerAgent",
            allowed_paths=REVIEWER_OWNED_PATHS,
        )
        return state

    def _research_backend(self, payload: dict[str, Any]) -> SearchBackend:
        vector_store = payload.get("vector_store")
        if vector_store is not None:
            return SearchBackend.from_vector_store(vector_store=vector_store)
        kb_id = payload.get("kb_id")
        if kb_id:
            return SearchBackend.from_kb(kb_id, data_dir=DATA_DIR / "knowledge_bases")
        return SearchBackend.disabled("No knowledge base selected")

    @staticmethod
    def _render_plan(research: ResearchState) -> str:
        return "\n".join(f"- {item.question}" for item in research.subquestions)

    @staticmethod
    def _research_sources(research: ResearchState) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in research.evidence_store.items:
            rows.append(
                {
                    "id": item.evidence_id,
                    "source": item.source_id,
                    "page": item.metadata.get("page", "?"),
                    "title": item.source_title,
                    "locator": item.locator,
                    "excerpt": item.snippet,
                    "content": item.snippet,
                    "score": item.relevance_score,
                    "quality_score": item.quality_score,
                    "subquestion_ids": list(item.subquestion_ids),
                    "paper_id": item.metadata.get("paper_id") or item.source_id,
                    "file_id": item.metadata.get("file_id"),
                }
            )
        return rows

    def _research_meta(self, state: RuntimeState) -> dict[str, Any]:
        research = state.research
        if research is None:
            return {}
        review = research.review_result or ReviewResult()
        return {
            "coverage_status": research.coverage_status.overall,
            "covered_ratio": research.coverage_status.covered_ratio,
            "high_priority_complete": research.coverage_status.high_priority_complete,
            "ready_for_report": research.coverage_status.ready_for_report,
            "halt_reason": state.control.halt_reason,
            "search_rounds": state.control.current_search_round,
            "search_budget_exhausted": state.control.search_budget_exhausted,
            "replans_used": state.control.replans_used,
            "repair_passes_used": state.control.repair_passes_used,
            "unresolved_gaps": [gap.description for gap in research.unresolved_gaps],
            "review_summary": review.summary,
            "review_blocking": review.blocking,
            "review_action": review.repair_action,
        }

    def _research_metrics(
        self,
        state: RuntimeState,
        sources: list[dict[str, Any]],
        timings: dict[str, int],
    ) -> dict[str, Any]:
        identity = llm_identity()
        citation_coverage = 0.0
        inference_ratio = 0.0
        if state.research and state.research.final_report:
            statements = [
                statement
                for section in state.research.final_report.sections
                for statement in section.statements
            ]
            if statements:
                cited = sum(1 for statement in statements if statement.evidence_ids)
                tentative = sum(1 for statement in statements if statement.support_status == "tentative_inference")
                citation_coverage = round(cited / max(1, len(statements)), 4)
                inference_ratio = round(tentative / max(1, len(statements)), 4)

        return {
            "stage_timings_ms": {
                "plan": timings.get("plan", 0),
                "retrieve": timings.get("retrieve", 0),
                "synthesize": timings.get("synthesize", 0),
                "critique": timings.get("critique", 0),
            },
            "attempts": {
                "plan": max(1, state.control.replans_used + 1),
                "retrieve": max(1, state.control.current_search_round),
                "synthesize": max(1, state.control.repair_passes_used + 1),
                "critique": max(1, state.control.repair_passes_used + 1),
            },
            "retry_count": 0,
            "retry_rate": 0.0,
            "failure_count": 0,
            "failure_rate": 0.0,
            "empty_evidence_rate": 0.0 if sources else 1.0,
            "citation_missing_fix": 0,
            "source_count": len(sources),
            "evidence_status": state.research.coverage_status.overall if state.research else "unknown",
            "citation_coverage": citation_coverage,
            "paper_hit_rate": round(len({row.get("paper_id") or row.get("source") for row in sources}) / max(1, len(sources)), 4),
            "skill_success_rate": 0.0,
            "inference_ratio": inference_ratio,
            "model_calls": list(state.diagnostics.model_calls),
            "model_cost": {
                "provider": identity.get("provider", ""),
                "model": identity.get("model", ""),
                "estimated_usd": 0.0,
                "calls": len(state.diagnostics.model_calls),
            },
        }

    def _content_metrics(
        self,
        *,
        state: RuntimeState,
        timings: dict[str, int],
        evidence_meta: dict[str, Any],
        skill_meta: dict[str, Any],
        review_meta: dict[str, Any],
        identity: dict[str, str],
    ) -> dict[str, Any]:
        sources = state.content.output_sources if state.content else []
        prompt_tokens = sum(estimate_tokens(str(message.get("content") or "")) for message in state.diagnostics.metrics.get("messages", []))
        completion_tokens = estimate_tokens(state.content.output_text if state.content else "")
        return {
            "stage_timings_ms": {
                "plan": 1,
                "retrieve": 1 if sources else 0,
                "synthesize": timings.get("synthesize", 0),
                "critique": timings.get("critique", 0),
            },
            "attempts": {"plan": 1, "retrieve": 1 if sources else 0, "synthesize": 1, "critique": 1},
            "retry_count": 0,
            "retry_rate": 0.0,
            "failure_count": 0,
            "failure_rate": 0.0,
            "empty_evidence_rate": 0.0 if sources else 1.0,
            "citation_missing_fix": int(review_meta.get("citation_missing_fix", 0)),
            "source_count": len(sources),
            "evidence_status": evidence_meta.get("evidence_status", "unknown"),
            "citation_coverage": float(review_meta.get("citation_coverage", 0.0)),
            "paper_hit_rate": float(skill_meta.get("paper_hits", 0)),
            "skill_success_rate": float(skill_meta.get("skill_success_rate", 0.0)),
            "inference_ratio": float(review_meta.get("inference_ratio", 0.0)),
            "model_calls": [
                {
                    "provider": identity.get("provider", ""),
                    "model": identity.get("model", ""),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "estimated_usd": 0.0,
                }
            ],
            "model_cost": {
                "provider": identity.get("provider", ""),
                "model": identity.get("model", ""),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "estimated_usd": 0.0,
                "calls": 1,
            },
        }

    def _content_review(self, state: RuntimeState) -> dict[str, Any]:
        if state.content is None:
            return {"citation_coverage": 0.0, "inference_ratio": 0.0, "citation_missing_fix": 0}
        parts = [part.strip() for part in state.content.output_text.split("\n\n") if part.strip()]
        cited_parts = sum(1 for part in parts if re.search(r"\[[0-9]+\]", part))
        inference_parts = sum(1 for part in parts if "(inference)" in part)
        return {
            "citation_coverage": round(cited_parts / max(1, len(parts)), 4),
            "inference_ratio": round(inference_parts / max(1, len(parts)), 4),
            "citation_missing_fix": int(bool(state.content.output_sources and cited_parts == 0 and state.content.mode == "chat")),
        }

    def _postprocess_chat_output(self, text: str, sources: list[dict[str, Any]]) -> str:
        if sources:
            return bind_paragraph_evidence(text, sources)
        return ensure_inference_tag(text)

    def _step_event(
        self,
        stage: str,
        status: str,
        run: RunRecord,
        *,
        attempt: int,
        message: str = "",
        duration_ms: int | None = None,
    ) -> dict[str, Any]:
        return build_step_event(
            LEGACY_STAGE_MAP.get(stage, stage),
            status,
            attempt=attempt,
            message=message,
            duration_ms=duration_ms,
            trace_id=run.trace_id,
            agent_id=LEGACY_AGENT_MAP.get(stage, stage),
        )

    @staticmethod
    def _chunk_text(text: str, size: int = 200) -> list[str]:
        if not text:
            return []
        return [text[i : i + size] for i in range(0, len(text), size)]

    @staticmethod
    def _mark_budget_exhausted(state: RuntimeState) -> None:
        if state.research is None:
            return
        state.research.coverage_status.overall = "exhausted"
        for gap in state.research.unresolved_gaps:
            if gap.reason in {"no_hits", "plan_gap"}:
                gap.reason = "budget_exhausted"

    @staticmethod
    def _infer_evidence_status(bundle: dict[str, Any]) -> str:
        sources = bundle.get("sources", []) or []
        if sources:
            return "ok"
        buckets = bundle.get("buckets", []) or []
        total_recalled = 0
        total_judged = 0
        for bucket in buckets:
            result = bucket.get("result", {}) or {}
            recalls = result.get("recalls", {}) or {}
            total_recalled += len(recalls.get("vector", []) or [])
            total_recalled += len(recalls.get("bm25", []) or [])
            total_recalled += len(recalls.get("graph", []) or [])
            total_judged += len(result.get("judge", []) or [])
        if total_recalled == 0:
            return "no_match"
        if total_judged > 0:
            return "filtered_out"
        return "no_match"

    def _append_run_log(
        self,
        *,
        run_id: str,
        trace_id: str,
        status: str,
        total_ms: int,
        mode: str,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "run_id": run_id,
            "trace_id": trace_id,
            "status": status,
            "total_ms": total_ms,
            "mode": mode,
            "timestamp": datetime.now().isoformat(),
        }
        if metrics is not None:
            payload["metrics"] = metrics
        with open(self.metrics_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @staticmethod
    def _build_metrics_summary_from_store(run: RunRecord) -> dict[str, Any]:
        identity = get_llm_config()
        summary: dict[str, Any] = {
            "stage_timings_ms": {},
            "attempts": {},
            "retry_count": 0,
            "retry_rate": 0.0,
            "failure_count": 0,
            "failure_rate": 0.0,
            "empty_evidence_rate": 0.0,
            "citation_missing_fix": 0,
            "source_count": len((run.result or {}).get("sources", []) or []),
            "evidence_status": (run.result or {}).get("meta", {}).get("evidence_status", "unknown"),
            "citation_coverage": 0.0,
            "paper_hit_rate": 0.0,
            "skill_success_rate": 0.0,
            "inference_ratio": 0.0,
            "model_calls": [],
            "model_cost": {"provider": identity.provider, "model": identity.model, "estimated_usd": 0.0},
        }
        for metric in getattr(run, "metrics", []) or []:
            name = metric.get("name")
            step = metric.get("step")
            attempt = metric.get("attempt")
            value = metric.get("value")
            if name and name.startswith("step_") and name.endswith("_ms") and step:
                summary["stage_timings_ms"][step] = value
            if attempt and step:
                summary["attempts"][step] = attempt
        total_attempts = sum(int(value) for value in summary["attempts"].values()) or 1
        summary["retry_rate"] = round(summary["retry_count"] / total_attempts, 4)
        summary["failure_rate"] = round(summary["failure_count"] / total_attempts, 4)
        return summary

    @staticmethod
    def _legacy_paper_workflow(state: RuntimeState) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "user_task": state.user_task,
            "control_flags": {
                "current_stage": state.control.current_stage,
                "max_search_rounds": state.control.max_search_rounds,
                "current_search_round": state.control.current_search_round,
                "max_queries_per_round": state.control.max_queries_per_round,
                "max_results_per_query": state.control.max_results_per_query,
                "max_replans": state.control.max_replans,
                "replans_used": state.control.replans_used,
                "replan_requested": bool(state.research and state.research.repair_focus_subquestion_ids),
                "search_budget_exhausted": state.control.search_budget_exhausted,
                "report_ready": state.control.report_ready,
                "halt_reason": state.control.halt_reason,
            },
        }
        if state.research is not None:
            payload.update(
                {
                    "research_goal": model_to_dict(state.research.goal),
                    "subquestions": model_to_dict(state.research).get("subquestions", []),
                    "search_plan": model_to_dict(state.research.search_plan),
                    "evidence_store": model_to_dict(state.research.evidence_store),
                    "coverage_status": model_to_dict(state.research.coverage_status),
                    "unresolved_gaps": model_to_dict(state.research).get("unresolved_gaps", []),
                    "report_outline": model_to_dict(state.research.report_outline),
                    "final_report": model_to_dict(state.research.final_report) if state.research.final_report else None,
                    "review_result": model_to_dict(state.research.review_result) if state.research.review_result else None,
                }
            )
        return payload


_agent_runtime: AgentRuntime | None = None


def get_agent_runtime() -> AgentRuntime:
    global _agent_runtime
    if _agent_runtime is None:
        _agent_runtime = AgentRuntime()
    return _agent_runtime
