# -*- coding: utf-8 -*-
"""
Conversation API Router
========================

Handles conversation/session CRUD operations.
Migrated from Flask server.py to FastAPI.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

# Project root for data directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Lazy-loaded session manager
_session_manager = None

router = APIRouter()


def get_session_manager():
    """Get SessionManager instance (lazy init)."""
    global _session_manager
    if _session_manager is None:
        from src.session.manager import SessionManager
        _session_manager = SessionManager(DATA_DIR / "sessions")
    return _session_manager


# ============== Conversation CRUD ==============


@router.get("/conversations")
async def list_conversations():
    """List all conversations."""
    return {"success": True, "data": get_session_manager().list_sessions()}


@router.post("/conversations")
async def create_conversation(request: Request):
    """Create a new conversation."""
    data = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    session_id = str(uuid.uuid4())

    sm = get_session_manager()
    session = sm.get_or_create(
        session_id,
        title=data.get("title", "New Chat"),
        kb_id=data.get("kb_id"),
    )
    sm.save(session)

    return {"success": True, "data": session.to_dict()}


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    """Get a specific conversation."""
    session = get_session_manager().get(conv_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "data": session.to_dict()}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    """Delete a conversation."""
    get_session_manager().delete(conv_id)
    return {"success": True}
