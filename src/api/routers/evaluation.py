# -*- coding: utf-8 -*-
"""Offline evaluation APIs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.evaluation.service import get_evaluation_service


router = APIRouter()


@router.post("/evaluation/run")
async def run_evaluation():
    service = get_evaluation_service()
    job = service.create_job()
    service.run_async(job.id)
    return {"success": True, "data": {"id": job.id, "status": job.status, "created_at": job.created_at}}


@router.get("/evaluation/report/latest")
async def get_latest_report():
    service = get_evaluation_service()
    report = service.latest_report_summary()
    if report is None:
        raise HTTPException(status_code=404, detail="No evaluation reports found")
    return {"success": True, "data": report}


@router.get("/evaluation/report/{job_id}")
async def get_report(job_id: str):
    service = get_evaluation_service()
    report = service.load_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report not found: {job_id}")
    return {"success": True, "data": report}


@router.get("/evaluation/reports")
async def list_reports(limit: int = 10):
    service = get_evaluation_service()
    return {"success": True, "data": service.list_reports(limit=limit)}
