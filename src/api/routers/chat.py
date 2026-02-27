# -*- coding: utf-8 -*-
"""
Chat API Router
================

Multi-agent chat with SSE streaming and agent collaboration workflow.

SSE Event Protocol:
- agent_step: {"type":"agent_step", "agent":"retriever", "status":"working|done", "message":"...", "duration":1.2}
- chunk:      {"type":"chunk", "content":"...", "agent":"reasoner"}
- sources:    {"type":"sources", "data":[...]}
- done:       {"type":"done", "conversation_id":"..."}
- error:      {"type":"error", "error":"..."}
"""

import json
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.agents.registry import get_all_agents, AGENT_REGISTRY

# Project root for data directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Lazy-loaded instances
_session_manager = None
_chat_agent = None

router = APIRouter()


def get_session_manager():
    global _session_manager
    if _session_manager is None:
        from src.session.manager import SessionManager
        _session_manager = SessionManager(DATA_DIR / "sessions")
    return _session_manager


def get_chat_agent():
    global _chat_agent
    if _chat_agent is None:
        from src.agents.chat import ChatAgent
        _chat_agent = ChatAgent()
    return _chat_agent


def get_vector_store(kb_id: str):
    from src.knowledge.kb_manager import KnowledgeBaseManager
    from src.knowledge.vector_store import VectorStore

    kb_manager = KnowledgeBaseManager(DATA_DIR / "knowledge_bases")
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=400, detail=f"KB not found: {kb_id}")

    vector_path = kb_manager.get_vector_store_path(kb_id)
    embedding_provider = kb.get("embedding_provider", "sentence-transformers")
    embedding_model = kb.get("embedding_model", "sentence-transformers/all-mpnet-base-v2")

    return VectorStore(
        persist_dir=str(vector_path),
        collection_name=kb["collection_name"],
        embedding_model=embedding_model,
        embedding_provider=embedding_provider,
    )


def _get_or_create_session(sm, conv_id, message, kb_id):
    if conv_id:
        session = sm.get(conv_id)
        if not session:
            session = sm.get_or_create(
                conv_id,
                title=message[:30] + "..." if len(message) > 30 else message,
                kb_id=kb_id,
            )
        if not kb_id:
            kb_id = session.metadata.get("kb_id")
    else:
        conv_id = str(uuid.uuid4())
        session = sm.get_or_create(
            conv_id,
            title=message[:30] + "..." if len(message) > 30 else message,
            kb_id=kb_id,
        )
    return session, conv_id, kb_id


def _sse(data: dict) -> str:
    """Format a dict as an SSE data event."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_at_mention(message: str) -> tuple[str | None, str]:
    """
    Parse @agent mention from message.
    Returns (agent_id, clean_message).
    """
    match = re.match(r"@(\S+)\s*(.*)", message, re.DOTALL)
    if match:
        mention = match.group(1)
        clean_msg = match.group(2).strip()
        # Try to match by ID or name
        for agent_id, info in AGENT_REGISTRY.items():
            if mention in (agent_id, info.name):
                return agent_id, clean_msg
    return None, message


# ============== API Endpoints ==============


@router.get("/agents")
async def list_agents():
    """List all available agents with their metadata."""
    return {"success": True, "data": get_all_agents()}


@router.post("/chat")
async def chat(request: Request):
    """Non-streaming chat endpoint."""
    try:
        data = await request.json()
        if not data or "message" not in data:
            raise HTTPException(status_code=400, detail="No message provided")

        message = data["message"]
        conv_id = data.get("conversation_id")
        kb_id = data.get("kb_id")

        sm = get_session_manager()
        session, conv_id, kb_id = _get_or_create_session(sm, conv_id, message, kb_id)

        if not kb_id:
            raise HTTPException(status_code=400, detail="No Knowledge Base selected")

        session.add_message("user", message)

        agent = get_chat_agent()
        vs = get_vector_store(kb_id)
        history = session.get_history()
        result = agent.process(message, vector_store=vs, history=history, stream=False)

        assistant_msg = session.add_message(
            "assistant", result["answer"], sources=result.get("sources", []),
        )
        sm.save(session)

        return {
            "success": True,
            "data": {"conversation_id": conv_id, "message": assistant_msg},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: Request):
    """
    Streaming chat with multi-agent collaboration workflow.
    Sends agent_step events to visualize the collaboration process.
    """
    data = await request.json()
    if not data or "message" not in data:
        raise HTTPException(status_code=400, detail="No message provided")

    message = data["message"]
    conv_id = data.get("conversation_id")
    kb_id = data.get("kb_id")

    def generate():
        nonlocal conv_id

        # Buffer flush for proxies
        yield f": {' ' * 2048}\n\n"

        try:
            sm = get_session_manager()
            session, conv_id_local, session_kb_id = _get_or_create_session(
                sm, conv_id, message, kb_id
            )
            conv_id = conv_id_local

            if not session_kb_id:
                yield _sse({"type": "error", "error": "请先选择知识库"})
                return

            # Parse @mention
            target_agent, clean_message = _parse_at_mention(message)

            session.add_message("user", message)

            # ========== Agent Collaboration Workflow ==========

            # --- Step 1: Retrieval ---
            t0 = time.time()
            yield _sse({
                "type": "agent_step",
                "agent": "retriever",
                "status": "working",
                "message": "正在从知识库检索相关文献...",
            })

            agent = get_chat_agent()
            vs = get_vector_store(session_kb_id)
            history = session.get_history()

            # Route to appropriate agent based on @mention
            if target_agent == "researcher":
                yield _sse({
                    "type": "agent_step",
                    "agent": "retriever",
                    "status": "done",
                    "message": "检索完成",
                    "duration": round(time.time() - t0, 1),
                })
                # Use ResearchAgent for deeper analysis
                t1 = time.time()
                yield _sse({
                    "type": "agent_step",
                    "agent": "researcher",
                    "status": "working",
                    "message": "正在生成研究报告...",
                })

                from src.agents.research import ResearchAgent
                research_agent = ResearchAgent()
                result = research_agent.process(
                    clean_message, vector_store=vs, stream=True
                )

                sources = result.get("sources", [])
                if sources:
                    yield _sse({"type": "sources", "data": sources})

                yield _sse({
                    "type": "agent_step",
                    "agent": "researcher",
                    "status": "done",
                    "message": "报告生成中",
                    "duration": round(time.time() - t1, 1),
                })

                # Stream report
                full_response = ""
                if result.get("plan"):
                    full_response += f"## 📋 研究计划\n\n{result['plan']}\n\n---\n\n## 📝 研究报告\n\n"
                    yield _sse({"type": "chunk", "content": full_response, "agent": "researcher"})

                for chunk in result.get("stream", []):
                    full_response += chunk
                    yield _sse({"type": "chunk", "content": chunk, "agent": "researcher"})

            else:
                # Default: ChatAgent (RAG question-answering)
                result = agent.process(
                    clean_message, vector_store=vs, history=history, stream=True
                )

                sources = result.get("sources", [])
                retrieval_time = round(time.time() - t0, 1)

                yield _sse({
                    "type": "agent_step",
                    "agent": "retriever",
                    "status": "done",
                    "message": f"已找到 {len(sources)} 条相关段落",
                    "duration": retrieval_time,
                })

                if sources:
                    yield _sse({"type": "sources", "data": sources})

                # --- Step 2: Reasoning ---
                t1 = time.time()
                yield _sse({
                    "type": "agent_step",
                    "agent": "reasoner",
                    "status": "working",
                    "message": "正在基于检索结果进行分析推理...",
                })

                full_response = ""
                first_chunk = True
                for chunk in result["stream"]:
                    if first_chunk:
                        yield _sse({
                            "type": "agent_step",
                            "agent": "reasoner",
                            "status": "done",
                            "message": "分析推理中",
                            "duration": round(time.time() - t1, 1),
                        })
                        first_chunk = False
                    full_response += chunk
                    yield _sse({"type": "chunk", "content": chunk, "agent": "reasoner"})

                # If no chunks came through (empty response)
                if first_chunk:
                    yield _sse({
                        "type": "agent_step",
                        "agent": "reasoner",
                        "status": "done",
                        "message": "分析完成",
                        "duration": round(time.time() - t1, 1),
                    })

            # Save and finalize
            session.add_message("assistant", full_response, sources=sources)
            sm.save(session)

            yield _sse({"type": "done", "conversation_id": conv_id})

        except Exception as e:
            yield _sse({"type": "error", "error": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )
