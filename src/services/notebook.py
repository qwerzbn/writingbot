# -*- coding: utf-8 -*-
"""
NotebookLM-style notebook service.

Storage layout:
  data/notebooklm/notebooks/<notebook_id>/
    manifest.json
    assets/
    bodies/
    sources/
    source_chunks/
    embeddings/
    chat_sessions/
    studio_outputs/
    notes/
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.processing.semantic_chunker import SemanticChunker
from src.retrieval.common import (
    build_sentence_excerpt,
    build_text_evidence_excerpt,
    clean_source_title,
    format_page_locator,
    normalize_display_text,
    summarize_display_text,
    tokenize,
)
from src.services.config import get_main_config


def _now_iso() -> str:
    return datetime.now().isoformat()


def _safe_json_load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def _safe_json_save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _slugify(text: str, fallback: str = "source") -> str:
    normalized = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", (text or "").strip()).strip("-")
    return normalized[:80] or fallback


def _normalize_whitespace(text: str) -> str:
    return normalize_display_text(text, preserve_paragraphs=True)


def _summarize_text(text: str, limit: int = 220) -> str:
    return summarize_display_text(text, limit)


def _word_count(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text))


def _dedupe_citations(rows: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("source_id") or ""),
            str(row.get("locator") or ""),
            str(row.get("excerpt") or "")[:120],
        )
        if key in seen:
            continue
        seen.add(key)
        payload = {**row, "index": len(deduped) + 1}
        deduped.append(payload)
        if len(deduped) >= limit:
            break
    return deduped


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self.title: str = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in {"p", "div", "section", "article", "br", "li", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "section", "article", "li"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if not stripped:
            return
        if self._in_title and not self.title:
            self.title = stripped
        self._parts.append(stripped)

    def text(self) -> str:
        return _normalize_whitespace(" ".join(self._parts))


@dataclass
class RetrievedChunk:
    chunk_id: str
    source_id: str
    source_title: str
    content: str
    score: float
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    bbox: list[float] | None = None
    page_width: float | None = None
    page_height: float | None = None
    highlight_boxes: list[dict[str, Any]] | None = None
    spans: list[dict[str, Any]] | None = None
    kind: str = "text"
    match_reasons: tuple[str, ...] = ()


class NotebookConflictError(ValueError):
    def __init__(self, latest: dict[str, Any], message: str = "Note has been updated by another request") -> None:
        super().__init__(message)
        self.latest = latest


class NotebookManager:
    STOPWORDS = {
        "the",
        "and",
        "for",
        "that",
        "this",
        "with",
        "from",
        "into",
        "your",
        "have",
        "will",
        "about",
        "研究",
        "来源",
        "笔记",
        "内容",
        "一个",
        "一种",
        "在",
        "的",
        "了",
        "和",
    }

    def __init__(self, data_dir: Path | str | None = None):
        if data_dir is None:
            config = get_main_config()
            data_dir = Path(config.get("paths", {}).get("data_dir", "./data"))
        self.data_dir = Path(data_dir)
        self.base_dir = self.data_dir / "notebooklm"
        (self.base_dir / "notebooks").mkdir(parents=True, exist_ok=True)
        self._kb_manager = None
        self._pdf_parser = None
        self._embedding_fn = None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get_kb_manager(self):
        if self._kb_manager is None:
            from src.knowledge.kb_manager import KnowledgeBaseManager

            self._kb_manager = KnowledgeBaseManager(self.data_dir / "knowledge_bases")
        return self._kb_manager

    def _get_pdf_parser(self):
        if self._pdf_parser is None:
            from src.parsing.pdf_parser import PDFParser

            self._pdf_parser = PDFParser()
        return self._pdf_parser

    def _get_embedding_fn(self):
        if self._embedding_fn is None:
            from src.knowledge.vector_store import get_embedding_function

            provider = os.getenv("EMBEDDING_PROVIDER", "sentence-transformers")
            model = os.getenv("EMBEDDING_MODEL", "all-mpnet-base-v2")
            base_url = os.getenv("EMBEDDING_BASE_URL")
            api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY")
            self._embedding_fn = get_embedding_function(
                provider=provider,
                model=model,
                base_url=base_url,
                api_key=api_key,
            )
        return self._embedding_fn

    def _notebook_dir(self, notebook_id: str, ensure: bool = False) -> Path:
        path = self.base_dir / "notebooks" / notebook_id
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _manifest_path(self, notebook_id: str) -> Path:
        return self._notebook_dir(notebook_id, ensure=True) / "manifest.json"

    def _assets_dir(self, notebook_id: str, ensure: bool = False) -> Path:
        path = self._notebook_dir(notebook_id, ensure=ensure) / "assets"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _bodies_dir(self, notebook_id: str, ensure: bool = False) -> Path:
        path = self._notebook_dir(notebook_id, ensure=ensure) / "bodies"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _sources_dir(self, notebook_id: str, ensure: bool = False) -> Path:
        path = self._notebook_dir(notebook_id, ensure=ensure) / "sources"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _chunks_dir(self, notebook_id: str, ensure: bool = False) -> Path:
        path = self._notebook_dir(notebook_id, ensure=ensure) / "source_chunks"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _embeddings_dir(self, notebook_id: str, ensure: bool = False) -> Path:
        path = self._notebook_dir(notebook_id, ensure=ensure) / "embeddings"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _sessions_dir(self, notebook_id: str, ensure: bool = False) -> Path:
        path = self._notebook_dir(notebook_id, ensure=ensure) / "chat_sessions"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _studio_dir(self, notebook_id: str, ensure: bool = False) -> Path:
        path = self._notebook_dir(notebook_id, ensure=ensure) / "studio_outputs"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _notes_dir(self, notebook_id: str, ensure: bool = False) -> Path:
        path = self._notebook_dir(notebook_id, ensure=ensure) / "notes"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _source_path(self, notebook_id: str, source_id: str) -> Path:
        return self._sources_dir(notebook_id, ensure=True) / f"{source_id}.json"

    def _source_body_path(self, notebook_id: str, source_id: str) -> Path:
        return self._bodies_dir(notebook_id, ensure=True) / f"{source_id}.txt"

    def _source_chunks_path(self, notebook_id: str, source_id: str) -> Path:
        return self._chunks_dir(notebook_id, ensure=True) / f"{source_id}.json"

    def _source_embedding_path(self, notebook_id: str, source_id: str) -> Path:
        return self._embeddings_dir(notebook_id, ensure=True) / f"{source_id}.json"

    def _session_path(self, notebook_id: str, session_id: str) -> Path:
        return self._sessions_dir(notebook_id, ensure=True) / f"{session_id}.json"

    def _studio_path(self, notebook_id: str, output_id: str) -> Path:
        return self._studio_dir(notebook_id, ensure=True) / f"{output_id}.json"

    def _note_path(self, notebook_id: str, note_id: str) -> Path:
        return self._notes_dir(notebook_id, ensure=True) / f"{note_id}.json"

    def _load_manifest(self, notebook_id: str) -> dict[str, Any] | None:
        return _safe_json_load(self._manifest_path(notebook_id), None)

    def _save_manifest(self, notebook: dict[str, Any]) -> None:
        notebook["updated_at"] = notebook.get("updated_at") or _now_iso()
        _safe_json_save(self._manifest_path(str(notebook["id"])), notebook)

    def _iter_records(self, directory: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not directory.exists():
            return rows
        for path in sorted(directory.glob("*.json")):
            row = _safe_json_load(path, None)
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def _touch_notebook(self, notebook_id: str) -> None:
        notebook = self._load_manifest(notebook_id)
        if not notebook:
            return
        notebook["updated_at"] = _now_iso()
        self._save_manifest(notebook)

    def _count_dir_items(self, directory: Path) -> int:
        return len(list(directory.glob("*.json"))) if directory.exists() else 0

    def _build_notebook_summary(self, notebook: dict[str, Any]) -> dict[str, Any]:
        notebook_id = str(notebook["id"])
        sessions = self._iter_records(self._sessions_dir(notebook_id, ensure=False))
        studio_outputs = self._iter_records(self._studio_dir(notebook_id, ensure=False))
        source_count = self._count_dir_items(self._sources_dir(notebook_id, ensure=False))
        note_count = self._count_dir_items(self._notes_dir(notebook_id, ensure=False))
        last_chat_at = max((str(row.get("updated_at") or "") for row in sessions), default="")
        last_output_at = max((str(row.get("updated_at") or "") for row in studio_outputs), default="")
        return {
            "id": notebook_id,
            "name": notebook.get("name", "Untitled notebook"),
            "description": notebook.get("description", ""),
            "color": notebook.get("color", "#111827"),
            "icon": notebook.get("icon", "book"),
            "source_count": source_count,
            "note_count": note_count,
            "last_chat_at": last_chat_at or None,
            "last_output_at": last_output_at or None,
            "created_at": notebook.get("created_at"),
            "updated_at": notebook.get("updated_at"),
            "default_kb_id": notebook.get("default_kb_id"),
        }

    def _normalize_source_title(self, source: dict[str, Any]) -> str:
        aliases = self._source_title_aliases(source)
        return aliases[0] if aliases else "Untitled source"

    def _source_title_aliases(self, source: dict[str, Any]) -> list[str]:
        metadata = source.get("metadata", {}) or {}
        candidates = [
            clean_source_title(str(source.get("title") or ""), strip_extension=False),
            clean_source_title(str(metadata.get("file_name") or "")),
            clean_source_title(str(metadata.get("source") or ""), strip_extension=False),
        ]
        url = str(metadata.get("url") or "").strip()
        if url:
            candidates.append(url)
            candidates.append(urlparse(url).netloc)

        aliases: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_query(candidate)
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            aliases.append(candidate if candidate else normalized)
        return aliases

    def _extract_url_content(self, url: str) -> tuple[str, str]:
        request = Request(
            url,
            headers={
                "User-Agent": "WritingBot Notebook/1.0",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise ValueError(f"URL 抓取失败：HTTP {exc.code}") from exc
        except URLError as exc:
            raise ValueError(f"URL 抓取失败：{exc.reason}") from exc

        parser = _HTMLTextExtractor()
        parser.feed(raw)
        text = parser.text()
        if not text:
            raise ValueError("URL 内容为空，无法导入")
        title = parser.title or urlparse(url).netloc or "网页来源"
        return title[:200], text

    def _read_plain_text_file(self, path: Path) -> str:
        data = path.read_bytes()
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                return data.decode(encoding)
            except Exception:
                continue
        return data.decode("utf-8", errors="ignore")

    def _materialize_pdf(
        self,
        notebook_id: str,
        source_id: str,
        filename: str,
        file_bytes: bytes | None = None,
        source_path: Path | None = None,
    ) -> tuple[Path, list[dict[str, Any]], list[dict[str, Any]], str]:
        ext = Path(filename).suffix or ".pdf"
        asset_path = self._assets_dir(notebook_id, ensure=True) / f"{source_id}{ext}"
        if file_bytes is not None:
            asset_path.write_bytes(file_bytes)
        elif source_path is not None:
            shutil.copy2(source_path, asset_path)
        else:
            raise ValueError("PDF 来源缺失")

        content_list = self._get_pdf_parser().parse(str(asset_path))
        full_text = "\n\n".join(item.get("content", "") for item in content_list if item.get("content"))
        chunker = SemanticChunker(chunk_size=900, chunk_overlap=120)
        chunk_rows: list[dict[str, Any]] = []
        for chunk in chunker.chunk_content_list(content_list):
            content = _normalize_whitespace(chunk.content)
            if not content:
                continue
            metadata = dict(chunk.metadata or {})
            chunk_rows.append(
                {
                    "id": f"{source_id}:{chunk.chunk_idx}",
                    "source_id": source_id,
                    "content": content,
                    "page": metadata.get("page"),
                    "chunk_idx": chunk.chunk_idx,
                    "tokens": tokenize(content),
                    "metadata": {
                        "page": metadata.get("page"),
                        "source": metadata.get("source") or filename,
                        "bbox": metadata.get("bbox"),
                        "line_start": metadata.get("line_start"),
                        "line_end": metadata.get("line_end"),
                        "page_width": metadata.get("page_width"),
                        "page_height": metadata.get("page_height"),
                        "highlight_boxes": metadata.get("highlight_boxes") or [],
                        "spans": metadata.get("spans") or [],
                    },
                }
            )
        return asset_path, content_list, chunk_rows, _normalize_whitespace(full_text)

    def _materialize_text_chunks(
        self,
        source_id: str,
        text: str,
        title: str,
    ) -> list[dict[str, Any]]:
        chunker = SemanticChunker(chunk_size=900, chunk_overlap=120)
        rows: list[dict[str, Any]] = []
        for chunk in chunker.chunk_text(_normalize_whitespace(text), metadata={"source": title}):
            content = _normalize_whitespace(chunk.content)
            if not content:
                continue
            rows.append(
                {
                    "id": f"{source_id}:{chunk.chunk_idx}",
                    "source_id": source_id,
                    "content": content,
                    "page": None,
                    "chunk_idx": chunk.chunk_idx,
                    "tokens": tokenize(content),
                    "metadata": {"source": title},
                }
            )
        return rows

    def _build_retrieval_cache(
        self,
        source_id: str,
        chunks: list[dict[str, Any]],
        *,
        source_title: str = "",
        source_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        doc_freq: Counter[str] = Counter()
        chunk_lengths: dict[str, int] = {}
        chunk_ids: list[str] = []
        texts: list[str] = []
        for chunk in chunks:
            unique_tokens = set(chunk.get("tokens", []) or [])
            for token in unique_tokens:
                doc_freq[token] += 1
            chunk_lengths[str(chunk["id"])] = len(chunk.get("tokens", []) or [])
            chunk_ids.append(str(chunk["id"]))
            texts.append(str(chunk.get("content") or ""))

        vectors: dict[str, list[float]] = {}
        if texts:
            try:
                rows = self._get_embedding_fn()(texts)
                for chunk_id, vector in zip(chunk_ids, rows):
                    vectors[chunk_id] = [float(value) for value in vector]
            except Exception:
                vectors = {}
        aliases: list[str] = []
        if source_title:
            aliases.append(source_title)
        metadata = source_metadata or {}
        file_name = clean_source_title(str(metadata.get("file_name") or ""))
        if file_name:
            aliases.append(file_name)
        source_name = clean_source_title(str(metadata.get("source") or ""), strip_extension=False)
        if source_name:
            aliases.append(source_name)
        url = str(metadata.get("url") or "").strip()
        if url:
            aliases.append(url)
            aliases.append(urlparse(url).netloc)

        title_aliases: list[str] = []
        title_tokens: list[str] = []
        seen_aliases: set[str] = set()
        for alias in aliases:
            normalized = self._normalize_query(alias)
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen_aliases:
                continue
            seen_aliases.add(key)
            title_aliases.append(alias if alias else normalized)
            for token in tokenize(normalized):
                if token not in title_tokens:
                    title_tokens.append(token)
        return {
            "source_id": source_id,
            "chunk_count": len(chunks),
            "doc_freq": dict(doc_freq),
            "chunk_lengths": chunk_lengths,
            "chunk_vectors": vectors,
            "title_aliases": title_aliases,
            "title_tokens": title_tokens,
            "representative_chunk_ids": chunk_ids[:2],
            "updated_at": _now_iso(),
        }

    def _build_embedding_index(self, source_id: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        return self._build_retrieval_cache(source_id, chunks)

    def _ensure_source_retrieval_cache(self, notebook_id: str, source: dict[str, Any]) -> dict[str, Any]:
        source_id = str(source.get("id") or "")
        chunks = self._load_source_chunks(notebook_id, source_id)
        cache = self._load_source_embedding_index(notebook_id, source_id)
        if (
            not isinstance(cache, dict)
            or int(cache.get("chunk_count") or 0) != len(chunks)
            or "title_aliases" not in cache
            or "title_tokens" not in cache
            or "representative_chunk_ids" not in cache
        ):
            cache = self._build_retrieval_cache(
                source_id,
                chunks,
                source_title=self._normalize_source_title(source),
                source_metadata=source.get("metadata", {}) or {},
            )
            _safe_json_save(self._source_embedding_path(notebook_id, source_id), cache)
        return cache

    def _merge_retrieved_chunk(self, existing: RetrievedChunk | None, incoming: RetrievedChunk) -> RetrievedChunk:
        if existing is None:
            return incoming
        reasons = tuple(dict.fromkeys([*existing.match_reasons, *incoming.match_reasons]))
        return RetrievedChunk(
            chunk_id=existing.chunk_id,
            source_id=existing.source_id,
            source_title=incoming.source_title or existing.source_title,
            content=incoming.content or existing.content,
            score=max(existing.score, incoming.score),
            page=incoming.page if incoming.page is not None else existing.page,
            line_start=incoming.line_start if incoming.line_start is not None else existing.line_start,
            line_end=incoming.line_end if incoming.line_end is not None else existing.line_end,
            bbox=incoming.bbox or existing.bbox,
            page_width=incoming.page_width if incoming.page_width is not None else existing.page_width,
            page_height=incoming.page_height if incoming.page_height is not None else existing.page_height,
            highlight_boxes=incoming.highlight_boxes or existing.highlight_boxes,
            spans=incoming.spans or existing.spans,
            kind=incoming.kind or existing.kind,
            match_reasons=reasons,
        )

    def _derive_source_payload(self, notebook_id: str, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        kind = str(payload["kind"])
        title = str(payload.get("title") or "")
        text = ""
        metadata: dict[str, Any] = {}

        if kind == "pdf":
            file_name = str(payload.get("file_name") or "document.pdf")
            asset_path, _content_list, chunk_rows, text = self._materialize_pdf(
                notebook_id,
                source_id,
                file_name,
                file_bytes=payload.get("file_bytes"),
            )
            metadata = {
                "file_name": file_name,
                "asset_path": str(asset_path),
            }
            if not title:
                title = Path(file_name).stem
        elif kind == "kb_ref":
            kb_id = str(payload.get("kb_id") or "")
            file_id = str(payload.get("file_id") or "")
            kb = self._get_kb_manager().get_kb(kb_id)
            if not kb:
                raise ValueError("知识库不存在")
            file_info = next((row for row in kb.get("files", []) if row.get("id") == file_id), None)
            if not file_info:
                raise ValueError("知识库文件不存在")
            file_name = str(file_info.get("name") or "knowledge-file.pdf")
            source_path = Path(str(file_info.get("path") or ""))
            if not source_path.exists():
                raise ValueError("知识库文件在磁盘上不存在")
            if file_name.lower().endswith(".pdf"):
                asset_path, _content_list, chunk_rows, text = self._materialize_pdf(
                    notebook_id,
                    source_id,
                    file_name,
                    source_path=source_path,
                )
            else:
                asset_path = self._assets_dir(notebook_id, ensure=True) / f"{source_id}{source_path.suffix}"
                shutil.copy2(source_path, asset_path)
                text = self._read_plain_text_file(asset_path)
                chunk_rows = self._materialize_text_chunks(source_id, text, file_name)
            metadata = {
                "kb_id": kb_id,
                "file_id": file_id,
                "file_name": file_name,
                "asset_path": str(asset_path),
            }
            if not title:
                title = Path(file_name).stem
        elif kind == "url":
            url = str(payload.get("url") or "").strip()
            if not url:
                raise ValueError("URL 不能为空")
            inferred_title, text = self._extract_url_content(url)
            title = title or inferred_title
            chunk_rows = self._materialize_text_chunks(source_id, text, title)
            metadata = {"url": url}
        elif kind == "text":
            text = str(payload.get("text") or "").strip()
            if not text:
                raise ValueError("文本内容不能为空")
            title = title or "Pasted text"
            chunk_rows = self._materialize_text_chunks(source_id, text, title)
            metadata = {"source": "pasted_text"}
        else:
            raise ValueError(f"Unsupported source kind: {kind}")

        if not text or not chunk_rows:
            raise ValueError("来源内容为空，无法建立检索索引")

        return {
            "kind": kind,
            "title": title[:200],
            "text": _normalize_whitespace(text),
            "chunk_rows": chunk_rows,
            "metadata": metadata,
        }

    def _write_source_artifacts(
        self,
        notebook_id: str,
        source_id: str,
        kind: str,
        title: str,
        text: str,
        chunk_rows: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        body_path = self._source_body_path(notebook_id, source_id)
        body_path.write_text(text, encoding="utf-8")
        _safe_json_save(self._source_chunks_path(notebook_id, source_id), chunk_rows)
        _safe_json_save(
            self._source_embedding_path(notebook_id, source_id),
            self._build_retrieval_cache(
                source_id,
                chunk_rows,
                source_title=title,
                source_metadata=metadata,
            ),
        )

        source = {
            "id": source_id,
            "notebook_id": notebook_id,
            "kind": kind,
            "title": title,
            "included": True,
            "status": "ready",
            "snippet": _summarize_text(text),
            "word_count": _word_count(text),
            "char_count": len(text),
            "chunk_count": len(chunk_rows),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "metadata": metadata,
        }
        _safe_json_save(self._source_path(notebook_id, source_id), source)
        return source

    def _load_source(self, notebook_id: str, source_id: str) -> dict[str, Any] | None:
        return _safe_json_load(self._source_path(notebook_id, source_id), None)

    def _load_source_chunks(self, notebook_id: str, source_id: str) -> list[dict[str, Any]]:
        rows = _safe_json_load(self._source_chunks_path(notebook_id, source_id), [])
        return rows if isinstance(rows, list) else []

    def _load_source_embedding_index(self, notebook_id: str, source_id: str) -> dict[str, Any]:
        payload = _safe_json_load(self._source_embedding_path(notebook_id, source_id), {})
        return payload if isinstance(payload, dict) else {}

    def _load_session(self, notebook_id: str, session_id: str) -> dict[str, Any] | None:
        return _safe_json_load(self._session_path(notebook_id, session_id), None)

    def _load_note(self, notebook_id: str, note_id: str) -> dict[str, Any] | None:
        return _safe_json_load(self._note_path(notebook_id, note_id), None)

    def _load_studio_output(self, notebook_id: str, output_id: str) -> dict[str, Any] | None:
        return _safe_json_load(self._studio_path(notebook_id, output_id), None)

    def _iter_included_sources(self, notebook_id: str) -> list[dict[str, Any]]:
        return [row for row in self.list_sources(notebook_id) if row.get("included")]

    def _top_concepts(self, texts: list[str], limit: int = 10) -> list[str]:
        counter: Counter[str] = Counter()
        for text in texts:
            for token in tokenize(text):
                if len(token) < 2 or token in self.STOPWORDS or token.isdigit():
                    continue
                counter[token] += 1
        return [token for token, _ in counter.most_common(limit)]

    def _score_chunk(self, query_tokens: list[str], chunk: dict[str, Any], source_title: str) -> float:
        tokens = chunk.get("tokens", []) or []
        if not query_tokens:
            return 0.0
        token_counts = Counter(tokens)
        metadata_source = str((chunk.get("metadata", {}) or {}).get("source") or "")
        title_tokens = set(tokenize(source_title)) | set(tokenize(metadata_source))
        content_overlap = set(query_tokens) & set(tokens)
        title_overlap = set(query_tokens) & title_tokens
        if not content_overlap and not title_overlap:
            return 0.0
        overlap_score = sum(token_counts[token] for token in content_overlap)
        title_bonus = float(len(title_overlap)) * 0.6
        density = len(content_overlap or title_overlap) / max(1, len(set(query_tokens)))
        return float(overlap_score) + float(title_bonus) * 0.6 + density

    def _normalize_query(self, query: str) -> str:
        return normalize_display_text(query or "", preserve_paragraphs=False)

    def _query_variants(self, query: str, source_index: dict[str, dict[str, Any]]) -> list[str]:
        normalized = self._normalize_query(query)
        variants: list[str] = []
        if normalized:
            variants.append(normalized)

        stripped = re.sub(
            r"(给我一份|请给我|帮我|报告|总结|研究|概览|介绍|分析|说明|核心主题|主要贡献|overview|summary|report|research)",
            " ",
            normalized,
            flags=re.IGNORECASE,
        )
        stripped = re.sub(r"\s+", " ", stripped).strip()
        if stripped and stripped not in variants:
            variants.append(stripped)

        topic_tokens = [token for token in tokenize(normalized) if token not in self.STOPWORDS]
        if topic_tokens:
            topic_variant = " ".join(topic_tokens[:8])
            if topic_variant and topic_variant not in variants:
                variants.append(topic_variant)
            english_variant = " ".join(token for token in topic_tokens if re.search(r"[A-Za-z]", token))
            if english_variant and english_variant not in variants:
                variants.append(english_variant)
            cjk_variant = " ".join(token for token in topic_tokens if re.search(r"[\u4e00-\u9fff]", token))
            if cjk_variant and cjk_variant not in variants:
                variants.append(cjk_variant)
        return variants

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = sum(a * a for a in left) ** 0.5
        right_norm = sum(b * b for b in right) ** 0.5
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)

    def _vector_recall(
        self,
        notebook_id: str,
        source_index: dict[str, dict[str, Any]],
        query_variants: list[str],
        limit: int,
    ) -> list[RetrievedChunk]:
        if not query_variants:
            return []
        try:
            query_vectors = self._get_embedding_fn()(query_variants)
        except Exception:
            return []

        candidates: dict[str, RetrievedChunk] = {}
        for source_id, source in source_index.items():
            source_title = self._normalize_source_title(source)
            chunks = self._load_source_chunks(notebook_id, source_id)
            index = self._ensure_source_retrieval_cache(notebook_id, source)
            stored_vectors = index.get("chunk_vectors", {}) if isinstance(index, dict) else {}
            for chunk in chunks:
                chunk_id = str(chunk.get("id") or "")
                vector = stored_vectors.get(chunk_id)
                if not vector:
                    continue
                similarity = max((self._cosine_similarity(query_vector, vector) for query_vector in query_vectors), default=0.0)
                if similarity <= 0:
                    continue
                candidate = RetrievedChunk(
                    chunk_id=chunk_id,
                    source_id=source_id,
                    source_title=source_title,
                    content=str(chunk.get("content") or ""),
                    score=similarity + 0.15,
                    page=chunk.get("page"),
                    line_start=(chunk.get("metadata", {}) or {}).get("line_start"),
                    line_end=(chunk.get("metadata", {}) or {}).get("line_end"),
                    bbox=(chunk.get("metadata", {}) or {}).get("bbox"),
                    page_width=(chunk.get("metadata", {}) or {}).get("page_width"),
                    page_height=(chunk.get("metadata", {}) or {}).get("page_height"),
                    highlight_boxes=(chunk.get("metadata", {}) or {}).get("highlight_boxes"),
                    spans=(chunk.get("metadata", {}) or {}).get("spans"),
                    kind=str(source.get("kind") or "text"),
                    match_reasons=("vector",),
                )
                candidates[chunk_id] = self._merge_retrieved_chunk(candidates.get(chunk_id), candidate)
        rows = sorted(candidates.values(), key=lambda item: (item.score, len(item.content)), reverse=True)
        return rows[: max(1, limit)]

    def _title_recall(
        self,
        notebook_id: str,
        source_index: dict[str, dict[str, Any]],
        query_variants: list[str],
        limit: int,
    ) -> list[RetrievedChunk]:
        query_text = " ".join(query_variants)
        query_tokens = {token for token in tokenize(query_text) if token not in self.STOPWORDS}
        if not query_tokens:
            return []

        rows: list[RetrievedChunk] = []
        normalized_query = self._normalize_query(query_text).casefold()
        for source_id, source in source_index.items():
            cache = self._ensure_source_retrieval_cache(notebook_id, source)
            title_aliases = [str(alias) for alias in cache.get("title_aliases", []) if alias]
            title_tokens = {str(token) for token in cache.get("title_tokens", []) if token}
            overlap = query_tokens & title_tokens
            best_score = 0.0
            for alias in title_aliases:
                normalized_alias = self._normalize_query(alias).casefold()
                if not normalized_alias:
                    continue
                if normalized_alias in normalized_query:
                    best_score = max(best_score, 1.2 + len(overlap) * 0.1)
                elif overlap:
                    best_score = max(best_score, 0.7 + len(overlap) * 0.12)
            if best_score <= 0:
                continue

            chunks = self._load_source_chunks(notebook_id, source_id)
            representative_ids = {str(row) for row in cache.get("representative_chunk_ids", []) if row}
            representative = [chunk for chunk in chunks if str(chunk.get("id") or "") in representative_ids] or chunks[:1]
            for chunk in representative[:1]:
                rows.append(
                    RetrievedChunk(
                        chunk_id=str(chunk.get("id") or ""),
                        source_id=source_id,
                        source_title=self._normalize_source_title(source),
                        content=str(chunk.get("content") or ""),
                        score=best_score,
                        page=chunk.get("page"),
                        line_start=(chunk.get("metadata", {}) or {}).get("line_start"),
                        line_end=(chunk.get("metadata", {}) or {}).get("line_end"),
                        bbox=(chunk.get("metadata", {}) or {}).get("bbox"),
                        page_width=(chunk.get("metadata", {}) or {}).get("page_width"),
                        page_height=(chunk.get("metadata", {}) or {}).get("page_height"),
                        highlight_boxes=(chunk.get("metadata", {}) or {}).get("highlight_boxes"),
                        spans=(chunk.get("metadata", {}) or {}).get("spans"),
                        kind=str(source.get("kind") or "text"),
                        match_reasons=("title",),
                    )
                )
        rows.sort(key=lambda item: (item.score, len(item.content)), reverse=True)
        return rows[: max(1, limit)]

    def _rerank_candidates(self, query: str, candidates: list[RetrievedChunk], limit: int) -> list[RetrievedChunk]:
        if len(candidates) <= limit:
            return sorted(candidates, key=lambda item: (item.score, len(item.content)), reverse=True)
        reranker_provider = os.getenv("RERANKER_PROVIDER")
        reranker_model = os.getenv("RERANKER_MODEL")
        if not reranker_provider and not reranker_model:
            return sorted(candidates, key=lambda item: (item.score, len(item.content)), reverse=True)[:limit]
        try:
            from src.rag.components.reranker import Reranker

            docs = [
                {
                    "id": chunk.chunk_id,
                    "content": chunk.content,
                    "metadata": {"source": chunk.source_title},
                }
                for chunk in candidates
            ]
            reranked = Reranker(provider=reranker_provider, model=reranker_model).rerank(query, docs, top_k=limit)
            mapping = {chunk.chunk_id: chunk for chunk in candidates}
            ordered: list[RetrievedChunk] = []
            for doc in reranked:
                chunk_id = str(doc.get("id") or "")
                chunk = mapping.get(chunk_id)
                if chunk is None:
                    continue
                ordered.append(RetrievedChunk(**{**chunk.__dict__, "score": float(doc.get("rerank_score") or chunk.score)}))
            return ordered or sorted(candidates, key=lambda item: (item.score, len(item.content)), reverse=True)[:limit]
        except Exception:
            return sorted(candidates, key=lambda item: (item.score, len(item.content)), reverse=True)[:limit]

    def _representative_chunks(
        self,
        notebook_id: str,
        source_index: dict[str, dict[str, Any]],
        limit: int,
    ) -> list[RetrievedChunk]:
        rows: list[RetrievedChunk] = []
        per_source = max(1, limit // max(1, len(source_index)))
        for source_id, source in source_index.items():
            source_title = self._normalize_source_title(source)
            for chunk in self._load_source_chunks(notebook_id, source_id)[:per_source]:
                rows.append(
                    RetrievedChunk(
                        chunk_id=str(chunk.get("id") or ""),
                        source_id=source_id,
                        source_title=source_title,
                        content=str(chunk.get("content") or ""),
                        score=0.01,
                        page=chunk.get("page"),
                        line_start=(chunk.get("metadata", {}) or {}).get("line_start"),
                        line_end=(chunk.get("metadata", {}) or {}).get("line_end"),
                        bbox=(chunk.get("metadata", {}) or {}).get("bbox"),
                        page_width=(chunk.get("metadata", {}) or {}).get("page_width"),
                        page_height=(chunk.get("metadata", {}) or {}).get("page_height"),
                        highlight_boxes=(chunk.get("metadata", {}) or {}).get("highlight_boxes"),
                        spans=(chunk.get("metadata", {}) or {}).get("spans"),
                        kind=str(source.get("kind") or "text"),
                        match_reasons=("representative",),
                    )
                )
                if len(rows) >= max(1, limit):
                    return rows
        return rows

    def retrieve_chunks(
        self,
        notebook_id: str,
        query: str,
        source_ids: list[str] | None = None,
        limit: int = 6,
    ) -> list[RetrievedChunk]:
        sources = self.list_sources(notebook_id)
        if source_ids:
            source_index = {str(row["id"]): row for row in sources if str(row["id"]) in set(source_ids)}
        else:
            source_index = {str(row["id"]): row for row in sources if row.get("included")}

        query_variants = self._query_variants(query, source_index)
        lexical_candidates: dict[str, RetrievedChunk] = {}
        for source_id, source in source_index.items():
            source_title = self._normalize_source_title(source)
            for chunk in self._load_source_chunks(notebook_id, source_id):
                score = max(
                    (
                        self._score_chunk(
                            [token for token in tokenize(variant) if token not in self.STOPWORDS],
                            chunk,
                            source_title,
                        )
                        for variant in query_variants
                    ),
                    default=0.0,
                )
                if score <= 0 and query_variants:
                    continue
                candidate = RetrievedChunk(
                    chunk_id=str(chunk.get("id") or ""),
                    source_id=source_id,
                    source_title=source_title,
                    content=str(chunk.get("content") or ""),
                    score=score,
                    page=chunk.get("page"),
                    line_start=(chunk.get("metadata", {}) or {}).get("line_start"),
                    line_end=(chunk.get("metadata", {}) or {}).get("line_end"),
                    bbox=(chunk.get("metadata", {}) or {}).get("bbox"),
                    page_width=(chunk.get("metadata", {}) or {}).get("page_width"),
                    page_height=(chunk.get("metadata", {}) or {}).get("page_height"),
                    highlight_boxes=(chunk.get("metadata", {}) or {}).get("highlight_boxes"),
                    spans=(chunk.get("metadata", {}) or {}).get("spans"),
                    kind=str(source.get("kind") or "text"),
                    match_reasons=("lexical",),
                )
                lexical_candidates[candidate.chunk_id] = self._merge_retrieved_chunk(
                    lexical_candidates.get(candidate.chunk_id),
                    candidate,
                )
        scored = list(lexical_candidates.values())
        if not scored and not query_variants:
            for source_id, source in source_index.items():
                for chunk in self._load_source_chunks(notebook_id, source_id)[:2]:
                    scored.append(
                        RetrievedChunk(
                            chunk_id=str(chunk.get("id") or ""),
                            source_id=source_id,
                            source_title=self._normalize_source_title(source),
                            content=str(chunk.get("content") or ""),
                            score=1.0,
                            page=chunk.get("page"),
                            line_start=(chunk.get("metadata", {}) or {}).get("line_start"),
                            line_end=(chunk.get("metadata", {}) or {}).get("line_end"),
                            bbox=(chunk.get("metadata", {}) or {}).get("bbox"),
                            page_width=(chunk.get("metadata", {}) or {}).get("page_width"),
                            page_height=(chunk.get("metadata", {}) or {}).get("page_height"),
                            highlight_boxes=(chunk.get("metadata", {}) or {}).get("highlight_boxes"),
                            spans=(chunk.get("metadata", {}) or {}).get("spans"),
                            kind=str(source.get("kind") or "text"),
                            match_reasons=("representative",),
                        )
                    )
        title_rows = self._title_recall(notebook_id, source_index, query_variants, limit=max(limit * 2, 6))
        if title_rows:
            merged = {row.chunk_id: row for row in scored}
            for row in title_rows:
                merged[row.chunk_id] = self._merge_retrieved_chunk(merged.get(row.chunk_id), row)
            scored = list(merged.values())
        vector_rows = self._vector_recall(notebook_id, source_index, query_variants, limit=max(limit * 3, 8))
        if vector_rows:
            merged = {row.chunk_id: row for row in scored}
            for row in vector_rows:
                merged[row.chunk_id] = self._merge_retrieved_chunk(merged.get(row.chunk_id), row)
            scored = list(merged.values())
        if scored:
            scored = self._rerank_candidates(query, scored, limit=max(limit * 2, 8))
        if not scored and source_index:
            scored = self._representative_chunks(notebook_id, source_index, limit=max(1, limit))
        scored.sort(key=lambda item: (item.score, len(item.content)), reverse=True)
        return scored[: max(1, limit)]

    def _build_citations(self, chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for chunk in chunks:
            locator = format_page_locator(chunk.page, chunk.line_start, chunk.line_end) if chunk.page is not None else chunk.kind
            rows.append(
                {
                    "source_id": chunk.source_id,
                    "source_title": chunk.source_title,
                    "locator": locator,
                    "excerpt": build_text_evidence_excerpt(
                        chunk.content,
                        metadata={
                            "spans": chunk.spans
                            or [
                                {
                                    "content": chunk.content,
                                    "page": chunk.page,
                                    "bbox": chunk.bbox,
                                    "line_start": chunk.line_start,
                                    "line_end": chunk.line_end,
                                    "page_width": chunk.page_width,
                                    "page_height": chunk.page_height,
                                }
                            ]
                        },
                        limit=260,
                    ),
                    "line_start": chunk.line_start,
                    "line_end": chunk.line_end,
                    "bbox": chunk.bbox,
                    "page": chunk.page,
                    "page_width": chunk.page_width,
                    "page_height": chunk.page_height,
                    "highlight_boxes": chunk.highlight_boxes or [],
                }
            )
        return _dedupe_citations(rows, limit=6)

    def _extract_json_blob(self, text: str) -> dict[str, Any] | None:
        match = re.search(r"\{[\s\S]*\}", text or "")
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _generate_with_llm(
        self,
        prompt: str,
        default: dict[str, Any],
        *,
        max_tokens: int = 1800,
    ) -> dict[str, Any]:
        try:
            from src.services.llm import get_llm_client

            client = get_llm_client()
            raw = client.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是一个来源优先的智能笔记本助手。"
                            "请只返回 JSON，不要输出解释。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            parsed = self._extract_json_blob(raw)
            if parsed:
                return parsed
        except Exception:
            pass
        return default

    def _fallback_chat_answer(
        self,
        question: str,
        citations: list[dict[str, Any]],
        answer_mode: str,
    ) -> dict[str, Any]:
        if answer_mode == "llm_fallback":
            return {
                "answer_markdown": (
                    "当前未选来源，以下为通用回答。\n\n"
                    f"关于“{question.strip()}”，我先给你一个通用概览：\n\n"
                    "- 下面的回答基于通用模型知识整理。\n"
                    "- 如果你把相关论文、网页或知识库文件加入 Sources，我可以进一步给出带引用的版本。"
                ),
                "background_extension": "",
            }

        bullets = "\n".join(f"- {row['excerpt']} [{row['index']}]" for row in citations[:4])
        prefix = (
            "以下回答优先基于已选来源中的高相关内容。"
            if answer_mode == "grounded"
            else "以下为基于相关材料的整理/推断。"
        )
        return {
            "answer_markdown": (
                f"{prefix}\n\n"
                f"围绕“{question.strip()}”，我先提炼到这些信息：\n\n"
                f"{bullets}\n\n"
                "如果你愿意，我可以继续把这些内容整理成报告、FAQ 或学习指南。"
            ),
            "background_extension": "",
        }

    def _llm_fallback_answer(self, question: str) -> dict[str, Any]:
        prompt = (
            "用户当前没有提供可用来源。请直接给出一个清晰、有结构的中文回答。"
            "请尽量写得具体，至少包含背景、关键点和下一步建议。"
            "返回 JSON，字段为 answer_markdown 和 background_extension。"
            f"\n\n用户问题：{question.strip()}"
        )
        generated = self._generate_with_llm(
            prompt,
            default=self._fallback_chat_answer(question, [], "llm_fallback"),
            max_tokens=2400,
        )
        answer = str(generated.get("answer_markdown") or "").strip()
        background = str(generated.get("background_extension") or "").strip()
        if not answer:
            return self._fallback_chat_answer(question, [], "llm_fallback")
        return {"answer_markdown": answer, "background_extension": background}

    def _classify_answer_mode(self, question: str, retrieved: list[RetrievedChunk], sources_available: bool) -> str:
        if not sources_available:
            return "llm_fallback"
        if not retrieved:
            return "weakly_grounded"
        original_tokens = {token for token in tokenize(question) if token not in self.STOPWORDS}
        representative_only = all(set(row.match_reasons).issubset({"representative"}) for row in retrieved[:4])
        strong_recall = any({"lexical", "vector"} & set(row.match_reasons) for row in retrieved[:4])
        if original_tokens:
            overlap = False
            for row in retrieved[:4]:
                evidence_tokens = set(tokenize(f"{row.source_title} {row.content}"))
                if original_tokens.intersection(evidence_tokens):
                    overlap = True
                    break
            if not overlap:
                if representative_only:
                    return "weakly_grounded"
                if strong_recall and max((row.score for row in retrieved), default=0.0) >= 0.45:
                    return "grounded"
                return "weakly_grounded"
        top_score = max((row.score for row in retrieved), default=0.0)
        if representative_only:
            return "weakly_grounded"
        return "grounded" if top_score >= 1.0 else "weakly_grounded"

    def _generate_chat_answer(
        self,
        notebook_id: str,
        question: str,
        retrieved: list[RetrievedChunk],
        citations: list[dict[str, Any]],
        *,
        sources_available: bool,
    ) -> dict[str, Any]:
        answer_mode = self._classify_answer_mode(question, retrieved, sources_available)
        if answer_mode == "llm_fallback":
            payload = self._llm_fallback_answer(question)
            return {
                **payload,
                "answer_mode": "llm_fallback",
                "retrieval_mode": "llm_fallback",
            }

        snippets = []
        for row in citations:
            snippets.append(
                f"[{row['index']}] 来源：{row['source_title']} ({row['locator']})\n{row['excerpt']}"
            )
        snippets_text = "\n\n".join(snippets)
        mode_rule = (
            "主回答必须优先基于来源，关键句后附上 [编号] 引用。"
            if answer_mode == "grounded"
            else "请尽可能基于这些相关材料回答；若有归纳或推断，请明确说明，并在能引用的地方附上 [编号]。"
        )
        prompt = (
            "请根据提供的来源片段回答用户问题。\n"
            "要求：\n"
            f"1. {mode_rule}\n"
            "2. 主体内容要写得尽量充实，优先输出 4-6 段有小标题或分点的完整回答，而不是只给很短的摘要。\n"
            "3. 如果问题是报告、总结、综述、学习导览这类请求，请覆盖：背景/主题、关键观点、方法或机制、局限性/风险、可行动建议。\n"
            "4. 如果需要补充你自己的背景知识，请放到 background_extension 字段，并尽量写成 1-2 段补充说明。\n"
            "5. weakly-grounded 场景下，请明确写出“以下为基于相关材料的整理/推断”。\n"
            "6. 返回 JSON，字段为 answer_markdown 和 background_extension。\n\n"
            f"用户问题：{question.strip()}\n\n"
            f"来源片段：\n{snippets_text}"
        )
        generated = self._generate_with_llm(
            prompt,
            default=self._fallback_chat_answer(question, citations, answer_mode),
            max_tokens=2600,
        )
        answer = str(generated.get("answer_markdown") or "").strip()
        background = str(generated.get("background_extension") or "").strip()
        if not answer:
            fallback = self._fallback_chat_answer(question, citations, answer_mode)
            return {
                **fallback,
                "answer_mode": answer_mode,
                "retrieval_mode": answer_mode,
            }
        return {
            "answer_markdown": answer,
            "background_extension": background,
            "answer_mode": answer_mode,
            "retrieval_mode": answer_mode,
        }

    def _fallback_studio(self, notebook: dict[str, Any], kind: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
        title = {
            "summary": "Notebook Summary",
            "study_guide": "Study Guide",
            "faq": "FAQ",
            "mind_map": "Mind Map",
        }.get(kind, "Studio Output")
        excerpts = [row["excerpt"] for row in citations[:5]]
        concepts = self._top_concepts(excerpts, limit=8)

        if kind == "mind_map":
            tree = {
                "id": "root",
                "label": notebook.get("name", "Notebook"),
                "children": [
                    {"id": f"topic-{index}", "label": concept, "children": []}
                    for index, concept in enumerate(concepts[:6], start=1)
                ],
            }
            return {
                "title": title,
                "content": "\n".join(f"- {concept}" for concept in concepts[:6]) or "- 暂无概念节点",
                "blocks": [{"title": "核心主题", "items": concepts[:6]}],
                "tree": tree,
            }

        if kind == "faq":
            content = (
                "## 常见问题\n"
                "### 这组来源主要讲了什么？\n"
                + (excerpts[0] if excerpts else "当前还没有足够来源。")
                + "\n\n### 下一步应该关注什么？\n"
                + ("优先继续追问这些主题：" + "、".join(concepts[:4]) if concepts else "建议补充更多来源。")
            )
            return {
                "title": title,
                "content": content,
                "blocks": [{"title": "FAQ", "items": excerpts[:4]}],
                "tree": None,
            }

        if kind == "study_guide":
            content = (
                "## 学习导览\n"
                "### 主题概览\n"
                + (excerpts[0] if excerpts else "当前还没有足够来源。")
                + "\n\n### 重点概念\n"
                + "\n".join(f"- {concept}" for concept in concepts[:6])
                + "\n\n### 复习问题\n- 这些来源之间有什么共同观点？\n- 哪些结论需要进一步验证？"
            )
            return {
                "title": title,
                "content": content,
                "blocks": [
                    {"title": "重点概念", "items": concepts[:6]},
                    {"title": "复习问题", "items": ["这些来源之间有什么共同观点？", "哪些结论需要进一步验证？"]},
                ],
                "tree": None,
            }

        content = (
            "## 摘要\n"
            + "\n".join(f"- {excerpt}" for excerpt in excerpts[:4])
            + "\n\n## 关键主题\n"
            + "\n".join(f"- {concept}" for concept in concepts[:6])
        )
        return {
            "title": title,
            "content": content,
            "blocks": [
                {"title": "摘要", "items": excerpts[:4]},
                {"title": "关键主题", "items": concepts[:6]},
            ],
            "tree": None,
        }

    def _generate_studio_output(
        self,
        notebook: dict[str, Any],
        kind: str,
        citations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fallback = self._fallback_studio(notebook, kind, citations)
        if not citations:
            return fallback

        prompt = (
            "请基于给定来源生成一个智能笔记本 Studio 产物。\n"
            f"产物类型：{kind}\n"
            "返回 JSON，字段：title, content, blocks, tree。\n"
            "rules:\n"
            "- content 使用中文 markdown。\n"
            "- blocks 为结构化段落数组，每项含 title 和 items。\n"
            "- kind 为 mind_map 时 tree 返回树结构，否则返回 null。\n\n"
            "写作要求：\n"
            "- 写得尽量充实，不要只给短摘要，要产出可以直接保存为笔记阅读的完整正文。\n"
            "- 至少包含 4 个一级或二级小节，每个小节下给出充分展开的说明或要点。\n"
            "- summary 要覆盖背景、核心主题、关键机制/方法、重要发现、局限与启发。\n"
            "- study_guide 要覆盖学习路径、重点概念解释、复习问题与延伸建议。\n"
            "- faq 至少生成 5 个有信息量的问题与回答，而不是简短占位句。\n"
            "- mind_map 除 tree 外，content 也要补充对结构的文字解释。\n\n"
            "来源：\n"
            + "\n\n".join(
                f"[{row['index']}] {row['source_title']} ({row['locator']})\n{row['excerpt']}"
                for row in citations
            )
        )
        generated = self._generate_with_llm(prompt, default=fallback, max_tokens=3200)
        title = str(generated.get("title") or fallback["title"]).strip() or fallback["title"]
        content = str(generated.get("content") or fallback["content"]).strip() or fallback["content"]
        blocks = generated.get("blocks")
        if not isinstance(blocks, list):
            blocks = fallback["blocks"]
        tree = generated.get("tree")
        if kind != "mind_map":
            tree = None
        if kind == "mind_map" and not isinstance(tree, dict):
            tree = fallback["tree"]
        return {
            "title": title,
            "content": content,
            "blocks": blocks,
            "tree": tree,
        }

    def _split_stream_chunks(self, text: str, size: int = 120) -> list[str]:
        normalized = text or ""
        return [normalized[index : index + size] for index in range(0, len(normalized), size)] or [""]

    # ------------------------------------------------------------------ #
    # Notebook CRUD
    # ------------------------------------------------------------------ #

    def list_notebooks(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for manifest_path in sorted((self.base_dir / "notebooks").glob("*/manifest.json")):
            notebook = _safe_json_load(manifest_path, None)
            if isinstance(notebook, dict):
                rows.append(self._build_notebook_summary(notebook))
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return rows

    def get_statistics(self) -> dict[str, Any]:
        notebooks = self.list_notebooks()
        return {
            "notebook_count": len(notebooks),
            "source_count": sum(int(row.get("source_count") or 0) for row in notebooks),
            "note_count": sum(int(row.get("note_count") or 0) for row in notebooks),
        }

    def create_notebook(
        self,
        name: str,
        description: str = "",
        color: str = "#111827",
        icon: str = "book",
        default_kb_id: str | None = None,
        auto_import_enabled: bool = False,
    ) -> dict[str, Any]:
        notebook_id = str(uuid.uuid4())
        now = _now_iso()
        notebook = {
            "id": notebook_id,
            "name": name.strip() or "Untitled notebook",
            "description": description or "",
            "color": color,
            "icon": icon,
            "created_at": now,
            "updated_at": now,
            "default_kb_id": default_kb_id,
            "auto_import_enabled": bool(auto_import_enabled),
        }
        self._notebook_dir(notebook_id, ensure=True)
        self._save_manifest(notebook)
        return self._build_notebook_summary(notebook)

    def get_notebook(self, notebook_id: str) -> dict[str, Any] | None:
        notebook = self._load_manifest(notebook_id)
        if not notebook:
            return None
        return self._build_notebook_summary(notebook)

    def update_notebook(self, notebook_id: str, **patch: Any) -> dict[str, Any] | None:
        notebook = self._load_manifest(notebook_id)
        if not notebook:
            return None
        for key in ("name", "description", "color", "icon", "default_kb_id", "auto_import_enabled"):
            if key in patch and patch[key] is not None:
                notebook[key] = patch[key]
        notebook["updated_at"] = _now_iso()
        self._save_manifest(notebook)
        return self._build_notebook_summary(notebook)

    def delete_notebook(self, notebook_id: str) -> bool:
        directory = self._notebook_dir(notebook_id, ensure=False)
        if not directory.exists():
            return False
        shutil.rmtree(directory)
        return True

    # ------------------------------------------------------------------ #
    # Sources
    # ------------------------------------------------------------------ #

    def list_sources(self, notebook_id: str) -> list[dict[str, Any]]:
        directory = self._sources_dir(notebook_id, ensure=False)
        rows = self._iter_records(directory)
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return rows

    def create_source(self, notebook_id: str, **payload: Any) -> dict[str, Any]:
        if not self._load_manifest(notebook_id):
            raise ValueError("Notebook not found")
        source_id = str(uuid.uuid4())
        materialized = self._derive_source_payload(notebook_id, source_id, payload)
        source = self._write_source_artifacts(
            notebook_id,
            source_id,
            kind=str(materialized["kind"]),
            title=str(materialized["title"]),
            text=str(materialized["text"]),
            chunk_rows=list(materialized["chunk_rows"]),
            metadata=dict(materialized["metadata"]),
        )
        self._touch_notebook(notebook_id)
        return source

    def update_source(self, notebook_id: str, source_id: str, **patch: Any) -> dict[str, Any] | None:
        source = self._load_source(notebook_id, source_id)
        if not source:
            return None
        refresh_cache = False
        if "included" in patch and patch["included"] is not None:
            source["included"] = bool(patch["included"])
        if "title" in patch and patch["title"]:
            source["title"] = str(patch["title"])[:200]
            refresh_cache = True
        source["updated_at"] = _now_iso()
        _safe_json_save(self._source_path(notebook_id, source_id), source)
        if refresh_cache:
            chunks = self._load_source_chunks(notebook_id, source_id)
            _safe_json_save(
                self._source_embedding_path(notebook_id, source_id),
                self._build_retrieval_cache(
                    source_id,
                    chunks,
                    source_title=self._normalize_source_title(source),
                    source_metadata=source.get("metadata", {}) or {},
                ),
            )
        self._touch_notebook(notebook_id)
        return source

    def delete_source(self, notebook_id: str, source_id: str) -> bool:
        source = self._load_source(notebook_id, source_id)
        if not source:
            return False
        paths = [
            self._source_path(notebook_id, source_id),
            self._source_chunks_path(notebook_id, source_id),
            self._source_embedding_path(notebook_id, source_id),
            self._source_body_path(notebook_id, source_id),
        ]
        asset_value = str((source.get("metadata", {}) or {}).get("asset_path") or "").strip()
        asset_path = Path(asset_value) if asset_value else None
        if asset_path and asset_path.exists() and asset_path.is_file():
            paths.append(asset_path)
        deleted = False
        for path in paths:
            if path.exists():
                path.unlink()
                deleted = True
        if deleted:
            self._touch_notebook(notebook_id)
        return deleted

    # ------------------------------------------------------------------ #
    # Chat
    # ------------------------------------------------------------------ #

    def list_chat_sessions(self, notebook_id: str) -> list[dict[str, Any]]:
        rows = self._iter_records(self._sessions_dir(notebook_id, ensure=False))
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        result: list[dict[str, Any]] = []
        for row in rows[:12]:
            messages = row.get("messages", []) or []
            last_message = messages[-1]["content"] if messages else ""
            result.append(
                {
                    "id": row.get("id"),
                    "title": row.get("title", "New chat"),
                    "updated_at": row.get("updated_at"),
                    "created_at": row.get("created_at"),
                    "message_count": len(messages),
                    "last_message": _summarize_text(last_message, 140),
                }
            )
        return result

    def create_chat_session(self, notebook_id: str, title: str | None = None) -> dict[str, Any]:
        if not self._load_manifest(notebook_id):
            raise ValueError("Notebook not found")
        session_id = str(uuid.uuid4())
        now = _now_iso()
        session = {
            "id": session_id,
            "notebook_id": notebook_id,
            "title": title or "New chat",
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        _safe_json_save(self._session_path(notebook_id, session_id), session)
        self._touch_notebook(notebook_id)
        return session

    def get_chat_session(self, notebook_id: str, session_id: str) -> dict[str, Any] | None:
        return self._load_session(notebook_id, session_id)

    def chat_in_session(
        self,
        notebook_id: str,
        session_id: str | None,
        message: str,
        source_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self._load_manifest(notebook_id):
            raise ValueError("Notebook not found")
        session = self._load_session(notebook_id, session_id) if session_id else None
        if session is None:
            session = self.create_chat_session(notebook_id)

        user_message = {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": message.strip(),
            "created_at": _now_iso(),
            "source_ids": source_ids or [],
        }
        session.setdefault("messages", []).append(user_message)

        sources_available = bool(source_ids) or bool(self._iter_included_sources(notebook_id))
        retrieved = self.retrieve_chunks(notebook_id, message, source_ids=source_ids, limit=6)
        citations = self._build_citations(retrieved)
        generated = self._generate_chat_answer(
            notebook_id,
            message,
            retrieved,
            citations,
            sources_available=sources_available,
        )
        assistant_message = {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": generated["answer_markdown"],
            "background_extension": generated["background_extension"],
            "citations": citations,
            "answer_mode": generated.get("answer_mode", "grounded"),
            "retrieval_mode": generated.get("retrieval_mode", "grounded"),
            "source_ids": source_ids or [row.get("source_id") for row in citations],
            "created_at": _now_iso(),
        }
        session["messages"].append(assistant_message)
        session["updated_at"] = _now_iso()
        if session.get("title", "New chat") == "New chat":
            session["title"] = _summarize_text(message, 36) or "New chat"
        _safe_json_save(self._session_path(notebook_id, str(session["id"])), session)

        notebook = self._load_manifest(notebook_id)
        if notebook:
            notebook["updated_at"] = _now_iso()
            self._save_manifest(notebook)
        return {
            "session": session,
            "assistant_message": assistant_message,
            "stream_chunks": self._split_stream_chunks(assistant_message["content"]),
        }

    # ------------------------------------------------------------------ #
    # Studio outputs
    # ------------------------------------------------------------------ #

    def list_studio_outputs(self, notebook_id: str) -> list[dict[str, Any]]:
        rows = self._iter_records(self._studio_dir(notebook_id, ensure=False))
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return rows[:24]

    def generate_studio_output(
        self,
        notebook_id: str,
        kind: str,
        source_ids: list[str] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        notebook = self._load_manifest(notebook_id)
        if not notebook:
            raise ValueError("Notebook not found")

        base_query = {
            "summary": "总结这些来源的核心内容",
            "study_guide": "整理这些来源的学习导览和复习重点",
            "faq": "围绕这些来源整理常见问题与回答",
            "mind_map": "提炼这些来源的主题结构与概念节点",
        }.get(kind, "总结这些来源")

        selected_sources = source_ids or [row["id"] for row in self._iter_included_sources(notebook_id)]
        if session_id:
            session = self._load_session(notebook_id, session_id)
            if session and session.get("messages"):
                latest_user = next(
                    (row for row in reversed(session["messages"]) if row.get("role") == "user"),
                    None,
                )
                if latest_user and latest_user.get("content"):
                    base_query = str(latest_user["content"])

        retrieved = self.retrieve_chunks(notebook_id, base_query, source_ids=selected_sources, limit=8)
        citations = self._build_citations(retrieved)
        generated = self._generate_studio_output(notebook, kind, citations)

        output_id = str(uuid.uuid4())
        now = _now_iso()
        output = {
            "id": output_id,
            "notebook_id": notebook_id,
            "kind": kind,
            "title": generated["title"],
            "content": generated["content"],
            "blocks": generated["blocks"],
            "tree": generated["tree"],
            "citations": citations,
            "source_ids": selected_sources,
            "created_at": now,
            "updated_at": now,
        }
        _safe_json_save(self._studio_path(notebook_id, output_id), output)
        notebook["updated_at"] = now
        self._save_manifest(notebook)
        return output

    def delete_studio_output(self, notebook_id: str, output_id: str) -> bool:
        path = self._studio_path(notebook_id, output_id)
        if not path.exists():
            return False
        path.unlink()
        self._touch_notebook(notebook_id)
        return True

    # ------------------------------------------------------------------ #
    # Notes
    # ------------------------------------------------------------------ #

    def _note_summary(self, note: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": note.get("id"),
            "title": note.get("title", "Untitled note"),
            "kind": note.get("kind", "manual"),
            "preview": _summarize_text(str(note.get("content") or ""), 180),
            "tags": list(note.get("tags", []) or []),
            "source_ids": list(note.get("source_ids", []) or []),
            "updated_at": note.get("updated_at"),
            "created_at": note.get("created_at"),
            "origin": note.get("origin"),
            "citations": note.get("citations", []),
        }

    def list_notes(
        self,
        notebook_id: str,
        search: str | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._iter_records(self._notes_dir(notebook_id, ensure=False))
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        summaries = [self._note_summary(row) for row in rows]
        if search:
            needle = search.strip().lower()
            summaries = [
                row
                for row in summaries
                if needle in str(row.get("title") or "").lower()
                or needle in str(row.get("preview") or "").lower()
            ]
        if tag:
            tag_lower = tag.strip().lower()
            summaries = [
                row
                for row in summaries
                if any(tag_lower in str(item).lower() for item in row.get("tags", []) or [])
            ]
        return summaries

    def create_note(
        self,
        notebook_id: str,
        title: str,
        content: str = "",
        kind: str = "manual",
        origin: str | None = None,
        citations: list[dict[str, Any]] | None = None,
        source_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self._load_manifest(notebook_id):
            raise ValueError("Notebook not found")
        note_id = str(uuid.uuid4())
        now = _now_iso()
        note = {
            "id": note_id,
            "notebook_id": notebook_id,
            "title": title.strip() or "Untitled note",
            "content": _normalize_whitespace(content),
            "kind": kind,
            "origin": origin,
            "citations": citations or [],
            "source_ids": source_ids or [],
            "tags": tags or [],
            "created_at": now,
            "updated_at": now,
        }
        _safe_json_save(self._note_path(notebook_id, note_id), note)
        self._touch_notebook(notebook_id)
        return note

    def get_note(self, notebook_id: str, note_id: str) -> dict[str, Any] | None:
        return self._load_note(notebook_id, note_id)

    def update_note(self, notebook_id: str, note_id: str, **patch: Any) -> dict[str, Any] | None:
        note = self._load_note(notebook_id, note_id)
        if not note:
            return None
        expected_updated_at = patch.pop("expected_updated_at", None)
        if expected_updated_at is not None and str(note.get("updated_at") or "") != str(expected_updated_at):
            raise NotebookConflictError(note)
        for key in ("title", "kind", "origin"):
            if key in patch and patch[key] is not None:
                note[key] = patch[key]
        if "content" in patch and patch["content"] is not None:
            note["content"] = _normalize_whitespace(str(patch["content"]))
        if "citations" in patch and patch["citations"] is not None:
            note["citations"] = patch["citations"]
        if "source_ids" in patch and patch["source_ids"] is not None:
            note["source_ids"] = patch["source_ids"]
        if "tags" in patch and patch["tags"] is not None:
            note["tags"] = patch["tags"]
        note["updated_at"] = _now_iso()
        _safe_json_save(self._note_path(notebook_id, note_id), note)
        self._touch_notebook(notebook_id)
        return note

    def delete_note(self, notebook_id: str, note_id: str) -> bool:
        path = self._note_path(notebook_id, note_id)
        if not path.exists():
            return False
        path.unlink()
        self._touch_notebook(notebook_id)
        return True

    def create_note_from_sources(
        self,
        notebook_id: str,
        title: str,
        content: str,
        sources: list[dict[str, Any]] | None = None,
        kb_id: str | None = None,
        origin_type: str = "chat",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        citations = _dedupe_citations(
            [
                {
                    "source_id": row.get("source_id") or row.get("file_id") or row.get("id"),
                    "source_title": row.get("source_title") or row.get("title") or row.get("source") or row.get("file_name") or "来源",
                    "locator": (
                        format_page_locator(row.get("page"), row.get("line_start"), row.get("line_end"))
                        if row.get("page") is not None
                        else (row.get("locator") or "source")
                    ),
                    "excerpt": row.get("excerpt") or row.get("content") or "",
                    "summary": row.get("summary"),
                    "line_start": row.get("line_start"),
                    "line_end": row.get("line_end"),
                    "bbox": row.get("bbox"),
                    "page": row.get("page"),
                    "page_width": row.get("page_width"),
                    "page_height": row.get("page_height"),
                    "highlight_boxes": row.get("highlight_boxes") or [],
                    "asset_id": row.get("asset_id"),
                    "asset_type": row.get("asset_type"),
                    "caption": row.get("caption"),
                    "ref_label": row.get("ref_label"),
                    "thumbnail_url": row.get("thumbnail_url"),
                    "interpretation": row.get("interpretation"),
                    "title": row.get("title"),
                    "is_primary": row.get("is_primary"),
                    "evidence_kind": row.get("evidence_kind"),
                }
                for row in (sources or [])
            ]
        )
        kind = {
            "chat": "saved_chat",
            "research": "saved_research",
            "co_writer": "saved_studio",
            "studio": "saved_studio",
        }.get(origin_type, "manual")
        source_ids = [str(row.get("source_id") or row.get("file_id") or "") for row in citations if row.get("source_id")]
        origin = origin_type if not kb_id else f"{origin_type}:{kb_id}"
        return self.create_note(
            notebook_id=notebook_id,
            title=title,
            content=content,
            kind=kind,
            origin=origin,
            citations=citations,
            source_ids=source_ids,
            tags=tags,
        )

    def save_studio_output_as_note(self, notebook_id: str, output_id: str) -> dict[str, Any] | None:
        output = self._load_studio_output(notebook_id, output_id)
        if not output:
            return None
        return self.create_note(
            notebook_id=notebook_id,
            title=output.get("title", "Studio output"),
            content=output.get("content", ""),
            kind="saved_studio",
            origin=f"studio:{output.get('kind', 'summary')}",
            citations=output.get("citations", []),
            source_ids=output.get("source_ids", []),
        )

    # ------------------------------------------------------------------ #
    # Workspace view
    # ------------------------------------------------------------------ #

    def build_workspace_view(
        self,
        notebook_id: str,
        active_note_id: str | None = None,
        search: str | None = None,
        tag: str | None = None,
    ) -> dict[str, Any] | None:
        notebook_manifest = self._load_manifest(notebook_id)
        if not notebook_manifest:
            return None
        notebook = self._build_notebook_summary(notebook_manifest)
        sessions = self.list_chat_sessions(notebook_id)
        outputs = self.list_studio_outputs(notebook_id)
        notes = self.list_notes(notebook_id, search=search, tag=tag)
        sources = self.list_sources(notebook_id)
        note_ids = [str(row.get("id") or "") for row in notes]
        resolved_active_note_id = active_note_id if active_note_id and active_note_id in note_ids else None
        if not resolved_active_note_id and note_ids:
            resolved_active_note_id = note_ids[0]
        return {
            "generated_at": _now_iso(),
            "notebook": notebook,
            "sources": sources,
            "recent_sessions": sessions,
            "studio_outputs": outputs,
            "notes_summary": notes,
            "filters": {
                "search": search or "",
                "tag": tag or "",
            },
            "ui_defaults": {
                "selected_source_ids": [row["id"] for row in sources if row.get("included")],
                "active_session_id": sessions[0]["id"] if sessions else None,
                "active_output_id": outputs[0]["id"] if outputs else None,
                "active_note_id": resolved_active_note_id,
                "note_drawer_open": False,
            },
        }

    # ------------------------------------------------------------------ #
    # Compatibility helpers
    # ------------------------------------------------------------------ #

    def trigger_auto_import_for_kb_file(self, kb_id: str, file_id: str) -> list[dict[str, Any]]:
        # NotebookLM-style notebooks opt in manually via "Add from knowledge base".
        return []


_notebook_manager: NotebookManager | None = None


def get_notebook_manager() -> NotebookManager:
    global _notebook_manager
    if _notebook_manager is None:
        _notebook_manager = NotebookManager()
    return _notebook_manager
