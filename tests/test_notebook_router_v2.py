from __future__ import annotations

import uuid
from pathlib import Path
import json

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


def _iter_sse_data_chunks(response):
    for chunk in response.iter_text():
        for line in chunk.splitlines():
            if not line.startswith("data: "):
                continue
            yield line[6:].strip()


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
    assert workspace["ui_defaults"]["active_note_id"] is None

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
    active_note = notes[0]["id"]

    filtered_workspace_resp = client.get(
        f"/api/notebooks/{notebook_id}/workspace",
        params={"search": "research", "tag": "research", "active_note_id": active_note},
    )
    assert filtered_workspace_resp.status_code == 200
    filtered_workspace = filtered_workspace_resp.json()["data"]
    assert len(filtered_workspace["notes_summary"]) == 1
    assert filtered_workspace["ui_defaults"]["active_note_id"] == active_note

    note_detail_resp = client.get(f"/api/notebooks/{notebook_id}/notes/{save_studio_note_resp.json()['data']['id']}")
    assert note_detail_resp.status_code == 200

    graph_view_resp = client.get(f"/api/notebooks/{notebook_id}/graph-view")
    assert graph_view_resp.status_code == 200
    graph_view = graph_view_resp.json()["data"]
    assert graph_view["notebook_id"] == notebook_id
    assert "nodes" in graph_view and "edges" in graph_view

    graph_alias_resp = client.get(f"/api/notebooks/{notebook_id}/graph")
    assert graph_alias_resp.status_code == 200

    insights_resp = client.get(f"/api/notebooks/{notebook_id}/insights")
    assert insights_resp.status_code == 200
    assert "coverage" in insights_resp.json()["data"]

    related_resp = client.get(
        f"/api/notebooks/{notebook_id}/notes/{save_studio_note_resp.json()['data']['id']}/related"
    )
    assert related_resp.status_code == 200
    assert isinstance(related_resp.json()["data"], list)

    meta_resp = client.get(
        f"/api/notebooks/{notebook_id}/notes/{save_studio_note_resp.json()['data']['id']}/meta"
    )
    assert meta_resp.status_code == 200
    assert "summary" in meta_resp.json()["data"]

    update_meta_resp = client.put(
        f"/api/notebooks/{notebook_id}/notes/{save_studio_note_resp.json()['data']['id']}/meta",
        json={"summary": "updated summary"},
    )
    assert update_meta_resp.status_code == 200
    assert update_meta_resp.json()["data"]["summary"] == "updated summary"

    extract_resp = client.post(
        f"/api/notebooks/{notebook_id}/notes/{save_studio_note_resp.json()['data']['id']}/extract"
    )
    assert extract_resp.status_code == 200
    assert extract_resp.json()["data"]["job_id"]
    assert "meta" in extract_resp.json()["data"]

    migrate_resp = client.post(f"/api/notebooks/{notebook_id}/migrate-records")
    assert migrate_resp.status_code == 200
    assert "migrated_count" in migrate_resp.json()["data"]

    import_resp = client.post(
        f"/api/notebooks/{notebook_id}/imports/kb",
        json={"kb_id": kb_id, "trigger_mode": "manual", "run_async": False},
    )
    assert import_resp.status_code == 200
    assert import_resp.json()["data"]["status"] in ("done", "partial_failed")

    with client.stream("GET", f"/api/notebooks/{notebook_id}/events?single_pass=1") as events_resp:
        assert events_resp.status_code == 200
        chunks: list[str] = []
        for chunk in events_resp.iter_text():
            chunks.append(chunk)
            if '"type": "job_patch"' in chunk or ": ping" in chunk:
                break
        payload = "".join(chunks)
        assert '"type": "job_patch"' in payload or ": ping" in payload

    delete_source_resp = client.delete(f"/api/notebooks/{notebook_id}/sources/{source['id']}")
    assert delete_source_resp.status_code == 200


def test_update_note_conflict_returns_latest(tmp_path, monkeypatch):
    manager = NotebookManager(data_dir=tmp_path / "data")
    monkeypatch.setattr(notebook_router, "get_notebook_manager", lambda: manager)

    app = FastAPI()
    app.include_router(notebook_router.router, prefix="/api")
    client = TestClient(app)

    notebook_id = client.post("/api/notebooks", json={"name": "conflict"}).json()["data"]["id"]
    created_note = client.post(
        f"/api/notebooks/{notebook_id}/notes",
        json={"title": "v1", "content": "body"},
    ).json()["data"]

    ok_resp = client.put(
        f"/api/notebooks/{notebook_id}/notes/{created_note['id']}",
        json={"title": "v2", "expected_updated_at": created_note["updated_at"]},
    )
    assert ok_resp.status_code == 200
    latest = ok_resp.json()["data"]

    conflict_resp = client.put(
        f"/api/notebooks/{notebook_id}/notes/{created_note['id']}",
        json={"title": "stale write", "expected_updated_at": created_note["updated_at"]},
    )
    assert conflict_resp.status_code == 409
    detail = conflict_resp.json()["detail"]
    assert detail["latest"]["id"] == created_note["id"]
    assert detail["latest"]["title"] == latest["title"]


def test_notebook_events_support_cursor_resume(tmp_path, monkeypatch):
    manager = NotebookManager(data_dir=tmp_path / "data")
    monkeypatch.setattr(notebook_router, "get_notebook_manager", lambda: manager)

    app = FastAPI()
    app.include_router(notebook_router.router, prefix="/api")
    client = TestClient(app)

    notebook_id = client.post("/api/notebooks", json={"name": "cursor"}).json()["data"]["id"]
    notebook_router._append_event(notebook_id, {"type": "job_patch", "status": "pending"})

    first_cursor = 0
    with client.stream("GET", f"/api/notebooks/{notebook_id}/events?cursor=0&single_pass=1") as resp:
        assert resp.status_code == 200
        for raw in _iter_sse_data_chunks(resp):
            data = json.loads(raw)
            first_cursor = int(data["cursor"])
            break
    assert first_cursor > 0

    notebook_router._append_event(notebook_id, {"type": "job_patch", "status": "running"})
    with client.stream("GET", f"/api/notebooks/{notebook_id}/events?cursor={first_cursor}&single_pass=1") as resp:
        assert resp.status_code == 200
        for raw in _iter_sse_data_chunks(resp):
            data = json.loads(raw)
            assert int(data["cursor"]) > first_cursor
            break


def test_notebook_events_support_last_event_id_resume(tmp_path, monkeypatch):
    manager = NotebookManager(data_dir=tmp_path / "data")
    monkeypatch.setattr(notebook_router, "get_notebook_manager", lambda: manager)

    app = FastAPI()
    app.include_router(notebook_router.router, prefix="/api")
    client = TestClient(app)

    notebook_id = client.post("/api/notebooks", json={"name": "last-event-id"}).json()["data"]["id"]
    notebook_router._append_event(notebook_id, {"type": "job_patch", "status": "pending"})

    first_cursor = 0
    with client.stream("GET", f"/api/notebooks/{notebook_id}/events?cursor=0&single_pass=1") as resp:
        assert resp.status_code == 200
        for raw in _iter_sse_data_chunks(resp):
            data = json.loads(raw)
            first_cursor = int(data["cursor"])
            break
    assert first_cursor > 0

    notebook_router._append_event(notebook_id, {"type": "job_patch", "status": "running"})
    with client.stream(
        "GET",
        f"/api/notebooks/{notebook_id}/events?single_pass=1",
        headers={"Last-Event-ID": str(first_cursor)},
    ) as resp:
        assert resp.status_code == 200
        for raw in _iter_sse_data_chunks(resp):
            data = json.loads(raw)
            assert int(data["cursor"]) > first_cursor
            break
