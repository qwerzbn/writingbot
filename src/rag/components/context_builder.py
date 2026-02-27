# -*- coding: utf-8 -*-
"""
Context Builder Component
==========================

Builds context strings and source lists from retrieved documents.
Context is formatted cleanly for LLM consumption — source metadata
is tracked separately and NOT embedded in the context text.
"""


class ContextBuilder:
    """Builds formatted context from retrieved documents."""

    def __init__(self, max_context_length: int = 4000):
        """
        Args:
            max_context_length: Maximum character length for context
        """
        self.max_context_length = max_context_length

    def build(self, results: list[dict]) -> tuple[str, list[dict]]:
        """
        Build context string and source list from retrieval results.

        The context string contains ONLY document content (no source markers).
        Sources are tracked separately to avoid LLM regurgitating metadata.

        Args:
            results: List of retrieval results

        Returns:
            Tuple of (context_string, sources_list)
        """
        if not results:
            return "", []

        context_parts = []
        sources = []
        total_length = 0

        for i, result in enumerate(results, 1):
            content = result.get("content", result.get("text", ""))
            metadata = result.get("metadata", {})

            # Check length limit
            if total_length + len(content) > self.max_context_length:
                break

            source_name = metadata.get("source", "Unknown")
            page = metadata.get("page", "?")

            # Context: numbered content ONLY, no source metadata
            context_parts.append(f"[{i}] {content}")
            total_length += len(content)

            # Sources tracked separately for frontend display
            sources.append({
                "content": content[:200],
                "source": source_name,
                "page": page,
                "score": result.get("score", 0),
            })

        context = "\n\n".join(context_parts) if context_parts else ""
        return context, sources
