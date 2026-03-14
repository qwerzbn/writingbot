# -*- coding: utf-8 -*-
"""Offline evaluation runner and report store."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.evaluation.metrics import citation_precision, faithfulness, helpfulness, mrr_at_k, recall_at_k
from src.orchestrator.service import get_orchestrator_service


@dataclass
class EvalJob:
    id: str
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    report_path: str | None = None
    error: str | None = None


class EvaluationService:
    def __init__(self, data_dir: str | Path = "./data/evaluation"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir = self.data_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_path = self.data_dir / "dataset.jsonl"
        self._jobs: dict[str, EvalJob] = {}
        self._lock = threading.RLock()

    def create_job(self) -> EvalJob:
        with self._lock:
            job = EvalJob(id=str(uuid.uuid4()))
            self._jobs[job.id] = job
            return job

    def get_job(self, job_id: str) -> EvalJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def run_async(self, job_id: str) -> None:
        th = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        th.start()

    def _run_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        self._set_status(job, "running")
        try:
            dataset = self._load_dataset()
            report = self._evaluate_dataset(dataset)
            report["id"] = job_id
            report["created_at"] = job.created_at
            report["finished_at"] = datetime.now().isoformat()
            report_path = self.reports_dir / f"{job_id}.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            job.report_path = str(report_path)
            self._set_status(job, "done")
        except Exception as exc:
            job.error = str(exc)
            self._set_status(job, "failed")

    def load_report(self, job_id: str) -> dict[str, Any] | None:
        job = self.get_job(job_id)
        if not job:
            path = self.reports_dir / f"{job_id}.json"
            if not path.exists():
                return None
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("status", data.get("status", "done"))
            return data
        if not job.report_path:
            return {
                "id": job_id,
                "status": job.status,
                "error": job.error,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
            }
        path = Path(job.report_path)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data["status"] = job.status
        data["updated_at"] = job.updated_at
        data["error"] = job.error
        return data

    def list_reports(self, limit: int = 10) -> list[dict[str, Any]]:
        reports: list[dict[str, Any]] = []
        for path in sorted(self.reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                reports.append(
                    {
                        "id": data.get("id") or path.stem,
                        "status": data.get("status", "done"),
                        "created_at": data.get("created_at"),
                        "finished_at": data.get("finished_at"),
                        "dataset_size": data.get("dataset_size"),
                        "summary": data.get("summary", {}),
                        "gate": data.get("gate", {}),
                    }
                )
            except Exception:
                continue
        return reports

    def latest_report_summary(self) -> dict[str, Any] | None:
        reports = self.list_reports(limit=1)
        if not reports:
            return None
        return reports[0]

    def _set_status(self, job: EvalJob, status: str) -> None:
        with self._lock:
            job.status = status
            job.updated_at = datetime.now().isoformat()

    def _load_dataset(self) -> list[dict[str, Any]]:
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found: {self.dataset_path}")
        rows: list[dict[str, Any]] = []
        with open(self.dataset_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        if len(rows) < 120:
            raise ValueError("Dataset must contain at least 120 items")
        return rows

    def _evaluate_dataset(self, dataset: list[dict[str, Any]]) -> dict[str, Any]:
        orchestrator = get_orchestrator_service()
        per_item: list[dict[str, Any]] = []
        sums = {
            "Recall@5": 0.0,
            "MRR@10": 0.0,
            "Citation Precision": 0.0,
            "Faithfulness": 0.0,
            "Answer Helpfulness": 0.0,
            "latency_ms": 0.0,
        }

        for item in dataset:
            mode = item.get("mode") or self._infer_mode(item.get("task_type", "single_hop"))
            payload = self._build_payload(item, mode)
            t0 = datetime.now()
            result = orchestrator.execute_sync(mode=mode, payload=payload)
            latency_ms = int((datetime.now() - t0).total_seconds() * 1000)

            answer = result.get("output", "")
            sources = result.get("sources", [])
            expected_sources = item.get("expected_sources", [])

            recall = recall_at_k(sources, expected_sources, k=5)
            mrr = mrr_at_k(sources, expected_sources, k=10)
            cprec = citation_precision(answer, sources)
            faith = faithfulness(answer, sources)
            helpf = helpfulness(answer, item.get("query", ""))

            row = {
                "id": item.get("id"),
                "mode": mode,
                "task_type": item.get("task_type"),
                "metrics": {
                    "Recall@5": recall,
                    "MRR@10": mrr,
                    "Citation Precision": cprec,
                    "Faithfulness": faith,
                    "Answer Helpfulness": helpf,
                    "latency_ms": latency_ms,
                },
            }
            per_item.append(row)

            sums["Recall@5"] += recall
            sums["MRR@10"] += mrr
            sums["Citation Precision"] += cprec
            sums["Faithfulness"] += faith
            sums["Answer Helpfulness"] += helpf
            sums["latency_ms"] += latency_ms

        n = max(1, len(per_item))
        summary = {k: round(v / n, 4) for k, v in sums.items()}
        gate = {
            "Citation Precision >= 0.85": summary["Citation Precision"] >= 0.85,
            "Faithfulness >= 0.80": summary["Faithfulness"] >= 0.8,
        }
        blocked = not all(gate.values())

        return {
            "dataset_size": len(per_item),
            "summary": summary,
            "gate": gate,
            "status": "blocked" if blocked else "pass",
            "items": per_item,
        }

    @staticmethod
    def _infer_mode(task_type: str) -> str:
        if task_type in {"survey", "research"}:
            return "research"
        if task_type in {"single_hop", "multi_hop"}:
            # Chat mode has been removed; fallback to research mode for QA-style items.
            return "research"
        return "writing"

    @staticmethod
    def _build_payload(item: dict[str, Any], mode: str) -> dict[str, Any]:
        if mode == "research":
            return {
                "topic": item.get("query", ""),
                "kb_id": item.get("kb_id"),
            }
        return {
            "text": item.get("input_text", item.get("query", "")),
            "action": item.get("action", "polish"),
            "instruction": item.get("instruction", ""),
            "kb_id": item.get("kb_id"),
        }


_evaluation_service: EvaluationService | None = None


def get_evaluation_service() -> EvaluationService:
    global _evaluation_service
    if _evaluation_service is None:
        _evaluation_service = EvaluationService()
    return _evaluation_service
