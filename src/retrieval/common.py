# -*- coding: utf-8 -*-
"""Shared helpers for hybrid retrieval."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]", text.lower())


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # Rough multilingual estimate for budgeting.
    return max(1, int(len(text) / 3.5))


def stable_doc_id(content: str, metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    raw = "|".join(
        [
            str(metadata.get("source", "")),
            str(metadata.get("page", "")),
            str(metadata.get("chunk_idx", "")),
            content[:256],
        ]
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def safe_norm(scores: list[float]) -> list[float]:
    if not scores:
        return []
    max_score = max(scores)
    min_score = min(scores)
    if math.isclose(max_score, min_score):
        return [1.0 for _ in scores]
    scale = max_score - min_score
    return [(s - min_score) / scale for s in scores]
