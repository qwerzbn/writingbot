from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from src.agent_runtime.state import RuntimeMode


@dataclass
class RunRecord:
    run_id: str
    trace_id: str
    mode: RuntimeMode
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(hours=2))
    status: str = "pending"
    result: dict[str, Any] = field(default_factory=dict)
    metrics: list[dict[str, Any]] = field(default_factory=list)

    def touch(self, ttl_hours: int = 2) -> None:
        self.expires_at = datetime.now() + timedelta(hours=ttl_hours)


class RunStore:
    def __init__(self, ttl_hours: int = 2):
        self._ttl_hours = ttl_hours
        self._runs: dict[str, RunRecord] = {}
        self._lock = threading.RLock()

    def _cleanup_expired(self) -> None:
        now = datetime.now()
        expired = [run_id for run_id, run in self._runs.items() if run.expires_at <= now]
        for run_id in expired:
            self._runs.pop(run_id, None)

    def create_run(self, mode: RuntimeMode, payload: dict[str, Any]) -> RunRecord:
        with self._lock:
            self._cleanup_expired()
            run = RunRecord(run_id=str(uuid.uuid4()), trace_id=str(uuid.uuid4()), mode=mode, payload=payload)
            run.touch(self._ttl_hours)
            self._runs[run.run_id] = run
            return run

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            self._cleanup_expired()
            run = self._runs.get(run_id)
            if run:
                run.touch(self._ttl_hours)
            return run

    def set_status(self, run_id: str, status: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run.status = status
            run.touch(self._ttl_hours)

    def set_result(self, run_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run.result = result
            run.status = "done"
            run.touch(self._ttl_hours)

    def append_metric(self, run_id: str, metric: dict[str, Any]) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run.metrics.append(metric)
            run.touch(self._ttl_hours)
