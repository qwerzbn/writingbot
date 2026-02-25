# -*- coding: utf-8 -*-
"""
LLM Configuration
==================

Reads LLM settings from environment variables.
Supports OpenAI, Ollama, and any OpenAI-compatible API.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    """LLM configuration data class."""
    provider: str
    base_url: str
    model: str
    api_key: str

    @property
    def is_enabled(self) -> bool:
        """Check if LLM is properly configured."""
        return bool(self.api_key and self.api_key != "your_api_key_here")


_llm_config: LLMConfig | None = None


def get_llm_config() -> LLMConfig:
    """
    Get LLM configuration from environment variables.

    Returns:
        LLMConfig instance
    """
    global _llm_config
    if _llm_config is None:
        _llm_config = LLMConfig(
            provider=os.getenv("LLM_PROVIDER", "ollama"),
            base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
            model=os.getenv("LLM_MODEL", "qwen3:0.6b"),
            api_key=os.getenv("LLM_API_KEY", "ollama"),
        )
    return _llm_config
