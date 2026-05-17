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
    build_step_event,
)
from src.agent_runtime.state import (
    ContentMode,
    RuntimeMode,
    RuntimeState,
    model_to_dict,
    new_content_state,
)
from src.agent_runtime.store import RunRecord, RunStore
from src.agent_workflows.content import ContentAgent, ContentExecution
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
    "content_generation": "synthesize",
    "reviewing": "critique",
}
LEGACY_AGENT_MAP = {
    "planning": "planning_agent",
    "searching": "search_agent",
    "content_generation": "content_agent",
    "reviewing": "reviewer_agent",
}


class AgentRuntime:
    """Canonical runtime for content workflows."""

    def __init__(self) -> None:
        self.run_store = RunStore(ttl_hours=2)
        self.hybrid = HybridRetrievalService()
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
            yield from self._stream_content_run(run)
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
        execution = self.content_agent.execute(state, stream=True)
        state.diagnostics.metrics["messages"] = list(execution.messages)
        content_parts: list[str] = []
        if execution.stream is not None:
            for raw_chunk in execution.stream:
                chunk = str(raw_chunk or "")
                if not chunk:
                    continue
                content_parts.append(chunk)
                yield {"type": "chunk", "run_id": run.run_id, "trace_id": run.trace_id, "content": chunk}

        content = "".join(content_parts) or execution.content or ""
        if state.content is None:
            raise ValueError("content state is required")
        if state.content.mode == "chat":
            content = self._postprocess_chat_output(content, state.content.output_sources)
        streamed_content = "".join(content_parts)
        if content != streamed_content:
            if streamed_content and content.startswith(streamed_content):
                suffix = content[len(streamed_content) :]
                if suffix:
                    yield {"type": "chunk", "run_id": run.run_id, "trace_id": run.trace_id, "content": suffix}
            elif not streamed_content:
                for chunk in self._chunk_text(content, size=180):
                    yield {"type": "chunk", "run_id": run.run_id, "trace_id": run.trace_id, "content": chunk}
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
            manual_context = str(payload.get("context_text") or "").strip()
            manual_skill_directive = str(payload.get("skill_directive") or "").strip()
            manual_sources = payload.get("sources") or payload.get("evidence") or []
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
            sources = list(bundle.get("sources", []))
            if isinstance(manual_sources, list) and manual_sources:
                sources = list(manual_sources)
            instructions = [manual_skill_directive] if manual_skill_directive else []
            instructions.extend(skill_meta.get("instructions", []))
            state.content.context_text = manual_context or str(bundle.get("context") or "")
            state.content.output_sources = sources
            state.content.evidence_bundle = sources
            state.content.skill_directive = "\n".join(instructions)
            return state, bundle, skill_meta

        action = str(mode or payload.get("action") or "rewrite").strip().lower()
        if action not in {"rewrite", "expand", "shorten", "polish"}:
            action = "rewrite"
        text = str(payload.get("text") or "").strip()
        instruction = str(payload.get("instruction") or "").strip()
        state = new_content_state(text, mode=action, instruction=instruction)
        include_evidence = bool(payload.get("include_evidence", True))
        manual_evidence = payload.get("evidence") or payload.get("sources") or []
        bundle = (
            self._retrieve_content_bundle(
                query=instruction or text[:400],
                kb_id=payload.get("kb_id"),
                top_k=int(payload.get("top_k") or 5),
            )
            if include_evidence
            else {"sources": [], "context": "", "asset_hits": 0, "evidence_status": "unknown"}
        )
        sources = list(bundle.get("sources", []))
        if isinstance(manual_evidence, list) and manual_evidence:
            sources = list(manual_evidence)
        state.content.evidence_bundle = sources
        state.content.output_sources = sources
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

        backend = SearchBackend.from_kb(kb_id, data_dir=DATA_DIR)
        if backend.vector_store is None:
            return {"sources": [], "context": "", "asset_hits": 0, "evidence_status": "no_match"}

        try:
            result = self.hybrid.retrieve(
                kb_id=kb_id,
                vector_store=backend.vector_store,
                query=query,
                top_k=top_k,
            )
        except Exception as exc:
            return {"sources": [], "context": "", "asset_hits": 0, "evidence_status": "no_match", "error": str(exc)}

        augmented = augment_chart_evidence(
            kb_id=kb_id,
            query=query,
            context=result.get("context_window", {}).get("context", ""),
            sources=result.get("sources", []) or [],
            data_dir=DATA_DIR,
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
            "timings_ms": result.get("timings_ms", {}),
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
        prompt_tokens = sum(
            estimate_tokens(str(message.get("content") or ""))
            for message in state.diagnostics.metrics.get("messages", [])
        )
        completion_tokens = estimate_tokens(state.content.output_text if state.content else "")
        return {
            "stage_timings_ms": {
                "plan": 1,
                "retrieve": 1 if sources else 0,
                "synthesize": timings.get("synthesize", 0),
                "critique": timings.get("critique", 0),
            },
            "retrieval_timings_ms": evidence_meta.get("timings_ms", {}),
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
        return {
            "user_task": state.user_task,
            "control_flags": {
                "current_stage": state.control.current_stage,
                "report_ready": state.control.report_ready,
                "halt_reason": state.control.halt_reason,
            },
            "content": model_to_dict(state.content) if state.content else None,
        }


_agent_runtime: AgentRuntime | None = None


def get_agent_runtime() -> AgentRuntime:
    global _agent_runtime
    if _agent_runtime is None:
        _agent_runtime = AgentRuntime()
    return _agent_runtime
