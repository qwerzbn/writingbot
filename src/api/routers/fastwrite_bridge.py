# -*- coding: utf-8 -*-
"""FastWrite lightweight bridge APIs."""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter()
DEFAULT_FASTWRITE_URL = "http://127.0.0.1:3002"


def _resolve_fastwrite_url() -> str:
    value = (
        os.getenv("FASTWRITE_URL")
        or os.getenv("NEXT_PUBLIC_FASTWRITE_URL")
        or DEFAULT_FASTWRITE_URL
    ).strip()
    return value.rstrip("/") if value else DEFAULT_FASTWRITE_URL


@dataclass
class BridgeSession:
    session_id: str
    callback_token: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(hours=2))
    status: str = "pending"
    error: str | None = None
    callback_result: dict[str, Any] | None = None


class BridgeStore:
    def __init__(self):
        self._sessions: dict[str, BridgeSession] = {}
        self._callback_index: dict[str, str] = {}
        self._expired_tokens: dict[str, str] = {}
        self._lock = threading.RLock()

    def _cleanup(self) -> None:
        now = datetime.now()
        expired = [sid for sid, sess in self._sessions.items() if sess.expires_at <= now]
        for sid in expired:
            session = self._sessions[sid]
            token = session.callback_token
            self._expired_tokens[token] = session.expires_at.isoformat()
            self._sessions.pop(sid, None)
            self._callback_index.pop(token, None)

    def create(self, payload: dict[str, Any]) -> BridgeSession:
        with self._lock:
            self._cleanup()
            session_id = str(uuid.uuid4())
            callback_token = str(uuid.uuid4())
            session = BridgeSession(session_id=session_id, callback_token=callback_token, payload=payload)
            self._sessions[session_id] = session
            self._callback_index[callback_token] = session_id
            return session

    def get_session(self, session_id: str) -> BridgeSession | None:
        with self._lock:
            self._cleanup()
            return self._sessions.get(session_id)

    def set_callback(self, callback_token: str, data: dict[str, Any]) -> BridgeSession | None:
        with self._lock:
            self._cleanup()
            session_id = self._callback_index.get(callback_token)
            if not session_id:
                return None
            session = self._sessions.get(session_id)
            if not session:
                return None
            status = data.get("status", "completed")
            session.status = status
            session.error = data.get("error")
            session.callback_result = {
                "received_at": datetime.now().isoformat(),
                **data,
            }
            return session

    def get_by_callback(self, callback_token: str) -> BridgeSession | None:
        with self._lock:
            self._cleanup()
            session_id = self._callback_index.get(callback_token)
            if not session_id:
                return None
            return self._sessions.get(session_id)

    def get_callback_status(self, callback_token: str) -> tuple[str, BridgeSession | None]:
        with self._lock:
            self._cleanup()
            session_id = self._callback_index.get(callback_token)
            if session_id:
                session = self._sessions.get(session_id)
                if not session:
                    return "failed", None
                return session.status, session
            if callback_token in self._expired_tokens:
                return "expired", None
            return "invalid", None


_bridge_store = BridgeStore()


class HandoffRequest(BaseModel):
    text: str
    title: str = "WritingBot Draft"
    kb_id: str | None = None
    source: str = "co_writer"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CallbackRequest(BaseModel):
    content: str
    title: str | None = None
    status: str = "completed"
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/fastwrite/handoff")
async def create_handoff(req: HandoffRequest):
    session = _bridge_store.create(
        {
            "text": req.text,
            "title": req.title,
            "kb_id": req.kb_id,
            "source": req.source,
            "metadata": req.metadata,
            "created_at": datetime.now().isoformat(),
        }
    )
    fastwrite_url = (
        f"{_resolve_fastwrite_url()}/"
        f"?wb_session={session.session_id}&wb_callback={session.callback_token}"
    )
    return {
        "success": True,
        "data": {
            "session_id": session.session_id,
            "callback_token": session.callback_token,
            "fastwrite_url": fastwrite_url,
            "expires_at": session.expires_at.isoformat(),
        },
    }


@router.get("/fastwrite/health")
async def fastwrite_health():
    base_url = _resolve_fastwrite_url()
    target = f"{base_url}/"
    req = urllib_request.Request(target, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=2.0) as resp:
            status_code = int(getattr(resp, "status", 200))
            return {
                "success": True,
                "data": {
                    "available": True,
                    "status_code": status_code,
                    "url": base_url,
                },
            }
    except urllib_error.HTTPError as exc:
        return {
            "success": True,
            "data": {
                "available": True,
                "status_code": int(exc.code),
                "url": base_url,
                "warning": f"FastWrite returned HTTP {exc.code}",
            },
        }
    except Exception as exc:
        return {
            "success": True,
            "data": {
                "available": False,
                "url": base_url,
                "error": str(exc),
            },
        }


@router.get("/fastwrite/handoff/{session_id}")
async def get_handoff(session_id: str):
    session = _bridge_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return {
        "success": True,
        "data": {
            "session_id": session.session_id,
            "callback_token": session.callback_token,
            "payload": session.payload,
            "status": session.status,
            "error": session.error,
            "callback_result": session.callback_result,
        },
    }


@router.post("/fastwrite/callback/{callback_token}")
async def fastwrite_callback(callback_token: str, req: CallbackRequest):
    session = _bridge_store.set_callback(
        callback_token,
        {
            "content": req.content,
            "title": req.title,
            "status": req.status,
            "error": req.error,
            "metadata": req.metadata,
        },
    )
    if not session:
        raise HTTPException(status_code=404, detail="Invalid callback token")
    return {
        "success": True,
        "data": {
            "session_id": session.session_id,
            "status": session.status,
            "error": session.error,
            "callback_result": session.callback_result,
        },
    }


@router.get("/fastwrite/callback/{callback_token}")
async def get_callback_result(callback_token: str):
    status, session = _bridge_store.get_callback_status(callback_token)
    if status == "invalid":
        raise HTTPException(status_code=404, detail="Invalid callback token")
    if status == "expired":
        return {
            "success": True,
            "data": {
                "session_id": None,
                "callback_result": None,
                "status": "expired",
                "error": "callback token expired",
            },
        }
    return {
        "success": True,
        "data": {
            "session_id": session.session_id,
            "callback_result": session.callback_result,
            "status": status,
            "error": session.error,
        },
    }
