from __future__ import annotations

from src.agent_runtime.runtime import AgentRuntime
from src.agent_runtime.state import (
    CoverageEntry,
    CoverageStatus,
    FinalReport,
    Gap,
    ReportSection,
    ReportStatement,
    ReviewResult,
    new_research_state,
)
from src.agent_workflows.research import PlannerAgent, ReviewerAgent
from src.shared_capabilities.retrieval.search_backend import SearchBackend, SearchCandidate, SearchResponse


def _candidate(name: str, source_id: str | None = None, quality: float = 0.9) -> SearchCandidate:
    return SearchCandidate(
        candidate_id=name,
        source_id=source_id or f"{name}-paper",
        source_title=f"{name} paper",
        locator="p.1",
        snippet=f"{name} evidence snippet",
        source_type="paper",
        relevance_score=0.92,
        quality_score=quality,
        metadata={"page": 1, "paper_id": source_id or f"{name}-paper"},
    )


def _responses_for(topic: str) -> dict[str, SearchResponse]:
    planned = PlannerAgent().run(new_research_state(topic))
    responses: dict[str, SearchResponse] = {}
    for batch in planned.research.search_plan.query_batches:
        for query in batch:
            responses[query.query] = SearchResponse(
                query=query.query,
                candidates=[_candidate(query.id, source_id=f"src-{query.id}")],
            )
    return responses


def test_runtime_research_flow_completes_with_traceable_report(monkeypatch):
    runtime = AgentRuntime()
    monkeypatch.setattr(
        runtime,
        "_research_backend",
        lambda payload: SearchBackend.from_responses(_responses_for(str(payload.get("topic") or ""))),
    )

    result = runtime.execute_sync("research", {"topic": "RAG survey and comparison"})
    runtime_state = result["metadata"]["runtime_state"]
    paper_workflow = result["metadata"]["paper_workflow"]
    research = runtime_state["research"]

    assert runtime_state["control"]["current_stage"] == "complete"
    assert paper_workflow["control_flags"]["current_stage"] == "complete"
    assert result["metadata"]["meta"]["coverage_status"] == "sufficient"

    known_ids = set(research["evidence_store"]["by_id"])
    for evidence_ids in research["final_report"]["traceability"].values():
        assert set(evidence_ids).issubset(known_ids)


def test_runtime_research_budget_exhaustion_still_produces_report(monkeypatch):
    runtime = AgentRuntime()
    monkeypatch.setattr(runtime, "_research_backend", lambda payload: SearchBackend.disabled("offline"))

    result = runtime.execute_sync(
        "research",
        {
            "topic": "Offline topic",
            "max_search_rounds": 1,
            "max_replans": 0,
        },
    )

    assert result["metadata"]["meta"]["search_budget_exhausted"] is True
    assert result["metadata"]["meta"]["coverage_status"] == "exhausted"
    assert "No retrieved evidence currently supports this section." in result["output"]


def test_reviewer_detects_invalid_evidence_ids_and_hidden_gaps():
    state = PlannerAgent().run(new_research_state("Verifier topic"))
    state.research.coverage_status = CoverageStatus(
        overall="partial",
        covered_ratio=0.25,
        high_priority_complete=False,
        ready_for_report=False,
        subquestions=[
            CoverageEntry(subquestion_id=state.research.subquestions[0].id, priority="high", status="missing", reason="no evidence"),
            CoverageEntry(subquestion_id=state.research.subquestions[1].id, priority="high", status="covered", reason="ok"),
        ],
    )
    state.research.unresolved_gaps.append(
        Gap(
            subquestion_id=state.research.subquestions[0].id,
            description="Background coverage is incomplete.",
            reason="plan_gap",
        )
    )
    state.research.final_report = FinalReport(
        title="Verifier topic",
        sections=[
            ReportSection(
                section_id="section_background",
                heading="Background",
                body="",
                statements=[
                    ReportStatement(
                        text="A supported claim without valid evidence.",
                        evidence_ids=["ev-missing"],
                        support_status="supported",
                    )
                ],
                evidence_ids=["ev-missing"],
            )
        ],
        unresolved_questions=[],
        traceability={"section_background": ["ev-missing"]},
    )

    reviewed = ReviewerAgent().run(state)
    review: ReviewResult = reviewed.research.review_result

    assert review.invalid_evidence_ids == ["ev-missing"]
    assert review.missing_high_priority_subquestions == [state.research.subquestions[0].id]
    assert review.hidden_gaps == ["Background coverage is incomplete."]
    assert review.blocking is True
    assert review.repair_action == "report_repair"
