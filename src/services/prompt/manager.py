# -*- coding: utf-8 -*-
"""Compatibility wrapper for the shared prompt loader."""

from __future__ import annotations

from typing import Any

from src.shared_capabilities.prompts import PromptLoader, get_prompt_loader


class PromptManager:
    def __init__(self) -> None:
        self._loader = get_prompt_loader()

    def load_prompts(
        self,
        module_name: str,
        agent_name: str | None = None,
        language: str = "zh",
    ) -> dict[str, Any] | None:
        _ = agent_name
        return self._loader.load(module_name, language=language)

    def clear_cache(self) -> None:
        self._loader.clear()


_prompt_manager: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager
