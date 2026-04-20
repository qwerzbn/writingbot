from __future__ import annotations

import re
from typing import Any

from src.agent_runtime.state import FinalReport, ReportStatement


def render_statement(statement: ReportStatement) -> str:
    citation = ""
    if statement.evidence_ids:
        citation = " [" + ", ".join(statement.evidence_ids) + "]"
    return f"- {statement.support_status}: {statement.text}{citation}"


def render_final_report_markdown(final_report: FinalReport) -> str:
    parts = [f"# {final_report.title}"]
    for section in final_report.sections:
        parts.append(f"## {section.heading}")
        parts.append(section.body)
    if final_report.unresolved_questions:
        parts.append("## Unresolved Questions")
        for question in final_report.unresolved_questions:
            parts.append(f"- {question}")
    return "\n\n".join(parts).strip()


def ensure_inference_tag(text: str) -> str:
    parts = [part.strip() for part in text.split("\n\n") if part.strip()]
    fixed: list[str] = []
    for part in parts:
        if re.search(r"\[[0-9]+\]", part):
            fixed.append(part)
        elif "(inference)" in part:
            fixed.append(part)
        else:
            fixed.append(f"{part} (inference)")
    return "\n\n".join(fixed)


def bind_paragraph_evidence(text: str, evidence: list[dict[str, Any]]) -> str:
    if not text.strip():
        return text
    ids = [f"[{idx}]" for idx in range(1, min(len(evidence), 4) + 1)]
    citation_suffix = " " + " ".join(ids) if ids else ""
    parts = [part.strip() for part in text.split("\n\n") if part.strip()]
    rendered: list[str] = []
    for part in parts:
        if re.search(r"\[[0-9]+\]", part):
            rendered.append(part)
        elif citation_suffix:
            rendered.append(f"{part}{citation_suffix}")
        else:
            rendered.append(f"{part} (inference)")
    return "\n\n".join(rendered)
