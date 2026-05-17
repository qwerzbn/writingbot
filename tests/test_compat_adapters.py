from __future__ import annotations

from src.agent_runtime.runtime import AgentRuntime
from src.agent_workflows.content.content_agent import ContentExecution
from src.compat.legacy_chat_adapter import ChatAgent
from src.compat.legacy_cowriter_adapter import CoWriterAgent


def test_legacy_chat_and_cowriter_share_runtime_content_backend(monkeypatch):
    runtime = AgentRuntime()
    seen_modes: list[str] = []
    seen_contexts: list[str] = []
    seen_skill_directives: list[str] = []
    seen_evidence_counts: list[int] = []

    def fake_execute(state, *, stream: bool):
        seen_modes.append(state.content.mode)
        seen_contexts.append(state.content.context_text)
        seen_skill_directives.append(state.content.skill_directive)
        seen_evidence_counts.append(len(state.content.evidence_bundle))
        return ContentExecution(messages=[{"role": "user", "content": state.content.user_input}], content="stub")

    monkeypatch.setattr(runtime.content_agent, "execute", fake_execute)
    monkeypatch.setattr("src.compat.legacy_chat_adapter.get_agent_runtime", lambda: runtime)
    monkeypatch.setattr("src.compat.legacy_cowriter_adapter.get_agent_runtime", lambda: runtime)

    chat_result = ChatAgent().process(
        "Explain this",
        evidence_text="Evidence block",
        skill_directive="Use strict citations.",
        stream=False,
    )
    rewrite_result = CoWriterAgent().process(
        "Draft text",
        action="rewrite",
        evidence=[{"source": "paper.pdf", "page": 1, "content": "Grounded evidence"}],
        stream=False,
    )

    assert chat_result["content"] == "stub (inference)"
    assert rewrite_result["edited_text"] == "stub"
    assert seen_modes == ["chat", "rewrite"]
    assert seen_contexts == ["Evidence block", ""]
    assert seen_skill_directives == ["Use strict citations.", ""]
    assert seen_evidence_counts == [0, 1]
