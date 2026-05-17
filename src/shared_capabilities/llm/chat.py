from __future__ import annotations

import os
from typing import Any, Generator

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_LLM_MODEL = "qwen3.6-plus"
DEFAULT_LLM_API_KEY = "your_api_key_here"

_CLIENT: OpenAI | None = None
_CLIENT_KEY: tuple[str, str] | None = None


def _env_value(*names: str, default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value
    return default


def _llm_config() -> dict[str, str]:
    return {
        "provider": _env_value("LLM_PROVIDER", default=DEFAULT_LLM_PROVIDER),
        "base_url": _env_value("LLM_BASE_URL", "BASE_URL", default=DEFAULT_LLM_BASE_URL),
        "model": _env_value("LLM_MODEL", "MODEL_ID", default=DEFAULT_LLM_MODEL),
        "api_key": _env_value("LLM_API_KEY", "API_KEY", default=DEFAULT_LLM_API_KEY),
    }


def _client() -> OpenAI:
    global _CLIENT
    global _CLIENT_KEY
    config = _llm_config()
    key = (config["api_key"], config["base_url"])
    if _CLIENT is None or _CLIENT_KEY != key:
        _CLIENT = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
        _CLIENT_KEY = key
    return _CLIENT


def call_chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    **kwargs: Any,
) -> str:
    response = _client().chat.completions.create(
        model=_llm_config()["model"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
    return response.choices[0].message.content or ""


def stream_chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    **kwargs: Any,
) -> Generator[str, None, None]:
    stream = _client().chat.completions.create(
        model=_llm_config()["model"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        **kwargs,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def llm_identity() -> dict[str, str]:
    config = _llm_config()
    return {"provider": config["provider"], "model": config["model"]}
