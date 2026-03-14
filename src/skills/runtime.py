# -*- coding: utf-8 -*-
"""Runtime execution helpers for research skills."""

from __future__ import annotations

import time
from typing import Any

from src.skills.registry import SkillDefinition


_SKILL_INSTRUCTIONS: dict[str, str] = {
    "/paper-find": "优先给出与问题最相关的论文及证据片段，注明[1][2]引用索引。",
    "/paper-summary": "按论文粒度总结：研究问题、方法、数据集、结论与局限。",
    "/paper-compare": "比较不同论文的方法假设、实验设置与结果差异。",
    "/method-explain": "解释核心方法原理、输入输出、适用边界与实现要点。",
    "/related-work": "以主题维度组织相关工作，并指出研究空白。",
    "/citation-check": "最终回答中每个关键结论都尽量附引用；缺失引用需标注（推断）。",
    "/limitations": "明确列出证据不足、外推风险和方法局限。",
    "/experiment-ideas": "补充可执行的后续实验设计与评估指标建议。",
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
