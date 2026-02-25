# -*- coding: utf-8 -*-
"""
Knowledge Base API Router
==========================

Handles knowledge base CRUD operations and file uploads.
Migrated from Flask server.py to FastAPI.
"""

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

# Project root for data directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Lazy-loaded managers
_kb_manager = None
_parser = None

router = APIRouter()


def get_kb_manager():
    """Get KnowledgeBaseManager instance (lazy init)."""
    global _kb_manager
    if _kb_manager is None:
        from src.knowledge.kb_manager import KnowledgeBaseManager
        _kb_manager = KnowledgeBaseManager(DATA_DIR / "knowledge_bases")
    return _kb_manager


def get_parser():
    """Get PDFParser instance (lazy init)."""
    global _parser
    if _parser is None:
        from src.parsing.pdf_parser import PDFParser
        _parser = PDFParser()
    return _parser


def get_vector_store(kb_id: str):
    """Get VectorStore for a specific KB."""
    from src.knowledge.vector_store import VectorStore

    kb_manager = get_kb_manager()
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"KB not found: {kb_id}")

    vector_path = kb_manager.get_vector_store_path(kb_id)
    embedding_provider = kb.get("embedding_provider", "sentence-transformers")
    embedding_model = kb.get("embedding_model", "sentence-transformers/all-mpnet-base-v2")

    return VectorStore(
        persist_dir=str(vector_path),
        collection_name=kb["collection_name"],
        embedding_model=embedding_model,
        embedding_provider=embedding_provider,
    )


# ============== Knowledge Base CRUD ==============


@router.get("/kbs")
async def list_kbs():
    """List all knowledge bases."""
    return {"success": True, "data": get_kb_manager().list_kbs()}


@router.post("/kbs")
async def create_kb(request: Request):
    """Create a new knowledge base."""
    data = await request.json()
    name = data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    description = data.get("description", "")
    embedding_provider = data.get("embedding_provider", "sentence-transformers")
    embedding_model = data.get("embedding_model")

    # Defaults based on provider
    if not embedding_model:
        if embedding_provider == "ollama":
            embedding_model = "nomic-embed-text:latest"
        elif embedding_provider == "openai":
            embedding_model = "text-embedding-3-small"
        else:
            embedding_model = "sentence-transformers/all-mpnet-base-v2"

    kb = get_kb_manager().create_kb(name, embedding_model, embedding_provider, description)
    return {"success": True, "data": kb}


@router.delete("/kbs/{kb_id}")
async def delete_kb(kb_id: str):
    """Delete a knowledge base."""
    if get_kb_manager().delete_kb(kb_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="KB not found")


@router.get("/kbs/{kb_id}")
async def get_kb_details(kb_id: str):
    """Get knowledge base details."""
    kb_manager = get_kb_manager()
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="KB not found")

    try:
        vs = get_vector_store(kb_id)
        stats = vs.get_stats()
        return {"success": True, "data": {"metadata": kb, "stats": stats}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/kbs/{kb_id}/ingest")
async def ingest_file(
    kb_id: str,
    file: UploadFile = File(...),
    chunk_size: int = Form(1000),
    chunk_overlap: int = Form(200),
):
    """Upload and ingest a file into a knowledge base."""
    kb_manager = get_kb_manager()
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="KB not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        from src.processing.semantic_chunker import SemanticChunker

        file_id = str(uuid.uuid4())
        filename = file.filename

        # Save to KB's raw directory
        raw_dir = kb_manager.get_raw_path(kb_id)
        raw_dir.mkdir(parents=True, exist_ok=True)
        filepath = raw_dir / f"{file_id}_{filename}"

        # Read file content and save
        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)

        # Parse PDF
        parser = get_parser()
        content_list = parser.parse(str(filepath))

        # Chunk content
        chunker = SemanticChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunks = chunker.chunk_content_list(content_list)

        # Add metadata to chunks
        for chunk in chunks:
            if chunk.metadata:
                chunk.metadata["source"] = filename
                chunk.metadata["file_id"] = file_id

        # Index in vector store
        vs = get_vector_store(kb_id)
        chunk_dicts = [c.to_dict() for c in chunks]
        vs.add_chunks(chunk_dicts)

        # Record file info
        file_info = {
            "id": file_id,
            "name": filename,
            "path": str(filepath),
            "size": filepath.stat().st_size,
            "uploaded_at": datetime.now().isoformat(),
            "blocks": len(content_list),
            "chunks": len(chunks),
        }
        kb_manager.add_file(kb_id, file_info)

        return {"success": True, "data": file_info}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/kbs/{kb_id}/files/{file_id}")
async def delete_file(kb_id: str, file_id: str):
    """Delete a file from a knowledge base."""
    kb_manager = get_kb_manager()
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="KB not found")

    kb_manager.remove_file(kb_id, file_id)
    return {"success": True}
