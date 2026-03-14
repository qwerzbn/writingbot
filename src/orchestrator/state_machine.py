# -*- coding: utf-8 -*-
"""Finite state machine for orchestrator stage transitions."""

from __future__ import annotations

from src.orchestrator.models import OrchestratorStep


class OrchestratorStateMachine:
    """Simple deterministic FSM for the orchestration lifecycle."""

    ORDER: tuple[OrchestratorStep, ...] = (
        "plan",
        "retrieve",
        "synthesize",
        "critique",
        "finalize",
    )

    def __init__(self) -> None:
        self._index = 0

    @property
    def current(self) -> OrchestratorStep:
        return self.ORDER[self._index]

    def advance(self) -> OrchestratorStep | None:
        """Move to the next stage and return it, or None if finished."""
        if self._index >= len(self.ORDER) - 1:
            return None
        self._index += 1
        return self.ORDER[self._index]

    def remaining(self) -> list[OrchestratorStep]:
        return list(self.ORDER[self._index :])

    def is_terminal(self, step: OrchestratorStep) -> bool:
        return step == "finalize"
