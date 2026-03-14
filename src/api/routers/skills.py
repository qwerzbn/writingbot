# -*- coding: utf-8 -*-
"""Skill listing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from src.skills import list_skills


router = APIRouter()


@router.get("/skills")
async def get_skills(
    domain: str = Query(default="research"),
    enabled_only: bool = Query(default=True),
):
    return {"success": True, "data": list_skills(domain=domain, enabled_only=enabled_only)}
