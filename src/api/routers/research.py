# -*- coding: utf-8 -*-
"""
Research API Router
====================

Endpoints for deep research with streaming report generation.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.services.config import get_main_config

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Lazy-loaded agent
_research_agent = None


def get_research_agent():
    global _research_agent
    if _research_agent is None:
        from src.agents.research import ResearchAgent
        _research_agent = ResearchAgent()
    return _research_agent


def get_vector_store(kb_id: str):
    from src.knowledge.kb_manager import KnowledgeBaseManager
    from src.knowledge.vector_store import VectorStore

    kb_manager = KnowledgeBaseManager(DATA_DIR / "knowledge_bases")
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        return None
    vector_path = kb_manager.get_vector_store_path(kb_id)
    return VectorStore(
        persist_dir=str(vector_path),
        collection_name=kb["collection_name"],
        embedding_model=kb.get("embedding_model", "sentence-transformers/all-mpnet-base-v2"),
        embedding_provider=kb.get("embedding_provider", "sentence-transformers"),
    )


class ResearchRequest(BaseModel):
    topic: str
    kb_id: str | None = None


@router.post("/research")
async def research(req: ResearchRequest):
    """Generate a research report (non-streaming)."""
    try:
        agent = get_research_agent()
        vs = get_vector_store(req.kb_id) if req.kb_id else None
        result = agent.process(topic=req.topic, vector_store=vs, stream=False)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/research/stream")
async def research_stream(req: ResearchRequest):
    """Generate a research report with SSE streaming."""
    agent = get_research_agent()
    vs = get_vector_store(req.kb_id) if req.kb_id else None

    def generate():
        yield f": {' ' * 2048}\n\n"
        try:
            result = agent.process(topic=req.topic, vector_store=vs, stream=True)

            # Send plan
            yield f"data: {json.dumps({'type': 'plan', 'content': result['plan']})}\n\n"

            # Stream report
            full_report = ""
            for chunk in result["stream"]:
                full_report += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            # Send sources & done
            yield f"data: {json.dumps({'type': 'sources', 'data': result.get('sources', [])})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
