# -*- coding: utf-8 -*-
"""
WritingBot FastAPI Application
================================

FastAPI-based REST API for the WritingBot RAG system.
Replaces the Flask-based server.py.
"""

import sys
from contextlib import asynccontextmanager
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
