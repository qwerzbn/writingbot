from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceabilityIssue:
    code: str
    severity: str
    message: str
    section_id: str = ""
    statement_text: str = ""
    evidence_ids: list[str] = field(default_factory=list)


def _items(value: Any) -> list[Any]:
    return list(value or []) if isinstance(value, list) else []


def _mapping_values(value: Any) -> list[Any]:
    return list(value.values()) if isinstance(value, dict) else []


def collect_report_evidence_ids(report: Any | None) -> set[str]:
    if report is None:
        return set()
    evidence_ids: set[str] = set()
    for section in _items(getattr(report, "sections", [])):
        evidence_ids.update(str(item) for item in _items(getattr(section, "evidence_ids", [])) if str(item))
        for statement in _items(getattr(section, "statements", [])):
            evidence_ids.update(str(item) for item in _items(getattr(statement, "evidence_ids", [])) if str(item))
    for rows in _mapping_values(getattr(report, "traceability", {})):
        evidence_ids.update(str(item) for item in _items(rows) if str(item))
    return evidence_ids


def find_invalid_evidence_ids(report: Any | None, known_evidence_ids: set[str]) -> list[str]:
    return sorted(collect_report_evidence_ids(report) - set(known_evidence_ids))


def find_statement_issues(report: Any | None, known_evidence_ids: set[str]) -> list[TraceabilityIssue]:
    if report is None:
        return []
    issues: list[TraceabilityIssue] = []
    for section in _items(getattr(report, "sections", [])):
        section_id = str(getattr(section, "section_id", ""))
        for statement in _items(getattr(section, "statements", [])):
            evidence_ids = [str(row) for row in _items(getattr(statement, "evidence_ids", [])) if str(row)]
            invalid_ids = [row for row in evidence_ids if row not in known_evidence_ids]
            if getattr(statement, "support_status", "") in {"supported", "tentative_inference"} and not evidence_ids:
                issues.append(
                    TraceabilityIssue(
                        code="missing_statement_evidence",
                        severity="error",
                        message="Supported or tentative statements must cite at least one evidence id.",
                        section_id=section_id,
                        statement_text=str(getattr(statement, "text", "")),
                    )
                )
            if invalid_ids:
                issues.append(
                    TraceabilityIssue(
                        code="invalid_statement_evidence",
                        severity="error",
                        message=f"Statement cites unknown evidence ids: {', '.join(invalid_ids)}.",
                        section_id=section_id,
                        statement_text=str(getattr(statement, "text", "")),
                        evidence_ids=invalid_ids,
                    )
                )
    return issues


def find_hidden_gaps(report: Any | None, unresolved_gaps: list[str]) -> list[str]:
    if report is None:
        return list(unresolved_gaps)
    visible = set(_items(getattr(report, "unresolved_questions", [])))
    return [gap for gap in unresolved_gaps if gap not in visible]
