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

DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_LLM_MODEL = "qwen3.6-plus"
DEFAULT_LLM_API_KEY = "your_api_key_here"


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


def _env_value(*names: str, default: str) -> str:
    """Return the first non-empty environment value among aliases."""
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value
    return default


def get_llm_config() -> LLMConfig:
    """
    Get LLM configuration from environment variables.

    Returns:
        LLMConfig instance
    """
    global _llm_config
    if _llm_config is None:
        _llm_config = LLMConfig(
            provider=_env_value("LLM_PROVIDER", default=DEFAULT_LLM_PROVIDER),
            base_url=_env_value("LLM_BASE_URL", "BASE_URL", default=DEFAULT_LLM_BASE_URL),
            model=_env_value("LLM_MODEL", "MODEL_ID", default=DEFAULT_LLM_MODEL),
            api_key=_env_value("LLM_API_KEY", "API_KEY", default=DEFAULT_LLM_API_KEY),
        )
    return _llm_config
