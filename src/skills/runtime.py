# -*- coding: utf-8 -*-
"""Runtime execution helpers for research skills."""

from __future__ import annotations

import time
from typing import Any

from src.skills.registry import SkillDefinition


_SKILL_INSTRUCTIONS: dict[str, str] = {
    "/paper-summary": "按论文粒度总结：研究问题、方法、数据集、结论与局限。",
    "/experiment-compare": "重点比较实验设置、指标定义、结果差异及可能原因。",
    "/innovation-summary": "总结核心创新点、技术贡献和与现有工作的关键区别。",
    "/research-gaps": "明确研究不足、适用边界、潜在偏差及可改进方向。",
}


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
                inst = _SKILL_INSTRUCTIONS.get(skill.id, "").strip()
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
