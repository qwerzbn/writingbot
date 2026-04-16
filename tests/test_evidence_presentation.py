from __future__ import annotations

from src.knowledge.assets import asset_search_score, extract_chart_reference
from src.retrieval.common import (
    build_sentence_excerpt,
    build_text_evidence_excerpt,
    clean_source_title,
    format_page_locator,
    normalize_display_text,
)


def test_normalize_display_text_merges_hyphenated_line_breaks():
    raw = "an achieves state-of-the-art multi-step reasoning per-\nformance among frontier models."
    cleaned = normalize_display_text(raw, preserve_paragraphs=False)
    assert "per-\nformance" not in cleaned
    assert "performance among frontier models." in cleaned


def test_build_sentence_excerpt_returns_readable_sentence():
    raw = (
        "frame, and x is the mean position of all evidence frames. "
        "The overall difficulty is then defined as EDI = (1-P) Var, "
        "where higher EDI values indicate sparser evidences."
    )
    excerpt = build_sentence_excerpt(raw, query="overall difficulty", limit=140, max_sentences=2)
    assert "overall difficulty" in excerpt.lower()
    assert excerpt.endswith(".")


def test_clean_source_title_removes_uuid_noise():
    source = "60629ba1-ac90-4ac9-8a71-a1415ba252a9_f19f06fd4ed746c28d6d9c41b63963f8_Conan- Progressive Learning.pdf"
    assert clean_source_title(source) == "Conan- Progressive Learning"


def test_extract_chart_reference_and_score_prefer_exact_kind():
    figure_asset = {"kind": "figure", "ref_label": "Fig. 3", "caption": "Figure 3. Training dynamics.", "nearby_text": ""}
    table_asset = {"kind": "table", "ref_label": "Table 3", "caption": "Table 3. Ablation results.", "nearby_text": ""}

    ref = extract_chart_reference("请解释图3的核心结论")
    assert ref == {"kind": "figure", "index": "3", "ref_label": "Fig. 3"}
    assert asset_search_score(figure_asset, "请解释图3的核心结论") > asset_search_score(table_asset, "请解释图3的核心结论")


def test_build_text_evidence_excerpt_prefers_readable_span():
    metadata = {
        "spans": [
            {"content": "3\n2. Related Work", "line_start": 8, "line_end": 9},
            {
                "content": "Conan achieves state-of-the-art multi-step reasoning performance among frontier MLLMs.",
                "line_start": 10,
                "line_end": 12,
            },
        ]
    }
    excerpt = build_text_evidence_excerpt("fallback chunk", metadata=metadata, limit=180)
    assert "state-of-the-art" in excerpt
    assert "Related Work" not in excerpt


def test_format_page_locator_includes_line_range():
    assert format_page_locator(3, 12, 16) == "第 3 页 · 第 12-16 行"
