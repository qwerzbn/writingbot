from __future__ import annotations

from src.agent_runtime.state import ReviewIssue, ReviewResult, RuntimeState
from src.shared_capabilities.traceability.validation import (
    find_hidden_gaps,
    find_invalid_evidence_ids,
    find_statement_issues,
)


class ReviewerAgent:
    def run(self, state: RuntimeState) -> RuntimeState:
        if state.research is None:
            raise ValueError("research state is required")

        issues: list[ReviewIssue] = []
        report = state.research.final_report
        if report is None:
            state.research.review_result = ReviewResult(
                issues=[
                    ReviewIssue(
                        code="missing_report",
                        severity="error",
                        message="No final report was produced for review.",
                    )
                ],
                blocking=True,
                repair_action="report_repair",
                summary="Report generation failed before review.",
            )
            return state

        known_evidence_ids = set(state.research.evidence_store.by_id)
        invalid_evidence_ids = find_invalid_evidence_ids(report, known_evidence_ids)
        issues.extend(find_statement_issues(report, known_evidence_ids))

        missing_high_priority_subquestions = [
            entry.subquestion_id
            for entry in state.research.coverage_status.subquestions
            if entry.priority == "high" and entry.status != "covered"
        ]
        hidden_gaps = find_hidden_gaps(report, [gap.description for gap in state.research.unresolved_gaps])

        if invalid_evidence_ids:
            issues.append(
                ReviewIssue(
                    code="invalid_evidence_ids",
                    severity="error",
                    message=f"Report references unknown evidence ids: {', '.join(invalid_evidence_ids)}.",
                    evidence_ids=invalid_evidence_ids,
                )
            )
        if missing_high_priority_subquestions:
            issues.append(
                ReviewIssue(
                    code="missing_high_priority_coverage",
                    severity="error",
                    message="High-priority subquestions are still missing evidence coverage.",
                )
            )
        for gap in hidden_gaps:
            issues.append(
                ReviewIssue(
                    code="hidden_gap",
                    severity="warning",
                    message=f"Gap is not disclosed in the final report: {gap}",
                )
            )

        repair_action = "none"
        blocking = False
        if invalid_evidence_ids or any(issue.code.startswith("missing_statement") or issue.code.startswith("invalid_statement") for issue in issues):
            repair_action = "report_repair"
            blocking = True
        elif missing_high_priority_subquestions or hidden_gaps:
            repair_action = "search_repair"
            blocking = True

        state.research.review_result = ReviewResult(
            issues=issues,
            invalid_evidence_ids=invalid_evidence_ids,
            missing_high_priority_subquestions=missing_high_priority_subquestions,
            hidden_gaps=hidden_gaps,
            blocking=blocking,
            repair_action=repair_action,
            summary=self._summary(blocking, repair_action, issues),
        )
        return state

    @staticmethod
    def _summary(blocking: bool, repair_action: str, issues: list[ReviewIssue]) -> str:
        if not issues:
            return "Review passed with no blocking issues."
        if not blocking:
            return f"Review completed with {len(issues)} non-blocking issue(s)."
        return f"Review found {len(issues)} blocking issue(s); recommended action: {repair_action}."
