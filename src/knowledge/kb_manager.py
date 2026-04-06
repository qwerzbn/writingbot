# -*- coding: utf-8 -*-
"""
Knowledge Base Manager (Enterprise)
====================================

Manages multiple knowledge bases with:
- Directory-based isolation per KB
- Cross-platform file locking for concurrency safety
- Robust configuration management

Based on DeepTutor's architecture.
"""

import json
import os
import sys
import uuid
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ==============================================================================
# Cross-platform File Locking
# ==============================================================================

@contextmanager
def file_lock_shared(file_handle):
    """Acquire a shared (read) lock on a file - cross-platform."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            file_handle.seek(0)
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def file_lock_exclusive(file_handle):
    """Acquire an exclusive (write) lock on a file - cross-platform."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            file_handle.seek(0)
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


# ==============================================================================
# Knowledge Base Manager
# ==============================================================================

class KnowledgeBaseManager:
    """
    Manages knowledge bases with directory-based isolation.
    
    Structure:
        base_dir/
        ├── kb_config.json       # Global KB registry
        ├── <kb_id>/
        │   ├── metadata.json    # KB-specific config
        │   ├── raw/             # Original documents
        │   └── vector_store/    # ChromaDB files
        └── ...
    """
    
    def __init__(self, base_dir: str | Path = "./data/knowledge_bases"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.base_dir / "kb_config.json"
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load global KB configuration with shared lock."""
        if not self.config_file.exists():
            return {"knowledge_bases": {}}
        
        try:
            with open(self.config_file, encoding="utf-8") as f:
                with file_lock_shared(f):
                    content = f.read()
                    if not content.strip():
                        return {"knowledge_bases": {}}
                    return json.loads(content)
        except (json.JSONDecodeError, Exception) as e:
            print(f"[KBManager] Error loading config: {e}")
            return {"knowledge_bases": {}}
    
    def _save_config(self):
        """Save global KB configuration with exclusive lock."""
        with open(self.config_file, "w", encoding="utf-8") as f:
            with file_lock_exclusive(f):
                json.dump(self.config, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
    
    def create_kb(
        self,
        name: str,
        embedding_model: str = "sentence-transformers/all-mpnet-base-v2",
        embedding_provider: str = "sentence-transformers",
        description: str = ""
    ) -> dict:
        """Create a new knowledge base with its own directory."""
        kb_id = str(uuid.uuid4())
        kb_dir = self.base_dir / kb_id
        
        # Create directory structure
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "raw").mkdir(exist_ok=True)
        (kb_dir / "vector_store").mkdir(exist_ok=True)
        
        now = datetime.now().isoformat()
        
        # KB metadata (stored in KB's own directory)
        metadata = {
            "id": kb_id,
            "name": name,
            "description": description,
            "embedding_model": embedding_model,
            "embedding_provider": embedding_provider,
            "collection_name": f"kb_{kb_id.replace('-', '_')}",
            "created_at": now,
            "updated_at": now,
            "files": [],
            "status": "ready"
        }
        
        # Save KB metadata
        with open(kb_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # Register in global config
        self.config = self._load_config()  # Reload to get latest
        self.config["knowledge_bases"][kb_id] = {
            "name": name,
            "path": kb_id,
            "created_at": now
        }
        self._save_config()
        
        return metadata
    
    def delete_kb(self, kb_id: str) -> bool:
        """Delete a knowledge base and its directory."""
        kb_dir = self.base_dir / kb_id
        
        if not kb_dir.exists():
            return False
        
        # Delete directory
        shutil.rmtree(kb_dir)
        
        # Remove from config
        self.config = self._load_config()
        if kb_id in self.config.get("knowledge_bases", {}):
            del self.config["knowledge_bases"][kb_id]
            self._save_config()
        
        return True
    
    def get_kb(self, kb_id: str) -> Optional[dict]:
        """Get KB metadata from its directory."""
        metadata_file = self.base_dir / kb_id / "metadata.json"
        
        if not metadata_file.exists():
            return None
        
        try:
            with open(metadata_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    
    def list_kbs(self) -> list[dict]:
        """List all knowledge bases."""
        self.config = self._load_config()
        result = []
        
        for kb_id in self.config.get("knowledge_bases", {}).keys():
            metadata = self.get_kb(kb_id)
            if metadata:
                result.append(metadata)
        
        return sorted(result, key=lambda x: x.get("created_at", ""), reverse=True)
    
    def add_file(self, kb_id: str, file_info: dict):
        """Add a file record to KB metadata."""
        metadata_file = self.base_dir / kb_id / "metadata.json"
        
        if not metadata_file.exists():
            raise ValueError(f"KB not found: {kb_id}")
        
        with open(metadata_file, encoding="utf-8") as f:
            metadata = json.load(f)
        
        metadata["files"].append(file_info)
        metadata["updated_at"] = datetime.now().isoformat()
        
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    def remove_file(self, kb_id: str, file_id: str) -> dict[str, Any] | None:
        """Remove a file record from KB metadata and return the removed row."""
        metadata_file = self.base_dir / kb_id / "metadata.json"
        
        if not metadata_file.exists():
            return None
        
        with open(metadata_file, encoding="utf-8") as f:
            metadata = json.load(f)

        removed: dict[str, Any] | None = None
        remaining: list[dict[str, Any]] = []
        for row in metadata.get("files", []):
            if str(row.get("id")) == str(file_id):
                removed = row
                continue
            remaining.append(row)

        metadata["files"] = remaining
        metadata["updated_at"] = datetime.now().isoformat()
        
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        return removed
    
    def get_kb_path(self, kb_id: str) -> Path:
        """Get the directory path for a KB."""
        return self.base_dir / kb_id
    
    def get_vector_store_path(self, kb_id: str) -> Path:
        """Get the vector store path for a KB."""
        return self.base_dir / kb_id / "vector_store"
    
    def get_raw_path(self, kb_id: str) -> Path:
        """Get the raw documents path for a KB."""
        return self.base_dir / kb_id / "raw"
