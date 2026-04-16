from __future__ import annotations

from pathlib import Path
import pytest

fitz = pytest.importorskip("fitz")

from src.parsing.pdf_parser import PDFParser
from src.knowledge.assets import asset_search_score


def _build_pdf_with_figure(pdf_path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 88), "This paper studies chart-aware retrieval for academic assistants.")
    page.draw_rect(fitz.Rect(90, 180, 500, 520), color=(0.2, 0.4, 0.8), fill=(0.88, 0.93, 1.0))
    page.insert_text(
        fitz.Point(90, 610),
        "Figure 3. Accuracy rises as chart evidence is added to the retrieval pipeline.",
    )
    page.insert_text((90, 650), "The caption suggests a strong positive trend after multimodal grounding.")
    doc.save(pdf_path)
    doc.close()


def test_parse_with_assets_extracts_figure_thumbnail_and_metadata(tmp_path):
    pdf_path = tmp_path / "figure-demo.pdf"
    asset_dir = tmp_path / "assets"
    _build_pdf_with_figure(pdf_path)

    parser = PDFParser()
    content_list, assets = parser.parse_with_assets(str(pdf_path), asset_output_dir=str(asset_dir), file_id="file-1")

    assert content_list
    assert len(assets) == 1

    asset = assets[0]
    assert asset["kind"] == "figure"
    assert asset["file_id"] == "file-1"
    assert asset["page"] == 1
    assert asset["ref_label"] == "Fig. 3"
    assert "Accuracy rises" in asset["caption"]
    assert len(asset["bbox"]) == 4
    assert asset["bbox"][3] > asset["bbox"][1]
    assert asset["image_path"]
    assert Path(asset["image_path"]).exists()
    assert asset["visual_summary"].startswith("Accuracy rises")


def test_asset_search_score_uses_visual_summary_for_fuzzy_chart_match():
    asset = {
        "id": "asset-1",
        "kind": "figure",
        "ref_label": "Fig. 1",
        "caption": "Figure 1. Overall pipeline overview.",
        "nearby_text": "This section introduces the full workflow.",
        "visual_summary": "ARC system runtime architecture diagram with planning and execution stages.",
        "source_file": "arc-paper.pdf",
    }

    strong = asset_search_score(asset, "请解释 ARC 的运行架构图")
    weak = asset_search_score(asset, "请比较表2中的实验指标")

    assert strong > weak
