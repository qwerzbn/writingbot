# -*- coding: utf-8 -*-
"""
Semantic Chunker - Separator-based Text Chunking
=================================================

Replicates DeepTutor's chunking strategy:
- Split on semantic separators (\n\n, \n, ". ", " ")
- Maintain chunk overlap for context continuity
- Preserve metadata through chunking

This is "Recursive Character Splitting" with paragraph-awareness.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Chunk:
    """A text chunk with metadata."""
    content: str
    chunk_type: str = "text"
    chunk_idx: int = 0
    metadata: dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "chunk_type": self.chunk_type,
            "chunk_idx": self.chunk_idx,
            "metadata": self.metadata
        }


class SemanticChunker:
    """
    Semantic chunker using separator-based splitting.
    
    Replicates DeepTutor's SemanticChunker logic exactly:
    - Target chunk_size with best-effort separator alignment
    - Overlap between chunks for context preservation
    - Separators priority: \n\n > \n > ". " > " "
    """
    
    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " "]
    
    def __init__(self,
                 chunk_size: int = 1000,
                 chunk_overlap: int = 200,
                 separators: Optional[List[str]] = None):
        """
        Initialize the semantic chunker.
        
        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between consecutive chunks
            separators: List of separators, in priority order
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS
    
    def chunk_text(self, text: str, metadata: Optional[dict] = None) -> List[Chunk]:
        """
        Split text into chunks.
        
        Args:
            text: Input text to chunk
            metadata: Optional metadata to attach to all chunks
            
        Returns:
            List of Chunk objects
        """
        if not text or not text.strip():
            return []
        
        chunks = []
        current_pos = 0
        chunk_idx = 0
        
        while current_pos < len(text):
            # Determine end position
            end_pos = min(current_pos + self.chunk_size, len(text))
            
            # Try to find a natural break point
            if end_pos < len(text):
                best_break = self._find_best_break(text, current_pos, end_pos)
                if best_break > current_pos:
                    end_pos = best_break
            
            # Extract chunk text
            chunk_text = text[current_pos:end_pos].strip()
            
            if chunk_text:
                chunk_metadata = {
                    "start_pos": current_pos,
                    "end_pos": end_pos,
                    **(metadata or {})
                }
                
                chunks.append(Chunk(
                    content=chunk_text,
                    chunk_idx=chunk_idx,
                    metadata=chunk_metadata
                ))
                chunk_idx += 1
            
            # Move to next position with overlap
            current_pos = end_pos - self.chunk_overlap
            
            # Prevent infinite loop at end
            if current_pos >= len(text) - self.chunk_overlap:
                break
        
        return chunks
    
    def _find_best_break(self, text: str, start: int, end: int) -> int:
        """
        Find the best break point within the range [start, end].
        
        Searches backwards from end for separators in priority order.
        
        Args:
            text: Full text
            start: Range start position
            end: Range end position
            
        Returns:
            Best break position (end of separator), or original end if no good break found
        """
        # Search in the last portion of the chunk for a separator
        search_start = max(start + self.chunk_size - 200, start)
        
        for sep in self.separators:
            sep_pos = text.rfind(sep, search_start, end)
            if sep_pos > start:
                # Return position after the separator
                return sep_pos + len(sep)
        
        # No good break found, use original end
        return end
    
    def chunk_content_list(self, content_list: List[dict]) -> List[Chunk]:
        """
        Chunk a MinerU-style content_list.
        
        Args:
            content_list: List of content items from PDF parser
            
        Returns:
            List of Chunk objects with preserved metadata
        """
        # Concatenate all text content
        texts = []
        segments: list[dict] = []

        current_pos = 0
        for item in content_list:
            content = item.get("content", "")
            if content:
                metadata = item.get("metadata", {}) or {}
                start_pos = current_pos
                end_pos = start_pos + len(content)
                segments.append(
                    {
                        "start": start_pos,
                        "end": end_pos,
                        "content": content,
                        "metadata": metadata,
                    }
                )
                texts.append(content)
                current_pos = end_pos + 2  # +2 for \n\n separator
        
        # Join with double newlines (paragraph separator)
        full_text = "\n\n".join(texts)
        
        # Chunk the full text
        chunks = self.chunk_text(full_text)
        
        # Enrich chunk metadata with page/span info
        for chunk in chunks:
            start_pos = int(chunk.metadata.get("start_pos", 0) or 0)
            end_pos = int(chunk.metadata.get("end_pos", start_pos) or start_pos)
            overlaps = self._collect_overlap_segments(segments, start_pos, end_pos)
            if not overlaps:
                continue

            primary_page = self._select_primary_page(overlaps)
            page_spans = [span for span in overlaps if span.get("page") == primary_page] or overlaps
            first = page_spans[0]
            bbox = self._merge_bbox(page_spans)
            line_numbers = [
                int(span.get("line_start"))
                for span in page_spans
                if span.get("line_start") is not None
            ]
            line_ends = [
                int(span.get("line_end"))
                for span in page_spans
                if span.get("line_end") is not None
            ]

            chunk.metadata["page"] = first.get("page")
            chunk.metadata["source"] = first.get("source", "")
            chunk.metadata["bbox"] = bbox
            chunk.metadata["line_start"] = min(line_numbers) if line_numbers else None
            chunk.metadata["line_end"] = max(line_ends) if line_ends else None
            chunk.metadata["page_width"] = first.get("page_width")
            chunk.metadata["page_height"] = first.get("page_height")
            chunk.metadata["spans"] = page_spans
            chunk.metadata["highlight_boxes"] = [
                {
                    "page": span.get("page"),
                    "bbox": span.get("bbox"),
                    "line_start": span.get("line_start"),
                    "line_end": span.get("line_end"),
                    "page_width": span.get("page_width"),
                    "page_height": span.get("page_height"),
                }
                for span in page_spans
                if span.get("bbox")
            ]
        
        return chunks

    @staticmethod
    def _collect_overlap_segments(segments: list[dict], start: int, end: int) -> list[dict]:
        overlaps: list[dict] = []
        for segment in segments:
            segment_start = int(segment.get("start", 0) or 0)
            segment_end = int(segment.get("end", segment_start) or segment_start)
            overlap = max(0, min(end, segment_end) - max(start, segment_start))
            if overlap <= 0:
                continue
            metadata = segment.get("metadata", {}) or {}
            overlaps.append(
                {
                    "content": segment.get("content", ""),
                    "page": metadata.get("page"),
                    "source": metadata.get("source"),
                    "bbox": metadata.get("bbox"),
                    "block_idx": metadata.get("block_idx"),
                    "line_start": metadata.get("line_start"),
                    "line_end": metadata.get("line_end"),
                    "page_width": metadata.get("page_width"),
                    "page_height": metadata.get("page_height"),
                    "overlap": overlap,
                }
            )
        overlaps.sort(key=lambda item: (item.get("page") or 0, item.get("line_start") or 0, item.get("block_idx") or 0))
        return overlaps

    @staticmethod
    def _select_primary_page(spans: list[dict]) -> int | None:
        page_scores: dict[int, int] = {}
        for span in spans:
            page = span.get("page")
            if not isinstance(page, int):
                continue
            page_scores[page] = page_scores.get(page, 0) + int(span.get("overlap", 0) or 0)
        if not page_scores:
            return spans[0].get("page") if spans else None
        return max(page_scores.items(), key=lambda item: item[1])[0]

    @staticmethod
    def _merge_bbox(spans: list[dict]) -> list[float] | None:
        boxes = [span.get("bbox") for span in spans if isinstance(span.get("bbox"), list) and len(span.get("bbox")) == 4]
        if not boxes:
            return None
        return [
            min(float(box[0]) for box in boxes),
            min(float(box[1]) for box in boxes),
            max(float(box[2]) for box in boxes),
            max(float(box[3]) for box in boxes),
        ]


# Convenience function
def chunk_text(text: str, 
               chunk_size: int = 1000, 
               chunk_overlap: int = 200) -> List[Chunk]:
    """
    Chunk text using semantic chunking.
    
    Args:
        text: Input text
        chunk_size: Target chunk size
        chunk_overlap: Overlap between chunks
        
    Returns:
        List of Chunk objects
    """
    chunker = SemanticChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return chunker.chunk_text(text)
