# -*- coding: utf-8 -*-
"""
PDF Parser - Column-Aware Text Extraction
==========================================

Implements a "LightMiner" parser using PyMuPDF with column-aware sorting
to correctly handle two-column academic paper layouts.

Output format mimics MinerU's content_list structure for downstream compatibility.
"""

import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # PyMuPDF

from src.knowledge.assets import KnowledgeAsset, normalize_ref_label


@dataclass
class TextBlock:
    """Represents a text block extracted from a PDF page."""
    content: str
    page: int
    page_width: float
    page_height: float
    x0: float
    y0: float
    x1: float
    y1: float
    block_type: str = "text"  # text, title, header, footer
    block_idx: int = 0
    line_start: int = 0
    line_end: int = 0
    
    @property
    def width(self) -> float:
        return self.x1 - self.x0
    
    @property
    def height(self) -> float:
        return self.y1 - self.y0
    
    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def line_count(self) -> int:
        lines = [line.strip() for line in str(self.content or "").splitlines() if line.strip()]
        return max(1, len(lines))


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
            sorted_blocks = self._assign_line_numbers(self._sort_blocks_column_aware(page_blocks, page.rect))
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

    def parse_with_assets(
        self,
        file_path: str,
        output_dir: Optional[str] = None,
        asset_output_dir: Optional[str] = None,
        file_id: str | None = None,
    ) -> tuple[List[dict], list[dict]]:
        """
        Parse a PDF into text content and figure/table assets.

        Args:
            file_path: Path to the PDF file
            output_dir: Optional directory to save content_list JSON
            asset_output_dir: Optional directory to write extracted asset PNGs
            file_id: Optional file id used in asset metadata

        Returns:
            Tuple of (content_list, asset_list)
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path}")

        doc = fitz.open(file_path)
        all_blocks: List[TextBlock] = []
        all_assets: list[dict] = []

        asset_dir_path = Path(asset_output_dir) if asset_output_dir else None
        if asset_dir_path:
            asset_dir_path.mkdir(parents=True, exist_ok=True)

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_blocks = self._extract_page_blocks(page, page_num + 1)
            sorted_blocks = self._assign_line_numbers(self._sort_blocks_column_aware(page_blocks, page.rect))
            all_blocks.extend(sorted_blocks)
            if asset_dir_path:
                all_assets.extend(
                    self._extract_page_assets(
                        page=page,
                        page_num=page_num + 1,
                        blocks=sorted_blocks,
                        source_name=file_path.name,
                        asset_output_dir=asset_dir_path,
                        file_id=file_id,
                    )
                )

        doc.close()

        content_list = self._blocks_to_content_list(all_blocks, file_path.name)
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            json_file = output_path / f"{file_path.stem}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(content_list, f, ensure_ascii=False, indent=2)

        return content_list, all_assets
    
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
                page_width=page.rect.width,
                page_height=page.rect.height,
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

    @staticmethod
    def _assign_line_numbers(blocks: List[TextBlock]) -> List[TextBlock]:
        current_line = 1
        for block in blocks:
            block.line_start = current_line
            block.line_end = current_line + block.line_count - 1
            current_line = block.line_end + 1
        return blocks
    
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
                    "page_width": block.page_width,
                    "page_height": block.page_height,
                    "block_idx": block.block_idx,
                    "bbox": [block.x0, block.y0, block.x1, block.y1],
                    "line_start": block.line_start,
                    "line_end": block.line_end,
                }
            }
            content_list.append(item)
        
        return content_list

    @staticmethod
    def _is_caption_text(text: str) -> bool:
        compact = re.sub(r"\s+", " ", (text or "").strip())
        if not compact:
            return False
        return bool(re.match(r"^(?:fig(?:ure)?|table|图|表)[\s\.:：-]*[A-Za-z]?\d+", compact, flags=re.IGNORECASE))

    @staticmethod
    def _asset_kind(text: str) -> str:
        compact = (text or "").strip().lower()
        if compact.startswith("table") or compact.startswith("表"):
            return "table"
        return "figure"

    def _extract_page_assets(
        self,
        page: fitz.Page,
        page_num: int,
        blocks: List[TextBlock],
        source_name: str,
        asset_output_dir: Path,
        file_id: str | None = None,
    ) -> list[dict]:
        caption_blocks = [block for block in blocks if self._is_caption_text(block.content)]
        if not caption_blocks:
            return []

        caption_blocks.sort(key=lambda block: block.y0)
        assets: list[dict] = []
        page_rect = page.rect

        for idx, caption_block in enumerate(caption_blocks, start=1):
            kind = self._asset_kind(caption_block.content)
            prev_caption = caption_blocks[idx - 2] if idx >= 2 else None
            next_caption = caption_blocks[idx] if idx < len(caption_blocks) else None
            clip = self._estimate_asset_bbox(
                page_rect=page_rect,
                caption_block=caption_block,
                prev_caption=prev_caption,
                next_caption=next_caption,
                kind=kind,
            )
            if clip is None:
                continue

            ref_label = normalize_ref_label(caption_block.content, fallback_kind=kind, default_index=idx)
            image_file = asset_output_dir / f"{page_num:03d}_{ref_label.replace(' ', '_').replace('.', '').lower()}_{uuid.uuid4().hex[:8]}.png"
            pixmap = page.get_pixmap(clip=fitz.Rect(*clip), matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            pixmap.save(str(image_file))

            nearby_blocks = self._neighbor_blocks(blocks, caption_block, limit=3)
            nearby_text = "\n".join(block.content for block in nearby_blocks if block.content.strip()).strip()
            asset = KnowledgeAsset(
                id=str(uuid.uuid4()),
                kind=kind,
                page=page_num,
                bbox=[float(v) for v in clip],
                page_width=float(page_rect.width),
                page_height=float(page_rect.height),
                caption=re.sub(r"\s+", " ", caption_block.content).strip(),
                ref_label=ref_label,
                image_path=str(image_file),
                source_file=source_name,
                file_id=str(file_id or ""),
                nearby_text=nearby_text,
                visual_summary=re.sub(
                    r"^(?:fig(?:ure)?|table|图|表)[\s\.:-]*[A-Za-z]?\d+(?:\.\d+)?[\s\.:-]*",
                    "",
                    re.sub(r"\s+", " ", caption_block.content).strip(),
                    flags=re.IGNORECASE,
                ).strip(),
            )
            assets.append(asset.to_dict())

        return assets

    @staticmethod
    def _neighbor_blocks(blocks: List[TextBlock], caption_block: TextBlock, limit: int = 3) -> List[TextBlock]:
        scored: list[tuple[float, TextBlock]] = []
        for block in blocks:
            if block.block_idx == caption_block.block_idx:
                continue
            vertical_gap = abs(((block.y0 + block.y1) / 2) - ((caption_block.y0 + caption_block.y1) / 2))
            if vertical_gap > 220:
                continue
            scored.append((vertical_gap, block))
        scored.sort(key=lambda item: item[0])
        return [block for _, block in scored[:limit]]

    @staticmethod
    def _estimate_asset_bbox(
        page_rect: fitz.Rect,
        caption_block: TextBlock,
        prev_caption: TextBlock | None,
        next_caption: TextBlock | None,
        kind: str,
    ) -> list[float] | None:
        pad_x = 18.0
        top_bound = page_rect.y0 + 18.0
        bottom_bound = page_rect.y1 - 18.0
        prev_edge = prev_caption.y1 + 8.0 if prev_caption else top_bound
        next_edge = next_caption.y0 - 8.0 if next_caption else bottom_bound

        if kind == "figure":
            y0 = max(prev_edge, caption_block.y0 - 360.0)
            y1 = min(next_edge, caption_block.y1 + 48.0)
        else:
            y0 = max(prev_edge, caption_block.y0 - 24.0)
            y1 = min(next_edge, caption_block.y1 + 360.0)

        if y1 - y0 < 96.0:
            if kind == "figure":
                y0 = max(top_bound, caption_block.y0 - 260.0)
                y1 = min(bottom_bound, caption_block.y1 + 80.0)
            else:
                y0 = max(top_bound, caption_block.y0 - 40.0)
                y1 = min(bottom_bound, caption_block.y1 + 260.0)

        if y1 - y0 < 80.0:
            return None

        x0 = page_rect.x0 + pad_x
        x1 = page_rect.x1 - pad_x
        return [x0, y0, x1, y1]


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
