# -*- coding: utf-8 -*-
"""
Prompt Manager
===============

Loads prompt templates from YAML files.

Prompt files are organized as:
    src/agents/{module_name}/prompts/{language}.yaml

Each YAML file contains key-value pairs of prompt names to prompt text.
"""

from pathlib import Path
from typing import Any

import yaml


class PromptManager:
    """Manages loading and caching of prompt templates."""

    def __init__(self):
        self._cache: dict[str, dict[str, Any]] = {}
        self._agents_root = Path(__file__).parent.parent.parent / "agents"

    def load_prompts(
        self,
        module_name: str,
        agent_name: str | None = None,
        language: str = "zh",
    ) -> dict[str, Any] | None:
        """
        Load prompts for a module agent.

        Looks for: src/agents/{module_name}/prompts/{language}.yaml

        Args:
            module_name: Module name (e.g., 'chat', 'solve')
            agent_name: Agent name (unused for now, reserved for future)
            language: Language code ('zh' or 'en')

        Returns:
            Dictionary of prompt templates, or None if not found
        """
        cache_key = f"{module_name}:{language}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt_path = self._agents_root / module_name / "prompts" / f"{language}.yaml"

        if not prompt_path.exists():
            return None

        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompts = yaml.safe_load(f) or {}
            self._cache[cache_key] = prompts
            return prompts
        except Exception:
            return None

    def clear_cache(self):
        """Clear prompt cache."""
        self._cache.clear()


_prompt_manager: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    """Get the global PromptManager instance."""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager
