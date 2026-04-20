from __future__ import annotations

from src.agent_runtime.state import FinalReport, ReportSection, ReportStatement, RuntimeState
from src.shared_capabilities.rendering.report import render_final_report_markdown, render_statement


class ReportAgent:
    def run(self, state: RuntimeState, *, repair_notes: list[str] | None = None) -> RuntimeState:
        if state.research is None:
            raise ValueError("research state is required")

        sections: list[ReportSection] = []
        unresolved_questions = [gap.description for gap in state.research.unresolved_gaps]
        if repair_notes:
            unresolved_questions.extend(repair_notes)
        traceability: dict[str, list[str]] = {}

        for outline_section in state.research.report_outline.sections:
            candidate_ids = list(outline_section.selected_evidence_ids)
            if not candidate_ids:
                candidate_ids = self._derive_section_evidence_ids(state, outline_section.subquestion_ids)

            statements: list[ReportStatement] = []
            resolved_ids: list[str] = []
            invalid_ids = [
                evidence_id
                for evidence_id in candidate_ids
                if evidence_id not in state.research.evidence_store.by_id
            ]

            for evidence_id in candidate_ids:
                item = state.research.evidence_store.by_id.get(evidence_id)
                if not item:
                    continue
                statements.append(
                    ReportStatement(
                        text=f"{item.source_title} ({item.locator}) reports: {item.snippet}",
                        evidence_ids=[evidence_id],
                        support_status="supported",
                        notes="Directly grounded in retrieved evidence.",
                    )
                )
                resolved_ids.append(evidence_id)

            if len(resolved_ids) >= 2:
                statements.append(
                    ReportStatement(
                        text="The retrieved evidence shows recurring themes across the cited sources.",
                        evidence_ids=resolved_ids[:2],
                        support_status="tentative_inference",
                        notes="Inference is limited to the retrieved evidence set.",
                    )
                )

            if invalid_ids:
                statements.append(
                    ReportStatement(
                        text=f"Some planned evidence references were unavailable at write time: {', '.join(invalid_ids)}.",
                        evidence_ids=[],
                        support_status="missing_evidence",
                        notes="Unknown evidence ids were downgraded safely.",
                    )
                )
                unresolved_questions.append(
                    f"{outline_section.heading}: missing planned evidence references {', '.join(invalid_ids)}."
                )

            if not statements:
                statements.append(
                    ReportStatement(
                        text="No retrieved evidence currently supports this section.",
                        evidence_ids=[],
                        support_status="missing_evidence",
                        notes="The report preserved the evidence gap explicitly.",
                    )
                )
                unresolved_questions.append(f"{outline_section.heading}: no retrieved evidence yet.")

            evidence_ids = sorted({evidence_id for statement in statements for evidence_id in statement.evidence_ids})
            body = "\n".join(render_statement(statement) for statement in statements)
            sections.append(
                ReportSection(
                    section_id=outline_section.id,
                    heading=outline_section.heading,
                    body=body,
                    statements=statements,
                    evidence_ids=evidence_ids,
                )
            )
            traceability[outline_section.id] = evidence_ids

        final_report = FinalReport(
            title=state.research.report_outline.title or state.research.goal.topic,
            sections=sections,
            unresolved_questions=unresolved_questions,
            traceability=traceability,
        )
        final_report.rendered_markdown = render_final_report_markdown(final_report)
        state.research.final_report = final_report
        return state

    @staticmethod
    def _derive_section_evidence_ids(state: RuntimeState, subquestion_ids: list[str]) -> list[str]:
        if state.research is None:
            return []
        evidence_ids: list[str] = []
        for subquestion_id in subquestion_ids:
            for evidence_id in state.research.evidence_store.by_subquestion.get(subquestion_id, []):
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
        return evidence_ids
