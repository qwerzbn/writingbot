# -*- coding: utf-8 -*-
"""Conversation and chat APIs with KB-aware RAG + pure-LLM fallback."""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Callable, Generator

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.knowledge.kb_manager import KnowledgeBaseManager
from src.knowledge.vector_store import VectorStore
from src.orchestrator.service import get_orchestrator_service
from src.rag.engine import RAGEngine
from src.services.llm import get_llm_client
from src.session import ConversationSession, SessionManager


router = APIRouter()
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

_CHAT_SYSTEM_PROMPT = (
    "你是 WritingBot 智能助手。"
    "在无知识库时请基于对话历史尽量提供准确、清晰、结构化的回答；"
    "不确定时请明确说明不确定。"
)

_NON_STREAM_TIMEOUT_SECONDS = 90.0
_NON_STREAM_RETRY_ATTEMPTS = 2
_STREAM_INIT_RETRY_ATTEMPTS = 2
_RETRY_BACKOFF_SECONDS = 0.35
_LLM_TIMEOUT_SECONDS = 60.0
_STREAM_HEARTBEAT_SECONDS = 10.0

_RATE_LIMIT_WINDOW_SECONDS = 10.0
_RATE_LIMIT_MAX_REQUESTS = 20
_CIRCUIT_FAILURE_THRESHOLD = 5
_CIRCUIT_OPEN_SECONDS = 20.0


_session_manager: SessionManager | None = None
_AUDIT_LOCK = threading.RLock()
_AUDIT_FILE = DATA_DIR / "logs" / "chat_events.jsonl"

_RUNTIME_LOCK = threading.RLock()
_RATE_BUCKETS: dict[str, list[float]] = {}
_CIRCUIT_STATE: dict[str, dict[str, float]] = {}
_INFLIGHT_KEYS: set[str] = set()
_METRICS: dict[str, int] = {
    "requests_total": 0,
    "sync_requests": 0,
    "stream_requests": 0,
    "errors_total": 0,
    "throttled_total": 0,
    "circuit_open_total": 0,
    "idempotent_replay_total": 0,
    "inflight_reject_total": 0,
    "retries_total": 0,
}
_LATENCIES_MS: list[int] = []

_STREAM_END = object()


class ConversationCreateRequest(BaseModel):
    title: str | None = None
    kb_id: str | None = None
    default_skill_ids: list[str] | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    kb_id: str | None = None
    title: str | None = None
    idempotency_key: str | None = None
    skill_ids: list[str] | None = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(DATA_DIR / "sessions")
    return _session_manager


def _append_chat_audit(event_type: str, payload: dict) -> None:
    _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        **payload,
    }
    with _AUDIT_LOCK:
        with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _inc_metric(name: str, value: int = 1) -> None:
    with _RUNTIME_LOCK:
        _METRICS[name] = _METRICS.get(name, 0) + value


def _observe_latency_ms(value: int) -> None:
    with _RUNTIME_LOCK:
        _LATENCIES_MS.append(max(0, int(value)))
        if len(_LATENCIES_MS) > 2000:
            del _LATENCIES_MS[: len(_LATENCIES_MS) - 2000]


def _latency_percentile(values: list[int], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, min(len(sorted_vals) - 1, int(round((len(sorted_vals) - 1) * p))))
    return float(sorted_vals[idx])


def _metrics_snapshot() -> dict:
    with _RUNTIME_LOCK:
        latencies = list(_LATENCIES_MS)
        counters = dict(_METRICS)
    return {
        "counters": counters,
        "latency_ms": {
            "count": len(latencies),
            "p50": _latency_percentile(latencies, 0.50),
            "p95": _latency_percentile(latencies, 0.95),
            "max": float(max(latencies) if latencies else 0),
        },
        "runtime": {
            "rate_limit_window_seconds": _RATE_LIMIT_WINDOW_SECONDS,
            "rate_limit_max_requests": _RATE_LIMIT_MAX_REQUESTS,
            "circuit_failure_threshold": _CIRCUIT_FAILURE_THRESHOLD,
            "circuit_open_seconds": _CIRCUIT_OPEN_SECONDS,
        },
    }


def _scope_key(request: Request, conversation_id: str | None) -> str:
    host = "unknown"
    if request.client and request.client.host:
        host = request.client.host
    return f"{host}:{conversation_id or 'draft'}"


def _enforce_rate_limit(scope: str) -> None:
    now = time.time()
    with _RUNTIME_LOCK:
        bucket = _RATE_BUCKETS.setdefault(scope, [])
        cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
        bucket[:] = [ts for ts in bucket if ts >= cutoff]
        if len(bucket) >= _RATE_LIMIT_MAX_REQUESTS:
            _METRICS["throttled_total"] += 1
            raise HTTPException(status_code=429, detail="Too many requests")
        bucket.append(now)


def _enforce_circuit(scope: str) -> None:
    now = time.time()
    with _RUNTIME_LOCK:
        state = _CIRCUIT_STATE.get(scope)
        if not state:
            return
        open_until = float(state.get("open_until", 0.0) or 0.0)
        if open_until > now:
            _METRICS["circuit_open_total"] += 1
            raise HTTPException(status_code=503, detail="Circuit is open, please retry later")


def _record_failure(scope: str) -> None:
    now = time.time()
    with _RUNTIME_LOCK:
        state = _CIRCUIT_STATE.setdefault(scope, {"failures": 0.0, "open_until": 0.0})
        open_until = float(state.get("open_until", 0.0) or 0.0)
        if open_until > now:
            return
        failures = int(state.get("failures", 0) or 0) + 1
        state["failures"] = float(failures)
        if failures >= _CIRCUIT_FAILURE_THRESHOLD:
            state["open_until"] = now + _CIRCUIT_OPEN_SECONDS
            state["failures"] = 0.0


def _record_success(scope: str) -> None:
    with _RUNTIME_LOCK:
        if scope in _CIRCUIT_STATE:
            _CIRCUIT_STATE[scope]["failures"] = 0.0


def _inflight_token(session_id: str, idempotency_key: str | None) -> str | None:
    if not idempotency_key:
        return None
    return f"{session_id}:{idempotency_key}"


def _acquire_inflight(token: str | None) -> bool:
    if not token:
        return True
    with _RUNTIME_LOCK:
        if token in _INFLIGHT_KEYS:
            _METRICS["inflight_reject_total"] += 1
            return False
        _INFLIGHT_KEYS.add(token)
        return True


def _release_inflight(token: str | None) -> None:
    if not token:
        return
    with _RUNTIME_LOCK:
        _INFLIGHT_KEYS.discard(token)


def _history_messages(session: ConversationSession, max_rounds: int = 8) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    max_items = max_rounds * 2
    for msg in session.messages[-max_items:]:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            history.append({"role": role, "content": content})
    return history


def _auto_title(message: str) -> str:
    text = (message or "").strip().replace("\n", " ")
    if not text:
        return "新对话"
    return text[:30]


def _normalize_idempotency_key(raw: str | None) -> str | None:
    if not raw:
        return None
    key = raw.strip()
    if not key:
        return None
    return key[:256]


def _normalize_skill_ids(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        skill_id = str(item or "").strip()
        if not skill_id.startswith("/"):
            continue
        if skill_id in seen:
            continue
        seen.add(skill_id)
        out.append(skill_id)
    return out


def _resolve_session(req: ChatRequest) -> ConversationSession:
    manager = get_session_manager()
    normalized_skill_ids = _normalize_skill_ids(req.skill_ids)
    if req.conversation_id:
        session = manager.get(req.conversation_id)
        if not session:
            title = req.title or _auto_title(req.message)
            session = manager.get_or_create(
                req.conversation_id,
                title=title,
                kb_id=req.kb_id,
                default_skill_ids=normalized_skill_ids,
            )
    else:
        title = req.title or _auto_title(req.message)
        session = manager.create(
            title=title,
            kb_id=req.kb_id,
            session_id=str(uuid.uuid4()),
            default_skill_ids=normalized_skill_ids,
        )

    if req.kb_id is not None:
        session.kb_id = req.kb_id

    if not session.messages and (not session.title or session.title == "新对话"):
        session.title = req.title or _auto_title(req.message)

    if req.skill_ids is not None:
        session.default_skill_ids = normalized_skill_ids

    return session


def _vector_store_for_kb(kb_id: str) -> VectorStore:
    kb_manager = KnowledgeBaseManager(DATA_DIR / "knowledge_bases")
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"KB not found: {kb_id}")

    return VectorStore(
        persist_dir=str(kb_manager.get_vector_store_path(kb_id)),
        collection_name=kb["collection_name"],
        embedding_model=kb.get("embedding_model", "sentence-transformers/all-mpnet-base-v2"),
        embedding_provider=kb.get("embedding_provider", "sentence-transformers"),
    )


def _chat_with_rag(history: list[dict[str, str]], message: str, kb_id: str) -> tuple[str, list[dict]]:
    engine = RAGEngine(vector_store=_vector_store_for_kb(kb_id))
    engine.history = history
    result = engine.query(message, use_history=True)
    return result.get("answer", ""), result.get("sources", []) or []


def _chat_with_llm(
    history: list[dict[str, str]],
    message: str,
    append_user_message: bool = True,
) -> tuple[str, list[dict]]:
    client = get_llm_client()
    messages = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]
    messages.extend(history)
    if append_user_message:
        messages.append({"role": "user", "content": message})
    answer = client.chat(messages=messages, temperature=0.7, max_tokens=2000, timeout=_LLM_TIMEOUT_SECONDS)
    return answer or "", []


def _chat_with_orchestrator_sync(
    history: list[dict[str, str]],
    message: str,
    kb_id: str | None,
    skill_ids: list[str],
) -> tuple[str, list[dict], dict]:
    payload = {
        "message": message,
        "kb_id": kb_id,
        "history": history,
        "skill_ids": skill_ids,
    }
    result = get_orchestrator_service().execute_sync(mode="chat_research", payload=payload)
    output = str(result.get("output") or "")
    sources = result.get("sources") or []
    metadata = result.get("metadata") or {}
    if not isinstance(sources, list):
        sources = []
    if not isinstance(metadata, dict):
        metadata = {}
    return output, sources, metadata


def _call_with_timeout(fn: Callable[[], object], timeout_seconds: float) -> object:
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chat-timeout")
    future = pool.submit(fn)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError(f"operation timeout after {timeout_seconds}s") from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _execute_with_retry(
    label: str,
    fn: Callable[[], object],
    timeout_seconds: float,
    max_attempts: int,
) -> object:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _call_with_timeout(fn, timeout_seconds)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _inc_metric("retries_total", 1)
            _append_chat_audit(
                "sync_retry",
                {
                    "label": label,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error": str(exc),
                },
            )
            if attempt >= max_attempts:
                break
            time.sleep(_RETRY_BACKOFF_SECONDS * attempt)

    raise RuntimeError(f"{label} failed after {max_attempts} attempts: {last_exc}")


def _message_idempotency_key(msg: dict) -> str | None:
    metadata = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
    key = metadata.get("idempotency_key")
    return key if isinstance(key, str) and key else None


def _message_request_message(msg: dict) -> str | None:
    metadata = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
    req_msg = metadata.get("request_message")
    if isinstance(req_msg, str) and req_msg:
        return req_msg
    content = msg.get("content")
    if msg.get("role") == "user" and isinstance(content, str):
        return content
    return None


def _find_idempotency_state(
    session: ConversationSession,
    idempotency_key: str,
    current_message: str,
) -> tuple[dict | None, bool]:
    pending_user = False
    for msg in reversed(session.messages):
        if _message_idempotency_key(msg) != idempotency_key:
            continue

        recorded_message = _message_request_message(msg)
        if recorded_message and recorded_message != current_message:
            raise HTTPException(status_code=409, detail="Idempotency key reused with different message")

        if msg.get("role") == "assistant":
            return msg, pending_user
        if msg.get("role") == "user":
            pending_user = True

    return None, pending_user


def _chunk_text(text: str, size: int = 180) -> list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def _make_message_meta(
    request_id: str,
    idempotency_key: str | None,
    channel: str,
    mode: str,
    request_message: str,
    selected_skill_ids: list[str] | None = None,
    extra: dict | None = None,
) -> dict:
    payload = {
        "request_id": request_id,
        "channel": channel,
        "mode": mode,
        "request_message": request_message,
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    if selected_skill_ids:
        payload["selected_skill_ids"] = list(selected_skill_ids)
    if isinstance(extra, dict):
        payload.update(extra)
    return payload


def _stream_rag_with_retry(
    history: list[dict[str, str]],
    kb_id: str,
    message: str,
    emit_chunk: Callable[[str], None],
) -> tuple[str, list[dict]]:
    last_exc: Exception | None = None
    for attempt in range(1, _STREAM_INIT_RETRY_ATTEMPTS + 1):
        full_response = ""
        try:
            engine = RAGEngine(vector_store=_vector_store_for_kb(kb_id))
            engine.history = history
            stream = engine.query_stream(message, use_history=True)

            try:
                first_chunk = next(stream)
            except StopIteration as stop:
                payload = stop.value if isinstance(stop.value, dict) else {}
                return "", payload.get("sources", []) or []

            full_response += first_chunk
            emit_chunk(first_chunk)
            while True:
                try:
                    chunk = next(stream)
                except StopIteration as stop:
                    payload = stop.value if isinstance(stop.value, dict) else {}
                    return full_response, payload.get("sources", []) or []
                full_response += chunk
                emit_chunk(chunk)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _inc_metric("retries_total", 1)
            retryable = attempt < _STREAM_INIT_RETRY_ATTEMPTS and full_response == ""
            _append_chat_audit(
                "stream_retry",
                {
                    "mode": "rag",
                    "attempt": attempt,
                    "max_attempts": _STREAM_INIT_RETRY_ATTEMPTS,
                    "retryable": retryable,
                    "error": str(exc),
                },
            )
            if retryable:
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
                continue
            raise

    raise RuntimeError(f"stream rag failed: {last_exc}")


def _stream_llm_with_retry(
    history: list[dict[str, str]],
    message: str,
    emit_chunk: Callable[[str], None],
) -> tuple[str, list[dict]]:
    last_exc: Exception | None = None
    for attempt in range(1, _STREAM_INIT_RETRY_ATTEMPTS + 1):
        full_response = ""
        try:
            client = get_llm_client()
            messages = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]
            messages.extend(history)
            messages.append({"role": "user", "content": message})

            llm_stream = client.chat_stream(
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
                timeout=_LLM_TIMEOUT_SECONDS,
            )

            try:
                first_chunk = next(llm_stream)
            except StopIteration:
                return "", []

            full_response += first_chunk
            emit_chunk(first_chunk)
            for chunk in llm_stream:
                full_response += chunk
                emit_chunk(chunk)

            return full_response, []
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _inc_metric("retries_total", 1)
            retryable = attempt < _STREAM_INIT_RETRY_ATTEMPTS and full_response == ""
            _append_chat_audit(
                "stream_retry",
                {
                    "mode": "llm",
                    "attempt": attempt,
                    "max_attempts": _STREAM_INIT_RETRY_ATTEMPTS,
                    "retryable": retryable,
                    "error": str(exc),
                },
            )
            if retryable:
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
                continue
            raise

    raise RuntimeError(f"stream llm failed: {last_exc}")


def _stream_orchestrator_with_retry(
    history: list[dict[str, str]],
    message: str,
    kb_id: str | None,
    skill_ids: list[str],
    emit_event: Callable[[dict], None],
) -> tuple[str, list[dict], dict]:
    last_exc: Exception | None = None
    for attempt in range(1, _STREAM_INIT_RETRY_ATTEMPTS + 1):
        full_response = ""
        try:
            service = get_orchestrator_service()
            run_data = service.create_run(
                mode="chat_research",
                payload={
                    "message": message,
                    "kb_id": kb_id,
                    "history": history,
                    "skill_ids": skill_ids,
                },
            )
            run_id = str(run_data.get("run_id") or "")
            trace_id = str(run_data.get("trace_id") or "")
            if not run_id:
                raise RuntimeError("orchestrator run_id missing")

            sources: list[dict] = []
            done_event: dict = {}
            current_agent = ""
            for event in service.stream_run(run_id):
                if event.get("type") == "chunk":
                    chunk = str(event.get("content") or "")
                    full_response += chunk
                    if chunk:
                        emit_event(
                            {
                                "type": "chunk",
                                "content": chunk,
                                "meta": {"agent_id": current_agent} if current_agent else {},
                            }
                        )
                elif event.get("type") == "step":
                    step_name = str(event.get("step") or "")
                    step_status = str(event.get("status") or "")
                    if event.get("status") == "working":
                        current_agent = str(event.get("agent_id") or "")
                    emit_event(
                        {
                            "type": "chunk",
                            "content": "",
                            "meta": {
                                "kind": "progress",
                                "step": step_name,
                                "status": step_status,
                                "attempt": int(event.get("attempt") or 1),
                                "agent_id": str(event.get("agent_id") or current_agent or ""),
                            },
                        }
                    )
                elif event.get("type") == "sources":
                    data = event.get("data")
                    if isinstance(data, list):
                        sources = data
                elif event.get("type") == "done":
                    done_event = event
                    output = str(event.get("output") or "")
                    if output and output != full_response:
                        full_response = output
                    ev_sources = event.get("sources")
                    if isinstance(ev_sources, list):
                        sources = ev_sources
                elif event.get("type") == "error":
                    raise RuntimeError(str(event.get("error") or "orchestrator stream failed"))

            return full_response, sources, {
                "run_id": run_id,
                "trace_id": trace_id,
                "done": done_event,
            }
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _inc_metric("retries_total", 1)
            retryable = attempt < _STREAM_INIT_RETRY_ATTEMPTS and full_response == ""
            _append_chat_audit(
                "stream_retry",
                {
                    "mode": "chat_research",
                    "attempt": attempt,
                    "max_attempts": _STREAM_INIT_RETRY_ATTEMPTS,
                    "retryable": retryable,
                    "error": str(exc),
                },
            )
            if retryable:
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
                continue
            raise

    raise RuntimeError(f"stream orchestrator failed: {last_exc}")


def _sse_data(event: dict, event_id: int) -> str:
    return f"id: {event_id}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


def _stream_replay_generate(session: ConversationSession, existing_assistant: dict) -> Generator[str, None, None]:
    yield f": {' ' * 2048}\n\n"
    event_id = 0
    for chunk in _chunk_text(existing_assistant.get("content", "")):
        event_id += 1
        yield _sse_data({"type": "chunk", "content": chunk}, event_id)
    event_id += 1
    yield _sse_data({"type": "sources", "data": existing_assistant.get("sources", []) or []}, event_id)
    event_id += 1
    yield _sse_data({"type": "done", "conversation_id": session.id, "idempotent_replay": True}, event_id)


def _reset_runtime_state_for_tests() -> None:
    with _RUNTIME_LOCK:
        _RATE_BUCKETS.clear()
        _CIRCUIT_STATE.clear()
        _INFLIGHT_KEYS.clear()
        _LATENCIES_MS.clear()
        for k in list(_METRICS.keys()):
            _METRICS[k] = 0


@router.get("/chat/metrics")
async def chat_metrics():
    return {"success": True, "data": _metrics_snapshot()}


@router.get("/conversations")
async def list_conversations():
    data = get_session_manager().list_sessions()
    return {"success": True, "data": data}


@router.post("/conversations")
async def create_conversation(req: ConversationCreateRequest):
    manager = get_session_manager()
    session = manager.create(
        title=req.title or "新对话",
        kb_id=req.kb_id,
        default_skill_ids=_normalize_skill_ids(req.default_skill_ids),
    )
    return {"success": True, "data": session.to_dict(include_messages=True)}


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    session = get_session_manager().get(conv_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "data": session.to_dict(include_messages=True)}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    deleted = get_session_manager().delete(conv_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True}


@router.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
):
    started_at = time.time()
    _inc_metric("requests_total", 1)
    _inc_metric("sync_requests", 1)

    message = (req.message or "").strip()
    if not message:
        _inc_metric("errors_total", 1)
        raise HTTPException(status_code=400, detail="No message provided")

    scope = _scope_key(request, req.conversation_id)
    _enforce_circuit(scope)
    _enforce_rate_limit(scope)

    idempotency_key = _normalize_idempotency_key(req.idempotency_key or idempotency_key_header)
    session = _resolve_session(req)

    existing_assistant: dict | None = None
    pending_user_exists = False
    if idempotency_key:
        existing_assistant, pending_user_exists = _find_idempotency_state(
            session,
            idempotency_key=idempotency_key,
            current_message=message,
        )
        if existing_assistant:
            _inc_metric("idempotent_replay_total", 1)
            _append_chat_audit(
                "sync_idempotent_replay",
                {"conversation_id": session.id, "idempotency_key": idempotency_key},
            )
            _observe_latency_ms(int((time.time() - started_at) * 1000))
            return {
                "success": True,
                "data": {
                    "conversation_id": session.id,
                    "message": existing_assistant,
                    "sources": existing_assistant.get("sources", []) or [],
                    "idempotent_replay": True,
                },
            }

    inflight_token = _inflight_token(session.id, idempotency_key)
    if not _acquire_inflight(inflight_token):
        _inc_metric("errors_total", 1)
        raise HTTPException(status_code=409, detail="Request with same idempotency key is in progress")

    request_id = str(uuid.uuid4())
    mode = "chat_research"
    selected_skill_ids = _normalize_skill_ids(req.skill_ids) if req.skill_ids is not None else list(session.default_skill_ids)

    try:
        history_snapshot = _history_messages(session)
        effective_history = history_snapshot
        if (
            pending_user_exists
            and history_snapshot
            and history_snapshot[-1].get("role") == "user"
            and history_snapshot[-1].get("content") == message
        ):
            effective_history = history_snapshot[:-1]

        if not pending_user_exists:
            user_meta = _make_message_meta(
                request_id=request_id,
                idempotency_key=idempotency_key,
                channel="sync",
                mode=mode,
                request_message=message,
                selected_skill_ids=selected_skill_ids,
            )
            session.add_message("user", message, metadata=user_meta)
            get_session_manager().save(session)

        answer, sources, orchestrator_meta = _execute_with_retry(
            label="sync_chat_research",
            fn=lambda: _chat_with_orchestrator_sync(
                history=effective_history,
                message=message,
                kb_id=session.kb_id,
                skill_ids=selected_skill_ids,
            ),
            timeout_seconds=_NON_STREAM_TIMEOUT_SECONDS,
            max_attempts=_NON_STREAM_RETRY_ATTEMPTS,
        )
        if not isinstance(answer, str):
            answer = str(answer or "")
        if not isinstance(sources, list):
            sources = []
        if not isinstance(orchestrator_meta, dict):
            orchestrator_meta = {}

        assistant_meta = _make_message_meta(
            request_id=request_id,
            idempotency_key=idempotency_key,
            channel="sync",
            mode=mode,
            request_message=message,
            selected_skill_ids=selected_skill_ids,
            extra={
                "orchestrator_run_id": orchestrator_meta.get("run_id"),
                "orchestrator_trace_id": orchestrator_meta.get("trace_id"),
                "orchestrator_meta": orchestrator_meta.get("meta"),
            },
        )
        assistant_msg = session.add_message("assistant", answer, sources=sources, metadata=assistant_meta)
        get_session_manager().save(session)
        _record_success(scope)

        _append_chat_audit(
            "sync_done",
            {
                "conversation_id": session.id,
                "mode": mode,
                "idempotency_key": idempotency_key,
                "selected_skill_ids": selected_skill_ids,
                "answer_chars": len(answer or ""),
                "source_count": len(sources),
                "paper_hits": orchestrator_meta.get("meta", {}).get("paper_hits")
                if isinstance(orchestrator_meta.get("meta"), dict)
                else None,
            },
        )

        return {
            "success": True,
            "data": {
                "conversation_id": session.id,
                "message": assistant_msg,
                "sources": sources,
                "meta": orchestrator_meta.get("meta") if isinstance(orchestrator_meta.get("meta"), dict) else {},
            },
        }
    except HTTPException:
        _inc_metric("errors_total", 1)
        _record_failure(scope)
        raise
    except Exception as exc:  # noqa: BLE001
        _inc_metric("errors_total", 1)
        _record_failure(scope)
        _append_chat_audit(
            "sync_error",
            {
                "conversation_id": session.id,
                "mode": mode,
                "idempotency_key": idempotency_key,
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc
    finally:
        _release_inflight(inflight_token)
        _observe_latency_ms(int((time.time() - started_at) * 1000))


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
):
    started_at = time.time()
    _inc_metric("requests_total", 1)
    _inc_metric("stream_requests", 1)

    message = (req.message or "").strip()
    if not message:
        _inc_metric("errors_total", 1)
        raise HTTPException(status_code=400, detail="No message provided")

    scope = _scope_key(request, req.conversation_id)
    _enforce_circuit(scope)
    _enforce_rate_limit(scope)

    idempotency_key = _normalize_idempotency_key(req.idempotency_key or idempotency_key_header)
    session = _resolve_session(req)

    existing_assistant: dict | None = None
    pending_user_exists = False
    if idempotency_key:
        existing_assistant, pending_user_exists = _find_idempotency_state(
            session,
            idempotency_key=idempotency_key,
            current_message=message,
        )
        if existing_assistant:
            _inc_metric("idempotent_replay_total", 1)
            _append_chat_audit(
                "stream_idempotent_replay",
                {"conversation_id": session.id, "idempotency_key": idempotency_key},
            )
            return StreamingResponse(
                _stream_replay_generate(session, existing_assistant),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

    inflight_token = _inflight_token(session.id, idempotency_key)
    if not _acquire_inflight(inflight_token):
        _inc_metric("errors_total", 1)
        raise HTTPException(status_code=409, detail="Request with same idempotency key is in progress")

    def generate() -> Generator[str, None, None]:
        event_queue: queue.Queue[dict | object] = queue.Queue()
        mode = "chat_research"
        request_id = str(uuid.uuid4())
        selected_skill_ids = _normalize_skill_ids(req.skill_ids) if req.skill_ids is not None else list(session.default_skill_ids)
        finished = False

        def worker() -> None:
            nonlocal finished
            try:
                history = _history_messages(session)
                effective_history = history

                if not pending_user_exists:
                    user_meta = _make_message_meta(
                        request_id=request_id,
                        idempotency_key=idempotency_key,
                        channel="stream",
                        mode=mode,
                        request_message=message,
                        selected_skill_ids=selected_skill_ids,
                    )
                    session.add_message("user", message, metadata=user_meta)
                    get_session_manager().save(session)
                elif history and history[-1].get("role") == "user" and history[-1].get("content") == message:
                    effective_history = history[:-1]

                def emit_event(payload: dict) -> None:
                    event_queue.put(payload)

                full_response, sources, orchestrator_meta = _stream_orchestrator_with_retry(
                    history=effective_history,
                    kb_id=session.kb_id,
                    skill_ids=selected_skill_ids,
                    message=message,
                    emit_event=emit_event,
                )

                assistant_meta = _make_message_meta(
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    channel="stream",
                    mode=mode,
                    request_message=message,
                    selected_skill_ids=selected_skill_ids,
                    extra={
                        "orchestrator_run_id": orchestrator_meta.get("run_id"),
                        "orchestrator_trace_id": orchestrator_meta.get("trace_id"),
                        "orchestrator_meta": orchestrator_meta.get("done", {}).get("meta")
                        if isinstance(orchestrator_meta.get("done"), dict)
                        else None,
                    },
                )
                session.add_message("assistant", full_response, sources=sources, metadata=assistant_meta)
                get_session_manager().save(session)
                _record_success(scope)

                _append_chat_audit(
                    "stream_done",
                    {
                        "conversation_id": session.id,
                        "mode": mode,
                        "idempotency_key": idempotency_key,
                        "selected_skill_ids": selected_skill_ids,
                        "answer_chars": len(full_response),
                        "source_count": len(sources),
                        "paper_hits": orchestrator_meta.get("done", {}).get("meta", {}).get("paper_hits")
                        if isinstance(orchestrator_meta.get("done"), dict)
                        and isinstance(orchestrator_meta.get("done", {}).get("meta"), dict)
                        else None,
                    },
                )

                done_meta = {}
                if isinstance(orchestrator_meta.get("done"), dict):
                    meta = orchestrator_meta.get("done", {}).get("meta")
                    if isinstance(meta, dict):
                        done_meta = meta
                event_queue.put({"type": "sources", "data": sources, "meta": {"paper_hits": done_meta.get("paper_hits", 0)}})
                event_queue.put({"type": "done", "conversation_id": session.id, "meta": done_meta})
            except Exception as exc:  # noqa: BLE001
                _inc_metric("errors_total", 1)
                _record_failure(scope)
                _append_chat_audit(
                    "stream_error",
                    {
                        "conversation_id": session.id,
                        "mode": mode,
                        "idempotency_key": idempotency_key,
                        "error": str(exc),
                    },
                )
                session.add_message(
                    "assistant",
                    f"处理失败：{exc}",
                    sources=[],
                    metadata=_make_message_meta(
                        request_id=request_id,
                        idempotency_key=idempotency_key,
                        channel="stream",
                        mode=mode,
                        request_message=message,
                    ),
                )
                get_session_manager().save(session)
                event_queue.put({"type": "error", "error": str(exc)})
            finally:
                finished = True
                event_queue.put(_STREAM_END)

        thread = threading.Thread(target=worker, name=f"chat-stream-{session.id[:8]}", daemon=True)
        thread.start()

        event_id = 0
        try:
            yield f": {' ' * 2048}\n\n"
            while True:
                try:
                    item = event_queue.get(timeout=_STREAM_HEARTBEAT_SECONDS)
                except queue.Empty:
                    if finished:
                        break
                    yield ": heartbeat\n\n"
                    continue

                if item is _STREAM_END:
                    break

                if not isinstance(item, dict):
                    continue

                event_id += 1
                yield _sse_data(item, event_id)
        finally:
            _release_inflight(inflight_token)
            _observe_latency_ms(int((time.time() - started_at) * 1000))

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
