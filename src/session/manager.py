# -*- coding: utf-8 -*-
"""Conversation session storage backed by JSONL files."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.services.config import get_main_config


@dataclass
class ConversationSession:
    """In-memory representation of a chat conversation."""

    id: str
    title: str = "新对话"
    kb_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    messages: list[dict[str, Any]] = field(default_factory=list)

    def add_message(
        self,
        role: str,
        content: str,
        sources: list[dict[str, Any]] | None = None,
        timestamp: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ts = timestamp or datetime.now().isoformat()
        message = {
            "role": role,
            "content": content,
            "timestamp": ts,
            "sources": sources or [],
        }
        if metadata:
            message["metadata"] = metadata
        self.messages.append(message)
        self.updated_at = ts
        return message

    def to_dict(self, include_messages: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "kb_id": self.kb_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_messages:
            payload["messages"] = list(self.messages)
        return payload


class SessionManager:
    """Manages chat conversation persistence under data/sessions."""

    def __init__(self, sessions_dir: str | Path | None = None):
        if sessions_dir is None:
            config = get_main_config()
            sessions_dir = config.get("paths", {}).get("sessions_dir", "./data/sessions")
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.jsonl"

    def create(self, title: str = "新对话", kb_id: str | None = None, session_id: str | None = None) -> ConversationSession:
        now = datetime.now().isoformat()
        return ConversationSession(
            id=session_id or str(uuid.uuid4()),
            title=title or "新对话",
            kb_id=kb_id,
            created_at=now,
            updated_at=now,
            messages=[],
        )

    def get_or_create(self, session_id: str, title: str = "新对话", kb_id: str | None = None) -> ConversationSession:
        session = self.get(session_id)
        if session:
            return session
        return self.create(title=title, kb_id=kb_id, session_id=session_id)

    def get(self, session_id: str) -> ConversationSession | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        session = self._load(path)
        if not session:
            return None
        if len(session.messages) == 0:
            with self._lock:
                path.unlink(missing_ok=True)
            return None
        return session

    def save(self, session: ConversationSession) -> None:
        path = self._path(session.id)
        with self._lock:
            # Keep only meaningful sessions; drafts stay in frontend state.
            if len(session.messages) == 0:
                path.unlink(missing_ok=True)
                return

            session.updated_at = datetime.now().isoformat()
            metadata = {
                "_type": "metadata",
                "id": session.id,
                "title": session.title,
                "kb_id": session.kb_id,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }

            lines = [json.dumps(metadata, ensure_ascii=False)]
            for msg in session.messages:
                normalized = {
                    "role": msg.get("role", "assistant"),
                    "content": msg.get("content", ""),
                    "timestamp": msg.get("timestamp") or datetime.now().isoformat(),
                    "sources": msg.get("sources", []) or [],
                }
                metadata_obj = msg.get("metadata")
                if isinstance(metadata_obj, dict) and metadata_obj:
                    normalized["metadata"] = metadata_obj
                lines.append(json.dumps(normalized, ensure_ascii=False))

            self._atomic_write_lines(path, lines)

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not path.exists():
            return False
        with self._lock:
            path.unlink(missing_ok=True)
        return True

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        with self._lock:
            for path in self.sessions_dir.glob("*.jsonl"):
                session = self._load(path)
                if not session:
                    continue
                if len(session.messages) == 0:
                    path.unlink(missing_ok=True)
                    continue

                last_message = (session.messages[-1].get("content") or "").strip()[:120] if session.messages else ""
                sessions.append(
                    {
                        "id": session.id,
                        "title": session.title,
                        "kb_id": session.kb_id,
                        "created_at": session.created_at,
                        "updated_at": session.updated_at,
                        "message_count": len(session.messages),
                        "last_message": last_message,
                    }
                )

        sessions.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
        return sessions

    def _atomic_write_lines(self, path: Path, lines: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for line in lines:
                    f.write(line)
                    f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _load(self, path: Path) -> ConversationSession | None:
        session_id = path.stem

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
        except Exception:
            return None

        if not lines:
            return None

        now = datetime.now().isoformat()
        meta = {
            "id": session_id,
            "title": "新对话",
            "kb_id": None,
            "created_at": now,
            "updated_at": now,
        }
        start_idx = 0

        try:
            first = json.loads(lines[0])
            if isinstance(first, dict) and first.get("_type") == "metadata":
                if "title" in first or "kb_id" in first:
                    meta["id"] = first.get("id") or session_id
                    meta["title"] = first.get("title") or "新对话"
                    meta["kb_id"] = first.get("kb_id")
                    meta["created_at"] = first.get("created_at") or now
                    meta["updated_at"] = first.get("updated_at") or meta["created_at"]
                else:
                    # Legacy metadata format: metadata={title, kb_id}
                    legacy = first.get("metadata", {}) if isinstance(first.get("metadata"), dict) else {}
                    meta["id"] = first.get("id") or session_id
                    meta["title"] = legacy.get("title") or first.get("title") or "新对话"
                    meta["kb_id"] = legacy.get("kb_id")
                    meta["created_at"] = first.get("created_at") or now
                    meta["updated_at"] = first.get("updated_at") or meta["created_at"]
                start_idx = 1
        except Exception:
            start_idx = 0

        messages: list[dict[str, Any]] = []
        for raw in lines[start_idx:]:
            try:
                item = json.loads(raw)
            except Exception:
                continue
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role not in ("user", "assistant"):
                continue
            msg = {
                "role": role,
                "content": item.get("content", ""),
                "timestamp": item.get("timestamp") or now,
                "sources": item.get("sources", []) or [],
            }
            metadata_obj = item.get("metadata")
            if isinstance(metadata_obj, dict) and metadata_obj:
                msg["metadata"] = metadata_obj
            messages.append(msg)

        if not messages:
            return None

        if meta["updated_at"] == meta["created_at"]:
            meta["updated_at"] = messages[-1].get("timestamp") or meta["updated_at"]

        return ConversationSession(
            id=meta["id"],
            title=meta["title"],
            kb_id=meta["kb_id"],
            created_at=meta["created_at"],
            updated_at=meta["updated_at"],
            messages=messages,
        )
