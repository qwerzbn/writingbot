# -*- coding: utf-8 -*-
"""Runtime execution helpers for research skills."""

from __future__ import annotations

import time
from typing import Any

from src.skills.registry import SkillDefinition


def run_research_skill_chain(
    *,
    skills: list[SkillDefinition],
    has_kb: bool,
    sources: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    instructions: list[str] = []
    runs: list[dict[str, Any]] = []
    success_count = 0
    total = len(skills)

    for skill in skills:
        started = time.time()
        status = "ok"
        error = ""
        try:
            if skill.requires_kb and not has_kb:
                status = "skipped_requires_kb"
            else:
                inst = (skill.instruction or "").strip()
                if inst:
                    instructions.append(inst)
                success_count += 1
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = str(exc)
            if skill.critical:
                runs.append(
                    {
                        "skill_id": skill.id,
                        "status": status,
                        "critical": True,
                        "error": error,
                        "duration_ms": int((time.time() - started) * 1000),
                    }
                )
                raise
        runs.append(
            {
                "skill_id": skill.id,
                "status": status,
                "critical": skill.critical,
                "error": error,
                "duration_ms": int((time.time() - started) * 1000),
            }
        )

    unique_papers = {
        str(src.get("paper_id") or src.get("file_id") or src.get("source") or "").strip()
        for src in sources
        if isinstance(src, dict)
    }
    unique_papers.discard("")

    metrics = {
        "skill_success_rate": round(success_count / max(1, total), 4),
        "paper_hits": len(unique_papers),
    }
    return instructions, runs, metrics
