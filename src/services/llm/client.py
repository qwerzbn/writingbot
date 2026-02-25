# -*- coding: utf-8 -*-
"""
LLM Client
===========

Unified LLM client wrapping OpenAI-compatible APIs.
Supports both synchronous and streaming calls.
"""

from typing import Generator

from openai import OpenAI

from src.services.llm.config import LLMConfig, get_llm_config


class LLMClient:
    """Unified LLM client for OpenAI-compatible APIs."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or get_llm_config()
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """Lazy-initialize the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> str:
        """
        Synchronous chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            Generated text content
        """
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return response.choices[0].message.content

    def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> Generator[str, None, None]:
        """
        Streaming chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Yields:
            Text chunks as they arrive
        """
        stream = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
