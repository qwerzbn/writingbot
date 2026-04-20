from __future__ import annotations

import hashlib
import re
from typing import Any

from src.agent_runtime.state import (
    CoverageEntry,
    CoverageStatus,
    DUPLICATE_RATIO_REPLAN_THRESHOLD,
    EvidenceItem,
    Gap,
    MIN_COVERED_RATIO,
    MIN_QUALITY_SCORE,
    RuntimeState,
    SearchAttempt,
    SearchRoundOutcome,
)
from src.shared_capabilities.retrieval.search_backend import SearchBackend


class SearchAgent:
    def __init__(self, backend: SearchBackend):
        self.backend = backend

    def run(self, state: RuntimeState, *, round_index: int) -> SearchRoundOutcome:
        if state.research is None:
            raise ValueError("research state is required")

        batch_index = round_index - 1
        if batch_index >= len(state.research.search_plan.query_batches):
            self._refresh_coverage(state)
            return SearchRoundOutcome(round_index=round_index, report_ready=True, budget_exhausted=True)

        batch = state.research.search_plan.query_batches[batch_index][: state.control.max_queries_per_round]
        fingerprint_map = {
            item.fingerprint: item.evidence_id
            for item in state.research.evidence_store.by_id.values()
            if item.fingerprint
        }
        round_new_items = 0
        round_duplicates = 0
        round_retrieved = 0
        round_failures = 0

        for query_spec in batch:
            response = self.backend.search(query=query_spec.query, top_k=state.control.max_results_per_query)
            results_kept = 0
            duplicate_results = 0
            discarded_reasons: list[str] = []
            failure_reason = None

            if response.error:
                round_failures += 1
                failure_reason = response.error
                discarded_reasons.append("backend_error")
                state.research.unresolved_gaps.append(
                    Gap(
                        subquestion_id=query_spec.subquestion_id,
                        description=f"Search failed for query '{query_spec.query}'.",
                        reason="backend_error",
                    )
                )
            else:
                round_retrieved += len(response.candidates)
                for candidate in response.candidates:
                    fingerprint = self._fingerprint(candidate.source_id, candidate.locator, candidate.snippet)
                    if candidate.quality_score < MIN_QUALITY_SCORE:
                        discarded_reasons.append("low_quality")
                        state.research.evidence_store.discarded_items.append(
                            self._discard_row(candidate, query_spec.id, round_index, "low_quality")
                        )
                        continue

                    if fingerprint in fingerprint_map:
                        evidence_id = fingerprint_map[fingerprint]
                        existing = state.research.evidence_store.by_id[evidence_id]
                        if query_spec.subquestion_id not in existing.subquestion_ids:
                            existing.subquestion_ids.append(query_spec.subquestion_id)
                            state.research.evidence_store.by_subquestion.setdefault(query_spec.subquestion_id, []).append(
                                evidence_id
                            )
                            results_kept += 1
                        else:
                            duplicate_results += 1
                            discarded_reasons.append("duplicate")
                            state.research.evidence_store.discarded_items.append(
                                self._discard_row(candidate, query_spec.id, round_index, "duplicate")
                            )
                        continue

                    evidence_id = "ev-" + hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:12]
                    item = EvidenceItem(
                        evidence_id=evidence_id,
                        subquestion_ids=[query_spec.subquestion_id],
                        source_id=candidate.source_id,
                        source_title=candidate.source_title,
                        locator=candidate.locator,
                        snippet=candidate.snippet,
                        source_type=self._normalize_source_type(candidate.source_type),
                        query_id=query_spec.id,
                        retrieval_round=round_index,
                        relevance_score=candidate.relevance_score,
                        quality_score=candidate.quality_score,
                        support_type="direct",
                        metadata={**candidate.metadata, "fingerprint": fingerprint},
                        fingerprint=fingerprint,
                    )
                    state.research.evidence_store.items.append(item)
                    state.research.evidence_store.by_id[evidence_id] = item
                    state.research.evidence_store.by_subquestion.setdefault(query_spec.subquestion_id, []).append(evidence_id)
                    fingerprint_map[fingerprint] = evidence_id
                    results_kept += 1
                    round_new_items += 1

            state.research.evidence_store.search_log.append(
                SearchAttempt(
                    round_index=round_index,
                    query_id=query_spec.id,
                    query_text=query_spec.query,
                    results_retrieved=len(response.candidates),
                    results_kept=results_kept,
                    duplicate_results=duplicate_results,
                    discarded_reasons=sorted(set(discarded_reasons)),
                    stop_reason=None,
                    failure_reason=failure_reason,
                )
            )
            round_duplicates += duplicate_results

        self._refresh_coverage(state)

        duplicate_ratio = round_duplicates / max(1, round_retrieved)
        zero_progress = round_new_items == 0
        replan_requested = zero_progress or duplicate_ratio >= DUPLICATE_RATIO_REPLAN_THRESHOLD
        if replan_requested:
            state.research.unresolved_gaps.append(
                Gap(
                    subquestion_id=None,
                    description=f"Search round {round_index} made no new evidence progress.",
                    reason="duplicates_only" if round_retrieved else "no_hits",
                )
            )

        focus_ids = [
            entry.subquestion_id
            for entry in state.research.coverage_status.subquestions
            if entry.status != "covered" and entry.priority == "high"
        ]
        report_ready = state.research.coverage_status.ready_for_report or round_failures == len(batch)
        return SearchRoundOutcome(
            round_index=round_index,
            query_count=len(batch),
            results_retrieved=round_retrieved,
            new_items=round_new_items,
            duplicate_results=round_duplicates,
            failures=round_failures,
            replan_requested=replan_requested,
            report_ready=report_ready,
            budget_exhausted=batch_index >= len(state.research.search_plan.query_batches) - 1,
            focus_subquestion_ids=focus_ids,
        )

    @staticmethod
    def _normalize_source_type(value: str) -> str:
        if value in {"paper", "section", "figure", "table"}:
            return value
        return "other"

    @staticmethod
    def _discard_row(candidate: Any, query_id: str, round_index: int, reason: str) -> dict[str, Any]:
        return {
            "query_id": query_id,
            "round_index": round_index,
            "candidate_id": candidate.candidate_id,
            "source_id": candidate.source_id,
            "reason": reason,
        }

    @staticmethod
    def _fingerprint(source_id: str, locator: str, snippet: str) -> str:
        compact = re.sub(r"\s+", " ", snippet.strip().lower())
        return hashlib.sha1(f"{source_id}|{locator}|{compact}".encode("utf-8")).hexdigest()

    def _refresh_coverage(self, state: RuntimeState) -> None:
        if state.research is None:
            return
        preserved_gaps = [
            gap
            for gap in state.research.unresolved_gaps
            if gap.reason in {"backend_error", "duplicates_only", "budget_exhausted", "conflict"}
        ]
        entries: list[CoverageEntry] = []
        gaps: list[Gap] = []
        covered_count = 0
        any_evidence = bool(state.research.evidence_store.by_id)
        for subquestion in state.research.subquestions:
            evidence_ids = state.research.evidence_store.by_subquestion.get(subquestion.id, [])
            evidence_count = len(set(evidence_ids))
            if evidence_count >= subquestion.coverage_target:
                status = "covered"
                reason = "coverage target met"
                covered_count += 1
            elif evidence_count > 0:
                status = "partial"
                reason = "some evidence retrieved but below target"
                gaps.append(
                    Gap(
                        subquestion_id=subquestion.id,
                        description=f"{subquestion.question} is only partially covered.",
                        reason="plan_gap",
                    )
                )
            else:
                status = "missing"
                reason = "no evidence retrieved"
                gaps.append(
                    Gap(
                        subquestion_id=subquestion.id,
                        description=f"No evidence retrieved yet for '{subquestion.question}'.",
                        reason="no_hits",
                    )
                )
            subquestion.status = status
            entries.append(
                CoverageEntry(
                    subquestion_id=subquestion.id,
                    priority=subquestion.priority,
                    evidence_count=evidence_count,
                    status=status,
                    reason=reason,
                )
            )

        high_priority_complete = all(entry.status == "covered" for entry in entries if entry.priority == "high")
        covered_ratio = covered_count / max(1, len(entries))
        ready_for_report = high_priority_complete and covered_ratio >= MIN_COVERED_RATIO
        overall = "not_started"
        if state.control.search_budget_exhausted and not ready_for_report:
            overall = "exhausted"
        elif ready_for_report:
            overall = "sufficient"
        elif any_evidence:
            overall = "partial"
        else:
            overall = "insufficient"

        state.research.coverage_status = CoverageStatus(
            overall=overall,
            subquestions=entries,
            covered_ratio=covered_ratio,
            high_priority_complete=high_priority_complete,
            ready_for_report=ready_for_report,
        )
        state.research.unresolved_gaps = preserved_gaps + gaps
