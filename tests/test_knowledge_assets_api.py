from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers import knowledge as knowledge_router
from src.knowledge.assets import ChartInterpretation
from src.knowledge.kb_manager import KnowledgeBaseManager


def _build_client(kb_manager: KnowledgeBaseManager, data_dir: Path) -> TestClient:
    app = FastAPI()
    app.include_router(knowledge_router.router, prefix="/api")
    knowledge_router.DATA_DIR = data_dir
    knowledge_router._kb_manager = kb_manager
    knowledge_router.get_kb_manager = lambda: kb_manager
    return TestClient(app)


def test_asset_list_content_and_interpret_endpoint(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    kb_manager = KnowledgeBaseManager(data_dir / "knowledge_bases")
    kb = kb_manager.create_kb("assets-kb")
    kb_id = str(kb["id"])

    image_path = kb_manager.get_assets_path(kb_id) / "fig3.png"
    image_path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    kb_manager.add_assets(
        kb_id,
        [
            {
                "id": "asset-1",
                "kind": "figure",
                "page": 3,
                "bbox": [10.0, 20.0, 100.0, 200.0],
                "caption": "Figure 3. Chart-aware retrieval improves citation quality.",
                "ref_label": "Fig. 3",
                "image_path": str(image_path),
                "source_file": "demo.pdf",
                "file_id": "file-1",
                "nearby_text": "The text around the figure describes stronger citation quality.",
                "visual_summary": "This figure summarizes how chart grounding improves citation quality.",
            }
        ],
    )

    monkeypatch.setattr(
        knowledge_router,
        "interpret_asset_with_llm",
        lambda asset: ChartInterpretation(
            chart_type="figure",
            main_message="The figure shows that citation quality improves after chart grounding.",
            entities=["chart grounding"],
            metrics=["citation quality"],
            trend="Performance increases after the multimodal step.",
            evidence_text="The nearby text explicitly describes stronger citation quality.",
            confidence=0.86,
        ),
    )

    client = _build_client(kb_manager, data_dir)

    list_resp = client.get(f"/api/kbs/{kb_id}/assets")
    assert list_resp.status_code == 200
    rows = list_resp.json()["data"]
    assert len(rows) == 1
    assert rows[0]["ref_label"] == "Fig. 3"
    assert rows[0]["title"] == "demo"
    assert rows[0]["visual_summary"].startswith("This figure summarizes")
    assert rows[0]["summary"].startswith("结论：Fig. 3")
    assert "图注：" in rows[0]["excerpt"]
    assert rows[0]["thumbnail_url"].endswith("/api/kbs/%s/assets/asset-1/content" % kb_id)

    content_resp = client.get(f"/api/kbs/{kb_id}/assets/asset-1/content")
    assert content_resp.status_code == 200
    assert content_resp.headers["content-type"].startswith("image/png")

    interpret_resp = client.post(f"/api/kbs/{kb_id}/assets/asset-1/interpret")
    assert interpret_resp.status_code == 200
    data = interpret_resp.json()["data"]
    assert data["interpretation"]["main_message"].startswith("The figure shows")
    assert data["visual_summary"].startswith("This figure summarizes")
    assert data["summary"].startswith("结论：Fig. 3")
    stored_asset = kb_manager.get_asset(kb_id, "asset-1")
    assert stored_asset is not None
    assert stored_asset["interpretation"]["confidence"] == 0.86
    assert stored_asset["visual_summary"].startswith("This figure summarizes")
