# -*- coding: utf-8 -*-
"""
Notebook API Router
====================

CRUD for notebooks and records.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.services.notebook import get_notebook_manager

router = APIRouter()


class CreateNotebookRequest(BaseModel):
    name: str
    description: str = ""
    color: str = "#3B82F6"
    icon: str = "book"


class UpdateNotebookRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class AddRecordRequest(BaseModel):
    notebook_ids: list[str]
    record_type: Literal["chat", "research", "co_writer"]
    title: str
    user_query: str
    output: str
    metadata: dict = {}
    kb_name: str | None = None


@router.get("/notebooks")
async def list_notebooks():
    return {"success": True, "data": get_notebook_manager().list_notebooks()}


@router.post("/notebooks")
async def create_notebook(req: CreateNotebookRequest):
    nb = get_notebook_manager().create_notebook(
        name=req.name, description=req.description, color=req.color, icon=req.icon
    )
    return {"success": True, "data": nb}


@router.get("/notebooks/{notebook_id}")
async def get_notebook(notebook_id: str):
    nb = get_notebook_manager().get_notebook(notebook_id)
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"success": True, "data": nb}


@router.put("/notebooks/{notebook_id}")
async def update_notebook(notebook_id: str, req: UpdateNotebookRequest):
    nb = get_notebook_manager().update_notebook(
        notebook_id, name=req.name, description=req.description, color=req.color, icon=req.icon
    )
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"success": True, "data": nb}


@router.delete("/notebooks/{notebook_id}")
async def delete_notebook(notebook_id: str):
    if not get_notebook_manager().delete_notebook(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"success": True}


@router.post("/notebooks/records")
async def add_record(req: AddRecordRequest):
    result = get_notebook_manager().add_record(
        notebook_ids=req.notebook_ids,
        record_type=req.record_type,
        title=req.title,
        user_query=req.user_query,
        output=req.output,
        metadata=req.metadata,
        kb_name=req.kb_name,
    )
    return {"success": True, "data": result}


@router.delete("/notebooks/{notebook_id}/records/{record_id}")
async def remove_record(notebook_id: str, record_id: str):
    if not get_notebook_manager().remove_record(notebook_id, record_id):
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True}


@router.get("/notebooks/stats/overview")
async def get_statistics():
    return {"success": True, "data": get_notebook_manager().get_statistics()}
