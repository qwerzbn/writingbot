from __future__ import annotations

import uuid
from pathlib import Path

from src.services.notebook import NotebookManager


def _prepare_kb_file(manager: NotebookManager, tmp_path: Path) -> tuple[str, str]:
    kb_manager = manager._get_kb_manager()
    kb = kb_manager.create_kb("kb-snapshot")
    kb_id = str(kb["id"])
    file_id = str(uuid.uuid4())
    file_path = tmp_path / "knowledge-note.txt"
    file_path.write_text("Graph retrieval links distant concepts for notebook answers.", encoding="utf-8")
    kb_manager.add_file(
        kb_id,
        {
            "id": file_id,
            "name": "knowledge-note.txt",
            "path": str(file_path),
            "size": file_path.stat().st_size,
            "uploaded_at": "2026-03-18T12:00:00",
            "blocks": 1,
            "chunks": 1,
        },
    )
    return kb_id, file_id


def test_create_all_source_kinds_and_workspace_view(tmp_path, monkeypatch):
    manager = NotebookManager(data_dir=tmp_path / "data")
    notebook = manager.create_notebook(name="NotebookLM")
    notebook_id = notebook["id"]
    kb_id, file_id = _prepare_kb_file(manager, tmp_path)

    def fake_materialize_pdf(
        current_notebook_id: str,
        source_id: str,
        filename: str,
        file_bytes: bytes | None = None,
        source_path: Path | None = None,
    ):
        asset_path = manager._assets_dir(current_notebook_id, ensure=True) / f"{source_id}.pdf"
        asset_path.write_bytes(file_bytes or source_path.read_bytes() if source_path else b"%PDF-1.4")
        chunks = [
            {
                "id": f"{source_id}:0",
                "source_id": source_id,
                "content": "PDF chunk about multimodal notebooks and grounded answers.",
                "page": 1,
                "chunk_idx": 0,
                "tokens": ["pdf", "chunk", "multimodal", "notebooks", "grounded", "answers"],
                "metadata": {"page": 1, "source": filename},
            }
        ]
        return asset_path, [{"content": chunks[0]["content"]}], chunks, chunks[0]["content"]

    monkeypatch.setattr(manager, "_materialize_pdf", fake_materialize_pdf)
    monkeypatch.setattr(
        manager,
        "_extract_url_content",
        lambda url: ("NotebookLM Article", "URL content explains citations and source-grounded chat."),
    )

    pdf_source = manager.create_source(
        notebook_id,
        kind="pdf",
        title="Research PDF",
        file_name="paper.pdf",
        file_bytes=b"%PDF-1.4",
    )
    url_source = manager.create_source(notebook_id, kind="url", url="https://example.com/notebook")
    text_source = manager.create_source(
        notebook_id,
        kind="text",
        title="Meeting note",
        text="Pasted text captures requirements for study guide generation.",
    )
    kb_source = manager.create_source(notebook_id, kind="kb_ref", kb_id=kb_id, file_id=file_id)

    sources = manager.list_sources(notebook_id)
    assert {source["kind"] for source in sources} == {"pdf", "url", "text", "kb_ref"}
    assert pdf_source["metadata"]["file_name"] == "paper.pdf"
    assert url_source["metadata"]["url"] == "https://example.com/notebook"
    assert text_source["metadata"]["source"] == "pasted_text"
    assert kb_source["metadata"]["kb_id"] == kb_id
    for source in sources:
        assert manager._source_chunks_path(notebook_id, source["id"]).exists()
        assert manager._source_embedding_path(notebook_id, source["id"]).exists()

    workspace = manager.build_workspace_view(notebook_id)
    assert workspace is not None
    assert workspace["notebook"]["source_count"] == 4
    assert len(workspace["sources"]) == 4
    assert len(workspace["ui_defaults"]["selected_source_ids"]) == 4


def test_source_scoped_chat_studio_and_note_flow(tmp_path):
    manager = NotebookManager(data_dir=tmp_path / "data")
    notebook = manager.create_notebook(name="Study notebook")
    notebook_id = notebook["id"]

    source_a = manager.create_source(
        notebook_id,
        kind="text",
        title="Transformer note",
        text="Transformer architecture improves long-context retrieval and source-grounded answers.",
    )
    source_b = manager.create_source(
        notebook_id,
        kind="text",
        title="Biology note",
        text="Protein folding experiments focus on molecular simulation and laboratory validation.",
    )

    chat = manager.chat_in_session(
        notebook_id=notebook_id,
        session_id=None,
        message="Transformer 为什么适合长上下文检索？",
        source_ids=[source_a["id"]],
    )
    assistant = chat["assistant_message"]
    assert chat["session"]["id"]
    assert assistant["content"]
    assert assistant["citations"]
    assert {citation["source_id"] for citation in assistant["citations"]} == {source_a["id"]}

    retrieved = manager.retrieve_chunks(
        notebook_id,
        query="protein folding",
        source_ids=[source_b["id"]],
        limit=4,
    )
    assert retrieved
    assert {chunk.source_id for chunk in retrieved} == {source_b["id"]}

    studio = manager.generate_studio_output(
        notebook_id=notebook_id,
        kind="mind_map",
        source_ids=[source_a["id"]],
        session_id=chat["session"]["id"],
    )
    assert studio["kind"] == "mind_map"
    assert studio["tree"] is not None

    studio_note = manager.save_studio_output_as_note(notebook_id, studio["id"])
    assert studio_note is not None
    assert studio_note["kind"] == "saved_studio"

    saved_chat_note = manager.create_note_from_sources(
        notebook_id=notebook_id,
        title="Chat note",
        content=assistant["content"],
        sources=assistant["citations"],
        origin_type="chat",
        tags=["chat"],
    )
    assert saved_chat_note["kind"] == "saved_chat"
    assert saved_chat_note["source_ids"] == [source_a["id"]]

    notes = manager.list_notes(notebook_id)
    assert len(notes) == 2
    assert {note["kind"] for note in notes} == {"saved_chat", "saved_studio"}

    workspace = manager.build_workspace_view(notebook_id)
    assert workspace is not None
    assert len(workspace["recent_sessions"]) == 1
    assert len(workspace["studio_outputs"]) == 1
    assert len(workspace["notes_summary"]) == 2
