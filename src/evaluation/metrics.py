# -*- coding: utf-8 -*-
"""Evaluation metrics for retrieval + generation quality."""

from __future__ import annotations

import re
from typing import Any

from src.services.llm import get_llm_client


def recall_at_k(pred_sources: list[dict[str, Any]], expected_sources: list[str], k: int = 5) -> float:
    if not expected_sources:
        return 0.0
    top = pred_sources[:k]
    expected = set(expected_sources)
    hit = any((row.get("source") in expected) for row in top)
    return 1.0 if hit else 0.0


def mrr_at_k(pred_sources: list[dict[str, Any]], expected_sources: list[str], k: int = 10) -> float:
    if not expected_sources:
        return 0.0
    expected = set(expected_sources)
    for idx, row in enumerate(pred_sources[:k], start=1):
        if row.get("source") in expected:
            return 1.0 / idx
    return 0.0


def citation_precision(answer: str, pred_sources: list[dict[str, Any]]) -> float:
    citations = re.findall(r"\[([0-9]+)\]", answer or "")
    if not citations:
        return 0.0
    valid = 0
    for c in citations:
        idx = int(c) - 1
        if 0 <= idx < len(pred_sources):
            valid += 1
    return valid / max(1, len(citations))


def llm_judge_score(prompt: str) -> float:
    """Return a score in [0,1] from current LLM config; fallback heuristic on parse failure."""
    client = get_llm_client()
    messages = [
        {"role": "system", "content": "你是评测器。只输出0到1之间的小数，不要解释。"},
        {"role": "user", "content": prompt},
    ]
    try:
        text = client.chat(messages=messages, temperature=0.0, max_tokens=16).strip()
        score = float(re.findall(r"[0-1](?:\.\d+)?", text)[0])
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.5


def faithfulness(answer: str, sources: list[dict[str, Any]]) -> float:
    src_text = "\n".join([f"[{i+1}] {s.get('content', '')}" for i, s in enumerate(sources[:6])])
    prompt = (
        "基于给定证据，评估回答是否忠实。"
        f"\n\n回答:\n{answer[:1800]}"
        f"\n\n证据:\n{src_text[:1800]}"
        "\n\n请输出0-1分数，越高越忠实。"
    )
    return llm_judge_score(prompt)


def helpfulness(answer: str, question: str) -> float:
    prompt = (
        "评估以下回答对问题是否有帮助。"
        f"\n\n问题:\n{question[:1200]}"
        f"\n\n回答:\n{answer[:1800]}"
        "\n\n请输出0-1分数，越高越有帮助。"
    )
    return llm_judge_score(prompt)
