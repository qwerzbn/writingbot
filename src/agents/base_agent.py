# -*- coding: utf-8 -*-
"""
BaseAgent - Unified base class for all WritingBot agents.

Provides:
- LLM configuration from agents.yaml
- Unified call_llm() / stream_llm() interface
- Prompt loading via PromptManager
- Abstract process() method for subclasses

Simplified from DeepTutor's base_agent.py.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Generator

from src.services.config import get_agents_config
from src.services.llm import get_llm_client, get_llm_config, LLMClient
from src.services.prompt import get_prompt_manager


class BaseAgent(ABC):
    """
    Base class for all WritingBot agents.

    Subclasses must implement the ``process()`` method.
    """

    def __init__(
        self,
        module_name: str,
        agent_name: str,
        language: str = "zh",
    ):
        """
        Initialize BaseAgent.

        Args:
            module_name: Module name (e.g., 'chat', 'solve', 'rag')
            agent_name: Agent name (e.g., 'chat_agent')
            language: Language setting ('zh' | 'en')
        """
        self.module_name = module_name
        self.agent_name = agent_name
        self.language = language

        # Load agent parameters from agents.yaml
        agents_config = get_agents_config()
        self._agent_params = agents_config.get(module_name, {})

        # Logger
        self.logger = logging.getLogger(f"{module_name}.{agent_name}")

        # Load prompts
        try:
            self.prompts = get_prompt_manager().load_prompts(
                module_name=module_name,
                agent_name=agent_name,
                language=language,
            )
        except Exception as e:
            self.prompts = None
            self.logger.warning(f"Failed to load prompts: {e}")

    # ---- Config Getters ----

    def get_temperature(self) -> float:
        """Get temperature from agents.yaml config."""
        return self._agent_params.get("temperature", 0.7)

    def get_max_tokens(self) -> int:
        """Get max_tokens from agents.yaml config."""
        return self._agent_params.get("max_tokens", 2000)

    def get_model(self) -> str:
        """Get model name from LLM config."""
        return get_llm_config().model

    # ---- LLM Interface ----

    def call_llm(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs,
    ) -> str:
        """
        Call LLM (non-streaming).

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override temperature
            max_tokens: Override max_tokens

        Returns:
            LLM response text
        """
        client = get_llm_client()
        temp = temperature if temperature is not None else self.get_temperature()
        tokens = max_tokens if max_tokens is not None else self.get_max_tokens()

        self.logger.debug(
            f"call_llm: model={self.get_model()}, temp={temp}, max_tokens={tokens}"
        )

        return client.chat(
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
            **kwargs,
        )

    def stream_llm(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Generator[str, None, None]:
        """
        Stream LLM response.

        Args:
            messages: List of message dicts
            temperature: Override temperature
            max_tokens: Override max_tokens

        Yields:
            Text chunks
        """
        client = get_llm_client()
        temp = temperature if temperature is not None else self.get_temperature()
        tokens = max_tokens if max_tokens is not None else self.get_max_tokens()

        self.logger.debug(
            f"stream_llm: model={self.get_model()}, temp={temp}, max_tokens={tokens}"
        )

        yield from client.chat_stream(
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
            **kwargs,
        )

    # ---- Prompt Helpers ----

    def get_prompt(self, key: str, fallback: str = "") -> str:
        """
        Get a prompt template by key.

        Args:
            key: Prompt key (e.g., 'system', 'user_template')
            fallback: Fallback value if not found

        Returns:
            Prompt string
        """
        if self.prompts and key in self.prompts:
            return self.prompts[key]
        return fallback

    def has_prompts(self) -> bool:
        """Check if prompts were loaded."""
        return self.prompts is not None

    # ---- Abstract ----

    @abstractmethod
    def process(self, *args, **kwargs) -> Any:
        """Main processing logic (must be implemented by subclasses)."""

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"module={self.module_name}, "
            f"name={self.agent_name})"
        )
