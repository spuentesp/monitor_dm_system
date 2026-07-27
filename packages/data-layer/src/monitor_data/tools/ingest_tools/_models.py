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

# Tiktoken encoding — cl100k_base is used by Claude / OpenAI text-embedding-3-*
# Using a consistent encoding across all models avoids chunk-size drift.
ENCODING = tiktoken.get_encoding("cl100k_base")

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
        """Serialise for Qdrant point payload."""
        return {
            "chunk_id": self.chunk_id,
            "source_name": self.source_name,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "token_count": self.token_count,
            "artifact_type": "source_chunk",
            **self.metadata,
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
