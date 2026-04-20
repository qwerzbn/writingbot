from __future__ import annotations

from typing import Any, Generator

from src.agent_runtime.runtime import get_agent_runtime


class ResearchAgent:
    def __init__(self, language: str = "zh"):
        self.language = language

    def plan(self, topic: str) -> str:
        result = get_agent_runtime().execute_sync("research", {"topic": topic})
        return str(result.get("plan") or "")

    def generate_report(
        self,
        topic: str,
        points: str = "",
        context: str = "",
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        _ = (points, context)
        result = self.process(topic=topic, vector_store=None, stream=stream)
        if stream:
            return result["stream"]
        return result["report"]

    def process(self, topic: str, vector_store: Any = None, stream: bool = False) -> dict[str, Any]:
        runtime = get_agent_runtime()
        payload = {"topic": topic}
        if vector_store is not None:
            payload["vector_store"] = vector_store
        result = runtime.execute_sync("research", payload)
        if stream:
            return {
                "plan": result.get("plan", ""),
                "stream": self._stream_text(result.get("output", "")),
                "sources": result.get("sources", []),
            }
        return {"plan": result.get("plan", ""), "report": result.get("output", ""), "sources": result.get("sources", [])}

    @staticmethod
    def _stream_text(text: str, chunk_size: int = 240) -> Generator[str, None, None]:
        for idx in range(0, len(text), chunk_size):
            yield text[idx : idx + chunk_size]
