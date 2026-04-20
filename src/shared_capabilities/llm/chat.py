from __future__ import annotations

from typing import Any, Generator

from src.services.llm import get_llm_client, get_llm_config


def call_chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    **kwargs: Any,
) -> str:
    return get_llm_client().chat(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


def stream_chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    **kwargs: Any,
) -> Generator[str, None, None]:
    yield from get_llm_client().chat_stream(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


def llm_identity() -> dict[str, str]:
    config = get_llm_config()
    return {"provider": config.provider, "model": config.model}
