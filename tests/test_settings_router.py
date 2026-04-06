from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers import settings


def build_client(tmp_env: Path) -> TestClient:
    app = FastAPI()
    app.include_router(settings.router, prefix="/api")
    settings.ENV_FILE = tmp_env
    return TestClient(app)


def test_get_settings_masks_api_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LLM_PROVIDER=openai",
                "LLM_BASE_URL=https://api.openai.com/v1",
                "LLM_MODEL=gpt-4o-mini",
                "LLM_API_KEY=sk-test-1234567890",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    client = build_client(env_file)

    resp = client.get("/api/settings/llm")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["has_api_key"] is True
    assert data["api_key"] != "sk-test-1234567890"
    assert "*" in data["api_key"]


def test_update_settings_keeps_existing_key_when_mask_sent(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LLM_PROVIDER=openai",
                "LLM_BASE_URL=https://api.openai.com/v1",
                "LLM_MODEL=gpt-4o-mini",
                "LLM_API_KEY=sk-existing-12345678",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    client = build_client(env_file)
    masked_key = client.get("/api/settings/llm").json()["data"]["api_key"]

    update_resp = client.put(
        "/api/settings/llm",
        json={
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "api_key": masked_key,
        },
    )
    assert update_resp.status_code == 200

    content = env_file.read_text(encoding="utf-8")
    assert "LLM_API_KEY=sk-existing-12345678" in content


def test_update_settings_accepts_new_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LLM_PROVIDER=ollama",
                "LLM_BASE_URL=http://localhost:11434/v1",
                "LLM_MODEL=qwen3:0.6b",
                "LLM_API_KEY=ollama",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    client = build_client(env_file)

    update_resp = client.put(
        "/api/settings/llm",
        json={
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "api_key": "sk-new-xyz",
        },
    )
    assert update_resp.status_code == 200
    content = env_file.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=openai" in content
    assert "LLM_API_KEY=sk-new-xyz" in content


def test_get_settings_without_api_key_reports_false(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LLM_PROVIDER=ollama",
                "LLM_BASE_URL=http://localhost:11434/v1",
                "LLM_MODEL=qwen3:0.6b",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    client = build_client(env_file)

    resp = client.get("/api/settings/llm")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["has_api_key"] is False
    assert data["api_key"] == ""
