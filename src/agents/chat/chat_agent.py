# -*- coding: utf-8 -*-
"""
ChatAgent - KB-aware academic conversation agent.

Provides a concrete chat agent so the orchestrator never instantiates the
abstract BaseAgent directly.
"""

from __future__ import annotations

from typing import Generator

from src.agents.base_agent import BaseAgent


class ChatAgent(BaseAgent):
    """Chat agent for evidence-grounded academic answers."""

    def __init__(self, language: str = "zh"):
        super().__init__(
            module_name="chat",
            agent_name="chat_agent",
            language=language,
        )

    def process(
        self,
        question: str,
        evidence_text: str = "",
        skill_directive: str = "",
        chat_history: list[dict[str, str]] | None = None,
        stream: bool = False,
    ) -> dict:
        """Generate a chat answer from question + evidence."""
        system_prompt = self.get_prompt("system", "你是严谨的智能论文助手。")
        user_template = self.get_prompt(
            "synthesize",
            "问题：{question}\n证据：\n{evidence_text}\n\n结构化详尽回答该问题。技能指令：\n{skill_directive}",
        )
        user_prompt = user_template.format(
            question=question,
            evidence_text=evidence_text or "(无证据)",
            skill_directive=skill_directive or "- 回答需要围绕科研写作，尽量给出可验证依据。",
        )

        messages = [{"role": "system", "content": system_prompt}]
        for item in (chat_history or [])[-8:]:
            role = item.get("role")
            content = item.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_prompt})

        if stream:
            return {"messages": messages, "stream": self.stream_llm(messages)}
        return {"messages": messages, "content": self.call_llm(messages)}
