from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers import fastwrite_bridge


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(fastwrite_bridge.router, prefix="/api")
    return TestClient(app)


def test_fastwrite_callback_token_validation():
    client = build_client()
    resp = client.post("/api/fastwrite/callback/not-found-token", json={"content": "x"})
    assert resp.status_code == 404


def test_fastwrite_handoff_and_callback_roundtrip():
    client = build_client()

    handoff = client.post(
        "/api/fastwrite/handoff",
        json={"text": "draft text", "title": "Draft", "source": "co_writer", "metadata": {"k": "v"}},
    )
    assert handoff.status_code == 200
    body = handoff.json()["data"]
    session_id = body["session_id"]
    callback_token = body["callback_token"]
    assert session_id
    assert callback_token
    assert body["fastwrite_url"].startswith("http://127.0.0.1:3002/")

    pending = client.get(f"/api/fastwrite/callback/{callback_token}")
    assert pending.status_code == 200
    assert pending.json()["data"]["status"] == "pending"

    cb = client.post(
        f"/api/fastwrite/callback/{callback_token}",
        json={"content": "updated content", "title": "Done", "metadata": {"source": "fastwrite"}},
    )
    assert cb.status_code == 200

    done = client.get(f"/api/fastwrite/callback/{callback_token}")
    assert done.status_code == 200
    assert done.json()["data"]["status"] == "completed"

    handoff_read = client.get(f"/api/fastwrite/handoff/{session_id}")
    assert handoff_read.status_code == 200
    callback_result = handoff_read.json()["data"]["callback_result"]
    assert callback_result["content"] == "updated content"


def test_fastwrite_callback_expired_status():
    client = build_client()

    handoff = client.post(
        "/api/fastwrite/handoff",
        json={"text": "draft text", "title": "Draft"},
    )
    callback_token = handoff.json()["data"]["callback_token"]
    session_id = handoff.json()["data"]["session_id"]
    session = fastwrite_bridge._bridge_store.get_session(session_id)
    assert session is not None
    session.expires_at = datetime.now() - timedelta(seconds=1)

    expired = client.get(f"/api/fastwrite/callback/{callback_token}")
    assert expired.status_code == 200
    body = expired.json()["data"]
    assert body["status"] == "expired"
    assert body["error"] == "callback token expired"


def test_fastwrite_callback_failed_status():
    client = build_client()

    handoff = client.post(
        "/api/fastwrite/handoff",
        json={"text": "draft text", "title": "Draft"},
    )
    callback_token = handoff.json()["data"]["callback_token"]

    cb = client.post(
        f"/api/fastwrite/callback/{callback_token}",
        json={"content": "", "status": "failed", "error": "render failed"},
    )
    assert cb.status_code == 200

    failed = client.get(f"/api/fastwrite/callback/{callback_token}")
    assert failed.status_code == 200
    body = failed.json()["data"]
    assert body["status"] == "failed"
    assert body["error"] == "render failed"


def test_fastwrite_handoff_respects_env_url(monkeypatch):
    monkeypatch.setenv("FASTWRITE_URL", "http://example-fastwrite:4321")
    client = build_client()

    handoff = client.post(
        "/api/fastwrite/handoff",
        json={"text": "draft text", "title": "Draft"},
    )
    assert handoff.status_code == 200
    url = handoff.json()["data"]["fastwrite_url"]
    assert url.startswith("http://example-fastwrite:4321/")


def test_fastwrite_health_endpoint_reports_unavailable(monkeypatch):
    monkeypatch.setenv("FASTWRITE_URL", "http://127.0.0.1:9")
    client = build_client()
    resp = client.get("/api/fastwrite/health")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["url"] == "http://127.0.0.1:9"
    assert data["available"] is False
