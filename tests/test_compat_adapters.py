from __future__ import annotations

from src.agent_runtime.runtime import AgentRuntime
from src.agent_workflows.content.content_agent import ContentExecution
from src.compat.legacy_chat_adapter import ChatAgent
from src.compat.legacy_cowriter_adapter import CoWriterAgent


def test_legacy_chat_and_cowriter_share_runtime_content_backend(monkeypatch):
    runtime = AgentRuntime()
    seen_modes: list[str] = []

    def fake_execute(state, *, stream: bool):
        seen_modes.append(state.content.mode)
        return ContentExecution(messages=[{"role": "user", "content": state.content.user_input}], content="stub")

    monkeypatch.setattr(runtime.content_agent, "execute", fake_execute)
    monkeypatch.setattr("src.compat.legacy_chat_adapter.get_agent_runtime", lambda: runtime)
    monkeypatch.setattr("src.compat.legacy_cowriter_adapter.get_agent_runtime", lambda: runtime)

    chat_result = ChatAgent().process("Explain this", stream=False)
    rewrite_result = CoWriterAgent().process("Draft text", action="rewrite", stream=False)

    assert chat_result["content"] == "stub (inference)"
    assert rewrite_result["edited_text"] == "stub"
    assert seen_modes == ["chat", "rewrite"]
