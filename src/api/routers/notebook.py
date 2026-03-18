# -*- coding: utf-8 -*-
"""
NotebookLM-style notebook router.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.orchestrator.events import build_done_event, build_error_event, build_init_event, sse_event
from src.services.notebook import get_notebook_manager

router = APIRouter()


class CreateNotebookRequest(BaseModel):
    name: str
    description: str = ""
    color: str = "#111827"
    icon: str = "book"
    default_kb_id: str | None = None
    auto_import_enabled: bool = False


class UpdateNotebookRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    default_kb_id: str | None = None
    auto_import_enabled: bool | None = None


class UpdateSourceRequest(BaseModel):
    title: str | None = None
    included: bool | None = None


class CreateChatSessionRequest(BaseModel):
    title: str | None = None


class ChatStreamRequest(BaseModel):
    session_id: str | None = None
    message: str
    source_ids: list[str] = Field(default_factory=list)


class GenerateStudioRequest(BaseModel):
    kind: Literal["summary", "study_guide", "faq", "mind_map"]
    source_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None


class CreateNoteRequest(BaseModel):
    title: str
    content: str = ""
    kind: Literal["manual", "saved_chat", "saved_research", "saved_studio"] = "manual"
    origin: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class UpdateNoteRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    kind: Literal["manual", "saved_chat", "saved_research", "saved_studio"] | None = None
    origin: str | None = None
    citations: list[dict[str, Any]] | None = None
    source_ids: list[str] | None = None
    tags: list[str] | None = None


class SaveFromSourcesRequest(BaseModel):
    title: str
    content: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    kb_id: str | None = None
    origin_type: Literal["research", "co_writer", "chat", "studio"] = "research"
    tags: list[str] = Field(default_factory=list)


def _require_notebook(notebook_id: str) -> None:
    if not get_notebook_manager().get_notebook(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook not found")


def _map_service_error(exc: ValueError) -> HTTPException:
    detail = str(exc) or "Invalid notebook request"
    if "not found" in detail.lower() or "不存在" in detail:
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=400, detail=detail)


@router.get("/notebooks")
async def list_notebooks():
    return {"success": True, "data": get_notebook_manager().list_notebooks()}


@router.get("/notebooks/stats/overview")
async def get_statistics():
    return {"success": True, "data": get_notebook_manager().get_statistics()}


@router.post("/notebooks")
async def create_notebook(req: CreateNotebookRequest):
    notebook = get_notebook_manager().create_notebook(
        name=req.name,
        description=req.description,
        color=req.color,
        icon=req.icon,
        default_kb_id=req.default_kb_id,
        auto_import_enabled=req.auto_import_enabled,
    )
    return {"success": True, "data": notebook}


@router.get("/notebooks/{notebook_id}")
async def get_notebook(notebook_id: str):
    notebook = get_notebook_manager().get_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"success": True, "data": notebook}


@router.put("/notebooks/{notebook_id}")
async def update_notebook(notebook_id: str, req: UpdateNotebookRequest):
    notebook = get_notebook_manager().update_notebook(notebook_id, **req.model_dump(exclude_none=True))
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"success": True, "data": notebook}


@router.delete("/notebooks/{notebook_id}")
async def delete_notebook(notebook_id: str):
    if not get_notebook_manager().delete_notebook(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"success": True, "data": True}


@router.get("/notebooks/{notebook_id}/workspace")
async def get_notebook_workspace(
    notebook_id: str,
    active_note_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    tag: str | None = Query(default=None),
):
    del active_note_id, search, tag
    payload = get_notebook_manager().build_workspace_view(notebook_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"success": True, "data": payload}


@router.get("/notebooks/{notebook_id}/sources")
async def list_sources(notebook_id: str):
    _require_notebook(notebook_id)
    return {"success": True, "data": get_notebook_manager().list_sources(notebook_id)}


@router.post("/notebooks/{notebook_id}/sources")
async def create_source(
    notebook_id: str,
    request: Request,
    kind: str | None = Form(default=None),
    title: str | None = Form(default=None),
    url: str | None = Form(default=None),
    text: str | None = Form(default=None),
    kb_id: str | None = Form(default=None),
    file_id: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
):
    payload: dict[str, Any]
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        payload = await request.json()
    else:
        payload = {
            "kind": kind,
            "title": title,
            "url": url,
            "text": text,
            "kb_id": kb_id,
            "file_id": file_id,
        }
        if file is not None:
            payload["file_name"] = file.filename
            payload["file_bytes"] = await file.read()
    if not payload.get("kind"):
        raise HTTPException(status_code=400, detail="Source kind is required")
    try:
        source = get_notebook_manager().create_source(notebook_id, **payload)
    except ValueError as exc:
        raise _map_service_error(exc) from exc
    return {"success": True, "data": source}


@router.get("/notebooks/{notebook_id}/sources/{source_id}")
async def get_source(notebook_id: str, source_id: str):
    _require_notebook(notebook_id)
    source = next(
        (row for row in get_notebook_manager().list_sources(notebook_id) if str(row.get("id")) == source_id),
        None,
    )
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"success": True, "data": source}


@router.put("/notebooks/{notebook_id}/sources/{source_id}")
async def update_source(notebook_id: str, source_id: str, req: UpdateSourceRequest):
    _require_notebook(notebook_id)
    source = get_notebook_manager().update_source(notebook_id, source_id, **req.model_dump(exclude_none=True))
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"success": True, "data": source}


@router.delete("/notebooks/{notebook_id}/sources/{source_id}")
async def delete_source(notebook_id: str, source_id: str):
    _require_notebook(notebook_id)
    if not get_notebook_manager().delete_source(notebook_id, source_id):
        raise HTTPException(status_code=404, detail="Source not found")
    return {"success": True, "data": True}


@router.get("/notebooks/{notebook_id}/chat/sessions")
async def list_chat_sessions(notebook_id: str):
    _require_notebook(notebook_id)
    return {"success": True, "data": get_notebook_manager().list_chat_sessions(notebook_id)}


@router.post("/notebooks/{notebook_id}/chat/sessions")
async def create_chat_session(notebook_id: str, req: CreateChatSessionRequest):
    try:
        session = get_notebook_manager().create_chat_session(notebook_id, title=req.title)
    except ValueError as exc:
        raise _map_service_error(exc) from exc
    return {"success": True, "data": session}


@router.get("/notebooks/{notebook_id}/chat/sessions/{session_id}")
async def get_chat_session(notebook_id: str, session_id: str):
    _require_notebook(notebook_id)
    session = get_notebook_manager().get_chat_session(notebook_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"success": True, "data": session}


@router.post("/notebooks/{notebook_id}/chat/stream")
async def stream_notebook_chat(notebook_id: str, req: ChatStreamRequest):
    _require_notebook(notebook_id)

    def generate():
        run_id = f"notebook-chat-{notebook_id}"
        trace_id = f"{run_id}:{req.session_id or 'new'}"
        yield f": {' ' * 2048}\n\n"
        yield sse_event(
            build_init_event(
                run_id=run_id,
                trace_id=trace_id,
                mode="notebook-chat",
                notebook_id=notebook_id,
                session_id=req.session_id,
            )
        )
        try:
            result = get_notebook_manager().chat_in_session(
                notebook_id=notebook_id,
                session_id=req.session_id,
                message=req.message,
                source_ids=req.source_ids or None,
            )
            assistant_message = result["assistant_message"]
            session = result["session"]
            for chunk in result["stream_chunks"]:
                if not chunk:
                    continue
                yield sse_event(
                    {
                        "type": "message_chunk",
                        "content": chunk,
                        "session_id": session["id"],
                        "message_id": assistant_message["id"],
                    }
                )
            yield sse_event(
                {
                    "type": "citations",
                    "data": assistant_message.get("citations", []),
                    "session_id": session["id"],
                    "message_id": assistant_message["id"],
                }
            )
            background_extension = str(assistant_message.get("background_extension") or "").strip()
            if background_extension:
                yield sse_event(
                    {
                        "type": "background_extension",
                        "content": background_extension,
                        "session_id": session["id"],
                        "message_id": assistant_message["id"],
                    }
                )
            yield sse_event(
                build_done_event(
                    run_id=run_id,
                    trace_id=trace_id,
                    output=assistant_message.get("content", ""),
                    notebook_id=notebook_id,
                    session_id=session["id"],
                    assistant_message=assistant_message,
                    session=session,
                )
            )
        except Exception as exc:
            yield sse_event(
                build_error_event(
                    str(exc),
                    step="notebook-chat",
                    retryable=False,
                    notebook_id=notebook_id,
                    session_id=req.session_id,
                )
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/notebooks/{notebook_id}/studio")
async def list_studio_outputs(notebook_id: str):
    _require_notebook(notebook_id)
    return {"success": True, "data": get_notebook_manager().list_studio_outputs(notebook_id)}


@router.post("/notebooks/{notebook_id}/studio")
async def generate_studio_output(notebook_id: str, req: GenerateStudioRequest):
    try:
        output = get_notebook_manager().generate_studio_output(
            notebook_id=notebook_id,
            kind=req.kind,
            source_ids=req.source_ids or None,
            session_id=req.session_id,
        )
    except ValueError as exc:
        raise _map_service_error(exc) from exc
    return {"success": True, "data": output}


@router.delete("/notebooks/{notebook_id}/studio/{output_id}")
async def delete_studio_output(notebook_id: str, output_id: str):
    _require_notebook(notebook_id)
    if not get_notebook_manager().delete_studio_output(notebook_id, output_id):
        raise HTTPException(status_code=404, detail="Studio output not found")
    return {"success": True, "data": True}


@router.post("/notebooks/{notebook_id}/studio/{output_id}/save-note")
async def save_studio_output_as_note(notebook_id: str, output_id: str):
    _require_notebook(notebook_id)
    note = get_notebook_manager().save_studio_output_as_note(notebook_id, output_id)
    if not note:
        raise HTTPException(status_code=404, detail="Studio output not found")
    return {"success": True, "data": note}


@router.get("/notebooks/{notebook_id}/notes")
async def list_notes(
    notebook_id: str,
    search: str | None = Query(default=None),
    tag: str | None = Query(default=None),
):
    _require_notebook(notebook_id)
    rows = get_notebook_manager().list_notes(notebook_id)
    if search:
        needle = search.lower().strip()
        rows = [
            row
            for row in rows
            if needle in str(row.get("title") or "").lower() or needle in str(row.get("preview") or "").lower()
        ]
    if tag:
        tag_lower = tag.lower().strip()
        rows = [
            row
            for row in rows
            if any(tag_lower in str(item).lower() for item in row.get("tags", []) or [])
        ]
    return {"success": True, "data": rows}


@router.post("/notebooks/{notebook_id}/notes")
async def create_note(notebook_id: str, req: CreateNoteRequest):
    try:
        note = get_notebook_manager().create_note(
            notebook_id=notebook_id,
            title=req.title,
            content=req.content,
            kind=req.kind,
            origin=req.origin,
            citations=req.citations,
            source_ids=req.source_ids,
            tags=req.tags,
        )
    except ValueError as exc:
        raise _map_service_error(exc) from exc
    return {"success": True, "data": note}


@router.get("/notebooks/{notebook_id}/notes/{note_id}")
async def get_note(notebook_id: str, note_id: str):
    _require_notebook(notebook_id)
    note = get_notebook_manager().get_note(notebook_id, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"success": True, "data": note}


@router.put("/notebooks/{notebook_id}/notes/{note_id}")
async def update_note(notebook_id: str, note_id: str, req: UpdateNoteRequest):
    _require_notebook(notebook_id)
    note = get_notebook_manager().update_note(notebook_id, note_id, **req.model_dump(exclude_none=True))
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"success": True, "data": note}


@router.delete("/notebooks/{notebook_id}/notes/{note_id}")
async def delete_note(notebook_id: str, note_id: str):
    _require_notebook(notebook_id)
    if not get_notebook_manager().delete_note(notebook_id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return {"success": True, "data": True}


@router.post("/notebooks/{notebook_id}/notes/from-sources")
async def create_note_from_sources(notebook_id: str, req: SaveFromSourcesRequest):
    _require_notebook(notebook_id)
    note = get_notebook_manager().create_note_from_sources(
        notebook_id=notebook_id,
        title=req.title,
        content=req.content,
        sources=req.sources,
        kb_id=req.kb_id,
        origin_type=req.origin_type,
        tags=req.tags,
    )
    return {"success": True, "data": note}
