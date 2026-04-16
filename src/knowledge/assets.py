# -*- coding: utf-8 -*-
"""Knowledge asset models and figure/table utilities."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from src.retrieval.common import (
    build_sentence_excerpt,
    clean_source_title,
    normalize_display_text,
    tokenize,
)
from src.services.llm import get_llm_client


AssetKind = Literal["figure", "table"]

_CAPTION_RE = re.compile(
    r"^\s*(?P<label>(?:fig(?:ure)?|table|图|表))[\s\.:-]*(?P<index>[A-Za-z]?\d+(?:\.\d+)?)?",
    re.IGNORECASE,
)
_QUERY_REF_RE = re.compile(
    r"(?P<label>(?:fig(?:ure)?|table|图|表))[\s\.:-]*(?P<index>[A-Za-z]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_CHART_QUERY_TERMS = (
    "图",
    "表",
    "图表",
    "表格",
    "figure",
    "fig.",
    "fig",
    "table",
    "实验结果",
    "趋势",
    "对比",
    "比较",
    "消融",
    "ablation",
    "trend",
    "compare",
    "comparison",
    "metric",
    "结果",
)


@dataclass
class ChartInterpretation:
    """Structured multimodal interpretation payload."""

    chart_type: str
    main_message: str
    entities: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    trend: str = ""
    evidence_text: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["confidence"] = round(max(0.0, min(1.0, float(payload["confidence"] or 0.0))), 4)
        return payload


@dataclass
class KnowledgeAsset:
    """Figure/table asset extracted from a paper PDF."""

    id: str
    kind: AssetKind
    page: int
    bbox: list[float]
    page_width: float
    page_height: float
    caption: str
    ref_label: str
    image_path: str
    source_file: str
    file_id: str = ""
    nearby_text: str = ""
    visual_summary: str = ""
    interpretation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bbox"] = [round(float(v), 2) for v in payload.get("bbox", [])]
        return payload


def normalize_asset_kind(label: str) -> AssetKind:
    text = (label or "").strip().lower()
    if text.startswith("table") or text.startswith("表"):
        return "table"
    return "figure"


def normalize_ref_label(text: str, fallback_kind: AssetKind = "figure", default_index: int | None = None) -> str:
    raw = (text or "").strip()
    match = _CAPTION_RE.match(raw)
    kind = fallback_kind
    index_text = str(default_index or 0)
    if match:
        kind = normalize_asset_kind(match.group("label") or fallback_kind)
        index_text = (match.group("index") or "").strip() or index_text
    prefix = "Table" if kind == "table" else "Fig."
    if not index_text or index_text == "0":
        return prefix
    if kind == "table":
        return f"{prefix} {index_text}"
    return f"{prefix} {index_text}"


def is_chart_query(query: str) -> bool:
    lowered = (query or "").lower()
    return any(term in lowered for term in _CHART_QUERY_TERMS)


def extract_chart_reference(query: str) -> dict[str, str] | None:
    match = _QUERY_REF_RE.search(query or "")
    if not match:
        return None
    kind = normalize_asset_kind(match.group("label") or "figure")
    index = str(match.group("index") or "").strip()
    if not index:
        return None
    return {
        "kind": kind,
        "index": index.lower(),
        "ref_label": f"Table {index}" if kind == "table" else f"Fig. {index}",
    }


def _reference_index(text: str) -> str:
    match = re.search(r"([A-Za-z]?\d+(?:\.\d+)?)", text or "", flags=re.IGNORECASE)
    return str(match.group(1) or "").strip().lower() if match else ""


def asset_matches_reference(asset: dict[str, Any], reference: dict[str, str] | None) -> bool:
    if not reference:
        return False
    kind = str(asset.get("kind") or "")
    index = _reference_index(str(asset.get("ref_label") or asset.get("caption") or ""))
    return kind == reference.get("kind") and index == reference.get("index")


def asset_search_score(asset: dict[str, Any], query: str) -> float:
    if not query.strip():
        return 0.0
    interpretation = asset.get("interpretation") if isinstance(asset.get("interpretation"), dict) else {}
    visual_summary = normalize_display_text(
        str(asset.get("visual_summary") or interpretation.get("main_message") or ""),
        preserve_paragraphs=False,
    )
    text = " ".join(
        [
            str(asset.get("ref_label") or ""),
            str(asset.get("caption") or ""),
            str(asset.get("nearby_text") or ""),
            visual_summary,
            str(asset.get("kind") or ""),
        ]
    ).lower()
    query_lower = query.lower()
    score = 0.0
    explicit_ref = extract_chart_reference(query)

    ref_label = str(asset.get("ref_label") or "").lower()
    if ref_label and ref_label in query_lower:
        score += 4.0

    if explicit_ref:
        asset_index = _reference_index(str(asset.get("ref_label") or asset.get("caption") or ""))
        asset_kind = str(asset.get("kind") or "")
        if asset_kind == explicit_ref["kind"] and asset_index == explicit_ref["index"]:
            score += 8.0
        elif asset_index == explicit_ref["index"]:
            score -= 3.0
        elif asset_kind != explicit_ref["kind"]:
            score -= 0.8

    caption = str(asset.get("caption") or "")
    if caption and caption.lower() in query_lower:
        score += 2.0
    if visual_summary and visual_summary.lower() in query_lower:
        score += 2.8

    query_tokens = tokenize(query)
    asset_tokens = set(tokenize(text))
    overlap = [tok for tok in query_tokens if tok in asset_tokens]
    score += min(3.0, len(set(overlap)) * 0.6)
    if visual_summary:
        summary_tokens = set(tokenize(visual_summary))
        summary_overlap = [tok for tok in query_tokens if tok in summary_tokens]
        score += min(2.0, len(set(summary_overlap)) * 0.7)

    kind = str(asset.get("kind") or "")
    if kind == "figure" and any(term in query_lower for term in ("figure", "fig", "图")):
        score += 1.2
    if kind == "table" and any(term in query_lower for term in ("table", "表")):
        score += 1.2

    # Source-file disambiguation: if the query mentions keywords from the file name
    # (e.g. "ARC的图3" → boost ARC paper assets over unrelated papers)
    source_file = str(asset.get("source_file") or "").lower()
    # Strip common separators to get meaningful tokens from the file name
    source_tokens = set(re.split(r"[\s_\-\.]+", source_file)) - {"", "pdf", "arxiv", "paper"}
    for token in source_tokens:
        if len(token) >= 3 and token in query_lower:
            score += 3.0
            break

    return round(score, 4)


def _strip_caption_prefix(text: str) -> str:
    compact = normalize_display_text(text, preserve_paragraphs=False)
    return re.sub(
        r"^(?:fig(?:ure)?|table|图|表)[\s\.:-]*[A-Za-z]?\d+(?:\.\d+)?[\s\.:-]*",
        "",
        compact,
        flags=re.IGNORECASE,
    ).strip()


def build_asset_summary(asset: dict[str, Any], interpretation: dict[str, Any] | None = None) -> str:
    interpretation = interpretation if isinstance(interpretation, dict) else {}
    kind = str(asset.get("kind") or "figure")
    ref_label = str(asset.get("ref_label") or ("Table" if kind == "table" else "Fig.")).strip()
    caption = str(asset.get("caption") or "").strip()
    nearby_text = str(asset.get("nearby_text") or "").strip()
    main_message = normalize_display_text(str(interpretation.get("main_message") or ""), preserve_paragraphs=False)
    visual_summary = normalize_display_text(str(asset.get("visual_summary") or ""), preserve_paragraphs=False)
    core = _strip_caption_prefix(main_message) or visual_summary or _strip_caption_prefix(caption)
    if not core:
        core = "展示了论文中的关键实验结果" if kind == "table" else "展示了论文中的关键图表结论"
    if not core.endswith(("。", ".", "！", "!", "？", "?")):
        core = f"{core}。"

    evidence_candidates = [
        normalize_display_text(str(interpretation.get("trend") or ""), preserve_paragraphs=False),
        build_sentence_excerpt(str(interpretation.get("evidence_text") or nearby_text or caption), limit=160),
    ]
    evidence_text = next((item for item in evidence_candidates if item), "")
    if evidence_text and not evidence_text.endswith(("。", ".", "！", "!", "？", "?")):
        evidence_text = f"{evidence_text}。"
    if not evidence_text:
        evidence_text = "结合图注与邻近正文，可作为回答的直接证据。"

    return f"结论：{ref_label}主要说明了{core}\n依据：{evidence_text}"


def build_asset_excerpt(asset: dict[str, Any], interpretation: dict[str, Any] | None = None) -> str:
    interpretation = interpretation if isinstance(interpretation, dict) else {}
    kind = str(asset.get("kind") or "figure")
    caption_label = "表注" if kind == "table" else "图注"
    caption_body = _strip_caption_prefix(str(asset.get("caption") or "")) or normalize_display_text(str(asset.get("caption") or ""), preserve_paragraphs=False)
    nearby_source = str(interpretation.get("evidence_text") or asset.get("nearby_text") or "").strip()
    nearby_excerpt = build_sentence_excerpt(nearby_source, limit=220)

    parts: list[str] = []
    if caption_body:
        parts.append(f"{caption_label}：{caption_body}")
    if nearby_excerpt:
        parts.append(f"邻近正文：{nearby_excerpt}")
    return "\n".join(parts[:2])


def build_visual_summary(asset: dict[str, Any], interpretation: dict[str, Any] | None = None) -> str:
    interpretation = interpretation if isinstance(interpretation, dict) else {}
    candidates = [
        normalize_display_text(str(asset.get("visual_summary") or ""), preserve_paragraphs=False),
        normalize_display_text(str(interpretation.get("main_message") or ""), preserve_paragraphs=False),
        _strip_caption_prefix(str(asset.get("caption") or "")),
    ]
    for candidate in candidates:
        summary = build_sentence_excerpt(candidate, limit=120)
        if summary:
            return summary

    kind = str(asset.get("kind") or "figure")
    if kind == "table":
        return "该表概括了论文中的关键方法对比或指标结果。"
    return "该图概括了论文中的关键流程、现象或实验结论。"


def asset_to_chunk(asset: dict[str, Any]) -> dict[str, Any]:
    interpretation = asset.get("interpretation") if isinstance(asset.get("interpretation"), dict) else {}
    lines = [
        str(asset.get("ref_label") or asset.get("kind") or "Asset"),
        str(asset.get("caption") or "").strip(),
        str(asset.get("visual_summary") or "").strip(),
        str(asset.get("nearby_text") or "").strip(),
        str(interpretation.get("main_message") or "").strip(),
        str(interpretation.get("evidence_text") or "").strip(),
    ]
    content = "\n".join(line for line in lines if line).strip()
    return {
        "content": content,
        "metadata": {
            "source": asset.get("source_file") or "Unknown",
            "file_id": asset.get("file_id"),
            "page": asset.get("page"),
            "bbox": asset.get("bbox"),
            "page_width": asset.get("page_width"),
            "page_height": asset.get("page_height"),
            "asset_id": asset.get("id"),
            "asset_type": asset.get("kind"),
            "caption": asset.get("caption"),
            "ref_label": asset.get("ref_label"),
            "image_path": asset.get("image_path"),
            "chunk_type": asset.get("kind"),
        },
    }


def default_chart_interpretation(asset: dict[str, Any]) -> ChartInterpretation:
    kind = str(asset.get("kind") or "figure")
    caption = str(asset.get("caption") or "").strip()
    nearby_text = str(asset.get("nearby_text") or "").strip()
    visual_summary = str(asset.get("visual_summary") or "").strip()
    main_message = visual_summary or caption or f"{kind} evidence from the paper."
    trend = ""
    lowered = f"{caption} {nearby_text}".lower()
    if any(term in lowered for term in ("trend", "increase", "decrease", "提升", "下降", "趋势")):
        trend = "The surrounding text suggests a performance or trend comparison."
    elif kind == "table":
        trend = "The table likely compares methods, settings, or metrics across rows/columns."
    else:
        trend = "The figure likely visualizes a comparison, workflow, or experimental result."

    entities = []
    metrics = []
    for token in tokenize(caption):
        if re.search(r"[A-Za-z]", token) and token.lower() not in {"fig", "figure", "table"}:
            if token not in entities:
                entities.append(token)
        if len(entities) >= 4:
            break
    for token in tokenize(nearby_text):
        if any(ch.isdigit() for ch in token) or token.lower() in {"acc", "f1", "bleu", "map", "ndcg"}:
            if token not in metrics:
                metrics.append(token)
        if len(metrics) >= 4:
            break

    evidence_text = nearby_text or caption
    return ChartInterpretation(
        chart_type=kind,
        main_message=main_message,
        entities=entities,
        metrics=metrics,
        trend=trend,
        evidence_text=evidence_text[:400],
        confidence=0.38,
    )


def interpret_asset_with_llm(asset: dict[str, Any]) -> ChartInterpretation:
    image_path = str(asset.get("image_path") or "").strip()
    if not image_path or not os.path.exists(image_path):
        return default_chart_interpretation(asset)

    prompt = (
        "你是论文图表理解助手。请阅读学术论文中的单个图或表，并只输出 JSON。"
        "字段固定为 chart_type, main_message, entities, metrics, trend, evidence_text, confidence。"
        "confidence 取 0 到 1。若无法确定，请保守表达。"
        f"\nref_label: {asset.get('ref_label') or ''}"
        f"\ncaption: {asset.get('caption') or ''}"
        f"\nnearby_text: {asset.get('nearby_text') or ''}"
    )

    try:
        with open(image_path, "rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("ascii")
        client = get_llm_client().client
        response = client.chat.completions.create(
            model=getattr(get_llm_client().config, "model", None) or "",
            messages=[
                {"role": "system", "content": "你是一个严谨的学术图表分析助手，只返回 JSON。"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                    ],
                },
            ],
            temperature=0.2,
            max_tokens=800,
        )
        content = response.choices[0].message.content or ""
        if not isinstance(content, str):
            return default_chart_interpretation(asset)
        parsed = _extract_json_payload(content)
        if not parsed:
            return default_chart_interpretation(asset)
        return ChartInterpretation(
            chart_type=str(parsed.get("chart_type") or asset.get("kind") or "figure"),
            main_message=str(parsed.get("main_message") or asset.get("caption") or "").strip(),
            entities=[str(item).strip() for item in parsed.get("entities", []) if str(item).strip()],
            metrics=[str(item).strip() for item in parsed.get("metrics", []) if str(item).strip()],
            trend=str(parsed.get("trend") or "").strip(),
            evidence_text=str(parsed.get("evidence_text") or asset.get("nearby_text") or "").strip(),
            confidence=float(parsed.get("confidence", 0.68) or 0.68),
        )
    except Exception:
        return default_chart_interpretation(asset)


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    if "```" in raw:
        for match in re.findall(r"```(?:json)?\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL):
            candidates.append(match.strip())
    first = raw.find("{")
    last = raw.rfind("}")
    if first >= 0 and last > first:
        candidates.append(raw[first : last + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def asset_response_row(kb_id: str, asset: dict[str, Any]) -> dict[str, Any]:
    row = dict(asset)
    interpretation = row.get("interpretation") if isinstance(row.get("interpretation"), dict) else None
    row["visual_summary"] = build_visual_summary(asset, interpretation)
    display_asset = {**asset, "visual_summary": row["visual_summary"]}
    row["title"] = clean_source_title(str(asset.get("source_file") or ""))
    row["summary"] = build_asset_summary(display_asset, interpretation)
    row["excerpt"] = build_asset_excerpt(display_asset, interpretation)
    row["evidence_kind"] = str(asset.get("kind") or "figure")
    row["is_primary"] = bool(asset.get("is_primary"))
    row["highlight_boxes"] = [
        {
            "page": asset.get("page"),
            "bbox": asset.get("bbox"),
            "page_width": asset.get("page_width"),
            "page_height": asset.get("page_height"),
        }
    ] if asset.get("bbox") else []
    row["thumbnail_url"] = f"/api/kbs/{kb_id}/assets/{asset.get('id')}/content"
    return row


__all__ = [
    "AssetKind",
    "ChartInterpretation",
    "KnowledgeAsset",
    "asset_response_row",
    "asset_matches_reference",
    "asset_search_score",
    "asset_to_chunk",
    "build_asset_excerpt",
    "build_asset_summary",
    "build_visual_summary",
    "default_chart_interpretation",
    "extract_chart_reference",
    "interpret_asset_with_llm",
    "is_chart_query",
    "normalize_asset_kind",
    "normalize_ref_label",
]
