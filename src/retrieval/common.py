# -*- coding: utf-8 -*-
"""Shared helpers for hybrid retrieval."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]", text.lower())


_HYPHEN_BREAK_RE = re.compile(r"(?<=\w)[\-‐‑‒–—]\s*\n\s*(?=\w)")
_UUID_PREFIX_PATTERNS = (
    re.compile(r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_(.+)$", re.IGNORECASE),
    re.compile(r"^(?:[0-9a-f]{24,32})_(.+)$", re.IGNORECASE),
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])\s+|(?<=\.)\s+(?=[A-Z0-9])")
_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z\u4e00-\u9fff]")


def normalize_display_text(text: str, preserve_paragraphs: bool = True) -> str:
    if not text:
        return ""
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = _HYPHEN_BREAK_RE.sub("", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    if preserve_paragraphs:
        paragraphs = [
            re.sub(r"\s+", " ", paragraph).strip()
            for paragraph in re.split(r"\n{2,}", normalized)
            if paragraph.strip()
        ]
        return "\n\n".join(paragraphs)
    return re.sub(r"\s+", " ", normalized.replace("\n", " ")).strip()


def _trim_text(text: str, limit: int) -> str:
    compact = normalize_display_text(text, preserve_paragraphs=False)
    if len(compact) <= limit:
        return compact
    window = compact[: limit + 1]
    boundary = max(window.rfind(" "), window.rfind("，"), window.rfind("。"), window.rfind(", "), window.rfind(". "))
    if boundary >= max(24, int(limit * 0.55)):
        return window[:boundary].rstrip(" ,，。.;；:：")
    return compact[:limit].rstrip(" ,，。.;；:：")


def summarize_display_text(text: str, limit: int = 220) -> str:
    return _trim_text(text, limit)


def build_sentence_excerpt(
    text: str,
    query: str = "",
    limit: int = 320,
    max_sentences: int = 2,
) -> str:
    normalized = normalize_display_text(text, preserve_paragraphs=True)
    if not normalized:
        return ""

    paragraphs = [paragraph.strip() for paragraph in normalized.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        return ""

    query_tokens = set(tokenize(query))
    if query_tokens:
        paragraphs.sort(
            key=lambda paragraph: (
                len(query_tokens.intersection(tokenize(paragraph))),
                len(paragraph),
            ),
            reverse=True,
        )
    paragraph = paragraphs[0]
    sentences = [item.strip() for item in _SENTENCE_SPLIT_RE.split(paragraph) if item.strip()]
    paragraph_starts_cleanly = bool(re.match(r'^[A-Z\u4e00-\u9fff"“(（]', paragraph))
    if len(paragraph) <= limit and (paragraph_starts_cleanly or len(sentences) <= 1):
        return paragraph
    if not sentences:
        return _trim_text(paragraph, limit)

    start_index = 0
    if query_tokens:
        scored = []
        for idx, sentence in enumerate(sentences):
            overlap = len(query_tokens.intersection(tokenize(sentence)))
            scored.append((overlap, len(sentence), -idx))
        scored.sort(reverse=True)
        if scored and scored[0][0] > 0:
            start_index = -scored[0][2]

    selected: list[str] = []
    total_length = 0
    for sentence in sentences[start_index:]:
        normalized_sentence = normalize_display_text(sentence, preserve_paragraphs=False)
        if _looks_like_heading(normalized_sentence):
            continue
        projected = total_length + len(sentence) + (1 if selected else 0)
        if selected and (len(selected) >= max_sentences or projected > limit):
            break
        if not selected and len(sentence) > limit:
            return _trim_text(sentence, limit)
        selected.append(sentence)
        total_length = projected
        if len(selected) >= max_sentences:
            break

    excerpt = " ".join(selected).strip()
    if excerpt:
        return excerpt

    readable_sentences = [
        normalize_display_text(sentence, preserve_paragraphs=False)
        for sentence in sentences
        if not _looks_like_heading(sentence)
    ]
    if readable_sentences:
        return _trim_text(" ".join(readable_sentences), limit)
    return _trim_text(paragraph, limit)


def _looks_like_heading(text: str) -> bool:
    compact = normalize_display_text(text, preserve_paragraphs=False)
    if not compact:
        return True
    if compact.isdigit():
        return True
    if len(compact) <= 18 and not re.search(r"[。！？!?\.]", compact):
        return True
    if _HEADING_RE.match(compact) and len(compact) <= 90:
        return True
    return False


def select_evidence_spans(metadata: dict[str, Any] | None, query: str = "", limit: int = 2) -> list[dict[str, Any]]:
    metadata = normalize_source_metadata(metadata)
    if not isinstance(metadata, dict):
        return []
    raw_spans = metadata.get("spans")
    if not isinstance(raw_spans, list):
        return []

    query_tokens = set(tokenize(query))
    candidates: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for span in raw_spans:
        if not isinstance(span, dict):
            continue
        content = normalize_display_text(str(span.get("content") or ""), preserve_paragraphs=True)
        if not content:
            continue
        overlap = len(query_tokens.intersection(tokenize(content)))
        score = (
            overlap,
            0 if _looks_like_heading(content) else 1,
            len(content),
        )
        candidates.append((score, {**span, "content": content}))

    if not candidates:
        return []

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in candidates[: max(1, limit)]]


def build_text_evidence_excerpt(
    text: str,
    metadata: dict[str, Any] | None = None,
    query: str = "",
    limit: int = 320,
) -> str:
    metadata = normalize_source_metadata(metadata)
    spans = select_evidence_spans(metadata, query=query, limit=1)
    if spans:
        excerpt = build_sentence_excerpt(str(spans[0].get("content") or ""), query=query, limit=limit, max_sentences=2)
        if excerpt:
            return excerpt
    return build_sentence_excerpt(text, query=query, limit=limit, max_sentences=2)


def format_page_locator(
    page: int | str | None,
    line_start: int | None = None,
    line_end: int | None = None,
) -> str:
    if isinstance(page, str):
        raw = page.strip()
        if raw.startswith("第 ") and "页" in raw:
            return raw
    page_text = ""
    if isinstance(page, int) and page > 0:
        page_text = f"第 {page} 页"
    else:
        matched = re.search(r"(\d+)", str(page or ""))
        if matched:
            page_text = f"第 {matched.group(1)} 页"
    if line_start and line_end:
        line_text = f"第 {line_start} 行" if line_start == line_end else f"第 {line_start}-{line_end} 行"
        return f"{page_text} · {line_text}" if page_text else line_text
    if line_start:
        return f"{page_text} · 第 {line_start} 行" if page_text else f"第 {line_start} 行"
    return page_text or "定位未知"


def _parse_json_like(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw or raw[0] not in "[{":
        return value
    try:
        return json.loads(raw)
    except Exception:
        return value


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _coerce_bbox(value: Any) -> list[float] | None:
    parsed = _parse_json_like(value)
    if not isinstance(parsed, list) or len(parsed) != 4:
        return None
    try:
        return [float(item) for item in parsed]
    except Exception:
        return None


def normalize_source_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload["line_start"] = _coerce_int(payload.get("line_start"))
    payload["line_end"] = _coerce_int(payload.get("line_end"))
    payload["page_width"] = _coerce_float(payload.get("page_width"))
    payload["page_height"] = _coerce_float(payload.get("page_height"))
    payload["bbox"] = _coerce_bbox(payload.get("bbox"))

    raw_spans = _parse_json_like(payload.get("spans"))
    if isinstance(raw_spans, list):
        normalized_spans: list[dict[str, Any]] = []
        for span in raw_spans:
            if not isinstance(span, dict):
                continue
            normalized_spans.append(
                {
                    **span,
                    "bbox": _coerce_bbox(span.get("bbox")),
                    "line_start": _coerce_int(span.get("line_start")),
                    "line_end": _coerce_int(span.get("line_end")),
                    "page_width": _coerce_float(span.get("page_width")),
                    "page_height": _coerce_float(span.get("page_height")),
                }
            )
        payload["spans"] = normalized_spans
    else:
        payload["spans"] = []

    raw_boxes = _parse_json_like(payload.get("highlight_boxes"))
    if isinstance(raw_boxes, list):
        normalized_boxes: list[dict[str, Any]] = []
        for box in raw_boxes:
            if not isinstance(box, dict):
                continue
            normalized_boxes.append(
                {
                    **box,
                    "page": _coerce_int(box.get("page")),
                    "bbox": _coerce_bbox(box.get("bbox")),
                    "line_start": _coerce_int(box.get("line_start")),
                    "line_end": _coerce_int(box.get("line_end")),
                    "page_width": _coerce_float(box.get("page_width")),
                    "page_height": _coerce_float(box.get("page_height")),
                }
            )
        payload["highlight_boxes"] = normalized_boxes
    else:
        payload["highlight_boxes"] = []

    return payload


def clean_source_title(source: str, strip_extension: bool = True) -> str:
    raw = Path(str(source or "")).name
    if not raw:
        return "来源"

    cleaned = raw
    changed = True
    while changed:
        changed = False
        for pattern in _UUID_PREFIX_PATTERNS:
            match = pattern.match(cleaned)
            if match:
                cleaned = match.group(1)
                changed = True
                break

    if strip_extension:
        cleaned = re.sub(r"\.(pdf|txt|md|docx?)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"_+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "来源"


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
