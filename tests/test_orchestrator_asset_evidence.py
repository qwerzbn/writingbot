from __future__ import annotations

from pathlib import Path

from src.knowledge.assets import ChartInterpretation
from src.knowledge.kb_manager import KnowledgeBaseManager
import src.orchestrator.service as orchestrator_service


def test_augment_chart_evidence_appends_interpreted_asset(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(orchestrator_service, "DATA_DIR", data_dir)

    kb_manager = KnowledgeBaseManager(data_dir / "knowledge_bases")
    kb = kb_manager.create_kb("asset-orchestrator")
    kb_id = str(kb["id"])

    image_path = kb_manager.get_assets_path(kb_id) / "fig3.png"
    image_path.write_bytes(b"fake-image")
    kb_manager.add_assets(
        kb_id,
        [
            {
                "id": "asset-fig-3",
                "kind": "figure",
                "page": 3,
                "bbox": [20.0, 100.0, 520.0, 420.0],
                "caption": "Figure 3. Citation quality improves when chart evidence is added.",
                "ref_label": "Fig. 3",
                "image_path": str(image_path),
                "source_file": "paper.pdf",
                "file_id": "file-1",
                "nearby_text": "The text states that chart grounding improves citation quality and evidence coverage.",
                "visual_summary": "The figure shows chart grounding improves citation quality and evidence coverage.",
            },
            {
                "id": "asset-table-3",
                "kind": "table",
                "page": 8,
                "bbox": [20.0, 100.0, 520.0, 420.0],
                "caption": "Table 3. Ablation results of Conan.",
                "ref_label": "Table 3",
                "image_path": str(image_path),
                "source_file": "paper.pdf",
                "file_id": "file-1",
                "nearby_text": "Table 3 reports ablation results.",
            }
        ],
    )

    monkeypatch.setattr(
        orchestrator_service,
        "interpret_asset_with_llm",
        lambda asset: ChartInterpretation(
            chart_type="figure",
            main_message="Chart grounding increases citation quality.",
            entities=["chart grounding"],
            metrics=["citation quality"],
            trend="The curve rises after chart evidence is introduced.",
            evidence_text="Nearby text says citation quality and evidence coverage both improve.",
            confidence=0.9,
        ),
    )

    service = orchestrator_service.OrchestratorService()
    augmented = service._augment_chart_evidence(  # noqa: SLF001 - explicit unit coverage for shared helper
        kb_id=kb_id,
        query="请解释图3的核心结论，并说明它支持了作者哪条主张",
        context="",
        sources=[
            {
                "source": "paper.pdf",
                "page": 3,
                "file_id": "file-1",
                "title": "paper",
                "summary": "Chart-aware retrieval improves citation quality.",
                "excerpt": "The nearby text says citation quality improves after chart grounding.",
                "content": "The nearby text says citation quality improves after chart grounding.",
                "score": 0.88,
            },
            {
                "source": "paper.pdf",
                "page": 6,
                "file_id": "file-1",
                "title": "paper",
                "summary": "This is a distant paragraph that should be filtered out.",
                "excerpt": "This is a distant paragraph that should be filtered out.",
                "content": "This is a distant paragraph that should be filtered out.",
                "score": 0.83,
            },
        ],
    )

    assert augmented["asset_hits"] == 1
    assert len(augmented["sources"]) == 2
    source = augmented["sources"][0]
    assert source["asset_id"] == "asset-fig-3"
    assert source["is_primary"] is True
    assert source["thumbnail_url"].endswith(f"/api/kbs/{kb_id}/assets/asset-fig-3/content")
    assert source["summary"].startswith("结论：Fig. 3")
    assert source["visual_summary"].startswith("The figure shows chart grounding")
    assert source["interpretation"]["main_message"] == "Chart grounding increases citation quality."
    assert augmented["sources"][1]["page"] == 3
    assert "Table 3" not in augmented["context"]
