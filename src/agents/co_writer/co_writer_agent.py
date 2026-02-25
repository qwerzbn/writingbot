# -*- coding: utf-8 -*-
"""
CoWriterAgent - AI-assisted writing with edit operations.

Supported actions:
- rewrite: Rewrite text with instruction
- expand: Expand text with more detail
- shorten: Condense text
- polish: Improve style and readability
"""

from typing import Generator

from src.agents.base_agent import BaseAgent


class CoWriterAgent(BaseAgent):
    """
    Co-writing agent for text editing operations.
    """

    SUPPORTED_ACTIONS = ("rewrite", "expand", "shorten", "polish")

    def __init__(self, language: str = "zh"):
        super().__init__(
            module_name="co_writer",
            agent_name="co_writer_agent",
            language=language,
        )

    def edit(
        self,
        text: str,
        action: str = "rewrite",
        instruction: str = "",
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        """
        Apply an edit action to text.

        Args:
            text: Input text to edit
            action: Action type (rewrite/expand/shorten/polish)
            instruction: Additional user instruction (for rewrite)
            stream: Whether to stream the result

        Returns:
            Edited text (or stream generator)
        """
        if action not in self.SUPPORTED_ACTIONS:
            raise ValueError(f"Unsupported action: {action}. Use: {self.SUPPORTED_ACTIONS}")

        # Get prompt template for this action
        prompt_template = self.get_prompt(action, "")
        if not prompt_template:
            prompt_template = f"请{action}以下文本：\n\n{{text}}"

        # Format prompt
        user_prompt = prompt_template.format(text=text, instruction=instruction)

        messages = [
            {"role": "system", "content": self.get_prompt("system", "你是一个写作助手。")},
            {"role": "user", "content": user_prompt},
        ]

        if stream:
            return self.stream_llm(messages)
        return self.call_llm(messages)

    def process(
        self,
        text: str,
        action: str = "rewrite",
        instruction: str = "",
        stream: bool = False,
    ) -> dict:
        """
        Process an edit request.

        Returns:
            Dict with 'edited_text' (or 'stream')
        """
        result = self.edit(text, action, instruction, stream)

        if stream:
            return {"stream": result, "action": action}
        return {"edited_text": result, "action": action}
