# -*- coding: utf-8 -*-
"""SSE event helpers for orchestrator streams."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def now_iso() -> str:
    return datetime.now().isoformat()


def build_init_event(run_id: str, trace_id: str, mode: str, **extra: Any) -> dict[str, Any]:
    return {
        "type": "init",
        "run_id": run_id,
        "trace_id": trace_id,
        "mode": mode,
        "timestamp": now_iso(),
        **extra,
    }


def build_step_event(
    step: str,
    status: str,
    attempt: int = 1,
    message: str = "",
    duration_ms: int | None = None,
    confidence: float | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "step",
        "step": step,
        "status": status,
        "attempt": attempt,
        "message": message,
        "timestamp": now_iso(),
        **extra,
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if confidence is not None:
        payload["confidence"] = confidence
    return payload


def build_metric_event(name: str, value: float | int, unit: str = "", **extra: Any) -> dict[str, Any]:
    return {
        "type": "metric",
        "name": name,
        "value": value,
        "unit": unit,
        "timestamp": now_iso(),
        **extra,
    }


def build_done_event(run_id: str, trace_id: str, output: str = "", **extra: Any) -> dict[str, Any]:
    return {
        "type": "done",
        "run_id": run_id,
        "trace_id": trace_id,
        "output": output,
        "timestamp": now_iso(),
        **extra,
    }


def build_error_event(error: str, step: str = "", retryable: bool = False, **extra: Any) -> dict[str, Any]:
    return {
        "type": "error",
        "error": error,
        "step": step,
        "retryable": retryable,
        "timestamp": now_iso(),
        **extra,
    }
