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
        page_markers = {}  # Track which text came from which page
        
        current_pos = 0
        for item in content_list:
            content = item.get("content", "")
            if content:
                page = item.get("metadata", {}).get("page", 0)
                source = item.get("metadata", {}).get("source", "")
                
                # Store page mapping for position
                page_markers[current_pos] = {
                    "page": page,
                    "source": source
                }
                
                texts.append(content)
                current_pos += len(content) + 2  # +2 for \n\n separator
        
        # Join with double newlines (paragraph separator)
        full_text = "\n\n".join(texts)
        
        # Chunk the full text
        chunks = self.chunk_text(full_text)
        
        # Enrich chunk metadata with page info
        for chunk in chunks:
            start_pos = chunk.metadata.get("start_pos", 0)
            # Find the closest page marker
            closest_page = 1
            closest_source = ""
            for marker_pos, marker_info in sorted(page_markers.items()):
                if marker_pos <= start_pos:
                    closest_page = marker_info["page"]
                    closest_source = marker_info["source"]
                else:
                    break
            
            chunk.metadata["page"] = closest_page
            chunk.metadata["source"] = closest_source
        
        return chunks


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
