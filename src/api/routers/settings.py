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

from src.services.llm.config import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
)

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class LLMSettings(BaseModel):
    provider: str = DEFAULT_LLM_PROVIDER
    base_url: str = DEFAULT_LLM_BASE_URL
    model: str = DEFAULT_LLM_MODEL
    api_key: str | None = None


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

    alias_pairs = {
        "LLM_BASE_URL": {"BASE_URL"},
        "LLM_MODEL": {"MODEL_ID"},
        "LLM_API_KEY": {"API_KEY"},
    }
    alias_keys_to_remove = {
        alias
        for key, aliases in alias_pairs.items()
        if key in updates
        for alias in aliases
    }

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in alias_keys_to_remove:
                continue
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
    os.environ["LLM_API_KEY"] = settings.api_key or ""

    # 2. Reset cached singletons
    import src.services.llm.config as config_mod
    import src.services.llm.client as client_mod
    config_mod._llm_config = None
    client_mod._llm_client = None


def _mask_api_key(api_key: str) -> str:
    value = (api_key or "").strip()
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    if len(value) <= 8:
        return f"{value[:1]}{'*' * (len(value) - 2)}{value[-1:]}"
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def _resolve_api_key_for_update(incoming: str | None, existing: str) -> str:
    candidate = (incoming or "").strip()
    if not candidate:
        return existing
    if existing and candidate == _mask_api_key(existing):
        return existing
    return candidate


def _env_value(env: dict[str, str], *names: str, default: str) -> str:
    for name in names:
        value = str(env.get(name, "") or "").strip()
        if value:
            return value
    return default


@router.get("/settings/llm")
async def get_llm_settings():
    """Get current LLM configuration from .env file."""
    env = _read_env()
    api_key = _env_value(env, "LLM_API_KEY", "API_KEY", default="")
    return {
        "success": True,
        "data": {
            "provider": _env_value(env, "LLM_PROVIDER", default=DEFAULT_LLM_PROVIDER),
            "base_url": _env_value(env, "LLM_BASE_URL", "BASE_URL", default=DEFAULT_LLM_BASE_URL),
            "model": _env_value(env, "LLM_MODEL", "MODEL_ID", default=DEFAULT_LLM_MODEL),
            "api_key": _mask_api_key(api_key),
            "has_api_key": bool((api_key or "").strip()),
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
        env = _read_env()
        resolved_api_key = _resolve_api_key_for_update(
            settings.api_key,
            _env_value(env, "LLM_API_KEY", "API_KEY", default=""),
        )
        applied = LLMSettings(
            provider=settings.provider,
            base_url=settings.base_url,
            model=settings.model,
            api_key=resolved_api_key,
        )

        # Persist to .env
        _write_env({
            "LLM_PROVIDER": applied.provider,
            "LLM_BASE_URL": applied.base_url,
            "LLM_MODEL": applied.model,
            "LLM_API_KEY": applied.api_key or "",
        })

        # Apply to running process
        _apply_config_to_runtime(applied)

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
            env = _read_env()
            resolved_api_key = _resolve_api_key_for_update(
                settings.api_key,
                _env_value(env, "LLM_API_KEY", "API_KEY", default=""),
            )
            # Test with provided settings (before saving)
            config = LLMConfig(
                provider=settings.provider,
                base_url=settings.base_url,
                model=settings.model,
                api_key=resolved_api_key,
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
