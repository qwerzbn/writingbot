from __future__ import annotations

from threading import RLock
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.knowledge.kb_manager import KnowledgeBaseManager
    from src.knowledge.vector_store import VectorStore


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
_VECTOR_STORE_CACHE: dict[tuple[str, str, str, str, str], Any] = {}
_VECTOR_STORE_CACHE_LOCK = RLock()


def _coerce_data_dir(data_dir: Path | str | None = None) -> Path:
    return Path(data_dir) if data_dir is not None else DATA_DIR


def get_kb_manager(data_dir: Path | str | None = None) -> KnowledgeBaseManager:
    from src.knowledge.kb_manager import KnowledgeBaseManager

    return KnowledgeBaseManager(_coerce_data_dir(data_dir) / "knowledge_bases")


def get_vector_store(kb_id: str, data_dir: Path | str | None = None) -> VectorStore | None:
    from src.knowledge.vector_store import VectorStore

    root = _coerce_data_dir(data_dir)
    kb_manager = get_kb_manager(root)
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        return None
    persist_dir = str(kb_manager.get_vector_store_path(kb_id))
    collection_name = kb["collection_name"]
    embedding_model = kb.get("embedding_model", "BAAI/bge-m3")
    embedding_provider = kb.get("embedding_provider", "sentence-transformers")
    cache_key = (
        str(root.resolve()),
        kb_id,
        collection_name,
        embedding_model,
        embedding_provider,
    )
    with _VECTOR_STORE_CACHE_LOCK:
        cached = _VECTOR_STORE_CACHE.get(cache_key)
        if cached is not None:
            return cached
        vector_store = VectorStore(
            persist_dir=persist_dir,
            collection_name=collection_name,
            embedding_model=embedding_model,
            embedding_provider=embedding_provider,
        )
        _VECTOR_STORE_CACHE[cache_key] = vector_store
        return vector_store


def clear_vector_store_cache() -> None:
    with _VECTOR_STORE_CACHE_LOCK:
        _VECTOR_STORE_CACHE.clear()
