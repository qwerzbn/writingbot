# -*- coding: utf-8 -*-
"""Unified orchestrator service for research/writing workflows."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from src.agents.co_writer import CoWriterAgent
from src.agents.research import ResearchAgent
from src.knowledge.kb_manager import KnowledgeBaseManager
from src.knowledge.vector_store import VectorStore
from src.orchestrator.events import (
    build_done_event,
    build_error_event,
    build_init_event,
    build_metric_event,
    build_step_event,
)
from src.orchestrator.models import OrchestratorMode, RunExecutionContext
from src.orchestrator.run_store import RunStore
from src.orchestrator.state_machine import OrchestratorStateMachine
from src.retrieval import HybridRetrievalService
from src.retrieval.common import estimate_tokens
from src.services.llm import get_llm_client
from src.services.llm.config import get_llm_config
from src.skills import resolve_skill_chain, run_research_skill_chain


PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class OrchestratorService:
    """Coordinates multi-stage execution across modes."""

    def __init__(self):
        self.run_store = RunStore(ttl_hours=2)
        self.hybrid = HybridRetrievalService()
        self.research_agent = ResearchAgent()
        self.co_writer_agent = CoWriterAgent()
        self.metrics_file = DATA_DIR / "metrics" / "orchestrator_runs.jsonl"
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _agent_for_step(mode: str, step: str) -> str:
        if mode != "chat_research":
            return step
        mapping = {
            "plan": "question_planner",
            "retrieve": "literature_retriever",
            "synthesize": "method_comparer",
            "critique": "citation_validator",
            "finalize": "academic_writer",
        }
        return mapping.get(step, step)

    def create_run(self, mode: OrchestratorMode, payload: dict[str, Any]) -> dict[str, Any]:
        run = self.run_store.create_run(mode=mode, payload=payload)
        return {"run_id": run.run_id, "trace_id": run.trace_id}

    def get_run(self, run_id: str):
        return self.run_store.get_run(run_id)

    def get_run_detail(self, run_id: str) -> dict[str, Any] | None:
        run = self.run_store.get_run(run_id)
        if not run:
            return None
        metrics_summary = run.result.get("metrics") or self._build_metrics_summary_from_store(run)
        return {
            "run_id": run.run_id,
            "trace_id": run.trace_id,
            "mode": run.mode,
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "expires_at": run.expires_at.isoformat(),
            "result": run.result,
            "metrics": metrics_summary,
        }

    def execute_sync(self, mode: OrchestratorMode, payload: dict[str, Any]) -> dict[str, Any]:
        run_data = self.create_run(mode=mode, payload=payload)
        run_id = run_data["run_id"]
        output = ""
        sources: list[dict[str, Any]] = []
        final: dict[str, Any] = {}
        for event in self.stream_run(run_id):
            if event.get("type") == "chunk":
                output += event.get("content", "")
            elif event.get("type") == "sources":
                sources = event.get("data", [])
            elif event.get("type") == "done":
                final = event
        return {
            "run_id": run_id,
            "trace_id": run_data["trace_id"],
            "output": final.get("output", output),
            "sources": final.get("sources", sources),
            "metadata": final,
        }

    def stream_run(self, run_id: str) -> Generator[dict[str, Any], None, None]:
        run = self.run_store.get_run(run_id)
        if not run:
            yield build_error_event(f"run not found: {run_id}")
            return

        self.run_store.set_status(run_id, "running")
        started_at = time.time()
        ctx = RunExecutionContext(run=run)
        fsm = OrchestratorStateMachine()
        run_metrics: dict[str, Any] = {
            "stage_timings_ms": {},
            "attempts": {},
            "retry_count": 0,
            "retry_rate": 0.0,
            "failure_count": 0,
            "failure_rate": 0.0,
            "empty_evidence_rate": 0.0,
            "citation_missing_fix": 0,
            "source_count": 0,
            "evidence_status": "unknown",
            "citation_coverage": 0.0,
            "paper_hit_rate": 0.0,
            "skill_success_rate": 0.0,
            "inference_ratio": 0.0,
            "model_calls": [],
            "model_cost": {"provider": get_llm_config().provider, "model": get_llm_config().model, "estimated_usd": 0.0},
        }
        total_attempts = 0

        yield build_init_event(run.run_id, run.trace_id, run.mode)

        for step in fsm.ORDER:
            if step == "critique":
                critical = False
            else:
                critical = True

            step_ok = False
            for attempt in range(1, 4):
                total_attempts += 1
                t0 = time.time()
                yield build_step_event(
                    step=step,
                    status="working",
                    attempt=attempt,
                    trace_id=run.trace_id,
                    agent_id=self._agent_for_step(run.mode, step),
                )
                try:
                    if step == "plan":
                        for ev in self._step_plan(ctx):
                            yield ev
                    elif step == "retrieve":
                        for ev in self._step_retrieve(ctx):
                            yield ev
                    elif step == "synthesize":
                        for ev in self._step_synthesize(ctx):
                            yield ev
                    elif step == "critique":
                        for ev in self._step_critique(ctx):
                            yield ev
                    elif step == "finalize":
                        for ev in self._step_finalize(ctx):
                            yield ev

                    duration_ms = int((time.time() - t0) * 1000)
                    yield build_step_event(
                        step=step,
                        status="done",
                        attempt=attempt,
                        duration_ms=duration_ms,
                        confidence=ctx.confidence,
                        trace_id=run.trace_id,
                        agent_id=self._agent_for_step(run.mode, step),
                    )
                    self.run_store.append_metric(
                        run.run_id,
                        {"name": f"step_{step}_ms", "value": duration_ms, "step": step, "attempt": attempt},
                    )
                    run_metrics["stage_timings_ms"][step] = duration_ms
                    run_metrics["attempts"][step] = attempt
                    yield build_metric_event(f"step_{step}_ms", duration_ms, "ms", step=step, trace_id=run.trace_id)
                    step_ok = True
                    break
                except Exception as exc:
                    retryable = attempt < 3
                    run_metrics["failure_count"] += 1
                    yield build_error_event(
                        str(exc),
                        step=step,
                        retryable=retryable,
                        attempt=attempt,
                        trace_id=run.trace_id,
                        agent_id=self._agent_for_step(run.mode, step),
                    )
                    if retryable:
                        run_metrics["retry_count"] += 1
                        yield build_step_event(
                            step=step,
                            status="retry",
                            attempt=attempt,
                            message="retrying",
                            trace_id=run.trace_id,
                            agent_id=self._agent_for_step(run.mode, step),
                        )
                        continue
                    if not critical:
                        yield build_step_event(
                            step=step,
                            status="skipped",
                            attempt=attempt,
                            message="non-critical skipped",
                            trace_id=run.trace_id,
                            agent_id=self._agent_for_step(run.mode, step),
                        )
                        run_metrics["attempts"][step] = attempt
                        step_ok = True
                        break
                    self.run_store.set_status(run.run_id, "failed")
                    run.result["error"] = str(exc)
                    run.result["metrics"] = run_metrics
                    run_metrics["retry_rate"] = round(run_metrics["retry_count"] / max(1, total_attempts), 4)
                    run_metrics["failure_rate"] = round(run_metrics["failure_count"] / max(1, total_attempts), 4)
                    self._append_run_log(
                        run_id=run.run_id,
                        trace_id=run.trace_id,
                        status="failed",
                        total_ms=int((time.time() - started_at) * 1000),
                        mode=run.mode,
                        metrics=run_metrics,
                    )
                    return

            if not step_ok:
                self.run_store.set_status(run.run_id, "failed")
                run.result["error"] = "step failed without terminal result"
                run.result["metrics"] = run_metrics
                run_metrics["retry_rate"] = round(run_metrics["retry_count"] / max(1, total_attempts), 4)
                run_metrics["failure_rate"] = round(run_metrics["failure_count"] / max(1, total_attempts), 4)
                self._append_run_log(
                    run_id=run.run_id,
                    trace_id=run.trace_id,
                    status="failed",
                    total_ms=int((time.time() - started_at) * 1000),
                    mode=run.mode,
                    metrics=run_metrics,
                )
                return

        total_ms = int((time.time() - started_at) * 1000)
        run_metrics["retry_rate"] = round(run_metrics["retry_count"] / max(1, total_attempts), 4)
        run_metrics["failure_rate"] = round(run_metrics["failure_count"] / max(1, total_attempts), 4)
        run_metrics["empty_evidence_rate"] = ctx.metadata.get("empty_evidence_rate", 0.0)
        run_metrics["citation_missing_fix"] = ctx.metadata.get("citation_missing_fix", 0)
        run_metrics["source_count"] = len(ctx.sources)
        run_metrics["evidence_status"] = ctx.metadata.get("evidence_status", "unknown")
        run_metrics["citation_coverage"] = float(ctx.metadata.get("citation_coverage", 0.0) or 0.0)
        run_metrics["paper_hit_rate"] = float(ctx.metadata.get("paper_hit_rate", 0.0) or 0.0)
        run_metrics["skill_success_rate"] = float(ctx.metadata.get("skill_success_rate", 0.0) or 0.0)
        run_metrics["inference_ratio"] = float(ctx.metadata.get("inference_ratio", 0.0) or 0.0)
        run_metrics["model_calls"] = ctx.metadata.get("model_calls", [])
        run_metrics["model_cost"] = self._summarize_model_cost(run_metrics["model_calls"])
        ctx.metadata["run_metrics"] = run_metrics
        done = build_done_event(
            run_id=run.run_id,
            trace_id=run.trace_id,
            output=ctx.generated_text,
            sources=ctx.sources,
            total_ms=total_ms,
            mode=run.mode,
            plan=ctx.plan,
            metrics=run_metrics,
            meta={
                "selected_skill_ids": ctx.selected_skill_ids,
                "skill_runs": ctx.metadata.get("skill_runs", []),
                "paper_hits": ctx.metadata.get("paper_hits", 0),
            },
        )
        self.run_store.set_result(
            run.run_id,
            {
                "output": ctx.generated_text,
                "sources": ctx.sources,
                "metrics": run_metrics,
                "evidence_status": run_metrics["evidence_status"],
                "done": done,
            },
        )
        self._append_run_log(
            run_id=run.run_id,
            trace_id=run.trace_id,
            status="done",
            total_ms=total_ms,
            mode=run.mode,
            metrics=run_metrics,
        )
        yield done

    def _step_plan(self, ctx: RunExecutionContext) -> Generator[dict[str, Any], None, None]:
        payload = ctx.run.payload
        mode = ctx.run.mode
        if mode == "research":
            topic = payload.get("topic", "").strip()
            ctx.metadata["topic"] = topic
            plan = self.research_agent.plan(topic)
            ctx.plan = plan
            ctx.sub_questions = [line.strip(" -•") for line in plan.splitlines() if line.strip().startswith(("-", "•", "1", "2", "3"))][:4]
            if not ctx.sub_questions:
                ctx.sub_questions = self.hybrid.split_sub_questions(topic)
            yield {"type": "chunk", "content": f"## 研究计划\n\n{plan}\n\n"}
            ctx.run.result["plan"] = plan
            ctx.confidence = 0.75
            return

        if mode == "chat_research":
            message = str(payload.get("message") or "").strip()
            history = payload.get("history", [])
            if not isinstance(history, list):
                history = []
            normalized_history: list[dict[str, str]] = []
            for row in history[-12:]:
                if not isinstance(row, dict):
                    continue
                role = str(row.get("role") or "").strip()
                content = str(row.get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    normalized_history.append({"role": role, "content": content})
            skill_ids = payload.get("skill_ids", [])
            if not isinstance(skill_ids, list):
                skill_ids = []
            clean_skill_ids = [str(item).strip() for item in skill_ids if str(item).strip().startswith("/")]

            ctx.message = message
            ctx.chat_history = normalized_history
            ctx.selected_skill_ids = clean_skill_ids
            ctx.sub_questions = self.hybrid.split_sub_questions(message[:1200] if message else "")
            ctx.plan = "chat_research"
            ctx.metadata["question"] = message
            ctx.metadata["selected_skill_ids"] = clean_skill_ids
            ctx.confidence = 0.72
            return

        # writing mode
        if mode == "writing":
            action = payload.get("action", "rewrite")
            instruction = payload.get("instruction", "")
            ctx.metadata["action"] = action
            ctx.metadata["instruction"] = instruction
            source_text = payload.get("text", "")
            ctx.sub_questions = self.hybrid.split_sub_questions(source_text[:600])
            ctx.plan = f"action={action}; instruction={instruction or 'none'}"
            ctx.run.result["plan"] = ctx.plan
            ctx.confidence = 0.7

    def _step_retrieve(self, ctx: RunExecutionContext) -> Generator[dict[str, Any], None, None]:
        payload = ctx.run.payload
        kb_id = payload.get("kb_id")
        if not kb_id:
            ctx.context = ""
            ctx.sources = []
            ctx.evidence = []
            ctx.metadata["evidence_status"] = "no_kb"
            yield {"type": "sources", "data": []}
            return

        vector_store = self._get_vector_store(kb_id)
        if not vector_store:
            ctx.context = ""
            ctx.sources = []
            ctx.evidence = []
            ctx.metadata["evidence_status"] = "kb_unavailable"
            yield {"type": "sources", "data": []}
            return

        mode = ctx.run.mode
        if mode == "research":
            query = ctx.metadata.get("topic") or payload.get("topic", "")
        elif mode == "chat_research":
            query = ctx.message or payload.get("message", "")
        else:
            query = payload.get("text", "")[:1200]

        bundle = self.hybrid.retrieve_by_sub_questions(
            kb_id=kb_id,
            vector_store=vector_store,
            query=query,
            token_budget=6000,
        )
        ctx.context = bundle["context"]
        normalized_sources = self._normalize_paper_sources(bundle["sources"])
        ctx.sources = normalized_sources
        ctx.evidence = normalized_sources
        ctx.metadata["retrieval_buckets"] = bundle["buckets"]
        ctx.metadata["evidence_status"] = self._infer_evidence_status(bundle)
        empty_evidence_rate = 0.0 if ctx.sources else 1.0
        ctx.metadata["empty_evidence_rate"] = empty_evidence_rate
        paper_hits = {
            str(src.get("paper_id") or src.get("file_id") or src.get("source") or "").strip()
            for src in ctx.sources
            if isinstance(src, dict)
        }
        paper_hits.discard("")
        ctx.metadata["paper_hits"] = len(paper_hits)
        if mode == "chat_research":
            ctx.metadata["paper_hit_rate"] = round(len(paper_hits) / max(1, len(ctx.sub_questions)), 4)
        self.run_store.append_metric(ctx.run.run_id, {"name": "empty_evidence_rate", "value": empty_evidence_rate})
        yield {"type": "sources", "data": ctx.sources}
        yield build_metric_event("empty_evidence_rate", empty_evidence_rate, trace_id=ctx.run.trace_id)

    def _step_synthesize(self, ctx: RunExecutionContext) -> Generator[dict[str, Any], None, None]:
        mode = ctx.run.mode
        payload = ctx.run.payload
        client = get_llm_client()

        if mode == "research":
            topic = ctx.metadata.get("topic") or payload.get("topic", "")
            prompt = (
                "请写一份结构化研究报告，按主题分段，确保段落中使用[1][2]样式引用。"
                "若某段无证据支撑，请在段末标注（推断）。"
            )
            messages = self._build_messages(
                "你是严谨的研究助手。",
                f"主题：{topic}\n\n研究计划：\n{ctx.plan}\n\n证据：\n{ctx.context or '(无证据)'}\n\n要求：{prompt}",
                [],
            )
            full = ""
            for chunk in client.chat_stream(messages=messages, temperature=0.5, max_tokens=3500):
                full += chunk
                yield {"type": "chunk", "content": chunk}
            ctx.generated_text = self._ensure_inference_tag(full)
            self._record_model_call(ctx, stage="synthesize", messages=messages, output=ctx.generated_text)
            ctx.confidence = 0.8
            return

        if mode == "chat_research":
            question = ctx.message or str(payload.get("message") or "").strip()
            skill_chain = resolve_skill_chain(ctx.selected_skill_ids, domain="research")
            skill_instructions, skill_runs, skill_metrics = run_research_skill_chain(
                skills=skill_chain,
                has_kb=bool(payload.get("kb_id")),
                sources=ctx.sources,
            )
            ctx.metadata["skill_runs"] = skill_runs
            ctx.metadata["skill_success_rate"] = skill_metrics.get("skill_success_rate", 0.0)
            if skill_metrics.get("paper_hits") is not None:
                ctx.metadata["paper_hits"] = int(skill_metrics["paper_hits"])

            evidence_text = ctx.context or "(无本地论文证据)"
            if not payload.get("kb_id"):
                evidence_text = "(未选择本地论文库，仅基于通用知识回答)"
            skill_directive = "\n".join(f"- {item}" for item in skill_instructions if item)
            if not skill_directive:
                skill_directive = "- 回答需要围绕论文阅读与科研写作，尽量给出可验证依据。"

            prompt = (
                f"用户问题：{question}\n\n"
                f"可用证据：\n{evidence_text}\n\n"
                "写作要求：\n"
                "- 回答聚焦学术论文场景。\n"
                "- 有证据时优先引用[1][2]，无证据请明确标注（推断）。\n"
                "- 给出简明、结构化输出。\n"
                f"- Skills指令：\n{skill_directive}"
            )
            messages = self._build_messages(
                "你是智能论文助手，面向科研工作者提供论文检索、方法分析和写作支持。",
                prompt,
                ctx.chat_history,
            )

            full = ""
            for chunk in client.chat_stream(messages=messages, temperature=0.5, max_tokens=2200):
                full += chunk
                yield {"type": "chunk", "content": chunk}

            ctx.generated_text = full.strip()
            self._record_model_call(ctx, stage="synthesize", messages=messages, output=ctx.generated_text)
            yield {"type": "sources", "data": ctx.sources}
            ctx.confidence = 0.82 if ctx.sources else 0.7
            return

        # writing mode
        action = payload.get("action", "rewrite")
        text = payload.get("text", "")
        instruction = payload.get("instruction", "")
        result = self.co_writer_agent.process(
            text=text,
            action=action,
            instruction=instruction,
            evidence=ctx.evidence,
            stream=False,
        )
        edited = result.get("edited_text", "")
        bound = self._bind_paragraph_evidence(edited, ctx.evidence)
        ctx.generated_text = bound
        self._record_model_call(
            ctx,
            stage="synthesize",
            messages=[
                {"role": "system", "content": f"action={action}; instruction={instruction or 'none'}"},
                {"role": "user", "content": text},
            ],
            output=bound,
        )
        for chunk in self._chunk_text(bound, size=160):
            yield {"type": "chunk", "content": chunk}
        yield {"type": "sources", "data": ctx.evidence}
        ctx.confidence = 0.77

    def _step_critique(self, ctx: RunExecutionContext) -> Generator[dict[str, Any], None, None]:
        text = ctx.generated_text.strip()
        if not text:
            ctx.critique = "empty"
            return

        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        cited_parts = sum(1 for part in parts if re.search(r"\[[0-9]+\]", part))
        inference_parts = sum(1 for part in parts if "（推断）" in part or "(推断)" in part)
        ctx.metadata["citation_coverage"] = round(cited_parts / max(1, len(parts)), 4)
        ctx.metadata["inference_ratio"] = round(inference_parts / max(1, len(parts)), 4)

        missing_citation = len(re.findall(r"\[[0-9]+\]", text)) == 0 and bool(ctx.sources)
        if missing_citation:
            ctx.generated_text = self._ensure_inference_tag(text)
            ctx.critique = "missing citation fixed"
            ctx.metadata["citation_missing_fix"] = 1
            yield build_metric_event("citation_missing_fix", 1, trace_id=ctx.run.trace_id)
        else:
            ctx.critique = "ok"
            ctx.metadata["citation_missing_fix"] = 0
            yield build_metric_event("citation_missing_fix", 0, trace_id=ctx.run.trace_id)

        if ctx.run.mode == "chat_research" and not ctx.sources:
            # Ensure explicit uncertainty marker when no local-paper evidence is available.
            ctx.generated_text = self._ensure_inference_tag(ctx.generated_text)

    def _step_finalize(self, ctx: RunExecutionContext) -> Generator[dict[str, Any], None, None]:
        ctx.metadata["finalized_at"] = datetime.now().isoformat()
        ctx.metadata["final_status"] = "done"
        if False:
            yield None

    def _get_vector_store(self, kb_id: str) -> VectorStore | None:
        kb_manager = KnowledgeBaseManager(DATA_DIR / "knowledge_bases")
        kb = kb_manager.get_kb(kb_id)
        if not kb:
            return None
        vector_path = kb_manager.get_vector_store_path(kb_id)
        return VectorStore(
            persist_dir=str(vector_path),
            collection_name=kb["collection_name"],
            embedding_model=kb.get("embedding_model", "sentence-transformers/all-mpnet-base-v2"),
            embedding_provider=kb.get("embedding_provider", "sentence-transformers"),
        )

    @staticmethod
    def _normalize_paper_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in sources or []:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "Unknown")
            file_id = item.get("file_id")
            paper_id = item.get("paper_id") or file_id or item.get("id") or source
            title = item.get("title") or source
            authors = item.get("authors")
            if authors is None:
                authors = []
            year = item.get("year")
            venue = item.get("venue")
            doi = item.get("doi")
            section = item.get("section") or "unknown"
            chunk_type = item.get("chunk_type") or "paragraph"
            score = float(item.get("score", 0.0) or 0.0)
            metadata_incomplete = not bool(item.get("title")) or not bool(item.get("paper_id"))
            normalized.append(
                {
                    **item,
                    "paper_id": str(paper_id),
                    "title": str(title),
                    "authors": authors if isinstance(authors, list) else [str(authors)],
                    "year": year,
                    "venue": venue,
                    "doi": doi,
                    "section": section,
                    "chunk_type": chunk_type,
                    "score": score,
                    "metadata_incomplete": metadata_incomplete,
                }
            )
        return normalized

    @staticmethod
    def _build_messages(system: str, user: str, history: list[dict[str, Any]]) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": system}]
        for item in history[-8:]:
            role = item.get("role")
            content = item.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user})
        return messages

    @staticmethod
    def _chunk_text(text: str, size: int = 200) -> list[str]:
        return [text[i : i + size] for i in range(0, len(text), size)]

    @staticmethod
    def _ensure_inference_tag(text: str) -> str:
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        fixed: list[str] = []
        for part in parts:
            if re.search(r"\[[0-9]+\]", part):
                fixed.append(part)
            elif "（推断）" in part:
                fixed.append(part)
            else:
                fixed.append(f"{part}（推断）")
        return "\n\n".join(fixed)

    @staticmethod
    def _bind_paragraph_evidence(text: str, evidence: list[dict[str, Any]]) -> str:
        if not text.strip():
            return text
        ids = [f"[{i}]" for i in range(1, min(len(evidence), 4) + 1)]
        citation_suffix = " "+" ".join(ids) if ids else ""
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        out: list[str] = []
        for part in parts:
            if re.search(r"\[[0-9]+\]", part):
                out.append(part)
            elif citation_suffix:
                out.append(f"{part}{citation_suffix}")
            else:
                out.append(f"{part}（推断）")
        return "\n\n".join(out)

    def _record_model_call(
        self,
        ctx: RunExecutionContext,
        stage: str,
        messages: list[dict[str, str]],
        output: str,
    ) -> None:
        config = get_llm_config()
        prompt_tokens = sum(estimate_tokens((msg.get("content") or "")) for msg in messages)
        completion_tokens = estimate_tokens(output)
        call = {
            "stage": stage,
            "provider": config.provider,
            "model": config.model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_usd": self._estimate_model_cost_usd(
                provider=config.provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
        }
        ctx.metadata.setdefault("model_calls", []).append(call)
        self.run_store.append_metric(ctx.run.run_id, {"name": "model_cost_usd", "value": call["estimated_usd"], "stage": stage})

    @staticmethod
    def _estimate_model_cost_usd(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
        provider_key = (provider or "").lower()
        if provider_key == "openai":
            prompt_per_1k = 0.005
            completion_per_1k = 0.015
        else:
            prompt_per_1k = 0.0
            completion_per_1k = 0.0
        estimated = (prompt_tokens / 1000.0) * prompt_per_1k + (completion_tokens / 1000.0) * completion_per_1k
        return round(estimated, 6)

    def _summarize_model_cost(self, model_calls: list[dict[str, Any]]) -> dict[str, Any]:
        config = get_llm_config()
        prompt_tokens = sum(int(call.get("prompt_tokens", 0)) for call in model_calls)
        completion_tokens = sum(int(call.get("completion_tokens", 0)) for call in model_calls)
        estimated_usd = round(sum(float(call.get("estimated_usd", 0.0)) for call in model_calls), 6)
        return {
            "provider": config.provider,
            "model": config.model,
            "calls": len(model_calls),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_usd": estimated_usd,
        }

    def _append_run_log(
        self,
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
        with open(self.metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

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

    @staticmethod
    def _build_metrics_summary_from_store(run: Any) -> dict[str, Any]:
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
            "evidence_status": (run.result or {}).get("evidence_status", "unknown"),
            "citation_coverage": 0.0,
            "paper_hit_rate": 0.0,
            "skill_success_rate": 0.0,
            "inference_ratio": 0.0,
            "model_calls": [],
            "model_cost": {"provider": get_llm_config().provider, "model": get_llm_config().model, "estimated_usd": 0.0},
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
        total_attempts = sum(int(v) for v in summary["attempts"].values()) or 1
        summary["retry_rate"] = round(summary["retry_count"] / total_attempts, 4)
        summary["failure_rate"] = round(summary["failure_count"] / total_attempts, 4)
        return summary


_orchestrator_service: OrchestratorService | None = None


def get_orchestrator_service() -> OrchestratorService:
    global _orchestrator_service
    if _orchestrator_service is None:
        _orchestrator_service = OrchestratorService()
    return _orchestrator_service
