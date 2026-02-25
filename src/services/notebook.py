# -*- coding: utf-8 -*-
"""
Notebook Service
=================

Manages notebooks and records (CRUD + JSON storage).
"""

import json
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

    def list_notebooks(self) -> list[dict]:
        """List all notebooks with summary info."""
        notebooks = []
        for p in sorted(self.notebooks_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    nb = json.load(f)
                notebooks.append({
                    "id": nb["id"],
                    "name": nb["name"],
                    "description": nb.get("description", ""),
                    "color": nb.get("color", "#3B82F6"),
                    "icon": nb.get("icon", "book"),
                    "record_count": len(nb.get("records", [])),
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
        return self._load(notebook_id)

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
        if path.exists():
            path.unlink()
            return True
        return False

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

    def get_statistics(self) -> dict:
        """Get notebook statistics."""
        notebooks = self.list_notebooks()
        total_records = sum(n.get("record_count", 0) for n in notebooks)
        return {
            "total_notebooks": len(notebooks),
            "total_records": total_records,
        }


# Singleton
_notebook_manager: NotebookManager | None = None


def get_notebook_manager() -> NotebookManager:
    global _notebook_manager
    if _notebook_manager is None:
        _notebook_manager = NotebookManager()
    return _notebook_manager
