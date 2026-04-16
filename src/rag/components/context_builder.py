# -*- coding: utf-8 -*-
"""
Context Builder Component
==========================

Builds context strings and source lists from retrieved documents.
Context is formatted cleanly for LLM consumption — source metadata
is tracked separately and NOT embedded in the context text.
"""

from src.retrieval.common import build_sentence_excerpt, build_text_evidence_excerpt, clean_source_title, normalize_source_metadata


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
            metadata = normalize_source_metadata(result.get("metadata", {}))

            # Check length limit
            if total_length + len(content) > self.max_context_length:
                break

            source_name = metadata.get("source", "Unknown")
            page = metadata.get("page", "?")
            display_title = clean_source_title(metadata.get("title") or source_name)
            is_asset = bool(metadata.get("asset_id") or metadata.get("asset_type"))
            summary = build_sentence_excerpt(content, limit=160, max_sentences=1) if is_asset else ""
            excerpt = (
                build_sentence_excerpt(content, limit=320, max_sentences=2)
                if is_asset
                else build_text_evidence_excerpt(content, metadata=metadata, limit=320)
            )

            # Context: numbered content ONLY, no source metadata
            context_parts.append(f"[{i}] {content}")
            total_length += len(content)

            # Sources tracked separately for frontend display
            sources.append({
                "content": excerpt or summary or content[:200],
                "source": source_name,
                "page": page,
                "line_start": metadata.get("line_start"),
                "line_end": metadata.get("line_end"),
                "bbox": metadata.get("bbox"),
                "page_width": metadata.get("page_width"),
                "page_height": metadata.get("page_height"),
                "highlight_boxes": metadata.get("highlight_boxes") or [],
                "score": result.get("score", 0),
                "title": display_title,
                "summary": summary,
                "excerpt": excerpt,
                "file_id": metadata.get("file_id"), # Required for PDF viewer
                "asset_id": metadata.get("asset_id"),
                "asset_type": metadata.get("asset_type"),
                "caption": metadata.get("caption"),
                "ref_label": metadata.get("ref_label"),
                "image_path": metadata.get("image_path"),
                "evidence_kind": metadata.get("asset_type") or "text",
                "is_primary": False,
            })

        context = "\n\n".join(context_parts) if context_parts else ""
        return context, sources
