# -*- coding: utf-8 -*-
"""
Generator Component
====================

Generates answers using the LLM service layer.
Includes <think> tag filtering for reasoning models (Qwen3, DeepSeek-R1, etc.).
Yields a special sentinel when think-phase starts so the frontend can show status.
"""

import re
from typing import Generator as GenType

from src.services.llm import get_llm_client

# Sentinel value yielded when model starts thinking (before any visible output)
THINK_SENTINEL = "__THINK_START__"


class LLMGenerator:
    """Generates answers from an LLM given context and query."""

    def __init__(self, temperature: float = 0.7, max_tokens: int = 2000):
        self.temperature = temperature
        self.max_tokens = max_tokens

    @staticmethod
    def clean_think_tags(text: str) -> str:
        """Remove <think>...</think> blocks from completed text."""
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.DOTALL)
        return cleaned.strip()

    def generate(self, messages: list[dict[str, str]]) -> str:
        """Generate a non-streaming answer. Strips <think> tags."""
        client = get_llm_client()
        result = client.chat(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return self.clean_think_tags(result)

    def generate_stream(self, messages: list[dict[str, str]]) -> GenType[str, None, None]:
        """
        Generate a streaming answer.
        Filters out <think>...</think> blocks in real-time.
        Yields THINK_SENTINEL at the start of a think block so callers
        can show "模型正在思考..." status to the user.
        """
        client = get_llm_client()
        in_think = False
        buffer = ""

        for chunk in client.chat_stream(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        ):
            buffer += chunk

            if in_think:
                # Looking for </think> to end the thinking block
                if "</think>" in buffer:
                    _, _, after = buffer.partition("</think>")
                    buffer = ""
                    in_think = False
                    if after:
                        yield after
                else:
                    # Still thinking — cap buffer to avoid memory issues
                    if len(buffer) > 50000:
                        buffer = buffer[-1000:]
                    continue
            else:
                if "<think>" in buffer:
                    before, _, remainder = buffer.partition("<think>")
                    if before:
                        yield before
                    # Signal to caller that think phase started
                    yield THINK_SENTINEL
                    buffer = remainder
                    in_think = True

                    if "</think>" in buffer:
                        _, _, after = buffer.partition("</think>")
                        buffer = ""
                        in_think = False
                        if after:
                            yield after
                elif "<" in buffer and not buffer.endswith(">"):
                    tag_start = buffer.rfind("<")
                    possible_tag = buffer[tag_start:]
                    if "<think>"[:len(possible_tag)] == possible_tag:
                        if tag_start > 0:
                            yield buffer[:tag_start]
                        buffer = possible_tag
                    else:
                        yield buffer
                        buffer = ""
                else:
                    yield buffer
                    buffer = ""

        # Flush remaining
        if buffer and not in_think:
            yield buffer
