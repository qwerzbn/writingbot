# -*- coding: utf-8 -*-
"""Legacy orchestrator model aliases preserved for compatibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.agent_runtime.store import RunRecord


OrchestratorMode = Literal["research", "writing", "chat_research"]
OrchestratorStep = Literal["plan", "retrieve", "synthesize", "critique", "finalize"]
StepStatus = Literal["working", "done", "retry", "skipped", "error"]


@dataclass
class RunExecutionContext:
    """Deprecated compatibility surface for older orchestrator unit tests."""

    run: RunRecord
    sub_questions: list[str] = field(default_factory=list)
    plan: str = ""
    context: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    generated_text: str = ""
    critique: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    chat_history: list[dict[str, str]] = field(default_factory=list)
    message: str = ""
    selected_skill_ids: list[str] = field(default_factory=list)


__all__ = [
    "OrchestratorMode",
    "OrchestratorStep",
    "StepStatus",
    "RunExecutionContext",
    "RunRecord",
]
