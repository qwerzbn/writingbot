# -*- coding: utf-8 -*-
"""Research API compatibility layer backed by Orchestrator."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.orchestrator.service import get_orchestrator_service


router = APIRouter()


class ResearchRequest(BaseModel):
    topic: str
    kb_id: str | None = None


@router.post("/research")
async def research(req: ResearchRequest):
    service = get_orchestrator_service()
    if hasattr(service, "run_research_workflow"):
        result = service.run_research_workflow(topic=req.topic, kb_id=req.kb_id)
    else:
        result = service.execute_sync(mode="research", payload={"topic": req.topic, "kb_id": req.kb_id})
    return {
        "success": True,
        "data": {
            "plan": result.get("metadata", {}).get("plan") or result.get("plan") or result.get("output", "").split("\n\n")[0],
            "report": result.get("output", ""),
            "sources": result.get("sources", []),
            "run_id": result.get("run_id"),
            "trace_id": result.get("trace_id"),
            "meta": result.get("metadata", {}).get("meta", {}),
        },
    }


@router.post("/research/stream")
async def research_stream(req: ResearchRequest):
    service = get_orchestrator_service()

    def generate():
        yield f": {' ' * 2048}\n\n"
        if hasattr(service, "stream_research_workflow"):
            for event in service.stream_research_workflow(topic=req.topic, kb_id=req.kb_id):
                if event.get("type") == "done":
                    yield f"data: {json.dumps({'type': 'done', 'meta': event.get('meta', {})}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            return

        created = service.create_run(mode="research", payload={"topic": req.topic, "kb_id": req.kb_id})
        run_id = created["run_id"]
        plan_sent = False
        for event in service.stream_run(run_id):
            etype = event.get("type")
            if etype == "step" and event.get("step") == "plan" and event.get("status") == "done" and not plan_sent:
                run = service.get_run(run_id)
                plan = (run.result or {}).get("plan", "") if run else ""
                if plan:
                    yield f"data: {json.dumps({'type': 'plan', 'content': plan}, ensure_ascii=False)}\n\n"
                    plan_sent = True
            elif etype == "chunk":
                content = event.get("content", "")
                if content.startswith("## 鐮旂┒璁″垝"):
                    continue
                yield f"data: {json.dumps({'type': 'chunk', 'content': content}, ensure_ascii=False)}\n\n"
            elif etype == "sources":
                yield (
                    f"data: {json.dumps({'type': 'sources', 'data': event.get('data', []), 'meta': event.get('meta', {})}, ensure_ascii=False)}\n\n"
                )
            elif etype == "done":
                if not plan_sent and event.get("plan"):
                    yield f"data: {json.dumps({'type': 'plan', 'content': event.get('plan')}, ensure_ascii=False)}\n\n"
                    plan_sent = True
                yield f"data: {json.dumps({'type': 'done', 'meta': event.get('meta', {})}, ensure_ascii=False)}\n\n"
            elif etype == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': event.get('error', 'unknown')}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "x-orchestrated": "true"},
    )
