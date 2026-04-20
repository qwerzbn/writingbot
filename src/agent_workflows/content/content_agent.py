from __future__ import annotations

from dataclasses import dataclass
from typing import Generator

from src.agent_runtime.state import ContentState, RuntimeState
from src.shared_capabilities.llm import call_chat_completion, stream_chat_completion
from src.shared_capabilities.prompts import get_prompt_loader


@dataclass
class ContentExecution:
    messages: list[dict[str, str]]
    content: str | None = None
    stream: Generator[str, None, None] | None = None


class ContentAgent:
    def __init__(self, *, language: str = "zh"):
        self.language = language

    def execute(self, state: RuntimeState, *, stream: bool) -> ContentExecution:
        if state.content is None:
            raise ValueError("content state is required")

        messages = self._build_messages(state.content)
        if stream:
            return ContentExecution(messages=messages, stream=stream_chat_completion(messages, **self._params(state.content)))
        return ContentExecution(
            messages=messages,
            content=call_chat_completion(messages, **self._params(state.content)),
        )

    def _build_messages(self, content: ContentState) -> list[dict[str, str]]:
        if content.mode == "chat":
            prompts = get_prompt_loader().load("chat", language=self.language) or {}
            system_prompt = prompts.get("system", "You are a careful research assistant.")
            user_template = prompts.get(
                "synthesize",
                "Question:\n{question}\n\nEvidence:\n{evidence_text}\n\nInstructions:\n{skill_directive}",
            )
            user_prompt = user_template.format(
                question=content.user_input,
                evidence_text=content.context_text or "(no local evidence)",
                skill_directive=content.skill_directive or "- Be explicit about uncertainty when evidence is missing.",
            )
            messages = [{"role": "system", "content": system_prompt}]
            for item in content.history[-8:]:
                role = item.get("role")
                text = item.get("content", "")
                if role in {"user", "assistant"} and text:
                    messages.append({"role": role, "content": text})
            messages.append({"role": "user", "content": user_prompt})
            return messages

        prompts = get_prompt_loader().load("co_writer", language=self.language) or {}
        prompt_template = prompts.get(content.mode, "Rewrite the following text:\n\n{text}")
        user_prompt = prompt_template.format(text=content.user_input, instruction=content.instruction)
        evidence_lines: list[str] = []
        for idx, item in enumerate(content.evidence_bundle[:6], start=1):
            source = item.get("source", "unknown-source")
            page = item.get("page", "?")
            excerpt = (item.get("content") or item.get("excerpt") or "").strip()
            if len(excerpt) > 180:
                excerpt = excerpt[:180] + "..."
            evidence_lines.append(f"[{idx}] {source} p.{page}: {excerpt}")
        if evidence_lines:
            user_prompt += "\n\nAvailable evidence:\n" + "\n".join(evidence_lines)
        return [
            {"role": "system", "content": prompts.get("system", "You are a writing assistant.")},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _params(content: ContentState) -> dict[str, float | int]:
        if content.mode == "chat":
            return {"temperature": 0.45, "max_tokens": 4000}
        return {"temperature": 0.5, "max_tokens": 2000}
