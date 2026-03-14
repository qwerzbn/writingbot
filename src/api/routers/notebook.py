# -*- coding: utf-8 -*-
"""
Notebook API Router
====================

CRUD for notebooks, legacy records, and **notes**.
AI-powered note writing assistant with SSE streaming.
"""

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.services.notebook import get_notebook_manager

router = APIRouter()


# ------------------------------------------------------------------ #
#  Request / Response Models                                          #
# ------------------------------------------------------------------ #

class CreateNotebookRequest(BaseModel):
    name: str
    description: str = ""
    color: str = "#3B82F6"
    icon: str = "book"


class UpdateNotebookRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class AddRecordRequest(BaseModel):
    notebook_ids: list[str]
    record_type: Literal["research", "co_writer"]
    title: str
    user_query: str
    output: str
    metadata: dict = Field(default_factory=dict)
    kb_name: str | None = None


class NoteSource(BaseModel):
    type: Literal["manual", "knowledge_base", "research", "co_writer"] = "manual"
    file_name: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    original_quote: str | None = None
    evidence_links: list[dict] | None = None
    citation_count: int | None = None
    last_used_at: str | None = None


class CreateNoteRequest(BaseModel):
    title: str = Field(max_length=200)
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    source: NoteSource = Field(default_factory=NoteSource)


class UpdateNoteRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content: str | None = None
    tags: list[str] | None = None
    source: NoteSource | None = None
    expected_updated_at: str | None = None  # optimistic lock


class UpdateNoteMetaRequest(BaseModel):
    summary: str | None = None
    suggested_tags: list[str] | None = None
    related_notes: list[dict] | None = None


# ================================================================== #
#  Notebook endpoints (original)                                      #
# ================================================================== #

@router.get("/notebooks")
async def list_notebooks():
    return {"success": True, "data": get_notebook_manager().list_notebooks()}


@router.get("/notebooks/stats/overview")
async def get_statistics():
    return {"success": True, "data": get_notebook_manager().get_statistics()}


@router.post("/notebooks")
async def create_notebook(req: CreateNotebookRequest):
    nb = get_notebook_manager().create_notebook(
        name=req.name, description=req.description, color=req.color, icon=req.icon
    )
    return {"success": True, "data": nb}


@router.post("/notebooks/records")
async def add_record(req: AddRecordRequest):
    result = get_notebook_manager().add_record(
        notebook_ids=req.notebook_ids,
        record_type=req.record_type,
        title=req.title,
        user_query=req.user_query,
        output=req.output,
        metadata=req.metadata,
        kb_name=req.kb_name,
    )
    return {"success": True, "data": result}


@router.get("/notebooks/{notebook_id}")
async def get_notebook(notebook_id: str):
    nb = get_notebook_manager().get_notebook(notebook_id)
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"success": True, "data": nb}


@router.put("/notebooks/{notebook_id}")
async def update_notebook(notebook_id: str, req: UpdateNotebookRequest):
    nb = get_notebook_manager().update_notebook(
        notebook_id, name=req.name, description=req.description, color=req.color, icon=req.icon
    )
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"success": True, "data": nb}


@router.delete("/notebooks/{notebook_id}")
async def delete_notebook(notebook_id: str):
    if not get_notebook_manager().delete_notebook(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"success": True}


@router.delete("/notebooks/{notebook_id}/records/{record_id}")
async def remove_record(notebook_id: str, record_id: str):
    if not get_notebook_manager().remove_record(notebook_id, record_id):
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True}


# ================================================================== #
#  Note endpoints (new)                                                #
# ================================================================== #

@router.get("/notebooks/{notebook_id}/notes")
async def list_notes(
    notebook_id: str,
    search: str | None = Query(default=None, description="Search in title and content"),
    tag: str | None = Query(default=None, description="Filter by tag"),
):
    """List notes in a notebook with optional search and tag filter."""
    mgr = get_notebook_manager()
    if not mgr.get_notebook(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook not found")
    notes = mgr.list_notes(notebook_id, search=search, tag=tag)
    return {"success": True, "data": notes}


@router.post("/notebooks/{notebook_id}/notes")
async def create_note(notebook_id: str, req: CreateNoteRequest):
    """Create a new note in a notebook."""
    note = get_notebook_manager().create_note(
        notebook_id=notebook_id,
        title=req.title,
        content=req.content,
        tags=req.tags,
        source=req.source.model_dump(exclude_none=True),
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"success": True, "data": note}


@router.get("/notebooks/{notebook_id}/notes/{note_id}")
async def get_note(notebook_id: str, note_id: str):
    """Get a single note with AI metadata if available."""
    note = get_notebook_manager().get_note(notebook_id, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"success": True, "data": note}


@router.put("/notebooks/{notebook_id}/notes/{note_id}")
async def update_note(notebook_id: str, note_id: str, req: UpdateNoteRequest):
    """Update a note. Supports optimistic locking via expected_updated_at.

    Returns 409 if the note was modified since the expected timestamp.
    """
    kwargs: dict = {}
    if req.title is not None:
        kwargs["title"] = req.title
    if req.content is not None:
        kwargs["content"] = req.content
    if req.tags is not None:
        kwargs["tags"] = req.tags
    if req.source is not None:
        kwargs["source"] = req.source.model_dump(exclude_none=True)

    result = get_notebook_manager().update_note(
        notebook_id,
        note_id,
        expected_updated_at=req.expected_updated_at,
        **kwargs,
    )

    if result == "not_found":
        raise HTTPException(status_code=404, detail="Note not found")
    if result == "conflict":
        # Return the latest version so the frontend can resolve
        latest = get_notebook_manager().get_note(notebook_id, note_id)
        raise HTTPException(
            status_code=409,
            detail={"message": "Note was modified concurrently", "latest": latest},
        )
    return {"success": True, "data": result}


@router.delete("/notebooks/{notebook_id}/notes/{note_id}")
async def delete_note(notebook_id: str, note_id: str):
    """Delete a note and its AI metadata."""
    if not get_notebook_manager().delete_note(notebook_id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return {"success": True}


@router.get("/notebooks/{notebook_id}/notes/{note_id}/meta")
async def get_note_meta(notebook_id: str, note_id: str):
    """Get AI-generated metadata for a note (summary, suggested tags)."""
    meta = get_notebook_manager().get_note_meta(notebook_id, note_id)
    return {"success": True, "data": meta}


@router.put("/notebooks/{notebook_id}/notes/{note_id}/meta")
async def update_note_meta(notebook_id: str, note_id: str, req: UpdateNoteMetaRequest):
    """Update AI-generated metadata for a note."""
    payload = req.model_dump(exclude_none=True)
    meta = get_notebook_manager().update_note_meta(
        notebook_id=notebook_id,
        note_id=note_id,
        **payload,
    )
    if meta is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"success": True, "data": meta}


@router.get("/notebooks/{notebook_id}/notes/{note_id}/related")
async def list_related_notes(
    notebook_id: str,
    note_id: str,
    limit: int = Query(default=5, ge=1, le=20),
    include_all: bool = Query(default=False, description="Search across all notebooks"),
    min_score: float = Query(default=0.0, ge=0.0, le=20.0),
):
    """Recommend related notes, optionally across notebooks."""
    mgr = get_notebook_manager()
    if not mgr.get_note(notebook_id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    related = mgr.list_related_notes(
        notebook_id,
        note_id,
        limit=limit,
        include_all_notebooks=include_all,
        min_score=min_score,
    )
    return {"success": True, "data": related}

class AIAssistantRequest(BaseModel):
    action: Literal["polish", "continue", "summarize", "suggest_tags", "custom"]
    content: str
    title: str = ""
    instruction: str = ""


@router.post("/notebooks/ai/stream")
async def stream_ai_assistant(req: AIAssistantRequest):
    """Stream AI writing assistant response."""
    from src.services.note_ai import stream_note_ai

    def event_generator():
        try:
            for chunk in stream_note_ai(
                action=req.action,
                content=req.content,
                title=req.title,
                instruction=req.instruction,
            ):
                if chunk:
                    # SSE format: data: {"chunk": "..."}
                    data_str = json.dumps({"chunk": chunk}, ensure_ascii=False)
                    yield f"data: {data_str}\n\n"
        except Exception as e:
            err_str = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {err_str}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
