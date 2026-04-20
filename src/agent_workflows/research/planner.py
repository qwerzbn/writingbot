from __future__ import annotations

import hashlib

from src.agent_runtime.state import (
    OutlineSection,
    QuerySpec,
    ReportOutline,
    ResearchGoal,
    RuntimeState,
    SearchPlan,
    Subquestion,
)


class PlannerAgent:
    def run(self, state: RuntimeState) -> RuntimeState:
        if state.research is None:
            raise ValueError("research state is required")

        topic = state.user_task.strip() or "Academic Topic"
        repair_focus = set(state.research.repair_focus_subquestion_ids)
        comparison_requested = self._needs_comparison(topic)
        subquestions = self._build_subquestions(topic, comparison_requested)
        query_batches = self._build_query_batches(
            topic,
            subquestions,
            max_rounds=state.control.max_search_rounds,
            max_queries=state.control.max_queries_per_round,
            focus_subquestion_ids=repair_focus or None,
        )
        sections = self._build_outline(comparison_requested)

        state.research.goal = ResearchGoal(
            topic=topic,
            deliverable="evidence-grounded literature report",
            audience="academic reader",
            output_format="markdown",
            constraints=[
                "Only retrieved evidence may support final claims.",
                "Explicitly identify evidence gaps and unresolved questions.",
            ],
        )
        state.research.subquestions = subquestions
        state.research.search_plan = SearchPlan(
            plan_id="plan-" + hashlib.sha1(topic.encode("utf-8")).hexdigest()[:8],
            query_batches=query_batches,
            stop_rules=[
                "Stop when all high-priority subquestions meet coverage targets.",
                "Stop when the configured search budget is exhausted.",
            ],
            replan_triggers=[
                "Request replanning after a duplicate-only round.",
                "Request replanning after a zero-progress round.",
            ],
        )
        state.research.report_outline = ReportOutline(title=f"Literature Report: {topic}", sections=sections)
        return state

    @staticmethod
    def _needs_comparison(topic: str) -> bool:
        lowered = topic.lower()
        keywords = ("compare", "comparison", "survey", "review", "vs", "versus", "benchmark")
        return any(word in lowered for word in keywords)

    @staticmethod
    def _build_subquestions(topic: str, comparison_requested: bool) -> list[Subquestion]:
        rows = [
            Subquestion(
                id="sq_background",
                question=f"What problem scope and background define {topic}?",
                priority="high",
                coverage_target=2,
                rationale="Sets the scope of the report.",
            ),
            Subquestion(
                id="sq_methods",
                question=f"What core methods or approaches are used in {topic}?",
                priority="high",
                coverage_target=2,
                rationale="Explains the technical approach.",
            ),
            Subquestion(
                id="sq_results",
                question=f"What empirical evidence supports {topic}?",
                priority="high",
                coverage_target=2,
                rationale="Anchors the report in experiments and results.",
            ),
            Subquestion(
                id="sq_limitations",
                question=f"What limitations, risks, or open questions remain for {topic}?",
                priority="medium",
                coverage_target=1,
                rationale="Captures caveats and future work.",
            ),
        ]
        if comparison_requested:
            rows.append(
                Subquestion(
                    id="sq_comparison",
                    question=f"How does {topic} compare with adjacent approaches or baselines?",
                    priority="medium",
                    coverage_target=1,
                    rationale="Supports comparison- or survey-oriented tasks.",
                )
            )
        return rows

    def _build_query_batches(
        self,
        topic: str,
        subquestions: list[Subquestion],
        *,
        max_rounds: int,
        max_queries: int,
        focus_subquestion_ids: set[str] | None,
    ) -> list[list[QuerySpec]]:
        queries_by_subquestion = {
            "sq_background": [
                ("overview", f"{topic} overview background"),
                ("overview", f"{topic} research problem scope"),
                ("overview", f"{topic} open challenges"),
            ],
            "sq_methods": [
                ("method", f"{topic} method approach architecture"),
                ("method", f"{topic} algorithm pipeline"),
                ("method", f"{topic} implementation details"),
            ],
            "sq_results": [
                ("experiment", f"{topic} experiments benchmark results"),
                ("experiment", f"{topic} ablation evaluation"),
                ("experiment", f"{topic} empirical findings"),
            ],
            "sq_limitations": [
                ("limitation", f"{topic} limitations failure modes"),
                ("limitation", f"{topic} future work open questions"),
                ("limitation", f"{topic} constraints drawbacks"),
            ],
            "sq_comparison": [
                ("comparison", f"{topic} comparison related work"),
                ("comparison", f"{topic} baseline comparison"),
                ("comparison", f"{topic} survey taxonomy"),
            ],
        }

        eligible_subquestions = [
            subquestion
            for subquestion in subquestions
            if not focus_subquestion_ids or subquestion.id in focus_subquestion_ids
        ]
        batches: list[list[QuerySpec]] = [[] for _ in range(max(1, max_rounds))]
        for subquestion in eligible_subquestions:
            query_rows = queries_by_subquestion.get(subquestion.id, [])
            for round_index, row in enumerate(query_rows[: len(batches)]):
                intent, query_text = row
                batches[round_index].append(
                    QuerySpec(
                        id=f"{subquestion.id}_q{round_index + 1}",
                        subquestion_id=subquestion.id,
                        query=query_text,
                        intent=intent,  # type: ignore[arg-type]
                        required=round_index == 0 or subquestion.priority == "high",
                    )
                )

        bounded_batches = [batch[:max_queries] for batch in batches]
        return [batch for batch in bounded_batches if batch]

    @staticmethod
    def _build_outline(comparison_requested: bool) -> list[OutlineSection]:
        sections = [
            OutlineSection(id="section_background", heading="Background and Scope", subquestion_ids=["sq_background"]),
            OutlineSection(id="section_methods", heading="Methods and Approaches", subquestion_ids=["sq_methods"]),
            OutlineSection(id="section_results", heading="Evidence and Findings", subquestion_ids=["sq_results"]),
            OutlineSection(
                id="section_limitations",
                heading="Limitations and Open Questions",
                subquestion_ids=["sq_limitations"],
            ),
        ]
        if comparison_requested:
            sections.insert(
                3,
                OutlineSection(
                    id="section_comparison",
                    heading="Comparison to Adjacent Work",
                    subquestion_ids=["sq_comparison"],
                ),
            )
        return sections
