# -*- coding: utf-8 -*-
"""
Generator Component
====================

Generates answers using the LLM service layer.
"""

from typing import Generator as GenType

from src.services.llm import get_llm_client


class LLMGenerator:
    """Generates answers from an LLM given context and query."""

    def __init__(self, temperature: float = 0.7, max_tokens: int = 2000):
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(self, messages: list[dict[str, str]]) -> str:
        """
        Generate a non-streaming answer.

        Args:
            messages: Messages array for OpenAI API

        Returns:
            Generated answer text
        """
        client = get_llm_client()
        return client.chat(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    def generate_stream(self, messages: list[dict[str, str]]) -> GenType[str, None, None]:
        """
        Generate a streaming answer.

        Args:
            messages: Messages array for OpenAI API

        Yields:
            Text chunks
        """
        client = get_llm_client()
        yield from client.chat_stream(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
