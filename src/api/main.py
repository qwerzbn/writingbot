# -*- coding: utf-8 -*-
"""
WritingBot FastAPI Application
================================

FastAPI-based REST API for the WritingBot RAG system.
Replaces the Flask-based server.py.
"""

import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is in Python path
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.routers import (
    chat,
    knowledge,
    notebook,
    research,
    co_writer,
    settings,
    orchestrator,
    retrieval,
    evaluation,
    fastwrite_bridge,
    skills,
)
from src.services.config import get_main_config
from src.skills import get_skills_registry_report, warmup_skills_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    config = get_main_config()
    print(f"\n{'='*60}")
    print(f"  WritingBot API Server (FastAPI)")
    print(f"  Backend: http://localhost:{config.get('server', {}).get('port', 5001)}")
    print(f"  Frontend: http://localhost:3000 (run: npm run dev)")
    print(f"{'='*60}\n")

    # Initialize LLM client early
    try:
        from src.services.llm import get_llm_client, get_llm_config
        llm_config = get_llm_config()
        print(f"  LLM: {llm_config.provider} / {llm_config.model}")
        print(f"  Base URL: {llm_config.base_url}")
        print(f"  LLM Enabled: {llm_config.is_enabled}")
    except Exception as e:
        print(f"  Warning: LLM init failed: {e}")

    try:
        skills_report = warmup_skills_registry()
        print(
            "  Skills: loaded=%s rejected=%s fallback=%s"
            % (
                skills_report.get("loaded", 0),
                len(skills_report.get("rejected", [])),
                skills_report.get("used_legacy_fallback", False),
            )
        )
    except Exception as e:
        print(f"  Warning: skills warmup failed: {e}")

    yield
    print("Application shutdown")


app = FastAPI(
    title="WritingBot API",
    version="2.0.0",
    description="WritingBot RAG system - FastAPI backend",
    lifespan=lifespan,
    redirect_slashes=False,
)

# Configure CORS
cors_origins = [
    item.strip()
    for item in os.getenv(
        "WRITINGBOT_CORS_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:3005",
    ).split(",")
    if item.strip()
]
allow_credentials = os.getenv("WRITINGBOT_CORS_ALLOW_CREDENTIALS", "true").lower() in {
    "1",
    "true",
    "yes",
}
if "*" in cors_origins and allow_credentials:
    allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["http://127.0.0.1:3000"],
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(knowledge.router, prefix="/api", tags=["knowledge"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(notebook.router, prefix="/api", tags=["notebook"])
app.include_router(research.router, prefix="/api", tags=["research"])
app.include_router(co_writer.router, prefix="/api", tags=["co-writer"])
app.include_router(settings.router, prefix="/api", tags=["settings"])
app.include_router(orchestrator.router, prefix="/api", tags=["orchestrator"])
app.include_router(retrieval.router, prefix="/api", tags=["retrieval"])
app.include_router(evaluation.router, prefix="/api", tags=["evaluation"])
app.include_router(fastwrite_bridge.router, prefix="/api", tags=["fastwrite"])
app.include_router(skills.router, prefix="/api", tags=["skills"])


@app.get("/")
async def root():
    return {"message": "Welcome to WritingBot API (FastAPI)"}


@app.get("/api/health")
async def health():
    skills_report = get_skills_registry_report()
    return {
        "success": True,
        "data": {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "skills": {
                "loaded": skills_report.get("loaded", 0),
                "rejected_count": len(skills_report.get("rejected", [])),
                "used_legacy_fallback": skills_report.get("used_legacy_fallback", False),
            },
        },
    }


if __name__ == "__main__":
    import uvicorn

    config = get_main_config()
    server_config = config.get("server", {})

    uvicorn.run(
        "src.api.main:app",
        host=server_config.get("host", "0.0.0.0"),
        port=server_config.get("port", 5001),
        reload=True,
        reload_excludes=[
            str(PROJECT_ROOT / "data"),
            str(PROJECT_ROOT / "web"),
            str(PROJECT_ROOT / ".git"),
        ],
    )
