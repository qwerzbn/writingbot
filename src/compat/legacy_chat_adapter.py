from __future__ import annotations

from src.agent_runtime.runtime import get_agent_runtime


class ChatAgent:
    def __init__(self, language: str = "zh"):
        self.language = language

    def process(
        self,
        question: str,
        evidence_text: str = "",
        skill_directive: str = "",
        chat_history: list[dict[str, str]] | None = None,
        stream: bool = False,
    ) -> dict:
        runtime = get_agent_runtime()
        payload = {
            "message": question,
            "history": list(chat_history or []),
            "context_text": evidence_text,
            "skill_directive": skill_directive,
        }
        if stream:
            execution = runtime.prepare_content_execution("chat", payload, stream=True)
            return {"messages": execution.messages, "stream": execution.stream}
        execution = runtime.prepare_content_execution("chat", payload, stream=False)
        return {"messages": execution.messages, "content": execution.content}
