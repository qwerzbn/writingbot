# -*- coding: utf-8 -*-
"""
ChatAgent - Conversational AI with RAG support.

Features:
- Multi-turn conversation with history management
- RAG context retrieval via pipeline system
- Streaming and non-streaming responses
"""

from typing import Any, Generator

from src.agents.base_agent import BaseAgent
from src.rag.factory import create_pipeline


class ChatAgent(BaseAgent):
    """
    Chat agent with RAG pipeline support.

    Uses the pipeline factory to create RAG pipelines for retrieval
    and generation, replacing direct VectorStore/LLM calls.
    """

    def __init__(
        self,
        language: str = "zh",
        max_history_messages: int = 20,
        pipeline_type: str = "naive",
    ):
        """
        Initialize ChatAgent.

        Args:
            language: Language setting
            max_history_messages: Max messages to include in context
            pipeline_type: RAG pipeline type ('naive' for now)
        """
        super().__init__(
            module_name="chat",
            agent_name="chat_agent",
            language=language,
        )
        self.max_history_messages = max_history_messages
        self.pipeline_type = pipeline_type

    def _get_pipeline(self, vector_store: Any):
        """Create a RAG pipeline for the given vector store."""
        return create_pipeline(
            self.pipeline_type,
            vector_store,
            top_k=self._agent_params.get("top_k", 5),
            temperature=self.get_temperature(),
            max_tokens=self.get_max_tokens(),
        )

    def _truncate_history(
        self, history: list[dict[str, str]] | None
    ) -> list[dict[str, str]] | None:
        """Truncate history to max_history_messages."""
        if not history:
            return None
        return history[-self.max_history_messages:]

    def _build_no_rag_messages(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Build messages for non-RAG chat (fallback)."""
        system_prompt = self.get_prompt(
            "system_no_context",
            self.get_prompt("system", "You are a helpful assistant."),
        )
        messages = [{"role": "system", "content": system_prompt}]

        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})
        return messages

    def process(
        self,
        message: str,
        vector_store: Any = None,
        history: list[dict[str, str]] | None = None,
        stream: bool = False,
    ) -> dict | Generator:
        """
        Process a chat message.

        Args:
            message: User message
            vector_store: VectorStore instance for RAG
            history: Conversation history
            stream: Whether to stream the response

        Returns:
            If stream=False: dict with 'answer' and 'sources'
            If stream=True: dict with 'stream' generator and 'sources'
        """
        history = self._truncate_history(history)

        # If no vector store, use direct LLM (no RAG)
        if not vector_store:
            messages = self._build_no_rag_messages(message, history)
            if stream:
                return {
                    "stream": self.stream_llm(messages),
                    "sources": [],
                    "context": "",
                }
            else:
                return {
                    "answer": self.call_llm(messages),
                    "sources": [],
                    "context": "",
                }

        # Use RAG pipeline
        pipeline = self._get_pipeline(vector_store)

        if stream:
            chunk_stream, metadata = pipeline.query_stream(message, history=history)
            return {
                "stream": chunk_stream,
                "sources": metadata.get("sources", []),
                "context": metadata.get("context", ""),
            }
        else:
            result = pipeline.query(message, history=history)
            return {
                "answer": result.answer,
                "sources": result.sources,
                "context": result.context,
            }
