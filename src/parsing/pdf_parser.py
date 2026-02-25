# -*- coding: utf-8 -*-
"""
PDF Parser - Column-Aware Text Extraction
==========================================

Implements a "LightMiner" parser using PyMuPDF with column-aware sorting
to correctly handle two-column academic paper layouts.

Output format mimics MinerU's content_list structure for downstream compatibility.
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # PyMuPDF


@dataclass
class TextBlock:
    """Represents a text block extracted from a PDF page."""
    content: str
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    block_type: str = "text"  # text, title, header, footer
    block_idx: int = 0
    
    @property
    def width(self) -> float:
        return self.x1 - self.x0
    
    @property
    def height(self) -> float:
        return self.y1 - self.y0
    
    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class ContentItem:
    """A content item in the MinerU-compatible content_list format."""
    type: str  # "text", "title", etc.
    content: str
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "content": self.content,
            "metadata": self.metadata
        }


class PDFParser:
    """
    Column-aware PDF parser for academic papers.
    
    Handles two-column layouts by:
    1. Detecting page width midpoint
    2. Classifying blocks as Left Column / Right Column / Spanning
    3. Sorting: Spanning -> Left (by Y) -> Right (by Y)
    """
    
    # Header/footer detection: blocks in top/bottom X% are ignored
    HEADER_FOOTER_MARGIN = 0.05  # 5%
    
    # Spanning detection: blocks wider than X% of page are considered spanning
    SPANNING_THRESHOLD = 0.7  # 70%
    
    def __init__(self, 
                 header_footer_margin: float = 0.05,
                 spanning_threshold: float = 0.7):
        """
        Initialize the PDF parser.
        
        Args:
            header_footer_margin: Fraction of page height to ignore as header/footer
            spanning_threshold: Minimum width fraction for a block to be "spanning"
        """
        self.header_footer_margin = header_footer_margin
        self.spanning_threshold = spanning_threshold
    
    def parse(self, file_path: str, output_dir: Optional[str] = None) -> List[dict]:
        """
        Parse a PDF file and return a content_list in MinerU-compatible format.
        
        Args:
            file_path: Path to the PDF file
            output_dir: Optional directory to save the content_list JSON
            
        Returns:
            List of content items (dicts with 'type', 'content', 'metadata')
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path}")
        
        doc = fitz.open(file_path)
        all_blocks: List[TextBlock] = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_blocks = self._extract_page_blocks(page, page_num + 1)
            sorted_blocks = self._sort_blocks_column_aware(page_blocks, page.rect)
            all_blocks.extend(sorted_blocks)
        
        doc.close()
        
        # Convert to content_list format
        content_list = self._blocks_to_content_list(all_blocks, file_path.name)
        
        # Optionally save to JSON
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            json_file = output_path / f"{file_path.stem}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(content_list, f, ensure_ascii=False, indent=2)
        
        return content_list
    
    def _extract_page_blocks(self, page: fitz.Page, page_num: int) -> List[TextBlock]:
        """
        Extract text blocks from a single page.
        
        Args:
            page: PyMuPDF page object
            page_num: 1-indexed page number
            
        Returns:
            List of TextBlock objects
        """
        blocks = []
        raw_blocks = page.get_text("blocks")  # Returns (x0, y0, x1, y1, text, block_no, block_type)
        
        page_height = page.rect.height
        header_y = page_height * self.header_footer_margin
        footer_y = page_height * (1 - self.header_footer_margin)
        
        for idx, block in enumerate(raw_blocks):
            # block structure: (x0, y0, x1, y1, text, block_no, block_type)
            if len(block) < 5:
                continue
            
            x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
            
            # Skip non-text blocks (images, etc.)
            if not isinstance(text, str):
                continue
            
            text = text.strip()
            if not text:
                continue
            
            # Filter header/footer
            block_center_y = (y0 + y1) / 2
            if block_center_y < header_y or block_center_y > footer_y:
                continue
            
            blocks.append(TextBlock(
                content=text,
                page=page_num,
                x0=x0, y0=y0, x1=x1, y1=y1,
                block_idx=idx
            ))
        
        return blocks
    
    def _sort_blocks_column_aware(self, 
                                   blocks: List[TextBlock], 
                                   page_rect: fitz.Rect) -> List[TextBlock]:
        """
        Sort blocks respecting two-column layout.
        
        Strategy:
        1. Identify spanning blocks (titles, abstracts)
        2. Separate left and right column blocks
        3. Sequence: Spanning (at top) -> Left Column (by Y) -> Right Column (by Y)
        
        Args:
            blocks: List of TextBlock objects
            page_rect: Page rectangle for dimensions
            
        Returns:
            Sorted list of TextBlock objects
        """
        if not blocks:
            return []
        
        page_width = page_rect.width
        mid_x = page_width / 2
        spanning_width = page_width * self.spanning_threshold
        
        spanning_blocks = []
        left_blocks = []
        right_blocks = []
        
        for block in blocks:
            # Check if spanning (wide block)
            if block.width >= spanning_width:
                spanning_blocks.append(block)
            # Check if center is on left or right
            elif block.center_x < mid_x:
                left_blocks.append(block)
            else:
                right_blocks.append(block)
        
        # Sort each group by Y position
        spanning_blocks.sort(key=lambda b: b.y0)
        left_blocks.sort(key=lambda b: b.y0)
        right_blocks.sort(key=lambda b: b.y0)
        
        # Separate spanning blocks that appear at top vs bottom
        # Top spanning blocks go first, bottom spanning blocks go last
        if spanning_blocks:
            avg_y = sum(b.y0 for b in blocks) / len(blocks)
            top_spanning = [b for b in spanning_blocks if b.y0 < avg_y]
            bottom_spanning = [b for b in spanning_blocks if b.y0 >= avg_y]
        else:
            top_spanning = []
            bottom_spanning = []
        
        # Final order: Top Spanning -> Left Column -> Right Column -> Bottom Spanning
        return top_spanning + left_blocks + right_blocks + bottom_spanning
    
    def _blocks_to_content_list(self, 
                                 blocks: List[TextBlock], 
                                 source_name: str) -> List[dict]:
        """
        Convert TextBlock objects to MinerU-compatible content_list format.
        
        Args:
            blocks: List of TextBlock objects
            source_name: Original file name for metadata
            
        Returns:
            List of content item dicts
        """
        content_list = []
        
        for block in blocks:
            item = {
                "type": block.block_type,
                "content": block.content,
                "metadata": {
                    "source": source_name,
                    "page": block.page,
                    "block_idx": block.block_idx,
                    "bbox": [block.x0, block.y0, block.x1, block.y1]
                }
            }
            content_list.append(item)
        
        return content_list


# Convenience function
def parse_pdf(file_path: str, output_dir: Optional[str] = None) -> List[dict]:
    """
    Parse a PDF file and return structured content list.
    
    Args:
        file_path: Path to PDF file
        output_dir: Optional directory to save JSON output
        
    Returns:
        List of content items with text and metadata
    """
    parser = PDFParser()
    return parser.parse(file_path, output_dir)
