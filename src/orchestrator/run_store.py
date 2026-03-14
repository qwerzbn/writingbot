# -*- coding: utf-8 -*-
"""In-memory run registry with TTL cleanup."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime

from src.orchestrator.models import OrchestratorMode, RunRecord


class RunStore:
    """Thread-safe in-memory run store."""

    def __init__(self, ttl_hours: int = 2):
        self._ttl_hours = ttl_hours
        self._runs: dict[str, RunRecord] = {}
        self._lock = threading.RLock()

    def _cleanup_expired(self) -> None:
        now = datetime.now()
        expired = [run_id for run_id, run in self._runs.items() if run.expires_at <= now]
        for run_id in expired:
            self._runs.pop(run_id, None)

    def create_run(self, mode: OrchestratorMode, payload: dict) -> RunRecord:
        with self._lock:
            self._cleanup_expired()
            run = RunRecord(
                run_id=str(uuid.uuid4()),
                trace_id=str(uuid.uuid4()),
                mode=mode,
                payload=payload,
            )
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

    def set_result(self, run_id: str, result: dict) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run.result = result
            run.status = "done"
            run.touch(self._ttl_hours)

    def append_metric(self, run_id: str, metric: dict) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run.metrics.append(metric)
            run.touch(self._ttl_hours)
