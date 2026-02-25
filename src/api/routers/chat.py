# -*- coding: utf-8 -*-
"""
Chat API Router
================

Handles chat endpoints including SSE streaming.
Uses ChatAgent for business logic (Phase 2).
"""

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

# Project root for data directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Lazy-loaded instances
_session_manager = None
_chat_agent = None

router = APIRouter()


def get_session_manager():
    """Get SessionManager instance (lazy init)."""
    global _session_manager
    if _session_manager is None:
        from src.session.manager import SessionManager
        _session_manager = SessionManager(DATA_DIR / "sessions")
    return _session_manager


def get_chat_agent():
    """Get ChatAgent instance (lazy init)."""
    global _chat_agent
    if _chat_agent is None:
        from src.agents.chat import ChatAgent
        _chat_agent = ChatAgent()
    return _chat_agent


def get_vector_store(kb_id: str):
    """Get VectorStore for a specific KB."""
    from src.knowledge.kb_manager import KnowledgeBaseManager
    from src.knowledge.vector_store import VectorStore

    kb_manager = KnowledgeBaseManager(DATA_DIR / "knowledge_bases")
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=400, detail=f"KB not found: {kb_id}")

    vector_path = kb_manager.get_vector_store_path(kb_id)
    embedding_provider = kb.get("embedding_provider", "sentence-transformers")
    embedding_model = kb.get("embedding_model", "sentence-transformers/all-mpnet-base-v2")

    return VectorStore(
        persist_dir=str(vector_path),
        collection_name=kb["collection_name"],
        embedding_model=embedding_model,
        embedding_provider=embedding_provider,
    )


def _get_or_create_session(sm, conv_id, message, kb_id):
    """Helper to get or create a session."""
    if conv_id:
        session = sm.get(conv_id)
        if not session:
            session = sm.get_or_create(
                conv_id,
                title=message[:30] + "..." if len(message) > 30 else message,
                kb_id=kb_id,
            )
        if not kb_id:
            kb_id = session.metadata.get("kb_id")
    else:
        conv_id = str(uuid.uuid4())
        session = sm.get_or_create(
            conv_id,
            title=message[:30] + "..." if len(message) > 30 else message,
            kb_id=kb_id,
        )

    return session, conv_id, kb_id


# ============== Chat Endpoints ==============


@router.post("/chat")
async def chat(request: Request):
    """Non-streaming chat endpoint using ChatAgent."""
    try:
        data = await request.json()
        if not data or "message" not in data:
            raise HTTPException(status_code=400, detail="No message provided")

        message = data["message"]
        conv_id = data.get("conversation_id")
        kb_id = data.get("kb_id")

        sm = get_session_manager()
        session, conv_id, kb_id = _get_or_create_session(sm, conv_id, message, kb_id)

        if not kb_id:
            raise HTTPException(status_code=400, detail="No Knowledge Base selected")

        # Add user message
        session.add_message("user", message)

        # Use ChatAgent for processing
        agent = get_chat_agent()
        vs = get_vector_store(kb_id)
        history = session.get_history()
        result = agent.process(message, vector_store=vs, history=history, stream=False)

        # Add assistant message
        assistant_msg = session.add_message(
            "assistant",
            result["answer"],
            sources=result.get("sources", []),
        )

        # Save session
        sm.save(session)

        return {
            "success": True,
            "data": {
                "conversation_id": conv_id,
                "message": assistant_msg,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: Request):
    """
    Streaming chat endpoint using Server-Sent Events (SSE).

    Response format (frontend compatible):
    - Text chunks: data: {"type": "chunk", "content": "..."}
    - Sources: data: {"type": "sources", "data": [...]}
    - Done: data: {"type": "done", "conversation_id": "..."}
    - Error: data: {"type": "error", "error": "..."}
    """
    data = await request.json()
    if not data or "message" not in data:
        raise HTTPException(status_code=400, detail="No message provided")

    message = data["message"]
    conv_id = data.get("conversation_id")
    kb_id = data.get("kb_id")

    def generate():
        nonlocal conv_id

        # Send padding to exhaust browser/proxy buffers
        yield f": {' ' * 2048}\n\n"

        try:
            sm = get_session_manager()
            session, conv_id_local, session_kb_id = _get_or_create_session(
                sm, conv_id, message, kb_id
            )
            conv_id = conv_id_local

            if not session_kb_id:
                yield f"data: {json.dumps({'type': 'error', 'error': 'No Knowledge Base selected'})}\n\n"
                return

            # Add user message
            session.add_message("user", message)

            # Use ChatAgent for streaming
            agent = get_chat_agent()
            vs = get_vector_store(session_kb_id)
            history = session.get_history()
            result = agent.process(message, vector_store=vs, history=history, stream=True)

            # Stream response chunks
            full_response = ""
            for chunk in result["stream"]:
                full_response += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            # Send sources
            sources = result.get("sources", [])
            yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"

            # Save assistant message
            session.add_message("assistant", full_response, sources=sources)
            sm.save(session)

            # Send done signal
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )
