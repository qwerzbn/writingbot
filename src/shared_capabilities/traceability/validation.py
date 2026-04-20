from __future__ import annotations

from src.agent_runtime.state import FinalReport, ReviewIssue


def collect_report_evidence_ids(report: FinalReport | None) -> set[str]:
    if report is None:
        return set()
    evidence_ids: set[str] = set()
    for section in report.sections:
        evidence_ids.update(section.evidence_ids)
        for statement in section.statements:
            evidence_ids.update(statement.evidence_ids)
    for rows in report.traceability.values():
        evidence_ids.update(rows)
    return evidence_ids


def find_invalid_evidence_ids(report: FinalReport | None, known_evidence_ids: set[str]) -> list[str]:
    return sorted(collect_report_evidence_ids(report) - set(known_evidence_ids))


def find_statement_issues(report: FinalReport | None, known_evidence_ids: set[str]) -> list[ReviewIssue]:
    if report is None:
        return []
    issues: list[ReviewIssue] = []
    for section in report.sections:
        for statement in section.statements:
            invalid_ids = [row for row in statement.evidence_ids if row not in known_evidence_ids]
            if statement.support_status in {"supported", "tentative_inference"} and not statement.evidence_ids:
                issues.append(
                    ReviewIssue(
                        code="missing_statement_evidence",
                        severity="error",
                        message="Supported or tentative statements must cite at least one evidence id.",
                        section_id=section.section_id,
                        statement_text=statement.text,
                    )
                )
            if invalid_ids:
                issues.append(
                    ReviewIssue(
                        code="invalid_statement_evidence",
                        severity="error",
                        message=f"Statement cites unknown evidence ids: {', '.join(invalid_ids)}.",
                        section_id=section.section_id,
                        statement_text=statement.text,
                        evidence_ids=invalid_ids,
                    )
                )
    return issues


def find_hidden_gaps(report: FinalReport | None, unresolved_gaps: list[str]) -> list[str]:
    if report is None:
        return list(unresolved_gaps)
    visible = set(report.unresolved_questions)
    return [gap for gap in unresolved_gaps if gap not in visible]
