# -*- coding: utf-8 -*-
"""
Co-Writer API Router
=====================

Endpoints for AI-assisted text editing operations.
"""

import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()

# Lazy-loaded agent
_co_writer_agent = None


def get_co_writer_agent():
    global _co_writer_agent
    if _co_writer_agent is None:
        from src.agents.co_writer import CoWriterAgent
        _co_writer_agent = CoWriterAgent()
    return _co_writer_agent


class EditRequest(BaseModel):
    text: str
    action: Literal["rewrite", "expand", "shorten", "polish"] = "rewrite"
    instruction: str = ""


@router.post("/co-writer/edit")
async def edit_text(req: EditRequest):
    """Edit text with specified action (non-streaming)."""
    try:
        agent = get_co_writer_agent()
        result = agent.process(text=req.text, action=req.action, instruction=req.instruction)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/co-writer/edit/stream")
async def edit_text_stream(req: EditRequest):
    """Edit text with SSE streaming."""
    agent = get_co_writer_agent()

    def generate():
        yield f": {' ' * 2048}\n\n"
        try:
            result = agent.process(
                text=req.text, action=req.action, instruction=req.instruction, stream=True
            )
            full_text = ""
            for chunk in result["stream"]:
                full_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'action': req.action})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
