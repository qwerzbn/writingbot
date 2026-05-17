from __future__ import annotations

from types import SimpleNamespace

from src.shared_capabilities.traceability.validation import (
    TraceabilityIssue,
    collect_report_evidence_ids,
    find_hidden_gaps,
    find_invalid_evidence_ids,
    find_statement_issues,
)


def test_traceability_validation_accepts_report_like_objects():
    report = SimpleNamespace(
        sections=[
            SimpleNamespace(
                section_id="sec-1",
                evidence_ids=["ev-section"],
                statements=[
                    SimpleNamespace(text="Supported claim", support_status="supported", evidence_ids=["ev-known"]),
                    SimpleNamespace(text="Missing claim", support_status="supported", evidence_ids=[]),
                    SimpleNamespace(text="Bad claim", support_status="supported", evidence_ids=["ev-missing"]),
                ],
            )
        ],
        traceability={"claim-1": ["ev-trace"]},
        unresolved_questions=["visible gap"],
    )

    assert collect_report_evidence_ids(report) == {"ev-section", "ev-known", "ev-missing", "ev-trace"}
    assert find_invalid_evidence_ids(report, {"ev-section", "ev-known", "ev-trace"}) == ["ev-missing"]

    issues = find_statement_issues(report, {"ev-section", "ev-known", "ev-trace"})
    assert all(isinstance(issue, TraceabilityIssue) for issue in issues)
    assert [issue.code for issue in issues] == ["missing_statement_evidence", "invalid_statement_evidence"]
    assert find_hidden_gaps(report, ["visible gap", "hidden gap"]) == ["hidden gap"]
