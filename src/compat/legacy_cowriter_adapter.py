from __future__ import annotations

from typing import Generator

from src.agent_runtime.runtime import get_agent_runtime


class CoWriterAgent:
    SUPPORTED_ACTIONS = ("rewrite", "expand", "shorten", "polish")

    def __init__(self, language: str = "zh"):
        self.language = language

    def edit(
        self,
        text: str,
        action: str = "rewrite",
        instruction: str = "",
        evidence: list[dict] | None = None,
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        if action not in self.SUPPORTED_ACTIONS:
            raise ValueError(f"Unsupported action: {action}. Use: {self.SUPPORTED_ACTIONS}")
        runtime = get_agent_runtime()
        payload = {
            "text": text,
            "action": action,
            "instruction": instruction,
            "evidence": list(evidence or []),
        }
        execution = runtime.prepare_content_execution(action, payload, stream=stream)
        if stream:
            return execution.stream
        return execution.content or ""

    def process(
        self,
        text: str,
        action: str = "rewrite",
        instruction: str = "",
        evidence: list[dict] | None = None,
        stream: bool = False,
    ) -> dict:
        result = self.edit(text, action, instruction, evidence=evidence, stream=stream)
        if stream:
            return {"stream": result, "action": action, "used_sources": evidence or []}
        return {"edited_text": result, "action": action, "used_sources": evidence or []}
