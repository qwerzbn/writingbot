# -*- coding: utf-8 -*-
"""Co-Writer API compatibility layer backed by Orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.orchestrator.service import get_orchestrator_service
from src.retrieval import HybridRetrievalService
from src.shared_capabilities.knowledge import augment_chart_evidence, get_vector_store


router = APIRouter()
class EditRequest(BaseModel):
    text: str
    action: Literal["rewrite", "expand", "shorten", "polish"] = "rewrite"
    instruction: str = ""
    kb_id: str | None = None
    include_evidence: bool = True


class EvidenceRequest(BaseModel):
    query: str
    kb_id: str
    top_k: int = 5


@router.post("/co-writer/evidence")
async def get_writing_evidence(req: EvidenceRequest):
    if not req.query.strip():
        return {"success": True, "data": []}

    vector_store = get_vector_store(req.kb_id)
    if not vector_store:
        return {"success": True, "data": []}

    hybrid = HybridRetrievalService()
    data = hybrid.retrieve(kb_id=req.kb_id, vector_store=vector_store, query=req.query, top_k=req.top_k)
    augmented = augment_chart_evidence(
        kb_id=req.kb_id,
        query=req.query,
        context=data.get("context_window", {}).get("context", ""),
        sources=data.get("sources", []) or [],
        data_dir=Path(__file__).resolve().parents[4] / "data" / "knowledge_bases",
    )
    return {"success": True, "data": augmented.get("sources", [])}


@router.post("/co-writer/edit")
async def edit_text(req: EditRequest):
    service = get_orchestrator_service()
    result = service.execute_sync(
        mode="writing",
        payload={
            "text": req.text,
            "action": req.action,
            "instruction": req.instruction,
            "kb_id": req.kb_id,
        },
    )
    return {
        "success": True,
        "data": {
            "edited_text": result.get("output", ""),
            "action": req.action,
            "used_sources": result.get("sources", []),
            "run_id": result.get("run_id"),
            "trace_id": result.get("trace_id"),
        },
    }


@router.post("/co-writer/edit/stream")
async def edit_text_stream(req: EditRequest):
    service = get_orchestrator_service()
    created = service.create_run(
        mode="writing",
        payload={
            "text": req.text,
            "action": req.action,
            "instruction": req.instruction,
            "kb_id": req.kb_id,
            "include_evidence": req.include_evidence,
        },
    )
    run_id = created["run_id"]

    def generate():
        yield f": {' ' * 2048}\n\n"
        for event in service.stream_run(run_id):
            etype = event.get("type")
            if etype == "chunk":
                yield f"data: {json.dumps({'type': 'chunk', 'content': event.get('content', '')}, ensure_ascii=False)}\n\n"
            elif etype == "sources":
                yield f"data: {json.dumps({'type': 'sources', 'data': event.get('data', [])}, ensure_ascii=False)}\n\n"
            elif etype == "done":
                yield f"data: {json.dumps({'type': 'done', 'action': req.action}, ensure_ascii=False)}\n\n"
            elif etype == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': event.get('error', 'unknown')}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "x-orchestrated": "true"},
    )
