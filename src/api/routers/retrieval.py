# -*- coding: utf-8 -*-
"""Hybrid retrieval API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.retrieval import HybridRetrievalService
from src.shared_capabilities.knowledge import get_kb_manager, get_vector_store


router = APIRouter()


class HybridRequest(BaseModel):
    query: str
    kb_id: str
    top_k: int = Field(default=8, ge=1, le=30)


@router.post("/retrieval/hybrid")
async def hybrid_retrieval(req: HybridRequest):
    kb_manager = get_kb_manager()
    kb = kb_manager.get_kb(req.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"KB not found: {req.kb_id}")

    vector_store = get_vector_store(req.kb_id)
    if vector_store is None:
        raise HTTPException(status_code=404, detail=f"KB not found: {req.kb_id}")

    service = HybridRetrievalService()
    result = service.retrieve(kb_id=req.kb_id, vector_store=vector_store, query=req.query, top_k=req.top_k)
    return {"success": True, "data": result}
