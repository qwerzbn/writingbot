from __future__ import annotations

import re
from typing import Any

from src.knowledge.assets import (
    asset_matches_reference,
    asset_response_row,
    asset_search_score,
    build_visual_summary,
    extract_chart_reference,
    interpret_asset_with_llm,
    is_chart_query,
)
from src.retrieval.common import clean_source_title
from src.shared_capabilities.knowledge.access import get_kb_manager


def _page_number(page: Any) -> int | None:
    if isinstance(page, int):
        return page
    matched = re.search(r"(\d+)", str(page or ""))
    return int(matched.group(1)) if matched else None


def sort_evidence_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        sources,
        key=lambda item: (
            int(bool(item.get("is_primary"))),
            int(bool(item.get("asset_id"))),
            float(item.get("score", 0.0) or 0.0),
        ),
        reverse=True,
    )


def select_nearby_text_sources(
    primary_asset: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    asset_page = _page_number(primary_asset.get("page"))
    asset_file_id = str(primary_asset.get("file_id") or "")
    text_rows = [dict(row) for row in sources if not row.get("asset_id")]
    if not text_rows:
        return []

    def candidate_key(row: dict[str, Any]) -> tuple[int, float]:
        page = _page_number(row.get("page"))
        distance = abs((page or asset_page or 0) - (asset_page or 0)) if asset_page is not None else 99
        return (distance, -float(row.get("score", 0.0) or 0.0))

    same_file = [
        row
        for row in text_rows
        if not asset_file_id or str(row.get("file_id") or "") == asset_file_id
    ]
    candidate_rows = same_file or text_rows
    nearby = [
        row
        for row in candidate_rows
        if asset_page is not None
        and _page_number(row.get("page")) is not None
        and abs(_page_number(row.get("page")) - asset_page) <= 1
    ]
    selected = sorted(nearby, key=candidate_key)[:limit]
    if selected:
        return selected
    if asset_page is not None:
        return []
    fallback = same_file or text_rows
    return sorted(fallback, key=candidate_key)[:limit]


def build_chart_context(sources: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for idx, source in enumerate(sources, start=1):
        title = str(source.get("ref_label") or source.get("title") or source.get("source") or "Evidence").strip()
        label = "Chart Evidence" if source.get("asset_id") else "Text Evidence"
        lines = [f"[{idx}] {label}: {title}"]
        if str(source.get("summary") or "").strip():
            lines.append(f"Summary: {source.get('summary')}")
        if str(source.get("excerpt") or "").strip():
            lines.append(f"Excerpt: {source.get('excerpt')}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def normalize_paper_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in sources or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "Unknown")
        file_id = item.get("file_id")
        paper_id = item.get("paper_id") or file_id or item.get("id") or source
        authors = item.get("authors") if item.get("authors") is not None else []
        title = item.get("title") or clean_source_title(source)
        is_asset = bool(item.get("asset_id") or item.get("asset_type"))
        summary = item.get("summary")
        if summary is None:
            summary = item.get("content") or "" if is_asset else ""
        excerpt = item.get("excerpt") or item.get("content") or ""
        metadata_incomplete = not bool(item.get("title")) or not bool(item.get("paper_id"))
        normalized.append(
            {
                **item,
                "paper_id": str(paper_id),
                "title": str(title),
                "authors": authors if isinstance(authors, list) else [str(authors)],
                "section": item.get("section") or "unknown",
                "chunk_type": item.get("chunk_type") or "paragraph",
                "summary": summary,
                "excerpt": excerpt,
                "highlight_boxes": item.get("highlight_boxes") or [],
                "thumbnail_url": item.get("thumbnail_url"),
                "interpretation": item.get("interpretation"),
                "is_primary": bool(item.get("is_primary")),
                "evidence_kind": item.get("evidence_kind") or item.get("asset_type") or "text",
                "score": float(item.get("score", 0.0) or 0.0),
                "metadata_incomplete": metadata_incomplete,
            }
        )
    return normalized


def augment_chart_evidence(
    *,
    kb_id: str,
    query: str,
    context: str,
    sources: list[dict[str, Any]],
    data_dir: Any = None,
) -> dict[str, Any]:
    kb_manager = get_kb_manager(data_dir)
    assets = kb_manager.list_assets(kb_id)
    if not assets:
        return {"context": context, "sources": sources, "asset_hits": 0}
    if not is_chart_query(query):
        return {"context": context, "sources": normalize_paper_sources(sources), "asset_hits": 0}

    explicit_ref = extract_chart_reference(query)
    score_by_id = {str(asset.get("id") or ""): asset_search_score(asset, query) for asset in assets}
    ranked_assets = sorted(
        assets,
        key=lambda asset: score_by_id.get(str(asset.get("id") or ""), 0.0),
        reverse=True,
    )

    primary_asset: dict[str, Any] | None = None
    if explicit_ref:
        primary_asset = next((asset for asset in ranked_assets if asset_matches_reference(asset, explicit_ref)), None)
    if primary_asset is None:
        primary_asset = next(
            (asset for asset in ranked_assets if score_by_id.get(str(asset.get("id") or ""), 0.0) > 0.0),
            None,
        )
    if primary_asset is None:
        return {"context": context, "sources": normalize_paper_sources(sources), "asset_hits": 0}

    asset_id = str(primary_asset.get("id") or "")
    interpretation = primary_asset.get("interpretation") if isinstance(primary_asset.get("interpretation"), dict) else None
    if not interpretation:
        interpretation = interpret_asset_with_llm(primary_asset).to_dict()
        visual_summary = build_visual_summary(primary_asset, interpretation)
        primary_asset = kb_manager.update_asset(
            kb_id,
            asset_id,
            {"interpretation": interpretation, "visual_summary": visual_summary},
        ) or {**primary_asset, "interpretation": interpretation, "visual_summary": visual_summary}

    asset_payload = asset_response_row(kb_id, {**primary_asset, "interpretation": interpretation, "is_primary": True})
    asset_row = {
        **asset_payload,
        "id": asset_id,
        "source": primary_asset.get("source_file") or "Unknown",
        "page": primary_asset.get("page", "?"),
        "line_start": None,
        "line_end": None,
        "file_id": primary_asset.get("file_id"),
        "paper_id": primary_asset.get("file_id") or asset_id,
        "section": primary_asset.get("ref_label") or primary_asset.get("kind") or "asset",
        "chunk_type": primary_asset.get("kind") or "figure",
        "asset_id": asset_id,
        "asset_type": primary_asset.get("kind"),
        "caption": primary_asset.get("caption"),
        "ref_label": primary_asset.get("ref_label"),
        "bbox": primary_asset.get("bbox"),
        "page_width": primary_asset.get("page_width"),
        "page_height": primary_asset.get("page_height"),
        "highlight_boxes": asset_payload.get("highlight_boxes") or [],
        "interpretation": interpretation,
        "score": max(float(score_by_id.get(asset_id, 0.0) or 0.0), 0.96),
        "relevance": max(float(score_by_id.get(asset_id, 0.0) or 0.0), 0.72),
        "factual_risk": 0.16,
        "is_primary": True,
        "evidence_kind": primary_asset.get("kind") or "figure",
    }

    nearby_text_sources = select_nearby_text_sources(asset_row, sources, limit=2)
    focused_sources = [asset_row]
    for row in nearby_text_sources:
        focused_sources.append(
            {
                **row,
                "title": row.get("title") or clean_source_title(str(row.get("source") or "")),
                "summary": row.get("summary") or "",
                "excerpt": row.get("excerpt") or row.get("content") or "",
                "is_primary": False,
                "evidence_kind": row.get("evidence_kind") or "text",
            }
        )

    focused_sources = sort_evidence_sources(focused_sources)
    return {
        "context": build_chart_context(focused_sources),
        "sources": normalize_paper_sources(focused_sources),
        "asset_hits": 1,
    }
