# -*- coding: utf-8 -*-
"""Unified Orchestrator API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.orchestrator.events import sse_event
from src.orchestrator.models import OrchestratorMode
from src.orchestrator.service import get_orchestrator_service


router = APIRouter()


class OrchestratorRunRequest(BaseModel):
    mode: OrchestratorMode
    payload: dict = Field(default_factory=dict)


@router.post("/orchestrator/run")
async def create_run(req: OrchestratorRunRequest):
    service = get_orchestrator_service()
    run = service.create_run(mode=req.mode, payload=req.payload)
    return {"success": True, "data": run}


@router.get("/orchestrator/run/{run_id}")
async def get_run(run_id: str):
    service = get_orchestrator_service()
    run = service.get_run_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return {"success": True, "data": run}


@router.get("/orchestrator/stream/{run_id}")
async def stream_run(run_id: str):
    service = get_orchestrator_service()
    run = service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    def generate():
        yield f": {' ' * 2048}\n\n"
        for event in service.stream_run(run_id):
            yield sse_event(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
