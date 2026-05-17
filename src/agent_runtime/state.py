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

RuntimeMode = Literal["writing", "chat_research"]
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
    mode: RuntimeMode = "writing"
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
    content: ContentState | None = None


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
