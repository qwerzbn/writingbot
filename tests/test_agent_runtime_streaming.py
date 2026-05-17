from __future__ import annotations

from src.agent_runtime.runtime import AgentRuntime
from src.agent_workflows.content.content_agent import ContentExecution


def test_stream_run_yields_content_agent_stream_chunks(monkeypatch):
    runtime = AgentRuntime()
    seen_stream_flags: list[bool] = []

    def fake_execute(state, *, stream: bool):
        seen_stream_flags.append(stream)
        messages = [{"role": "user", "content": state.content.user_input}]
        if stream:
            return ContentExecution(messages=messages, stream=(chunk for chunk in ["hello", " world"]))
        return ContentExecution(messages=messages, content="one-shot")

    monkeypatch.setattr(runtime.content_agent, "execute", fake_execute)

    run_info = runtime.create_run("chat_research", {"message": "Stream please"})
    events = list(runtime.stream_run(run_info["run_id"]))

    chunks = [str(event.get("content") or "") for event in events if event.get("type") == "chunk"]
    done = [event for event in events if event.get("type") == "done"]

    assert seen_stream_flags == [True]
    assert chunks == ["hello", " world", " (inference)"]
    assert done[-1]["output"] == "hello world (inference)"
