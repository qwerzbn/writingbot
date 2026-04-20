from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DEFAULT_MAX_SEARCH_ROUNDS = 3
DEFAULT_MAX_QUERIES_PER_ROUND = 4
DEFAULT_MAX_REPLANS = 1
DEFAULT_MAX_RESULTS_PER_QUERY = 8
DEFAULT_MAX_REPAIR_PASSES = 1

MIN_QUALITY_SCORE = 0.60
MIN_COVERED_RATIO = 0.70
DUPLICATE_RATIO_REPLAN_THRESHOLD = 0.75

RuntimeMode = Literal["research", "writing", "chat_research"]
RuntimeStage = Literal[
    "planning",
    "searching",
    "reporting",
    "reviewing",
    "content_generation",
    "complete",
    "failed",
]
Priority = Literal["high", "medium", "low"]
CoverageState = Literal["unsearched", "covered", "partial", "missing", "blocked"]
SupportState = Literal["supported", "tentative_inference", "missing_evidence"]
CoverageOverall = Literal["not_started", "partial", "sufficient", "insufficient", "exhausted"]
GapReason = Literal[
    "no_hits",
    "duplicates_only",
    "low_relevance",
    "plan_gap",
    "budget_exhausted",
    "conflict",
    "backend_error",
]
ContentMode = Literal["chat", "rewrite", "expand", "shorten", "polish"]
ReviewRepairAction = Literal["none", "report_repair", "search_repair"]
IssueSeverity = Literal["info", "warning", "error"]


class ResearchGoal(BaseModel):
    topic: str = ""
    deliverable: str = "literature report"
    audience: str = "academic reader"
    output_format: str = "markdown"
    constraints: list[str] = Field(default_factory=list)


class Subquestion(BaseModel):
    id: str
    question: str
    priority: Priority = "medium"
    coverage_target: int = 1
    rationale: str = ""
    status: CoverageState = "unsearched"


class QuerySpec(BaseModel):
    id: str
    subquestion_id: str
    query: str
    intent: Literal["overview", "method", "experiment", "limitation", "comparison"] = "overview"
    required: bool = True


class SearchPlan(BaseModel):
    plan_id: str = "plan-1"
    query_batches: list[list[QuerySpec]] = Field(default_factory=list)
    stop_rules: list[str] = Field(default_factory=list)
    replan_triggers: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    evidence_id: str
    subquestion_ids: list[str] = Field(default_factory=list)
    source_id: str
    source_title: str
    locator: str = "unknown"
    snippet: str
    source_type: Literal["paper", "section", "figure", "table", "other"] = "other"
    query_id: str = ""
    retrieval_round: int = 0
    relevance_score: float = 0.0
    quality_score: float = 0.0
    support_type: Literal["direct", "contextual"] = "direct"
    metadata: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str = ""


class SearchAttempt(BaseModel):
    round_index: int
    query_id: str
    query_text: str
    results_retrieved: int = 0
    results_kept: int = 0
    duplicate_results: int = 0
    discarded_reasons: list[str] = Field(default_factory=list)
    stop_reason: str | None = None
    failure_reason: str | None = None


class EvidenceStore(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)
    by_id: dict[str, EvidenceItem] = Field(default_factory=dict)
    by_subquestion: dict[str, list[str]] = Field(default_factory=dict)
    search_log: list[SearchAttempt] = Field(default_factory=list)
    discarded_items: list[dict[str, Any]] = Field(default_factory=list)


class CoverageEntry(BaseModel):
    subquestion_id: str
    priority: Priority
    evidence_count: int = 0
    status: CoverageState = "unsearched"
    reason: str = ""


class CoverageStatus(BaseModel):
    overall: CoverageOverall = "not_started"
    subquestions: list[CoverageEntry] = Field(default_factory=list)
    covered_ratio: float = 0.0
    high_priority_complete: bool = False
    ready_for_report: bool = False


class Gap(BaseModel):
    subquestion_id: str | None = None
    description: str
    reason: GapReason = "no_hits"


class OutlineSection(BaseModel):
    id: str
    heading: str
    subquestion_ids: list[str] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["pending", "ready", "gap"] = "pending"


class ReportOutline(BaseModel):
    title: str = ""
    sections: list[OutlineSection] = Field(default_factory=list)


class ReportStatement(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    support_status: SupportState = "missing_evidence"
    notes: str = ""


class ReportSection(BaseModel):
    section_id: str
    heading: str
    body: str = ""
    statements: list[ReportStatement] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class FinalReport(BaseModel):
    title: str = ""
    rendered_markdown: str = ""
    sections: list[ReportSection] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    traceability: dict[str, list[str]] = Field(default_factory=dict)


class ReviewIssue(BaseModel):
    code: str
    severity: IssueSeverity = "warning"
    message: str
    section_id: str | None = None
    statement_text: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    issues: list[ReviewIssue] = Field(default_factory=list)
    invalid_evidence_ids: list[str] = Field(default_factory=list)
    missing_high_priority_subquestions: list[str] = Field(default_factory=list)
    hidden_gaps: list[str] = Field(default_factory=list)
    blocking: bool = False
    repair_action: ReviewRepairAction = "none"
    summary: str = ""


class SearchRoundOutcome(BaseModel):
    round_index: int
    query_count: int = 0
    results_retrieved: int = 0
    new_items: int = 0
    duplicate_results: int = 0
    failures: int = 0
    replan_requested: bool = False
    report_ready: bool = False
    budget_exhausted: bool = False
    focus_subquestion_ids: list[str] = Field(default_factory=list)


class ResearchState(BaseModel):
    goal: ResearchGoal = Field(default_factory=ResearchGoal)
    subquestions: list[Subquestion] = Field(default_factory=list)
    search_plan: SearchPlan = Field(default_factory=SearchPlan)
    evidence_store: EvidenceStore = Field(default_factory=EvidenceStore)
    coverage_status: CoverageStatus = Field(default_factory=CoverageStatus)
    unresolved_gaps: list[Gap] = Field(default_factory=list)
    report_outline: ReportOutline = Field(default_factory=ReportOutline)
    final_report: FinalReport | None = None
    review_result: ReviewResult | None = None
    repair_focus_subquestion_ids: list[str] = Field(default_factory=list)


class ContentState(BaseModel):
    mode: ContentMode = "chat"
    user_input: str = ""
    instruction: str = ""
    history: list[dict[str, str]] = Field(default_factory=list)
    evidence_bundle: list[dict[str, Any]] = Field(default_factory=list)
    context_text: str = ""
    skill_directive: str = ""
    output_text: str = ""
    output_sources: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeControl(BaseModel):
    mode: RuntimeMode = "research"
    current_stage: RuntimeStage = "planning"
    max_search_rounds: int = DEFAULT_MAX_SEARCH_ROUNDS
    current_search_round: int = 0
    max_queries_per_round: int = DEFAULT_MAX_QUERIES_PER_ROUND
    max_results_per_query: int = DEFAULT_MAX_RESULTS_PER_QUERY
    max_replans: int = DEFAULT_MAX_REPLANS
    replans_used: int = 0
    max_repair_passes: int = DEFAULT_MAX_REPAIR_PASSES
    repair_passes_used: int = 0
    search_budget_exhausted: bool = False
    report_ready: bool = False
    halt_reason: str | None = None


class RuntimeDiagnostics(BaseModel):
    stage_history: list[dict[str, Any]] = Field(default_factory=list)
    model_calls: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class RuntimeState(BaseModel):
    user_task: str
    control: RuntimeControl = Field(default_factory=RuntimeControl)
    diagnostics: RuntimeDiagnostics = Field(default_factory=RuntimeDiagnostics)
    research: ResearchState | None = None
    content: ContentState | None = None


def new_research_state(user_task: str) -> RuntimeState:
    return RuntimeState(
        user_task=user_task.strip(),
        control=RuntimeControl(mode="research", current_stage="planning"),
        research=ResearchState(),
    )


def new_content_state(
    user_task: str,
    *,
    mode: ContentMode,
    history: list[dict[str, str]] | None = None,
    instruction: str = "",
) -> RuntimeState:
    return RuntimeState(
        user_task=user_task.strip(),
        control=RuntimeControl(mode="chat_research" if mode == "chat" else "writing", current_stage="planning"),
        content=ContentState(
            mode=mode,
            user_input=user_task.strip(),
            instruction=instruction,
            history=list(history or []),
        ),
    )


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
