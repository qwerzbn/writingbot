# -*- coding: utf-8 -*-
"""
Notebook Service
=================

Manages notebooks, legacy records, and **notes** (CRUD + JSON storage).

Storage layout:
  data/notebooks/
    {notebook_id}.json              — notebook metadata + legacy records
    {notebook_id}/notes/
      {note_id}.json                — individual note content
      meta_{note_id}.json           — AI-generated metadata (tags, summary)
"""

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.services.config import get_main_config


class NotebookManager:
    """Manages notebooks with JSON file storage."""

    def __init__(self, data_dir: Path | str | None = None):
        if data_dir is None:
            config = get_main_config()
            data_dir = Path(config.get("paths", {}).get("data_dir", "./data"))
        self.notebooks_dir = Path(data_dir) / "notebooks"
        self.notebooks_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _get_path(self, notebook_id: str) -> Path:
        return self.notebooks_dir / f"{notebook_id}.json"

    def _load(self, notebook_id: str) -> dict | None:
        path = self._get_path(notebook_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, notebook: dict):
        path = self._get_path(notebook["id"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(notebook, f, ensure_ascii=False, indent=2)

    def _notes_dir(self, notebook_id: str, ensure: bool = False) -> Path:
        d = self.notebooks_dir / notebook_id / "notes"
        if ensure:
            d.mkdir(parents=True, exist_ok=True)
        return d

    def _note_path(self, notebook_id: str, note_id: str, ensure_parent: bool = False) -> Path:
        return self._notes_dir(notebook_id, ensure=ensure_parent) / f"{note_id}.json"

    def _note_meta_path(self, notebook_id: str, note_id: str, ensure_parent: bool = False) -> Path:
        return self._notes_dir(notebook_id, ensure=ensure_parent) / f"meta_{note_id}.json"

    def _load_note_meta(self, notebook_id: str, note_id: str) -> dict | None:
        path = self._note_meta_path(notebook_id, note_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _load_note(self, notebook_id: str, note_id: str) -> dict | None:
        path = self._note_path(notebook_id, note_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_note(self, notebook_id: str, note: dict):
        path = self._note_path(notebook_id, note["id"], ensure_parent=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(note, f, ensure_ascii=False, indent=2)

    def _count_notes(self, notebook_id: str) -> int:
        d = self.notebooks_dir / notebook_id / "notes"
        if not d.exists():
            return 0
        return sum(1 for p in d.glob("*.json") if not p.name.startswith("meta_"))

    def _tokenize(self, text: str) -> set[str]:
        tokens = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", (text or "").lower())
        return set(tokens)

    # ================================================================== #
    #  Notebook CRUD (original)                                            #
    # ================================================================== #

    def list_notebooks(self) -> list[dict]:
        """List all notebooks with summary info."""
        notebooks = []
        for p in sorted(
            self.notebooks_dir.glob("*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        ):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    nb = json.load(f)
                nb_id = nb["id"]
                notebooks.append({
                    "id": nb_id,
                    "name": nb["name"],
                    "description": nb.get("description", ""),
                    "color": nb.get("color", "#3B82F6"),
                    "icon": nb.get("icon", "book"),
                    "record_count": len(nb.get("records", [])),
                    "note_count": self._count_notes(nb_id),
                    "created_at": nb.get("created_at"),
                    "updated_at": nb.get("updated_at"),
                })
            except Exception:
                continue
        return notebooks

    def create_notebook(
        self, name: str, description: str = "", color: str = "#3B82F6", icon: str = "book"
    ) -> dict:
        """Create a new notebook."""
        now = datetime.now().isoformat()
        notebook = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "color": color,
            "icon": icon,
            "records": [],
            "created_at": now,
            "updated_at": now,
        }
        self._save(notebook)
        return notebook

    def get_notebook(self, notebook_id: str) -> dict | None:
        nb = self._load(notebook_id)
        if nb:
            nb["note_count"] = self._count_notes(notebook_id)
        return nb

    def update_notebook(self, notebook_id: str, **kwargs) -> dict | None:
        nb = self._load(notebook_id)
        if not nb:
            return None
        for key in ("name", "description", "color", "icon"):
            if kwargs.get(key) is not None:
                nb[key] = kwargs[key]
        nb["updated_at"] = datetime.now().isoformat()
        self._save(nb)
        return nb

    def delete_notebook(self, notebook_id: str) -> bool:
        path = self._get_path(notebook_id)
        deleted = False
        if path.exists():
            path.unlink()
            deleted = True
        # Also remove notes directory
        notes_parent = self.notebooks_dir / notebook_id
        if notes_parent.exists():
            shutil.rmtree(notes_parent)
            deleted = True
        return deleted

    # ================================================================== #
    #  Legacy records (kept for backward compatibility)                    #
    # ================================================================== #

    def add_record(
        self,
        notebook_ids: list[str],
        record_type: str,
        title: str,
        user_query: str,
        output: str,
        metadata: dict | None = None,
        kb_name: str | None = None,
    ) -> dict:
        """Add a record to one or more notebooks."""
        record = {
            "id": str(uuid.uuid4()),
            "type": record_type,
            "title": title,
            "user_query": user_query,
            "output": output,
            "metadata": metadata or {},
            "kb_name": kb_name,
            "created_at": datetime.now().isoformat(),
        }

        added_to = []
        for nb_id in notebook_ids:
            nb = self._load(nb_id)
            if nb:
                nb.setdefault("records", []).append(record)
                nb["updated_at"] = datetime.now().isoformat()
                self._save(nb)
                added_to.append(nb_id)

        return {"record": record, "added_to_notebooks": added_to}

    def remove_record(self, notebook_id: str, record_id: str) -> bool:
        nb = self._load(notebook_id)
        if not nb:
            return False
        original = len(nb.get("records", []))
        nb["records"] = [r for r in nb.get("records", []) if r["id"] != record_id]
        if len(nb["records"]) < original:
            nb["updated_at"] = datetime.now().isoformat()
            self._save(nb)
            return True
        return False

    # ================================================================== #
    #  Note CRUD (new)                                                     #
    # ================================================================== #

    def create_note(
        self,
        notebook_id: str,
        title: str,
        content: str = "",
        tags: list[str] | None = None,
        source: dict | None = None,
    ) -> dict | None:
        """Create a new note inside a notebook.

        Returns the created note dict, or None if notebook doesn't exist.
        """
        nb = self._load(notebook_id)
        if not nb:
            return None

        now = datetime.now().isoformat()
        note = {
            "id": str(uuid.uuid4()),
            "notebook_id": notebook_id,
            "title": title,
            "content": content,
            "tags": tags or [],
            "source": source or {"type": "manual"},
            "created_at": now,
            "updated_at": now,
        }
        self._save_note(notebook_id, note)

        # Touch notebook updated_at
        nb["updated_at"] = now
        self._save(nb)

        return note

    def get_note(self, notebook_id: str, note_id: str) -> dict | None:
        """Get a single note, merged with its AI meta if available."""
        note = self._load_note(notebook_id, note_id)
        if not note:
            return None
        # Merge AI meta
        meta = self.get_note_meta(notebook_id, note_id)
        if meta:
            note["ai_meta"] = meta
        return note

    def update_note(
        self,
        notebook_id: str,
        note_id: str,
        expected_updated_at: str | None = None,
        **kwargs,
    ) -> dict | str:
        """Update a note's fields.

        Supports optimistic locking: if *expected_updated_at* is provided and
        does not match the note's current updated_at, returns the string
        ``"conflict"`` instead of the updated note dict.

        Updatable fields: title, content, tags, source.
        """
        note = self._load_note(notebook_id, note_id)
        if not note:
            return "not_found"

        # Optimistic lock check
        if expected_updated_at and note["updated_at"] != expected_updated_at:
            return "conflict"

        for key in ("title", "content", "tags", "source"):
            if key in kwargs and kwargs[key] is not None:
                note[key] = kwargs[key]
        note["updated_at"] = datetime.now().isoformat()
        self._save_note(notebook_id, note)

        # Touch notebook updated_at
        nb = self._load(notebook_id)
        if nb:
            nb["updated_at"] = note["updated_at"]
            self._save(nb)

        return note

    def delete_note(self, notebook_id: str, note_id: str) -> bool:
        """Delete a note and its AI meta file."""
        path = self._note_path(notebook_id, note_id)
        deleted = False
        if path.exists():
            path.unlink()
            deleted = True
        meta_path = self._note_meta_path(notebook_id, note_id)
        if meta_path.exists():
            meta_path.unlink()
        if deleted:
            nb = self._load(notebook_id)
            if nb:
                nb["updated_at"] = datetime.now().isoformat()
                self._save(nb)
        return deleted

    def list_notes(
        self,
        notebook_id: str,
        search: str | None = None,
        tag: str | None = None,
    ) -> list[dict]:
        """List notes in a notebook, optionally filtered by search or tag.

        Returns summary dicts (without full content) sorted by updated_at desc.
        """
        d = self.notebooks_dir / notebook_id / "notes"
        if not d.exists():
            return []

        notes = []
        for p in d.glob("*.json"):
            if p.name.startswith("meta_"):
                continue
            try:
                with open(p, "r", encoding="utf-8") as f:
                    note = json.load(f)
                # Tag filter
                if tag and tag not in note.get("tags", []):
                    continue
                meta = self._load_note_meta(notebook_id, note.get("id", ""))
                ai_summary = ""
                ai_summary_updated_at = ""
                if meta and isinstance(meta.get("summary"), str):
                    ai_summary = meta.get("summary", "").strip()
                    ai_summary_updated_at = str(meta.get("updated_at", "") or "")
                # Search filter (title + content)
                if search:
                    search_lower = search.lower()
                    title_match = search_lower in note.get("title", "").lower()
                    content_match = search_lower in note.get("content", "").lower()
                    summary_match = search_lower in ai_summary.lower()
                    if not (title_match or content_match or summary_match):
                        continue
                notes.append({
                    "id": note["id"],
                    "notebook_id": notebook_id,
                    "title": note.get("title", "Untitled"),
                    "tags": note.get("tags", []),
                    "source": note.get("source", {}),
                    "content_preview": note.get("content", "")[:120],
                    "ai_summary": ai_summary[:240],
                    "has_ai_summary": bool(ai_summary),
                    "ai_summary_updated_at": ai_summary_updated_at,
                    "created_at": note.get("created_at"),
                    "updated_at": note.get("updated_at"),
                })
            except Exception:
                continue

        notes.sort(key=lambda n: n.get("updated_at", ""), reverse=True)
        return notes

    def list_related_notes(
        self,
        notebook_id: str,
        note_id: str,
        limit: int = 5,
        include_all_notebooks: bool = False,
        min_score: float = 0.0,
    ) -> list[dict]:
        """Find related notes using lightweight scoring.

        By default, search only in the same notebook. When
        ``include_all_notebooks=True``, search across all notebooks.
        """
        base_note = self._load_note(notebook_id, note_id)
        if not base_note:
            return []

        notebook_names: dict[str, str] = {}
        for nb_path in self.notebooks_dir.glob("*.json"):
            try:
                with open(nb_path, "r", encoding="utf-8") as f:
                    nb = json.load(f)
                notebook_names[nb["id"]] = nb.get("name", "未命名笔记本")
            except Exception:
                continue

        base_tags = set(base_note.get("tags", []))
        base_source = base_note.get("source", {}) or {}
        base_source_type = base_source.get("type", "manual")
        base_file = (base_source.get("file_name") or "").lower()
        base_tokens = self._tokenize(
            f'{base_note.get("title", "")}\n{(base_note.get("content", "") or "")[:2000]}'
        )

        candidate_notebook_ids = (
            list(notebook_names.keys())
            if include_all_notebooks
            else [notebook_id]
        )

        scored: list[dict] = []
        for candidate_nb_id in candidate_notebook_ids:
            notes_dir = self.notebooks_dir / candidate_nb_id / "notes"
            if not notes_dir.exists():
                continue

            for p in notes_dir.glob("*.json"):
                if p.name.startswith("meta_"):
                    continue
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        note = json.load(f)
                except Exception:
                    continue

                if candidate_nb_id == notebook_id and note.get("id") == note_id:
                    continue

                tags = set(note.get("tags", []))
                source = note.get("source", {}) or {}
                source_type = source.get("type", "manual")
                source_file = (source.get("file_name") or "").lower()
                tokens = self._tokenize(
                    f'{note.get("title", "")}\n{(note.get("content", "") or "")[:1600]}'
                )

                shared_tag_count = len(base_tags & tags)
                shared_token_count = len(base_tokens & tokens)

                score = 0.0
                score += shared_tag_count * 3.0
                score += min(shared_token_count, 10) * 0.4
                if source_type == base_source_type:
                    score += 1.2
                if base_file and source_file and base_file == source_file:
                    score += 2.5
                if candidate_nb_id == notebook_id:
                    score += 0.8

                if score <= 0 or score < min_score:
                    continue

                scored.append(
                    {
                        "id": note.get("id"),
                        "notebook_id": candidate_nb_id,
                        "notebook_name": notebook_names.get(candidate_nb_id, "未命名笔记本"),
                        "title": note.get("title", "Untitled"),
                        "tags": note.get("tags", []),
                        "source": source,
                        "content_preview": (note.get("content", "") or "")[:120],
                        "created_at": note.get("created_at"),
                        "updated_at": note.get("updated_at"),
                        "score": round(score, 2),
                    }
                )

        scored.sort(key=lambda n: (n.get("score", 0), n.get("updated_at", "")), reverse=True)
        return scored[: max(1, min(limit, 20))]

    # ================================================================== #
    #  AI Metadata (separate file to avoid write conflicts)                #
    # ================================================================== #

    def get_note_meta(self, notebook_id: str, note_id: str) -> dict | None:
        """Read AI-generated metadata for a note."""
        return self._load_note_meta(notebook_id, note_id)

    def update_note_meta(
        self, notebook_id: str, note_id: str, **kwargs
    ) -> dict | None:
        """Update AI metadata (summary, suggested_tags, etc.).

        This writes to ``meta_{note_id}.json``, fully isolated from the
        user-editable note file to prevent write conflicts.
        """
        # Ensure the note itself exists
        if not self._note_path(notebook_id, note_id).exists():
            return None
        path = self._note_meta_path(notebook_id, note_id, ensure_parent=True)
        meta: dict = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        for key in ("summary", "suggested_tags", "related_notes"):
            if key in kwargs and kwargs[key] is not None:
                meta[key] = kwargs[key]
        meta["updated_at"] = datetime.now().isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta

    # ================================================================== #
    #  Statistics                                                          #
    # ================================================================== #

    def get_statistics(self) -> dict:
        """Get notebook statistics."""
        notebooks = self.list_notebooks()
        total_records = sum(n.get("record_count", 0) for n in notebooks)
        total_notes = sum(n.get("note_count", 0) for n in notebooks)
        return {
            "total_notebooks": len(notebooks),
            "total_records": total_records,
            "total_notes": total_notes,
        }


# Singleton
_notebook_manager: NotebookManager | None = None


def get_notebook_manager() -> NotebookManager:
    global _notebook_manager
    if _notebook_manager is None:
        _notebook_manager = NotebookManager()
    return _notebook_manager
