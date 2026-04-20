from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.knowledge.kb_manager import KnowledgeBaseManager
    from src.knowledge.vector_store import VectorStore


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"


def _coerce_data_dir(data_dir: Path | str | None = None) -> Path:
    return Path(data_dir) if data_dir is not None else DATA_DIR


def get_kb_manager(data_dir: Path | str | None = None) -> KnowledgeBaseManager:
    from src.knowledge.kb_manager import KnowledgeBaseManager

    return KnowledgeBaseManager(_coerce_data_dir(data_dir) / "knowledge_bases")


def get_vector_store(kb_id: str, data_dir: Path | str | None = None) -> VectorStore | None:
    from src.knowledge.vector_store import VectorStore

    kb_manager = get_kb_manager(data_dir)
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        return None
    return VectorStore(
        persist_dir=str(kb_manager.get_vector_store_path(kb_id)),
        collection_name=kb["collection_name"],
        embedding_model=kb.get("embedding_model", "sentence-transformers/all-mpnet-base-v2"),
        embedding_provider=kb.get("embedding_provider", "sentence-transformers"),
    )
