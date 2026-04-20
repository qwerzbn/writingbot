from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class PromptLoader:
    def __init__(self, prompts_root: Path | None = None):
        self._cache: dict[str, dict[str, Any]] = {}
        self._prompts_root = prompts_root or Path(__file__).resolve().parents[2] / "agents"

    def load(self, module_name: str, language: str = "zh") -> dict[str, Any] | None:
        cache_key = f"{module_name}:{language}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt_path = self._prompts_root / module_name / "prompts" / f"{language}.yaml"
        if not prompt_path.exists():
            return None

        try:
            with open(prompt_path, "r", encoding="utf-8") as handle:
                prompts = yaml.safe_load(handle) or {}
        except Exception:
            return None

        self._cache[cache_key] = prompts
        return prompts

    def clear(self) -> None:
        self._cache.clear()


_prompt_loader: PromptLoader | None = None


def get_prompt_loader() -> PromptLoader:
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader
