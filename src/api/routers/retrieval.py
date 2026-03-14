# -*- coding: utf-8 -*-
"""Hybrid retrieval API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.knowledge.kb_manager import KnowledgeBaseManager
from src.knowledge.vector_store import VectorStore
from src.retrieval import HybridRetrievalService


router = APIRouter()
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class HybridRequest(BaseModel):
    query: str
    kb_id: str
    top_k: int = Field(default=8, ge=1, le=30)


@router.post("/retrieval/hybrid")
async def hybrid_retrieval(req: HybridRequest):
    kb_manager = KnowledgeBaseManager(DATA_DIR / "knowledge_bases")
    kb = kb_manager.get_kb(req.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"KB not found: {req.kb_id}")

    vector_store = VectorStore(
        persist_dir=str(kb_manager.get_vector_store_path(req.kb_id)),
        collection_name=kb["collection_name"],
        embedding_model=kb.get("embedding_model", "sentence-transformers/all-mpnet-base-v2"),
        embedding_provider=kb.get("embedding_provider", "sentence-transformers"),
    )

    service = HybridRetrievalService()
    result = service.retrieve(kb_id=req.kb_id, vector_store=vector_store, query=req.query, top_k=req.top_k)
    return {"success": True, "data": result}
