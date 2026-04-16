# -*- coding: utf-8 -*-
"""
NotebookLM-style notebook router.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.orchestrator.events import build_done_event, build_error_event, build_init_event, sse_event
from src.services.notebook import NotebookConflictError, get_notebook_manager

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
    expected_updated_at: str | None = None


class SaveFromSourcesRequest(BaseModel):
    title: str
    content: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    kb_id: str | None = None
    origin_type: Literal["research", "co_writer", "chat", "studio"] = "research"
    tags: list[str] = Field(default_factory=list)


class ImportFromKbRequest(BaseModel):
    kb_id: str
    trigger_mode: str = "manual"
    run_async: bool = True


class UpdateNoteMetaRequest(BaseModel):
    summary: str | None = None
    suggested_tags: list[str] | None = None
    related_notes: list[dict[str, Any]] | None = None
    paper_card: dict[str, Any] | None = None
    source_spans: list[dict[str, Any]] | None = None
    extraction_status: str | None = None


@dataclass
class NotebookJobState:
    id: str
    notebook_id: str
    job_type: str
    status: str
    progress: float
    processed: int
    total: int
    message: str
    note_ids: list[str]
    trigger_mode: str
    kb_id: str | None
    updated_at: str


_RUNTIME_LOCK = threading.RLock()
_NOTEBOOK_JOBS: dict[str, dict[str, NotebookJobState]] = {}
_NOTEBOOK_EVENTS: dict[str, list[dict[str, Any]]] = {}
_NOTEBOOK_EVENT_CURSOR: dict[str, int] = {}
_NOTE_META: dict[str, dict[str, dict[str, Any]]] = {}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _clamp_progress(value: float) -> float:
    return max(0.0, min(1.0, round(float(value), 4)))


def _job_payload(job: NotebookJobState) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "processed": job.processed,
        "total": job.total,
        "kb_id": job.kb_id,
        "trigger_mode": job.trigger_mode,
        "note_ids": list(job.note_ids),
        "updated_at": job.updated_at,
        "message": job.message,
    }


def _append_event(notebook_id: str, payload: dict[str, Any]) -> None:
    with _RUNTIME_LOCK:
        cursor = _NOTEBOOK_EVENT_CURSOR.get(notebook_id, 0) + 1
        _NOTEBOOK_EVENT_CURSOR[notebook_id] = cursor
        event = {
            **payload,
            "notebook_id": notebook_id,
            "timestamp": payload.get("timestamp") or _now_iso(),
            "cursor": cursor,
        }
        rows = _NOTEBOOK_EVENTS.setdefault(notebook_id, [])
        rows.append(event)
        if len(rows) > 300:
            del rows[: len(rows) - 300]


def _sse_event_with_cursor(event: dict[str, Any]) -> str:
    cursor = event.get("cursor")
    if cursor is None:
        return sse_event(event)
    return f"id: {int(cursor)}\n{sse_event(event)}"


def _create_job(
    notebook_id: str,
    job_type: str,
    total: int,
    trigger_mode: str,
    kb_id: str | None = None,
    message: str = "",
) -> NotebookJobState:
    now = _now_iso()
    job = NotebookJobState(
        id=str(uuid.uuid4()),
        notebook_id=notebook_id,
        job_type=job_type,
        status="pending",
        progress=0.0,
        processed=0,
        total=max(0, int(total)),
        message=message,
        note_ids=[],
        trigger_mode=trigger_mode,
        kb_id=kb_id,
        updated_at=now,
    )
    with _RUNTIME_LOCK:
        _NOTEBOOK_JOBS.setdefault(notebook_id, {})[job.id] = job
    _append_event(
        notebook_id,
        {
            "type": "job_patch",
            "job_id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "progress": job.progress,
            "processed": job.processed,
            "total": job.total,
            "message": job.message,
        },
    )
    return job


def _update_job(job: NotebookJobState, **patch: Any) -> NotebookJobState:
    now = _now_iso()
    with _RUNTIME_LOCK:
        current = _NOTEBOOK_JOBS.get(job.notebook_id, {}).get(job.id)
        if not current:
            return job
        for key, value in patch.items():
            if value is not None and hasattr(current, key):
                if key == "progress":
                    setattr(current, key, _clamp_progress(value))
                elif key == "note_ids":
                    setattr(current, key, list(value))
                else:
                    setattr(current, key, value)
        current.updated_at = now
        snapshot = current
    _append_event(
        job.notebook_id,
        {
            "type": "job_patch",
            "job_id": snapshot.id,
            "job_type": snapshot.job_type,
            "status": snapshot.status,
            "progress": snapshot.progress,
            "processed": snapshot.processed,
            "total": snapshot.total,
            "message": snapshot.message,
            "affected_note_ids": list(snapshot.note_ids),
        },
    )
    return snapshot


def _extract_keywords(text: str, limit: int = 6) -> list[str]:
    tokens: list[str] = []
    chunk = []
    for ch in (text or ""):
        if ch.isalnum() or ch == "_" or ("\u4e00" <= ch <= "\u9fff"):
            chunk.append(ch.lower())
        else:
            if chunk:
                tokens.append("".join(chunk))
                chunk = []
    if chunk:
        tokens.append("".join(chunk))
    stop = {
        "the",
        "and",
        "with",
        "for",
        "that",
        "this",
        "from",
        "into",
        "have",
        "will",
        "about",
        "note",
        "saved",
        "manual",
        "chat",
        "studio",
        "research",
        "source",
        "content",
        "title",
    }
    counts: Counter[str] = Counter()
    for token in tokens:
        if len(token) < 2 or token in stop:
            continue
        counts[token] += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [item[0] for item in ranked[:limit]]


def _generate_note_meta(note: dict[str, Any], related: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    citations = note.get("citations", []) or []
    content = str(note.get("content") or "")
    tags = [str(item) for item in note.get("tags", []) or [] if str(item).strip()]
    suggested = tags + [token for token in _extract_keywords(content, limit=8) if token not in tags]
    summary = " ".join(content.replace("\n", " ").split())[:220]
    source_spans = []
    for item in citations[:6]:
        source_spans.append(
            {
                "id": f"{item.get('source_id', '')}:{item.get('index', '')}",
                "source": item.get("source_title") or item.get("source"),
                "page": item.get("locator") or item.get("page"),
                "content": (item.get("excerpt") or item.get("content") or "")[:220],
            }
        )
    return {
        "summary": summary,
        "suggested_tags": suggested[:8],
        "related_notes": related or [],
        "paper_card": {
            "title": note.get("title"),
            "kind": note.get("kind"),
            "citation_count": len(citations),
            "tag_count": len(tags),
        },
        "source_spans": source_spans,
        "extraction_status": "done",
        "updated_at": _now_iso(),
    }


def _related_notes_for(notebook_id: str, note_id: str, limit: int = 8) -> list[dict[str, Any]]:
    manager = get_notebook_manager()
    target = manager.get_note(notebook_id, note_id)
    if not target:
        return []
    target_tags = {str(item).lower() for item in target.get("tags", []) or [] if str(item).strip()}
    target_sources = {
        str(item.get("source_id") or item.get("file_id") or "")
        for item in target.get("citations", []) or []
        if isinstance(item, dict)
    }
    target_sources.discard("")
    rows: list[dict[str, Any]] = []
    for row in manager.list_notes(notebook_id):
        rid = str(row.get("id") or "")
        if not rid or rid == note_id:
            continue
        tags = {str(item).lower() for item in row.get("tags", []) or [] if str(item).strip()}
        citations = row.get("citations", []) or []
        sources = {
            str(item.get("source_id") or item.get("file_id") or "")
            for item in citations
            if isinstance(item, dict)
        }
        sources.discard("")
        score = 0.0
        if target_tags and tags:
            score += len(target_tags & tags) / max(1, len(target_tags | tags))
        if target_sources and sources:
            score += len(target_sources & sources) / max(1, len(target_sources | sources))
        if score <= 0:
            continue
        rows.append(
            {
                "id": rid,
                "title": row.get("title", "Untitled note"),
                "tags": list(row.get("tags", []) or []),
                "score": round(score, 4),
                "content_preview": row.get("preview", ""),
                "updated_at": row.get("updated_at"),
            }
        )
    rows.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return rows[:limit]


def _graph_payload(notebook_id: str) -> dict[str, Any]:
    manager = get_notebook_manager()
    notes = manager.list_notes(notebook_id)
    note_nodes = []
    concept_nodes = []
    edges = []
    concept_to_notes: defaultdict[str, list[str]] = defaultdict(list)
    now = _now_iso()
    for note in notes:
        note_id = str(note.get("id") or "")
        if not note_id:
            continue
        mastery = 0.0
        kind = str(note.get("kind") or "manual")
        if kind == "manual":
            mastery = 0.65
        elif kind == "saved_chat":
            mastery = 0.74
        elif kind == "saved_research":
            mastery = 0.82
        elif kind == "saved_studio":
            mastery = 0.78
        note_nodes.append(
            {
                "id": f"note:{note_id}",
                "kind": "note",
                "label": note.get("title", "Untitled note"),
                "subtitle": kind,
                "mastery_score": round(mastery * 100, 1),
                "note_id": note_id,
            }
        )
        tags = [str(item).strip() for item in note.get("tags", []) or [] if str(item).strip()]
        if not tags:
            tags = _extract_keywords(str(note.get("preview") or ""), limit=3)
        for tag in tags[:6]:
            concept = tag.lower()
            concept_to_notes[concept].append(note_id)
            edges.append(
                {
                    "id": f"edge:{note_id}:{concept}",
                    "kind": "note_concept",
                    "source_id": f"note:{note_id}",
                    "target_id": f"concept:{concept}",
                    "source_label": note.get("title", "Untitled note"),
                    "target_label": concept,
                    "relation_label": "tag",
                    "score": 1.0,
                }
            )

    for concept, linked in concept_to_notes.items():
        concept_nodes.append(
            {
                "id": f"concept:{concept}",
                "kind": "concept",
                "label": concept,
                "subtitle": f"{len(linked)} notes",
                "mastery_score": None,
            }
        )
        if len(linked) > 1:
            left = linked[0]
            for right in linked[1:]:
                edges.append(
                    {
                        "id": f"edge:related:{left}:{right}:{concept}",
                        "kind": "note_relation",
                        "source_id": f"note:{left}",
                        "target_id": f"note:{right}",
                        "source_label": left,
                        "target_label": right,
                        "relation_label": f"shared:{concept}",
                        "score": 0.6,
                    }
                )
    return {
        "notebook_id": notebook_id,
        "updated_at": now,
        "metrics": {
            "note_count": len(note_nodes),
            "concept_count": len(concept_nodes),
            "edge_count": len(edges),
            "note_relation_count": len([row for row in edges if row.get("kind") == "note_relation"]),
        },
        "nodes": note_nodes + concept_nodes,
        "edges": edges,
    }


def _insights_payload(notebook_id: str) -> dict[str, Any]:
    manager = get_notebook_manager()
    notes = manager.list_notes(notebook_id)
    sources = manager.list_sources(notebook_id)
    concept_counter: Counter[str] = Counter()
    for row in notes:
        tags = [str(item).strip().lower() for item in row.get("tags", []) or [] if str(item).strip()]
        if not tags:
            tags = _extract_keywords(str(row.get("preview") or ""), limit=3)
        concept_counter.update(tags[:5])
    weak_topics = [{"concept": key, "count": value} for key, value in concept_counter.most_common(8)]
    high_value = []
    for row in notes[:8]:
        urgency = 80 if str(row.get("kind")) == "saved_research" else 55
        mastery = 72 if str(row.get("kind")) == "manual" else 84
        high_value.append(
            {
                "id": row.get("id"),
                "title": row.get("title", "Untitled note"),
                "urgency": urgency,
                "mastery_score": mastery,
            }
        )
    return {
        "coverage": {
            "papers_with_notes": len(notes),
            "total_papers": len(sources),
            "coverage_rate": round(len(notes) / max(1, len(sources)), 4),
        },
        "mastery": {
            "note_count": len(notes),
            "avg_score": int(round(sum(item.get("mastery_score", 0) for item in high_value) / max(1, len(high_value)))),
        },
        "weak_topics_top_n": weak_topics,
        "high_value_review_notes": high_value,
        "updated_at": _now_iso(),
    }


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
    payload = get_notebook_manager().build_workspace_view(
        notebook_id,
        active_note_id=active_note_id,
        search=search,
        tag=tag,
    )
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
    rows = get_notebook_manager().list_notes(notebook_id, search=search, tag=tag)
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
    try:
        note = get_notebook_manager().update_note(notebook_id, note_id, **req.model_dump(exclude_none=True))
    except NotebookConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "latest": exc.latest,
            },
        ) from exc
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


def _run_import_kb_job(job_id: str, notebook_id: str, kb_id: str) -> None:
    manager = get_notebook_manager()
    job = _NOTEBOOK_JOBS.get(notebook_id, {}).get(job_id)
    if not job:
        return
    kb_manager = manager._get_kb_manager()
    kb = kb_manager.get_kb(kb_id)
    files = list(kb.get("files", []) if kb else [])
    total = len(files)
    _update_job(
        job,
        status="running",
        total=total,
        progress=0.0,
        processed=0,
        message=f"importing 0/{total}",
    )
    _append_event(notebook_id, {"type": "step", "step": "import", "status": "working", "job_id": job_id})
    if total == 0:
        _update_job(job, status="done", progress=1.0, message="knowledge base has no files")
        _append_event(
            notebook_id,
            {
                "type": "done",
                "step": "import",
                "status": "done",
                "job_id": job_id,
                "message": "knowledge base has no files",
            },
        )
        _append_event(notebook_id, {"type": "context_invalidated", "job_id": job_id, "affected_note_ids": []})
        return

    processed = 0
    failures = 0
    for file_info in files:
        file_id = str(file_info.get("id") or "")
        if not file_id:
            failures += 1
            processed += 1
            continue
        try:
            title = Path(str(file_info.get("name") or "kb-file")).stem
            manager.create_source(
                notebook_id=notebook_id,
                kind="kb_ref",
                kb_id=kb_id,
                file_id=file_id,
                title=title,
            )
        except Exception:
            failures += 1
        finally:
            processed += 1
            _update_job(
                job,
                status="running",
                processed=processed,
                progress=processed / max(1, total),
                message=f"importing {processed}/{total}",
            )

    if failures == 0:
        status = "done"
    elif failures < total:
        status = "partial_failed"
    else:
        status = "error"
    final_message = f"import finished: {processed - failures} ok, {failures} failed"
    _update_job(job, status=status, progress=1.0, message=final_message)
    _append_event(
        notebook_id,
        {
            "type": "done",
            "step": "import",
            "status": status,
            "job_id": job_id,
            "message": final_message,
        },
    )
    _append_event(notebook_id, {"type": "context_invalidated", "job_id": job_id, "affected_note_ids": []})


@router.post("/notebooks/{notebook_id}/imports/kb")
async def import_kb_sources(notebook_id: str, req: ImportFromKbRequest):
    _require_notebook(notebook_id)
    manager = get_notebook_manager()
    kb = manager._get_kb_manager().get_kb(req.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    total = len(kb.get("files", []) or [])
    job = _create_job(
        notebook_id=notebook_id,
        job_type="import_kb",
        total=total,
        trigger_mode=req.trigger_mode,
        kb_id=req.kb_id,
        message="pending",
    )
    if req.run_async:
        thread = threading.Thread(
            target=_run_import_kb_job,
            args=(job.id, notebook_id, req.kb_id),
            daemon=True,
            name=f"nb-import-{job.id[:8]}",
        )
        thread.start()
    else:
        _run_import_kb_job(job.id, notebook_id, req.kb_id)
    with _RUNTIME_LOCK:
        payload = _job_payload(_NOTEBOOK_JOBS.get(notebook_id, {}).get(job.id, job))
    return {"success": True, "data": payload}


@router.get("/notebooks/{notebook_id}/events")
async def stream_notebook_events(
    notebook_id: str,
    request: Request,
    cursor: int | None = Query(default=None, ge=0),
    single_pass: bool = Query(default=False),
):
    _require_notebook(notebook_id)
    header_cursor = request.headers.get("last-event-id")
    if cursor is None and header_cursor and str(header_cursor).isdigit():
        cursor = int(header_cursor)

    async def generate():
        yield f": {' ' * 2048}\n\n"
        current_cursor = int(cursor or 0)
        while True:
            if await request.is_disconnected():
                break
            with _RUNTIME_LOCK:
                rows = list(_NOTEBOOK_EVENTS.get(notebook_id, []))
            pending = [event for event in rows if int(event.get("cursor", 0)) > current_cursor]
            if pending:
                for event in pending:
                    current_cursor = int(event.get("cursor", current_cursor))
                    yield _sse_event_with_cursor(event)
                if single_pass:
                    break
            else:
                yield ": ping\n\n"
                if single_pass:
                    break
            await asyncio.sleep(1.0)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/notebooks/{notebook_id}/graph-view")
async def get_graph_view(notebook_id: str, refresh: bool = Query(default=False)):
    _require_notebook(notebook_id)
    del refresh
    return {"success": True, "data": _graph_payload(notebook_id)}


@router.get("/notebooks/{notebook_id}/graph")
async def get_graph_alias(notebook_id: str):
    _require_notebook(notebook_id)
    return {"success": True, "data": _graph_payload(notebook_id)}


@router.get("/notebooks/{notebook_id}/insights")
async def get_insights(notebook_id: str):
    _require_notebook(notebook_id)
    return {"success": True, "data": _insights_payload(notebook_id)}


@router.get("/notebooks/{notebook_id}/notes/{note_id}/related")
async def get_related_notes(
    notebook_id: str,
    note_id: str,
    limit: int = Query(default=8, ge=1, le=20),
    include_all: bool = Query(default=True),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
):
    del include_all
    _require_notebook(notebook_id)
    rows = _related_notes_for(notebook_id, note_id, limit=max(limit, 8))
    rows = [row for row in rows if float(row.get("score", 0.0)) >= float(min_score)]
    return {"success": True, "data": rows[:limit]}


@router.get("/notebooks/{notebook_id}/notes/{note_id}/meta")
async def get_note_meta(notebook_id: str, note_id: str):
    _require_notebook(notebook_id)
    note = get_notebook_manager().get_note(notebook_id, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    with _RUNTIME_LOCK:
        existing = _NOTE_META.get(notebook_id, {}).get(note_id)
    if existing:
        return {"success": True, "data": existing}
    related = _related_notes_for(notebook_id, note_id)
    generated = _generate_note_meta(note, related=related)
    with _RUNTIME_LOCK:
        _NOTE_META.setdefault(notebook_id, {})[note_id] = generated
    return {"success": True, "data": generated}


@router.put("/notebooks/{notebook_id}/notes/{note_id}/meta")
async def update_note_meta(notebook_id: str, note_id: str, req: UpdateNoteMetaRequest):
    _require_notebook(notebook_id)
    note = get_notebook_manager().get_note(notebook_id, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    with _RUNTIME_LOCK:
        current = dict(_NOTE_META.get(notebook_id, {}).get(note_id) or _generate_note_meta(note))
        for key, value in req.model_dump(exclude_none=True).items():
            current[key] = value
        current["updated_at"] = _now_iso()
        _NOTE_META.setdefault(notebook_id, {})[note_id] = current
    _append_event(
        notebook_id,
        {
            "type": "context_invalidated",
            "step": "meta_update",
            "status": "done",
            "affected_note_ids": [note_id],
        },
    )
    return {"success": True, "data": current}


@router.post("/notebooks/{notebook_id}/notes/{note_id}/extract")
async def rerun_note_extraction(notebook_id: str, note_id: str):
    _require_notebook(notebook_id)
    manager = get_notebook_manager()
    note = manager.get_note(notebook_id, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    job = _create_job(
        notebook_id=notebook_id,
        job_type="extract_note",
        total=1,
        trigger_mode="manual",
        message="running extraction",
    )
    _update_job(job, status="running", processed=0, progress=0.0, message="extracting")
    related = _related_notes_for(notebook_id, note_id)
    meta = _generate_note_meta(note, related=related)
    merged_tags = []
    for item in list(note.get("tags", []) or []) + list(meta.get("suggested_tags", []) or []):
        tag = str(item).strip()
        if tag and tag not in merged_tags:
            merged_tags.append(tag)
    updated = manager.update_note(notebook_id, note_id, tags=merged_tags) or note
    updated["ai_meta"] = meta
    with _RUNTIME_LOCK:
        _NOTE_META.setdefault(notebook_id, {})[note_id] = meta
    _update_job(job, status="done", processed=1, progress=1.0, note_ids=[note_id], message="extraction done")
    _append_event(
        notebook_id,
        {
            "type": "context_invalidated",
            "step": "extract_note",
            "status": "done",
            "job_id": job.id,
            "affected_note_ids": [note_id],
        },
    )
    return {"success": True, "data": {"job_id": job.id, "note": updated, "meta": meta}}


@router.post("/notebooks/{notebook_id}/migrate-records")
async def migrate_notebook_records(notebook_id: str):
    _require_notebook(notebook_id)
    manager = get_notebook_manager()
    migrated = 0
    for row in manager.list_notes(notebook_id):
        note_id = str(row.get("id") or "")
        if not note_id:
            continue
        detail = manager.get_note(notebook_id, note_id)
        if not detail:
            continue
        tags = []
        for item in detail.get("tags", []) or []:
            tag = str(item).strip()
            if tag and tag not in tags:
                tags.append(tag)
        if tags != list(detail.get("tags", []) or []):
            manager.update_note(notebook_id, note_id, tags=tags)
            migrated += 1
    _append_event(
        notebook_id,
        {
            "type": "context_invalidated",
            "step": "migrate_records",
            "status": "done",
            "affected_note_ids": [],
            "message": f"migrated={migrated}",
        },
    )
    return {"success": True, "data": {"migrated_count": migrated}}
