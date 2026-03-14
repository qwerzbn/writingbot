# -*- coding: utf-8 -*-
"""Orchestrator core data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal


OrchestratorMode = Literal["research", "writing"]
OrchestratorStep = Literal["plan", "retrieve", "synthesize", "critique", "finalize"]
StepStatus = Literal["working", "done", "retry", "skipped", "error"]


@dataclass
class AgentEnvelope:
    """Standardized payload passed between orchestrator stages."""

    task_id: str
    step: OrchestratorStep
    evidence: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunRecord:
    """In-memory run record."""

    run_id: str
    trace_id: str
    mode: OrchestratorMode
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(hours=2))
    status: str = "pending"
    result: dict[str, Any] = field(default_factory=dict)
    metrics: list[dict[str, Any]] = field(default_factory=list)

    def touch(self, ttl_hours: int = 2) -> None:
        self.expires_at = datetime.now() + timedelta(hours=ttl_hours)


@dataclass
class RunExecutionContext:
    """Mutable context shared by stage handlers."""

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
