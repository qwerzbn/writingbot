# -*- coding: utf-8 -*-
"""
Generator Component
====================

Generates answers using the LLM service layer.
Includes <think> tag filtering for reasoning models (Qwen3, DeepSeek-R1, etc.).
"""

import re
from typing import Generator as GenType

from src.services.llm import get_llm_client


class LLMGenerator:
    """Generates answers from an LLM given context and query."""

    def __init__(self, temperature: float = 0.7, max_tokens: int = 2000):
        self.temperature = temperature
        self.max_tokens = max_tokens

    @staticmethod
    def clean_think_tags(text: str) -> str:
        """
        Remove <think>...</think> blocks from completed text.
        These are reasoning traces from models like Qwen3 and DeepSeek-R1.
        """
        # Remove complete <think>...</think> blocks (including multiline)
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        # Remove any remaining opening <think> tag (in case of incomplete block)
        cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.DOTALL)
        return cleaned.strip()

    def generate(self, messages: list[dict[str, str]]) -> str:
        """
        Generate a non-streaming answer.
        Automatically strips <think> tags from the response.
        """
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
        Filters out <think>...</think> blocks in real-time so the user
        only sees the actual answer, not the model's internal reasoning.
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
                    # Discard everything up to and including </think>
                    _, _, after = buffer.partition("</think>")
                    buffer = ""
                    in_think = False
                    if after:
                        yield after
                else:
                    # Still in think block, don't yield, keep buffering
                    # But cap buffer size to avoid memory issues
                    if len(buffer) > 50000:
                        buffer = buffer[-1000:]
                    continue
            else:
                # Looking for <think> tags
                if "<think>" in buffer:
                    # Yield everything before <think>
                    before, _, remainder = buffer.partition("<think>")
                    if before:
                        yield before
                    buffer = remainder
                    in_think = True

                    # Check if </think> is already in the remainder
                    if "</think>" in buffer:
                        _, _, after = buffer.partition("</think>")
                        buffer = ""
                        in_think = False
                        if after:
                            yield after
                elif "<" in buffer and not buffer.endswith(">"):
                    # Might be a partial <think> tag, hold the buffer
                    # But only hold if the trailing part looks like it could be a tag start
                    tag_start = buffer.rfind("<")
                    possible_tag = buffer[tag_start:]
                    if "<think>"[:len(possible_tag)] == possible_tag:
                        # Could be partial, yield everything before it
                        if tag_start > 0:
                            yield buffer[:tag_start]
                        buffer = possible_tag
                    else:
                        # Not a think tag, yield everything
                        yield buffer
                        buffer = ""
                else:
                    yield buffer
                    buffer = ""

        # Flush remaining buffer
        if buffer and not in_think:
            yield buffer
