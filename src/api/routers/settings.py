# -*- coding: utf-8 -*-
"""
Settings API Router
====================

Endpoints for reading and updating application settings (LLM config, etc.).
Settings are persisted to .env and take effect immediately for all modules.
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class LLMSettings(BaseModel):
    provider: str = "ollama"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen3:0.6b"
    api_key: str = "ollama"


def _read_env() -> dict[str, str]:
    """Read .env file into a dict."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


def _write_env(updates: dict[str, str]):
    """Update .env file with new values, preserving comments and structure."""
    if not ENV_FILE.exists():
        lines = []
    else:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Append any new keys not already in file
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _apply_config_to_runtime(settings: LLMSettings):
    """
    Apply LLM config changes to the running process immediately.
    Resets cached LLM config and client so all modules pick up new settings.
    """
    # 1. Update os.environ so any future reads get new values
    os.environ["LLM_PROVIDER"] = settings.provider
    os.environ["LLM_BASE_URL"] = settings.base_url
    os.environ["LLM_MODEL"] = settings.model
    os.environ["LLM_API_KEY"] = settings.api_key

    # 2. Reset cached singletons
    import src.services.llm.config as config_mod
    import src.services.llm.client as client_mod
    config_mod._llm_config = None
    client_mod._llm_client = None


@router.get("/settings/llm")
async def get_llm_settings():
    """Get current LLM configuration from .env file."""
    env = _read_env()
    return {
        "success": True,
        "data": {
            "provider": env.get("LLM_PROVIDER", "ollama"),
            "base_url": env.get("LLM_BASE_URL", "http://localhost:11434/v1"),
            "model": env.get("LLM_MODEL", "qwen3:0.6b"),
            "api_key": env.get("LLM_API_KEY", "ollama"),
        },
    }


@router.put("/settings/llm")
async def update_llm_settings(settings: LLMSettings):
    """
    Update LLM configuration.
    - Persists to .env file (survives restart)
    - Applies to runtime immediately (no restart needed)
    """
    try:
        # Persist to .env
        _write_env({
            "LLM_PROVIDER": settings.provider,
            "LLM_BASE_URL": settings.base_url,
            "LLM_MODEL": settings.model,
            "LLM_API_KEY": settings.api_key,
        })

        # Apply to running process
        _apply_config_to_runtime(settings)

        return {"success": True, "message": "LLM 配置已保存并生效"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/llm/test")
async def test_llm_connection(settings: LLMSettings | None = None):
    """
    Test LLM connection.
    If settings are provided, tests with those settings.
    Otherwise tests with the current saved config.
    """
    try:
        from src.services.llm.client import LLMClient
        from src.services.llm.config import LLMConfig

        if settings:
            # Test with provided settings (before saving)
            config = LLMConfig(
                provider=settings.provider,
                base_url=settings.base_url,
                model=settings.model,
                api_key=settings.api_key,
            )
        else:
            # Test with current saved config
            from src.services.llm.config import get_llm_config
            config = get_llm_config()

        client = LLMClient(config)
        result = client.chat(
            messages=[{"role": "user", "content": "Say 'OK' in one word."}],
            temperature=0,
            max_tokens=10,
        )
        return {
            "success": True,
            "data": {
                "response": result,
                "model": config.model,
                "provider": config.provider,
            },
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
