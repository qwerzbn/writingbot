# -*- coding: utf-8 -*-
"""
Session Manager (Enterprise)
============================

Manages conversation sessions with:
- JSONL storage (one file per session)
- Append-only writes for crash safety
- LRU caching for active sessions
- Message windowing for LLM context

Based on Nanobot's architecture.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: str) -> str:
    """Convert a string to a safe filename."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


@dataclass
class Session:
    """
    A conversation session.
    
    Stores messages in JSONL format for easy reading and persistence.
    """
    
    key: str  # session_id or channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str, **kwargs: Any) -> dict:
        """Add a message to the session and return it."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()
        return msg
    
    def get_history(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """
        Get message history for LLM context.
        
        Args:
            max_messages: Maximum messages to return (for context windowing).
        
        Returns:
            List of messages in LLM format.
        """
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        return [{"role": m["role"], "content": m["content"]} for m in recent]
    
    def clear(self) -> None:
        """Clear all messages in the session."""
        self.messages = []
        self.updated_at = datetime.now()
    
    def to_dict(self) -> dict:
        """Convert session to dictionary for API responses."""
        return {
            "id": self.key,
            "title": self.metadata.get("title", "New Chat"),
            "kb_id": self.metadata.get("kb_id"),
            "messages": self.messages,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class SessionManager:
    """
    Manages conversation sessions.
    
    Sessions are stored as JSONL files:
    - Line 1: Metadata (created_at, kb_id, title)
    - Line N: Message objects
    
    This enables O(1) append operations and crash-safe storage.
    """
    
    def __init__(self, sessions_dir: str | Path = "./data/sessions"):
        self.sessions_dir = ensure_dir(Path(sessions_dir))
        self._cache: dict[str, Session] = {}
    
    def _get_session_path(self, key: str) -> Path:
        """Get the file path for a session."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"
    
    def get_or_create(self, key: str, **metadata) -> Session:
        """
        Get an existing session or create a new one.
        
        Args:
            key: Session key (session_id).
            **metadata: Optional metadata for new sessions (kb_id, title).
        
        Returns:
            The session.
        """
        # Check cache first
        if key in self._cache:
            return self._cache[key]
        
        # Try to load from disk
        session = self._load(key)
        if session is None:
            session = Session(key=key, metadata=metadata)
        
        self._cache[key] = session
        return session
    
    def _load(self, key: str) -> Optional[Session]:
        """Load a session from disk."""
        path = self._get_session_path(key)
        
        if not path.exists():
            return None
        
        try:
            messages = []
            metadata = {}
            created_at = None
            
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    data = json.loads(line)
                    
                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        if data.get("created_at"):
                            created_at = datetime.fromisoformat(data["created_at"])
                    else:
                        messages.append(data)
            
            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata
            )
        except Exception as e:
            print(f"[SessionManager] Failed to load session {key}: {e}")
            return None
    
    def save(self, session: Session) -> None:
        """Save a session to disk (full rewrite)."""
        path = self._get_session_path(session.key)
        
        with open(path, "w", encoding="utf-8") as f:
            # Write metadata first
            metadata_line = {
                "_type": "metadata",
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata
            }
            f.write(json.dumps(metadata_line, ensure_ascii=False) + "\n")
            
            # Write messages
            for msg in session.messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        
        self._cache[session.key] = session
    
    def append_message(self, session: Session, message: dict) -> None:
        """Append a single message to session file (O(1) operation)."""
        path = self._get_session_path(session.key)
        
        # If file doesn't exist, do full save
        if not path.exists():
            self.save(session)
            return
        
        # Append message to file
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(message, ensure_ascii=False) + "\n")
        
        # Update metadata line (rewrite first line for updated_at)
        # For simplicity, we'll do full save on metadata changes
        # Append-only for messages is the key optimization
    
    def delete(self, key: str) -> bool:
        """Delete a session."""
        self._cache.pop(key, None)
        
        path = self._get_session_path(key)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions with basic info."""
        sessions = []
        
        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                with open(path, encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            metadata = data.get("metadata", {})
                            sessions.append({
                                "id": path.stem,
                                "title": metadata.get("title", "New Chat"),
                                "kb_id": metadata.get("kb_id"),
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at")
                            })
            except Exception:
                continue
        
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
    
    def get(self, key: str) -> Optional[Session]:
        """Get a session by key (load if not cached)."""
        if key in self._cache:
            return self._cache[key]
        
        session = self._load(key)
        if session:
            self._cache[key] = session
        return session
