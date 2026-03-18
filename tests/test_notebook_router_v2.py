from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routers.notebook as notebook_router
from src.services.notebook import NotebookManager


def _prepare_kb_file(manager: NotebookManager, tmp_path: Path) -> tuple[str, str]:
    kb_manager = manager._get_kb_manager()
    kb = kb_manager.create_kb("router-kb")
    kb_id = str(kb["id"])
    file_id = str(uuid.uuid4())
    file_path = tmp_path / "router-knowledge.txt"
    file_path.write_text("Knowledge base snapshots should stay local to the notebook.", encoding="utf-8")
    kb_manager.add_file(
        kb_id,
        {
            "id": file_id,
            "name": "router-knowledge.txt",
            "path": str(file_path),
            "size": file_path.stat().st_size,
            "uploaded_at": "2026-03-18T13:00:00",
            "blocks": 1,
            "chunks": 1,
        },
    )
    return kb_id, file_id


def test_notebook_router_end_to_end(tmp_path, monkeypatch):
    manager = NotebookManager(data_dir=tmp_path / "data")
    kb_id, file_id = _prepare_kb_file(manager, tmp_path)

    monkeypatch.setattr(
        manager,
        "_extract_url_content",
        lambda url: ("Router article", "This URL source explains why citations improve trust."),
    )
    monkeypatch.setattr(notebook_router, "get_notebook_manager", lambda: manager)

    app = FastAPI()
    app.include_router(notebook_router.router, prefix="/api")
    client = TestClient(app)

    create_resp = client.post("/api/notebooks", json={"name": "router-nb"})
    assert create_resp.status_code == 200
    notebook = create_resp.json()["data"]
    notebook_id = notebook["id"]

    source_resp = client.post(
        f"/api/notebooks/{notebook_id}/sources",
        data={"kind": "text", "title": "Source A", "text": "Transformer retrieval depends on grounded evidence."},
    )
    assert source_resp.status_code == 200
    source = source_resp.json()["data"]

    kb_source_resp = client.post(
        f"/api/notebooks/{notebook_id}/sources",
        data={"kind": "kb_ref", "kb_id": kb_id, "file_id": file_id},
    )
    assert kb_source_resp.status_code == 200

    update_source_resp = client.put(
        f"/api/notebooks/{notebook_id}/sources/{source['id']}",
        json={"included": False},
    )
    assert update_source_resp.status_code == 200
    assert update_source_resp.json()["data"]["included"] is False

    workspace_resp = client.get(f"/api/notebooks/{notebook_id}/workspace")
    assert workspace_resp.status_code == 200
    workspace = workspace_resp.json()["data"]
    assert workspace["notebook"]["id"] == notebook_id
    assert len(workspace["sources"]) == 2
    assert workspace["ui_defaults"]["selected_source_ids"] == [kb_source_resp.json()["data"]["id"]]

    chat_resp = client.post(
        f"/api/notebooks/{notebook_id}/chat/stream",
        json={
            "message": "为什么 grounded evidence 重要？",
            "source_ids": [kb_source_resp.json()["data"]["id"]],
        },
    )
    assert chat_resp.status_code == 200
    assert '"type": "message_chunk"' in chat_resp.text
    assert '"type": "citations"' in chat_resp.text
    assert '"type": "done"' in chat_resp.text

    sessions_resp = client.get(f"/api/notebooks/{notebook_id}/chat/sessions")
    assert sessions_resp.status_code == 200
    sessions = sessions_resp.json()["data"]
    assert len(sessions) == 1

    session_detail_resp = client.get(f"/api/notebooks/{notebook_id}/chat/sessions/{sessions[0]['id']}")
    assert session_detail_resp.status_code == 200
    session_detail = session_detail_resp.json()["data"]
    assert len(session_detail["messages"]) == 2

    studio_resp = client.post(
        f"/api/notebooks/{notebook_id}/studio",
        json={"kind": "summary", "source_ids": [kb_source_resp.json()["data"]["id"]]},
    )
    assert studio_resp.status_code == 200
    studio = studio_resp.json()["data"]
    assert studio["kind"] == "summary"

    save_studio_note_resp = client.post(
        f"/api/notebooks/{notebook_id}/studio/{studio['id']}/save-note"
    )
    assert save_studio_note_resp.status_code == 200
    assert save_studio_note_resp.json()["data"]["kind"] == "saved_studio"

    save_from_sources_resp = client.post(
        f"/api/notebooks/{notebook_id}/notes/from-sources",
        json={
            "title": "Saved from research",
            "content": "Grounded answers build trust.",
            "sources": [
                {
                    "source_id": kb_source_resp.json()["data"]["id"],
                    "source_title": "router-knowledge.txt",
                    "locator": "text",
                    "excerpt": "Knowledge base snapshots should stay local to the notebook.",
                }
            ],
            "origin_type": "research",
            "tags": ["research"],
        },
    )
    assert save_from_sources_resp.status_code == 200
    assert save_from_sources_resp.json()["data"]["kind"] == "saved_research"

    notes_resp = client.get(f"/api/notebooks/{notebook_id}/notes")
    assert notes_resp.status_code == 200
    notes = notes_resp.json()["data"]
    assert len(notes) == 2

    note_detail_resp = client.get(f"/api/notebooks/{notebook_id}/notes/{save_studio_note_resp.json()['data']['id']}")
    assert note_detail_resp.status_code == 200

    delete_source_resp = client.delete(f"/api/notebooks/{notebook_id}/sources/{source['id']}")
    assert delete_source_resp.status_code == 200
