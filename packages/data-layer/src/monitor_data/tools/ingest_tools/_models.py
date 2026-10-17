"""
Data models, constants, and tokenization helpers for document ingestion.

LAYER: 1 (data-layer)
IMPORTS FROM: tiktoken

These are the shared building blocks used by chunking, PDF processing,
and multi-format ingestion modules.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import tiktoken

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_TOKENS: int = 512
RULEBOOK_CHUNK_SIZE: int = 1024
DEFAULT_OVERLAP_RATIO: float = 0.10  # 10% — per LIBRARY_PLAN DL-B3

class _FallbackEncoding:
    """Offline fallback tokenizer when tiktoken BPE cache is unavailable and sockets are blocked."""

    def __init__(self) -> None:
        self._id_to_tok: list[str] = []
        self._tok_to_id: dict[str, int] = {}

    def encode(self, text: str) -> list[int]:
        import re

        if not text:
            return []
        parts = re.findall(r"\S+\s*|\s+", text)
        ids: list[int] = []
        for part in parts:
            tid = self._tok_to_id.get(part)
            if tid is None:
                tid = len(self._id_to_tok)
                self._id_to_tok.append(part)
                self._tok_to_id[part] = tid
            ids.append(tid)
        return ids

    def decode(self, token_ids: list[int]) -> str:
        return "".join(self._id_to_tok[tid] for tid in token_ids if 0 <= tid < len(self._id_to_tok))


def _load_encoding() -> tiktoken.Encoding | _FallbackEncoding:
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:  # noqa: BLE001  # reason: falls back to `_FallbackEncoding()` on failure (in _load_encoding)
        return _FallbackEncoding()


# Tiktoken encoding — cl100k_base is used by Claude / OpenAI text-embedding-3-*
# Using a consistent encoding across all models avoids chunk-size drift.
ENCODING: tiktoken.Encoding | _FallbackEncoding = _load_encoding()

# ---------------------------------------------------------------------------
# Optional dependency guards (graceful degradation)
# ---------------------------------------------------------------------------

_BS4_AVAILABLE = importlib.util.find_spec("bs4") is not None
_DOCX_AVAILABLE = importlib.util.find_spec("docx") is not None
_EPUB_AVAILABLE = importlib.util.find_spec("ebooklib") is not None


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class IngestedChunk:
    """
    A single embedding-ready text chunk with provenance metadata.

    Stored in Qdrant as the payload alongside its embedding vector.
    The chunk_id is a stable hash so re-ingestion is idempotent.
    """

    chunk_id: str
    source_name: str
    page_number: int | None  # None for non-PDF sources
    chunk_index: int
    text: str
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def stable_id(source_name: str, chunk_index: int, text: str) -> str:
        """Deterministic Qdrant-safe UUID for a chunk."""
        seed = f"{source_name}:{chunk_index}:{text}"
        return str(uuid5(NAMESPACE_URL, seed))

    def to_qdrant_payload(self) -> dict[str, Any]:
        """Serialise for Qdrant point payload with normalized provenance keys."""
        meta = dict(self.metadata)
        job_id = meta.get("ingestion_job_id") or meta.get("job_id")
        if job_id is not None:
            meta.setdefault("job_id", str(job_id))
            meta.setdefault("ingestion_job_id", str(job_id))

        doc_id = meta.get("doc_id") or meta.get("source_document_id")
        if doc_id is not None:
            meta.setdefault("doc_id", str(doc_id))
            meta.setdefault("source_document_id", str(doc_id))

        if not meta.get("section_path") and isinstance(meta.get("heading_path"), list) and meta["heading_path"]:
            meta["section_path"] = " > ".join(str(h) for h in meta["heading_path"] if h)

        return {
            "chunk_id": self.chunk_id,
            "source_name": self.source_name,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "token_count": self.token_count,
            "artifact_type": "source_chunk",
            **meta,
        }


@dataclass
class SectionBlock:
    """A document section extracted from a PDF bookmark tree or heading heuristic."""

    heading_path: list[str]  # headings from root to this section
    depth: int  # 0 = top-level chapter, 1 = section, 2 = subsection
    page_start: int  # 0-indexed
    page_end: int  # 0-indexed, inclusive
    text: str  # raw extracted text for this section span


# ---------------------------------------------------------------------------
# Tokenization helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[int]:
    """Encode text to token IDs using cl100k_base."""
    return ENCODING.encode(text)


def _detokenize(token_ids: list[int]) -> str:
    """Decode token IDs back to text."""
    return ENCODING.decode(token_ids)


def _split_tokens(
    tokens: list[int],
    max_tokens: int,
    overlap_tokens: int,
) -> list[list[int]]:
    """
    Sliding-window split of a flat token list into overlapping chunks.

    Args:
        tokens:         Full token sequence for a document/page.
        max_tokens:     Maximum tokens per chunk (inclusive).
        overlap_tokens: Number of tokens shared between consecutive chunks.

    Returns:
        List of token-ID lists, each no longer than max_tokens.
    """
    if not tokens:
        return []

    stride = max_tokens - overlap_tokens
    if stride <= 0:
        raise ValueError(f"overlap ({overlap_tokens}) must be less than max_tokens ({max_tokens})")

    chunks: list[list[int]] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunks.append(tokens[start:end])
        if end == len(tokens):
            break
        start += stride

    return chunks
